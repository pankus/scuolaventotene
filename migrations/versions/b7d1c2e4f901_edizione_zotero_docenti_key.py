"""edizione: zotero_proposte_key -> zotero_docenti_key

Struttura Zotero semplificata: Edizione -> "Relatori" e "Docenti". Rinomino scritto a mano:
l'autogenerate farebbe drop + add, perdendo i valori. RENAME COLUMN nativo di SQLite (>= 3.25)
invece del batch: il batch ricopierebbe `edizioni`, che è referenziata da altre tabelle, e con
le foreign key attive il DROP della vecchia tabella fallisce.

Revision ID: b7d1c2e4f901
Revises: e0930a0b84a5
Create Date: 2026-11-06 15:00:00

"""
from alembic import op


revision = 'b7d1c2e4f901'
down_revision = 'e0930a0b84a5'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE edizioni RENAME COLUMN zotero_proposte_key TO zotero_docenti_key")


def downgrade():
    op.execute("ALTER TABLE edizioni RENAME COLUMN zotero_docenti_key TO zotero_proposte_key")
