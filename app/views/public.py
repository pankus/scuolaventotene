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
    letture = []
    if ed.zotero_collection_key:
        col = db.session.get(ZoteroCollezione, ed.zotero_collection_key)
        if col:
            letture = sorted((i for i in col.items if not i.eliminato),
                             key=lambda i: (i.primo_autore or "", i.anno or ""))
    return render_template("public/edizione.html", ed=ed, letture=letture)


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
