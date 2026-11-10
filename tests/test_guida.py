"""Guide (modello Itinera), link «Guida» per pagina, testata con il menu dell'account."""
import pytest

from app.extensions import db
from app.guida import AIUTO, GUIDE, SENZA_AIUTO, leggi, sezione
from app.models import Candidatura

from conftest import crea_edizione, crea_utente, login
from test_rotte import client_di


def test_ogni_pagina_ha_la_sua_sezione(app):
    """Pagina nuova dell'area, del back-office o dell'accesso: va messa in AIUTO (o SENZA_AIUTO)."""
    mancanti = [r.endpoint for r in app.url_map.iter_rules()
                if "GET" in r.methods and r.endpoint.split(".")[0] in ("area", "admin", "auth")
                and r.endpoint not in SENZA_AIUTO and not sezione(r.endpoint)]
    assert mancanti == []


def test_le_sezioni_esistono(app):
    titoli = {slug: {v["titolo"] for v in leggi(slug)[1]} for slug in GUIDE}
    assert [(e, s) for e, (g, s) in AIUTO.items() if s not in titoli[g]] == []


def test_guida_pubblica(client):
    html = client.get("/guida").get_data(as_text=True)
    assert "Indice" in html and 'id="invito-alla-lettura"' in html
    assert client.get("/guida/inesistente").status_code == 404


def test_guida_del_comitato_riservata(app, client):
    assert client.get("/guida/comitato").status_code == 302  # al login
    assert client_di(app, crea_utente()).get("/guida/comitato").status_code == 403
    assert client_di(app, crea_utente(ruolo="comitato", edizioni=[])).get("/guida/comitato").status_code == 403
    assert "Doppioni" in client_di(app, crea_utente(ruolo="comitato", edizioni=[crea_edizione()])).get(
        "/guida/comitato").get_data(as_text=True)


def test_link_alla_sezione(app):
    docente = client_di(app, crea_utente())
    assert 'href="/guida#larea-personale">Guida: L&#39;area personale' in docente.get("/area/").get_data(as_text=True)
    comitato = client_di(app, crea_utente(ruolo="comitato", edizioni=[crea_edizione()]))
    assert 'href="/guida/comitato#il-cruscotto"' in comitato.get("/admin/").get_data(as_text=True)


def test_menu_dell_account(app):
    u = crea_utente(verificata=False)
    db.session.add(Candidatura(utente=u, edizione=crea_edizione(), stato="inviata"))
    db.session.commit()
    html = client_di(app, u).get("/").get_data(as_text=True)
    assert 'class="utente"' in html and u.email in html and "Candidatura " in html
    assert "Email da confermare" in html and 'class="menu-gestione"' not in html
    html = client_di(app, crea_utente(ruolo="comitato")).get("/admin/").get_data(as_text=True)
    assert 'class="menu-gestione" href="/admin/" aria-current="page"' in html


def test_esci_solo_con_post(app, client):
    u = crea_utente()
    login(client, u)
    assert client.get("/esci").status_code == 405
    assert client.post("/esci").status_code == 302
    assert client.get("/area/").status_code == 302  # uscito: torna al login
