import csv
from io import StringIO
from datetime import datetime,date,timedelta,time
from collections import Counter,defaultdict
from flask import Blueprint,render_template,request,redirect,url_for,flash,Response,abort
from flask_login import current_user
from sqlalchemy import or_
from app.extensions import db
from app.models import *
from app.utils.security import roles,READ
from app.utils.time import now,today
from app.utils.storage import save_image
from app.services.common import audit,BusinessError
from app.services.indicators import summarize,avg,hours,waiting
bp=Blueprint("management",__name__)
def all_rows(model): return db.session.scalars(db.select(model)).all()
@bp.get("/")
@roles(*READ)
def dashboard():
    machines=all_rows(Maquina); maintenance=all_rows(Manutencao); orders=all_rows(OrdemServico); parts=all_rows(Peca)
    config=db.session.get(ConfiguracaoEmpresa,1); days=config.alerta_dias if config else 7
    counts=Counter(m.status for m in maintenance if m.status not in ("FINALIZADA","CANCELADA"))
    cards=[("Máquinas cadastradas",len(machines),url_for("catalog.listing",kind="maquinas")),("Em manutenção",sum(counts.values()),url_for("operation.maintenances",ativas=1))]
    for label,status in [("Aguardando checklist","AGUARDANDO_CHECKLIST"),("Aguardando diagnóstico","AGUARDANDO_DIAGNOSTICO"),("Aguardando peça","AGUARDANDO_PECA"),("Em reparo","EM_REPARO"),("Aguardando teste","AGUARDANDO_TESTE")]:
        cards.append((label,counts[status],url_for("operation.maintenances",status=status)))
    cards += [("Finalizadas hoje",sum(o.status=="FINALIZADA" and o.data_finalizacao.date()==today() for o in orders),url_for("operation.orders",status="FINALIZADA",hoje=1)),("OS abertas",sum(o.status not in ("FINALIZADA","CANCELADA") for o in orders),url_for("operation.orders",abertas=1)),("OS atrasadas",sum(o.status not in ("FINALIZADA","CANCELADA") and (now()-o.data_abertura).days>=days for o in orders),url_for("operation.orders",atrasadas=1))]
    stats=summarize(maintenance,orders)
    month_keys=[]
    for offset in range(11,-1,-1):
        n=today().year*12+today().month-1-offset
        month_keys.append(f"{n//12}-{n%12+1:02d}")
    charts=[("Manutenções por mês",{month:sum(m.data_entrada.strftime("%Y-%m")==month for m in maintenance) for month in month_keys}),("Máquinas por status",dict(Counter(m.status for m in machines))),("Principais defeitos",dict(stats["defects"].most_common(5))),("Peças mais substituídas",dict(stats["used"].most_common(5))),("Máquinas com mais manutenções",dict(stats["machines"].most_common(5))),("Custo de manutenção por mês",{month:float(sum(o.valor_total for o in orders if o.status=="FINALIZADA" and o.data_finalizacao.strftime("%Y-%m")==month)) for month in month_keys}),("Tempo médio de manutenção (horas)",{month:avg([hours(m) for m in maintenance if m.status=="FINALIZADA" and m.data_saida.strftime("%Y-%m")==month]) for month in month_keys})]
    alerts=[]
    for m in maintenance:
        if m.status in ("FINALIZADA","CANCELADA"): continue
        link=url_for("operation.maintenance_detail",id=m.id)
        if m.dias_parada>=days: alerts.append((f"{m.maquina.codigo_patrimonio} parada há {m.dias_parada} dias",link))
        if m.status in ("AGUARDANDO_DIAGNOSTICO","AGUARDANDO_PECA"): alerts.append((m.numero_manutencao+": "+m.status.replace("_"," ").lower(),link))
        if (now()-m.atualizado_em).days>=days: alerts.append((m.numero_manutencao+" sem movimentação",link))
    for part in parts:
        if part.ativo and part.quantidade_estoque<part.estoque_minimo: alerts.append(("Estoque baixo: "+part.descricao,url_for("catalog.listing",kind="pecas")))
    for machine in machines:
        if sum(m.data_entrada>=now()-timedelta(days=90) for m in machine.manutencoes)>=3: alerts.append(("Manutenção recorrente: "+machine.codigo_patrimonio,url_for("catalog.machine",id=machine.id)))
    active=sorted([m for m in maintenance if m.status not in ("FINALIZADA","CANCELADA")],key=lambda m:m.data_entrada)[:10]
    return render_template("dashboard.html",cards=cards,charts=charts,alerts=alerts,stats=stats,active=active)
