"""Sincronizzazione Zotero -> sito del gruppo della scuola (cache SQLite).

Usa la Zotero Web API v3 tramite pyzotero (logica portata da Itinera, app/biblio/sync.py):
- la versione della libreria si legge PRIMA dei download: ciò che cambia durante la sync
  viene ripreso alla volta successiva, niente va perso;
- collezioni: sempre la lista completa (sono poche); il cestino vale per tutto il sotto-albero;
  se Zotero non restituisce nessuna collezione ma in locale ce ne sono, non si cancella nulla
  (probabile errore di rete o di permessi);
- record: solo top-level modificati dopo l'ultima sync (``since``), con la citazione già formattata
  (``include=bib``); gli item nel cestino Zotero restano in cache con ``eliminato=True``
  (``/items/top`` non li restituisce, vanno chiesti a ``/items/trash``); gli item eliminati
  definitivamente arrivano da ``/deleted`` e si tolgono dalla cache.

La bibliografia si cura in Zotero; la scrittura dal sito (letture approvate) è in
``zotero_scrittura.py``. Lanciare da cron con ``flask zotero-sync``.
"""
import json
import re
import unicodedata

from flask import current_app

from .extensions import db
from .models import SyncStato, ZoteroCollezione, ZoteroItem, adesso

TIPI_ESCLUSI = {"attachment", "note", "annotation"}


def client():
    from pyzotero import zotero

    cfg = current_app.config
    if not cfg.get("ZOTERO_LIBRARY_ID"):
        raise RuntimeError("ZOTERO_LIBRARY_ID non configurato (.env)")
    return zotero.Zotero(cfg["ZOTERO_LIBRARY_ID"], cfg["ZOTERO_LIBRARY_TYPE"],
                         cfg.get("ZOTERO_API_KEY") or None)


# --------------------------------------------------------------------------- verifica
def puo_scrivere(zot, info=None):
    """True/False dal permesso della chiave sul gruppo; None se non si capisce."""
    cfg = current_app.config
    try:
        accesso = (info or zot.key_info()).get("access", {})
    except Exception:  # noqa: BLE001  (chiave assente o non valida)
        return None
    if cfg["ZOTERO_LIBRARY_TYPE"] == "user":
        return bool(accesso.get("user", {}).get("write"))
    gruppi = accesso.get("groups", {})
    permessi = gruppi.get(str(cfg["ZOTERO_LIBRARY_ID"])) or gruppi.get("all") or {}
    return bool(permessi.get("write"))


def verifica(zot=None):
    """Controllo della configurazione: connessione, contenuto, permesso di scrittura."""
    zot = zot or client()
    return {"item": zot.num_items(), "versione": zot.last_modified_version(),
            "scrittura": puo_scrivere(zot)}


# --------------------------------------------------------------------------- normalizzazioni
def normalizza_isbn(testo):
    """Primo ISBN valido nel campo Zotero (può contenerne più d'uno), sempre a 13 cifre."""
    for pezzo in re.split(r"[\s,;]+", testo or ""):
        c = re.sub(r"[^0-9X]", "", pezzo.upper())
        if len(c) == 13 and c.isdigit() and _cifra13(c[:12]) == c[12]:
            return c
        if len(c) == 10 and c[:9].isdigit() and _cifra10(c[:9]) == c[9]:
            base = "978" + c[:9]
            return base + _cifra13(base)
    return None


def _cifra10(nove):
    r = (11 - sum((10 - i) * int(d) for i, d in enumerate(nove)) % 11) % 11
    return "X" if r == 10 else str(r)


def _cifra13(dodici):
    return str((10 - sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(dodici)) % 10) % 10)


def piega(testo):
    """minuscole, senza accenti né punteggiatura, spazi compattati."""
    t = unicodedata.normalize("NFKD", testo or "")
    t = "".join(ch for ch in t if not unicodedata.combining(ch)).lower()
    return " ".join(re.sub(r"[^\w]+", " ", t).split())


def firma(titolo, tipo):
    """Chiave per riconoscere i doppioni (portata da Itinera: titolo normalizzato + tipo)."""
    t = piega(titolo)
    return f"{t}|{tipo}" if t else None


# --------------------------------------------------------------------------- sync
def _nome(c):
    if c.get("name"):
        return c["name"]
    return ", ".join(x for x in (c.get("lastName"), c.get("firstName")) if x)


