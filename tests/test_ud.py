"""Pagina di lezioni e UD, UD delle edizioni passate dal programma, materiali caricati
dall'admin dentro la UD, copertine della bibliografia per ISBN."""
import io
from datetime import date

import pytest

from app.edizioni_precedenti import lezioni_dal_programma, ud_dal_programma
from app.extensions import db
from app.models import (Candidatura, EdizionePersona, Materiale, Persona, ProgrammaVoce,
                        PropostaLettura, ZoteroItem)
from app.ricerca_libri import scarica_copertine

from conftest import crea_edizione, crea_intervento, crea_utente
from test_rotte import client_di


def crea_ud(ed=None, tipo="ud", titolo="Albi illustrati dei fuoriusciti"):
    return crea_intervento(ed or crea_edizione(stato="conclusa"), tipo=tipo, titolo=titolo,
                           nome="Caterina", cognome="Inesi")


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
    ud = sorted((iv.titolo, a.persona.cognome) for iv in ed.interventi if iv.ud for a in iv.autori)
    assert ud == [("UD due", "Ceccacci"), ("UD uno", "Alvaro")]


def test_lezioni_dal_programma(app):
    ed = crea_edizione(stato="conclusa")
    db.session.add(Persona(nome="Donato", cognome="Di Sanzo"))  # cognome composto già noto
    for i, (tipo, titolo, chi) in enumerate([("lezione", "Asilo", "Stefano Gallo"),
                                             ("lezione", "Profughi", "Donato Di Sanzo, Giovanni Ferrarese"),
                                             ("lezione", "Senza relatori", None),
                                             ("unita_didattiche", "Una UD", "Ada Alvaro")]):
        db.session.add(ProgrammaVoce(edizione=ed, giorno=date(2026, 10, 30), tipo=tipo,
                                     titolo=titolo, relatori=chi, ordine=i))
    db.session.commit()
    assert lezioni_dal_programma(ed) == 2  # una lezione per voce, anche a due voci
    assert lezioni_dal_programma(ed) == 0
    db.session.commit()
    lezioni = {iv.titolo: [a.persona.cognome for a in iv.autori] for iv in ed.interventi}
    assert lezioni == {"Asilo": ["Gallo"], "Profughi": ["Di Sanzo", "Ferrarese"]}
    assert Persona.query.filter_by(cognome="Di Sanzo").count() == 1


# ------------------------------------------------------------------ pagina pubblica
def test_pagina_ud_e_lezione(app):
    ud = crea_ud()
    ud.descrizione = "Un **abstract**"
    materiale(edizione=ud.edizione, intervento=ud)
    materiale(edizione=ud.edizione, intervento=ud, titolo="Bozza nascosta").stato = "in_revisione"
    materiale(edizione=ud.edizione, intervento=ud, titolo="Solo comitato").visibilita = "privato"
    db.session.commit()
    html = client_di(app).get(f"/edizioni/{ud.edizione.slug}/interventi/{ud.id}").get_data(as_text=True)
    assert "Albi illustrati dei fuoriusciti" in html and "Caterina Inesi" in html
    assert "<strong>abstract</strong>" in html and "Unità didattica" in html
    assert "Slide della UD" in html
    assert "Bozza nascosta" not in html and "Solo comitato" not in html
    assert "Carica un materiale" not in html  # niente riquadro admin per gli anonimi
    lez = crea_ud(ed=ud.edizione, tipo="relazione", titolo="Esilio e migrazione")
    assert "Lezione" in client_di(app).get(f"/edizioni/{ud.edizione.slug}/interventi/{lez.id}").get_data(as_text=True)


def test_pagina_404(app):
    ud = crea_ud()
    altra = crea_edizione(stato="conclusa")
    bozza = crea_ud(ed=crea_edizione(stato="bozza"))
    c = client_di(app)
    assert c.get(f"/edizioni/{altra.slug}/interventi/{ud.id}").status_code == 404
    assert c.get(f"/edizioni/{ud.edizione.slug}/interventi/9999").status_code == 404
    assert c.get(f"/edizioni/{bozza.edizione.slug}/interventi/{bozza.id}").status_code == 404


def test_programma_collega_la_pagina(app):
    ud = crea_ud()
    db.session.add(ProgrammaVoce(edizione=ud.edizione, giorno=date(2023, 10, 30),
                                 tipo="unita_didattiche", titolo=ud.titolo, relatori="Caterina Inesi"))
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
        assert (m.intervento_id, m.edizione_id, m.stato) == (ud.id, ud.edizione_id, "pubblicato")
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

    def candidati(isbn, errori):
        if isbn.endswith("586"):
            yield "https://non-ammesso.example/x.jpg"
            yield "https://covers.openlibrary.org/ok.jpg"
        elif isbn.endswith("165"):
            yield "https://covers.openlibrary.org/manca.jpg"
        else:
            errori.append("Google Books (troppe richieste)")

    def salva(url):
        if "ok" not in url:
            raise ValueError("no")
        return "copertine/ok.jpg"

    assert scarica_copertine(salva=salva, candidati=candidati) == (1, 1)
    stato = {z.key: z.copertina_path for z in ZoteroItem.query}
    assert stato == {"A": "copertine/ok.jpg", "B": "", "C": None, "W": None}
    html = client_di(app).get("/bibliografia?tutto=1").get_data(as_text=True)
    assert "/bibliografia/copertine/A" in html and "copertina-vuota" in html


def test_archivio_elenca_anche_le_ud_senza_materiali(app):
    ud = crea_ud()
    html = client_di(app).get(f"/archivio/{ud.edizione.slug}").get_data(as_text=True)
    assert "Unità didattiche dei docenti" in html
    assert f'href="/edizioni/{ud.edizione.slug}/interventi/{ud.id}"' in html


def test_isbn10():
    from app.ricerca_libri import isbn10
    assert isbn10("9788833142586") == "8833142582"
    assert isbn10("9780306406157") == "0306406152"
    assert isbn10("9788800000005")[-1] in "0123456789X"
    assert isbn10("9791032305690") is None and isbn10(None) is None


def test_una_fonte_giu_non_ferma_le_altre(app, monkeypatch):
    import urllib.error
    from app import ricerca_libri

    def quota(*a, **k):
        raise urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None)
    monkeypatch.setattr(ricerca_libri, "open_library", quota)
    monkeypatch.setattr(ricerca_libri, "google_books", quota)
    errori = []
    urls = list(ricerca_libri._copertine_per_isbn("9788833142586", None, errori))
    assert urls[0].startswith("https://covers.openlibrary.org/")
    assert urls[1] == "https://images-na.ssl-images-amazon.com/images/P/8833142582.01.LZZZZZZZ.jpg"
    assert errori == ["Open Library (troppe richieste)", "Google Books (troppe richieste)"]
    # scheda admin: si prende Amazon; se nessuno ha la copertina il messaggio dice chi non ha risposto
    assert ricerca_libri.cerca_copertina(
        "9788833142586", salva=lambda u: "copertine/a.jpg" if "amazon" in u else 1 / 0) == "copertine/a.jpg"
    with pytest.raises(ValueError, match="Google Books \\(troppe richieste\\).*GOOGLE_BOOKS_API_KEY"):
        ricerca_libri.cerca_copertina("9788833142586", salva=lambda u: 1 / 0)


def test_archivio_vuoto(app, client):
    ed = crea_edizione(stato="conclusa")
    html = client.get(f"/archivio/{ed.slug}").get_data(as_text=True)
    assert "non sono ancora stati caricati" in html and f'href="/edizioni/{ed.slug}"' in html
    assert "accedi</a> per vederli" in html
