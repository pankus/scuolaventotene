"""Archivio delle edizioni precedenti: materiali PDF/PowerPoint."""
from flask import Blueprint, abort, current_app, render_template, send_from_directory, url_for
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
    materiali = _materiali_visibili(ed)
    n_mat = {}
    for m in materiali:
        chiave = ("iv", m.intervento_id) if m.intervento_id else ("c", m.candidatura_id) if m.candidatura_id else None
        n_mat[chiave] = n_mat.get(chiave, 0) + 1

    def voce(url, titolo, autore, chiave, letture):
        return {"url": url, "titolo": titolo or "Senza titolo", "autore": autore,
                "materiali": n_mat.get(chiave, 0),
                "letture": sum(1 for p in letture if p.stato == "approvata" and p.zotero_key)}

    def voce_iv(iv):
        return voce(url_for("public.intervento", slug=ed.slug, iid=iv.id), iv.titolo, iv.nomi_autori,
                    ("iv", iv.id), iv.letture)

    ivs = sorted((iv for iv in ed.interventi if not iv.candidatura), key=lambda iv: iv.posizione)  # quelle: sotto
    lezioni = [voce_iv(iv) for iv in ivs if not iv.ud]
    ud = [voce_iv(iv) for iv in ivs if iv.ud]
    ud += [voce(url_for("public.unita_didattica", slug=ed.slug, cid=c.id), c.titolo_ud,
                c.nomi_autori, ("c", c.id), c.letture)
           for c in sorted(ed.candidature, key=lambda c: c.titolo_ud or "")
           if c.stato == "ammessa" and c.titolo_ud]
    return render_template("archivio/edizione.html", ed=ed, lezioni=lezioni, ud=ud,
                           altri=[m for m in materiali if not m.intervento_id and not m.candidatura_id])


@bp.route("/materiali/<int:mid>/scarica")
def scarica(mid):
    m = db.get_or_404(Materiale, mid)
    if not m.file_path or not m.visibile_a(current_user):
        abort(404)
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], m.file_path,
                               as_attachment=m.mime != "application/pdf",
                               download_name=m.file_nome, mimetype=m.mime)
