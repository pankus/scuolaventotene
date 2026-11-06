"""Back-office: edizioni e programma, candidature e graduatoria, materiali, letture, utenti, Zotero."""
import csv
import io

from flask import (Blueprint, Response, abort, current_app, flash, redirect, render_template,
                   request, url_for)
from flask_login import current_user, login_required
from sqlalchemy import or_

from ..extensions import db
from .. import zotero_sync as modulo_sync  # la vista zotero_sync() ne oscura il nome
from ..forms import (CopertinaForm, DescrizioneForm, ItemZoteroForm, EdizioneForm, LetturaRevisioneForm, LezioneForm, MaterialeAdminForm,
                     MaterialeUDForm, PersonaEdizioneForm, ProgrammaVoceForm, StatoCandidaturaForm,
                     ValutazioneForm)
from ..models import (ESITI_CANDIDATURA, RUOLI, STATI_MATERIALE, VISIBILITA, Candidatura,
                      Edizione, EdizionePersona, Materiale, Persona, ProgrammaVoce,
                      PropostaLettura, SyncStato, Utente, Valutazione, ZoteroCollezione, ZoteroItem,
                      adesso)
from ..posta import email_esito
from ..ricerca_libri import cerca_copertina
from ..utils import (admin_required, carica_copertina, comitato_required, elimina_upload,
                     salva_copertina, salva_upload)
from ..zotero_scrittura import (CAMPI_MODULO, SOTTOCOLLEZIONI, ErroreScrittura, aggiorna_item,
                                campi_da_item, salva_lettura, scelte_duplicati,
                                sostituisci_copertina)

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
        letture_da_rivedere=_letture().filter(PropostaLettura.stato == "proposta").count(),
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
    radici = ZoteroCollezione.query.filter(ZoteroCollezione.parent_key.is_(None)).order_by(ZoteroCollezione.nome)
    form.zotero_collection_key.choices = [("", "— nessuna —")] + [(c.key, c.nome) for c in radici]
    if ed.zotero_collection_key and ed.zotero_collection_key not in dict(form.zotero_collection_key.choices):
        # key salvata ma non (più) in cache: resta scelta finché non si cambia
        form.zotero_collection_key.choices.append((ed.zotero_collection_key, f"{ed.zotero_collection_key} (non sincronizzata)"))
    if form.validate_on_submit():
        bando = form.bando.data
        form.bando.data = None
        if (form.zotero_collection_key.data or None) != ed.zotero_collection_key:
            ed.zotero_docenti_key = None  # la sottocollezione delle proposte si ricrea sotto la nuova
        form.populate_obj(ed)
        ed.zotero_collection_key = ed.zotero_collection_key or None
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
                           persona_form=PersonaEdizioneForm(prefix="pers"),
                           lezione_forms={ep.id: _lezione_form(ep) for ep in ed.persone
                                          if ep.ruolo in ("relatore", "docente")})


def _lezione_form(ep):
    f = LezioneForm(prefix=f"lez{ep.id}", data={"titolo_lezione": ep.titolo_lezione, "ordine": ep.ordine,
                                                "utente_id": ep.persona.utente_id or 0})
    relatori = Utente.query.filter(or_(Utente.ruolo == ep.ruolo, Utente.id == ep.persona.utente_id)) \
        .order_by(Utente.cognome, Utente.nome)
    if ep.ruolo == "docente":
        f.titolo_lezione.label.text, f.utente_id.label.text = "Titolo della UD", "Account del docente"
    f.utente_id.choices = [(0, "— nessun account —")] + [(u.id, f"{u.cognome} {u.nome} ({u.email})")
                                                       for u in relatori]
    return f


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
            db.session.add(EdizionePersona(edizione=ed, persona=p, ruolo=f.ruolo.data,
                                           titolo_lezione=(f.titolo_lezione.data or None)
                                           if f.ruolo.data != "comitato" else None))
        db.session.commit()
    return redirect(url_for("admin.modifica_edizione", eid=eid) + "#persone")


