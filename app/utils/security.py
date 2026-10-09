from functools import wraps
from flask import abort
from flask_login import current_user, login_required
PROFILES=["ADMINISTRADOR","RECEPCAO","TECNICO","ESTOQUE","GESTOR"]
READ=tuple(PROFILES)
def roles(*allowed):
    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapped(*args,**kwargs):
            if not current_user.ativo or (current_user.perfil!="ADMINISTRADOR" and current_user.perfil not in allowed): abort(403)
            return fn(*args,**kwargs)
        return wrapped
    return decorator
