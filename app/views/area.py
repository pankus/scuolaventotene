"""Area riservata. Docente: profilo, candidatura a passi (profilo, UD, invito alla lettura,
riepilogo e invio), invio materiali. Relatore: materiali e bibliografia della propria lezione,
UD dei docenti ammessi. Per tutti: ricerca dei libri."""
import time
from collections import defaultdict, deque

from flask import (Blueprint, abort, current_app, flash, jsonify, redirect, render_template,
                   request, send_from_directory, url_for)
from flask_login import current_user, login_required

from .. import zotero_sync as modulo_sync
from ..extensions import db
from ..forms import CandidaturaForm, CoautoreForm, LetturaDocenteForm, MaterialeForm, ProfiloForm
from ..models import (TIPI_LETTURA, Candidatura, Edizione, Intervento, Materiale, PropostaLettura, Utente,
                      ZoteroItem, adesso)
from ..posta import email_conferma_invio, email_invito_coautore
from ..ricerca_libri import cerca
from ..utils import copertina_ammessa, conta_caratteri, elimina_upload, salva_upload
from ..zotero_scrittura import CAMPI_MODULO, ErroreScrittura, salva_lettura, scelte_duplicati

bp = Blueprint("area", __name__)


@bp.before_request
@login_required
def _protezione():
    pass


def _mia_candidatura(cid, titolare=False):
    """Candidatura di cui l'account è autore (titolare o co-autore che ha accettato); con
    `titolare` solo il titolare (ritiro, invito del co-autore)."""
    c = db.get_or_404(Candidatura, cid)
    if not (c.utente_id == current_user.id if titolare else c.di(current_user)):
        abort(404)
    return c


@bp.route("/")
def dashboard():
    aperte = [e for e in Edizione.query.filter_by(stato="aperta").all() if e.candidature_aperte]
    candidature = current_user.mie_candidature()
    gia = {c.edizione_id for c in candidature}
    materiali = Materiale.query.filter_by(caricato_da_id=current_user.id).order_by(
        Materiale.creato_il.desc()).all()
    return render_template("area/dashboard.html", aperte=[e for e in aperte if e.id not in gia],
                           candidature=candidature, inviti=current_user.inviti(), materiali=materiali,
                           lezioni=current_user.lezioni())


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
    # la propria, o quella di cui si è co-autore: una candidatura per docente per edizione
    cand = next((c for c in current_user.mie_candidature() if c.edizione_id == ed.id), None)
    if cand and not cand.modificabile:
        if cand.stato == "bozza":
            flash("Le candidature per questa edizione non sono aperte.", "errore")
        return redirect(url_for("area.dettaglio", cid=cand.id))
    if not ed.candidature_aperte:
        flash("Le candidature per questa edizione non sono aperte.", "errore")
        return redirect(url_for("area.dashboard"))

    form = CandidaturaForm(obj=cand)
    if form.validate_on_submit():
        inviata = cand is not None and cand.stato != "bozza"
        if cand is None:
            cand = Candidatura(utente=current_user, edizione=ed)
            db.session.add(cand)
        cand.tipo = form.tipo.data
        cand.titolo_ud = form.titolo_ud.data
        cand.discipline = form.discipline.data
        cand.abstract = form.abstract.data
        vecchio = nuovo = None
        if form.file.data:
            info = salva_upload(form.file.data, f"candidature/{ed.slug}",
                                current_app.config["ESTENSIONI_PROPOSTE"])
            vecchio, nuovo = cand.file_path, info["file_path"]
            cand.file_path, cand.file_nome = info["file_path"], info["file_nome"]
            cand.n_caratteri = conta_caratteri(cand.file_path)
        problemi = cand.problemi_invio() if inviata else []
        if problemi:
            # già inviata: le modifiche devono rispettare il bando, se no resta la versione inviata
            db.session.rollback()
            elimina_upload(nuovo)
            for p in problemi:
                flash(p, "errore")
            flash("Modifiche non salvate: la candidatura inviata resta com'era.", "errore")
            return render_template("area/candidatura_form.html", form=form, ed=ed, cand=cand)
        db.session.commit()
        elimina_upload(vecchio)
        if inviata:
            flash("Modifiche salvate: la candidatura resta inviata, non serve inviarla di nuovo.", "ok")
            return redirect(url_for("area.dettaglio", cid=cand.id))
        flash("Bozza salvata. Ora puoi consigliare libri e siti (facoltativo).", "ok")
        return redirect(url_for("area.letture", cid=cand.id))
    return render_template("area/candidatura_form.html", form=form, ed=ed, cand=cand)


