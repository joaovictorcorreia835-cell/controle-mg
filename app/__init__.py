import logging
import sqlite3
from flask import Flask, render_template, redirect, url_for, request, flash, send_from_directory
from flask_login import current_user, logout_user
from sqlalchemy import event
from sqlalchemy.engine import Engine
from config import Config
from app.extensions import db, login, migrate, csrf
@event.listens_for(Engine, "connect")
def sqlite_foreign_keys(connection, record):
    if isinstance(connection,sqlite3.Connection): connection.execute("PRAGMA foreign_keys=ON")
def create_app(test_config=None):
    app=Flask(__name__)
    app.config.from_object(Config)
    if test_config: app.config.update(test_config)
    if not app.config.get("SECRET_KEY"): raise RuntimeError("Configure SECRET_KEY no ambiente antes de iniciar.")
    if app.config.get("IS_PRODUCTION"):
        if len(app.config["SECRET_KEY"])<32: raise RuntimeError("SECRET_KEY de produção deve ter pelo menos 32 caracteres.")
        if not app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql+psycopg://"): raise RuntimeError("Configure DATABASE_URL PostgreSQL no Render.")
        if not app.config.get("SESSION_COOKIE_SECURE"): raise RuntimeError("Configure COOKIE_SECURE=true para HTTPS no Render.")
        app.config["DEBUG"]=False; app.config["TESTING"]=False
    db.init_app(app); login.init_app(app); migrate.init_app(app,db,render_as_batch=True); csrf.init_app(app)
    login.login_view="auth.login"; login.login_message="Entre para continuar."
    from app.models import Usuario
    @login.user_loader
    def load_user(id):
        try: return db.session.get(Usuario,int(id))
        except (ValueError,TypeError): return None
    from app.routes.auth import bp as auth
    from app.routes.catalog import bp as catalog
    from app.routes.operation import bp as operation
    from app.routes.management import bp as management
    from app.routes.checklist_models import bp as checklist_models
    for bp in (auth,catalog,operation,management,checklist_models): app.register_blueprint(bp)
    from app.cli import register
    register(app)
    @app.get("/health")
    def health():
        db.session.execute(db.text("SELECT 1"))
        return {"status":"ok"}
    @app.get("/static/uploads/<path:filename>")
    def uploaded(filename):
        from flask_login import login_required
        if not current_user.is_authenticated: return redirect(url_for("auth.login"))
        from pathlib import Path
        return send_from_directory(app.config.get("UPLOAD_FOLDER") or str(Path(app.static_folder)/"uploads"),filename)
    @app.before_request
    def require_password():
        if request.endpoint=="health": return None
        if current_user.is_authenticated:
            if not current_user.ativo:
                logout_user(); return redirect(url_for("auth.login"))
            if current_user.trocar_senha and request.endpoint not in ("auth.password","auth.logout","static"):
                return redirect(url_for("auth.password"))
    def page_url(page):
        args=request.args.to_dict(); args["page"]=page
        return url_for(request.endpoint,**(request.view_args or {}),**args)
    @app.context_processor
    def context():
        from app.utils.time import now,today
        from app.models import ConfiguracaoEmpresa
        return dict(today=today(),now=now(),empresa=db.session.get(ConfiguracaoEmpresa,1),getattr=getattr,page_url=page_url)
    @app.template_filter("money")
    def money(value): return f"R$ {float(value or 0):,.2f}".replace(",","X").replace(".",",").replace("X",".")
    @app.template_filter("label")
    def label(value): return str(value or "").replace("_"," ").title()
    @app.errorhandler(403)
    @app.errorhandler(404)
    def known_error(error): return render_template("error.html",code=error.code,message=error.description),error.code
    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback(); app.logger.exception("Erro interno")
        return render_template("error.html",code=500,message="Não foi possível concluir a operação."),500
    logging.basicConfig(level=logging.INFO)
    return app
