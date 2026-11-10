"""ruoli per edizione: Utente.admin al posto di ruolo

L'unico ruolo globale resta amministratore; comitato, relatore e docente valgono per edizione
(EdizionePersona). Gli account con ruolo «comitato» senza una riga di comitato in un'edizione
perdono il back-office: la migrazione li elenca, l'admin li aggiunge da /admin/utenti.

Revision ID: 96a97a8d076f
Revises: e7319d5018d9
Create Date: 2026-11-10 12:07:24.477588

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '96a97a8d076f'
down_revision = 'e7319d5018d9'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    senza_ep = conn.execute(sa.text(
        "SELECT email FROM utenti u WHERE ruolo = 'comitato' AND NOT EXISTS ("
        " SELECT 1 FROM persone p JOIN edizioni_persone ep ON ep.persona_id = p.id"
        " WHERE p.utente_id = u.id AND ep.ruolo = 'comitato')")).scalars().all()
    for email in senza_ep:
        print(f"ATTENZIONE: {email} era «comitato» ma non è nel comitato di nessuna edizione: "
              "aggiungilo da /admin/utenti.")

    with op.batch_alter_table('utenti', schema=None) as batch_op:
        batch_op.add_column(sa.Column('admin', sa.Boolean(), nullable=False, server_default=sa.false()))
    conn.execute(sa.text("UPDATE utenti SET admin = (ruolo = 'admin')"))
    with op.batch_alter_table('utenti', schema=None) as batch_op:
        batch_op.drop_column('ruolo')


def downgrade():
    with op.batch_alter_table('utenti', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ruolo', sa.VARCHAR(length=20), nullable=False,
                                      server_default='docente'))
    op.execute("UPDATE utenti SET ruolo = 'admin' WHERE admin")
    op.execute("UPDATE utenti SET ruolo = 'relatore' WHERE ruolo = 'docente' AND id IN ("
               " SELECT p.utente_id FROM persone p JOIN edizioni_persone ep ON ep.persona_id = p.id"
               " WHERE ep.ruolo = 'relatore')")
    with op.batch_alter_table('utenti', schema=None) as batch_op:
        batch_op.drop_column('admin')