@bp.route("/candidatura/<int:cid>")
def dettaglio(cid):
    c = _mia_candidatura(cid)
    return render_template("area/candidatura.html", c=c, problemi=c.problemi_invio(),
                           form_coautore=CoautoreForm() if c.utente_id == current_user.id else None)


def _gia_impegnato(u, ed, tranne=None):
    """Il bando vuole una candidatura per docente per edizione: vale anche per il co-autore."""
    return any(c.edizione_id == ed.id and c is not tranne for c in u.mie_candidature())


@bp.post("/candidatura/<int:cid>/coautore")
def coautore(cid):
    """Il titolare invita un collega registrato come co-autore (o lo toglie, `togli`), finché la
    candidatura è modificabile. Il collega riceve un'email e accetta dalla sua area."""
    c = _mia_candidatura(cid, titolare=True)
    if not c.modificabile:
        abort(400)
    if request.form.get("togli"):
        c.coautore_id, c.coautore_confermato = None, False
        db.session.commit()
        flash("Co-autore tolto.", "info")
        return redirect(url_for("area.dettaglio", cid=c.id))
    form = CoautoreForm()
    if form.validate_on_submit():
        u = Utente.query.filter_by(email=form.email.data.strip().lower()).first()
        if not u or not u.attivo:
            flash("Nessun account con questa email: il collega deve prima registrarsi sul sito.", "errore")
        elif u.id == current_user.id:
            flash("Indica l'email di un collega, non la tua.", "errore")
        elif _gia_impegnato(u, c.edizione):
            flash(f"{u.nome_completo} ha già una candidatura per questa edizione.", "errore")
        else:
            c.coautore_id, c.coautore_confermato = u.id, False
            db.session.commit()
            email_invito_coautore(c)
            flash(f"Invito inviato a {u.nome_completo}: la candidatura si potrà inviare dopo la sua accettazione.", "ok")
    else:
        for errori in form.errors.values():
            flash(" ".join(errori), "errore")
    return redirect(url_for("area.dettaglio", cid=c.id))


@bp.post("/candidatura/<int:cid>/invito")
def invito(cid):
    """Il collega invitato accetta o rifiuta di essere co-autore."""
    c = db.get_or_404(Candidatura, cid)
    if c.coautore_id != current_user.id or c.coautore_confermato:
        abort(404)
    if request.form.get("azione") == "accetta":
        if _gia_impegnato(current_user, c.edizione, tranne=c):
            flash("Hai già una candidatura per questa edizione: non puoi essere anche co-autore.", "errore")
            return redirect(url_for("area.dashboard"))
        c.coautore_confermato = True
        db.session.commit()
        flash(f"Ora sei co-autore della UD di {c.utente.nome_completo}.", "ok")
        return redirect(url_for("area.dettaglio", cid=c.id))
    c.coautore_id = None
    db.session.commit()
    flash("Invito rifiutato.", "info")
    return redirect(url_for("area.dashboard"))


MAX_LETTURE = 10  # per candidatura o per lezione


def _compila(p, form):
    """Campi della lettura dal form; dalla ricerca si tengono solo valori verificabili."""
    p.campi = {k: (form[k].data or "").strip() for k in CAMPI_MODULO[p.tipo]}
    p.motivazione = form.motivazione.data
    key = form.zotero_key.data or None
    p.zotero_key = key if key and ZoteroItem.query.filter_by(key=key, eliminato=False).first() else None
    p.copertina_url = form.copertina_url.data if copertina_ammessa(form.copertina_url.data) else None


def _tipo_lettura():
    """Tipo della lettura da aggiungere (?tipo=), libro se manca o non previsto."""
    t = request.args.get("tipo")
    return t if t in TIPI_LETTURA else "book"


