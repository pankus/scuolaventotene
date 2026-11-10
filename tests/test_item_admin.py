"""L'admin corregge una voce dell'invito alla lettura (scritta in Zotero) e ne gestisce la copertina."""
import io
import os

import pytest

from app import zotero_sync
from app.extensions import db
from app.models import ZoteroItem
from app.zotero_scrittura import crea_item

from conftest import crea_utente
from test_rotte import client_di

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture
def zot(app, fake_zot, monkeypatch):
    monkeypatch.setattr(zotero_sync, "client", lambda: fake_zot)
    return fake_zot


@pytest.fixture
def libro(app, zot):
    zi = crea_item(zot, "book", {"title": "Prima", "ISBN": "9788833142586"},
                   autori="Rossi, Anna\nCentro studi", tag_proposte=False)
    db.session.commit()
    return zi


@pytest.fixture
def admin(app):
    return client_di(app, crea_utente(ruolo="admin"))


@pytest.mark.parametrize("ruolo, atteso", [(None, 302), ("docente", 403), ("comitato", 403), ("admin", 200)])
def test_permessi(app, libro, ruolo, atteso):
    c = client_di(app, crea_utente(ruolo=ruolo) if ruolo else None)
    assert c.get(f"/admin/bibliografia/{libro.key}").status_code == atteso


def test_link_modifica_solo_admin(app, libro, admin):
    assert "/admin/bibliografia/" in admin.get("/bibliografia?tutto=1").get_data(as_text=True)
    assert "/admin/bibliografia/" not in client_di(app).get("/bibliografia?tutto=1").get_data(as_text=True)


def test_modifica_scheda_in_zotero(app, libro, admin, zot):
    html = admin.get(f"/admin/bibliografia/{libro.key}").get_data(as_text=True)
    assert "Rossi, Anna\nCentro studi" in html  # autori precompilati, ente su una riga
    dati = {"azione": "scheda", "versione": libro.version, "title": "Dopo",
            "autori": "Bianchi, Luca", "ISBN": "9788833142586"}
    assert admin.post(f"/admin/bibliografia/{libro.key}", data=dati).status_code == 302
    zi = db.session.get(ZoteroItem, libro.key)
    assert zi.titolo == "Dopo" and zi.autori == "Bianchi, Luca"
    assert zot.record[libro.key]["data"]["title"] == "Dopo"
    # versione vecchia: Zotero risponde 412, niente sovrascritto
    html = admin.post(f"/admin/bibliografia/{libro.key}", data={**dati, "title": "Vecchia"},
                      follow_redirects=True).get_data(as_text=True)
    assert "ricarica" in html and zot.record[libro.key]["data"]["title"] == "Dopo"


def test_copertina_caricata_e_tolta(app, libro, admin):
    r = admin.post(f"/admin/bibliografia/{libro.key}", content_type="multipart/form-data",
                   data={"azione": "file", "file": (io.BytesIO(PNG), "c.png")})
    assert r.status_code == 302
    zi = db.session.get(ZoteroItem, libro.key)
    percorso = os.path.join(app.config["UPLOAD_FOLDER"], zi.copertina_path)
    assert zi.copertina_path.endswith(".png") and os.path.isfile(percorso)
    admin.post(f"/admin/bibliografia/{libro.key}", data={"azione": "togli"})
    db.session.refresh(zi)
    assert zi.copertina_path == "" and not os.path.exists(percorso)


def test_copertina_rifiutata(app, libro, admin):
    finto = admin.post(f"/admin/bibliografia/{libro.key}", content_type="multipart/form-data",
                       data={"azione": "file", "file": (io.BytesIO(b"<svg>"), "c.png")},
                       follow_redirects=True).get_data(as_text=True)
    assert "non è un&#39;immagine" in finto
    host = admin.post(f"/admin/bibliografia/{libro.key}", follow_redirects=True,
                      data={"azione": "url", "url": "https://esempio.it/c.jpg"}).get_data(as_text=True)
    assert "non ammesso" in host
    assert db.session.get(ZoteroItem, libro.key).copertina_path is None


def test_cerca_per_isbn_non_perde_la_vecchia(app, libro, admin, monkeypatch):
    from app.views import admin as vista
    libro.copertina_path = "copertine/vecchia.png"
    db.session.commit()

    def nessuna(isbn):
        raise ValueError("nessuna copertina trovata per questo ISBN")
    monkeypatch.setattr(vista, "cerca_copertina", nessuna)
    admin.post(f"/admin/bibliografia/{libro.key}", data={"azione": "cerca"})
    assert db.session.get(ZoteroItem, libro.key).copertina_path == "copertine/vecchia.png"
    monkeypatch.setattr(vista, "cerca_copertina", lambda isbn: "copertine/nuova.jpg")
    admin.post(f"/admin/bibliografia/{libro.key}", data={"azione": "cerca"})
    assert db.session.get(ZoteroItem, libro.key).copertina_path == "copertine/nuova.jpg"
