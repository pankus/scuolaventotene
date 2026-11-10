"""Back-office: edizioni e programma, candidature e graduatoria, materiali, letture, utenti, Zotero."""
import csv
import io

from flask import (Blueprint, Response, abort, current_app, flash, redirect, render_template,
                   request, url_for)
from flask_login import current_user, login_required

from ..edizioni_precedenti import lezioni_dal_programma
from ..extensions import db
from .. import zotero_sync as modulo_sync  # la vista zotero_sync() ne oscura il nome
from ..forms import (CopertinaForm, DescrizioneForm, EmailPartecipantiForm, ItemZoteroForm, EdizioneForm, LetturaRevisioneForm, LezioneForm, MaterialeAdminForm,
                     MaterialeUDForm, PersonaEdizioneForm, ProgrammaVoceForm, StatoCandidaturaForm,
                     ValutazioneForm)
from ..models import (ESITI_CANDIDATURA, GRUPPI_PARTECIPANTI, RUOLI_EDIZIONE, STATI_MATERIALE, VISIBILITA, Candidatura,
                      Edizione, EdizionePersona, Materiale, Persona, ProgrammaVoce,
                      PropostaLettura, SyncStato, Utente, Valutazione, ZoteroCollezione, ZoteroItem,
                      adesso)
from ..posta import email_esito, email_partecipanti, indirizzi_risposta
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


def _edizioni_visibili():
    """Edizioni del back-office: tutte per l'admin, quelle del proprio comitato per gli altri."""
    q = Edizione.query.order_by(Edizione.anno.desc())
    return q if current_user.is_admin else q.filter(Edizione.id.in_(current_user.edizioni_comitato()))


def _filtra_edizioni(q, colonna):
    """Restringe una query alle edizioni del comitato dell'utente (l'admin vede tutto)."""
    return q if current_user.is_admin else q.filter(colonna.in_(current_user.edizioni_comitato()))


def _edizione_comitato(eid):
    ed = db.get_or_404(Edizione, eid)
    return ed if current_user.comitato_di(ed) else abort(404)


@bp.route("/")
def dashboard():
    return render_template(
        "admin/dashboard.html",
        edizioni=_edizioni_visibili().all(),
        da_valutare=_filtra_edizioni(Candidatura.query, Candidatura.edizione_id)
        .filter(Candidatura.stato.in_(["inviata", "in_valutazione"])).count(),
        materiali_revisione=_filtra_edizioni(Materiale.query, Materiale.edizione_id)
        .filter_by(stato="in_revisione").count(),
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
                           voce_form=ProgrammaVoceForm(prefix="voce", ordine=None),
                           voce_forms={v.id: ProgrammaVoceForm(prefix=f"v{v.id}", obj=v) for v in ed.programma},
                           persona_form=PersonaEdizioneForm(prefix="pers"),
                           lezione_forms={ep.id: _lezione_form(ep) for ep in ed.persone
                                          if ep.ruolo in ("relatore", "docente")})


def _lezione_form(ep):
    f = LezioneForm(prefix=f"lez{ep.id}", data={"titolo_lezione": ep.titolo_lezione, "ordine": ep.ordine,
                                                "utente_id": ep.persona.utente_id or 0})
    relatori = Utente.query.order_by(Utente.cognome, Utente.nome)  # qualsiasi account: il ruolo è l'EP
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
        if v.ordine is None:  # senza ordine: in fondo
            v.ordine = max((x.ordine or 0 for x in ed.programma if x is not v), default=-1) + 1
        db.session.add(v)
        db.session.commit()
        if v.tipo == "lezione":
            _crea_lezioni(ed)
    else:
        flash("Voce di programma non valida.", "errore")
    return redirect(url_for("admin.modifica_edizione", eid=eid) + "#programma")


