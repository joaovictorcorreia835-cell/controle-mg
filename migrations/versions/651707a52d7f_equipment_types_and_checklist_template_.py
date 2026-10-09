"""Equipment types and checklist template snapshots

Revision ID: 651707a52d7f
Revises: 46f053ce9f99
Create Date: 2026-10-07 14:08:55.285134

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '651707a52d7f'
down_revision = '46f053ce9f99'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('categoria_checklist',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=120), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('nome')
    )
    op.create_table('tipo_equipamento',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=80), nullable=False),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('nome')
    )
    op.create_table('modelo_checklist',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tipo_equipamento_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['tipo_equipamento_id'], ['tipo_equipamento.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tipo_equipamento_id')
    )
    op.create_table('modelo_checklist_item',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('modelo_id', sa.Integer(), nullable=False),
    sa.Column('categoria_id', sa.Integer(), nullable=False),
    sa.Column('componente', sa.String(length=180), nullable=False),
    sa.Column('descricao', sa.Text(), nullable=True),
    sa.Column('obrigatorio', sa.Boolean(), nullable=False),
    sa.Column('ordem', sa.Integer(), nullable=False),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.CheckConstraint('ordem >= 0', name='ck_modelo_item_ordem'),
    sa.ForeignKeyConstraint(['categoria_id'], ['categoria_checklist.id'], ),
    sa.ForeignKeyConstraint(['modelo_id'], ['modelo_checklist.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('modelo_checklist_item', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_modelo_checklist_item_modelo_id'), ['modelo_id'], unique=False)

    # Additive ALTERs avoid recreating parent tables referenced by historical rows.
    _add_reference("checklist", "modelo_id", "modelo_checklist", "fk_checklist_modelo")
    op.add_column("checklist", sa.Column("tipo_nome", sa.String(80), nullable=True))
    for column in (
        sa.Column("categoria", sa.String(120), nullable=True),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("obrigatorio", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("respondido", sa.Boolean(), nullable=False, server_default=sa.true()),
    ):
        op.add_column("checklist_item", column)
    _add_reference("maquina", "tipo_equipamento_id", "tipo_equipamento", "fk_maquina_tipo_equipamento")
    op.create_index("ix_maquina_tipo_equipamento_id", "maquina", ["tipo_equipamento_id"])
    _seed()


def _add_reference(table, column, target, name):
    if op.get_bind().dialect.name == "sqlite":
        op.execute(sa.text(f"ALTER TABLE {table} ADD COLUMN {column} INTEGER CONSTRAINT {name} REFERENCES {target}(id)"))
    else:
        op.add_column(table, sa.Column(column, sa.Integer(), sa.ForeignKey(target + ".id", name=name), nullable=True))


def _seed():
    # Versioned immutable seed shared with the development command; never overwrite edits.
    import json
    from pathlib import Path
    data = json.loads((Path(__file__).parents[2] / "app" / "data" / "checklist_inicial_v1.json").read_text(encoding="utf-8"))
    categories = {name: i + 1 for i, name in enumerate(data["categorias"])}
    category_table = sa.table("categoria_checklist", sa.column("id", sa.Integer()), sa.column("nome", sa.String()))
    type_table = sa.table("tipo_equipamento", sa.column("id", sa.Integer()), sa.column("nome", sa.String()), sa.column("ativo", sa.Boolean()))
    model_table = sa.table("modelo_checklist", sa.column("id", sa.Integer()), sa.column("tipo_equipamento_id", sa.Integer()))
    item_table = sa.table("modelo_checklist_item", sa.column("modelo_id", sa.Integer()), sa.column("categoria_id", sa.Integer()), sa.column("componente", sa.String()), sa.column("descricao", sa.Text()), sa.column("obrigatorio", sa.Boolean()), sa.column("ordem", sa.Integer()), sa.column("ativo", sa.Boolean()))
    op.bulk_insert(category_table, [{"id": id, "nome": name} for name, id in categories.items()])
    for id, spec in enumerate(data["tipos"], 1):
        op.bulk_insert(type_table, [{"id": id, "nome": spec["nome"], "ativo": True}])
        op.bulk_insert(model_table, [{"id": id, "tipo_equipamento_id": id}])
        op.bulk_insert(item_table, [dict(modelo_id=id, categoria_id=categories[item["categoria"]], **{k: v for k, v in item.items() if k != "categoria"}) for item in spec["itens"]])
    if op.get_bind().dialect.name == "postgresql":
        for table in ("categoria_checklist", "tipo_equipamento", "modelo_checklist"):
            op.execute(sa.text(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), (SELECT max(id) FROM {table}), true)"))
    # Existing machines/checklists/OS are intentionally left untouched.


def downgrade():
    op.drop_index("ix_maquina_tipo_equipamento_id", table_name="maquina")
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint("fk_maquina_tipo_equipamento", "maquina", type_="foreignkey")
        op.drop_constraint("fk_checklist_modelo", "checklist", type_="foreignkey")
    op.drop_column("maquina", "tipo_equipamento_id")
    for column in ("respondido", "ativo", "ordem", "obrigatorio", "descricao", "categoria"):
        op.drop_column("checklist_item", column)
    op.drop_column("checklist", "tipo_nome")
    op.drop_column("checklist", "modelo_id")
    op.drop_index("ix_modelo_checklist_item_modelo_id", table_name="modelo_checklist_item")
    op.drop_table("modelo_checklist_item")
    op.drop_table("modelo_checklist")
    op.drop_table("tipo_equipamento")
    op.drop_table("categoria_checklist")
