from datetime import datetime
from functools import wraps
from urllib.parse import urlsplit
from flask import current_app,Blueprint,render_template,request,redirect,url_for,flash,send_file,abort
from flask_login import current_user
from sqlalchemy.exc import IntegrityError,OperationalError
from app.extensions import db
from app.models import *
from app.utils.security import roles,READ
from app.utils.time import now,today
from app.utils.storage import save_image
from app.services.operations import *
bp=Blueprint("operation",__name__)
def transaction(fn):
    @wraps(fn)
    def wrapper(*args,**kwargs):
        try:
            result=fn(*args,**kwargs); db.session.commit(); return result
        except (BusinessError,ValueError,IntegrityError,OperationalError) as e:
            db.session.rollback()
            flash(str(e) if isinstance(e,(BusinessError,ValueError)) else "Conflito de dados. Atualize e tente novamente.","danger")
            back=urlsplit(request.referrer or "")
            path=back.path+("?" + back.query if back.query else "") if back.netloc==request.host and back.path.startswith("/") else url_for("management.dashboard")
            return redirect(path)
    return wrapper
def integer(name,optional=False):
    raw=request.form.get(name,"")
    if optional and not raw: return None
    try: return int(raw)
    except (ValueError,TypeError): raise BusinessError("Seleção inválida: "+name)
def entered(name):
    try: return datetime.fromisoformat(request.form.get(name,""))
    except ValueError: raise BusinessError("Data/hora inválida.")
def techs(): return db.session.scalars(db.select(Usuario).where(Usuario.ativo.is_(True),Usuario.perfil.in_(["TECNICO","ADMINISTRADOR"]))).all()
def add_photo(maintenance,file,stage,category="",caption=""):
    path=save_image(file,"manutencao-"+str(maintenance.id))
    if path:
        db.session.add(FotoManutencao(manutencao_id=maintenance.id,etapa=stage,categoria=category,caminho=path,legenda=caption[:180],usuario_id=current_user.id))
        audit(current_user.id,"Foto registrada: "+stage,maintenance.id,maintenance.maquina_id,maintenance.id,"foto")
    return path
@bp.route("/manutencoes/nova",methods=["GET","POST"])
@roles("RECEPCAO")
@transaction
def maintenance_new():
    if request.method=="POST":
        if "numero_serie" in request.form or "tipo_equipamento_id" in request.form:
            from app.services.equipamento_service import equipamento_por_serie
            machine=equipamento_por_serie(integer("tipo_equipamento_id"),request.form.get("numero_serie",""),current_user.id,request.form.get("codigo_patrimonio",""),request.form.get("localizacao",""),integer("maquina_id",optional=True))
            machine_id=machine.id
        else: machine_id=integer("maquina_id")
        maintenance=criar_entrada(machine_id,current_user.id,entered("data_entrada"),request.form.get("horimetro",0),request.form.get("defeito",""),request.form.get("condicao_visual",""),request.form.get("observacoes",""))
        for category in ("Frente","Traseira","Lado direito","Lado esquerdo","Painel","Defeito","Outras"):
            for file in request.files.getlist("foto_"+category): add_photo(maintenance,file,"ENTRADA",category)
        flash("Entrada registrada. Próxima etapa: realizar checklist.","success")
        return redirect(url_for("operation.checklist",id=maintenance.id))
    selected=db.session.get(Maquina,request.args.get("maquina",type=int)) if request.args.get("maquina",type=int) else None
    types=db.session.scalars(db.select(TipoEquipamento).where(TipoEquipamento.ativo.is_(True)).order_by(TipoEquipamento.nome)).all()
    return render_template("maintenance_form.html",equipment_types=types,selected=selected)