@bp.route("/candidatura/<int:cid>/letture", methods=["GET", "POST"])
def letture(cid):
    """Passo 3: invito alla lettura (facoltativo). Il docente aggiunge letture in qualsiasi
    momento, fino a MAX_LETTURE in tutto (``Candidatura.letture_aperte``); quelle aggiunte quando
    la candidatura non è più modificabile hanno momento post_scuola. Stessa revisione."""
    c = _mia_candidatura(cid)
    aperte = c.letture_aperte
    momento = "iscrizione" if c.modificabile else "post_scuola"
    p = None
    if request.values.get("p"):
        p = next((x for x in c.letture if x.id == request.values.get("p", type=int)
                  and x.modificabile), None) or abort(404)
    tipo = p.tipo if p else _tipo_lettura()
    form = LetturaDocenteForm(data={**p.campi, "motivazione": p.motivazione, "zotero_key": p.zotero_key,
                                    "copertina_url": p.copertina_url} if p else None)
    n_letture = len(c.letture)  # il limite vale per la candidatura, in tutto
    if aperte and form.validate_on_submit():
        if p is None and n_letture >= MAX_LETTURE:
            flash(f"Puoi consigliare al massimo {MAX_LETTURE} letture.", "errore")
            return redirect(url_for("area.letture", cid=c.id))
        p = p or PropostaLettura(candidatura=c, tipo=tipo, momento=momento)
        db.session.add(p)
        _compila(p, form)
        db.session.commit()
        flash("Lettura salvata.", "ok")
        return redirect(url_for("area.letture", cid=c.id))
    return render_template("area/letture.html", c=c, ed=c.edizione, form=form, tipo=tipo, p=p,
                           campi=CAMPI_MODULO[tipo], max_letture=MAX_LETTURE, aperte=aperte,
                           n_letture=n_letture)


@bp.post("/candidatura/<int:cid>/letture/<int:pid>/elimina")
def elimina_lettura(cid, pid):
    c = _mia_candidatura(cid)
    p = next((x for x in c.letture if x.id == pid), None) or abort(404)
    if not p.modificabile:
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
    c = _mia_candidatura(cid, titolare=True)
    if c.stato in ("bozza", "inviata", "in_valutazione", "ammessa", "riserva"):
        c.stato = "ritirata"
        db.session.commit()
        flash("Candidatura ritirata.", "info")
    return redirect(url_for("area.dashboard"))


@bp.route("/candidatura/<int:cid>/file")
def file_candidatura(cid):
    c = db.get_or_404(Candidatura, cid)
    if not c.di(current_user) and not current_user.comitato_di(c.edizione_id) and not _relatore_di(c):
        abort(404)
    if not c.file_path:
        abort(404)
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], c.file_path,
                               as_attachment=True, download_name=c.file_nome)


@bp.route("/materiali/nuovo", methods=["GET", "POST"])
def nuovo_materiale():
    """Materiale di una lezione (?lezione=, il relatore) o di una candidatura ammessa dopo la
    scuola (?candidatura=, il docente). Quelli dello staff si caricano da /admin/materiali."""
    lezione = cand = None
    if request.args.get("lezione"):
        lezione = _mia_lezione(request.args.get("lezione", type=int), modifica=True)
        ed = lezione.edizione
    elif request.args.get("candidatura"):
        cand = _mia_candidatura(request.args.get("candidatura", type=int))
        if not cand.dopo_la_scuola:
            abort(404)
        ed = cand.edizione
    else:
        abort(404)
    form = MaterialeForm(tipo="unita_didattica" if cand else "slide")
    form.edizione_id.choices = [(ed.id, f"{ed.anno} – {ed.titolo}")]
    if form.validate_on_submit():
        if not form.file.data and not form.url.data:
            flash("Carica un file oppure indica un link.", "errore")
        else:
            m = Materiale(edizione_id=ed.id, titolo=form.titolo.data,
                          autori=form.autori.data or current_user.nome_completo,
                          tipo=form.tipo.data, descrizione=form.descrizione.data,
                          url=form.url.data or None, caricato_da_id=current_user.id,
                          intervento=lezione, candidatura=cand, stato="in_revisione",
                          visibilita="pubblico")
            if form.file.data:
                info = salva_upload(form.file.data, "materiali",
                                    current_app.config["ESTENSIONI_MATERIALI"])
                for k, v in info.items():
                    setattr(m, k, v)
            db.session.add(m)
            db.session.commit()
            flash("Materiale inviato: sarà pubblicato dopo la revisione.", "ok")
            return redirect(url_for("area.dettaglio", cid=cand.id) if cand else url_for("area.dashboard"))
    return render_template("area/materiale_form.html", form=form, lezione=lezione, cand=cand)


# ------------------------------------------------------------------ relatore: la propria lezione
def _mia_lezione(iid, modifica=False):
    """La lezione di cui l'account è autore; l'admin apre qualunque lezione o UD senza
    candidatura (per completare le edizioni passate). Con `modifica`, 403 dopo la chiusura dei
    contenuti."""
    if current_user.is_admin:
        return db.get_or_404(Intervento, iid)
    iv = next((iv for iv in current_user.lezioni() if iv.id == iid), None) or abort(404)
    if modifica and not current_user.puo_modificare(iv.edizione):
        abort(403)
    return iv


