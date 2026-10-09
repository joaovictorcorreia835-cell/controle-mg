from collections import Counter
from flask import Blueprint,render_template,request,redirect,url_for,flash,abort
from flask_login import current_user
from sqlalchemy import or_,update
from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.models import *
from app.utils.security import roles,PROFILES,READ
from app.utils.storage import save_image
from app.services.common import decimal,BusinessError,audit,locked
bp=Blueprint("catalog",__name__)
CATALOGS={
 "maquinas":(Maquina,"Máquinas",["RECEPCAO"],["codigo_patrimonio","numero_serie","marca","modelo","tipo_equipamento_id","potencia","tensao","capacidade","ano","horimetro","localizacao","observacoes"]),
 "pecas":(Peca,"Peças",["ESTOQUE"],["codigo","descricao","marca","aplicacao","unidade","estoque_minimo","custo_unitario","localizacao"]),
 "usuarios":(Usuario,"Usuários",[],["nome","email","perfil"])
}
def info(kind,write=False):
    if kind not in CATALOGS: abort(404)
    model,title,allowed,fields=CATALOGS[kind]
    if (kind=="usuarios" or write) and current_user.perfil!="ADMINISTRADOR" and current_user.perfil not in allowed: abort(403)
    return model,title,fields
@bp.get("/cadastros/<kind>")
@roles(*READ)
def listing(kind):
    model,title,fields=info(kind); query=db.select(model)
    q=request.args.get("q","").strip()
    search=[f for f in fields if isinstance(model.__table__.c[f].type,(db.String,db.Text))]
    if q: query=query.where(or_(*[getattr(model,f).ilike("%"+q+"%") for f in search]))
    for field in ("status","marca","modelo","localizacao"):
        if hasattr(model,field) and request.args.get(field): query=query.where(getattr(model,field)==request.args[field])
    if request.args.get("ativo") in ("0","1"): query=query.where(model.ativo==(request.args["ativo"]=="1"))
    pagination=db.paginate(query.order_by(model.id.desc()),per_page=25,error_out=False)
    columns={"maquinas":["codigo_patrimonio","numero_serie","marca","modelo","status","localizacao"],"pecas":["codigo","descricao","quantidade_estoque","estoque_minimo","custo_unitario","ativo"],"usuarios":["nome","email","perfil","ativo"]}[kind]
    return render_template("catalog_list.html",kind=kind,title=title,rows=pagination.items,pagination=pagination,columns=columns,can_edit=current_user.perfil=="ADMINISTRADOR" or current_user.perfil in CATALOGS[kind][2])
