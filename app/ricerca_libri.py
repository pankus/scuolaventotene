"""Ricerca delle letture mentre si scrive il titolo (PIANO_LETTURE.md, F4).

a) cache locale di Zotero (``ZoteroItem``): veloce, senza rete, sempre per prima;
b) solo per i libri e su richiesta (casella «cerca anche online»): Google Books e Open Library, interrogati dal server (l'IP del docente non arriva a loro),
   in parallelo, con timeout; se una fonte non risponde restano i risultati dell'altra.
I risultati online si fondono per ISBN. Le copertine restano URL: si scaricano in locale solo
quando il comitato approva la lettura (``utils.salva_copertina``).
"""
import json
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from flask import current_app
from sqlalchemy import and_, false, or_

from .models import ZoteroItem
from .zotero_sync import _cifra10, normalizza_isbn, piega

TIMEOUT = 5
MAX_RISULTATI = 6


def _json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "scuola-ventotene"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)


def _https(url):
    return url.replace("http://", "https://", 1) if url else None


# --------------------------------------------------------------------------- fonti
def google_books(q, isbn=None, chiave=None):
    params = {"q": f"isbn:{isbn}" if isbn else q, "maxResults": MAX_RISULTATI, "printType": "books"}
    if chiave:  # senza chiave la quota anonima di Google si esaurisce presto (429)
        params["key"] = chiave
    dati = _json("https://www.googleapis.com/books/v1/volumes?" + urllib.parse.urlencode(params))
    out = []
    for v in dati.get("items", []):
        info = v.get("volumeInfo", {})
        isbn_v = normalizza_isbn(" ".join(i.get("identifier", "") for i in info.get("industryIdentifiers", [])
                                          if i.get("type", "").startswith("ISBN")))
        titolo = ": ".join(x for x in (info.get("title"), info.get("subtitle")) if x)
        out.append({"fonte": "Google Books", "titolo": titolo, "autori": info.get("authors", []),
                    "anno": (info.get("publishedDate") or "")[:4], "editore": info.get("publisher"),
                    "isbn": isbn_v,
                    "copertina_url": _https((info.get("imageLinks") or {}).get("thumbnail"))})
    return out


def open_library(q, isbn=None):
    params = {"isbn": isbn} if isbn else {"q": q}
    params.update(limit=MAX_RISULTATI,
                  fields="title,subtitle,author_name,first_publish_year,publisher,isbn,cover_i")
    dati = _json("https://openlibrary.org/search.json?" + urllib.parse.urlencode(params))
    out = []
    for d in dati.get("docs", []):
        titolo = ": ".join(x for x in (d.get("title"), d.get("subtitle")) if x)
        isbn_d = isbn or normalizza_isbn(" ".join(sorted(d.get("isbn", []), key=len, reverse=True)))
        out.append({"fonte": "Open Library", "titolo": titolo, "autori": d.get("author_name", []),
                    "anno": str(d.get("first_publish_year") or ""),
                    "editore": (d.get("publisher") or [None])[0], "isbn": isbn_d,
                    "copertina_url": (f"https://covers.openlibrary.org/b/id/{d['cover_i']}-M.jpg"
                                      if d.get("cover_i") else None)})
    return out


# --------------------------------------------------------------------------- ricerca
def fondi(liste):
    """Unisce i risultati delle fonti: stesso ISBN (o stesso titolo+anno senza ISBN) = un libro.
    Vince la prima fonte; dalle altre si prendono solo i campi che mancano."""
    fusi = {}
    for lista in liste:
        for r in lista:
            if not r.get("titolo"):
                continue
            chiave = r.get("isbn") or f"{piega(r['titolo'])}|{r.get('anno')}"
            if chiave in fusi:
                for k, v in r.items():
                    fusi[chiave][k] = fusi[chiave].get(k) or v
            else:
                fusi[chiave] = dict(r)
    return list(fusi.values())


def cerca_online(q, isbn=None, chiave_google=None):
    """Interroga le fonti in parallelo. (risultati fusi, nomi delle fonti non raggiungibili)."""
    fonti = {"google_books": lambda: google_books(q, isbn, chiave_google),
             "open_library": lambda: open_library(q, isbn)}
    with ThreadPoolExecutor(len(fonti)) as ex:
        futuri = {nome: ex.submit(f) for nome, f in fonti.items()}
    liste, errori = [], []
    for nome, fut in futuri.items():
        try:
            liste.append(fut.result())
        except Exception:  # noqa: BLE001  (rete, timeout, quota, JSON inatteso: la fonte si salta)
            errori.append(nome)
    return fondi(liste), errori


def cerca_zotero(q, isbn=None, tipo=None):
    """Item già nella bibliografia, non nel cestino: ogni parola di ``q`` nel titolo o negli
    autori (oppure lo stesso ISBN); con ``tipo`` solo quel tipo Zotero."""
    parole = [or_(ZoteroItem.titolo.ilike(f"%{p}%"), ZoteroItem.autori.ilike(f"%{p}%"))
              for p in (q or "").split()]
    filtro = and_(*parole) if parole else false()
    if isbn:
        filtro = or_(filtro, ZoteroItem.isbn == isbn)
    righe = ZoteroItem.query.filter(ZoteroItem.eliminato.is_(False), filtro)
    if tipo:
        righe = righe.filter(ZoteroItem.tipo == tipo)
    return [{"key": z.key, "tipo": z.tipo, "titolo": z.titolo, "autori": z.autori, "anno": z.anno,
             "isbn": z.isbn} for z in righe.order_by(ZoteroItem.titolo).limit(10)]


