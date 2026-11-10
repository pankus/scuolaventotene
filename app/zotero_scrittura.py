"""Scrittura in Zotero dal sito (letture approvate dal comitato).

Porta ridotta di Itinera (app/biblio/write.py). Zotero resta la fonte di verità: si scrive via
API, poi si salva in cache solo l'item riscaricato da Zotero. ``SyncStato.zotero_version`` non si
tocca: alla sync successiva l'item torna come modificato ed è solo aggiornato.

Solo i tipi in ``TIPI`` (libro, capitolo, articolo, sito). Nessun dato del docente va in Zotero: le funzioni accettano
solo campi bibliografici; il legame docente↔libro resta nel DB del sito.
"""
from flask import current_app
from pyzotero import errors as ze

from .extensions import db
from .models import ZoteroCollezione, ZoteroItem
from .utils import salva_copertina
from .zotero_sync import applica_item, firma, normalizza_isbn

# campi Zotero modificabili dal sito, per tipo
TIPI = {
    "book": ["title", "date", "publisher", "place", "ISBN", "series", "url"],
    "bookSection": ["title", "bookTitle", "date", "publisher", "place", "ISBN", "pages", "url"],
    "journalArticle": ["title", "publicationTitle", "volume", "issue", "pages", "date", "DOI", "url"],
    "webpage": ["title", "websiteTitle", "url", "accessDate"],
}
CREATORI = {"book": ("author", "editor"), "bookSection": ("author", "editor"),
            "journalArticle": ("author",), "webpage": ("author",)}
# campi dei moduli del sito (forms.LetturaForm), in ordine: titolo, autori (e curatori), il resto
CAMPI_MODULO = {t: c[:1] + ["autori"] + (["curatori"] if "editor" in CREATORI[t] else []) + c[1:]
                for t, c in TIPI.items()}


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


def campi_da_item(zi):
    """Valori per ``LetturaForm`` dall'item in cache (dati Zotero): campi del tipo, autori e
    curatori come testo, una persona per riga ("Cognome, Nome")."""
    import json
    data = json.loads(zi.dati_json or "{}")
    campi = {k: data.get(k) or "" for k in TIPI.get(data.get("itemType"), [])}

    def righe(tipo):
        return "\n".join(f"{c['lastName']}, {c.get('firstName', '')}".rstrip(", ") if c.get("lastName")
                         else c.get("name", "")
                         for c in data.get("creators", []) if c.get("creatorType") == tipo)
    campi["autori"], campi["curatori"] = righe("author"), righe("editor")
    return campi


def sostituisci_copertina(zi, nuova):
    """Mette la copertina ``nuova`` (percorso, o "" = nessuna, da non cercare più) ed elimina il
    file vecchio se nessun altro item lo usa (dopo un merge in Zotero il file è condiviso)."""
    from .utils import elimina_upload
    vecchia = zi.copertina_path
    zi.copertina_path = nuova
    if vecchia and vecchia != nuova and not ZoteroItem.query.filter(
            ZoteroItem.key != zi.key, ZoteroItem.copertina_path == vecchia).first():
        elimina_upload(vecchia)


def _aggiorna_cache(zot, key):
    """Riscarica l'item da Zotero e lo salva in ``ZoteroItem`` (flush; commit del chiamante)."""
    cfg = current_app.config
    it = zot.item(key, include="data,bib", style=cfg["ZOTERO_STYLE"], locale=cfg["ZOTERO_LOCALE"])
    zi = db.session.get(ZoteroItem, key) or ZoteroItem(key=key)
    applica_item(zi, it, {c.key: c for c in ZoteroCollezione.query.all()})
    db.session.add(zi)
    db.session.flush()
    return zi


def crea_item(zot, tipo, campi, autori="", curatori="", collezioni=(), tag_proposte=True):
    """Crea l'item in Zotero e ne salva la copia locale. ``tag_proposte``: tag delle letture
    dei docenti (ZOTERO_TAG_PROPOSTE); le letture dei relatori non lo hanno.

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
    data["tags"] = [{"tag": current_app.config["ZOTERO_TAG_PROPOSTE"]}] if tag_proposte else []
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


def collega_item(zot, key, collezioni=(), tag_proposte=True):
    """Item già in Zotero scelto per l'invito alla lettura: aggiunge le collezioni e, per le
    letture dei docenti, il tag delle proposte.

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
    manca_tag = tag_proposte and tag not in {t["tag"] for t in data.get("tags", [])}
    if nuove or manca_tag:
        data["collections"] = data.get("collections", []) + nuove
        if manca_tag:
            data["tags"] = data.get("tags", []) + [{"tag": tag}]
        try:
            zot.update_item(data, last_modified=data["version"])
        except ze.PreConditionFailedError as e:
            raise ErroreScrittura("L'item è cambiato in Zotero proprio ora: riprova.") from e
        except ze.PyZoteroError as e:
            raise ErroreScrittura(f"Zotero ha rifiutato la modifica: {e}") from e
    return _aggiorna_cache(zot, key)


