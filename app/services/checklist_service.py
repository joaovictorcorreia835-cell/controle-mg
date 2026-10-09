from app.extensions import db
from app.models import *
from app.utils.time import now
from .common import *
def salvar_checklist(maintenance_id,entries,uid):
    maintenance=locked(Manutencao,maintenance_id)
    if maintenance.status in ("FINALIZADA","CANCELADA"): raise BusinessError("Manutenção encerrada.")
    order=maintenance.ordem
    if order and (order.data_inicio or order.testes or any(i.status!="PENDENTE" or i.solicitacao for i in order.itens)): raise BusinessError("Checklist bloqueado após diagnóstico operacional ou solicitação de peças.")
    checklist=maintenance.checklist; valid={i.id:i for i in checklist.itens}
    supplied={e.get("id"):e for e in entries}
    for item in checklist.itens:
        if item.obrigatorio and not item.respondido and (item.id not in supplied or supplied[item.id].get("acao") not in ("OK","REPARAR","SUBSTITUIR","NAO_SE_APLICA")):
            raise BusinessError("Responda o componente obrigatório: "+item.componente)
    for entry in entries:
        item=valid.get(entry.get("id"))
        if item is None:
            if entry.get("id"): raise BusinessError("Item não pertence ao checklist.")
            name=entry.get("componente","").strip()
            if not name: continue
            if len(name)>180: raise BusinessError("Nome de componente muito longo.")
            item=ChecklistItem(checklist_id=checklist.id,componente=name); db.session.add(item)
        if entry["acao"] not in ("OK","REPARAR","SUBSTITUIR","NAO_SE_APLICA"): raise BusinessError("Ação inválida.")
        item.respondido=True; item.acao=entry["acao"]; item.observacao=entry.get("observacao","")
        item.quantidade=decimal(entry.get("quantidade",1),Decimal("0.01"))
        if entry.get("foto"): item.foto=entry["foto"]
    checklist.salvo_em=now(); checklist.usuario_id=uid
    db.session.flush(); db.session.expire(checklist,["itens"])
    audit(uid,"CHECKLIST REALIZADO",maintenance.id,maintenance.maquina_id,maintenance.id,"checklist")
    if order:
        from .os_service import sincronizar_itens
        sincronizar_itens(order)
    else: change_status(maintenance,"AGUARDANDO_DIAGNOSTICO",uid,"Checklist finalizado; gerar ordem de serviço")
    config=db.session.get(ConfiguracaoEmpresa,1)
    if config and config.gerar_os_automaticamente and not order:
        from .os_service import gerar_os
        order=gerar_os(maintenance.id,uid)
    return order
