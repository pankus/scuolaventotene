"""Le migrazioni devono produrre lo stesso schema dei modelli.

Se fallisce: è cambiato un modello senza migrazione. Lanciare
`uv run flask db migrate -m "descrizione"`, rileggere il file generato e committarlo.
"""
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from flask_migrate import upgrade

from app import create_app
from app.extensions import db
from config import TestConfig


def test_migrazioni_allineate_ai_modelli(tmp_path):
    class Cfg(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'migrato.db'}"

    app = create_app(Cfg)
    with app.app_context():
        upgrade()
        with db.engine.connect() as conn:
            differenze = compare_metadata(MigrationContext.configure(conn), db.metadata)
        db.engine.dispose()
    assert differenze == []
