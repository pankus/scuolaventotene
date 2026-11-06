"""Candidatura a passi e invito alla lettura del docente (F5)."""
import io
import os
from datetime import date, timedelta

import docx
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


def test_letture_in_qualsiasi_momento(app, bozza):
    c, client = bozza
    client.post(url(c), data=LIBRO)
    (p,) = c.letture
    c.stato = "inviata"
    db.session.commit()
    # prima della scadenza: si aggiunge, si modifica, si elimina
    client.post(url(c), data={**LIBRO, "title": "Aggiunta dopo l'invio"})
    assert len(c.letture) == 2 and c.letture[1].momento == "iscrizione"
    assert client.post(f"/area/candidatura/{c.id}/letture/{c.letture[1].id}/elimina").status_code == 302
    # lettura già riveduta dal comitato: ferma
    p.stato = "approvata"
    db.session.commit()
    assert client.post(f"/area/candidatura/{c.id}/letture/{p.id}/elimina").status_code == 400
    # scadenza passata: si aggiunge ancora (momento post_scuola), fino a MAX_LETTURE in tutto
    c.edizione.scadenza_candidature = date.today() - timedelta(days=1)
    db.session.commit()
    for i in range(MAX_LETTURE):
        client.post(url(c), data={**LIBRO, "title": f"Aggiunta tardiva {i}"})
    assert len(c.letture) == MAX_LETTURE
    assert {x.momento for x in c.letture[1:]} == {"post_scuola"}
    assert "Salva la lettura" not in client.get(url(c)).get_data(as_text=True)  # limite raggiunto
    # ritirata: chiusa
    client.post(f"/area/candidatura/{c.id}/letture/{c.letture[-1].id}/elimina")
    c.stato = "ritirata"
    db.session.commit()
    client.post(url(c), data={**LIBRO, "title": "Dopo il ritiro"})
    assert len(c.letture) == MAX_LETTURE - 1


@pytest.mark.parametrize("stato, scadenza, modificabile", [
    ("bozza", 1, True), ("inviata", 1, True), ("in_valutazione", 1, True),
    ("inviata", -1, False), ("bozza", -1, False), ("ammessa", 1, False), ("non_ammessa", 1, False),
    ("ritirata", 1, False)])
def test_candidatura_modificabile(app, stato, scadenza, modificabile):
    ed = crea_edizione(scadenza=date.today() + timedelta(days=scadenza))
    c = Candidatura(utente=crea_utente(), edizione=ed, stato=stato)
    db.session.add(c)
    db.session.commit()
    assert c.modificabile is modificabile


def _docx(caratteri):
    d = docx.Document()
    d.add_paragraph("x" * caratteri)
    buf = io.BytesIO()
    d.save(buf)
    buf.seek(0)
    return buf, "proposta.docx"


def test_modifica_proposta_dopo_invio(app):
    docente = crea_utente()
    ed = crea_edizione()
    client = client_di(app, docente)
    pagina = f"/area/candidatura/edizione/{ed.slug}"
    client.post(pagina, data={"tipo": "borsista", "titolo_ud": "Prima", "file": _docx(7000)},
                content_type="multipart/form-data")
    c = Candidatura.query.one()
    c.stato = "inviata"
    db.session.commit()
    file_inviato = c.file_path
    assert "Salva le modifiche" in client.get(pagina).get_data(as_text=True)
    # file fuori dai limiti del bando: resta la versione inviata
    html = client.post(pagina, data={"tipo": "borsista", "titolo_ud": "Seconda", "file": _docx(100)},
                       content_type="multipart/form-data").get_data(as_text=True)
    db.session.refresh(c)
    assert "Modifiche non salvate" in html and (c.titolo_ud, c.file_path) == ("Prima", file_inviato)
    assert os.listdir(os.path.join(app.config["UPLOAD_FOLDER"], "candidature", ed.slug)) == [
        os.path.basename(file_inviato)]  # il file scartato non resta sul disco
    # modifica valida: salvata, sempre inviata, vecchio file eliminato
    r = client.post(pagina, data={"tipo": "borsista", "titolo_ud": "Seconda", "file": _docx(7500)},
                    content_type="multipart/form-data")
    db.session.refresh(c)
    assert r.headers["Location"].endswith(f"/area/candidatura/{c.id}")
    assert (c.titolo_ud, c.stato, c.n_caratteri) == ("Seconda", "inviata", 7500)
    assert not os.path.exists(os.path.join(app.config["UPLOAD_FOLDER"], file_inviato))
    # dopo l'esito: niente modifiche
    c.stato = "ammessa"
    db.session.commit()
    assert client.get(pagina).headers["Location"].endswith(f"/area/candidatura/{c.id}")
    client.post(pagina, data={"tipo": "borsista", "titolo_ud": "Terza"})
    assert db.session.get(Candidatura, c.id).titolo_ud == "Seconda"


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