def cerca(q, isbn_testo=None, online=False, tipo="book"):
    """Prima la bibliografia della scuola; i cataloghi online (solo libri) se ``online``.
    Dagli online si tolgono i libri con un ISBN già trovato in Zotero."""
    q = (q or "").strip()
    isbn = normalizza_isbn(isbn_testo) or normalizza_isbn(q)
    zotero = cerca_zotero(q, isbn, tipo)
    trovati, errori = [], []
    if online and tipo == "book":
        trovati, errori = cerca_online(q, isbn, current_app.config.get("GOOGLE_BOOKS_API_KEY"))
        gia = {z["isbn"] for z in zotero if z["isbn"]}
        trovati = [r for r in trovati if not r.get("isbn") or r["isbn"] not in gia]
    return {"zotero": zotero, "online": trovati, "errori": errori}


# --------------------------------------------------------------------------- copertine della bibliografia
def isbn10(isbn13):
    """ISBN-10 di un ISBN-13 978- (Amazon indicizza le immagini così); None per i 979-."""
    if not isbn13 or len(isbn13) != 13 or not isbn13.startswith("978"):
        return None
    return isbn13[3:12] + _cifra10(isbn13[3:12])


def _motivo(e):
    if isinstance(e, urllib.error.HTTPError) and e.code == 429:
        return "troppe richieste"
    return str(e) or e.__class__.__name__


def _copertine_per_isbn(isbn, chiave_google=None, errori=None):
    """URL candidati della copertina, fonte per fonte e solo quando servono: Open Library
    (diretto per ISBN, 404 se manca; poi ricerca), Amazon per ISBN-10, Google Books per ultima
    (quota). Una fonte che non risponde (429, rete) si annota in ``errori`` e si passa alla
    successiva."""
    errori = [] if errori is None else errori
    yield f"https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg?default=false"
    i10 = isbn10(isbn)
    fonti = [
        ("Open Library", lambda: [r["copertina_url"] for r in open_library(None, isbn)]),
        # ponytail: endpoint immagini di Amazon non documentato; se sparisce resta Google Books
        ("Amazon", lambda: [f"https://images-na.ssl-images-amazon.com/images/P/{i10}.01.LZZZZZZZ.jpg"]
         if i10 else []),
        ("Google Books", lambda: [r["copertina_url"] for r in google_books(None, isbn, chiave_google)]),
    ]
    for nome, fonte in fonti:
        try:
            urls = fonte()
        except Exception as e:  # noqa: BLE001  (quota, rete, JSON inatteso: fonte successiva)
            errori.append(f"{nome} ({_motivo(e)})")
            continue
        yield from (u for u in urls if u)


def cerca_copertina(isbn, salva=None):
    """Prima copertina scaricabile per l'ISBN (pulsante dell'admin): percorso o ValueError."""
    from .utils import salva_copertina
    errori = []
    for url in _copertine_per_isbn(isbn, current_app.config.get("GOOGLE_BOOKS_API_KEY"), errori):
        try:
            return (salva or salva_copertina)(url)
        except Exception:  # noqa: BLE001  (404, segnaposto, non immagine: si prova il candidato dopo)
            continue
    messaggio = "nessuna copertina trovata per questo ISBN"
    if errori:
        messaggio += "; non hanno risposto: " + ", ".join(errori)
        if any(e.startswith("Google Books") for e in errori) and not current_app.config.get("GOOGLE_BOOKS_API_KEY"):
            messaggio += " (per Google Books configura GOOGLE_BOOKS_API_KEY)"
    raise ValueError(messaggio)


def scarica_copertine(limite=50, salva=None, candidati=None):
    """Copertine in locale per i libri con ISBN che non ne hanno una (``flask zotero-copertine``,
    in cron dopo il sync). Un libro per cui tutte le fonti hanno risposto senza copertina resta
    con ``copertina_path=""`` e non si riprova. ``salva(url) -> percorso`` e
    ``candidati(isbn, errori)`` si sostituiscono nei test.
    Restituisce (scaricate, non trovate); i libri con una fonte giù restano da riprovare."""
    from .extensions import db
    from .utils import salva_copertina
    salva = salva or salva_copertina
    chiave = current_app.config.get("GOOGLE_BOOKS_API_KEY")
    candidati = candidati or (lambda isbn, errori: _copertine_per_isbn(isbn, chiave, errori))
    # ponytail: un libro alla volta, in serie; ``limite`` per giro tiene basso il carico sulle fonti
    libri = (ZoteroItem.query.filter(ZoteroItem.eliminato.is_(False), ZoteroItem.tipo == "book",
                                     ZoteroItem.isbn.isnot(None), ZoteroItem.copertina_path.is_(None))
             .limit(limite).all())
    scaricate = 0
    senza = 0
    for zi in libri:
        errori = []
        try:
            for url in candidati(zi.isbn, errori):
                try:
                    zi.copertina_path = salva(url)
                    scaricate += 1
                    break
                except Exception:  # noqa: BLE001  (404, segnaposto, host non ammesso, troppo grande)
                    continue
        except Exception as e:  # noqa: BLE001
            errori.append(str(e))
        if zi.copertina_path is None and not errori:
            zi.copertina_path, senza = "", senza + 1  # tutte le fonti hanno risposto: non c'è
        # con una fonte giù (quota, rete) resta None e si riprova al giro dopo
        db.session.commit()
    return scaricate, senza
