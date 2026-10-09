from app.extensions import db
from app.utils.time import now
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import Index, text

class Maquina(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    codigo_patrimonio=db.Column(db.String(60),unique=True,nullable=False,index=True)
    numero_serie=db.Column(db.String(120),unique=True,index=True)
    marca=db.Column(db.String(120),index=True)
    modelo=db.Column(db.String(120),nullable=False,index=True)
    tipo=db.Column(db.String(80))  # Texto legado preservado para o histórico.
    tipo_equipamento_id=db.Column(db.Integer,db.ForeignKey("tipo_equipamento.id"),index=True)
    tipo_equipamento=db.relationship("TipoEquipamento")
    potencia=db.Column(db.String(60))
    tensao=db.Column(db.String(60))
    capacidade=db.Column(db.String(60))
    ano=db.Column(db.Integer)
    horimetro=db.Column(db.Numeric(12,2),default=0,nullable=False)
    localizacao=db.Column(db.String(120),index=True)
    foto=db.Column(db.String(255))
    status=db.Column(db.String(30),default="DISPONIVEL",nullable=False,index=True)
    observacoes=db.Column(db.Text)
    ativo=db.Column(db.Boolean,default=True,nullable=False)
    criado_em=db.Column(db.DateTime,default=now,nullable=False)
    atualizado_em=db.Column(db.DateTime,default=now,onupdate=now,nullable=False)
    __table_args__=(db.CheckConstraint("status IN ('DISPONIVEL','EM_MANUTENCAO','AGUARDANDO_CHECKLIST','AGUARDANDO_DIAGNOSTICO','AGUARDANDO_PECA','EM_REPARO','AGUARDANDO_TESTE','INATIVA')",name="ck_maquina_status"),db.CheckConstraint("horimetro >= 0",name="ck_maquina_horimetro"))
