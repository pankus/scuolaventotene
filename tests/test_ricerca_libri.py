"""Ricerca dei libri: fonti online finte (mai Google o Open Library veri)."""
import pytest

from app import ricerca_libri
from app.views import area
from app.zotero_sync import sincronizza

from conftest import crea_utente
from test_rotte import client_di

GOOGLE = {"items": [{"volumeInfo": {
    "title": "Il confino", "subtitle": "storia di un'isola", "authors": ["Anna Rossi"],
    "publishedDate": "2019-05-01", "publisher": "Mimesis",
    "industryIdentifiers": [{"type": "ISBN_10", "identifier": "0306406152"}],
    "imageLinks": {"thumbnail": "http://books.google.com/books/content?id=1"}}}]}
OPENLIB = {"docs": [
    {"title": "Il confino", "subtitle": "storia di un'isola", "author_name": ["Anna Rossi"],
     "first_publish_year": 2019, "publisher": ["Mimesis"], "isbn": ["0306406152", "9780306406157"],
     "cover_i": 42},
    {"title": "Ventotene", "author_name": ["Luca Bianchi"], "first_publish_year": 1990}]}


@pytest.fixture
def rete(monkeypatch):
    """_json finto: risposta per host; un'eccezione al posto della risposta = fonte giù."""
    risposte = {"www.googleapis.com": GOOGLE, "openlibrary.org": OPENLIB}
    chiamate = []

    def finto(url):
        chiamate.append(url)
        r = next(v for h, v in risposte.items() if f"//{h}/" in url)
        if isinstance(r, Exception):
            raise r
        return r
    monkeypatch.setattr(ricerca_libri, "_json", finto)
    area._ricerche.clear()
    return risposte, chiamate


def test_google_books(rete):
    (r,) = ricerca_libri.google_books("confino")
    assert r["titolo"] == "Il confino: storia di un'isola"
    assert r["isbn"] == "9780306406157" and r["anno"] == "2019"
    assert r["copertina_url"] == "https://books.google.com/books/content?id=1"


def test_open_library(rete):
    r = ricerca_libri.open_library("confino")
    assert r[0]["isbn"] == "9780306406157" and r[0]["editore"] == "Mimesis"
    assert r[0]["copertina_url"] == "https://covers.openlibrary.org/b/id/42-M.jpg"
    assert r[1]["isbn"] is None and r[1]["copertina_url"] is None


def test_isbn_cercato_come_isbn(app, rete):
    _, chiamate = rete
    ricerca_libri.cerca("88-06-17471-X o altro", "0306406152", online=True)
    assert any("isbn%3A9780306406157" in u for u in chiamate)       # Google: q=isbn:...
    assert any("isbn=9780306406157" in u for u in chiamate)          # Open Library


def test_fusione_per_isbn(rete):
    online, errori = ricerca_libri.cerca_online("confino")
    assert errori == []
    assert len(online) == 2  # stesso ISBN fuso, "Ventotene" a parte
    fuso = next(r for r in online if r["isbn"])
    assert fuso["fonte"] == "Google Books"  # vince la prima fonte
    assert fuso["copertina_url"].startswith("https://books.google.com")


def test_fonte_giu(rete):
    risposte, _ = rete
    risposte["www.googleapis.com"] = TimeoutError("lenta")
    online, errori = ricerca_libri.cerca_online("confino")
    assert errori == ["google_books"]
    assert {r["fonte"] for r in online} == {"Open Library"}


def test_cerca_in_zotero(app, fake_zot, rete):
    fake_zot.metti_item("A", "Il confino politico", ISBN="9780306406157")
    fake_zot.metti_item("B", "Altro", ISBN="0306406152")
    fake_zot.metti_item("C", "Il confino nel cestino")
    fake_zot.metti_item("D", "Il confino, articolo", tipo="journalArticle")
    fake_zot.cestina("C")
    sincronizza(zot=fake_zot)
    assert [z["key"] for z in ricerca_libri.cerca_zotero("confino", tipo="book")] == ["A"]
    assert [z["key"] for z in ricerca_libri.cerca_zotero("confino", tipo="journalArticle")] == ["D"]
    assert [z["key"] for z in ricerca_libri.cerca_zotero("politico rossi")] == ["A"]  # parole in titolo e autori
    assert ricerca_libri.cerca_zotero("confino bianchi") == []
    assert {z["key"] for z in ricerca_libri.cerca_zotero("nulla", "9780306406157")} == {"A", "B"}
    assert [z["key"] for z in ricerca_libri.cerca_zotero("rossi", tipo="book")] == ["B", "A"]  # per autore


# ------------------------------------------------------------------ rotta
def test_rotta(app, rete):
    assert client_di(app).get("/area/letture/cerca?q=confino").status_code == 302
    c = client_di(app, crea_utente())
    assert c.get("/area/letture/cerca?q=co").status_code == 400
    d = c.get("/area/letture/cerca?q=confino").get_json()
    assert set(d) == {"zotero", "online", "errori"} and d["online"] == [] and not rete[1]  # solo Zotero
    assert c.get("/area/letture/cerca?q=confino&online=1").get_json()["online"]
    # i cataloghi online hanno solo libri: per un articolo niente rete
    rete[1].clear()
    assert c.get("/area/letture/cerca?q=confino&online=1&tipo=journalArticle").get_json()["online"] == []
    assert not rete[1]


def test_online_senza_doppioni_zotero(app, fake_zot, rete):
    fake_zot.metti_item("A", "Il confino", ISBN="9780306406157")
    sincronizza(zot=fake_zot)
    d = ricerca_libri.cerca("confino", online=True)
    assert [z["key"] for z in d["zotero"]] == ["A"]
    assert all(r["isbn"] != "9780306406157" for r in d["online"]) and d["online"]  # resta «Ventotene»


def test_limite_ricerche(app, rete):
    c = client_di(app, crea_utente())
    codici = [c.get("/area/letture/cerca?q=confino&online=1").status_code
              for _ in range(area.LIMITE_RICERCHE + 1)]
    assert codici[-2:] == [200, 429]
    assert c.get("/area/letture/cerca?q=confino").status_code == 200  # in Zotero si cerca sempre
    assert client_di(app, crea_utente()).get("/area/letture/cerca?q=confino&online=1").status_code == 200


def test_chiave_google(rete):
    _, chiamate = rete
    ricerca_libri.google_books("confino", chiave="K123")
    ricerca_libri.google_books("confino")
    assert "key=K123" in chiamate[0] and "key=" not in chiamate[1]