@bp.get("/manutencoes")
@roles(*READ)
def maintenances():
    query=db.select(Manutencao).join(Maquina)
    if request.args.get("status"): query=query.where(Manutencao.status==request.args["status"])
    if request.args.get("ativas"): query=query.where(Manutencao.status.notin_(["FINALIZADA","CANCELADA"]))
    if request.args.get("q"):
        q="%"+request.args["q"]+"%"
        query=query.where(db.or_(Manutencao.numero_manutencao.ilike(q),Maquina.codigo_patrimonio.ilike(q),Maquina.modelo.ilike(q),Maquina.numero_serie.ilike(q)))
    query=period_filter(query,Manutencao.data_entrada)
    pagination=db.paginate(query.order_by(Manutencao.id.desc()),per_page=25,error_out=False)
    return render_template("maintenances.html",rows=pagination.items,pagination=pagination)
def period_filter(query,column):
    from datetime import date,time
    try:
        if request.args.get("inicio"): query=query.where(column>=datetime.combine(date.fromisoformat(request.args["inicio"]),time.min))
        if request.args.get("fim"): query=query.where(column<=datetime.combine(date.fromisoformat(request.args["fim"]),time.max))
    except ValueError: flash("Período inválido.","danger")
    return query
@bp.get("/manutencoes/<int:id>")
@roles(*READ)
def maintenance_detail(id):
    return render_template("maintenance.html",maintenance=db.get_or_404(Manutencao,id))
@bp.route("/manutencoes/<int:id>/checklist",methods=["GET","POST"])
@roles("RECEPCAO","TECNICO","GESTOR","ESTOQUE")
@transaction
def checklist(id):
    maintenance=db.get_or_404(Manutencao,id)
    if request.method=="POST":
        if current_user.perfil not in ("ADMINISTRADOR","RECEPCAO","TECNICO"): abort(403)
        entries=[]
        for item in maintenance.checklist.itens:
            path=add_photo(maintenance,request.files.get("foto_"+str(item.id)),"CHECKLIST",item.componente)
            entries.append(dict(id=item.id,acao=request.form.get("acao_"+str(item.id),item.acao if item.respondido or not item.obrigatorio else ""),observacao=request.form.get("obs_"+str(item.id),""),quantidade=request.form.get("qty_"+str(item.id),"1"),foto=path))
        for name,action,obs,qty in zip(request.form.getlist("extra_nome"),request.form.getlist("extra_acao"),request.form.getlist("extra_obs"),request.form.getlist("extra_qty")):
            entries.append(dict(componente=name,acao=action,observacao=obs,quantidade=qty))
        order=salvar_checklist(id,entries,current_user.id)
        flash("Checklist finalizado.","success")
        return redirect(url_for("operation.order_detail",id=order.id) if order else url_for("operation.maintenance_detail",id=id))
    return render_template("checklist.html",maintenance=maintenance)
@bp.post("/manutencoes/<int:id>/gerar-os")
@roles("RECEPCAO","TECNICO")
@transaction
def generate_order(id):
    order=gerar_os(id,current_user.id)
    flash("OS gerada. Próxima etapa: diagnóstico.","success")
    return redirect(url_for("operation.order_detail",id=order.id))
@bp.post("/manutencoes/<int:id>/cancelar")
@roles("TECNICO")
@transaction
def maintenance_cancel(id):
    cancelar_manutencao(id,current_user.id,request.form.get("motivo",""))
    flash("Cancelamento registrado; histórico preservado.","success")
    return redirect(url_for("operation.maintenance_detail",id=id))
@bp.post("/manutencoes/<int:id>/fotos")
@roles("RECEPCAO","TECNICO")
@transaction
def photo_upload(id):
    maintenance=locked(Manutencao,id)
    if maintenance.status in ("FINALIZADA","CANCELADA"): raise BusinessError("Manutenção encerrada.")
    stage=request.form.get("etapa")
    if stage not in ("ENTRADA","CHECKLIST","DIAGNOSTICO","REPARO","PECA_DANIFICADA","TESTE","FINALIZACAO"): raise BusinessError("Etapa inválida.")
    files=request.files.getlist("fotos")
    if not any(f.filename for f in files): raise BusinessError("Selecione uma foto.")
    for file in files: add_photo(maintenance,file,stage,caption=request.form.get("legenda",""))
    return redirect(url_for("operation.maintenance_detail",id=id))
