"""Pagina di lezioni e UD, UD delle edizioni passate dal programma, materiali caricati
dall'admin dentro la UD, copertine della bibliografia per ISBN."""
import io
from datetime import date

import pytest

from app.edizioni_precedenti import ud_dal_programma
from app.extensions import db
from app.models import (Candidatura, EdizionePersona, Materiale, Persona, ProgrammaVoce,
                        PropostaLettura, ZoteroItem)
from app.ricerca_libri import scarica_copertine

from conftest import crea_edizione, crea_utente
from test_rotte import client_di


def crea_ud(ed=None, ruolo="docente", titolo="Albi illustrati dei fuoriusciti"):
    ed = ed or crea_edizione(stato="conclusa")
    ep = EdizionePersona(edizione=ed, persona=Persona(nome="Caterina", cognome="Inesi"),
                         ruolo=ruolo, titolo_lezione=titolo)
    db.session.add(ep)
    db.session.commit()
    return ep


def materiale(**kw):
    m = Materiale(titolo=kw.pop("titolo", "Slide della UD"), tipo="slide", stato="pubblicato",
                  visibilita="pubblico", url="https://esempio.it/slide", **kw)
    db.session.add(m)
    db.session.commit()
    return m


# ------------------------------------------------------------------ UD dal programma
def test_ud_dal_programma_idempotente(app):
    ed = crea_edizione(stato="conclusa")
    for i, (tipo, titolo, chi) in enumerate([("unita_didattiche", "UD uno", "Ada Alvaro"),
                                             ("unita_didattiche", "UD due", "Giulio Massimo Girola Ceccacci"),
                                             ("unita_didattiche", "Senza nome", None),
                                             ("lezione", "Una lezione", "Stefano Gallo")]):
        db.session.add(ProgrammaVoce(edizione=ed, giorno=date(2023, 10, 30), tipo=tipo,
                                     titolo=titolo, relatori=chi, ordine=i))
    db.session.commit()
    assert ud_dal_programma(ed) == 2
    assert ud_dal_programma(ed) == 0
    db.session.commit()
    ud = sorted((ep.titolo_lezione, ep.persona.cognome) for ep in ed.persone if ep.ruolo == "docente")
    assert ud == [("UD due", "Ceccacci"), ("UD uno", "Alvaro")]


# ------------------------------------------------------------------ pagina pubblica
def test_pagina_ud_e_lezione(app):
    ud = crea_ud()
    ud.descrizione = "Un **abstract**"
    materiale(edizione=ud.edizione, lezione=ud)
    materiale(edizione=ud.edizione, lezione=ud, titolo="Bozza nascosta").stato = "in_revisione"
    materiale(edizione=ud.edizione, lezione=ud, titolo="Solo comitato").visibilita = "privato"
    db.session.commit()
    html = client_di(app).get(f"/edizioni/{ud.edizione.slug}/interventi/{ud.id}").get_data(as_text=True)
    assert "Albi illustrati dei fuoriusciti" in html and "Caterina Inesi" in html
    assert "<strong>abstract</strong>" in html and "Unità didattica" in html
    assert "Slide della UD" in html
    assert "Bozza nascosta" not in html and "Solo comitato" not in html
    assert "Carica un materiale" not in html  # niente riquadro admin per gli anonimi
    lez = crea_ud(ed=ud.edizione, ruolo="relatore", titolo="Esilio e migrazione")
    assert "Lezione" in client_di(app).get(f"/edizioni/{ud.edizione.slug}/interventi/{lez.id}").get_data(as_text=True)


def test_pagina_404(app):
    ud = crea_ud()
    altra = crea_edizione(stato="conclusa")
    comitato = crea_ud(ed=ud.edizione, ruolo="comitato")
    bozza = crea_ud(ed=crea_edizione(stato="bozza"))
    c = client_di(app)
    assert c.get(f"/edizioni/{altra.slug}/interventi/{ud.id}").status_code == 404
    assert c.get(f"/edizioni/{ud.edizione.slug}/interventi/{comitato.id}").status_code == 404
    assert c.get(f"/edizioni/{bozza.edizione.slug}/interventi/{bozza.id}").status_code == 404


def test_programma_collega_la_pagina(app):
    ud = crea_ud()
    db.session.add(ProgrammaVoce(edizione=ud.edizione, giorno=date(2023, 10, 30),
                                 tipo="unita_didattiche", titolo=ud.titolo_lezione, relatori="Caterina Inesi"))
    db.session.commit()
    html = client_di(app).get(f"/edizioni/{ud.edizione.slug}").get_data(as_text=True)
    assert f'href="/edizioni/{ud.edizione.slug}/interventi/{ud.id}"' in html


