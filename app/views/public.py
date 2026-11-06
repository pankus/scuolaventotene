"""Sito pubblico: home, pagina edizione, la scuola, contatti, privacy."""
from flask import Blueprint, abort, current_app, render_template, send_from_directory

from ..extensions import db
from ..models import Edizione, ZoteroCollezione

bp = Blueprint("public", __name__)


def edizione_corrente():
    """L'edizione 'in vetrina': prima quella aperta, poi la più recente pubblicata."""
    q = Edizione.query.filter(Edizione.stato != "bozza")
    return (q.filter_by(stato="aperta").order_by(Edizione.anno.desc()).first()
            or q.order_by(Edizione.anno.desc()).first())


@bp.route("/")
def index():
    corrente = edizione_corrente()
    precedenti = (Edizione.query.filter(Edizione.stato != "bozza")
                  .order_by(Edizione.anno.desc()).all())
    return render_template("public/index.html", corrente=corrente,
                           precedenti=[e for e in precedenti if e != corrente])


@bp.route("/edizioni/<slug>")
def edizione(slug):
    ed = Edizione.query.filter_by(slug=slug).first_or_404()
    if ed.stato == "bozza":
        abort(404)
    return render_template("public/edizione.html", ed=ed, letture=_letture_edizione(ed))


def _letture_edizione(ed):
    """Invito alla lettura: [(titolo sezione o None, item)] dal sotto-albero della collezione
    dell'edizione. Prima i record della radice, poi una sezione per sottocollezione in ordine di
    nome ("Relatori"; nelle edizioni vecchie una per lezione), per ultima "Docenti". Un item
    compare una volta sola."""
    radice = ed.zotero_collection_key and db.session.get(ZoteroCollezione, ed.zotero_collection_key)
    if not radice:
        return []
    figli = {}
    for c in ZoteroCollezione.query.all():
        figli.setdefault(c.parent_key, []).append(c)

    def discendenti(c):
        out = [c]
        for f in figli.get(c.key, []):
            out += discendenti(f)
        return out

    sezioni = [(None, [radice])]
    for c in sorted(figli.get(radice.key, []),
                    key=lambda c: (c.key == ed.zotero_docenti_key, c.nome.lower())):
        sezioni.append((c.nome, discendenti(c)))
    visti, out = set(), []
    for titolo, cols in sezioni:
        items = sorted({i.key: i for c in cols for i in c.items
                        if not i.eliminato and i.key not in visti}.values(),
                       key=lambda i: (i.primo_autore or "", i.anno or ""))
        visti |= {i.key for i in items}
        if items:
            out.append((titolo, items))
    return out


@bp.route("/edizioni/<slug>/bando")
def bando(slug):
    ed = Edizione.query.filter_by(slug=slug).first_or_404()
    if ed.stato == "bozza" or not ed.bando_path:
        abort(404)
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], ed.bando_path,
                               download_name=f"Bando_Ventotene_{ed.anno}.pdf")


@bp.route("/la-scuola")
def la_scuola():
    return render_template("public/la_scuola.html")


@bp.route("/contatti")
def contatti():
    return render_template("public/contatti.html")


@bp.route("/privacy")
def privacy():
    return render_template("public/privacy.html")