def scollega_item(zot, key, collezione):
    """Toglie l'item dalla collezione (lettura scollegata da una lezione). Il record resta in
    Zotero e nelle altre collezioni; niente da fare se non c'è o non c'è più."""
    try:
        data = dict(zot.item(key)["data"])
    except ze.ResourceNotFoundError:
        return None
    if collezione not in data.get("collections", []):
        return None
    data["collections"] = [k for k in data["collections"] if k != collezione]
    try:
        zot.update_item(data, last_modified=data["version"])
    except ze.PreConditionFailedError as e:
        raise ErroreScrittura("L'item è cambiato in Zotero proprio ora: riprova.") from e
    except ze.PyZoteroError as e:
        raise ErroreScrittura(f"Zotero ha rifiutato la modifica: {e}") from e
    return _aggiorna_cache(zot, key)


def crea_collezione(zot, nome, parent=None):
    """Crea la collezione in Zotero e la aggiunge alla cache (flush; commit del chiamante)."""
    try:
        res = zot.create_collections([{"name": nome, "parentCollection": parent or False}])
    except ze.PyZoteroError as e:
        raise ErroreScrittura(f"Zotero ha rifiutato la collezione «{nome}»: {e}") from e
    ok = (res.get("successful") or {}).get("0")
    if not ok:
        raise ErroreScrittura(f"Zotero ha rifiutato la collezione «{nome}»: {res.get('failed')}")
    col = ZoteroCollezione(key=ok["key"], nome=nome, parent_key=parent,
                           version=(ok.get("data") or {}).get("version"))
    db.session.add(col)
    db.session.flush()
    return col


def _anni_compatibili(a, b):
    """Stesso anno, oppure uno dei due manca."""
    return not a or not b or a == b


def candidati_duplicati(zot, tipo, campi):
    """Possibili doppioni di un item da creare: ``(locali, remoti)``.

    locali = ``ZoteroItem`` con lo stesso ISBN, oppure stessa firma e anno compatibile (anche
    quelli nel cestino), più quelli in cache trovati dalla ricerca per titolo in Zotero (titolo
    simile ma non uguale); remoti = trovati dalla ricerca ma non ancora sincronizzati.
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
            if d.get("itemType") not in TIPI:
                continue
            zi = db.session.get(ZoteroItem, d["key"])
            if zi:
                locali.setdefault(zi.key, zi)
            else:
                remoti.append({"key": d["key"], "titolo": d.get("title"), "tipo": d.get("itemType")})
    return list(locali.values()), remoti


# --------------------------------------------------------------------------- letture del sito
# sottocollezioni della collezione dell'edizione: quale -> (nome in Zotero, attributo di Edizione)
SOTTOCOLLEZIONI = {"docenti": ("Docenti", "zotero_docenti_key"),
                   "relatori": ("Relatori", "zotero_relatori_key")}


def sottocollezione_edizione(zot, ed, quale):
    """Key di «Docenti» o «Relatori» sotto la collezione dell'edizione; creata la prima volta
    (o ritrovata per nome se esiste già). Commit subito: se poi la scrittura dell'item fallisce,
    alla volta dopo non si crea un doppione."""
    nome, attr = SOTTOCOLLEZIONI[quale]
    col = getattr(ed, attr) and db.session.get(ZoteroCollezione, getattr(ed, attr))
    if col is None:
        col = ZoteroCollezione.query.filter_by(parent_key=ed.zotero_collection_key, nome=nome).first() \
            or crea_collezione(zot, nome, ed.zotero_collection_key)
        setattr(ed, attr, col.key)
        db.session.commit()
    return col.key


def scelte_duplicati(zot, tipo, campi):
    """Record Zotero a cui collegare una lettura: ([(key, descrizione)], avviso o None)."""
    avviso = None
    try:
        locali, remoti = candidati_duplicati(zot, tipo, campi)
    except Exception as e:  # noqa: BLE001  (Zotero irraggiungibile: restano i locali)
        avviso = f"Ricerca in Zotero non riuscita ({e}): controllati solo i record già sincronizzati."
        locali, remoti = candidati_duplicati(None, tipo, campi)
    scelte = [(z.key, f"{z.autori or ''} {z.anno or ''} — {z.titolo}") for z in locali if not z.eliminato]
    scelte += [(r["key"], f"{r['titolo']} (in Zotero, non ancora sincronizzato)") for r in remoti]
    return scelte, avviso


def salva_lettura(zot, p, ed, quale, scelta="", tag_proposte=None):
    """Scrive in Zotero la lettura ``p`` nella sottocollezione ``quale`` dell'edizione:
    collegando il record ``scelta`` se indicato, altrimenti creandone uno nuovo. Imposta
    ``p.zotero_key`` e scarica la copertina. Restituisce un avviso sulla copertina o None.
    Commit del chiamante. Tag delle proposte: per default solo in «Docenti»."""
    if not ed.zotero_collection_key:
        raise ErroreScrittura("Manca la collezione Zotero dell'edizione (Modifica edizione).")
    destinazione = [sottocollezione_edizione(zot, ed, quale)]
    tag = quale == "docenti" if tag_proposte is None else tag_proposte
    if scelta:
        zi = collega_item(zot, scelta, destinazione, tag_proposte=tag)
    else:
        campi = dict(p.campi)
        zi = crea_item(zot, p.tipo, campi, campi.pop("autori", ""), campi.pop("curatori", ""),
                       destinazione, tag_proposte=tag)
    p.zotero_key = zi.key
    if p.copertina_url and not zi.copertina_path:
        try:
            zi.copertina_path = salva_copertina(p.copertina_url)
        except Exception as e:  # noqa: BLE001  (la copertina non blocca)
            return f"Copertina non scaricata: {e}"
    return None
