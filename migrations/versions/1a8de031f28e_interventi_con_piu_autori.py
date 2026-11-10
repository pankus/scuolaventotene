"""interventi con più autori

Lezioni e UD diventano `interventi` (edizione, tipo relazione|ud, titolo, abstract, ordine) con
gli autori in `intervento_autori` (righe di edizioni_persone). Ogni EP relatore/docente diventa
un intervento con lo **stesso id** (gli URL /edizioni/<slug>/interventi/<id> non cambiano); poi
gli interventi della stessa edizione, dello stesso tipo e con lo stesso titolo si uniscono in uno
con più autori (lezioni a due voci). Materiali e letture passano da lezione_id a intervento_id.

Revision ID: 1a8de031f28e
Revises: d3c7d257acc6
Create Date: 2026-11-10 12:18:44.106648

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1a8de031f28e'
down_revision = 'd3c7d257acc6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('interventi',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('edizione_id', sa.Integer(), nullable=False),
    sa.Column('tipo', sa.String(length=20), nullable=False),
    sa.Column('titolo', sa.String(length=255), nullable=True),
    sa.Column('descrizione', sa.Text(), nullable=True),
    sa.Column('ordine', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['edizione_id'], ['edizioni.id'], name=op.f('fk_interventi_edizione_id_edizioni'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_interventi'))
    )
    op.create_table('intervento_autori',
    sa.Column('intervento_id', sa.Integer(), nullable=False),
    sa.Column('ep_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['ep_id'], ['edizioni_persone.id'], name=op.f('fk_intervento_autori_ep_id_edizioni_persone'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['intervento_id'], ['interventi.id'], name=op.f('fk_intervento_autori_intervento_id_interventi'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('intervento_id', 'ep_id', name=op.f('pk_intervento_autori'))
    )

    # dati: un intervento per lezione/UD, stesso id dell'EP, la persona come autore
    conn = op.get_bind()
    conn.execute(sa.text(
        "INSERT INTO interventi (id, edizione_id, tipo, titolo, descrizione, ordine) "
        "SELECT id, edizione_id, CASE ruolo WHEN 'relatore' THEN 'relazione' ELSE 'ud' END, "
        "titolo_lezione, descrizione, ordine FROM edizioni_persone WHERE ruolo IN ('relatore', 'docente')"))
    conn.execute(sa.text("INSERT INTO intervento_autori (intervento_id, ep_id) SELECT id, id FROM interventi"))

    with op.batch_alter_table('materiali', schema=None) as batch_op:
        batch_op.add_column(sa.Column('intervento_id', sa.Integer(), nullable=True))
    with op.batch_alter_table('proposte_lettura', schema=None) as batch_op:
        batch_op.add_column(sa.Column('intervento_id', sa.Integer(), nullable=True))
    conn.execute(sa.text("UPDATE materiali SET intervento_id = lezione_id"))
    conn.execute(sa.text("UPDATE proposte_lettura SET intervento_id = lezione_id"))

    # lezioni a due voci: stessa edizione, tipo e titolo → un intervento, il primo
    gruppi = conn.execute(sa.text(
        "SELECT edizione_id, tipo, titolo, MIN(id) FROM interventi WHERE titolo IS NOT NULL "
        "GROUP BY edizione_id, tipo, titolo HAVING COUNT(*) > 1")).all()
    for ed_id, tipo, titolo, tieni in gruppi:
        altri = conn.execute(sa.text(
            "SELECT id FROM interventi WHERE edizione_id = :e AND tipo = :t AND titolo = :ti AND id <> :k"),
            {"e": ed_id, "t": tipo, "ti": titolo, "k": tieni}).scalars().all()
        for a in altri:
            par = {"a": a, "k": tieni}
            conn.execute(sa.text("UPDATE intervento_autori SET intervento_id = :k WHERE intervento_id = :a"), par)
            conn.execute(sa.text("UPDATE materiali SET intervento_id = :k WHERE intervento_id = :a"), par)
            conn.execute(sa.text("UPDATE proposte_lettura SET intervento_id = :k WHERE intervento_id = :a"), par)
            conn.execute(sa.text(
                "UPDATE interventi SET descrizione = (SELECT descrizione FROM interventi WHERE id = :a) "
                "WHERE id = :k AND descrizione IS NULL"), par)
            conn.execute(sa.text("DELETE FROM interventi WHERE id = :a"), par)
        print(f"Unite in un intervento ({tieni}) le lezioni {altri} «{titolo}»")

    with op.batch_alter_table('edizioni_persone', schema=None) as batch_op:
        batch_op.drop_column('descrizione')
        batch_op.drop_column('titolo_lezione')
        batch_op.drop_column('ordine')

    with op.batch_alter_table('materiali', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('fk_materiali_lezione_id_edizioni_persone'), type_='foreignkey')
        batch_op.create_foreign_key(batch_op.f('fk_materiali_intervento_id_interventi'), 'interventi', ['intervento_id'], ['id'], ondelete='SET NULL')
        batch_op.drop_column('lezione_id')

    with op.batch_alter_table('proposte_lettura', schema=None) as batch_op:
        batch_op.drop_constraint('una_origine', type_='check')
        batch_op.drop_index(batch_op.f('ix_proposte_lettura_lezione_id'))
        batch_op.create_index(batch_op.f('ix_proposte_lettura_intervento_id'), ['intervento_id'], unique=False)
        batch_op.drop_constraint(batch_op.f('fk_proposte_lettura_lezione_id_edizioni_persone'), type_='foreignkey')
        batch_op.create_foreign_key(batch_op.f('fk_proposte_lettura_intervento_id_interventi'), 'interventi', ['intervento_id'], ['id'], ondelete='CASCADE')
        batch_op.drop_column('lezione_id')
        # a mano (l'autogenerate non vede i CHECK)
        batch_op.create_check_constraint('una_origine', '(candidatura_id IS NULL) <> (intervento_id IS NULL)')


def downgrade():
    """Ritorno allo schema con la lezione nell'EP: ogni intervento torna sul primo autore; gli
    altri autori di un intervento condiviso restano senza titolo (perdita accettata)."""
    with op.batch_alter_table('edizioni_persone', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ordine', sa.INTEGER(), nullable=True))
        batch_op.add_column(sa.Column('titolo_lezione', sa.VARCHAR(length=255), nullable=True))
        batch_op.add_column(sa.Column('descrizione', sa.TEXT(), nullable=True))
    with op.batch_alter_table('materiali', schema=None) as batch_op:
        batch_op.add_column(sa.Column('lezione_id', sa.INTEGER(), nullable=True))
    with op.batch_alter_table('proposte_lettura', schema=None) as batch_op:
        batch_op.add_column(sa.Column('lezione_id', sa.INTEGER(), nullable=True))

    primo = "(SELECT MIN(ep_id) FROM intervento_autori a WHERE a.intervento_id = {})"
    op.execute(
        "UPDATE edizioni_persone SET titolo_lezione = i.titolo, descrizione = i.descrizione, ordine = i.ordine "
        "FROM interventi i WHERE edizioni_persone.id = " + primo.format("i.id"))
    op.execute("UPDATE materiali SET lezione_id = " + primo.format("materiali.intervento_id"))
    op.execute("UPDATE proposte_lettura SET lezione_id = " + primo.format("proposte_lettura.intervento_id"))

    with op.batch_alter_table('proposte_lettura', schema=None) as batch_op:
        batch_op.drop_constraint('una_origine', type_='check')
        batch_op.drop_constraint(batch_op.f('fk_proposte_lettura_intervento_id_interventi'), type_='foreignkey')
        batch_op.create_foreign_key(batch_op.f('fk_proposte_lettura_lezione_id_edizioni_persone'), 'edizioni_persone', ['lezione_id'], ['id'], ondelete='CASCADE')
        batch_op.drop_index(batch_op.f('ix_proposte_lettura_intervento_id'))
        batch_op.create_index(batch_op.f('ix_proposte_lettura_lezione_id'), ['lezione_id'], unique=False)
        batch_op.drop_column('intervento_id')
        batch_op.create_check_constraint('una_origine', '(candidatura_id IS NULL) <> (lezione_id IS NULL)')

    with op.batch_alter_table('materiali', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('fk_materiali_intervento_id_interventi'), type_='foreignkey')
        batch_op.create_foreign_key(batch_op.f('fk_materiali_lezione_id_edizioni_persone'), 'edizioni_persone', ['lezione_id'], ['id'], ondelete='SET NULL')
        batch_op.drop_column('intervento_id')

    op.drop_table('intervento_autori')
    op.drop_table('interventi')