def applica_item(zi, it, collezioni_idx):
    d = it.get("data", it)
    creatori = d.get("creators", [])
    autori = [c for c in creatori if c.get("creatorType") == "author"] or creatori
    zi.version = d.get("version")
    zi.tipo = d.get("itemType")
    zi.titolo = d.get("title") or d.get("caseName") or "(senza titolo)"
    zi.autori = "; ".join(_nome(c) for c in autori)
    zi.primo_autore = (autori[0].get("lastName") or autori[0].get("name")) if autori else zi.titolo[:255]
    zi.data = d.get("date")
    zi.anno = ((it.get("meta") or {}).get("parsedDate") or "")[:4] or None
    zi.pubblicazione = (d.get("publicationTitle") or d.get("bookTitle") or d.get("websiteTitle")
                        or d.get("publisher") or d.get("university"))
    zi.url = d.get("url")
    zi.doi = d.get("DOI")
    zi.isbn = normalizza_isbn(d.get("ISBN"))
    zi.firma = firma(d.get("title"), d.get("itemType"))
    zi.abstract = d.get("abstractNote")
    zi.tags = json.dumps([t["tag"] for t in d.get("tags", [])], ensure_ascii=False)
    zi.citazione_html = it.get("bib")
    zi.dati_json = json.dumps(d, ensure_ascii=False)
    zi.eliminato = bool(d.get("deleted"))
    zi.sincronizzato_il = adesso()
    zi.collezioni = [collezioni_idx[k] for k in d.get("collections", []) if k in collezioni_idx]


def _sync_collezioni(zot, stats):
    scaricate = [c["data"] for c in zot.everything(zot.collections())]
    locali = {c.key: c for c in ZoteroCollezione.query.all()}
    if not scaricate and locali:
        stats["avvisi"].append("Zotero non ha restituito collezioni: nessuna cancellata in locale.")
        return

    figli = {}
    for d in scaricate:
        figli.setdefault(d.get("parentCollection") or None, []).append(d["key"])
    nel_cestino = set()
    da_visitare = [d["key"] for d in scaricate if d.get("deleted")]
    while da_visitare:  # il cestino vale per tutto il sotto-albero
        k = da_visitare.pop()
        if k not in nel_cestino:
            nel_cestino.add(k)
            da_visitare.extend(figli.get(k, []))

    vive = set()
    for d in scaricate:
        if d["key"] in nel_cestino:
            continue
        col = locali.get(d["key"]) or ZoteroCollezione(key=d["key"])
        col.nome = d["name"]
        col.parent_key = d.get("parentCollection") or None
        col.version = d.get("version")
        db.session.add(col)
        vive.add(d["key"])
        stats["collezioni"] += 1
    for k, col in locali.items():
        if k not in vive:
            db.session.delete(col)
    db.session.flush()


def sincronizza(completa=False, zot=None):
    cfg = current_app.config
    zot = zot or client()
    since = 0 if completa else int(SyncStato.get("zotero_version", 0) or 0)
    versione_libreria = zot.last_modified_version()  # PRIMA dei download
    stats = {"collezioni": 0, "item": 0, "cestino": 0, "eliminati": 0,
             "versione": versione_libreria, "avvisi": []}

    if since and versione_libreria == since:
        SyncStato.set("zotero_ultima_sync", adesso().isoformat(timespec="seconds"))
        db.session.commit()
        return stats

    # 1. collezioni
    _sync_collezioni(zot, stats)
    collezioni_idx = {c.key: c for c in ZoteroCollezione.query.all()}

    # 2. record (solo top-level: niente allegati/note); poi quelli finiti nel cestino
    visti = set()
    formato = {"include": "data,bib", "style": cfg["ZOTERO_STYLE"], "locale": cfg["ZOTERO_LOCALE"]}
    for chiamata, chiave_stat in ((zot.top, "item"), (zot.trash, "cestino")):
        for it in zot.everything(chiamata(since=since, **formato)):
            d = it.get("data", it)
            if d.get("itemType") in TIPI_ESCLUSI or d.get("parentItem"):
                continue
            zi = db.session.get(ZoteroItem, d["key"]) or ZoteroItem(key=d["key"])
            applica_item(zi, it, collezioni_idx)
            if chiave_stat == "cestino":
                zi.eliminato = True
            db.session.add(zi)
            visti.add(d["key"])
            stats[chiave_stat] += 1

    # 3. eliminati definitivamente
    if since:
        chiavi = zot.deleted(since=since).get("items", [])
        for zi in ZoteroItem.query.filter(ZoteroItem.key.in_(chiavi)).all():
            db.session.delete(zi)
            stats["eliminati"] += 1
    else:  # sync completa: via ciò che non esiste più su Zotero
        for zi in ZoteroItem.query.filter(ZoteroItem.key.notin_(visti or {""})).all():
            db.session.delete(zi)
            stats["eliminati"] += 1

    SyncStato.set("zotero_version", versione_libreria)
    SyncStato.set("zotero_ultima_sync", adesso().isoformat(timespec="seconds"))
    db.session.commit()
    return stats