@bp.get("/ordens")
@roles(*READ)
def orders():
    query=db.select(OrdemServico).join(Maquina)
    if request.args.get("status"): query=query.where(OrdemServico.status==request.args["status"])
    if request.args.get("q"): query=query.where(OrdemServico.numero_os.ilike("%"+request.args["q"]+"%"))
    if request.args.get("maquina"): query=query.where(Maquina.codigo_patrimonio.ilike("%"+request.args["maquina"]+"%"))
    if request.args.get("tecnico",type=int): query=query.where(OrdemServico.tecnico_id==request.args.get("tecnico",type=int))
    if request.args.get("abertas"): query=query.where(OrdemServico.status.notin_(["FINALIZADA","CANCELADA"]))
    if request.args.get("atrasadas"):
        config=db.session.get(ConfiguracaoEmpresa,1); from datetime import timedelta
        query=query.where(OrdemServico.status.notin_(["FINALIZADA","CANCELADA"]),OrdemServico.data_abertura<now()-timedelta(days=config.alerta_dias if config else 7))
    if request.args.get("hoje"): query=query.where(OrdemServico.data_finalizacao>=datetime.combine(today(),datetime.min.time()))
    query=period_filter(query,OrdemServico.data_abertura)
    pagination=db.paginate(query.order_by(OrdemServico.id.desc()),per_page=25,error_out=False)
    return render_template("orders.html",rows=pagination.items,pagination=pagination,technicians=techs())
@bp.get("/ordens/<int:id>")
@roles(*READ)
def order_detail(id):
    order=db.get_or_404(OrdemServico,id)
    parts=db.session.scalars(db.select(Peca).where(Peca.ativo.is_(True)).order_by(Peca.descricao)).all()
    return render_template("order.html",order=order,parts=parts,technicians=techs(),allow_manual_parts=current_app.config.get("ALLOW_MANUAL_PARTS",False))
@bp.post("/ordens/<int:id>/diagnostico")
@roles("TECNICO")
@transaction
def diagnosis(id):
    order=db.get_or_404(OrdemServico,id); entries=[]
    for item in order.itens:
        suffix=str(item.id); raw=request.form.get("peca_"+suffix,"")
        try: part=int(raw) if raw else None
        except ValueError: raise BusinessError("Peça inválida.")
        entries.append(dict(id=item.id,acao=request.form.get("acao_"+suffix,item.acao),problema=request.form.get("problema_"+suffix,""),diagnostico=request.form.get("diagnostico_"+suffix,""),causa=request.form.get("causa_"+suffix,""),peca_id=part,peca_manual=request.form.get("peca_manual_"+suffix,""),quantidade=request.form.get("qty_"+suffix,1),observacoes=request.form.get("obs_"+suffix,"")))
    salvar_diagnostico(id,current_user.id,integer("tecnico_id"),request.form.get("diagnostico",""),entries)
    flash("Diagnóstico salvo. Solicite peças ou inicie reparo.","success")
    return redirect(url_for("operation.order_detail",id=id))
@bp.post("/ordens/<int:id>/iniciar")
@roles("TECNICO")
@transaction
def repair_start(id):
    iniciar_reparo(id,current_user.id); return redirect(url_for("operation.order_detail",id=id))
@bp.post("/ordens/<int:id>/itens")
@roles("TECNICO")
@transaction
def item_new(id):
    adicionar_item(id,current_user.id,request.form.get("componente",""),request.form.get("acao"),request.form.get("quantidade",1),request.form.get("problema",""))
    return redirect(url_for("operation.order_detail",id=id))
@bp.post("/itens/<int:id>/status")
@roles("TECNICO")
@transaction
def item_finish(id):
    item=db.get_or_404(OrdemServicoItem,id)
    concluir_item(id,current_user.id,request.form.get("status","CONCLUIDO"))
    return redirect(url_for("operation.order_detail",id=item.ordem_servico_id))
