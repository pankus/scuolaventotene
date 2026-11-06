"""Invito alla lettura: bibliografia dalla cache del gruppo Zotero."""
import json

from flask import Blueprint, current_app, render_template, request
from sqlalchemy import or_

from ..models import SyncStato, ZoteroCollezione, ZoteroItem

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


@bp.route("/bibliografia")
def index():
    q = request.args.get("q", "").strip()
    col = request.args.get("collezione", "")
    tag = request.args.get("tag", "")

    query = ZoteroItem.query.filter_by(eliminato=False)
    if col:
        query = query.filter(ZoteroItem.collezioni.any(key=col))
    if q:
        like = f"%{q}%"
        query = query.filter(or_(ZoteroItem.titolo.ilike(like), ZoteroItem.autori.ilike(like),
                                 ZoteroItem.abstract.ilike(like)))
    if tag:
        query = query.filter(ZoteroItem.tags.like(f"%{json.dumps(tag, ensure_ascii=False)}%"))
    query = query.order_by(ZoteroItem.primo_autore, ZoteroItem.anno)
    pagina = query.paginate(per_page=50, error_out=False)

    return render_template("bibliografia/index.html", pagina=pagina, q=q, col=col, tag=tag,
                           collezioni=_albero(ZoteroCollezione.query.all()),
                           ultima_sync=SyncStato.get("zotero_ultima_sync"),
                           url_gruppo=current_app.config.get("ZOTERO_GROUP_URL"))
