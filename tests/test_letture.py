"""Proposte di lettura e revisione del comitato (FakeZot, mai il gruppo vero)."""
import io

import pytest

from app import utils, zotero_sync
from app.extensions import db
from app.models import Candidatura, PropostaLettura, ZoteroCollezione, ZoteroItem
from app.zotero_sync import sincronizza

from conftest import crea_edizione, crea_utente
from test_rotte import client_di


@pytest.fixture
def zot(app, fake_zot, monkeypatch):
    monkeypatch.setattr(zotero_sync, "client", lambda: fake_zot)
    fake_zot.metti_collezione("COL26", "Invito alla lettura 2026")
    return fake_zot


def crea_proposta(stato_candidatura="inviata", collezione="COL26", **kw):
    ed = crea_edizione()
    ed.zotero_collection_key = collezione
    docente = crea_utente()
    c = Candidatura(utente=docente, edizione=ed, stato=stato_candidatura)
    p = PropostaLettura(candidatura=c, tipo=kw.pop("tipo", "book"),
                        campi=kw.pop("campi", {"title": "Il confino fascista", "autori": "Rossi, Anna",
                                               "date": "2019"}),
                        motivazione="La uso in classe da anni", **kw)
    db.session.add(p)
    db.session.commit()
    return p


def approva(c, p, **dati):
    return c.post(f"/admin/letture/{p.id}", data={"azione": "approva", "title": p.campi["title"],
                                                  "autori": p.campi.get("autori", ""), **dati})


# ------------------------------------------------------------------ permessi
@pytest.mark.parametrize("ruolo, atteso", [(None, 302), ("docente", 403), ("comitato", 200), ("admin", 200)])
def test_permessi(app, zot, ruolo, atteso):
    p = crea_proposta()
    c = client_di(app, crea_utente(ruolo=ruolo) if ruolo else None)
    assert c.get("/admin/letture").status_code == atteso
    assert c.get(f"/admin/letture/{p.id}").status_code == atteso
    assert c.post(f"/admin/letture/{p.id}", data={"azione": "rifiuta"}).status_code in (atteso, 302)
    if atteso != 200:
        assert db.session.get(PropostaLettura, p.id).stato == "proposta"


def test_bozza_non_visibile(app, zot):
    p = crea_proposta(stato_candidatura="bozza")
    assert client_di(app, crea_utente(ruolo="comitato")).get(f"/admin/letture/{p.id}").status_code == 404


# ------------------------------------------------------------------ approvazione
def test_approva_crea_in_zotero(app, zot):
    sincronizza(zot=zot)
    p = crea_proposta()
    docente = p.candidatura.utente
    c = client_di(app, crea_utente(ruolo="comitato"))
    r = approva(c, p, title="Il confino fascista (1926-1943)", ISBN="0306406152",
                nota_comitato="Ottima scelta")
    assert r.status_code == 302

    p = db.session.get(PropostaLettura, p.id)
    assert p.stato == "approvata" and p.zotero_key and p.deciso_da_id
    assert p.campi["title"] == "Il confino fascista (1926-1943)"
    inviato = zot.creati[0]
    ed = p.candidatura.edizione
    assert inviato["collections"] == [ed.zotero_docenti_key]
    assert zot.collezioni[ed.zotero_docenti_key]["name"] == "Docenti"
    assert zot.collezioni[ed.zotero_docenti_key]["parentCollection"] == "COL26"
    assert inviato["tags"] == [{"tag": "proposta-docenti"}]
    testo = repr(inviato)
    for privato in (docente.nome_completo, docente.email, docente.cognome, "La uso in classe"):
        assert privato not in testo
    zi = db.session.get(ZoteroItem, p.zotero_key)
    assert zi.isbn == "9780306406157" and [k.key for k in zi.collezioni] == [ed.zotero_docenti_key]


def test_approva_collega_esistente(app, zot):
    zot.metti_item("ESIST", "Il confino fascista", date="2019")
    sincronizza(zot=zot)
    p = crea_proposta()
    c = client_di(app, crea_utente(ruolo="comitato"))
    html = c.get(f"/admin/letture/{p.id}").get_data(as_text=True)
    assert "Il confino fascista" in html
    assert 'data-ricerca-url="/area/letture/cerca"' in html and "js/letture.js" in html
    approva(c, p, zotero_key="ESIST")

    assert not zot.creati
    assert db.session.get(PropostaLettura, p.id).zotero_key == "ESIST"
    data = zot.record["ESIST"]["data"]
    ed = db.session.get(PropostaLettura, p.id).candidatura.edizione
    assert ed.zotero_docenti_key in data["collections"] and {"tag": "proposta-docenti"} in data["tags"]


def test_approva_senza_collezione(app, zot):
    p = crea_proposta(collezione=None)
    approva(client_di(app, crea_utente(ruolo="comitato")), p)
    assert db.session.get(PropostaLettura, p.id).stato == "proposta"
    assert not zot.creati


