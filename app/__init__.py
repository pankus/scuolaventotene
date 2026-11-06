import os

from flask import Flask

from config import Config

from .extensions import csrf, db, login_manager, migrate


def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)
    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db, directory=os.path.join(os.path.dirname(app.root_path), "migrations"))
    login_manager.init_app(app)
    csrf.init_app(app)

    from . import models  # noqa: F401  (registra i modelli)
    from .views import admin, archivio, area, auth, bibliografia, public

    app.register_blueprint(public.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(area.bp, url_prefix="/area")
    app.register_blueprint(archivio.bp)
    app.register_blueprint(bibliografia.bp)
    app.register_blueprint(admin.bp, url_prefix="/admin")

    from .cli import register_cli
    from .utils import register_template_utils

    register_cli(app)
    register_template_utils(app)

    from flask import render_template

    @app.errorhandler(403)
    def _403(_e):
        return render_template("errore.html", codice=403, messaggio="Accesso non consentito."), 403

    @app.errorhandler(404)
    def _404(_e):
        return render_template("errore.html", codice=404, messaggio="Pagina non trovata."), 404

    @app.errorhandler(413)
    def _413(_e):
        return render_template("errore.html", codice=413, messaggio="File troppo grande."), 413

    return app
