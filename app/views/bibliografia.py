"""Invito alla lettura: bibliografia dalla cache del gruppo Zotero, con le copertine locali."""
import json

from flask import Blueprint, abort, current_app, render_template, request, send_from_directory
from sqlalchemy import or_

from ..extensions import db
from ..models import Edizione, SyncStato, ZoteroCollezione, ZoteroItem
from .public import _letture_edizione

bp = Blueprint("bibliografia", __name__)


def _albero(collezioni):
    """Restituisce [(collezione, livello)] in ordine gerarchico."""
    figli = {}
    for c in collezioni:
        figli.setdefault(c.parent_key, []).append(c)
    out = []

    def visita(parent, livello):
        for c in sorted(figli.get(parent, []), key=lambda x: x.nome.lower()):
            out.append((c, livello))
            visita(c.key, livello + 1)
    visita(None, 0)
    return out


def _sotto_albero(key, collezioni):
    """Key della collezione e di tutte le sue discendenti (edizione → «Relatori», «Docenti»)."""
    keys, nuovi = set(), {key}
    while nuovi:
        keys |= nuovi
        nuovi = {c.key for c in collezioni if c.parent_key in nuovi} - keys
    return keys


@bp.route("/bibliografia")
def index():
    """Di default le letture dell'ultima edizione chiusa, a sezioni (riferimenti di base,
    relatori, docenti); con ricerca, sezione di Zotero o «tutta» una griglia unica paginata."""
    q = request.args.get("q", "").strip()
    col = request.args.get("collezione", "")
    tag = request.args.get("tag", "")
    tutto = request.args.get("tutto") == "1"
    eid = request.args.get("edizione", type=int)
    collezioni = ZoteroCollezione.query.all()
    edizioni = (Edizione.query.filter(Edizione.zotero_collection_key.isnot(None),
                                      Edizione.stato.in_(("chiusa", "conclusa")))
                .order_by(Edizione.anno.desc()).all())
    # select «Mostra»: e<id> = edizione a sezioni, c<key> = sezione di Zotero, tutto
    mostra = request.args.get("mostra", "")
    if mostra == "tutto":
        tutto = True
    elif mostra.startswith("c"):
        col = mostra[1:]
    elif mostra[1:].isdigit():
        eid = int(mostra[1:])
    if q and eid and not col:  # ricerca dentro l'edizione scelta
        e = db.session.get(Edizione, eid)
        col = e.zotero_collection_key if e else ""
    comuni = dict(collezioni=_albero(collezioni), edizioni=edizioni, q=q, col=col, tag=tag, tutto=tutto,
                  ultima_sync=SyncStato.get("zotero_ultima_sync"),
                  url_gruppo=current_app.config.get("ZOTERO_GROUP_URL"))

    if not (q or col or tag or tutto):
        ed = db.session.get(Edizione, eid) if eid else (edizioni[0] if edizioni else None)
        if eid and (not ed or ed not in edizioni):
            abort(404)
        sezioni = _letture_edizione(ed, base_prima=True) if ed else []
        return render_template("bibliografia/index.html", ed=ed, sezioni=sezioni, pagina=None, **comuni)

    query = ZoteroItem.query.filter_by(eliminato=False)
    if col:
        query = query.filter(ZoteroItem.collezioni.any(
            ZoteroCollezione.key.in_(_sotto_albero(col, collezioni))))
    if q:
        like = f"%{q}%"
        query = query.filter(or_(ZoteroItem.titolo.ilike(like), ZoteroItem.autori.ilike(like),
                                 ZoteroItem.abstract.ilike(like)))
    if tag:
        query = query.filter(ZoteroItem.tags.like(f"%{json.dumps(tag, ensure_ascii=False)}%"))
    query = query.order_by(ZoteroItem.primo_autore, ZoteroItem.anno)
    pagina = query.paginate(per_page=48, error_out=False)
    return render_template("bibliografia/index.html", ed=None, sezioni=None, pagina=pagina, **comuni)


@bp.route("/bibliografia/copertine/<key>")
def copertina(key):
    """Copertina scaricata all'approvazione: si serve solo quella di un item vivo."""
    zi = ZoteroItem.query.filter_by(key=key, eliminato=False).first()
    if not zi or not zi.copertina_path:
        abort(404)
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], zi.copertina_path, max_age=86400)