def test_rifiuta_e_approvata_bloccata(app, zot):
    p = crea_proposta()
    c = client_di(app, crea_utente(ruolo="comitato"))
    c.post(f"/admin/letture/{p.id}", data={"azione": "rifiuta", "nota_comitato": "Fuori tema"})
    p = db.session.get(PropostaLettura, p.id)
    assert (p.stato, p.nota_comitato) == ("rifiutata", "Fuori tema")

    approva(c, p)
    assert db.session.get(PropostaLettura, p.id).stato == "approvata"
    assert c.post(f"/admin/letture/{p.id}", data={"azione": "rifiuta"}).status_code == 409


def test_copertina_scaricata(app, zot, monkeypatch):
    monkeypatch.setattr("app.zotero_scrittura.salva_copertina", lambda url: "copertine/x.jpg")
    p = crea_proposta(copertina_url="https://covers.openlibrary.org/b/isbn/9780306406157-L.jpg")
    approva(client_di(app, crea_utente(ruolo="comitato")), p)
    p = db.session.get(PropostaLettura, p.id)
    assert db.session.get(ZoteroItem, p.zotero_key).copertina_path == "copertine/x.jpg"


# ------------------------------------------------------------------ copertine
@pytest.mark.parametrize("url, ok", [
    ("https://covers.openlibrary.org/b/isbn/1-L.jpg", True),
    ("https://ia800100.us.archive.org/x.jpg", True),
    ("https://books.google.com/books/content?id=1", True),
    ("https://images-na.ssl-images-amazon.com/images/P/8833142582.01.LZZZZZZZ.jpg", True),
    ("https://amazon.com.evil.it/x.jpg", False),
    ("http://covers.openlibrary.org/b/isbn/1-L.jpg", False),   # solo https
    ("https://evilarchive.org/x.jpg", False),
    ("https://127.0.0.1/x.jpg", False),
    ("", False),
])
def test_host_copertine(url, ok):
    assert utils.copertina_ammessa(url) is ok


class _Risposta(io.BytesIO):
    def __init__(self, dati, tipo):
        super().__init__(dati)
        from email.message import Message
        self.headers = Message()
        self.headers["Content-Type"] = tipo

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.mark.parametrize("tipo, dati, errore", [
    ("image/jpeg", b"\xff\xd8" + b"x" * 2000, None),
    ("image/gif", b"GIF89a" + b"\x00" * 37, "segnaposto"),  # 1×1 di Amazon quando manca
    ("text/html", b"<html>", "immagine"),
    ("image/png", b"x" * (utils.MAX_COPERTINA + 1), "grande"),
])
def test_salva_copertina(app, monkeypatch, tipo, dati, errore):
    class Opener:
        def open(self, req, timeout):
            return _Risposta(dati, tipo)
    monkeypatch.setattr(utils.urllib.request, "build_opener", lambda *h: Opener())
    url = "https://covers.openlibrary.org/b/isbn/1-L.jpg"
    if errore:
        with pytest.raises(ValueError, match=errore):
            utils.salva_copertina(url)
    else:
        assert utils.salva_copertina(url).startswith("copertine/") and utils.salva_copertina(url).endswith(".jpg")


# ------------------------------------------------------------------ merge in Zotero
def test_merge_sposta_proposte(app, zot):
    zot.metti_item("VECCHIO", "Il confino")
    sincronizza(zot=zot)
    p = crea_proposta(zotero_key="VECCHIO", stato="approvata")
    db.session.get(ZoteroItem, "VECCHIO").copertina_path = "copertine/v.jpg"
    db.session.commit()

    zot.metti_item("NUOVO", "Il confino",
                   relations={"dc:replaces": ["http://zotero.org/groups/12345/items/VECCHIO"]})
    zot.cestina("VECCHIO")
    sincronizza(zot=zot)
    assert db.session.get(PropostaLettura, p.id).zotero_key == "NUOVO"
    assert db.session.get(ZoteroItem, "NUOVO").copertina_path == "copertine/v.jpg"


# ------------------------------------------------------------------ struttura Zotero dell'edizione
def test_sottocollezione_creata_una_volta(app, zot):
    sincronizza(zot=zot)
    p1 = crea_proposta()
    ed = p1.candidatura.edizione
    p2 = PropostaLettura(candidatura=p1.candidatura, tipo="book", campi={"title": "Secondo libro"})
    db.session.add(p2)
    db.session.commit()
    c = client_di(app, crea_utente(ruolo="comitato"))
    assert "Invito alla lettura 2026 › Docenti" in c.get(f"/admin/letture/{p1.id}").get_data(as_text=True)
    approva(c, p1)
    approva(c, p2)
    proposte = [k for k, d in zot.collezioni.items() if d["name"] == "Docenti"]
    assert proposte == [ed.zotero_docenti_key]
    assert all(d["collections"] == proposte for d in zot.creati)


