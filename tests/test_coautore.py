"""UD in due: invito del co-autore, accettazione, regole del bando, permessi, ammissione che
crea la UD come Intervento con entrambi gli autori."""
import pytest

from app import posta
from app.extensions import db
from app.models import Candidatura, EdizionePersona, Intervento

from conftest import crea_edizione, crea_utente
from test_rotte import client_di


@pytest.fixture
def inviate(monkeypatch):
    msgs = []
    monkeypatch.setattr(posta, "_spedisci", msgs.append)
    return msgs


def _bozza(u, ed=None, **kw):
    c = Candidatura(utente=u, edizione=ed or crea_edizione(), tipo="borsista", titolo_ud="Il confino",
                    file_path="x.docx", file_nome="x.docx", **kw)
    db.session.add(c)
    db.session.commit()
    return c


def test_invito_e_accettazione(app, inviate):
    titolare, collega = crea_utente(), crea_utente()
    c = _bozza(titolare)
    t = client_di(app, titolare)
    t.post(f"/area/candidatura/{c.id}/coautore", data={"email": collega.email.upper()})
    db.session.expire_all()
    assert c.coautore_id == collega.id and not c.coautore_confermato
    assert inviate[-1]["To"] == collega.email and "co-autore" in inviate[-1].get_content()
    assert any("non ha ancora accettato" in p for p in c.problemi_invio())
    co = client_di(app, collega)
    assert co.get(f"/area/candidatura/{c.id}").status_code == 404  # prima di accettare non vede
    assert "ti ha invitato come co-autore" in co.get("/area/").get_data(as_text=True)

    co.post(f"/area/candidatura/{c.id}/invito", data={"azione": "accetta"})
    db.session.expire_all()
    assert c.coautore_confermato and c.problemi_invio() == []
    assert c.autori() == [titolare, collega] and collega.mie_candidature() == [c]
    assert co.get(f"/area/candidatura/{c.id}").status_code == 200
    # dalla pagina dell'edizione il co-autore modifica la stessa candidatura, non ne crea un'altra
    co.post(f"/area/candidatura/edizione/{c.edizione.slug}", data={"tipo": "borsista", "titolo_ud": "Il confino in due"})
    db.session.expire_all()
    assert Candidatura.query.count() == 1 and c.titolo_ud == "Il confino in due"
    # ritiro e invito solo del titolare
    assert co.post(f"/area/candidatura/{c.id}/ritira").status_code == 404
    assert co.post(f"/area/candidatura/{c.id}/coautore", data={"togli": "1"}).status_code == 404
    assert client_di(app, crea_utente()).get(f"/area/candidatura/{c.id}").status_code == 404


def test_rifiuto_dell_invito(app, inviate):
    titolare, collega = crea_utente(), crea_utente()
    c = _bozza(titolare, coautore_id=None)
    client_di(app, titolare).post(f"/area/candidatura/{c.id}/coautore", data={"email": collega.email})
    client_di(app, collega).post(f"/area/candidatura/{c.id}/invito", data={"azione": "rifiuta"})
    db.session.expire_all()
    assert c.coautore_id is None


def test_inviti_non_validi(app, inviate):
    titolare, collega = crea_utente(), crea_utente()
    c = _bozza(titolare)
    _bozza(collega, ed=c.edizione)  # il collega ha già una sua candidatura
    t = client_di(app, titolare)
    for email in ("nessuno@esempio.it", titolare.email, collega.email):
        t.post(f"/area/candidatura/{c.id}/coautore", data={"email": email})
        db.session.expire_all()
        assert c.coautore_id is None, email
    assert not inviate


def test_accettare_con_una_propria_candidatura(app, inviate):
    titolare, collega = crea_utente(), crea_utente()
    c = _bozza(titolare)
    client_di(app, titolare).post(f"/area/candidatura/{c.id}/coautore", data={"email": collega.email})
    _bozza(collega, ed=c.edizione)  # creata dopo l'invito
    client_di(app, collega).post(f"/area/candidatura/{c.id}/invito", data={"azione": "accetta"})
    db.session.expire_all()
    assert not c.coautore_confermato


def test_profilo_del_coautore_richiesto(app):
    collega = crea_utente(completo=False)
    c = _bozza(crea_utente(), coautore_id=collega.id, coautore_confermato=True)
    problemi = c.problemi_invio()
    assert any(p.startswith(f"Co-autore ({collega.nome_completo})") and "data di nascita" in p for p in problemi)


def test_ammissione_crea_la_ud_con_gli_autori(app, inviate):
    titolare, collega = crea_utente(), crea_utente()
    c = _bozza(titolare, coautore_id=collega.id, coautore_confermato=True, stato="in_valutazione")
    c.edizione.stato = "chiusa"
    db.session.commit()
    admin = client_di(app, crea_utente(ruolo="admin"))
    admin.post(f"/admin/candidature/{c.id}/stato", data={"st-stato": "ammessa"})
    db.session.expire_all()
    iv = c.intervento
    assert iv.tipo == "ud" and iv.titolo == "Il confino" and iv.edizione_id == c.edizione_id
    assert {a.persona.utente_id for a in iv.autori} == {titolare.id, collega.id}
    assert {a.ruolo for a in iv.autori} == {"docente"}
    assert sorted(m["To"] for m in inviate) == sorted([titolare.email, collega.email])  # esito a entrambi
    admin.post(f"/admin/candidature/{c.id}/stato", data={"st-stato": "ammessa", "st-note_comitato": "x"})
    assert Intervento.query.count() == 1 and EdizionePersona.query.filter_by(ruolo="docente").count() == 2

    pubblico = client_di(app)
    r = pubblico.get(f"/edizioni/{c.edizione.slug}/interventi/{iv.id}")
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/unita-didattiche/{c.id}")
    html = pubblico.get(f"/edizioni/{c.edizione.slug}/unita-didattiche/{c.id}").get_data(as_text=True)
    assert titolare.nome_completo in html and collega.nome_completo in html
    archivio = pubblico.get(f"/archivio/{c.edizione.slug}").get_data(as_text=True)
    assert archivio.count("Il confino") == 1  # una volta sola, non anche come intervento


def test_comando_ud_dalle_candidature(app):
    c = _bozza(crea_utente(), stato="ammessa")
    _bozza(crea_utente(), ed=c.edizione, stato="ammessa").tipo = "uditore"  # niente UD per gli uditori
    db.session.commit()
    runner = app.test_cli_runner()
    assert "1 UD create" in runner.invoke(args=["ud-dalle-candidature"]).output
    assert "0 UD create" in runner.invoke(args=["ud-dalle-candidature"]).output
    assert c.intervento.autori[0].persona.utente_id == c.utente_id
