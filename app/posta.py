"""Email transazionali (SMTP Infomaniak) e token firmati per verifica e reset password."""
import smtplib
from email.message import EmailMessage

from flask import current_app, render_template
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .extensions import db
from .models import STATI_CANDIDATURA, Utente

DURATA_VERIFICA = 7 * 24 * 3600   # secondi
DURATA_RESET = 3600


# --------------------------------------------------------------------------- invio
def _spedisci(msg):
    cfg = current_app.config
    if not cfg["MAIL_SERVER"]:
        current_app.logger.info("Email non inviata (MAIL_SERVER vuoto):\n%s", msg)
        return
    # ponytail: invio sincrono dentro la richiesta; coda/worker se i tempi diventano un problema
    if cfg["MAIL_PORT"] == 465:
        smtp = smtplib.SMTP_SSL(cfg["MAIL_SERVER"], cfg["MAIL_PORT"], timeout=10)
    else:
        smtp = smtplib.SMTP(cfg["MAIL_SERVER"], cfg["MAIL_PORT"], timeout=10)
        smtp.starttls()
    with smtp:
        if cfg["MAIL_USERNAME"]:
            smtp.login(cfg["MAIL_USERNAME"], cfg["MAIL_PASSWORD"])
        smtp.send_message(msg)


def invia_email(destinatari, oggetto, template, ccn=(), rispondi_a=None, **ctx):
    """Manda un'email di solo testo. Un errore SMTP finisce nel log e non blocca la richiesta.
    `ccn`: copia nascosta (send_message la usa come destinatari e non la trasmette)."""
    if isinstance(destinatari, str):
        destinatari = [destinatari]
    if not destinatari:
        return False
    msg = EmailMessage()
    msg["Subject"] = oggetto
    msg["From"] = current_app.config["MAIL_MITTENTE"]
    msg["To"] = ", ".join(destinatari)
    if ccn:
        msg["Bcc"] = ", ".join(ccn)
    if rispondi_a:
        msg["Reply-To"] = rispondi_a
    msg.set_content(render_template(f"email/{template}.txt", **ctx))
    try:
        _spedisci(msg)
        return True
    except (smtplib.SMTPException, OSError):
        current_app.logger.exception("Invio email fallito: %s", oggetto)
        return False


# --------------------------------------------------------------------------- token
def _serializer(scopo):
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=scopo)


def crea_token(utente, scopo):
    # verifica: legato all'email; reset: legato alla password, così il link vale una volta sola
    impronta = utente.email if scopo == "verifica" else utente.password_hash[-12:]
    return _serializer(scopo).dumps({"id": utente.id, "i": impronta})


def leggi_token(token, scopo):
    durata = DURATA_VERIFICA if scopo == "verifica" else DURATA_RESET
    try:
        dati = _serializer(scopo).loads(token, max_age=durata)
    except (BadSignature, SignatureExpired):
        return None
    u = db.session.get(Utente, dati.get("id"))
    if not u:
        return None
    impronta = u.email if scopo == "verifica" else u.password_hash[-12:]
    return u if dati.get("i") == impronta else None


# --------------------------------------------------------------------------- messaggi
def email_verifica(u):
    return invia_email(u.email, "Conferma il tuo indirizzo email", "verifica",
                       u=u, token=crea_token(u, "verifica"))


def email_reset(u):
    return invia_email(u.email, "Reimposta la password", "reset",
                       u=u, token=crea_token(u, "reset"))


def email_conferma_invio(c):
    invia_email(c.utente.email, f"Candidatura ricevuta – {c.edizione.titolo}", "conferma_invio", c=c)
    invia_email(current_app.config["MAIL_NOTIFICHE"],
                f"Nuova candidatura: {c.utente.nome_completo}", "notifica_invio", c=c)


def email_partecipanti(indirizzi, oggetto, testo, blocco=50):
    """Messaggio dell'admin ai partecipanti: tutti in copia nascosta, a blocchi (un collegamento
    SMTP per blocco). Restituisce quanti indirizzi non sono partiti."""
    cfg = current_app.config
    falliti = 0
    for i in range(0, len(indirizzi), blocco):
        parte = indirizzi[i:i + blocco]
        if not invia_email(cfg["MAIL_MITTENTE"], oggetto, "messaggio", ccn=parte,
                           rispondi_a=(cfg["EMAIL_CONTATTI"] or [None])[0], testo=testo):
            falliti += len(parte)
    return falliti


def email_esito(c):
    return invia_email(c.utente.email, f"Esito della candidatura – {c.edizione.titolo}", "esito",
                       c=c, esito=STATI_CANDIDATURA[c.stato])
