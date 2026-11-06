import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "cambiami-in-produzione")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{INSTANCE_DIR / 'ventotene.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Upload: PDF e PowerPoint possono essere pesanti
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", str(INSTANCE_DIR / "uploads"))
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_MB", "60")) * 1024 * 1024
    ESTENSIONI_PROPOSTE = {"pdf", "doc", "docx", "odt"}
    ESTENSIONI_MATERIALI = {"pdf", "ppt", "pptx", "odp", "doc", "docx", "odt"}

    # Zotero (gruppo)
    ZOTERO_LIBRARY_ID = os.environ.get("ZOTERO_LIBRARY_ID", "")
    ZOTERO_LIBRARY_TYPE = os.environ.get("ZOTERO_LIBRARY_TYPE", "group")
    ZOTERO_API_KEY = os.environ.get("ZOTERO_API_KEY", "")  # vuota se il gruppo è pubblico
    ZOTERO_STYLE = os.environ.get("ZOTERO_STYLE", "chicago-author-date")
    ZOTERO_LOCALE = os.environ.get("ZOTERO_LOCALE", "it-IT")
    ZOTERO_GROUP_URL = os.environ.get("ZOTERO_GROUP_URL", "")
    # tag messo sugli item creati dal sito con le letture proposte dai docenti
    ZOTERO_TAG_PROPOSTE = os.environ.get("ZOTERO_TAG_PROPOSTE", "proposta-docenti")

    # Contatti mostrati sul sito
    EMAIL_CONTATTI = [
        "michele.colucci@ismed.cnr.it",
        "donato.disanzo@ismed.cnr.it",
        "stefano.gallo@ismed.cnr.it",
    ]

    # Email (SMTP Infomaniak). Senza MAIL_SERVER le email non partono: finiscono nel log.
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", "465"))  # 465 = SSL, 587 = STARTTLS
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_MITTENTE = os.environ.get("MAIL_MITTENTE", "") or MAIL_USERNAME
    # referenti avvisati a ogni candidatura inviata (separati da virgola; vuoto = nessuno)
    MAIL_NOTIFICHE = [e.strip() for e in os.environ.get("MAIL_NOTIFICHE", "").split(",") if e.strip()]

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    MAIL_SERVER = ""
    MAIL_MITTENTE = "scuola@esempio.it"
    MAIL_NOTIFICHE = ["referente@esempio.it"]
    # mai il gruppo vero nei test: si usa FakeZot (tests/conftest.py)
    ZOTERO_LIBRARY_ID = "12345"
    ZOTERO_API_KEY = ""
