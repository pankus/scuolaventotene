"""Ricerca dei libri mentre il docente scrive il titolo (PIANO_LETTURE.md, F4).

a) cache locale di Zotero (``ZoteroItem``): veloce, senza rete;
b) Google Books e Open Library, interrogati dal server (l'IP del docente non arriva a loro),
   in parallelo, con timeout; se una fonte non risponde restano i risultati dell'altra.
I risultati online si fondono per ISBN. Le copertine restano URL: si scaricano in locale solo
quando il comitato approva la lettura (``utils.salva_copertina``).
"""
import json
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from flask import current_app
from sqlalchemy import or_

from .models import ZoteroItem
from .zotero_sync import normalizza_isbn, piega

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


def cerca_zotero(q, isbn=None):
    """Item già nella bibliografia (book/webpage, non nel cestino)."""
    filtro = [ZoteroItem.titolo.ilike(f"%{q}%"), ZoteroItem.autori.ilike(f"%{q}%")]
    if isbn:
        filtro.append(ZoteroItem.isbn == isbn)
    righe = (ZoteroItem.query.filter(ZoteroItem.eliminato.is_(False),
                                     ZoteroItem.tipo.in_(("book", "webpage")), or_(*filtro))
             .order_by(ZoteroItem.titolo).limit(8))
    return [{"key": z.key, "tipo": z.tipo, "titolo": z.titolo, "autori": z.autori, "anno": z.anno,
             "isbn": z.isbn} for z in righe]


def cerca(q, isbn_testo=None):
    q = (q or "").strip()
    isbn = normalizza_isbn(isbn_testo) or normalizza_isbn(q)
    online, errori = cerca_online(q, isbn, current_app.config.get("GOOGLE_BOOKS_API_KEY"))
    return {"zotero": cerca_zotero(q, isbn), "online": online, "errori": errori}
