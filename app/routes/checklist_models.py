from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.models import TipoEquipamento, CategoriaChecklist, ModeloChecklist, ModeloChecklistItem
from app.utils.security import roles
from app.services.common import BusinessError, audit, locked

bp = Blueprint("checklist_models", __name__)


@bp.route("/configuracoes/modelos-checklist", methods=["GET", "POST"])
@roles()
def listing():
    if request.method == "POST":
        try:
            action = request.form.get("acao")
            nome = request.form.get("nome", "").strip().upper()
            if action == "tipo":
                if not nome or len(nome) > 80: raise BusinessError("Informe um tipo com até 80 caracteres.")
                tipo = TipoEquipamento(nome=nome)
                db.session.add(ModeloChecklist(tipo=tipo)); db.session.flush()
                audit(current_user.id, "Tipo de equipamento criado: " + nome, tipo.id, entity="tipo_equipamento")
                db.session.commit()
                return redirect(url_for("checklist_models.listing", tipo=tipo.id))
            elif action == "categoria":
                if not nome or len(nome) > 120: raise BusinessError("Informe uma categoria com até 120 caracteres.")
                categoria = CategoriaChecklist(nome=nome); db.session.add(categoria); db.session.flush()
                audit(current_user.id, "Categoria de checklist criada: " + nome, categoria.id, entity="categoria_checklist")
            else: raise BusinessError("Ação inválida.")
            db.session.commit(); flash("Cadastro salvo.", "success")
        except (BusinessError, IntegrityError) as error:
            db.session.rollback(); flash(str(error) if isinstance(error, BusinessError) else "Nome já cadastrado.", "danger")
        return redirect(url_for("checklist_models.listing", tipo=request.args.get("tipo")))
    tipos = db.session.scalars(db.select(TipoEquipamento).order_by(TipoEquipamento.nome)).all()
    selected = request.args.get("tipo", type=int)
    tipo = db.get_or_404(TipoEquipamento, selected) if selected else (tipos[0] if tipos else None)
    categorias = db.session.scalars(db.select(CategoriaChecklist).order_by(CategoriaChecklist.nome)).all()
    return render_template("checklist_models.html", tipos=tipos, tipo=tipo, categorias=categorias)


@bp.route("/configuracoes/modelos-checklist/<int:tipo_id>/itens/novo", methods=["GET", "POST"])
@bp.route("/configuracoes/modelos-checklist/<int:tipo_id>/itens/<int:item_id>/editar", methods=["GET", "POST"])
@roles()
def item_edit(tipo_id, item_id=None):
    tipo = db.get_or_404(TipoEquipamento, tipo_id)
    item = db.get_or_404(ModeloChecklistItem, item_id) if item_id else ModeloChecklistItem(modelo_id=tipo.modelo_checklist.id)
    if item.modelo_id != tipo.modelo_checklist.id:
        from flask import abort
        abort(404)
    if request.method == "POST":
        try:
            locked(ModeloChecklist, tipo.modelo_checklist.id)
            if item_id: item = locked(ModeloChecklistItem, item_id)
            componente = request.form.get("componente", "").strip()
            if not componente or len(componente) > 180: raise BusinessError("Informe componente com até 180 caracteres.")
            try:
                ordem = int(request.form.get("ordem", "")); categoria_id = int(request.form.get("categoria_id", ""))
            except ValueError: raise BusinessError("Categoria ou ordem inválida.")
            if ordem < 0 or not db.session.get(CategoriaChecklist, categoria_id): raise BusinessError("Categoria ou ordem inválida.")
            if request.form.get("obrigatorio") not in ("0", "1") or request.form.get("ativo") not in ("0", "1"): raise BusinessError("Selecione Sim ou Não.")
            item.componente = componente; item.categoria_id = categoria_id
            item.descricao = request.form.get("descricao", "").strip()
            item.obrigatorio = request.form["obrigatorio"] == "1"
            item.ativo = request.form["ativo"] == "1"; item.ordem = ordem
            db.session.add(item); db.session.flush()
            audit(current_user.id, "Modelo de checklist atualizado: " + tipo.nome, item.id, entity="modelo_checklist_item")
            db.session.commit(); flash("Item salvo. Checklists existentes permanecem preservados.", "success")
            return redirect(url_for("checklist_models.listing", tipo=tipo.id))
        except (BusinessError, IntegrityError) as error:
            db.session.rollback(); flash(str(error) if isinstance(error, BusinessError) else "Conflito de dados.", "danger")
    categorias = db.session.scalars(db.select(CategoriaChecklist).order_by(CategoriaChecklist.nome)).all()
    return render_template("checklist_model_item.html", tipo=tipo, item=item, categorias=categorias)


@bp.post("/configuracoes/modelos-checklist/<int:tipo_id>/itens/<int:item_id>/desativar")
@roles()
def item_disable(tipo_id, item_id):
    tipo = db.get_or_404(TipoEquipamento, tipo_id)
    item = db.get_or_404(ModeloChecklistItem, item_id)
    if item.modelo_id != tipo.modelo_checklist.id:
        from flask import abort
        abort(404)
    locked(ModeloChecklist, tipo.modelo_checklist.id)
    item = locked(ModeloChecklistItem, item_id); item.ativo = False
    audit(current_user.id, "Item do modelo desativado: " + tipo.nome, item.id, entity="modelo_checklist_item")
    db.session.commit(); flash("Item desativado para novos checklists.", "success")
    return redirect(url_for("checklist_models.listing", tipo=tipo.id))
