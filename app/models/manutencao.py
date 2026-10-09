from app.extensions import db
from app.utils.time import now
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import Index, text

class Manutencao(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    numero_manutencao=db.Column(db.String(40),unique=True,nullable=False,index=True)
    maquina_id=db.Column(db.Integer,db.ForeignKey("maquina.id"),nullable=False,index=True)
    data_entrada=db.Column(db.DateTime,default=now,nullable=False,index=True)
    data_saida=db.Column(db.DateTime)
    horimetro_entrada=db.Column(db.Numeric(12,2),nullable=False)
    horimetro_final=db.Column(db.Numeric(12,2))
    defeito_relatado=db.Column(db.Text,nullable=False)
    condicao_visual=db.Column(db.Text)
    responsavel_id=db.Column(db.Integer,db.ForeignKey("usuario.id"),nullable=False)
    observacoes=db.Column(db.Text)
    status=db.Column(db.String(30),default="AGUARDANDO_CHECKLIST",nullable=False,index=True)
    atualizado_em=db.Column(db.DateTime,default=now,onupdate=now,nullable=False)
    maquina=db.relationship("Maquina",backref="manutencoes")
    responsavel=db.relationship("Usuario")
    __table_args__=(Index("uq_manutencao_ativa_maquina","maquina_id",unique=True,sqlite_where=text("status NOT IN ('FINALIZADA','CANCELADA')"),postgresql_where=text("status NOT IN ('FINALIZADA','CANCELADA')")),db.CheckConstraint("horimetro_entrada >= 0",name="ck_manutencao_horimetro"))
    @property
    def dias_parada(self): return max(0,((self.data_saida or now())-self.data_entrada).days)

class FotoManutencao(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    manutencao_id=db.Column(db.Integer,db.ForeignKey("manutencao.id"),nullable=False,index=True)
    etapa=db.Column(db.String(30),nullable=False)
    categoria=db.Column(db.String(60))
    caminho=db.Column(db.String(255),nullable=False)
    legenda=db.Column(db.String(180))
    usuario_id=db.Column(db.Integer,db.ForeignKey("usuario.id"),nullable=False)
    criado_em=db.Column(db.DateTime,default=now,nullable=False)
    manutencao=db.relationship("Manutencao",backref="fotos")

class EventoStatus(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    manutencao_id=db.Column(db.Integer,db.ForeignKey("manutencao.id"),nullable=False,index=True)
    status=db.Column(db.String(30),nullable=False)
    inicio=db.Column(db.DateTime,default=now,nullable=False)
    fim=db.Column(db.DateTime)
    manutencao=db.relationship("Manutencao",backref="etapas")