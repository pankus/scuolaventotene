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
    assert inviato["collections"] == ["COL26"]
    assert inviato["tags"] == [{"tag": "proposta-docenti"}]
    testo = repr(inviato)
    for privato in (docente.nome_completo, docente.email, docente.cognome, "La uso in classe"):
        assert privato not in testo
    zi = db.session.get(ZoteroItem, p.zotero_key)
    assert zi.isbn == "9780306406157" and [k.key for k in zi.collezioni] == ["COL26"]


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
    assert "COL26" in data["collections"] and {"tag": "proposta-docenti"} in data["tags"]


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
    monkeypatch.setattr("app.views.admin.salva_copertina", lambda url: "copertine/x.jpg")
    p = crea_proposta(copertina_url="https://covers.openlibrary.org/b/isbn/9780306406157-L.jpg")
    approva(client_di(app, crea_utente(ruolo="comitato")), p)
    p = db.session.get(PropostaLettura, p.id)
    assert db.session.get(ZoteroItem, p.zotero_key).copertina_path == "copertine/x.jpg"


# ------------------------------------------------------------------ copertine
@pytest.mark.parametrize("url, ok", [
    ("https://covers.openlibrary.org/b/isbn/1-L.jpg", True),
    ("https://ia800100.us.archive.org/x.jpg", True),
    ("https://books.google.com/books/content?id=1", True),
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
    ("image/jpeg", b"\xff\xd8 jpeg", None),
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
