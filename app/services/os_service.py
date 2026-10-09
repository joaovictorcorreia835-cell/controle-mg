from uuid import uuid4
from flask import current_app
from app.extensions import db
from app.models import *
from app.utils.time import now,today
from .common import *
def sincronizar_itens(order):
    existing={i.checklist_item_id:i for i in order.itens if i.checklist_item_id}
    for ci in order.manutencao.checklist.itens:
        item=existing.get(ci.id)
        if ci.acao in ("REPARAR","SUBSTITUIR"):
            if not item:
                item=OrdemServicoItem(ordem_servico_id=order.id,checklist_item_id=ci.id); db.session.add(item)
            item.componente=ci.componente; item.acao=ci.acao
            if ci.acao!="SUBSTITUIR": item.peca_manual=None
            item.descricao_problema=ci.observacao; item.quantidade=ci.quantidade
        elif item: db.session.delete(item)
    db.session.flush(); db.session.expire(order,["itens"])
def gerar_os(maintenance_id,uid):
    maintenance=locked(Manutencao,maintenance_id)
    if maintenance.status in ("FINALIZADA","CANCELADA"): raise BusinessError("Manutenção encerrada.")
    if not maintenance.checklist.salvo_em: raise BusinessError("Realize o checklist antes de gerar a OS.")
    if maintenance.ordem: raise BusinessError("Já existe OS para esta manutenção.")
    order=OrdemServico(numero_os="TMP-"+uuid4().hex,manutencao_id=maintenance.id,maquina_id=maintenance.maquina_id,defeito_relatado=maintenance.defeito_relatado,status="AGUARDANDO_DIAGNOSTICO")
    db.session.add(order); db.session.flush()
    order.numero_os=f"OS-{today().year}-{order.id:06d}"
    sincronizar_itens(order); db.session.expire(maintenance,["ordem"])
    change_status(maintenance,"AGUARDANDO_DIAGNOSTICO",uid,order.numero_os+" ABERTA")
    return order
def technician(id):
    user=db.session.get(Usuario,id)
    if not user or not user.ativo or user.perfil not in ("TECNICO","ADMINISTRADOR"): raise BusinessError("Técnico inválido.")
    return user
def salvar_diagnostico(id,uid,tech,diagnosis,entries):
    order=locked(OrdemServico,id); open_order(order)
    if order.status=="AGUARDANDO_TESTE": raise BusinessError("Retorne a OS para reparo antes de alterar diagnóstico.")
    if not diagnosis.strip(): raise BusinessError("Diagnóstico geral obrigatório.")
    technician(tech); order.tecnico_id=tech; order.diagnostico=diagnosis
    valid={i.id:i for i in order.itens}
    for entry in entries:
        item=valid.get(entry["id"])
        if not item: raise BusinessError("Item inválido.")
        if item.status=="CONCLUIDO": continue
        action=entry.get("acao",item.acao)
        if action not in ("REPARAR","SUBSTITUIR"): raise BusinessError("Ação inválida.")
        if item.solicitacao and (action!=item.acao or entry.get("peca_id")!=item.peca_id or decimal(entry.get("quantidade",item.quantidade))!=item.quantidade): raise BusinessError("Peça solicitada não pode ser alterada.")
        manual=str(entry.get("peca_manual",item.peca_manual or "")).strip()
        if action!="SUBSTITUIR": manual=""
        if len(manual)>180: raise BusinessError("Peça manual deve ter até 180 caracteres.")
        if manual:
            if not current_app.config.get("ALLOW_MANUAL_PARTS"): raise BusinessError("Lançamento manual de peça não está habilitado.")
            if entry.get("peca_id") or item.solicitacao: raise BusinessError("Use estoque ou lançamento manual; solicitação existente deve continuar pelo estoque.")
        item.peca_manual=manual or None
        item.acao=action; item.descricao_problema=entry.get("problema","")
        item.diagnostico=entry.get("diagnostico",""); item.causa_provavel=entry.get("causa","")
        item.observacoes=entry.get("observacoes","")
        if not item.solicitacao:
            part_id=entry.get("peca_id")
            if part_id:
                part=db.session.get(Peca,part_id)
                if not part or not part.ativo: raise BusinessError("Peça inválida.")
            item.peca_id=part_id if action=="SUBSTITUIR" else None
            item.quantidade=decimal(entry.get("quantidade",1),Decimal("0.01"))
    if current_app.config.get("PARTS_ON_DEMAND"):
        from .estoque_service import solicitar_peca
        for item in order.itens:
            if item.acao=="SUBSTITUIR" and item.status!="CONCLUIDO" and item.peca_id and not item.solicitacao:
                solicitar_peca(item.id,item.peca_id,item.quantidade,uid)
    order.atualizado_em=now()
    audit(uid,"DIAGNÓSTICO REALIZADO",order.id,order.maquina_id,order.manutencao_id,"ordem_servico")