@bp.post("/edizioni-persone/<int:epid>/lezione")
@admin_required
def aggiorna_lezione(epid):
    """Titolo e ordine della lezione (o della UD di un docente) e account collegato alla persona."""
    ep = db.get_or_404(EdizionePersona, epid)
    if ep.ruolo not in ("relatore", "docente"):
        abort(404)
    f = _lezione_form(ep)
    if f.validate_on_submit():
        ep.titolo_lezione, ep.ordine = f.titolo_lezione.data or None, f.ordine.data or 0
        uid = f.utente_id.data or None
        if uid and Persona.query.filter(Persona.utente_id == uid, Persona.id != ep.persona_id).first():
            flash("Quell'account è già collegato a un'altra persona.", "errore")
        else:
            ep.persona.utente_id = uid
            flash("Lezione aggiornata.", "ok")
        db.session.commit()
    else:
        flash("Dati della lezione non validi.", "errore")
    return redirect(url_for("admin.modifica_edizione", eid=ep.edizione_id) + "#persone")


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
        if _pubblica_materiale(form, edizione_id=form.edizione_id.data):
            return redirect(url_for("admin.materiali"))
    elenco = Materiale.query.order_by(
        (Materiale.stato == "in_revisione").desc(), Materiale.creato_il.desc()).all()
    return render_template("admin/materiali.html", form=form, materiali=elenco)


def _pubblica_materiale(form, **origine):
    """Crea il materiale pubblicato dal form dell'admin; False (con avviso) se manca file e link."""
    if not form.file.data and not form.url.data:
        flash("Carica un file oppure indica un link.", "errore")
        return False
    m = Materiale(titolo=form.titolo.data, autori=form.autori.data, tipo=form.tipo.data,
                  descrizione=form.descrizione.data, url=form.url.data or None,
                  visibilita=form.visibilita.data, stato="pubblicato",
                  caricato_da_id=current_user.id, **origine)
    if form.file.data:
        for k, v in salva_upload(form.file.data, "materiali",
                                 current_app.config["ESTENSIONI_MATERIALI"]).items():
            setattr(m, k, v)
    db.session.add(m)
    db.session.commit()
    flash("Materiale pubblicato.", "ok")
    return True


def _materiale_in(origine, pagina, **chiavi):
    form = MaterialeUDForm()
    if form.validate_on_submit():
        _pubblica_materiale(form, edizione_id=origine.edizione_id, **chiavi)
    else:
        for errori in form.errors.values():
            flash(" ".join(errori), "errore")
    return redirect(pagina + "#materiali")


@bp.post("/interventi/<int:epid>/materiali")
@admin_required
def materiale_intervento(epid):
    """Materiale caricato dall'admin dentro una lezione o UD (anche delle edizioni passate)."""
    ep = db.get_or_404(EdizionePersona, epid)
    if ep.ruolo not in ("relatore", "docente"):
        abort(404)
    return _materiale_in(ep, url_for("public.intervento", slug=ep.edizione.slug, epid=ep.id),
                         lezione_id=ep.id)


@bp.post("/candidature/<int:cid>/materiali")
@admin_required
def materiale_candidatura(cid):
    c = db.get_or_404(Candidatura, cid)
    if c.stato != "ammessa":
        abort(404)
    return _materiale_in(c, url_for("public.unita_didattica", slug=c.edizione.slug, cid=c.id),
                         candidatura_id=c.id)


@bp.post("/interventi/<int:epid>/descrizione")
@admin_required
def descrizione_intervento(epid):
    ep = db.get_or_404(EdizionePersona, epid)
    if ep.ruolo not in ("relatore", "docente"):
        abort(404)
    form = DescrizioneForm()
    if form.validate_on_submit():
        ep.descrizione = form.descrizione.data or None
        db.session.commit()
        flash("Abstract salvato.", "ok")
    return redirect(url_for("public.intervento", slug=ep.edizione.slug, epid=ep.id))


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


