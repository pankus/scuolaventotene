"""Candidatura a passi e invito alla lettura del docente (F5)."""
import pytest

from app import posta
from app.extensions import db
from app.models import Candidatura, PropostaLettura, ZoteroItem
from app.views.area import MAX_LETTURE

from conftest import crea_edizione, crea_utente
from test_rotte import client_di

LIBRO = {"title": "Il confino fascista", "autori": "Rossi, Anna", "date": "2019",
         "ISBN": "0306406152", "motivazione": "La uso in classe"}


@pytest.fixture
def bozza(app):
    docente = crea_utente()
    c = Candidatura(utente=docente, edizione=crea_edizione(), tipo="uditore")
    db.session.add(c)
    db.session.commit()
    return c, client_di(app, docente)


def url(c, **q):
    return f"/area/candidatura/{c.id}/letture" + ("?" + "&".join(f"{k}={v}" for k, v in q.items()) if q else "")


def test_bozza_porta_al_passo_letture(app):
    ed = crea_edizione()
    c = client_di(app, crea_utente())
    r = c.post(f"/area/candidatura/edizione/{ed.slug}", data={"tipo": "uditore"})
    cand = Candidatura.query.filter_by(edizione_id=ed.id).one()
    assert r.headers["Location"].endswith(f"/area/candidatura/{cand.id}/letture")
    pagina = c.get(url(cand)).get_data(as_text=True)
    assert 'aria-current="step"' in pagina and 'data-ricerca-url="/area/letture/cerca"' in pagina


def test_slug_numerico(app):
    """Regressione: con slug = anno la pagina di candidatura finiva sul dettaglio (404)."""
    ed = crea_edizione()
    ed.slug = "2099"
    db.session.commit()
    c = client_di(app, crea_utente())
    assert c.get("/area/").get_data(as_text=True).count("/area/candidatura/edizione/2099") == 1
    assert c.get("/area/candidatura/edizione/2099").status_code == 200
    c.post("/area/candidatura/edizione/2099", data={"tipo": "uditore"})
    assert Candidatura.query.filter_by(edizione_id=ed.id).count() == 1


def test_profilo_nel_percorso(app):
    ed = crea_edizione()
    c = client_di(app, crea_utente())
    r = c.post(f"/area/profilo?edizione={ed.slug}",
               data={"nome": "Ada", "cognome": "Prova", "telefono": "1", "residenza": "Roma",
                     "data_nascita": "1980-01-01", "paese": "Italia", "grado": "", "tipo_contratto": ""})
    assert r.headers["Location"].endswith(f"/area/candidatura/edizione/{ed.slug}")


def test_aggiungi_libro_dalla_ricerca(app, bozza):
    c, client = bozza
    db.session.add(ZoteroItem(key="ESIST", titolo="Il confino fascista", tipo="book"))
    db.session.commit()
    client.post(url(c), data={**LIBRO, "zotero_key": "ESIST",
                              "copertina_url": "https://covers.openlibrary.org/b/id/1-M.jpg"})
    (p,) = c.letture
    assert (p.tipo, p.momento, p.stato) == ("book", "iscrizione", "proposta")
    assert p.campi["title"] == "Il confino fascista" and p.campi["autori"] == "Rossi, Anna"
    assert set(p.campi) == {"title", "autori", "curatori", "date", "publisher", "place", "ISBN",
                            "series", "url"}
    assert p.zotero_key == "ESIST" and p.copertina_url.startswith("https://covers.openlibrary.org")


def test_valori_della_ricerca_non_verificabili(app, bozza):
    c, client = bozza
    client.post(url(c), data={**LIBRO, "zotero_key": "INVENTATA",
                              "copertina_url": "https://127.0.0.1/x.jpg"})
    (p,) = c.letture
    assert p.zotero_key is None and p.copertina_url is None


def test_aggiungi_sito(app, bozza):
    c, client = bozza
    client.post(url(c, tipo="webpage"), data={"title": "Banca dati dei confinati",
                                               "url": "https://example.org", "websiteTitle": "ANPPIA"})
    (p,) = c.letture
    assert p.tipo == "webpage" and set(p.campi) == {"title", "autori", "websiteTitle", "url", "accessDate"}


def test_modifica_ed_elimina(app, bozza):
    c, client = bozza
    client.post(url(c), data=LIBRO)
    (p,) = c.letture
    assert "Il confino fascista" in client.get(url(c, p=p.id)).get_data(as_text=True)
    client.post(url(c), data={**LIBRO, "p": p.id, "title": "Titolo corretto"})
    assert [x.titolo for x in c.letture] == ["Titolo corretto"]

    client.post(f"/area/candidatura/{c.id}/letture/{p.id}/elimina")
    assert PropostaLettura.query.count() == 0


def test_letture_altrui(app, bozza):
    c, client = bozza
    client.post(url(c), data=LIBRO)
    (p,) = c.letture
    altro = client_di(app, crea_utente())
    assert altro.get(url(c)).status_code == 404
    assert altro.post(f"/area/candidatura/{c.id}/letture/{p.id}/elimina").status_code == 404
    # una proposta di un'altra candidatura non si modifica passando il suo id
    mia = Candidatura(utente=crea_utente(), edizione=crea_edizione())
    db.session.add(mia)
    db.session.commit()
    assert client.get(f"/area/candidatura/{mia.id}/letture?p={p.id}").status_code == 404


def test_limite_letture(app, bozza):
    c, client = bozza
    for i in range(MAX_LETTURE + 1):
        client.post(url(c), data={**LIBRO, "title": f"Libro {i}"})
    assert len(c.letture) == MAX_LETTURE


def test_dopo_invio_sola_lettura(app, bozza, monkeypatch):
    monkeypatch.setattr(posta, "_spedisci", lambda m: None)
    c, client = bozza
    client.post(url(c), data=LIBRO)
    (p,) = c.letture
    c.stato = "inviata"
    db.session.commit()
    client.post(url(c), data={**LIBRO, "title": "Aggiunta tardiva"})
    assert len(c.letture) == 1
    assert client.post(f"/area/candidatura/{c.id}/letture/{p.id}/elimina").status_code == 400
    assert "Salva la lettura" not in client.get(url(c)).get_data(as_text=True)


def test_invio_senza_letture_e_email(app, bozza, monkeypatch):
    inviate = []
    monkeypatch.setattr(posta, "_spedisci", inviate.append)
    c, client = bozza
    assert "Consigliato" in client.get(f"/area/candidatura/{c.id}").get_data(as_text=True)
    assert c.problemi_invio() == []  # le letture non bloccano l'invio

    client.post(url(c), data=LIBRO)
    client.post(f"/area/candidatura/{c.id}/invia")
    assert db.session.get(Candidatura, c.id).stato == "inviata"
    testo = next(m for m in inviate if m["To"] == c.utente.email).get_content()
    assert "Il confino fascista (Rossi, Anna)" in testo
    assert "La uso in classe" not in testo