def componente_disponivel(item):
    if item.solicitacao:
        return item.solicitacao.status=="ENTREGUE"
    return bool(current_app.config.get("ALLOW_MANUAL_PARTS") and item.peca_manual and item.peca_manual.strip() and not item.peca_id)

def iniciar_reparo(id,uid):
    order=locked(OrdemServico,id); open_order(order)
    if not order.diagnostico or not order.tecnico_id: raise BusinessError("Salve diagnóstico e técnico antes de iniciar reparo.")
    if order.status=="AGUARDANDO_TESTE": raise BusinessError("Use retornar para reparo após teste reprovado.")
    for item in order.itens:
        if item.acao=="SUBSTITUIR" and not componente_disponivel(item): raise BusinessError("Solicite e receba a peça pelo estoque ou registre o componente utilizado por lançamento manual habilitado.")
    order.data_inicio=order.data_inicio or now()
    change_status(order.manutencao,"EM_REPARO",uid,"REPARO INICIADO")
def concluir_item(id,uid,status="CONCLUIDO"):
    item=locked(OrdemServicoItem,id); order=locked(OrdemServico,item.ordem_servico_id); open_order(order)
    if order.status!="EM_REPARO": raise BusinessError("Inicie o reparo antes de atualizar serviços.")
    if item.status=="CONCLUIDO": raise BusinessError("Serviço já concluído.")
    if status not in ("PENDENTE","EM_REPARO","CONCLUIDO"): raise BusinessError("Status inválido.")
    if item.acao=="SUBSTITUIR" and not componente_disponivel(item): raise BusinessError("Peça ainda não entregue.")
    item.status=status
    if status=="CONCLUIDO": item.concluido_em=now(); item.concluido_por=uid
    order.atualizado_em=now()
    audit(uid,("REPARO FINALIZADO: " if status=="CONCLUIDO" else "Serviço "+status+": ")+item.componente,order.id,order.maquina_id,order.manutencao_id,"ordem_servico")
def adicionar_item(id,uid,name,action,qty,problem=""):
    order=locked(OrdemServico,id); open_order(order)
    if order.status=="AGUARDANDO_TESTE": raise BusinessError("Retorne para reparo antes de incluir serviço.")
    if not name.strip() or len(name)>180 or action not in ("REPARAR","SUBSTITUIR"): raise BusinessError("Componente ou ação inválidos.")
    db.session.add(OrdemServicoItem(ordem_servico_id=id,componente=name,acao=action,descricao_problema=problem,quantidade=decimal(qty,Decimal("0.01"))))
    order.atualizado_em=now()
    audit(uid,"Serviço manual adicionado: "+name,id,order.maquina_id,order.manutencao_id,"ordem_servico")
def enviar_teste(id,uid):
    order=locked(OrdemServico,id); open_order(order)
    if order.status!="EM_REPARO" or any(i.status!="CONCLUIDO" for i in order.itens): raise BusinessError("Conclua todos os serviços em reparo antes do teste.")
    change_status(order.manutencao,"AGUARDANDO_TESTE",uid,"MÁQUINA ENVIADA PARA TESTE")
