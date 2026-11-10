import io
import mimetypes
import os
import urllib.parse
import urllib.request
import uuid
from functools import wraps

import markdown as md
from flask import abort, current_app
from flask_login import current_user
from markupsafe import Markup
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from . import models


# --------------------------------------------------------------------------- permessi
def admin_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*a, **kw)
    return wrapper


def comitato_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not current_user.is_authenticated or not current_user.is_comitato:
            abort(403)
        return f(*a, **kw)
    return wrapper


# --------------------------------------------------------------------------- upload
def upload_root():
    return current_app.config["UPLOAD_FOLDER"]


def salva_upload(file_storage, sottocartella, estensioni):
    """Salva con nome casuale (mai il nome originale) e restituisce i metadati."""
    originale = secure_filename(file_storage.filename or "") or "file"
    ext = originale.rsplit(".", 1)[-1].lower() if "." in originale else ""
    if ext not in estensioni:
        raise ValueError(f"Estensione .{ext} non ammessa")
    rel = os.path.join(sottocartella, f"{uuid.uuid4().hex}.{ext}")
    dest = os.path.join(upload_root(), rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    file_storage.save(dest)
    return {
        "file_path": rel,
        "file_nome": originale,
        "mime": mimetypes.guess_type(originale)[0] or "application/octet-stream",
        "dimensione": os.path.getsize(dest),
    }


def elimina_upload(rel):
    if rel:
        p = os.path.join(upload_root(), rel)
        if os.path.isfile(p):
            os.remove(p)


# copertine: solo dalle fonti del lookup (anche dopo i redirect), solo immagini piccole
HOST_COPERTINE = ("books.google.com", "books.googleusercontent.com", "covers.openlibrary.org",
                  "archive.org", "images-na.ssl-images-amazon.com", "m.media-amazon.com")
TIPI_COPERTINA = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif"}
MAX_COPERTINA = 2 * 1024 * 1024
MIN_COPERTINA = 1000  # sotto: segnaposto (Amazon risponde 200 con una GIF 1×1 da 43 byte)


def copertina_ammessa(url):
    p = urllib.parse.urlsplit(url or "")
    host = (p.hostname or "").lower()
    return p.scheme == "https" and any(host == h or host.endswith("." + h) for h in HOST_COPERTINE)


class _RedirectControllato(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not copertina_ammessa(newurl):
            raise ValueError(f"redirect verso un host non ammesso: {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def salva_copertina(url):
    """Scarica la copertina in uploads/copertine/ (via salva_upload). Percorso o ValueError."""
    if not copertina_ammessa(url):
        raise ValueError("indirizzo della copertina non ammesso")
    apri = urllib.request.build_opener(_RedirectControllato).open
    with apri(urllib.request.Request(url, headers={"User-Agent": "scuola-ventotene"}), timeout=5) as r:
        ext = TIPI_COPERTINA.get(r.headers.get_content_type())
        if not ext:
            raise ValueError("la copertina non è un'immagine")
        dati = r.read(MAX_COPERTINA + 1)
    if len(dati) > MAX_COPERTINA:
        raise ValueError("copertina troppo grande")
    if len(dati) < MIN_COPERTINA:
        raise ValueError("copertina non disponibile (immagine segnaposto)")
    fs = FileStorage(io.BytesIO(dati), filename=f"copertina.{ext}")
    return salva_upload(fs, "copertine", set(TIPI_COPERTINA.values()))["file_path"]


# firme dei formati ammessi per le copertine caricate a mano (non ci si fida dell'estensione)
FIRME_IMMAGINI = {"jpg": (b"\xff\xd8\xff",), "png": (b"\x89PNG\r\n\x1a\n",),
                  "gif": (b"GIF87a", b"GIF89a"), "webp": (b"RIFF",)}


def carica_copertina(file_storage):
    """Copertina caricata dall'admin: solo jpg/png/webp/gif veri, max 2 MB. Percorso o ValueError."""
    dati = file_storage.read(MAX_COPERTINA + 1)
    if len(dati) > MAX_COPERTINA:
        raise ValueError("copertina troppo grande (max 2 MB)")
    ext = next((e for e, firme in FIRME_IMMAGINI.items() if dati.startswith(firme)
                and (e != "webp" or dati[8:12] == b"WEBP")), None)
    if not ext:
        raise ValueError("il file non è un'immagine jpg, png, webp o gif")
    fs = FileStorage(io.BytesIO(dati), filename=f"copertina.{ext}")
    return salva_upload(fs, "copertine", set(TIPI_COPERTINA.values()))["file_path"]


def conta_caratteri(rel):
    """Caratteri spazi inclusi per .docx (come il conteggio di Word). None se non calcolabile."""
    if not rel or not rel.lower().endswith(".docx"):
        return None
    try:
        import docx
        d = docx.Document(os.path.join(upload_root(), rel))
        testo = "".join(p.text for p in d.paragraphs)
        for t in d.tables:
            for row in t.rows:
                for cell in row.cells:
                    testo += "".join(p.text for p in cell.paragraphs)
        return len(testo)
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- template
def register_template_utils(app):
    @app.template_filter("markdown")
    def _markdown(text):
        return Markup(md.markdown(text or "", extensions=["extra"]))

    @app.template_filter("data_it")
    def _data_it(d, fmt="%d/%m/%Y"):
        return d.strftime(fmt) if d else ""

    @app.template_filter("dimensione")
    def _dim(n):
        if not n:
            return ""
        for u in ("B", "KB", "MB", "GB"):
            if n < 1024:
                return f"{n:.0f} {u}"
            n /= 1024
        return f"{n:.1f} TB"

    GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
    MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
            "agosto", "settembre", "ottobre", "novembre", "dicembre"]

    @app.template_filter("giorno_it")
    def _giorno_it(d):
        if not d:
            return ""
        return f"{GIORNI[d.weekday()].capitalize()} {d.day} {MESI[d.month - 1]}"

    @app.context_processor
    def _ctx():
        return {
            "STATI_CANDIDATURA": models.STATI_CANDIDATURA,
            "STATI_EDIZIONE": models.STATI_EDIZIONE,
            "STATI_MATERIALE": models.STATI_MATERIALE,
            "STATI_PROPOSTA": models.STATI_PROPOSTA,
            "TIPI_LETTURA": models.TIPI_LETTURA,
            "MOMENTI_PROPOSTA": models.MOMENTI_PROPOSTA,
            "TIPI_MATERIALE": models.TIPI_MATERIALE,
            "TIPI_CANDIDATURA": models.TIPI_CANDIDATURA,
            "TIPI_PROGRAMMA": models.TIPI_PROGRAMMA,
            "RUOLI_EDIZIONE": models.RUOLI_EDIZIONE,
            "GRUPPI_PARTECIPANTI": models.GRUPPI_PARTECIPANTI,
            "VISIBILITA": models.VISIBILITA,
        }