@bp.post("/programma/<int:vid>")
@admin_required
def aggiorna_voce(vid):
    v = db.get_or_404(ProgrammaVoce, vid)
    f = ProgrammaVoceForm(prefix=f"v{vid}")
    if f.validate_on_submit():
        vecchio = v.titolo
        f.populate_obj(v)
        v.ordine = v.ordine or 0
        if v.titolo != vecchio:  # la lezione segue il titolo, così il link del programma regge
            for ep in v.edizione.persone:
                if ep.ruolo == "relatore" and ep.titolo_lezione == vecchio:
                    ep.titolo_lezione = v.titolo
        db.session.commit()
        flash("Voce aggiornata.", "ok")
        if v.tipo == "lezione":
            _crea_lezioni(v.edizione)
    else:
        flash("Voce di programma non valida.", "errore")
    return redirect(url_for("admin.modifica_edizione", eid=v.edizione_id) + "#programma")


@bp.post("/edizioni/<int:eid>/programma/ordine")
@admin_required
def ordina_programma(eid):
    """Nuovo ordine delle voci dopo il trascinamento (ordine.js): id nell'ordine voluto."""
    ed = db.get_or_404(Edizione, eid)
    voci = {v.id: v for v in ed.programma}
    for i, vid in enumerate(request.form.getlist("id", type=int)):
        if vid in voci:
            voci[vid].ordine = i
    db.session.commit()
    return "", 204


@bp.post("/edizioni/<int:eid>/lezioni-dal-programma")
@admin_required
def lezioni_programma(eid):
    ed = db.get_or_404(Edizione, eid)
    if not _crea_lezioni(ed):
        flash("Nessuna lezione da creare: tutte le voci «lezione» hanno già la loro.", "ok")
    return redirect(url_for("admin.modifica_edizione", eid=eid) + "#persone")


def _crea_lezioni(ed):
    """Lezioni mancanti dalle voci «lezione» del programma (una per relatore)."""
    n = lezioni_dal_programma(ed)
    db.session.commit()
    if n:
        flash(f"Create {n} lezioni dal programma." if n > 1 else "Creata 1 lezione dal programma.", "ok")
    return n


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
    ed = _edizione_comitato(eid)
    return render_template("admin/candidature.html", ed=ed, candidature=_graduatoria(ed))


