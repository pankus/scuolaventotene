"""Dopo la scuola (F6): materiali del modulo e nuove letture dei docenti ammessi."""
import io

import pytest

from app.extensions import db
from app.models import Candidatura, Materiale, PropostaLettura

from conftest import crea_edizione, crea_utente
from test_rotte import client_di

LIBRO = {"title": "Ventotene, isola di confino", "autori": "Bianchi, Luca", "date": "2020"}


def pdf():
    return (io.BytesIO(b"%PDF-1.4 prova"), "modulo.pdf")


def candidatura(stato="ammessa", stato_edizione="chiusa"):
    c = Candidatura(utente=crea_utente(), edizione=crea_edizione(stato=stato_edizione),
                    tipo="borsista", stato=stato, titolo_ud="Il confino in classe")
    db.session.add(c)
    db.session.commit()
    return c


@pytest.mark.parametrize("stato, stato_edizione, atteso", [
    ("ammessa", "chiusa", True), ("ammessa", "conclusa", True), ("ammessa", "aperta", False),
    ("riserva", "conclusa", False), ("inviata", "chiusa", False), ("bozza", "chiusa", False)])
def test_dopo_la_scuola(app, stato, stato_edizione, atteso):
    assert candidatura(stato, stato_edizione).dopo_la_scuola is atteso


def test_carica_materiale_del_modulo(app):
    c = candidatura()
    client = client_di(app, c.utente)
    assert "Carica un materiale" in client.get(f"/area/candidatura/{c.id}").get_data(as_text=True)
    assert f"/area/materiali/nuovo?candidatura={c.id}" in client.get("/area/").get_data(as_text=True)
    assert "Il confino in classe" in client.get(f"/area/materiali/nuovo?candidatura={c.id}").get_data(as_text=True)
    r = client.post(f"/area/materiali/nuovo?candidatura={c.id}",
                    data={"edizione_id": c.edizione_id, "titolo": "Slide del modulo",
                          "tipo": "slide", "file": pdf()}, content_type="multipart/form-data")
    assert r.headers["Location"].endswith(f"/area/candidatura/{c.id}")
    m = Materiale.query.one()
    assert (m.candidatura_id, m.lezione_id, m.edizione_id, m.stato, m.visibilita) == \
        (c.id, None, c.edizione_id, "in_revisione", "pubblico")
    # pubblicato dal comitato: nell'archivio, tra le UD dei docenti
    m.stato = "pubblicato"
    db.session.commit()
    html = client_di(app).get(f"/archivio/{c.edizione.slug}").get_data(as_text=True)
    assert "Unità didattiche dei docenti" in html and "Slide del modulo" in html


def test_upload_chiuso_agli_altri(app):
    c = candidatura()
    altro = client_di(app, crea_utente())
    assert altro.get(f"/area/materiali/nuovo?candidatura={c.id}").status_code == 404
    assert altro.get("/area/materiali/nuovo").status_code == 404  # niente upload libero
    for stato, stato_ed in (("ammessa", "aperta"), ("non_ammessa", "conclusa")):
        x = candidatura(stato, stato_ed)
        assert client_di(app, x.utente).get(f"/area/materiali/nuovo?candidatura={x.id}").status_code == 404


def test_letture_dopo_la_scuola(app):
    c = candidatura()
    vecchia = PropostaLettura(candidatura=c, campi={"title": "Già decisa"}, stato="approvata")
    db.session.add(vecchia)
    db.session.commit()
    client = client_di(app, c.utente)
    url = f"/area/candidatura/{c.id}/letture"
    client.post(url, data=LIBRO)
    nuova = PropostaLettura.query.filter_by(momento="post_scuola").one()
    assert (nuova.stato, nuova.campi["title"]) == ("proposta", LIBRO["title"])
    # la nuova si corregge e si elimina finché non è riveduta; quella dell'iscrizione no
    assert client.get(f"{url}?p={nuova.id}").status_code == 200
    assert client.get(f"{url}?p={vecchia.id}").status_code == 404
    assert client.post(f"{url}/{vecchia.id}/elimina").status_code == 400
    client.post(f"{url}/{nuova.id}/elimina")
    assert PropostaLettura.query.filter_by(momento="post_scuola").count() == 0


def test_letture_chiuse_se_non_ammessa(app):
    c = candidatura("riserva", "conclusa")
    client_di(app, c.utente).post(f"/area/candidatura/{c.id}/letture", data=LIBRO)
    assert PropostaLettura.query.count() == 0


def test_letture_post_scuola_nella_coda_del_comitato(app):
    c = candidatura()
    client_di(app, c.utente).post(f"/area/candidatura/{c.id}/letture", data=LIBRO)
    html = client_di(app, crea_utente(ruolo="comitato")).get(
        f"/admin/letture?edizione={c.edizione_id}").get_data(as_text=True)
    assert LIBRO["title"] in html and "Dopo la scuola" in html