def _relatore_di(c):
    """Il relatore vede le UD dei docenti ammessi nelle edizioni in cui tiene una lezione."""
    return (c.stato == "ammessa"
            and any(iv.edizione_id == c.edizione_id for iv in current_user.lezioni()))


@bp.route("/lezioni/<int:iid>/letture", methods=["GET", "POST"])
def letture_lezione(iid):
    """Bibliografia della lezione: ogni lettura entra subito in Zotero, in «Relatori».
    Dopo la chiusura dei contenuti si consulta soltanto."""
    iv = _mia_lezione(iid, modifica=request.method == "POST")
    tipo = _tipo_lettura()
    form = LetturaDocenteForm()
    scelte = []
    if form.validate_on_submit():
        if len(iv.letture) >= MAX_LETTURE:
            flash(f"Puoi indicare al massimo {MAX_LETTURE} letture per lezione.", "errore")
            return redirect(url_for("area.letture_lezione", iid=iv.id))
        p = PropostaLettura(intervento_id=iv.id, tipo=tipo)  # in sessione solo se si salva
        _compila(p, form)
        scelta = p.zotero_key or request.form.get("scelta", "")
        try:
            zot = modulo_sync.client()
            if not scelta:
                # si controlla a ogni invio: se c'è un doppione che la pagina non mostrava
                # (anche comparso dopo, per esempio da un altro relatore) si chiede di scegliere
                trovate, avviso = scelte_duplicati(zot, tipo, p.campi)
                if avviso:
                    flash(avviso, "errore")
                visti = set(request.form.get("visti", "").split(","))
                if any(k not in visti for k, _ in trovate):
                    scelte = trovate
            if not scelte:
                quale = "docenti" if iv.ud else "relatori"
                avviso = salva_lettura(zot, p, iv.edizione, quale, scelta, tag_proposte=False)
                p.stato, p.deciso_il, p.deciso_da_id = "approvata", adesso(), current_user.id
                db.session.add(p)
                db.session.commit()
                if avviso:
                    flash(avviso, "errore")
                flash("Lettura salvata nella bibliografia della lezione.", "ok")
                return redirect(url_for("area.letture_lezione", iid=iv.id))
            # altrimenti: possibili doppioni, si ripropone il modulo con la scelta del record
        except (ErroreScrittura, RuntimeError) as e:
            db.session.rollback()
            flash(str(e), "errore")
        except Exception as e:  # noqa: BLE001  (rete, permessi)
            db.session.rollback()
            flash(f"Scrittura in Zotero non riuscita: {e}", "errore")
    return render_template("area/letture_lezione.html", iv=iv, form=form, tipo=tipo, scelte=scelte,
                           aperta=current_user.puo_modificare(iv.edizione),
                           campi=CAMPI_MODULO[tipo], max_letture=MAX_LETTURE)


@bp.post("/lezioni/<int:iid>/letture/<int:pid>/elimina")
def elimina_lettura_lezione(iid, pid):
    """Toglie la lettura dal sito; il record resta in Zotero (fonte di verità)."""
    iv = _mia_lezione(iid, modifica=True)
    p = next((x for x in iv.letture if x.id == pid), None) or abort(404)
    db.session.delete(p)
    db.session.commit()
    flash("Lettura tolta dalla lezione. Il record resta in Zotero: se va eliminato, fallo lì.", "info")
    return redirect(url_for("area.letture_lezione", iid=iv.id))


@bp.route("/lezioni/<int:iid>/unita-didattiche")
def ud_lezione(iid):
    """UD dei docenti ammessi nell'edizione della lezione: niente dati personali oltre al nome."""
    iv = _mia_lezione(iid)
    ammesse = (Candidatura.query.filter_by(edizione_id=iv.edizione_id, stato="ammessa")
               .order_by(Candidatura.titolo_ud).all())
    return render_template("area/ud_lezione.html", iv=iv, candidature=ammesse)


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
    tipo = request.args.get("tipo") if request.args.get("tipo") in TIPI_LETTURA else "book"
    online = request.args.get("online") == "1" and tipo == "book"
    if online and _troppe_ricerche(current_user.id):  # il limite protegge le fonti esterne
        return jsonify(errore="Troppe ricerche online: riprova tra un minuto."), 429
    return jsonify(cerca(q[:200], request.args.get("isbn"), online=online, tipo=tipo))
