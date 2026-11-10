"""Sync Zotero -> sito con FakeZot: mai il gruppo vero."""
import pytest

from app.extensions import db
from app.models import ZoteroCollezione, ZoteroItem
from app.zotero_sync import firma, normalizza_isbn, puo_scrivere, sincronizza, verifica


# ------------------------------------------------------------------ normalizzazioni
@pytest.mark.parametrize("testo, atteso", [
    ("978-0-306-40615-7", "9780306406157"),
    ("0306406152", "9780306406157"),                    # ISBN-10 convertito
    ("978-0-306-40615-7 0306406152", "9780306406157"),  # più ISBN nel campo: il primo valido
    ("9780306406158", None),                            # cifra di controllo sbagliata
    ("ISBN 88-06-17471-X", None),                       # X valida solo se il calcolo dà 10
    ("", None), (None, None),
])
def test_normalizza_isbn(testo, atteso):
    assert normalizza_isbn(testo) == atteso


def test_isbn10_con_x():
    assert normalizza_isbn("0-8044-2957-X") == "9780804429573"


def test_firma():
    assert firma("L'età  dell'oro: storia", "book") == firma("l eta dell oro storia", "book")
    assert firma("Titolo", "book") != firma("Titolo", "webpage")
    assert firma("", "book") is None


# ------------------------------------------------------------------ permessi
@pytest.mark.parametrize("accesso, atteso", [
    ({"groups": {"12345": {"library": True, "write": True}}}, True),
    ({"groups": {"all": {"library": True, "write": True}}}, True),
    ({"groups": {"12345": {"library": True}}}, False),
    ({"groups": {"99999": {"write": True}}}, False),
])
def test_puo_scrivere(app, fake_zot, accesso, atteso):
    fake_zot.accesso = accesso
    assert puo_scrivere(fake_zot) is atteso


def test_verifica(app, fake_zot):
    fake_zot.metti_item("A", "Uno")
    assert verifica(fake_zot) == {"item": 1, "versione": fake_zot.versione, "scrittura": True}


# ------------------------------------------------------------------ sync
def _libreria(fz):
    fz.metti_collezione("C1", "Edizione 2026")
    fz.metti_collezione("C2", "Proposte", parent="C1")
    fz.metti_item("A", "Libro uno", collezioni=["C1"], ISBN="0306406152", date="2020")
    fz.metti_item("B", "Libro due", collezioni=["C2"])
    fz.metti_item("N", "nota", tipo="note")
    fz.metti_item("F", "allegato figlio", parentItem="A")


def test_sync_completa(app, fake_zot):
    _libreria(fake_zot)
    s = sincronizza(completa=True, zot=fake_zot)
    assert s["item"] == 2 and s["collezioni"] == 2
    a = db.session.get(ZoteroItem, "A")
    assert a.isbn == "9780306406157" and a.anno == "2020" and a.firma == "libro uno|book"
    assert [c.key for c in a.collezioni] == ["C1"]
    assert db.session.get(ZoteroItem, "N") is None and db.session.get(ZoteroItem, "F") is None


def test_sync_incrementale(app, fake_zot):
    _libreria(fake_zot)
    sincronizza(completa=True, zot=fake_zot)
    fake_zot.metti_item("A", "Libro uno, nuova edizione", collezioni=["C1"])
    fake_zot.cestina("B")
    fake_zot.metti_item("D", "Da eliminare")
    sincronizza(zot=fake_zot)
    fake_zot.elimina("D")

    s = sincronizza(zot=fake_zot)
    assert s["eliminati"] == 1
    assert db.session.get(ZoteroItem, "A").titolo == "Libro uno, nuova edizione"
    assert db.session.get(ZoteroItem, "B").eliminato        # nel cestino: resta, segnato
    assert db.session.get(ZoteroItem, "D") is None          # eliminato davvero: via

    # niente cambiato su Zotero: nessun download
    assert sincronizza(zot=fake_zot)["item"] == 0


def test_ripristino_dal_cestino(app, fake_zot):
    _libreria(fake_zot)
    fake_zot.cestina("B")
    sincronizza(completa=True, zot=fake_zot)
    assert db.session.get(ZoteroItem, "B").eliminato
    fake_zot.cestino.discard("B")
    fake_zot.record["B"]["data"]["version"] = fake_zot._bump()
    sincronizza(zot=fake_zot)
    assert not db.session.get(ZoteroItem, "B").eliminato


def test_collezione_nel_cestino_con_sottocollezioni(app, fake_zot):
    _libreria(fake_zot)
    sincronizza(completa=True, zot=fake_zot)
    fake_zot.collezioni["C1"]["deleted"] = True
    fake_zot._bump()
    sincronizza(zot=fake_zot)
    assert ZoteroCollezione.query.count() == 0              # C1 e la figlia C2


def test_nessuna_collezione_scaricata_non_cancella(app, fake_zot):
    _libreria(fake_zot)
    sincronizza(completa=True, zot=fake_zot)
    fake_zot.collezioni.clear()
    fake_zot._bump()
    s = sincronizza(zot=fake_zot)
    assert ZoteroCollezione.query.count() == 2 and s["avvisi"]


def test_pagina_bibliografia(app, client, fake_zot):
    _libreria(fake_zot)
    fake_zot.cestina("B")
    sincronizza(completa=True, zot=fake_zot)
    r = client.get("/bibliografia?tutto=1")
    assert r.status_code == 200
    assert b"Libro uno" in r.data and b"Libro due" not in r.data   # il cestino non si vede
    assert client.get("/bibliografia?collezione=C1&q=uno").status_code == 200
