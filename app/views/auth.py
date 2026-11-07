"""Registrazione, accesso, verifica dell'email e reset della password."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db
from ..forms import LoginForm, PasswordDimenticataForm, RegistrazioneForm, ReimpostaPasswordForm
from ..models import Utente, adesso
from ..posta import email_reset, email_verifica, leggi_token

bp = Blueprint("auth", __name__)


def _next_sicuro(default):
    nxt = request.args.get("next", "")
    # "//host" e "/\\host" i browser li aprono come indirizzo esterno
    return nxt if nxt.startswith("/") and not nxt.startswith(("//", "/\\")) else default


@bp.route("/registrati", methods=["GET", "POST"])
def registrati():
    if current_user.is_authenticated:
        return redirect(url_for("area.dashboard"))
    form = RegistrazioneForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        if Utente.query.filter_by(email=email).first():
            flash("Esiste già un account con questa email.", "errore")
        else:
            u = Utente(email=email, nome=form.nome.data.strip(), cognome=form.cognome.data.strip(),
                       consenso_privacy_il=adesso())
            u.set_password(form.password.data)
            db.session.add(u)
            db.session.commit()
            login_user(u)
            email_verifica(u)
            flash("Registrazione completata. Ti abbiamo scritto per confermare l'indirizzo email; "
                  "intanto completa il tuo profilo.", "ok")
            return redirect(url_for("area.profilo"))
    return render_template("auth/registrati.html", form=form)


@bp.route("/accedi", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("area.dashboard"))
    form = LoginForm()
    if form.validate_on_submit():
        u = Utente.query.filter_by(email=form.email.data.strip().lower()).first()
        if u and u.attivo and u.check_password(form.password.data):
            login_user(u, remember=form.ricordami.data)
            return redirect(_next_sicuro(url_for("admin.dashboard") if u.is_comitato
                                         else url_for("area.dashboard")))
        flash("Credenziali non valide.", "errore")
    return render_template("auth/login.html", form=form)


@bp.post("/esci")  # POST con CSRF: un link o un'immagine altrui non può far uscire
@login_required
def logout():
    logout_user()
    flash("Sei uscito.", "info")
    return redirect(url_for("public.index"))


# ------------------------------------------------------------------ verifica email
@bp.route("/verifica/<token>")
def verifica(token):
    u = leggi_token(token, "verifica")
    if not u:
        flash("Link di conferma non valido o scaduto. Accedi e chiedine uno nuovo.", "errore")
        return redirect(url_for("auth.login"))
    u.email_verificata = True
    db.session.commit()
    flash("Indirizzo email confermato.", "ok")
    return redirect(url_for("area.dashboard"))


@bp.post("/verifica/reinvia")
@login_required
def reinvia_verifica():
    if not current_user.email_verificata:
        email_verifica(current_user)
        flash(f"Ti abbiamo inviato un nuovo link a {current_user.email}.", "info")
    return redirect(url_for("area.dashboard"))


# ------------------------------------------------------------------ password
@bp.route("/password-dimenticata", methods=["GET", "POST"])
def password_dimenticata():
    form = PasswordDimenticataForm()
    if form.validate_on_submit():
        u = Utente.query.filter_by(email=form.email.data.strip().lower()).first()
        if u and u.attivo:
            email_reset(u)
        # stesso messaggio in ogni caso: non riveliamo quali email sono registrate
        flash("Se l'indirizzo è registrato, riceverai un'email con il link per la nuova password.", "info")
        return redirect(url_for("auth.login"))
    return render_template("auth/password_dimenticata.html", form=form)


@bp.route("/reimposta-password/<token>", methods=["GET", "POST"])
def reimposta_password(token):
    u = leggi_token(token, "reset")
    if not u:
        flash("Link non valido o scaduto. Richiedine uno nuovo.", "errore")
        return redirect(url_for("auth.password_dimenticata"))
    form = ReimpostaPasswordForm()
    if form.validate_on_submit():
        u.set_password(form.password.data)
        u.email_verificata = True  # ha appena dimostrato di leggere quella casella
        db.session.commit()
        flash("Password aggiornata. Ora puoi accedere.", "ok")
        return redirect(url_for("auth.login"))
    return render_template("auth/reimposta_password.html", form=form)