@bp.route("/edizioni/<int:eid>/candidature.csv")
def candidature_csv(eid):
    ed = _edizione_comitato(eid)
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
    if c.stato == "bozza" or not current_user.comitato_di(c.edizione_id):
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
    elenco = _filtra_edizioni(Materiale.query, Materiale.edizione_id).order_by(
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
    """Proposte delle candidature inviate (quelle in bozza le vede solo il docente), delle
    edizioni del proprio comitato."""
    return _filtra_edizioni(PropostaLettura.query.join(Candidatura), Candidatura.edizione_id) \
        .filter(Candidatura.stato != "bozza")


@bp.route("/letture")
def letture():
    edizioni = _edizioni_visibili().all()
    ed = next((e for e in edizioni if e.id == request.args.get("edizione", type=int)), None) or \
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
    """Elenco filtrabile per edizione e partecipazione (?edizione=<id>&gruppo=<chiave>)."""
    eid = request.args.get("edizione", 0, type=int)
    gruppo = request.args.get("gruppo", "")
    tutti = Utente.query.order_by(Utente.cognome, Utente.nome).all()
    if gruppo == "nessuno":
        elenco = [u for u in tutti if not _edizioni_di(u)]
    elif gruppo in GRUPPI_PARTECIPANTI:
        elenco = _partecipanti(eid, [gruppo], solo_attivi=False)[0]
    elif eid:
        elenco = [u for u in tutti if eid in _edizioni_di(u)]
    else:
        elenco = tutti
    return render_template("admin/utenti.html", utenti=elenco, eid=eid, gruppo=gruppo,
                           edizioni=Edizione.query.order_by(Edizione.anno.desc()).all())


def _edizioni_di(u):
    """Id delle edizioni a cui l'account è legato: UD, lezioni o comitato (via Persona) e candidature."""
    return {ep.edizione_id for ep in (u.persona.edizioni if u.persona else [])} \
        | {c.edizione_id for c in u.candidature}


def _torna_a_utenti():
    """Alla lista com'era filtrata; solo verso /admin/utenti (niente redirect altrove)."""
    r = request.form.get("ritorno", "")
    return redirect(r if r.startswith(url_for("admin.utenti")) else url_for("admin.utenti"))


@bp.post("/utenti/<int:uid>")
@admin_required
def aggiorna_utente(uid):
    """Nome e cognome (anche i propri: gli account importati possono averli sbagliati),
    amministratore e attivo (non i propri)."""
    u = db.get_or_404(Utente, uid)
    nome, cognome = request.form.get("nome", "").strip(), request.form.get("cognome", "").strip()
    if not (nome and cognome) or len(nome) > 100 or len(cognome) > 100:
        flash("Nome e cognome sono obbligatori (al massimo 100 caratteri).", "errore")
        return _torna_a_utenti()
    u.nome, u.cognome = nome, cognome
    if u.id != current_user.id:
        u.admin = request.form.get("admin") == "1"
        u.attivo = request.form.get("attivo") == "1"
    db.session.commit()
    flash(f"Utente {u.email} aggiornato.", "ok")
    return _torna_a_utenti()


@bp.post("/utenti/<int:uid>/edizione")
@admin_required
def edizione_utente(uid):
    """Con `epid`: sposta quella UD/lezione dell'account in un'altra edizione (titolo, materiali e
    letture vanno con lei). Senza: aggiunge l'account all'edizione con il `ruolo` scelto
    (RUOLI_EDIZIONE): lezione del relatore, UD del docente o comitato."""
    u = db.get_or_404(Utente, uid)
    ed = db.get_or_404(Edizione, request.form.get("edizione", 0, type=int))
    epid = request.form.get("epid", type=int)
    if epid:
        ep = db.get_or_404(EdizionePersona, epid)
        if ep.persona.utente_id != u.id:
            abort(404)
        if ep.edizione_id == ed.id:
            return _torna_a_utenti()
        if EdizionePersona.query.filter_by(edizione_id=ed.id, persona_id=ep.persona_id, ruolo=ep.ruolo).first():
            flash(f"{u.nome_completo} ha già quel ruolo nell'edizione {ed.anno}.", "errore")
            return _torna_a_utenti()
        da = ep.edizione.anno
        ep.edizione = ed
        for m in ep.materiali:
            m.edizione_id = ed.id
        msg = f"{RUOLI_EDIZIONE[ep.ruolo]} di {u.nome_completo} spostato dal {da} al {ed.anno}."
        if any(l.zotero_key for l in ep.letture):
            msg += " Le letture già in Zotero restano nella collezione della vecchia edizione."
        flash(msg, "ok")
    else:
        ruolo = request.form.get("ruolo")
        if ruolo not in RUOLI_EDIZIONE:
            flash("Scegli il ruolo nell'edizione.", "errore")
            return _torna_a_utenti()
        # la persona dell'account, o quella con lo stesso nome già nel programma e senza account
        p = u.persona or Persona.query.filter_by(nome=u.nome, cognome=u.cognome, utente_id=None).first() \
            or Persona(nome=u.nome, cognome=u.cognome)
        p.utente_id = u.id
        db.session.add(p)
        db.session.flush()
        if EdizionePersona.query.filter_by(edizione_id=ed.id, persona_id=p.id, ruolo=ruolo).first():
            flash(f"{u.nome_completo} è già nell'edizione {ed.anno}.", "errore")
            return _torna_a_utenti()
        db.session.add(EdizionePersona(edizione=ed, persona=p, ruolo=ruolo))
        flash(f"{u.nome_completo} aggiunto all'edizione {ed.anno} ({RUOLI_EDIZIONE[ruolo]}): "
              f"titolo e dettagli nella scheda dell'edizione.", "ok")
    db.session.commit()
    return _torna_a_utenti()


@bp.post("/utenti/<int:uid>/elimina")
@admin_required
def elimina_utente(uid):
    """Per gli account di prova: via l'utente con candidature, letture e file. Chi ha valutato
    o caricato materiali resta (si disattiva), per non perdere lo storico."""
    u = db.get_or_404(Utente, uid)
    if u.id == current_user.id:
        flash("Non puoi eliminare il tuo stesso account.", "errore")
    elif Valutazione.query.filter_by(valutatore_id=u.id).first() \
            or Materiale.query.filter_by(caricato_da_id=u.id).first():
        flash(f"{u.nome_completo} ha valutazioni o materiali: disattivalo invece di eliminarlo.", "errore")
    else:
        file = [c.file_path for c in u.candidature]
        db.session.delete(u)
        db.session.commit()
        for f in file:
            elimina_upload(f)
        flash(f"Utente {u.email} eliminato.", "ok")
    return _torna_a_utenti()


# ------------------------------------------------------------------ email ai partecipanti
GRUPPI_EMAIL = {"relatori": "relatore", "docenti": "docente", "comitato": "comitato"}  # gruppo → ruolo EP


def _partecipanti(eid, gruppi, solo_attivi=True):
    """(utenti, nomi senza account) dei gruppi scelti, per un'edizione o tutte (eid 0).
    relatori/docenti/comitato: persone dell'edizione con un account; docenti anche le candidature
    ammesse; comitato anche gli amministratori; candidati: candidature inviate."""
    eps = EdizionePersona.query.filter(
        EdizionePersona.ruolo.in_([GRUPPI_EMAIL[g] for g in gruppi if g in GRUPPI_EMAIL]))
    cands = Candidatura.query.filter(Candidatura.stato != "bozza")
    if eid:
        eps, cands = eps.filter_by(edizione_id=eid), cands.filter_by(edizione_id=eid)
    eps = eps.all()
    utenti = {ep.persona.utente for ep in eps if ep.persona.utente}
    senza = sorted({ep.persona.nome_completo for ep in eps if not ep.persona.utente})
    if "docenti" in gruppi:
        utenti |= {c.utente for c in cands.filter_by(stato="ammessa")}
    if "candidati" in gruppi:
        utenti |= {c.utente for c in cands}
    if "comitato" in gruppi:
        utenti |= set(Utente.query.filter_by(admin=True))
    return sorted((u for u in utenti if u.attivo or not solo_attivi),
                  key=lambda u: (u.cognome, u.nome)), senza


def _destinatari(eid, gruppi):
    """Destinatari del modulo email: solo account attivi."""
    return _partecipanti(eid, gruppi)


@bp.route("/email", methods=["GET", "POST"])
@admin_required
def email():
    """Anteprima dei destinatari, poi invio in copia nascosta."""
    form = EmailPartecipantiForm()
    form.edizione_id.choices = [(0, "Tutte le edizioni")] + [
        (e.id, f"{e.anno} · {e.titolo}") for e in Edizione.query.order_by(Edizione.anno.desc())]
    utenti = senza = None
    if form.validate_on_submit():
        gruppi = [g for g in GRUPPI_EMAIL if form[g].data]
        if not gruppi:
            flash("Scegli almeno un gruppo di destinatari.", "errore")
        else:
            utenti, senza = _destinatari(form.edizione_id.data, gruppi)
            if request.form.get("azione") == "invia" and utenti:
                falliti = email_partecipanti([u.email for u in utenti], form.oggetto.data, form.testo.data)
                if falliti:
                    flash(f"Inviata a {len(utenti) - falliti} persone; non partita per {falliti} "
                          f"(errore SMTP, vedi il log).", "errore")
                else:
                    flash(f"Email inviata a {len(utenti)} persone.", "ok")
                return redirect(url_for("admin.email"))
    return render_template("admin/email.html", form=form, utenti=utenti, senza=senza,
                           rispondi_a=indirizzi_risposta())


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
