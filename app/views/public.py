"""Sito pubblico: home, pagina edizione, la scuola, contatti, privacy, guide."""
from flask import Blueprint, abort, current_app, redirect, render_template, send_from_directory, url_for
from flask_login import current_user

from ..guida import GUIDE, leggi

from ..extensions import db
from ..forms import DescrizioneForm, MaterialeUDForm
from ..models import Candidatura, Edizione, Intervento, PropostaLettura, ZoteroCollezione, ZoteroItem

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
    return render_template("public/edizione.html", ed=ed, letture=_letture_edizione(ed),
                           pagine=pagine_interventi(ed))


def pagine_interventi(ed):
    """Titolo → URL della pagina di lezioni e UD dell'edizione (per i link del programma)."""
    out = {iv.titolo: url_for("public.intervento", slug=ed.slug, iid=iv.id)
           for iv in ed.interventi if iv.titolo and not iv.candidatura}
    out.update({c.titolo_ud: url_for("public.unita_didattica", slug=ed.slug, cid=c.id)
                for c in ed.candidature if c.stato == "ammessa" and c.titolo_ud})
    return out


def _edizione_pubblica(slug):
    ed = Edizione.query.filter_by(slug=slug).first_or_404()
    if ed.stato == "bozza":
        abort(404)
    return ed


def _letture_consigliate(letture):
    """[(ZoteroItem, motivazione, id della proposta)] delle letture approvate già in Zotero, item vivi."""
    approvate = [p for p in letture if p.stato == "approvata" and p.zotero_key]
    items = {i.key: i for i in ZoteroItem.query.filter(
        ZoteroItem.key.in_([p.zotero_key for p in approvate]), ZoteroItem.eliminato.is_(False))}
    return [(items[p.zotero_key], p.motivazione, p.id) for p in approvate if p.zotero_key in items]


def _pagina_intervento(ed, titolo, **dati):
    voce = next((v for v in ed.programma if v.titolo == titolo), None)
    materiali = [m for m in sorted(dati.pop("materiali"), key=lambda m: (m.tipo, m.titolo))
                 if m.stato == "pubblicato" and m.visibile_a(current_user)]
    admin = current_user.is_authenticated and current_user.is_admin
    return render_template("public/intervento.html", ed=ed, titolo=titolo, voce=voce,
                           materiali=materiali, letture=_letture_consigliate(dati.pop("letture")),
                           form=MaterialeUDForm() if admin else None, **dati)


@bp.route("/edizioni/<slug>/interventi/<int:iid>")
def intervento(slug, iid):
    """Pagina di una lezione o di una UD senza candidatura (edizioni passate), con tutti gli autori."""
    ed = _edizione_pubblica(slug)
    iv = db.get_or_404(Intervento, iid)
    if iv.edizione_id != ed.id:
        abort(404)
    if iv.candidatura:  # UD di una candidatura ammessa: la pagina è quella della candidatura
        return redirect(url_for("public.unita_didattica", slug=ed.slug, cid=iv.candidatura.id))
    admin = current_user.is_authenticated and current_user.is_admin
    affiliazioni = "; ".join(a.persona.affiliazione for a in iv.autori if a.persona.affiliazione)
    return _pagina_intervento(
        ed, iv.titolo or "Senza titolo", iv=iv, ud=iv.ud,
        autore=iv.nomi_autori, affiliazione=affiliazioni,
        abstract=iv.descrizione, materiali=iv.materiali, letture=iv.letture,
        form_descrizione=DescrizioneForm(obj=iv) if admin else None, gestisce_letture=_gestisce_letture(iv))


def _gestisce_letture(iv):
    """Admin, o autore della lezione finché i contenuti dell'edizione sono aperti
    (stessa regola di ``area._mia_lezione(iid, modifica=True)``)."""
    u = current_user
    if not u.is_authenticated:
        return False
    return u.is_admin or (iv in u.lezioni() and u.puo_modificare(iv.edizione))


