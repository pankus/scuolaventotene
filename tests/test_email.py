"""Email transazionali: verifica, reset password, conferma invio, esiti."""
import re
import smtplib

import pytest

from app import posta
from app.extensions import db
from app.models import Candidatura, Utente

from conftest import PASSWORD, crea_edizione, crea_utente, login


@pytest.fixture
def inviate(monkeypatch):
    """Raccoglie le email invece di spedirle."""
    msgs = []
    monkeypatch.setattr(posta, "_spedisci", msgs.append)
    return msgs


def link(msg):
    return re.search(r"http://localhost(/\S+)", msg.get_content()).group(1)


def client_di(app, utente=None):
    c = app.test_client()
    if utente:
        login(c, utente)
    return c


# ------------------------------------------------------------------ verifica
def test_registrazione_e_verifica(app, inviate):
    c = client_di(app)
    c.post("/registrati", data={"nome": "Ada", "cognome": "Prova", "email": "ada@esempio.it",
                                "password": PASSWORD, "conferma": PASSWORD, "consenso_privacy": "y"})
    u = Utente.query.filter_by(email="ada@esempio.it").one()
    assert not u.email_verificata
    assert len(inviate) == 1 and inviate[0]["To"] == "ada@esempio.it"

    c.get(link(inviate[0]))
    db.session.refresh(u)
    assert u.email_verificata


def test_token_manomesso_o_scaduto(app, inviate, monkeypatch):
    u = crea_utente(verificata=False)
    with app.test_request_context():
        posta.email_verifica(u)
    url = link(inviate[0])
    client_di(app).get(url[:-2] + "xx")
    monkeypatch.setattr(posta, "DURATA_VERIFICA", -1)
    client_di(app).get(url)
    db.session.refresh(u)
    assert not u.email_verificata


def test_token_di_verifica_non_vale_per_reset(app, inviate):
    u = crea_utente()
    assert posta.leggi_token(posta.crea_token(u, "verifica"), "reset") is None


# ------------------------------------------------------------------ reset password
def test_reset_password(app, inviate):
    u = crea_utente()
    c = client_di(app)
    r_ignoto = c.post("/password-dimenticata", data={"email": "nessuno@esempio.it"})
    assert inviate == []
    r_noto = c.post("/password-dimenticata", data={"email": u.email})
    assert len(inviate) == 1
    assert r_ignoto.location == r_noto.location  # stessa risposta: non rivela chi è registrato

    url = link(inviate[0])
    c.post(url, data={"password": "nuova-password-123", "conferma": "nuova-password-123"})
    db.session.refresh(u)
    assert u.check_password("nuova-password-123")
    # il link vale una volta sola
    assert c.get(url).location.endswith("/password-dimenticata")


# ------------------------------------------------------------------ candidature
def _bozza(autore):
    c = Candidatura(utente=autore, edizione=crea_edizione(), tipo="uditore")
    db.session.add(c)
    db.session.commit()
    return c


def test_conferma_invio_e_notifica(app, inviate):
    autore = crea_utente()
    cand = _bozza(autore)
    client_di(app, autore).post(f"/area/candidatura/{cand.id}/invia")
    assert [m["To"] for m in inviate] == [autore.email, "referente@esempio.it"]


def test_errore_smtp_non_blocca_invio(app, monkeypatch):
    def guasto(_msg):
        raise smtplib.SMTPException("server giù")
    monkeypatch.setattr(posta, "_spedisci", guasto)
    autore = crea_utente()
    cand = _bozza(autore)
    assert client_di(app, autore).post(f"/area/candidatura/{cand.id}/invia").status_code == 302
    db.session.refresh(cand)
    assert cand.stato == "inviata"


def test_esito_solo_al_cambio_stato(app, inviate):
    cand = _bozza(crea_utente())
    cand.stato = "in_valutazione"
    db.session.commit()
    admin = client_di(app, crea_utente(ruolo="admin"))
    url = f"/admin/candidature/{cand.id}/stato"
    admin.post(url, data={"st-stato": "ammessa"})
    admin.post(url, data={"st-stato": "ammessa", "st-note_comitato": "solo una nota"})
    assert len(inviate) == 1 and "Ammessa" in inviate[0].get_content()


# ------------------------------------------------------------------ SMTP
def test_spedisci_usa_ssl_e_login(app, monkeypatch):
    chiamate = []

    class FintoSMTP:
        def __init__(self, host, port, timeout):
            chiamate.append(("connessione", host, port))
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def login(self, user, pwd):
            chiamate.append(("login", user))
        def send_message(self, msg):
            chiamate.append(("invio", msg["To"]))

    monkeypatch.setattr(smtplib, "SMTP_SSL", FintoSMTP)
    app.config.update(MAIL_SERVER="mail.infomaniak.com", MAIL_PORT=465,
                      MAIL_USERNAME="scuola@esempio.it", MAIL_PASSWORD="x")
    assert posta.invia_email("a@esempio.it", "Prova", "prova")
    assert chiamate == [("connessione", "mail.infomaniak.com", 465),
                        ("login", "scuola@esempio.it"), ("invio", "a@esempio.it")]
