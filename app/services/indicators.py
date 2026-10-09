from collections import Counter
from app.utils.time import now
def avg(values): return sum(values)/len(values) if values else 0
def hours(maintenance): return ((maintenance.data_saida or now())-maintenance.data_entrada).total_seconds()/3600
def waiting(maintenance):
    return sum(((p.fim or now())-p.inicio).total_seconds()/3600 for p in maintenance.etapas if p.status=="AGUARDANDO_PECA")
def summarize(maintenances,orders):
    closed=[m for m in maintenances if m.status=="FINALIZADA"]
    used=Counter()
    for order in orders:
        for item in order.itens:
            if item.solicitacao and item.solicitacao.status=="ENTREGUE" and item.peca: used[item.peca.descricao]+=float(item.quantidade)
    defects=Counter(m.defeito_relatado.strip().lower() for m in maintenances)
    machines=Counter(m.maquina.codigo_patrimonio for m in maintenances)
    return dict(average_hours=avg([hours(m) for m in closed]),waiting_hours=avg([waiting(m) for m in maintenances if any(p.status=="AGUARDANDO_PECA" for p in m.etapas)]),average_cost=avg([float(o.valor_total) for o in orders if o.status=="FINALIZADA"]),closed=len([o for o in orders if o.status=="FINALIZADA"]),stopped=sum(m.status not in ("FINALIZADA","CANCELADA") for m in maintenances),used=used,defects=defects,machines=machines)
