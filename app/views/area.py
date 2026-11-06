"""Area riservata del docente: profilo, candidature, invio materiali."""
from flask import (Blueprint, abort, current_app, flash, redirect, render_template,
                   send_from_directory, url_for)
from flask_login import current_user, login_required

from ..extensions import db
from ..forms import CandidaturaForm, MaterialeForm, ProfiloForm
from ..models import Candidatura, Edizione, Materiale, adesso
from ..posta import email_conferma_invio
from ..utils import conta_caratteri, elimina_upload, salva_upload

bp = Blueprint("area", __name__)


@bp.before_request
@login_required
def _protezione():
    pass


def _mia_candidatura(cid):
    c = db.get_or_404(Candidatura, cid)
    if c.utente_id != current_user.id:
        abort(404)
    return c


@bp.route("/")
def dashboard():
    aperte = [e for e in Edizione.query.filter_by(stato="aperta").all() if e.candidature_aperte]
    gia = {c.edizione_id for c in current_user.candidature}
    materiali = Materiale.query.filter_by(caricato_da_id=current_user.id).order_by(
        Materiale.creato_il.desc()).all()
    return render_template("area/dashboard.html", aperte=[e for e in aperte if e.id not in gia],
                           candidature=current_user.candidature, materiali=materiali)


@bp.route("/profilo", methods=["GET", "POST"])
def profilo():
    form = ProfiloForm(obj=current_user)
    if form.validate_on_submit():
        form.populate_obj(current_user)
        db.session.commit()
        flash("Profilo aggiornato.", "ok")
        return redirect(url_for("area.dashboard"))
    return render_template("area/profilo.html", form=form)


@bp.route("/candidatura/<slug>", methods=["GET", "POST"])
def candidatura(slug):
    ed = Edizione.query.filter_by(slug=slug).first_or_404()
    cand = Candidatura.query.filter_by(utente_id=current_user.id, edizione_id=ed.id).first()
    if cand and cand.stato != "bozza":
        return redirect(url_for("area.dettaglio", cid=cand.id))
    if not ed.candidature_aperte:
        flash("Le candidature per questa edizione non sono aperte.", "errore")
        return redirect(url_for("area.dashboard"))

    form = CandidaturaForm(obj=cand)
    if form.validate_on_submit():
        if cand is None:
            cand = Candidatura(utente=current_user, edizione=ed)
            db.session.add(cand)
        cand.tipo = form.tipo.data
        cand.titolo_ud = form.titolo_ud.data
        cand.discipline = form.discipline.data
        cand.abstract = form.abstract.data
        if form.file.data:
            info = salva_upload(form.file.data, f"candidature/{ed.slug}",
                                current_app.config["ESTENSIONI_PROPOSTE"])
            elimina_upload(cand.file_path)
            cand.file_path, cand.file_nome = info["file_path"], info["file_nome"]
            cand.n_caratteri = conta_caratteri(cand.file_path)
        db.session.commit()
        flash("Bozza salvata. Controlla i dati e invia la candidatura.", "ok")
        return redirect(url_for("area.dettaglio", cid=cand.id))
    return render_template("area/candidatura_form.html", form=form, ed=ed, cand=cand)


@bp.route("/candidatura/<int:cid>")
def dettaglio(cid):
    c = _mia_candidatura(cid)
    return render_template("area/candidatura.html", c=c, problemi=c.problemi_invio())


@bp.post("/candidatura/<int:cid>/invia")
def invia(cid):
    c = _mia_candidatura(cid)
    if c.stato != "bozza" or not c.edizione.candidature_aperte:
        abort(400)
    problemi = c.problemi_invio()
    if problemi:
        for p in problemi:
            flash(p, "errore")
        return redirect(url_for("area.dettaglio", cid=c.id))
    c.stato, c.inviata_il = "inviata", adesso()
    db.session.commit()
    email_conferma_invio(c)
    flash("Candidatura inviata. Riceverai l'esito entro la data indicata nel bando.", "ok")
    return redirect(url_for("area.dettaglio", cid=c.id))


@bp.post("/candidatura/<int:cid>/ritira")
def ritira(cid):
    c = _mia_candidatura(cid)
    if c.stato in ("bozza", "inviata", "in_valutazione", "ammessa", "riserva"):
        c.stato = "ritirata"
        db.session.commit()
        flash("Candidatura ritirata.", "info")
    return redirect(url_for("area.dashboard"))


@bp.route("/candidatura/<int:cid>/file")
def file_candidatura(cid):
    c = db.get_or_404(Candidatura, cid)
    if c.utente_id != current_user.id and not current_user.is_comitato:
        abort(404)
    if not c.file_path:
        abort(404)
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], c.file_path,
                               as_attachment=True, download_name=c.file_nome)


@bp.route("/materiali/nuovo", methods=["GET", "POST"])
def nuovo_materiale():
    form = MaterialeForm()
    form.edizione_id.choices = [(e.id, f"{e.anno} – {e.titolo}") for e in
                                Edizione.query.filter(Edizione.stato != "bozza")
                                .order_by(Edizione.anno.desc())]
    if form.validate_on_submit():
        if not form.file.data and not form.url.data:
            flash("Carica un file oppure indica un link.", "errore")
        else:
            m = Materiale(edizione_id=form.edizione_id.data, titolo=form.titolo.data,
                          autori=form.autori.data or current_user.nome_completo,
                          tipo=form.tipo.data, descrizione=form.descrizione.data,
                          url=form.url.data or None, caricato_da_id=current_user.id,
                          stato="in_revisione", visibilita="pubblico")
            if form.file.data:
                info = salva_upload(form.file.data, "materiali",
                                    current_app.config["ESTENSIONI_MATERIALI"])
                for k, v in info.items():
                    setattr(m, k, v)
            db.session.add(m)
            db.session.commit()
            flash("Materiale inviato: sarà pubblicato dopo la revisione.", "ok")
            return redirect(url_for("area.dashboard"))
    return render_template("area/materiale_form.html", form=form)
