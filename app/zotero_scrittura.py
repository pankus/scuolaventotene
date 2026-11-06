"""Scrittura in Zotero dal sito (letture approvate dal comitato).

Porta ridotta di Itinera (app/biblio/write.py). Zotero resta la fonte di verità: si scrive via
API, poi si salva in cache solo l'item riscaricato da Zotero. ``SyncStato.zotero_version`` non si
tocca: alla sync successiva l'item torna come modificato ed è solo aggiornato.

Solo i tipi ``book`` e ``webpage``. Nessun dato del docente va in Zotero: le funzioni accettano
solo campi bibliografici; il legame docente↔libro resta nel DB del sito.
"""
from flask import current_app
from pyzotero import errors as ze

from .extensions import db
from .models import ZoteroCollezione, ZoteroItem
from .zotero_sync import applica_item, firma, normalizza_isbn

# campi Zotero modificabili dal sito, per tipo
TIPI = {
    "book": ["title", "date", "publisher", "place", "ISBN", "series", "url"],
    "webpage": ["title", "websiteTitle", "url", "accessDate"],
}
CREATORI = {"book": ("author", "editor"), "webpage": ("author",)}
# campi dei moduli del sito (forms.LetturaForm), in ordine: quelli Zotero più autori e curatori
CAMPI_MODULO = {"book": TIPI["book"][:1] + ["autori", "curatori"] + TIPI["book"][1:],
                "webpage": TIPI["webpage"][:1] + ["autori"] + TIPI["webpage"][1:]}


class ErroreScrittura(Exception):
    """Scrittura rifiutata da Zotero o dai controlli: messaggio da mostrare all'utente."""


def parse_autori(testo, tipo="author"):
    """Una riga per autore: 'Cognome, Nome' oppure un nome unico (ente)."""
    out = []
    for riga in (testo or "").splitlines():
        riga = riga.strip()
        if not riga:
            continue
        if "," in riga:
            cognome, nome = (p.strip() for p in riga.split(",", 1))
            out.append({"creatorType": tipo, "lastName": cognome, "firstName": nome})
        else:
            out.append({"creatorType": tipo, "name": riga})
    return out


def _applica(data, campi, autori, curatori):
    """Copia nel ``data`` Zotero i campi del modulo (solo quelli previsti dal tipo)."""
    tipo = data["itemType"]
    for k in TIPI[tipo]:
        if k in campi:
            data[k] = (campi.get(k) or "").strip()
    nuovi = {"author": autori, "editor": curatori}
    if any(nuovi[t] is not None for t in CREATORI[tipo]):
        vecchi = data.get("creators") or []
        creatori = []
        for t in CREATORI[tipo]:
            creatori += (parse_autori(nuovi[t], t) if nuovi[t] is not None
                         else [c for c in vecchi if c.get("creatorType") == t])
        data["creators"] = creatori + [c for c in vecchi if c.get("creatorType") not in CREATORI[tipo]]


def _aggiorna_cache(zot, key):
    """Riscarica l'item da Zotero e lo salva in ``ZoteroItem`` (flush; commit del chiamante)."""
    cfg = current_app.config
    it = zot.item(key, include="data,bib", style=cfg["ZOTERO_STYLE"], locale=cfg["ZOTERO_LOCALE"])
    zi = db.session.get(ZoteroItem, key) or ZoteroItem(key=key)
    applica_item(zi, it, {c.key: c for c in ZoteroCollezione.query.all()})
    db.session.add(zi)
    db.session.flush()
    return zi


def crea_item(zot, tipo, campi, autori="", curatori="", collezioni=()):
    """Crea l'item in Zotero (tag delle proposte) e ne salva la copia locale.

    Il controllo dei duplicati (``candidati_duplicati``) è del chiamante.
    """
    if tipo not in TIPI:
        raise ErroreScrittura(f"Tipo non previsto: {tipo}")
    if not (campi.get("title") or "").strip():
        raise ErroreScrittura("Il titolo è obbligatorio.")
    data = zot.item_template(tipo)
    data["creators"] = []
    _applica(data, campi, autori, curatori)
    data["collections"] = list(collezioni)
    data["tags"] = [{"tag": current_app.config["ZOTERO_TAG_PROPOSTE"]}]
    try:
        res = zot.create_items([data])
    except ze.PyZoteroError as e:
        raise ErroreScrittura(f"Zotero ha rifiutato la creazione: {e}") from e
    if res.get("failed"):
        raise ErroreScrittura(f"Zotero ha rifiutato la creazione: {res['failed']}")
    key = (res.get("successful") or {}).get("0", {}).get("key") or (res.get("success") or {}).get("0")
    return _aggiorna_cache(zot, key)


