from app.extensions import db
from app.utils.time import now
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import Index, text

class ConfiguracaoEmpresa(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    nome_empresa=db.Column(db.String(180),default="Controle MG")
    razao_social=db.Column(db.String(180),default="Controle MG")
    cnpj=db.Column(db.String(18))
    telefone=db.Column(db.String(30))
    email=db.Column(db.String(180))
    endereco=db.Column(db.String(250))
    cidade=db.Column(db.String(120))
    estado=db.Column(db.String(2))
    logo=db.Column(db.String(255))
    alerta_dias=db.Column(db.Integer,default=7,nullable=False)
    gerar_os_automaticamente=db.Column(db.Boolean,default=False,nullable=False)
    __table_args__=(db.CheckConstraint("alerta_dias > 0",name="ck_alerta_dias"),)