@bp.post("/itens/<int:id>/solicitar")
@roles("TECNICO")
@transaction
def part_request(id):
    item=db.get_or_404(OrdemServicoItem,id)
    solicitar_peca(id,integer("peca_id"),request.form.get("quantidade",1),current_user.id)
    flash("Peça solicitada. O estoque fará a entrega.","success")
    return redirect(url_for("operation.order_detail",id=item.ordem_servico_id))
@bp.get("/pecas/solicitadas")
@roles(*READ)
def part_requests():
    query=db.select(SolicitacaoPeca)
    if request.args.get("status"): query=query.where(SolicitacaoPeca.status==request.args["status"])
    pagination=db.paginate(query.order_by(SolicitacaoPeca.id.desc()),per_page=25,error_out=False)
    return render_template("part_requests.html",rows=pagination.items,pagination=pagination)
@bp.post("/solicitacoes/<int:id>/status")
@roles("ESTOQUE")
@transaction
def request_status(id):
    status=request.form.get("status")
    if status=="ENTREGUE": entregar_peca(id,current_user.id)
    else: atualizar_solicitacao(id,status,current_user.id)
    flash("Solicitação atualizada.","success")
    return redirect(url_for("operation.part_requests"))
@bp.post("/ordens/<int:id>/enviar-teste")
@roles("TECNICO")
@transaction
def test_send(id):
    enviar_teste(id,current_user.id); return redirect(url_for("operation.order_detail",id=id))
@bp.post("/ordens/<int:id>/teste")
@roles("TECNICO")
@transaction
def test_save(id):
    registrar_teste(id,current_user.id,{k:request.form.get(k) for k in ("eletrico","funcionamento","carga","ventilacao","painel")},request.form.get("observacoes",""))
    return redirect(url_for("operation.order_detail",id=id))
@bp.post("/ordens/<int:id>/retornar")
@roles("TECNICO")
@transaction
def repair_return(id):
    retornar_reparo(id,current_user.id); return redirect(url_for("operation.order_detail",id=id))
@bp.post("/ordens/<int:id>/finalizar")
@roles("TECNICO")
@transaction
def finish(id):
    finalized=entered("data_finalizacao") if request.form.get("data_finalizacao") else None
    finalizar_os(id,current_user.id,integer("tecnico_id"),request.form.get("diagnostico",""),request.form.get("servico",""),request.form.get("observacoes",""),request.form.get("horimetro",0),request.form.get("mao_obra",0),finalized)
    flash("Manutenção finalizada. Máquina disponível.","success")
    return redirect(url_for("operation.order_detail",id=id))
@bp.get("/ordens/<int:id>/pdf")
@roles(*READ)
def pdf(id):
    from app.services.pdf_service import generate_order
    order=db.get_or_404(OrdemServico,id)
    return send_file(generate_order(order),mimetype="application/pdf",as_attachment=True,download_name=order.numero_os+".pdf")
@bp.route("/estoque/movimentacoes",methods=["GET","POST"])
@roles(*READ)
@transaction
def stock():
    if request.method=="POST":
        if current_user.perfil not in ("ESTOQUE","ADMINISTRADOR"): abort(403)
        tipo=request.form.get("tipo")
        if tipo not in ("ENTRADA","AJUSTE","DEVOLUCAO"): raise BusinessError("Entregue peças pela tela de solicitações.")
        movimentar(integer("peca_id"),tipo,request.form.get("quantidade"),current_user.id,request.form.get("observacao",""))
        flash("Movimentação registrada.","success")
        return redirect(url_for("operation.stock"))
    query=db.select(MovimentacaoEstoque).order_by(MovimentacaoEstoque.id.desc())
    pagination=db.paginate(query,per_page=30,error_out=False)
    parts=db.session.scalars(db.select(Peca).where(Peca.ativo.is_(True))).all()
    return render_template("stock.html",rows=pagination.items,pagination=pagination,parts=parts)

@bp.post("/itens/<int:id>/reabrir")
@roles("TECNICO")
@transaction
def item_reopen(id):
    item=db.get_or_404(OrdemServicoItem,id); reabrir_item(id,current_user.id)
    return redirect(url_for("operation.order_detail",id=item.ordem_servico_id))