def test_sottocollezione_gia_in_zotero(app, zot):
    """Se "Docenti" c'è già (creata a mano e sincronizzata) si riusa."""
    zot.metti_collezione("ESISTE", "Docenti", parent="COL26")
    sincronizza(zot=zot)
    p = crea_proposta()
    approva(client_di(app, crea_utente(ruolo="comitato")), p)
    assert p.candidatura.edizione.zotero_docenti_key == "ESISTE"
    assert zot.creati[0]["collections"] == ["ESISTE"]


def test_scelta_collezione_edizione(app, zot):
    zot.metti_collezione("COL27", "2027")
    zot.metti_collezione("SUB", "01) Rossi - Lezione", parent="COL27")
    sincronizza(zot=zot)
    ed = crea_edizione()
    ed.zotero_docenti_key = "VECCHIA"
    db.session.commit()
    c = client_di(app, crea_utente(ruolo="admin"))
    html = c.get(f"/admin/edizioni/{ed.id}").get_data(as_text=True)
    assert '<option value="COL27">2027</option>' in html and "01) Rossi" not in html  # solo radici
    dati = {"numero": ed.numero, "anno": ed.anno, "slug": ed.slug, "titolo": ed.titolo, "stato": "aperta",
            "zotero_collection_key": "COL27"}
    c.post(f"/admin/edizioni/{ed.id}", data=dati)
    db.session.refresh(ed)
    assert (ed.zotero_collection_key, ed.zotero_docenti_key) == ("COL27", None)
    c.post(f"/admin/edizioni/{ed.id}", data={**dati, "zotero_collection_key": ""})
    db.session.refresh(ed)
    assert ed.zotero_collection_key is None


def test_pagina_edizione_sotto_albero(app, zot):
    zot.metti_collezione("SUB2", "Relatori", parent="COL26")
    zot.metti_collezione("SUB1", "01) Rossi - Prima", parent="COL26")  # struttura vecchia (2024)
    zot.metti_collezione("PROP", "Docenti", parent="COL26")
    zot.metti_item("R", "Nella radice", collezioni=["COL26"])
    zot.metti_item("L1", "Libro lezione uno", collezioni=["SUB1"])
    zot.metti_item("L2", "Libro lezione due", collezioni=["SUB1", "COL26"])  # anche in radice
    zot.metti_item("RL", "Scelto da un relatore", collezioni=["SUB2"])
    zot.metti_item("P", "Proposto da un docente", collezioni=["PROP"])
    sincronizza(zot=zot)
    ed = crea_edizione()
    ed.zotero_collection_key, ed.zotero_docenti_key = "COL26", "PROP"
    db.session.commit()
    html = client_di(app).get(f"/edizioni/{ed.slug}").get_data(as_text=True)
    ordine = [html.index(t) for t in ("Nella radice", "01) Rossi - Prima", "Libro lezione uno",
                                      "<h3>Relatori</h3>", "Scelto da un relatore", "<h3>Docenti</h3>",
                                      "Proposto da un docente")]
    assert ordine == sorted(ordine)
    assert html.count("Libro lezione due") == 2  # una voce sola: citazione + segnaposto della copertina


def test_doppione_comparso_dopo_apertura(app, zot):
    """Regressione: due schede aperte prima di approvare; la seconda creava un doppione."""
    p1, p2 = crea_proposta(), crea_proposta()
    a, b = client_di(app, crea_utente(ruolo="comitato")), client_di(app, crea_utente(ruolo="comitato"))
    assert 'name="visti" value=""' in b.get(f"/admin/letture/{p2.id}").get_data(as_text=True)
    approva(a, p1, zotero_key="", visti="")
    r = approva(b, p2, zotero_key="", visti="")  # form di b generato quando non c'era nulla
    key = db.session.get(PropostaLettura, p1.id).zotero_key
    assert len(zot.creati) == 1 and db.session.get(PropostaLettura, p2.id).stato == "proposta"
    html = r.get_data(as_text=True)
    assert "possibili doppioni" in html and f'value="{key}" checked' in html
    # visto il doppione, il comitato può collegarlo...
    approva(b, p2, zotero_key=key, visti=key)
    assert len(zot.creati) == 1 and db.session.get(PropostaLettura, p2.id).zotero_key == key


def test_crea_nuovo_confermato(app, zot):
    """Doppione già mostrato e scartato dal comitato: si crea il nuovo record senza altri passi."""
    zot.metti_item("ESIST", "Il confino fascista", date="2019")
    sincronizza(zot=zot)
    p = crea_proposta()
    approva(client_di(app, crea_utente(ruolo="comitato")), p, zotero_key="", visti="ESIST")
    assert len(zot.creati) == 1 and db.session.get(PropostaLettura, p.id).stato == "approvata"