# ------------------------------------------------------------------ item della bibliografia
def _torna():
    """Pagina da cui si è arrivati (solo percorsi interni), per il link di ritorno."""
    t = request.values.get("torna", "")
    return t if t.startswith("/") and not t.startswith("//") else url_for("bibliografia.index")


@bp.route("/bibliografia/<key>", methods=["GET", "POST"])
@admin_required
def item_zotero(key):
    """Scheda di un item dell'invito alla lettura: campi (scritti in Zotero) e copertina."""
    zi = ZoteroItem.query.filter_by(key=key, eliminato=False).first_or_404()
    modificabile = zi.tipo in CAMPI_MODULO
    form = ItemZoteroForm(data={**campi_da_item(zi), "versione": zi.version} if modificabile else None)
    form_cop = CopertinaForm()
    azione = request.form.get("azione")
    torna = _torna()

    if azione == "scheda" and modificabile and form.validate_on_submit():
        campi = {k: (form[k].data or "").strip() for k in CAMPI_MODULO[zi.tipo]
                 if k not in ("autori", "curatori")}
        try:
            aggiorna_item(modulo_sync.client(), key, form.versione.data, campi,
                          form.autori.data or "", (form.curatori.data or "") if zi.tipo == "book" else None)
        except (ErroreScrittura, RuntimeError) as e:
            db.session.rollback()
            flash(str(e), "errore")
        except Exception as e:  # noqa: BLE001  (rete, permessi)
            db.session.rollback()
            flash(f"Scrittura in Zotero non riuscita: {e}", "errore")
        else:
            db.session.commit()
            flash("Scheda aggiornata in Zotero.", "ok")
            return redirect(url_for("admin.item_zotero", key=key, torna=torna))

    elif azione in ("cerca", "url", "file", "togli") and form_cop.validate_on_submit():
        try:
            if azione == "togli":
                sostituisci_copertina(zi, "")
            elif azione == "cerca":
                if not zi.isbn:
                    raise ValueError("l'item non ha un ISBN")
                sostituisci_copertina(zi, cerca_copertina(zi.isbn))
            elif azione == "url":
                if not form_cop.url.data:
                    raise ValueError("indica l'indirizzo dell'immagine")
                sostituisci_copertina(zi, salva_copertina(form_cop.url.data))
            else:
                if not form_cop.file.data:
                    raise ValueError("scegli un file")
                sostituisci_copertina(zi, carica_copertina(form_cop.file.data))
        except Exception as e:  # noqa: BLE001  (host non ammesso, non immagine, rete)
            db.session.rollback()
            flash(f"Copertina non salvata: {e}", "errore")
        else:
            db.session.commit()
            flash("Copertina tolta." if azione == "togli" else "Copertina salvata.", "ok")
            return redirect(url_for("admin.item_zotero", key=key, torna=torna))

    return render_template("admin/item_zotero.html", zi=zi, form=form, form_cop=form_cop,
                           modificabile=modificabile, campi=CAMPI_MODULO.get(zi.tipo, []), torna=torna,
                           url_zotero=current_app.config.get("ZOTERO_GROUP_URL"))


# ------------------------------------------------------------------ letture proposte
def _letture():
    """Proposte delle candidature inviate (quelle in bozza le vede solo il docente)."""
    return PropostaLettura.query.join(Candidatura).filter(Candidatura.stato != "bozza")


@bp.route("/letture")
def letture():
    edizioni = Edizione.query.order_by(Edizione.anno.desc()).all()
    ed = db.session.get(Edizione, request.args.get("edizione", type=int) or 0) or \
        (edizioni[0] if edizioni else None)
    elenco = []
    if ed:
        elenco = (_letture().filter(Candidatura.edizione_id == ed.id)
                  .order_by((PropostaLettura.stato == "proposta").desc(), PropostaLettura.id).all())
    return render_template("admin/letture.html", edizioni=edizioni, ed=ed, letture=elenco)