def aggiorna_item(zot, key, versione, campi, autori=None, curatori=None):
    """Modifica l'item partendo da quello attuale in Zotero; cambiano solo i campi del modulo.

    ``versione`` = versione con cui è stato aperto il modulo: se in Zotero l'item è cambiato
    nel frattempo, Zotero risponde 412 e niente viene sovrascritto.
    """
    data = dict(zot.item(key)["data"])
    if data.get("itemType") not in TIPI:
        raise ErroreScrittura(f"Tipo non modificabile dal sito: {data.get('itemType')}")
    _applica(data, campi, autori, curatori)
    data["version"] = int(versione)  # JSON e header devono coincidere, se no Zotero dà 400
    try:
        zot.update_item(data, last_modified=int(versione))
    except ze.PreConditionFailedError as e:
        raise ErroreScrittura("L'item è stato modificato in Zotero dopo l'apertura del modulo: "
                              "ricarica la pagina e ripeti la modifica.") from e
    except ze.PyZoteroError as e:
        raise ErroreScrittura(f"Zotero ha rifiutato la modifica: {e}") from e
    return _aggiorna_cache(zot, key)


def collega_item(zot, key, collezioni=()):
    """Item già in Zotero proposto da un docente: aggiunge collezioni e tag delle proposte.

    Si parte dalla versione attuale in Zotero (nessun modulo aperto da proteggere); se cambia
    proprio in quell'istante, Zotero risponde 412 e si chiede di riprovare.
    """
    try:
        data = dict(zot.item(key)["data"])
    except ze.ResourceNotFoundError as e:
        raise ErroreScrittura(f"L'item {key} non esiste più in Zotero.") from e
    if data.get("itemType") not in TIPI:
        raise ErroreScrittura(f"Tipo non previsto per l'invito alla lettura: {data.get('itemType')}")
    tag = current_app.config["ZOTERO_TAG_PROPOSTE"]
    nuove = [k for k in collezioni if k not in data.get("collections", [])]
    if nuove or tag not in {t["tag"] for t in data.get("tags", [])}:
        data["collections"] = data.get("collections", []) + nuove
        data["tags"] = [t for t in data.get("tags", []) if t["tag"] != tag] + [{"tag": tag}]
        try:
            zot.update_item(data, last_modified=data["version"])
        except ze.PreConditionFailedError as e:
            raise ErroreScrittura("L'item è cambiato in Zotero proprio ora: riprova.") from e
        except ze.PyZoteroError as e:
            raise ErroreScrittura(f"Zotero ha rifiutato la modifica: {e}") from e
    return _aggiorna_cache(zot, key)


def _anni_compatibili(a, b):
    """Stesso anno, oppure uno dei due manca."""
    return not a or not b or a == b


def candidati_duplicati(zot, tipo, campi):
    """Possibili doppioni di un item da creare: ``(locali, remoti)``.

    locali = ``ZoteroItem`` con lo stesso ISBN, oppure stessa firma e anno compatibile (anche
    quelli nel cestino); remoti = ricerca per titolo in Zotero, esclusi quelli già in cache
    (creati dopo l'ultima sync).
    """
    locali = {}
    isbn = normalizza_isbn(campi.get("ISBN"))
    if isbn:
        for zi in ZoteroItem.query.filter_by(isbn=isbn):
            locali[zi.key] = zi
    f = firma(campi.get("title"), tipo)
    if f:
        anno = (campi.get("date") or "").strip()[:4]
        for zi in ZoteroItem.query.filter_by(firma=f):
            if _anni_compatibili(anno, zi.anno):
                locali.setdefault(zi.key, zi)

    remoti = []
    titolo = (campi.get("title") or "").strip()
    if zot is not None and titolo:
        for it in zot.items(q=titolo, limit=5):
            d = it.get("data", it)
            if d.get("itemType") in TIPI and not db.session.get(ZoteroItem, d["key"]):
                remoti.append({"key": d["key"], "titolo": d.get("title"), "tipo": d.get("itemType")})
    return list(locali.values()), remoti
