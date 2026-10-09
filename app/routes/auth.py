from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from app.extensions import db
from app.models import Usuario
from app.services.operations import audit
bp=Blueprint("auth",__name__)
@bp.route("/login",methods=["GET","POST"])
def login():
    if current_user.is_authenticated: return redirect(url_for("management.dashboard"))
    if request.method=="POST":
        user=db.session.scalar(db.select(Usuario).where(Usuario.email==request.form.get("email","").strip().lower()))
        if user and user.ativo and user.check_password(request.form.get("password","")):
            login_user(user); audit(user.id,"Login",user.id); db.session.commit()
            return redirect(url_for("management.dashboard"))
        flash("Email ou senha inválidos.","danger")
    return render_template("login.html")
@bp.post("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
@bp.route("/senha",methods=["GET","POST"])
@login_required
def password():
    if request.method=="POST":
        old=request.form.get("old",""); new=request.form.get("new","")
        if not current_user.check_password(old): flash("Senha atual incorreta.","danger")
        elif len(new)<10 or new==old: flash("Use uma nova senha de pelo menos 10 caracteres.","danger")
        elif new!=request.form.get("confirm"): flash("As senhas não conferem.","danger")
        else:
            current_user.set_password(new); current_user.trocar_senha=False
            audit(current_user.id,"Senha alterada",current_user.id); db.session.commit()
            flash("Senha alterada.","success"); return redirect(url_for("management.dashboard"))
    return render_template("password.html")
