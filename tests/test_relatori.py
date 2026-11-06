"""Ruolo relatore (R2): account collegato alla lezione, materiali della lezione."""
import io

import pytest

from app.extensions import db
from app.models import EdizionePersona, Materiale, Persona

from conftest import crea_edizione, crea_utente
from test_rotte import client_di


def crea_lezione(ed=None, utente=None, titolo="Esilio e migrazione", ordine=1):
    ed = ed or crea_edizione(stato="chiusa")
    p = Persona(nome="Stefano", cognome="Gallo", utente=utente)
    ep = EdizionePersona(edizione=ed, persona=p, ruolo="relatore", titolo_lezione=titolo, ordine=ordine)
    db.session.add(ep)
    db.session.commit()
    return ep


def pdf(nome="slide.pdf"):
    return (io.BytesIO(b"%PDF-1.4 prova"), nome)


# ------------------------------------------------------------------ admin
def test_admin_collega_account(app):
    ep = crea_lezione()
    rel = crea_utente(ruolo="relatore")
    c = client_di(app, crea_utente(ruolo="admin"))
    html = c.get(f"/admin/edizioni/{ep.edizione_id}").get_data(as_text=True)
    assert rel.email in html  # tra gli account proponibili
    r = c.post(f"/admin/edizioni-persone/{ep.id}/lezione",
               data={f"lez{ep.id}-titolo_lezione": "Titolo nuovo", f"lez{ep.id}-ordine": "3",
                     f"lez{ep.id}-utente_id": str(rel.id)})
    assert r.status_code == 302
    db.session.refresh(ep)
    assert (ep.titolo_lezione, ep.ordine, ep.persona.utente_id) == ("Titolo nuovo", 3, rel.id)
    assert rel.lezioni() == [ep]


def test_account_su_una_sola_persona(app):
    rel = crea_utente(ruolo="relatore")
    crea_lezione(utente=rel)
    altra = crea_lezione()
    c = client_di(app, crea_utente(ruolo="admin"))
    c.post(f"/admin/edizioni-persone/{altra.id}/lezione",
           data={f"lez{altra.id}-titolo_lezione": "X", f"lez{altra.id}-ordine": "0",
                 f"lez{altra.id}-utente_id": str(rel.id)})
    db.session.refresh(altra)
    assert altra.persona.utente_id is None


@pytest.mark.parametrize("ruolo", ["comitato", "relatore", "docente"])
def test_solo_admin_collega(app, ruolo):
    ep = crea_lezione()
    c = client_di(app, crea_utente(ruolo=ruolo))
    assert c.post(f"/admin/edizioni-persone/{ep.id}/lezione", data={}).status_code == 403


def test_relatore_non_entra_nel_back_office(app):
    assert client_di(app, crea_utente(ruolo="relatore")).get("/admin/").status_code == 403


# ------------------------------------------------------------------ area del relatore
def test_dashboard_e_materiale_della_lezione(app):
    rel = crea_utente(ruolo="relatore")
    ep = crea_lezione(utente=rel)
    c = client_di(app, rel)
    html = c.get("/area/").get_data(as_text=True)
    assert "Le mie lezioni" in html and "Esilio e migrazione" in html
    r = c.post(f"/area/materiali/nuovo?lezione={ep.id}",
               data={"edizione_id": ep.edizione_id, "titolo": "Slide della lezione", "tipo": "slide",
                     "file": pdf()}, content_type="multipart/form-data")
    assert r.status_code == 302
    m = Materiale.query.one()
    assert (m.lezione_id, m.edizione_id, m.stato) == (ep.id, ep.edizione_id, "in_revisione")


def test_lezione_altrui(app):
    ep = crea_lezione(utente=crea_utente(ruolo="relatore"))
    altro = client_di(app, crea_utente(ruolo="relatore"))
    assert altro.get(f"/area/materiali/nuovo?lezione={ep.id}").status_code == 404
    docente = client_di(app, crea_utente())
    assert docente.get(f"/area/materiali/nuovo?lezione={ep.id}").status_code == 404
    assert "Le mie lezioni" not in docente.get("/area/").get_data(as_text=True)


def test_edizione_fissata_dalla_lezione(app):
    rel = crea_utente(ruolo="relatore")
    ep = crea_lezione(utente=rel)
    altra = crea_edizione(stato="chiusa")
    c = client_di(app, rel)
    c.post(f"/area/materiali/nuovo?lezione={ep.id}",
           data={"edizione_id": altra.id, "titolo": "X", "tipo": "slide", "file": pdf()},
           content_type="multipart/form-data")
    assert Materiale.query.count() == 0  # edizione non tra le scelte: form non valido


# ------------------------------------------------------------------ archivio
def test_archivio_separa_lezioni(app):
    ed = crea_edizione(stato="conclusa")
    ep2 = crea_lezione(ed, titolo="Seconda", ordine=2)
    ep1 = crea_lezione(ed, titolo="Prima", ordine=None)  # ordine mancante (righe vecchie)
    for titolo, lez in (("Materiale B", ep2), ("Materiale A", ep1), ("Bando", None)):
        db.session.add(Materiale(edizione=ed, titolo=titolo, lezione=lez, url="https://x.it",
                                 stato="pubblicato", visibilita="pubblico"))
    db.session.commit()
    html = client_di(app).get(f"/archivio/{ed.slug}").get_data(as_text=True)
    ordine = [html.index(t) for t in ("<h2>Lezioni</h2>", "Materiale A", "Materiale B",
                                      "<h2>Altri materiali</h2>", "Bando")]
    assert ordine == sorted(ordine)
