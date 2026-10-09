from app.extensions import db
from app.utils.time import now
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import Index, text

class HistoricoMaquina(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    maquina_id=db.Column(db.Integer,db.ForeignKey("maquina.id"),nullable=False,index=True)
    manutencao_id=db.Column(db.Integer,db.ForeignKey("manutencao.id"),index=True)
    usuario_id=db.Column(db.Integer,db.ForeignKey("usuario.id"))
    evento=db.Column(db.String(250),nullable=False)
    criado_em=db.Column(db.DateTime,default=now,nullable=False)
    maquina=db.relationship("Maquina",backref=db.backref("historico",order_by="HistoricoMaquina.criado_em.desc()"))