def registrar_teste(id,uid,results,notes=""):
    order=locked(OrdemServico,id); open_order(order)
    if order.status!="AGUARDANDO_TESTE": raise BusinessError("Envie a máquina para teste primeiro.")
    for name in ("eletrico","funcionamento","carga","ventilacao","painel"):
        allowed=("APROVADO","REPROVADO","NAO_SE_APLICA") if name=="carga" else ("APROVADO","REPROVADO")
        if results.get(name) not in allowed: raise BusinessError("Resultado inválido para "+name)
    approved=all(results[n]=="APROVADO" for n in ("eletrico","funcionamento","ventilacao","painel")) and results["carga"]!="REPROVADO"
    test=TesteFinal(ordem_servico_id=id,usuario_id=uid,observacoes=notes,aprovado=approved,**results)
    db.session.add(test); order.atualizado_em=now()
    order.teste_final="; ".join(f"{key}: {value}" for key,value in results.items())+"\n"+notes
    audit(uid,"TESTE APROVADO" if approved else "TESTE REPROVADO",id,order.maquina_id,order.manutencao_id,"ordem_servico")
    return test
def retornar_reparo(id,uid):
    order=locked(OrdemServico,id); open_order(order)
    if order.status!="AGUARDANDO_TESTE" or not order.testes or order.testes[-1].aprovado: raise BusinessError("Retorno exige teste reprovado.")
    change_status(order.manutencao,"EM_REPARO",uid,"Teste reprovado: RETORNO PARA REPARO")
def finalizar_os(id,uid,tech,diagnosis,service,notes,hours,labor,finished=None):
    order=locked(OrdemServico,id); open_order(order)
    if order.status!="AGUARDANDO_TESTE" or any(i.status!="CONCLUIDO" for i in order.itens): raise BusinessError("Não é possível finalizar com serviço pendente.")
    if not order.testes or not order.testes[-1].aprovado: raise BusinessError("Último teste obrigatório deve estar aprovado.")
    last=order.testes[-1]
    latest_stage=max((e.inicio for e in order.manutencao.etapas if e.status=="AGUARDANDO_TESTE"),default=order.data_abertura)
    if last.criado_em<latest_stage: raise BusinessError("Realize novo teste após o reparo.")
    technician(tech)
    if not diagnosis.strip() or not service.strip(): raise BusinessError("Diagnóstico final e serviços realizados são obrigatórios.")
    hours=decimal(hours)
    if hours<order.maquina.horimetro: raise BusinessError("Horímetro não pode diminuir.")
    finished=finished or now()
    if finished<last.criado_em or finished>now(): raise BusinessError("Data final deve estar entre o último teste e o momento atual.")
    order.diagnostico=diagnosis; order.servico_realizado=service; order.observacoes=notes; order.tecnico_id=tech
    order.valor_pecas=sum(i.valor_total for i in order.itens); order.valor_mao_obra=decimal(labor); order.valor_total=order.valor_pecas+order.valor_mao_obra
    order.data_finalizacao=finished; order.manutencao.data_saida=finished
    order.manutencao.horimetro_final=hours; order.maquina.horimetro=hours
    change_status(order.manutencao,"FINALIZADA",uid,"OS FINALIZADA E MÁQUINA LIBERADA: "+order.numero_os)
    for period in order.manutencao.etapas:
        if period.fim is None: period.fim=finished

def reabrir_item(id,uid):
    item=locked(OrdemServicoItem,id); order=locked(OrdemServico,item.ordem_servico_id); open_order(order)
    if order.status!="EM_REPARO" or item.status!="CONCLUIDO": raise BusinessError("Reabertura exige item concluído em OS em reparo.")
    item.status="PENDENTE"; item.concluido_em=None; item.concluido_por=None
    audit(uid,"Serviço reaberto: "+item.componente,order.id,order.maquina_id,order.manutencao_id,"ordem_servico")
