"""Permessi delle rotte e download controllati, tramite il client di test."""
from datetime import date, timedelta

import pytest

from app.extensions import db
from app.models import Candidatura, Materiale

from conftest import crea_edizione, crea_utente, login


def client_di(app, utente=None):
    """Un client separato per utente, così le sessioni non si mescolano."""
    c = app.test_client()
    if utente:
        login(c, utente)
    return c


# ------------------------------------------------------------------ back-office
@pytest.mark.parametrize("ruolo, atteso", [(None, 302), ("docente", 403), ("comitato", 200), ("admin", 200)])
def test_admin_dashboard_e_csv(app, ruolo, atteso):
    ed = crea_edizione()
    c = client_di(app, crea_utente(ruolo=ruolo) if ruolo else None)
    assert c.get("/admin/").status_code == atteso
    r = c.get(f"/admin/edizioni/{ed.id}/candidature.csv")
    assert r.status_code == atteso
    if atteso == 200:
        assert r.data.decode("utf-8").startswith("﻿Pos.;Cognome")


@pytest.mark.parametrize("url", ["/admin/utenti", "/admin/edizioni/nuova"])
@pytest.mark.parametrize("ruolo, atteso", [("comitato", 403), ("admin", 200)])
def test_rotte_solo_admin(app, url, ruolo, atteso):
    assert client_di(app, crea_utente(ruolo=ruolo)).get(url).status_code == atteso


# ------------------------------------------------------------------ area docente
def test_area_richiede_login(app):
    assert client_di(app).get("/area/").status_code == 302
    assert client_di(app, crea_utente()).get("/area/").status_code == 200


def _candidatura(app, autore, edizione=None):
    with open(f"{app.config['UPLOAD_FOLDER']}/ud.pdf", "wb") as f:
        f.write(b"%PDF")
    c = Candidatura(utente=autore, edizione=edizione or crea_edizione(), tipo="borsista",
                    titolo_ud="UD", file_path="ud.pdf", file_nome="ud.pdf")
    db.session.add(c)
    db.session.commit()
    return c


def test_candidatura_di_altri_non_visibile(app):
    autore, altro, comitato = crea_utente(), crea_utente(), crea_utente(ruolo="comitato")
    cand = _candidatura(app, autore)
    c_altro = client_di(app, altro)
    assert c_altro.get(f"/area/candidatura/{cand.id}").status_code == 404
    assert c_altro.get(f"/area/candidatura/{cand.id}/file").status_code == 404
    assert client_di(app, autore).get(f"/area/candidatura/{cand.id}/file").status_code == 200
    assert client_di(app, comitato).get(f"/area/candidatura/{cand.id}/file").status_code == 200


def test_invio_bloccato_se_ci_sono_problemi(app):
    autore = crea_utente(completo=False)
    cand = _candidatura(app, autore)
    client_di(app, autore).post(f"/area/candidatura/{cand.id}/invia")
    db.session.refresh(cand)
    assert cand.stato == "bozza"


def test_invio_riuscito(app):
    autore = crea_utente()
    cand = _candidatura(app, autore)
    client_di(app, autore).post(f"/area/candidatura/{cand.id}/invia")
    db.session.refresh(cand)
    assert cand.stato == "inviata" and cand.inviata_il is not None


def test_invio_dopo_scadenza(app):
    autore = crea_utente()
    ed = crea_edizione(scadenza=date.today() - timedelta(days=1))
    cand = _candidatura(app, autore, edizione=ed)
    assert client_di(app, autore).post(f"/area/candidatura/{cand.id}/invia").status_code == 400


# ------------------------------------------------------------------ download materiali
def test_scarica_materiale(app):
    autore, docente, comitato = crea_utente(), crea_utente(), crea_utente(ruolo="comitato")
    ed = crea_edizione(stato="conclusa")
    with open(f"{app.config['UPLOAD_FOLDER']}/m.pdf", "wb") as f:
        f.write(b"%PDF")

    def materiale(stato, visibilita):
        m = Materiale(edizione=ed, titolo="M", stato=stato, visibilita=visibilita, file_path="m.pdf",
                      file_nome="m.pdf", mime="application/pdf", caricato_da_id=autore.id)
        db.session.add(m)
        db.session.commit()
        return f"/materiali/{m.id}/scarica"

    anonimo, c_docente = client_di(app), client_di(app, docente)
    c_autore, c_comitato = client_di(app, autore), client_di(app, comitato)

    url = materiale("pubblicato", "pubblico")
    assert anonimo.get(url).status_code == 200

    url = materiale("pubblicato", "registrati")
    assert anonimo.get(url).status_code == 404
    assert c_docente.get(url).status_code == 200

    url = materiale("in_revisione", "pubblico")
    assert c_docente.get(url).status_code == 404
    assert c_autore.get(url).status_code == 200
    assert c_comitato.get(url).status_code == 200