def test_ud_della_candidatura_senza_dati_personali(app):
    ed = crea_edizione(stato="conclusa")
    u = crea_utente()
    c = Candidatura(utente=u, edizione=ed, stato="ammessa", titolo_ud="La mia UD",
                    abstract="<script>x</script> testo", discipline="Storia")
    db.session.add(c)
    db.session.add(PropostaLettura(candidatura=c, campi={"title": "Libro"}, zotero_key="ZK1",
                                   stato="approvata", motivazione="Perché sì"))
    db.session.add(ZoteroItem(key="ZK1", tipo="book", titolo="Libro consigliato", eliminato=False))
    db.session.commit()
    html = client_di(app).get(f"/edizioni/{ed.slug}/unita-didattiche/{c.id}").get_data(as_text=True)
    assert "La mia UD" in html and u.nome_completo in html and "Storia" in html
    assert "Libro consigliato" in html and "Perché sì" in html
    assert "<script>x" not in html  # abstract del docente come testo
    for dato in (u.email, u.telefono, u.residenza, "1980"):
        assert dato not in html
    c.stato = "riserva"
    db.session.commit()
    assert client_di(app).get(f"/edizioni/{ed.slug}/unita-didattiche/{c.id}").status_code == 404


# ------------------------------------------------------------------ admin
@pytest.mark.parametrize("ruolo, atteso", [("docente", 403), ("comitato", 403), ("admin", 302)])
def test_admin_carica_nella_ud(app, ruolo, atteso):
    ud = crea_ud()
    c = client_di(app, crea_utente(ruolo=ruolo))
    r = c.post(f"/admin/interventi/{ud.id}/materiali", content_type="multipart/form-data",
               data={"titolo": "Slide 2023", "tipo": "slide", "visibilita": "pubblico",
                     "file": (io.BytesIO(b"%PDF-1.4 prova"), "slide.pdf")})
    assert r.status_code == atteso
    m = Materiale.query.filter_by(titolo="Slide 2023").first()
    if atteso == 302:
        assert (m.lezione_id, m.edizione_id, m.stato) == (ud.id, ud.edizione_id, "pubblicato")
        r = c.post(f"/admin/interventi/{ud.id}/descrizione", data={"descrizione": "Abstract nuovo"})
        db.session.refresh(ud)
        assert ud.descrizione == "Abstract nuovo"
        assert "Carica un materiale" in c.get(
            f"/edizioni/{ud.edizione.slug}/interventi/{ud.id}").get_data(as_text=True)
    else:
        assert m is None


def test_admin_carica_nella_candidatura(app):
    ed = crea_edizione(stato="conclusa")
    cand = Candidatura(utente=crea_utente(), edizione=ed, stato="ammessa", titolo_ud="UD")
    db.session.add(cand)
    db.session.commit()
    c = client_di(app, crea_utente(ruolo="admin"))
    c.post(f"/admin/candidature/{cand.id}/materiali",
           data={"titolo": "Testo UD", "tipo": "unita_didattica", "visibilita": "registrati",
                 "url": "https://esempio.it/ud"})
    m = Materiale.query.filter_by(titolo="Testo UD").one()
    assert (m.candidatura_id, m.edizione_id) == (cand.id, ed.id)


def test_admin_apre_le_letture_della_ud(app):
    ud = crea_ud()
    assert client_di(app, crea_utente(ruolo="admin")).get(f"/area/lezioni/{ud.id}/letture").status_code == 200
    assert client_di(app, crea_utente(ruolo="relatore")).get(f"/area/lezioni/{ud.id}/letture").status_code == 404


# ------------------------------------------------------------------ copertine per ISBN
def test_scarica_copertine(app):
    for key, isbn in (("A", "9788833142586"), ("B", "9788849711165"), ("C", "9788837228897")):
        db.session.add(ZoteroItem(key=key, tipo="book", titolo=key, isbn=isbn, eliminato=False))
    db.session.add(ZoteroItem(key="W", tipo="webpage", titolo="sito", eliminato=False))
    db.session.commit()

    def candidati(isbn):
        if isbn.endswith("586"):
            yield "https://non-ammesso.example/x.jpg"
            yield "https://covers.openlibrary.org/ok.jpg"
        elif isbn.endswith("165"):
            yield "https://covers.openlibrary.org/manca.jpg"
        else:
            raise OSError("quota esaurita")

    def salva(url):
        if "ok" not in url:
            raise ValueError("no")
        return "copertine/ok.jpg"

    assert scarica_copertine(salva=salva, candidati=candidati) == (1, 1)
    stato = {z.key: z.copertina_path for z in ZoteroItem.query}
    assert stato == {"A": "copertine/ok.jpg", "B": "", "C": None, "W": None}
    html = client_di(app).get("/bibliografia").get_data(as_text=True)
    assert "/bibliografia/copertine/A" in html and "copertina-vuota" in html
