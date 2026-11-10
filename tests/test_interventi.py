"""Interventi (lezioni e UD) con più autori: vincolo edizione + ruolo, materiali e letture
condivisi, più interventi della stessa persona nella stessa edizione."""
import io

import pytest

from app.extensions import db
from app.models import EdizionePersona, Intervento, Materiale, Persona

from conftest import crea_edizione, crea_intervento, crea_utente
from test_rotte import client_di


def _autore(iv, utente, ruolo="relatore", ed=None):
    p = utente.persona or Persona(nome=utente.nome, cognome=utente.cognome, utente=utente)
    ep = EdizionePersona(edizione=ed or iv.edizione, persona=p, ruolo=ruolo)
    db.session.add(ep)
    db.session.flush()
    return ep


def test_vincolo_edizione_e_ruolo(app):
    ed, altra = crea_edizione(), crea_edizione()
    iv = crea_intervento(ed)
    u = crea_utente()
    with pytest.raises(ValueError):
        iv.aggiungi_autore(_autore(iv, u, ruolo="docente"))  # ruolo sbagliato per una lezione
    with pytest.raises(ValueError):
        iv.aggiungi_autore(_autore(iv, u, ed=altra))  # relatore, ma di un'altra edizione
    iv.aggiungi_autore(ep := _autore(iv, u))
    iv.aggiungi_autore(ep)  # due volte: nessun doppione
    assert len(iv.autori) == 2


def test_due_relatori_condividono_la_lezione(app):
    iv = crea_intervento(crea_edizione(stato="chiusa"), titolo="Profughi")
    a, b = crea_utente(), crea_utente()
    for u in (a, b):
        iv.aggiungi_autore(_autore(iv, u))
    db.session.commit()
    assert a.lezioni() == b.lezioni() == [iv]
    r = client_di(app, a).post(f"/area/materiali/nuovo?lezione={iv.id}",
                               data={"edizione_id": iv.edizione_id, "titolo": "Slide", "tipo": "slide",
                                     "file": (io.BytesIO(b"%PDF-1.4"), "s.pdf")},
                               content_type="multipart/form-data")
    assert r.status_code == 302 and Materiale.query.one().intervento_id == iv.id
    html = client_di(app, b).get("/area/").get_data(as_text=True)
    assert "Profughi" in html and "Slide" in html  # il collega vede il materiale caricato
    pagina = client_di(app).get(f"/edizioni/{iv.edizione.slug}/interventi/{iv.id}").get_data(as_text=True)
    assert a.nome_completo in pagina and b.nome_completo in pagina


def test_piu_interventi_della_stessa_persona(app):
    ed = crea_edizione()
    u = crea_utente()
    uno = crea_intervento(ed, titolo="Uno", utente=u)
    due = crea_intervento(ed, titolo="Due", utente=u)
    assert uno.autori == due.autori and EdizionePersona.query.count() == 1
    assert {iv.titolo for iv in u.lezioni()} == {"Uno", "Due"}


def test_admin_aggiunge_e_toglie_autori(app):
    ed = crea_edizione()
    iv = crea_intervento(ed)
    ep = _autore(iv, crea_utente())
    docente = _autore(iv, crea_utente(), ruolo="docente")
    db.session.commit()
    c = client_di(app, crea_utente(ruolo="admin"))
    c.post(f"/admin/interventi/{iv.id}/autori", data={"aggiungi": ep.id})
    c.post(f"/admin/interventi/{iv.id}/autori", data={"aggiungi": docente.id})  # rifiutato
    db.session.expire_all()
    assert ep in iv.autori and docente not in iv.autori
    c.post(f"/admin/interventi/{iv.id}/autori", data={"togli": ep.id})
    db.session.expire_all()
    assert ep not in iv.autori and len(iv.autori) == 1


def test_aggiungi_persona_con_titolo_crea_l_intervento(app):
    ed = crea_edizione()
    c = client_di(app, crea_utente(ruolo="admin"))
    for titolo in ("Prima", "Seconda"):
        c.post(f"/admin/edizioni/{ed.id}/persone", data={"pers-nome": "Anna", "pers-cognome": "Neri",
                                                       "pers-ruolo": "relatore", "pers-titolo_lezione": titolo})
    db.session.expire_all()
    assert sorted(iv.titolo for iv in ed.interventi) == ["Prima", "Seconda"]
    assert EdizionePersona.query.filter_by(edizione_id=ed.id).count() == 1


def test_sposta_rifiutato_se_l_intervento_ha_altri_autori(app):
    ed1, ed2 = crea_edizione(), crea_edizione()
    u = crea_utente()
    iv = crea_intervento(ed1, utente=u)
    iv.aggiungi_autore(_autore(iv, crea_utente()))
    db.session.commit()
    c = client_di(app, crea_utente(ruolo="admin"))
    c.post(f"/admin/utenti/{u.id}/edizione", data={"epid": iv.autori[0].id, "edizione": ed2.id})
    db.session.expire_all()
    assert iv.edizione_id == ed1.id and iv.autori[0].edizione_id == ed1.id


def test_eliminare_l_intervento_tiene_i_materiali(app):
    iv = crea_intervento(crea_edizione())
    db.session.add(Materiale(edizione=iv.edizione, titolo="Slide", intervento=iv, url="https://x.it"))
    db.session.commit()
    client_di(app, crea_utente(ruolo="admin")).post(f"/admin/interventi/{iv.id}/elimina")
    db.session.expire_all()
    assert Intervento.query.count() == 0 and Materiale.query.one().intervento_id is None