@bp.route("/cadastros/<kind>/novo",methods=["GET","POST"])
@bp.route("/cadastros/<kind>/<int:id>/editar",methods=["GET","POST"])
@roles(*READ)
def edit(kind,id=None):
    model,title,fields=info(kind,True); obj=db.get_or_404(model,id) if id else model()
    if request.method=="POST":
        try:
            if id: obj=locked(model,id)
            original_type=obj.tipo_equipamento_id if kind=="maquinas" else None
            for field in fields:
                col=model.__table__.c[field]; raw=request.form.get(field,"").strip()
                if not raw:
                    if not col.nullable and col.default is None: raise BusinessError("Preencha "+field.replace("_"," ")+".")
                    value=None if col.nullable else col.default.arg
                elif isinstance(col.type,db.Numeric): value=decimal(raw)
                elif isinstance(col.type,db.Integer):
                    try: value=int(raw)
                    except ValueError: raise BusinessError("Número inteiro inválido.")
                    if value<0: raise BusinessError("Número não pode ser negativo.")
                else:
                    value=raw
                    if col.type.length and len(value)>col.type.length: raise BusinessError("Texto muito longo: "+field)
                if field=="horimetro" and id and value<obj.horimetro: raise BusinessError("Horímetro não pode diminuir.")
                setattr(obj,field,value)
            if kind=="usuarios":
                if obj.perfil not in PROFILES: raise BusinessError("Perfil inválido.")
                if "@" not in obj.email: raise BusinessError("Email inválido.")
                obj.email=obj.email.lower(); password=request.form.get("password","")
                if password:
                    if len(password)<10: raise BusinessError("Senha deve ter pelo menos 10 caracteres.")
                    obj.set_password(password); obj.trocar_senha=True
                elif not id: raise BusinessError("Informe senha inicial.")
                if id==current_user.id and obj.perfil!="ADMINISTRADOR": raise BusinessError("Não altere seu próprio perfil administrativo.")
            if kind=="maquinas":
                tipo=db.session.get(TipoEquipamento,obj.tipo_equipamento_id) if obj.tipo_equipamento_id else None
                if not tipo or not tipo.ativo: raise BusinessError("Selecione um tipo de equipamento ativo.")
                if id and any(m.status not in ("FINALIZADA","CANCELADA") for m in obj.manutencoes):
                    if original_type!=obj.tipo_equipamento_id: raise BusinessError("Não altere o tipo durante uma manutenção ativa.")
                obj.tipo=tipo.nome
                photo=save_image(request.files.get("foto"))
                if photo: obj.foto=photo
                if not id: obj.status="DISPONIVEL"
            db.session.add(obj); db.session.flush()
            audit(current_user.id,("Cadastro criado: " if not id else "Cadastro atualizado: ")+title,obj.id,obj.id if kind=="maquinas" else None,entity=kind)
            db.session.commit(); flash("Registro salvo.","success")
            return redirect(url_for("catalog.machine",id=obj.id) if kind=="maquinas" else url_for("catalog.listing",kind=kind))
        except (BusinessError,IntegrityError) as e:
            db.session.rollback(); flash(str(e) if isinstance(e,BusinessError) else "Código, série ou email já cadastrado.","danger")
    specs=[]
    for f in fields:
        col=model.__table__.c[f]; type="number" if isinstance(col.type,(db.Numeric,db.Integer)) else "textarea" if isinstance(col.type,db.Text) else "email" if f=="email" else "text"
        specs.append((f,type,f=="tipo_equipamento_id" or (not col.nullable and col.default is None)))
    return render_template("catalog_form.html",kind=kind,title=title,obj=obj,fields=specs,profiles=PROFILES,equipment_types=db.session.scalars(db.select(TipoEquipamento).where(TipoEquipamento.ativo.is_(True)).order_by(TipoEquipamento.nome)).all())
@bp.post("/cadastros/<kind>/<int:id>/ativar")
@roles(*READ)
def toggle(kind,id):
    model,title,fields=info(kind,True)
    try:
        obj=locked(model,id)
        if kind=="usuarios" and id==current_user.id: raise BusinessError("Você não pode desativar seu próprio acesso.")
        if kind=="maquinas":
            if obj.status not in ("DISPONIVEL","INATIVA") or any(m.status not in ("FINALIZADA","CANCELADA") for m in obj.manutencoes): raise BusinessError("Máquina possui manutenção em andamento.")
            changed=db.session.execute(update(Maquina).where(Maquina.id==id,Maquina.status==obj.status,Maquina.ativo==obj.ativo).values(ativo=not obj.ativo,status="DISPONIVEL" if not obj.ativo else "INATIVA"))
            if changed.rowcount!=1: raise BusinessError("Máquina alterada por outra operação.")
        else: obj.ativo=not obj.ativo
        audit(current_user.id,"Ativação alterada",id,id if kind=="maquinas" else None,entity=kind)
        db.session.commit(); flash("Situação alterada.","success")
    except BusinessError as e: db.session.rollback(); flash(str(e),"danger")
    return redirect(url_for("catalog.listing",kind=kind))
@bp.get("/maquinas/<int:id>")
@roles(*READ)
def machine(id):
    machine=db.get_or_404(Maquina,id)
    parts=sum(o.valor_pecas for o in machine.ordens); labor=sum(o.valor_mao_obra for o in machine.ordens)
    closed=[m for m in machine.manutencoes if m.status=="FINALIZADA"]
    average=sum((m.data_saida-m.data_entrada).total_seconds()/3600 for m in closed)/len(closed) if closed else 0
    defects=Counter(m.defeito_relatado.strip().lower() for m in machine.manutencoes)
    return render_template("machine.html",machine=machine,parts=parts,labor=labor,average=average,recurring=defects.most_common(1)[0][0] if defects else "—")
