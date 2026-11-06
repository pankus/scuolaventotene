"""Archivio delle edizioni precedenti: materiali PDF/PowerPoint."""
from flask import Blueprint, abort, current_app, render_template, send_from_directory
from flask_login import current_user

from ..extensions import db
from ..models import Edizione, Materiale

bp = Blueprint("archivio", __name__)


def _materiali_visibili(ed):
    return [m for m in sorted(ed.materiali, key=lambda m: (m.tipo, m.titolo))
            if m.stato == "pubblicato" and m.visibile_a(current_user)]


@bp.route("/archivio")
def index():
    edizioni = (Edizione.query.filter(Edizione.stato != "bozza")
                .order_by(Edizione.anno.desc()).all())
    conteggi = {e.id: len(_materiali_visibili(e)) for e in edizioni}
    return render_template("archivio/index.html", edizioni=edizioni, conteggi=conteggi)


@bp.route("/archivio/<slug>")
def edizione(slug):
    ed = Edizione.query.filter_by(slug=slug).first_or_404()
    if ed.stato == "bozza":
        abort(404)
    return render_template("archivio/edizione.html", ed=ed, materiali=_materiali_visibili(ed))


@bp.route("/materiali/<int:mid>/scarica")
def scarica(mid):
    m = db.get_or_404(Materiale, mid)
    if not m.file_path or not m.visibile_a(current_user):
        abort(404)
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], m.file_path,
                               as_attachment=m.mime != "application/pdf",
                               download_name=m.file_nome, mimetype=m.mime)
