from uuid import uuid4
from sqlalchemy import update
from app.extensions import db
from app.models import *
from app.utils.time import now
from .common import *
from .equipamento_service import identificar_tipo
def criar_entrada(machine_id,uid,entered,hours,defect,visual="",notes=""):
    machine=locked(Maquina,machine_id)
    if not machine.ativo or machine.status not in ("DISPONIVEL","EM_MANUTENCAO"): raise BusinessError("Máquina indisponível para nova entrada.")
    if db.session.scalar(db.select(Manutencao.id).where(Manutencao.maquina_id==machine_id,Manutencao.status.notin_(["FINALIZADA","CANCELADA"]))): raise BusinessError("Já existe manutenção ativa para esta máquina.")
    if entered>now(): raise BusinessError("Entrada não pode estar no futuro.")
    tipo=identificar_tipo(machine)
    modelo=locked(ModeloChecklist,tipo.modelo_checklist.id)
    db.session.expire(modelo,["itens"])
    if not any(i.ativo for i in modelo.itens): raise BusinessError("Modelo sem itens ativos.")
    hours=decimal(hours)
    if hours<machine.horimetro: raise BusinessError("Horímetro não pode diminuir.")
    if not defect.strip(): raise BusinessError("Informe o defeito relatado.")
    changed=db.session.execute(update(Maquina).where(Maquina.id==machine_id,Maquina.status==machine.status,Maquina.ativo.is_(True)).values(status="AGUARDANDO_CHECKLIST",horimetro=hours))
    if changed.rowcount!=1: raise BusinessError("Máquina alterada por outra operação.")
    maintenance=Manutencao(numero_manutencao="TMP-"+uuid4().hex,maquina_id=machine_id,data_entrada=entered,horimetro_entrada=hours,defeito_relatado=defect,condicao_visual=visual,responsavel_id=uid,observacoes=notes)
    db.session.add(maintenance); db.session.flush()
    maintenance.numero_manutencao=f"MAN-{entered.year}-{maintenance.id:06d}"
    checklist=Checklist(manutencao_id=maintenance.id,modelo_id=modelo.id,tipo_nome=tipo.nome); db.session.add(checklist); db.session.flush()
    for item in modelo.itens:
        if item.ativo:
            db.session.add(ChecklistItem(checklist_id=checklist.id,componente=item.componente,categoria=item.categoria.nome,descricao=item.descricao,obrigatorio=item.obrigatorio,ordem=item.ordem,ativo=item.ativo))
    db.session.add(EventoStatus(manutencao_id=maintenance.id,status="AGUARDANDO_CHECKLIST",inicio=entered))
    audit(uid,"MÁQUINA RECEBIDA PARA MANUTENÇÃO: "+maintenance.numero_manutencao,maintenance.id,machine_id,maintenance.id,"manutencao")
    return maintenance
def cancelar_manutencao(id,uid,reason):
    maintenance=locked(Manutencao,id)
    if maintenance.status in ("FINALIZADA","CANCELADA") or not reason.strip(): raise BusinessError("Informe motivo para cancelar uma manutenção ativa.")
    if maintenance.ordem:
        for item in maintenance.ordem.itens:
            if item.solicitacao and item.solicitacao.status not in ("ENTREGUE","CANCELADA"): item.solicitacao.status="CANCELADA"
    maintenance.observacoes=(maintenance.observacoes or "")+"\nCancelamento: "+reason
    change_status(maintenance,"CANCELADA",uid,"Manutenção cancelada; máquina retida na oficina. "+reason)
    maintenance.data_saida=now()
    for period in maintenance.etapas:
        if period.fim is None: period.fim=now()
