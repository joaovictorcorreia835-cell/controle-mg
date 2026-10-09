from app.extensions import db


class TipoEquipamento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(80), unique=True, nullable=False)
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    modelo_checklist = db.relationship("ModeloChecklist", back_populates="tipo", uselist=False)


class CategoriaChecklist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), unique=True, nullable=False)


class ModeloChecklist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tipo_equipamento_id = db.Column(db.Integer, db.ForeignKey("tipo_equipamento.id"), unique=True, nullable=False)
    tipo = db.relationship("TipoEquipamento", back_populates="modelo_checklist")
    itens = db.relationship("ModeloChecklistItem", back_populates="modelo", order_by="ModeloChecklistItem.ordem, ModeloChecklistItem.id")


class ModeloChecklistItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    modelo_id = db.Column(db.Integer, db.ForeignKey("modelo_checklist.id"), nullable=False, index=True)
    categoria_id = db.Column(db.Integer, db.ForeignKey("categoria_checklist.id"), nullable=False)
    componente = db.Column(db.String(180), nullable=False)
    descricao = db.Column(db.Text)
    obrigatorio = db.Column(db.Boolean, default=False, nullable=False)
    ordem = db.Column(db.Integer, default=0, nullable=False)
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    modelo = db.relationship("ModeloChecklist", back_populates="itens")
    categoria = db.relationship("CategoriaChecklist")
    __table_args__ = (db.CheckConstraint("ordem >= 0", name="ck_modelo_item_ordem"),)