@bp.get("/manutencao")
@roles(*READ)
def kanban():
    columns=[("EM_MANUTENCAO","Entrada"),("AGUARDANDO_CHECKLIST","Checklist"),("AGUARDANDO_DIAGNOSTICO","Diagnóstico"),("AGUARDANDO_PECA","Aguardando peça"),("EM_REPARO","Em reparo"),("AGUARDANDO_TESTE","Aguardando teste"),("FINALIZADA","Finalizada")]
    query=db.select(Manutencao).join(Maquina).order_by(Manutencao.data_entrada.desc())
    if request.args.get("maquina"): query=query.where(Maquina.codigo_patrimonio.ilike("%"+request.args["maquina"]+"%"))
    config=db.session.get(ConfiguracaoEmpresa,1)
    latest={}
    for maintenance in db.session.scalars(query).all():
        if maintenance.maquina_id not in latest or maintenance.id>latest[maintenance.maquina_id].id: latest[maintenance.maquina_id]=maintenance
    board={status:[] for status,title in columns}
    for maintenance in latest.values():
        stage="EM_MANUTENCAO" if maintenance.status=="CANCELADA" and maintenance.maquina.status=="EM_MANUTENCAO" else maintenance.status
        if stage in board: board[stage].append(maintenance)
    return render_template("kanban.html",columns=columns,board=board,alert_days=config.alerta_dias if config else 7)
@bp.get("/checklists")
@roles(*READ)
def checklists(): return redirect(url_for("operation.maintenances",status="AGUARDANDO_CHECKLIST"))
@bp.get("/historico")
@roles(*READ)
def history(): return redirect(url_for("operation.maintenances"))
@bp.get("/pesquisa")
@roles(*READ)
def search():
    q=request.args.get("q","").strip(); results=[]
    if q:
        for model,fields,endpoint,label in [(Maquina,["codigo_patrimonio","numero_serie","modelo"],"catalog.machine","codigo_patrimonio"),(Manutencao,["numero_manutencao"],"operation.maintenance_detail","numero_manutencao"),(OrdemServico,["numero_os"],"operation.order_detail","numero_os"),(Peca,["codigo","descricao"],"catalog.listing","descricao")]:
            rows=db.session.scalars(db.select(model).where(or_(*[getattr(model,f).ilike("%"+q+"%") for f in fields])).limit(30)).all()
            for row in rows: results.append((model.__name__,getattr(row,label),url_for(endpoint,kind="pecas",q=row.codigo) if model==Peca else url_for(endpoint,id=row.id)))
    return render_template("search.html",results=results,q=q)
REPORTS={"manutencao":"Máquinas em manutenção","finalizadas":"Manutenções finalizadas","os_abertas":"OS abertas","os_finalizadas":"OS finalizadas","aguardando_peca":"Máquinas aguardando peça","pecas":"Peças utilizadas","custo_maquina":"Custo por máquina","custo_periodo":"Custo por período","defeitos":"Defeitos recorrentes","substituidas":"Peças mais substituídas","tempo":"Tempo médio de manutenção","recorrentes":"Máquinas com mais defeitos","produtividade":"Produtividade por técnico","estoque":"Movimentações de estoque"}
def report_period():
    period=request.args.get("periodo","personalizado"); start=request.args.get("inicio",""); end=request.args.get("fim","")
    if period=="hoje": return today(),today()
    if period=="semana": return today()-timedelta(days=today().weekday()),today()
    if period=="mes": return today().replace(day=1),today()
    a=date.fromisoformat(start) if start else date.min; b=date.fromisoformat(end) if end else date.max
    if a>b: raise ValueError()
    return a,b
