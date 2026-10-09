from app.extensions import db
from app.utils.time import now
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import Index, text

class Checklist(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    manutencao_id=db.Column(db.Integer,db.ForeignKey("manutencao.id"),unique=True,nullable=False)
    modelo_id=db.Column(db.Integer,db.ForeignKey("modelo_checklist.id"))
    tipo_nome=db.Column(db.String(80))
    criado_em=db.Column(db.DateTime,default=now,nullable=False)
    salvo_em=db.Column(db.DateTime)
    usuario_id=db.Column(db.Integer,db.ForeignKey("usuario.id"))
    manutencao=db.relationship("Manutencao",backref=db.backref("checklist",uselist=False))
class ChecklistItem(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    checklist_id=db.Column(db.Integer,db.ForeignKey("checklist.id"),nullable=False,index=True)
    componente=db.Column(db.String(180),nullable=False)
    categoria=db.Column(db.String(120))
    descricao=db.Column(db.Text)
    obrigatorio=db.Column(db.Boolean,default=False,server_default=db.false(),nullable=False)
    ordem=db.Column(db.Integer,default=0,server_default="0",nullable=False)
    ativo=db.Column(db.Boolean,default=True,server_default=db.true(),nullable=False)
    respondido=db.Column(db.Boolean,default=False,server_default=db.true(),nullable=False)
    acao=db.Column(db.String(30),default="NAO_SE_APLICA",nullable=False)
    observacao=db.Column(db.Text)
    quantidade=db.Column(db.Numeric(12,2),default=1,nullable=False)
    foto=db.Column(db.String(255))
    checklist=db.relationship("Checklist",backref=db.backref("itens",order_by="ChecklistItem.ordem, ChecklistItem.id"))
    __table_args__=(db.CheckConstraint("quantidade > 0",name="ck_checklist_quantidade"),db.CheckConstraint("acao IN ('OK','REPARAR','SUBSTITUIR','NAO_SE_APLICA')",name="ck_checklist_acao"))