def _scelte_zotero(p, zot):
    """Item Zotero a cui collegare la proposta: (key, descrizione). Vuota se non ce ne sono."""
    scelte, avviso = scelte_duplicati(zot, p.tipo, p.campi)
    if avviso:
        flash(avviso, "errore")
    if p.zotero_key and p.zotero_key not in {k for k, _ in scelte}:
        z = db.session.get(ZoteroItem, p.zotero_key)
        scelte.insert(0, (p.zotero_key, f"{z.titolo if z else p.zotero_key} (scelto dal docente)"))
    return scelte


@bp.route("/letture/<int:pid>", methods=["GET", "POST"])
def lettura(pid):
    p = _letture().filter(PropostaLettura.id == pid).first_or_404()
    ed = p.candidatura.edizione
    form = LetturaRevisioneForm(data={**p.campi, "nota_comitato": p.nota_comitato})
    try:
        zot = modulo_sync.client()
    except RuntimeError:
        zot = None
    azione = request.form.get("azione")
    if request.method == "POST" and p.stato == "approvata":
        abort(409)  # già in Zotero: si corregge lì

    if azione == "rifiuta":
        p.stato, p.nota_comitato = "rifiutata", form.nota_comitato.data
        p.deciso_il, p.deciso_da_id = adesso(), current_user.id
        db.session.commit()
        flash("Proposta rifiutata.", "ok")
        return redirect(url_for("admin.letture", edizione=ed.id))

    scelte = None
    if azione == "approva" and form.validate_on_submit():
        p.campi = {k: (form[k].data or "").strip() for k in CAMPI_MODULO[p.tipo]}
        scelta = request.form.get("zotero_key", "")
        nuovi = []
        if zot is not None and not scelta:
            # "crea nuovo": si ricontrolla ora, perché dall'apertura della pagina un altro
            # membro del comitato può aver approvato lo stesso libro (o la scheda è cambiata)
            scelte = _scelte_zotero(p, zot)
            visti = set(request.form.get("visti", "").split(","))
            nuovi = [k for k, _ in scelte if k not in visti]
            if nuovi:
                flash("Ci sono possibili doppioni che la pagina non mostrava: controlla e conferma.",
                      "errore")
        if zot is None:
            flash("Zotero non è configurato (.env).", "errore")
        elif not nuovi:
            try:
                avviso = salva_lettura(zot, p, ed, "docenti", scelta)
            except ErroreScrittura as e:
                db.session.rollback()
                flash(str(e), "errore")
            except Exception as e:  # noqa: BLE001  (rete, permessi)
                db.session.rollback()
                flash(f"Scrittura in Zotero non riuscita: {e}", "errore")
            else:
                p.stato, p.nota_comitato = "approvata", form.nota_comitato.data
                p.deciso_il, p.deciso_da_id = adesso(), current_user.id
                db.session.commit()
                if avviso:
                    flash(avviso, "errore")
                flash("Lettura approvata e salvata in Zotero.", "ok")
                return redirect(url_for("admin.letture", edizione=ed.id))

    if scelte is None:
        scelte = _scelte_zotero(p, zot) if p.stato != "approvata" else []
    radice = ed.zotero_collection_key and db.session.get(ZoteroCollezione, ed.zotero_collection_key)
    destinazione = f"{radice.nome if radice else ed.zotero_collection_key} › {SOTTOCOLLEZIONI['docenti'][0]}" \
        if ed.zotero_collection_key else None
    return render_template("admin/lettura.html", p=p, ed=ed, form=form, scelte=scelte,
                           destinazione=destinazione,
                           campi=CAMPI_MODULO[p.tipo])


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
