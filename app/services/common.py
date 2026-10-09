from decimal import Decimal,InvalidOperation
from app.extensions import db
from app.models import Auditoria,HistoricoMaquina,EventoStatus
from app.utils.time import now
class BusinessError(ValueError): pass
def decimal(value,minimum=0):
    try: result=Decimal(str(value).replace(",","."))
    except (InvalidOperation,TypeError): raise BusinessError("Valor numérico inválido.")
    if not result.is_finite() or result<minimum or result.as_tuple().exponent < -2 or result>Decimal("9999999999.99"): raise BusinessError("Informe valor válido, com até duas casas decimais.")
    return result
def locked(model,id):
    obj=db.session.execute(db.select(model).where(model.id==id).with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
    if not obj: raise BusinessError("Registro não encontrado.")
    return obj
def audit(uid,action,record,machine=None,maintenance=None,entity="operacao",description=""):
    db.session.add(Auditoria(usuario_id=uid,acao=action[:250],entidade=entity,entidade_id=int(record),descricao=description or action))
    if machine: db.session.add(HistoricoMaquina(maquina_id=machine,manutencao_id=maintenance,usuario_id=uid,evento=action[:250]))
def change_status(maintenance,status,uid,event):
    if maintenance.status != status:
        for period in maintenance.etapas:
            if period.fim is None: period.fim=now()
        db.session.add(EventoStatus(manutencao_id=maintenance.id,status=status))
    maintenance.status=status; maintenance.atualizado_em=now()
    maintenance.maquina.status="DISPONIVEL" if status=="FINALIZADA" else "EM_MANUTENCAO" if status=="CANCELADA" else status
    if maintenance.ordem:
        maintenance.ordem.status="ABERTA" if status=="EM_MANUTENCAO" else status
        maintenance.ordem.atualizado_em=now()
        if status=="EM_REPARO": maintenance.ordem.data_inicio=maintenance.ordem.data_inicio or now()
    audit(uid,event,maintenance.id,maintenance.maquina_id,maintenance.id,"manutencao")
def open_order(order):
    if order.status in ("FINALIZADA","CANCELADA"): raise BusinessError("OS encerrada.")