@bp.route("/edizioni/<slug>/unita-didattiche/<int:cid>")
def unita_didattica(slug, cid):
    """UD di un docente ammesso: solo nome, titolo, discipline e abstract, mai altri dati personali."""
    ed = _edizione_pubblica(slug)
    c = db.get_or_404(Candidatura, cid)
    if c.edizione_id != ed.id or c.stato != "ammessa" or not c.titolo_ud:
        abort(404)
    return _pagina_intervento(
        ed, c.titolo_ud, c=c, ud=True, autore=c.nomi_autori, discipline=c.discipline,
        abstract=c.abstract, materiali=c.materiali, letture=c.letture)


def _letture_edizione(ed, base_prima=False):
    """Invito alla lettura: [(titolo sezione o None, item)] dal sotto-albero della collezione
    dell'edizione. Prima i record della radice, poi una sezione per sottocollezione in ordine di
    nome ("Relatori"; nelle edizioni vecchie una per lezione), per ultima "Docenti". Un item
    compare una volta sola. In fondo i «Riferimenti di base», comuni a tutte le edizioni
    (collezione ZOTERO_COLLEZIONE_BASE), anche per le edizioni senza collezione; con
    ``base_prima`` (pagina /bibliografia) vanno in testa e tengono per sé gli item comuni."""
    radice = ed.zotero_collection_key and db.session.get(ZoteroCollezione, ed.zotero_collection_key)
    base_key = current_app.config.get("ZOTERO_COLLEZIONE_BASE")
    base = base_key and db.session.get(ZoteroCollezione, base_key)
    if not radice and not base:
        return []
    figli = {}
    for c in ZoteroCollezione.query.all():
        figli.setdefault(c.parent_key, []).append(c)

    def discendenti(c):
        out = [c]
        for f in figli.get(c.key, []):
            out += discendenti(f)
        return out

    sezioni = []
    if radice:
        sezioni.append((None, [radice]))
        for c in sorted(figli.get(radice.key, []),
                        key=lambda c: (c.key == ed.zotero_docenti_key or c.nome == "Docenti", c.nome.lower())):
            sezioni.append((c.nome, discendenti(c)))
    if base:
        sezioni.insert(0 if base_prima else len(sezioni), ("Riferimenti di base", discendenti(base)))
    visti, out = set(), []
    for titolo, cols in sezioni:
        items = sorted({i.key: i for c in cols for i in c.items
                        if not i.eliminato and i.key not in visti}.values(),
                       key=lambda i: (i.primo_autore or "", i.anno or ""))
        visti |= {i.key for i in items}
        if items and cols[0].key == ed.zotero_relatori_key:
            out += _per_lezione(ed, titolo, items)
        elif items:
            out.append((titolo, items))
    return out


def _per_lezione(ed, titolo, items):
    """«Relatori» divisa per lezione (il legame lettura↔lezione lo conosce solo il sito);
    i record messi a mano in Zotero restano sotto «Relatori»."""
    lezione_di = {p.zotero_key: p.intervento for p in PropostaLettura.query.join(Intervento)
                  .filter(Intervento.edizione_id == ed.id, PropostaLettura.zotero_key.isnot(None))}
    gruppi = {}
    for i in items:
        gruppi.setdefault(lezione_di.get(i.key), []).append(i)
    ordinate = sorted((iv for iv in gruppi if iv), key=lambda iv: iv.posizione)
    out = [(f"{titolo} · {iv.nome_lezione}", gruppi[iv]) for iv in ordinate]
    return ([(titolo, gruppi[None])] if None in gruppi else []) + out


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


@bp.route("/guida", defaults={"slug": "docenti"})
@bp.route("/guida/<slug>")
def guida(slug):
    g = GUIDE.get(slug) or abort(404)
    if g["riservata"]:
        if not current_user.is_authenticated:
            return current_app.login_manager.unauthorized()
        if not current_user.is_comitato:
            abort(403)
    html, indice = leggi(slug)
    return render_template("public/guida.html", guida=g, slug=slug, html=html, indice=indice)
