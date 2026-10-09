from app.extensions import db
from app.utils.time import now
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import Index, text

class Usuario(UserMixin, db.Model):
    id=db.Column(db.Integer,primary_key=True)
    nome=db.Column(db.String(120),nullable=False)
    email=db.Column(db.String(180),unique=True,nullable=False,index=True)
    senha_hash=db.Column(db.String(256),nullable=False)
    perfil=db.Column(db.String(30),nullable=False,default="RECEPCAO")
    ativo=db.Column(db.Boolean,default=True,nullable=False)
    trocar_senha=db.Column(db.Boolean,default=True,nullable=False)
    criado_em=db.Column(db.DateTime,default=now,nullable=False)
    @property
    def is_active(self): return self.ativo
    def set_password(self,password): self.senha_hash=generate_password_hash(password)
    def check_password(self,password): return check_password_hash(self.senha_hash,password)
    __table_args__=(db.CheckConstraint("perfil IN ('ADMINISTRADOR','RECEPCAO','TECNICO','ESTOQUE','GESTOR')",name="ck_usuario_perfil"),)
