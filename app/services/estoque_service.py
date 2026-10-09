from sqlalchemy import update
from flask import current_app
from app.extensions import db
from app.models import *
from app.utils.time import now
from .common import *
def movimentar(peca_id,tipo,qty,uid,notes="",order=None,solicitacao=None):
    if tipo not in ("ENTRADA","AJUSTE","DEVOLUCAO","SAIDA_OS"): raise BusinessError("Movimentação inválida.")
    if tipo=="SAIDA_OS" and (not order or not solicitacao): raise BusinessError("Saída para OS exige solicitação e ordem.")
    qty=decimal(qty,0 if tipo=="AJUSTE" else Decimal("0.01"))
    part=locked(Peca,peca_id)
    if not part.ativo: raise BusinessError("Peça inativa.")
    before=part.quantidade_estoque
    after=qty if tipo=="AJUSTE" else before+(-qty if tipo=="SAIDA_OS" else qty)
    if after<0: raise BusinessError("Estoque insuficiente.")
    changed=db.session.execute(update(Peca).where(Peca.id==part.id,Peca.quantidade_estoque==before).values(quantidade_estoque=after))
    if changed.rowcount!=1: raise BusinessError("Saldo alterado por outra operação. Tente novamente.")
    movement=MovimentacaoEstoque(peca_id=part.id,tipo=tipo,quantidade=abs(after-before),estoque_anterior=before,estoque_posterior=after,usuario_id=uid,observacao=notes,ordem_servico_id=order,solicitacao_id=solicitacao)
    db.session.add(movement)
    audit(uid,f"Baixa de estoque: {part.codigo}" if tipo=="SAIDA_OS" else f"Estoque {tipo}: {part.codigo}",part.id,entity="peca",description=f"{before} -> {after}. {notes}")
    return movement
def solicitar_peca(item_id,peca_id,qty,uid):
    item=locked(OrdemServicoItem,item_id); order=locked(OrdemServico,item.ordem_servico_id); open_order(order)
    if order.status not in ("AGUARDANDO_DIAGNOSTICO","ABERTA","AGUARDANDO_PECA","EM_REPARO"): raise BusinessError("Etapa não permite solicitar peças.")
    if item.acao!="SUBSTITUIR" or item.status=="CONCLUIDO": raise BusinessError("Somente substituição pendente pode solicitar peça.")
    if item.solicitacao and item.solicitacao.status!="CANCELADA": raise BusinessError("Já existe solicitação para este item.")
    if item.peca_manual: raise BusinessError("Remova o lançamento manual no diagnóstico antes de solicitar peça do estoque.")
    part=locked(Peca,peca_id); quantity=decimal(qty,Decimal("0.01"))
    if not part.ativo: raise BusinessError("Peça inativa.")
    item.peca_id=part.id; item.quantidade=quantity; item.status="AGUARDANDO_PECA"
    request=item.solicitacao or SolicitacaoPeca(item=item)
    request.peca_id=part.id; request.quantidade=quantity; request.solicitante_id=uid; request.data_solicitacao=now()
    request.status="SOLICITADA" if current_app.config.get("PARTS_ON_DEMAND") or part.quantidade_estoque>=quantity else "SEM_ESTOQUE"
    db.session.add(request)
    change_status(order.manutencao,"AGUARDANDO_PECA",uid,"PEÇA SOLICITADA: "+part.descricao)
    return request
def atualizar_solicitacao(id,status,uid):
    request=locked(SolicitacaoPeca,id); order=locked(OrdemServico,request.item.ordem_servico_id); open_order(order)
    if request.status in ("ENTREGUE","CANCELADA"): raise BusinessError("Solicitação já encerrada.")
    if status not in ("SEPARADA","SEM_ESTOQUE","CANCELADA"): raise BusinessError("Status inválido.")
    if status=="SEPARADA" and request.peca.quantidade_estoque<request.quantidade: raise BusinessError("Estoque insuficiente para separar.")
    request.status=status
    audit(uid,"Solicitação "+status,request.id,order.maquina_id,order.manutencao_id,"solicitacao_peca")
def entregar_peca(id,uid):
    request=locked(SolicitacaoPeca,id); order=locked(OrdemServico,request.item.ordem_servico_id); open_order(order)
    if request.status in ("ENTREGUE","CANCELADA"): raise BusinessError("Solicitação já encerrada; baixa duplicada bloqueada.")
    if db.session.scalar(db.select(MovimentacaoEstoque.id).where(MovimentacaoEstoque.solicitacao_id==id)): raise BusinessError("Peça já entregue.")
    part=locked(Peca,request.peca_id)
    if current_app.config.get("PARTS_ON_DEMAND"):
        movimentar(part.id,"ENTRADA",request.quantidade,uid,"Recebimento sob demanda para "+order.numero_os,order.id)
        db.session.flush()
        db.session.refresh(part)
    movimentar(part.id,"SAIDA_OS",request.quantidade,uid,"Entrega de peça para "+order.numero_os,order.id,request.id)
    request.status="ENTREGUE"; request.data_entrega=now(); request.entregue_por=uid
    item=request.item; item.status="PENDENTE"; item.valor_unitario=part.custo_unitario; item.valor_total=part.custo_unitario*request.quantidade
    db.session.flush()
    order.valor_pecas=sum(i.valor_total for i in order.itens); order.valor_total=order.valor_pecas+order.valor_mao_obra
    pending=db.session.scalar(db.select(SolicitacaoPeca.id).join(OrdemServicoItem).where(OrdemServicoItem.ordem_servico_id==order.id,SolicitacaoPeca.status.notin_(["ENTREGUE","CANCELADA"])))
    if not pending: change_status(order.manutencao,"AGUARDANDO_DIAGNOSTICO" if not order.diagnostico else "EM_REPARO",uid,"PEÇA ENTREGUE: "+part.descricao)
    else: audit(uid,"PEÇA ENTREGUE: "+part.descricao,request.id,order.maquina_id,order.manutencao_id,"solicitacao_peca")
