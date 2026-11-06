"""Back-office: edizioni e programma, candidature e graduatoria, materiali, utenti, Zotero."""
import csv
import io

from flask import (Blueprint, Response, abort, current_app, flash, redirect, render_template,
                   request, url_for)
from flask_login import current_user, login_required

from ..extensions import db
from ..forms import (EdizioneForm, MaterialeAdminForm, PersonaEdizioneForm, ProgrammaVoceForm,
                     StatoCandidaturaForm, ValutazioneForm)
from ..models import (ESITI_CANDIDATURA, RUOLI, STATI_MATERIALE, VISIBILITA, Candidatura,
                      Edizione, EdizionePersona, Materiale, Persona, ProgrammaVoce, SyncStato,
                      Utente, Valutazione, ZoteroItem)
from ..posta import email_esito
from ..utils import admin_required, comitato_required, elimina_upload, salva_upload

bp = Blueprint("admin", __name__)


@bp.before_request
@login_required
@comitato_required
def _protezione():
    """Tutto il back-office è riservato a comitato e admin; alcune azioni solo admin."""


@bp.route("/")
def dashboard():
    return render_template(
        "admin/dashboard.html",
        edizioni=Edizione.query.order_by(Edizione.anno.desc()).all(),
        da_valutare=Candidatura.query.filter(Candidatura.stato.in_(["inviata", "in_valutazione"])).count(),
        materiali_revisione=Materiale.query.filter_by(stato="in_revisione").count(),
        n_utenti=Utente.query.count(),
        n_biblio=ZoteroItem.query.filter_by(eliminato=False).count(),
        ultima_sync=SyncStato.get("zotero_ultima_sync"),
    )


# ------------------------------------------------------------------ edizioni
@bp.route("/edizioni/nuova", methods=["GET", "POST"])
@admin_required
def nuova_edizione():
    return _form_edizione(Edizione())


@bp.route("/edizioni/<int:eid>", methods=["GET", "POST"])
@admin_required
def modifica_edizione(eid):
    return _form_edizione(db.get_or_404(Edizione, eid))


def _form_edizione(ed):
    form = EdizioneForm(obj=ed)
    if form.validate_on_submit():
        bando = form.bando.data
        form.bando.data = None
        form.populate_obj(ed)
        if bando:
            info = salva_upload(bando, "bandi", {"pdf", "docx"})
            elimina_upload(ed.bando_path)
            ed.bando_path = info["file_path"]
        db.session.add(ed)
        db.session.commit()
        flash("Edizione salvata.", "ok")
        return redirect(url_for("admin.modifica_edizione", eid=ed.id))
    return render_template("admin/edizione_form.html", form=form, ed=ed,
                           voce_form=ProgrammaVoceForm(prefix="voce"),
                           persona_form=PersonaEdizioneForm(prefix="pers"))


@bp.post("/edizioni/<int:eid>/programma")
@admin_required
def aggiungi_voce(eid):
    ed = db.get_or_404(Edizione, eid)
    f = ProgrammaVoceForm(prefix="voce")
    if f.validate_on_submit():
        v = ProgrammaVoce(edizione=ed)
        f.populate_obj(v)
        db.session.add(v)
        db.session.commit()
    else:
        flash("Voce di programma non valida.", "errore")
    return redirect(url_for("admin.modifica_edizione", eid=eid) + "#programma")


@bp.post("/programma/<int:vid>/elimina")
@admin_required
def elimina_voce(vid):
    v = db.get_or_404(ProgrammaVoce, vid)
    eid = v.edizione_id
    db.session.delete(v)
    db.session.commit()
    return redirect(url_for("admin.modifica_edizione", eid=eid) + "#programma")


@bp.post("/edizioni/<int:eid>/persone")
@admin_required
def aggiungi_persona(eid):
    ed = db.get_or_404(Edizione, eid)
    f = PersonaEdizioneForm(prefix="pers")
    if f.validate_on_submit():
        p = (Persona.query.filter_by(nome=f.nome.data.strip(), cognome=f.cognome.data.strip()).first()
             or Persona(nome=f.nome.data.strip(), cognome=f.cognome.data.strip()))
        if f.affiliazione.data:
            p.affiliazione = f.affiliazione.data
        db.session.add(p)
        db.session.flush()
        if not EdizionePersona.query.filter_by(edizione_id=ed.id, persona_id=p.id, ruolo=f.ruolo.data).first():
            db.session.add(EdizionePersona(edizione=ed, persona=p, ruolo=f.ruolo.data))
        db.session.commit()
    return redirect(url_for("admin.modifica_edizione", eid=eid) + "#persone")


@bp.post("/edizioni-persone/<int:epid>/elimina")
@admin_required
def elimina_persona(epid):
    ep = db.get_or_404(EdizionePersona, epid)
    eid = ep.edizione_id
    db.session.delete(ep)
    db.session.commit()
    return redirect(url_for("admin.modifica_edizione", eid=eid) + "#persone")


# ------------------------------------------------------------------ candidature
def _graduatoria(ed):
    cands = [c for c in ed.candidature if c.stato != "bozza"]
    return sorted(cands, key=lambda c: (c.tipo != "borsista", -(c.punteggio_medio or -1),
                                        c.inviata_il or c.creato_il))


@bp.route("/edizioni/<int:eid>/candidature")
def candidature(eid):
    ed = db.get_or_404(Edizione, eid)
    return render_template("admin/candidature.html", ed=ed, candidature=_graduatoria(ed))


