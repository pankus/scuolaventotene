"""Scrittura in Zotero con FakeZot: mai il gruppo vero."""
import pytest

from app.extensions import db
from app.models import ZoteroCollezione, ZoteroItem
from app.zotero_scrittura import (ErroreScrittura, aggiorna_item, candidati_duplicati, crea_item,
                                  parse_autori, scelte_duplicati)
from app.zotero_sync import sincronizza


def test_parse_autori():
    assert parse_autori("Rossi, Anna\n\nANPPIA\n") == [
        {"creatorType": "author", "lastName": "Rossi", "firstName": "Anna"},
        {"creatorType": "author", "name": "ANPPIA"},
    ]


def test_crea_book(app, fake_zot):
    db.session.add(ZoteroCollezione(key="COL1", nome="Invito alla lettura 2026"))
    zi = crea_item(fake_zot, "book",
                   {"title": "Il confino", "date": "2020", "ISBN": "0306406152",
                    "publisher": "Mimesis", "abstractNote": "non previsto: ignorato"},
                   autori="Rossi, Anna", curatori="Bianchi, Luca", collezioni=["COL1"])
    db.session.commit()

    inviato = fake_zot.creati[0]
    assert inviato["tags"] == [{"tag": app.config["ZOTERO_TAG_PROPOSTE"]}]
    assert inviato["collections"] == ["COL1"]
    assert inviato["abstractNote"] == ""
    assert [c["creatorType"] for c in inviato["creators"]] == ["author", "editor"]
    # nessun campo oltre al template Zotero (niente dati del docente)
    assert set(inviato) <= set(fake_zot.item_template("book")) | {"itemType"}

    assert db.session.get(ZoteroItem, zi.key).isbn == "9780306406157"
    assert zi.firma == "il confino|book"
    assert [c.key for c in zi.collezioni] == ["COL1"]


def test_crea_capitolo_e_articolo(app, fake_zot):
    zi = crea_item(fake_zot, "bookSection", {"title": "Il confino", "bookTitle": "Storia d'Italia",
                                             "pages": "10-30"}, autori="Rossi, Anna", curatori="Bianchi, Luca")
    inviato = fake_zot.creati[0]
    assert inviato["bookTitle"] == "Storia d'Italia" and zi.tipo == "bookSection"
    assert [c["creatorType"] for c in inviato["creators"]] == ["author", "editor"]
    zi = crea_item(fake_zot, "journalArticle", {"title": "Ventotene", "publicationTitle": "Italia contemporanea",
                                                "DOI": "10.1/x", "ISBN": "0306406152"}, autori="Rossi, Anna")
    inviato = fake_zot.creati[1]
    assert inviato["publicationTitle"] == "Italia contemporanea" and inviato["DOI"] == "10.1/x"
    assert "ISBN" not in inviato and zi.firma == "ventotene|journalArticle"


def test_crea_webpage(app, fake_zot):
    zi = crea_item(fake_zot, "webpage", {"title": "Banca dati confinati", "url": "https://x.it",
                                         "ISBN": "0306406152"})
    assert zi.tipo == "webpage" and zi.url == "https://x.it"
    assert "ISBN" not in fake_zot.creati[0]


@pytest.mark.parametrize("tipo, campi", [("thesis", {"title": "X"}), ("book", {"title": "  "})])
def test_crea_rifiutata(app, fake_zot, tipo, campi):
    with pytest.raises(ErroreScrittura):
        crea_item(fake_zot, tipo, campi)
    assert not fake_zot.creati


def test_aggiorna_e_412(app, fake_zot):
    zi = crea_item(fake_zot, "book", {"title": "Prima"}, autori="Rossi, Anna")
    v = zi.version
    zi = aggiorna_item(fake_zot, zi.key, v, {"title": "Dopo"})
    assert zi.titolo == "Dopo" and zi.autori == "Rossi, Anna"  # autori non toccati
    with pytest.raises(ErroreScrittura, match="ricarica"):
        aggiorna_item(fake_zot, zi.key, v, {"title": "Vecchia versione"})


def test_duplicati_locali(app, fake_zot):
    fake_zot.metti_item("A", "L'isola dei confinati", ISBN="978-0-306-40615-7", date="2010")
    fake_zot.metti_item("B", "Altro titolo", date="1999")
    sincronizza(zot=fake_zot)

    locali, _ = candidati_duplicati(None, "book", {"title": "Nuovo", "ISBN": "0306406152"})
    assert [z.key for z in locali] == ["A"]  # stesso ISBN in forma diversa

    locali, _ = candidati_duplicati(None, "book", {"title": "l'isola dei CONFINATI"})
    assert [z.key for z in locali] == ["A"]  # firma, anno mancante = compatibile
    locali, _ = candidati_duplicati(None, "book", {"title": "L'isola dei confinati", "date": "2010"})
    assert [z.key for z in locali] == ["A"]
    locali, _ = candidati_duplicati(None, "book", {"title": "L'isola dei confinati", "date": "2015"})
    assert locali == []  # altra edizione
    locali, _ = candidati_duplicati(None, "webpage", {"title": "L'isola dei confinati"})
    assert locali == []  # altro tipo


def test_duplicati_remoti(app, fake_zot):
    fake_zot.metti_item("A", "Ventotene in cache")
    sincronizza(zot=fake_zot)
    fake_zot.metti_item("C", "Ventotene dopo la sync")
    fake_zot.metti_item("D", "Ventotene tesi", tipo="thesis")

    locali, remoti = candidati_duplicati(fake_zot, "book", {"title": "Ventotene"})
    assert [r["key"] for r in remoti] == ["C"]
    assert [z.key for z in locali] == ["A"]  # in cache: tra i locali, non scartato


def test_titolo_simile_gia_in_cache(app, fake_zot):
    """Regressione: firma diversa, niente ISBN; la ricerca remota lo trova ed era scartato
    perché già in cache, quindi nessun doppione segnalato."""
    fake_zot.metti_item("ESIST", "Il confino fascista. Storia e memoria", date="2019")
    sincronizza(zot=fake_zot)
    scelte, _ = scelte_duplicati(fake_zot, "book", {"title": "Il confino fascista", "date": "2019"})
    assert [k for k, _ in scelte] == ["ESIST"]