@bp.get("/relatorios")
@roles(*READ)
def reports():
    kind=request.args.get("tipo","manutencao")
    if kind not in REPORTS: abort(400)
    try: a,b=report_period()
    except ValueError: flash("Período inválido.","danger"); a=date.min; b=date.max
    maintenance=[m for m in all_rows(Manutencao) if a<= (m.data_saida.date() if kind in ("finalizadas","tempo","produtividade") and m.data_saida else m.data_entrada.date()) <=b]
    orders=[o for o in all_rows(OrdemServico) if a<= (o.data_finalizacao.date() if kind in ("os_finalizadas","custo_periodo","produtividade") and o.data_finalizacao else o.data_abertura.date()) <=b]
    rows=[]; headers=[]
    if kind in ("manutencao","finalizadas","aguardando_peca"):
        headers=["Manutenção","Patrimônio","Modelo","Entrada","Saída","Status","Horas","Defeito"]
        for m in maintenance:
            include=(m.status not in ("FINALIZADA","CANCELADA")) if kind=="manutencao" else m.status==("FINALIZADA" if kind=="finalizadas" else "AGUARDANDO_PECA")
            if include: rows.append([m.numero_manutencao,m.maquina.codigo_patrimonio,m.maquina.modelo,m.data_entrada,m.data_saida,m.status,round(hours(m),2),m.defeito_relatado])
    elif kind in ("os_abertas","os_finalizadas"):
        headers=["OS","Máquina","Técnico","Abertura","Finalização","Status","Custo"]
        rows=[[o.numero_os,o.maquina.codigo_patrimonio,o.tecnico.nome if o.tecnico else "",o.data_abertura,o.data_finalizacao,o.status,o.valor_total] for o in orders if (o.status not in ("FINALIZADA","CANCELADA") if kind=="os_abertas" else o.status=="FINALIZADA")]
    elif kind in ("pecas","estoque","substituidas"):
        moves=[m for m in all_rows(MovimentacaoEstoque) if a<=m.criado_em.date()<=b and (kind=="estoque" or m.tipo=="SAIDA_OS")]
        if kind=="substituidas":
            headers=["Peça","Quantidade"]; totals=defaultdict(float)
            for m in moves: totals[m.peca.descricao]+=float(m.quantidade)
            rows=sorted(totals.items(),key=lambda r:r[1],reverse=True)
        else:
            headers=["Data","Peça","Tipo","Quantidade","Anterior","Posterior","OS","Usuário"]
            rows=[[m.criado_em,m.peca.descricao,m.tipo,m.quantidade,m.estoque_anterior,m.estoque_posterior,m.ordem_servico_id,m.usuario.nome] for m in moves]
    elif kind in ("custo_maquina","recorrentes"):
        headers=["Máquina","Modelo","Manutenções","Peças","Mão de obra","Total"]
        for machine in all_rows(Maquina):
            selected=[o for o in orders if o.maquina_id==machine.id]; count=sum(m.maquina_id==machine.id for m in maintenance)
            parts=sum(o.valor_pecas for o in selected); labor=sum(o.valor_mao_obra for o in selected)
            rows.append([machine.codigo_patrimonio,machine.modelo,count,parts,labor,parts+labor])
        rows.sort(key=lambda r:r[-1] if kind=="custo_maquina" else r[2],reverse=True)
    elif kind=="custo_periodo":
        headers=["Mês","OS finalizadas","Custo"]; buckets=defaultdict(list)
        for o in orders:
            if o.status=="FINALIZADA": buckets[o.data_finalizacao.strftime("%Y-%m")].append(o)
        rows=[[k,len(v),sum(o.valor_total for o in v)] for k,v in sorted(buckets.items())]
    elif kind=="defeitos":
        headers=["Defeito relatado","Ocorrências"]
        rows=Counter(m.defeito_relatado.strip().lower() for m in maintenance).most_common()
    elif kind=="tempo":
        headers=["Máquina","Manutenções finalizadas","Tempo médio (h)","Tempo médio aguardando peça (h)"]
        for machine in all_rows(Maquina):
            selected=[m for m in maintenance if m.maquina_id==machine.id and m.status=="FINALIZADA"]
            if selected: rows.append([machine.codigo_patrimonio,len(selected),round(avg([hours(m) for m in selected]),2),round(avg([waiting(m) for m in selected]),2)])
    elif kind=="produtividade":
        headers=["Técnico","OS finalizadas","Serviços concluídos","Tempo médio por manutenção (h)"]
        for tech in all_rows(Usuario):
            if tech.perfil not in ("TECNICO","ADMINISTRADOR"): continue
            closed=[o for o in orders if o.tecnico_id==tech.id and o.status=="FINALIZADA"]
            count=sum(i.concluido_por==tech.id and i.concluido_em and a<=i.concluido_em.date()<=b for i in all_rows(OrdemServicoItem))
            rows.append([tech.nome,len(closed),count,round(avg([hours(o.manutencao) for o in closed]),2)])
    if request.args.get("csv"):
        output=StringIO(); writer=csv.writer(output,delimiter=";"); writer.writerow(headers)
        for row in rows: writer.writerow([("'"+str(v)) if str(v).startswith(("=","+","-","@","\t","\r")) else v for v in row])
        return Response("\ufeff"+output.getvalue(),mimetype="text/csv; charset=utf-8",headers={"Content-Disposition":f"attachment; filename={kind}.csv"})
    return render_template("reports.html",types=REPORTS,kind=kind,headers=headers,rows=rows,stats=summarize(maintenance,orders))
@bp.route("/configuracoes",methods=["GET","POST"])
@roles()
def settings():
    company=db.session.get(ConfiguracaoEmpresa,1) or ConfiguracaoEmpresa(id=1)
    if request.method=="POST":
        try:
            for field in ("nome_empresa","razao_social","cnpj","telefone","email","endereco","cidade","estado"):
                value=request.form.get(field,"").strip(); column=ConfiguracaoEmpresa.__table__.c[field]
                if len(value)>column.type.length: raise BusinessError("Texto muito longo: "+field)
                setattr(company,field,value)
            try: days=int(request.form.get("alerta_dias",7))
            except ValueError: raise BusinessError("Dias de alerta inválidos.")
            if not 1<=days<=365: raise BusinessError("Dias de alerta devem estar entre 1 e 365.")
            company.alerta_dias=days; company.gerar_os_automaticamente=request.form.get("gerar_os_automaticamente")=="1"
            photo=save_image(request.files.get("logo"))
            if photo: company.logo=photo
            db.session.add(company); audit(current_user.id,"Configurações atualizadas",1,entity="empresa"); db.session.commit()
            flash("Configurações salvas.","success")
        except BusinessError as e: db.session.rollback(); flash(str(e),"danger")
    return render_template("settings.html",company=company)
@bp.get("/auditoria")
@roles("GESTOR")
def audits():
    pagination=db.paginate(db.select(Auditoria).order_by(Auditoria.id.desc()),per_page=50,error_out=False)
    return render_template("audit.html",rows=pagination.items,pagination=pagination)
