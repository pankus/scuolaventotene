"""Area riservata del docente: profilo, candidatura a passi (profilo, UD, invito alla lettura,
riepilogo e invio), invio materiali, ricerca dei libri."""
import time
from collections import defaultdict, deque

from flask import (Blueprint, abort, current_app, flash, jsonify, redirect, render_template,
                   request, send_from_directory, url_for)
from flask_login import current_user, login_required

from ..extensions import db
from ..forms import CandidaturaForm, LetturaDocenteForm, MaterialeForm, ProfiloForm
from ..models import Candidatura, Edizione, Materiale, PropostaLettura, ZoteroItem, adesso
from ..posta import email_conferma_invio
from ..ricerca_libri import cerca
from ..utils import copertina_ammessa, conta_caratteri, elimina_upload, salva_upload
from ..zotero_scrittura import CAMPI_MODULO

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
                           candidature=current_user.candidature, materiali=materiali,
                           lezioni=current_user.lezioni() if current_user.is_relatore else [])


@bp.route("/profilo", methods=["GET", "POST"])
def profilo():
    # ?edizione=<slug>: passo 1 della candidatura, poi si prosegue con la proposta
    ed = Edizione.query.filter_by(slug=request.args.get("edizione", "")).first()
    form = ProfiloForm(obj=current_user)
    if form.validate_on_submit():
        form.populate_obj(current_user)
        db.session.commit()
        flash("Profilo aggiornato.", "ok")
        return redirect(url_for("area.candidatura", slug=ed.slug) if ed else url_for("area.dashboard"))
    cand = ed and Candidatura.query.filter_by(utente_id=current_user.id, edizione_id=ed.id).first()
    return render_template("area/profilo.html", form=form, ed=ed, cand=cand)


# "edizione/" evita lo scontro con /candidatura/<int:cid> quando lo slug è un anno (2027)
@bp.route("/candidatura/edizione/<slug>", methods=["GET", "POST"])
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
        flash("Bozza salvata. Ora puoi consigliare libri e siti (facoltativo).", "ok")
        return redirect(url_for("area.letture", cid=cand.id))
    return render_template("area/candidatura_form.html", form=form, ed=ed, cand=cand)


@bp.route("/candidatura/<int:cid>")
def dettaglio(cid):
    c = _mia_candidatura(cid)
    return render_template("area/candidatura.html", c=c, problemi=c.problemi_invio())


MAX_LETTURE = 10  # per candidatura


@bp.route("/candidatura/<int:cid>/letture", methods=["GET", "POST"])
def letture(cid):
    """Passo 3: invito alla lettura (facoltativo). Si modifica finché la candidatura è in bozza."""
    c = _mia_candidatura(cid)
    p = None
    if request.values.get("p"):
        p = next((x for x in c.letture if x.id == request.values.get("p", type=int)), None) or abort(404)
    tipo = p.tipo if p else ("webpage" if request.args.get("tipo") == "webpage" else "book")
    form = LetturaDocenteForm(data={**p.campi, "motivazione": p.motivazione, "zotero_key": p.zotero_key,
                                    "copertina_url": p.copertina_url} if p else None)
    if c.stato == "bozza" and form.validate_on_submit():
        if p is None and len(c.letture) >= MAX_LETTURE:
            flash(f"Puoi consigliare al massimo {MAX_LETTURE} letture.", "errore")
            return redirect(url_for("area.letture", cid=c.id))
        p = p or PropostaLettura(candidatura=c, tipo=tipo, momento="iscrizione")
        db.session.add(p)
        p.campi = {k: (form[k].data or "").strip() for k in CAMPI_MODULO[tipo]}
        p.motivazione = form.motivazione.data
        # dalla ricerca: si tengono solo valori verificabili
        key = form.zotero_key.data or None
        p.zotero_key = key if key and ZoteroItem.query.filter_by(key=key, eliminato=False).first() else None
        p.copertina_url = form.copertina_url.data if copertina_ammessa(form.copertina_url.data) else None
        db.session.commit()
        flash("Lettura salvata.", "ok")
        return redirect(url_for("area.letture", cid=c.id))
    return render_template("area/letture.html", c=c, ed=c.edizione, form=form, tipo=tipo, p=p,
                           campi=CAMPI_MODULO[tipo], max_letture=MAX_LETTURE)


@bp.post("/candidatura/<int:cid>/letture/<int:pid>/elimina")
def elimina_lettura(cid, pid):
    c = _mia_candidatura(cid)
    p = next((x for x in c.letture if x.id == pid), None) or abort(404)
    if c.stato != "bozza":
        abort(400)
    db.session.delete(p)
    db.session.commit()
    flash("Lettura eliminata.", "info")
    return redirect(url_for("area.letture", cid=c.id))


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
    # ?lezione=<id>: materiale della lezione di un relatore (solo la propria)
    lezione = None
    if request.args.get("lezione"):
        lezione = next((ep for ep in current_user.lezioni()
                        if ep.id == request.args.get("lezione", type=int)), None) or abort(404)
    form = MaterialeForm()
    edizioni = [lezione.edizione] if lezione else \
        Edizione.query.filter(Edizione.stato != "bozza").order_by(Edizione.anno.desc())
    form.edizione_id.choices = [(e.id, f"{e.anno} – {e.titolo}") for e in edizioni]
    if form.validate_on_submit():
        if not form.file.data and not form.url.data:
            flash("Carica un file oppure indica un link.", "errore")
        else:
            m = Materiale(edizione_id=form.edizione_id.data, titolo=form.titolo.data,
                          autori=form.autori.data or current_user.nome_completo,
                          tipo=form.tipo.data, descrizione=form.descrizione.data,
                          url=form.url.data or None, caricato_da_id=current_user.id,
                          lezione=lezione, stato="in_revisione", visibilita="pubblico")
            if form.file.data:
                info = salva_upload(form.file.data, "materiali",
                                    current_app.config["ESTENSIONI_MATERIALI"])
                for k, v in info.items():
                    setattr(m, k, v)
            db.session.add(m)
            db.session.commit()
            flash("Materiale inviato: sarà pubblicato dopo la revisione.", "ok")
            return redirect(url_for("area.dashboard"))
    return render_template("area/materiale_form.html", form=form, lezione=lezione)


# ------------------------------------------------------------------ ricerca dei libri (lookup)
LIMITE_RICERCHE = 30  # al minuto, per utente
# ponytail: memoria del processo; con più processi mod_wsgi il limite vale per processo
_ricerche = defaultdict(deque)


def _troppe_ricerche(uid):
    ora, coda = time.monotonic(), _ricerche[uid]
    while coda and ora - coda[0] > 60:
        coda.popleft()
    if len(coda) >= LIMITE_RICERCHE:
        return True
    coda.append(ora)
    return False


@bp.route("/letture/cerca")
def cerca_letture():
    q = request.args.get("q", "").strip()
    if len(q) < 3:
        return jsonify(errore="Scrivi almeno 3 caratteri."), 400
    if _troppe_ricerche(current_user.id):
        return jsonify(errore="Troppe ricerche: riprova tra un minuto."), 429
    return jsonify(cerca(q[:200], request.args.get("isbn")))
