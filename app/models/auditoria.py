from app.extensions import db
from app.utils.time import now
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import Index, text

class Auditoria(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    usuario_id=db.Column(db.Integer,db.ForeignKey("usuario.id"),nullable=False)
    acao=db.Column(db.String(250),nullable=False)
    entidade=db.Column(db.String(60),nullable=False)
    entidade_id=db.Column(db.Integer,nullable=False)
    descricao=db.Column(db.Text)
    data_hora=db.Column(db.DateTime,default=now,nullable=False,index=True)
    usuario=db.relationship("Usuario")