@bp.route("/edizioni/<int:eid>/candidature.csv")
def candidature_csv(eid):
    ed = db.get_or_404(Edizione, eid)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Pos.", "Cognome", "Nome", "Email", "Tipo", "Titolo UD", "Originalità",
                "Potenzialità", "Fonti", "Media totale", "N. valutazioni", "Stato"])
    for i, c in enumerate(_graduatoria(ed), 1):
        n = len(c.valutazioni) or 1
        media = lambda attr: round(sum(getattr(v, attr) for v in c.valutazioni) / n, 1)  # noqa: E731
        w.writerow([i, c.utente.cognome, c.utente.nome, c.utente.email, c.tipo, c.titolo_ud or "",
                    media("originalita"), media("potenzialita"), media("fonti"),
                    c.punteggio_medio or "", len(c.valutazioni), c.stato])
    return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=graduatoria_{ed.anno}.csv"})


@bp.route("/candidature/<int:cid>", methods=["GET", "POST"])
def candidatura(cid):
    c = db.get_or_404(Candidatura, cid)
    if c.stato == "bozza":
        abort(404)
    mia = Valutazione.query.filter_by(candidatura_id=c.id, valutatore_id=current_user.id).first()
    vform = ValutazioneForm(obj=mia, prefix="val")
    sform = StatoCandidaturaForm(obj=c, prefix="st")
    if vform.validate_on_submit() and "val-originalita" in request.form:
        mia = mia or Valutazione(candidatura=c, valutatore_id=current_user.id)
        vform.populate_obj(mia)
        db.session.add(mia)
        if c.stato == "inviata":
            c.stato = "in_valutazione"
        db.session.commit()
        flash("Valutazione salvata.", "ok")
        return redirect(url_for("admin.candidatura", cid=c.id))
    return render_template("admin/candidatura.html", c=c, vform=vform, sform=sform)


@bp.post("/candidature/<int:cid>/stato")
@admin_required
def stato_candidatura(cid):
    c = db.get_or_404(Candidatura, cid)
    f = StatoCandidaturaForm(prefix="st")
    if f.validate_on_submit():
        cambiato = c.stato != f.stato.data
        c.stato, c.note_comitato = f.stato.data, f.note_comitato.data
        db.session.commit()
        if cambiato and c.stato in ESITI_CANDIDATURA:
            email_esito(c)
            flash("Stato aggiornato ed esito comunicato al docente.", "ok")
        else:
            flash("Stato aggiornato.", "ok")
    return redirect(url_for("admin.candidatura", cid=c.id))


# ------------------------------------------------------------------ materiali
@bp.route("/materiali", methods=["GET", "POST"])
def materiali():
    form = MaterialeAdminForm()
    form.edizione_id.choices = [(e.id, f"{e.anno} – {e.titolo}")
                                for e in Edizione.query.order_by(Edizione.anno.desc())]
    if form.validate_on_submit():
        if not current_user.is_admin:
            abort(403)
        if not form.file.data and not form.url.data:
            flash("Carica un file oppure indica un link.", "errore")
        else:
            m = Materiale(edizione_id=form.edizione_id.data, titolo=form.titolo.data,
                          autori=form.autori.data, tipo=form.tipo.data,
                          descrizione=form.descrizione.data, url=form.url.data or None,
                          visibilita=form.visibilita.data, stato="pubblicato",
                          caricato_da_id=current_user.id)
            if form.file.data:
                for k, v in salva_upload(form.file.data, "materiali",
                                         current_app.config["ESTENSIONI_MATERIALI"]).items():
                    setattr(m, k, v)
            db.session.add(m)
            db.session.commit()
            flash("Materiale pubblicato.", "ok")
            return redirect(url_for("admin.materiali"))
    elenco = Materiale.query.order_by(
        (Materiale.stato == "in_revisione").desc(), Materiale.creato_il.desc()).all()
    return render_template("admin/materiali.html", form=form, materiali=elenco)


@bp.post("/materiali/<int:mid>")
@admin_required
def aggiorna_materiale(mid):
    m = db.get_or_404(Materiale, mid)
    azione = request.form.get("azione")
    if azione == "elimina":
        elimina_upload(m.file_path)
        db.session.delete(m)
    else:
        if request.form.get("stato") in STATI_MATERIALE:
            m.stato = request.form["stato"]
        if request.form.get("visibilita") in VISIBILITA:
            m.visibilita = request.form["visibilita"]
    db.session.commit()
    return redirect(url_for("admin.materiali"))


# ------------------------------------------------------------------ utenti
@bp.route("/utenti")
@admin_required
def utenti():
    return render_template("admin/utenti.html",
                           utenti=Utente.query.order_by(Utente.cognome, Utente.nome).all())


@bp.post("/utenti/<int:uid>")
@admin_required
def aggiorna_utente(uid):
    u = db.get_or_404(Utente, uid)
    if u.id == current_user.id:
        flash("Non puoi modificare il tuo stesso ruolo.", "errore")
    else:
        if request.form.get("ruolo") in RUOLI:
            u.ruolo = request.form["ruolo"]
        u.attivo = request.form.get("attivo") == "1"
        db.session.commit()
    return redirect(url_for("admin.utenti"))


# ------------------------------------------------------------------ Zotero
@bp.post("/zotero/sync")
@admin_required
def zotero_sync():
    from ..zotero_sync import sincronizza
    try:
        s = sincronizza(completa=request.form.get("completa") == "1")
        flash(f"Zotero sincronizzato: {s['item']} record aggiornati, {s['cestino']} nel cestino, "
              f"{s['eliminati']} rimossi (versione libreria {s['versione']}).", "ok")
        for a in s["avvisi"]:
            flash(a, "errore")
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        flash(f"Errore di sincronizzazione Zotero: {e}", "errore")
    return redirect(url_for("admin.dashboard"))
