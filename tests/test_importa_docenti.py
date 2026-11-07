"""Account dei docenti delle edizioni passate (flask importa-docenti) e modulo email ai partecipanti."""
import pytest

from app import posta
from app.cli import importa_docenti
from app.extensions import db
from app.models import Candidatura, EdizionePersona, Persona, Utente

from conftest import crea_edizione, crea_utente, login


@pytest.fixture
def inviate(monkeypatch):
    msgs = []
    monkeypatch.setattr(posta, "_spedisci", msgs.append)
    return msgs


def _ud(ed, nome, cognome, ruolo="docente"):
    p = Persona(nome=nome, cognome=cognome)
    db.session.add(EdizionePersona(edizione=ed, persona=p, ruolo=ruolo, titolo_lezione="UD"))
    db.session.commit()
    return p


def test_importa_docenti(app, inviate):
    ed = crea_edizione(stato="conclusa")
    caiazza, de_lorentiis = _ud(ed, "Tommaso", "Caiazza"), _ud(ed, "Daniela De", "Lorentiis")
    gia = crea_utente()
    righe = [str(ed.anno), "tommaso.caiazza@gmail.com", "Daniela.DeLorentiis@x.it; Daniela; De Lorentiis",
             "", gia.email, "sconosciuta@x.it", "nuova@x.it; Ada; Nuova"]

    importa_docenti(righe)
    db.session.rollback()  # la prova (senza --applica) non lascia niente
    assert Utente.query.count() == 1

    r = importa_docenti(righe)
    db.session.commit()
    esiti = {email: esito for _, email, esito in r}
    assert esiti["sconosciuta@x.it"].startswith("SALTATA") and esiti[gia.email] == "già presente"
    t = Utente.query.filter_by(email="tommaso.caiazza@gmail.com").one()
    d = Utente.query.filter_by(email="daniela.delorentiis@x.it").one()
    assert (t.nome, t.cognome, t.ruolo, caiazza.utente_id) == ("Tommaso", "Caiazza", "docente", t.id)
    assert (d.nome, d.cognome, de_lorentiis.utente_id) == ("Daniela", "De Lorentiis", d.id)
    assert Utente.query.filter_by(email="nuova@x.it").one().persona is None
    assert not inviate

    importa_docenti(righe)  # rilancio: niente doppioni
    db.session.commit()
    assert Utente.query.count() == 4

    app.test_client().post("/password-dimenticata", data={"email": t.email})
    assert len(inviate) == 1 and inviate[0]["To"] == t.email


# ------------------------------------------------------------------ email ai partecipanti
def test_email_partecipanti(app, inviate):
    admin, comitato = crea_utente(ruolo="admin"), crea_utente(ruolo="comitato")
    ed, altra = crea_edizione(stato="conclusa"), crea_edizione()
    relatore, docente_passato = crea_utente(ruolo="relatore"), crea_utente()
    _ud(ed, "Rel", "Atore", ruolo="relatore").utente_id = relatore.id
    _ud(ed, "Doc", "Ente").utente_id = docente_passato.id
    _ud(ed, "Senza", "Account")
    ammesso, escluso = crea_utente(), crea_utente()
    db.session.add_all([Candidatura(utente=ammesso, edizione=ed, stato="ammessa"),
                        Candidatura(utente=escluso, edizione=ed, stato="non_ammessa")])
    db.session.commit()

    c = app.test_client()
    login(c, comitato)
    assert c.get("/admin/email").status_code == 403
    c = app.test_client()
    login(c, admin)
    assert c.get("/admin/email").status_code == 200

    dati = {"edizione_id": ed.id, "docenti": "y", "oggetto": "Avviso", "testo": "Ciao a tutti",
            "azione": "anteprima"}
    html = c.post("/admin/email", data=dati).data.decode()
    assert ammesso.email in html and docente_passato.email in html
    assert escluso.email not in html and relatore.email not in html and "Senza Account" in html
    assert not inviate

    c.post("/admin/email", data=dati | {"relatori": "y", "comitato": "y", "azione": "invia"})
    assert len(inviate) == 1
    m = inviate[0]
    ccn = m["Bcc"]
    for u in (ammesso, docente_passato, relatore, comitato, admin):
        assert u.email in ccn and u.email not in m["To"]
    assert escluso.email not in ccn and m["To"] == app.config["MAIL_MITTENTE"]
    assert "Ciao a tutti" in m.get_content() and "Messaggio automatico" not in m.get_content()

    # altra edizione: nessun docente
    html = c.post("/admin/email", data=dati | {"edizione_id": altra.id}).data.decode()
    assert "Nessun destinatario" in html
