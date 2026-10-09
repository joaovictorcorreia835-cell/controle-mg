from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image,KeepTogether
from app.extensions import db
from app.models import ConfiguracaoEmpresa
from app.utils.storage import upload_root
def generate_order(order):
    buffer=BytesIO(); styles=getSampleStyleSheet()
    styles["Normal"].fontSize=8; styles["Normal"].leading=12
    styles["Heading2"].keepWithNext=True
    styles["Heading1"].keepWithNext=True
    def p(value,style="Normal"): return Paragraph(escape(str(value if value is not None and value!="" else "-")).replace("\n","<br/>"),styles[style])
    def table(rows,widths,header=True):
        t=Table([[p(v) for v in row] for row in rows],colWidths=widths,repeatRows=1 if header else 0,splitInRow=1)
        t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#dbeafe") if header else colors.HexColor("#f1f5f9")),("GRID",(0,0),(-1,-1),.35,colors.HexColor("#cbd5e1")),("VALIGN",(0,0),(-1,-1),"TOP"),("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7)]))
        return t
    company=db.session.get(ConfiguracaoEmpresa,1)
    doc=SimpleDocTemplate(buffer,pagesize=A4,rightMargin=36,leftMargin=36,topMargin=36,bottomMargin=40)
    story=[]
    if company and company.logo:
        path=upload_root()/company.logo.removeprefix("uploads/")
        if path.exists(): story.append(Image(str(path),width=95,height=45,kind="proportional"))
    story += [p(company.nome_empresa or company.razao_social if company else "Controle MG","Title")]
    if company:
        story.append(p(company.razao_social))
        contact=" | ".join(filter(None,[company.cnpj,company.telefone,company.email]))
        address=" | ".join(filter(None,[company.endereco,company.cidade,company.estado]))
        if contact: story.append(p(contact))
        if address: story.append(p(address))
    story += [Spacer(1,12),p("ORDEM DE SERVIÇO","Heading1"),p(order.numero_os,"Heading2")]
    m=order.maquina; maintenance=order.manutencao
    data=[["Patrimônio",m.codigo_patrimonio,"Número de série",m.numero_serie],["Marca",m.marca,"Modelo",m.modelo],["Tipo",maintenance.checklist.tipo_nome or m.tipo,"Potência",m.potencia],["Horímetro",m.horimetro,"Status",order.status.replace("_"," ")],["Entrada",maintenance.data_entrada.strftime("%d/%m/%Y %H:%M"),"Finalização",order.data_finalizacao.strftime("%d/%m/%Y %H:%M") if order.data_finalizacao else "-"],["Manutenção",maintenance.numero_manutencao,"Técnico",order.tecnico.nome if order.tecnico else "-"]]
    story += [table(data,[75,170,80,198],False),Spacer(1,12),p("Defeito relatado","Heading2"),p(order.defeito_relatado),p("Checklist com problemas","Heading2")]
    rows=[["Componente","Condição","Observação","Quantidade"]]
    for i in maintenance.checklist.itens:
        if i.acao in ("REPARAR","SUBSTITUIR"): rows.append([i.componente,i.acao,i.observacao,i.quantidade])
    story += [table(rows,[135,85,243,60]),p("Diagnóstico","Heading2"),p(order.diagnostico),p("Serviços","Heading2")]
    rows=[["Componente","Problema / Causa","Ação","Peça","Qtd.","Status"]]
    for i in order.itens: rows.append([i.componente,"\n".join(filter(None,[i.descricao_problema,i.diagnostico,i.causa_provavel])),i.acao,i.peca.descricao if i.peca else (i.peca_manual or "-"),i.quantidade,i.status.replace("_"," ")])
    story += [table(rows,[95,145,65,105,35,78]),p("Peças utilizadas","Heading2")]
    rows=[["Código / Peça","Quantidade","Custo unitário","Custo total"]]
    for i in order.itens:
        if i.solicitacao and i.solicitacao.status=="ENTREGUE": rows.append([i.peca.codigo+" / "+i.peca.descricao,i.quantidade,f"R$ {i.valor_unitario:.2f}",f"R$ {i.valor_total:.2f}"])
        elif i.acao=="SUBSTITUIR" and i.peca_manual and i.status=="CONCLUIDO": rows.append([i.peca_manual+" (lançamento manual)",i.quantidade,"Não informado","Não informado"])
    story += [table(rows,[260,60,100,103])]
    test_story=[p("Testes realizados","Heading2")]
    for test in order.testes:
        test_story += [p(test.criado_em.strftime("%d/%m/%Y %H:%M")+" - "+("APROVADO" if test.aprovado else "REPROVADO"))]
        for label,value in [("Elétrico",test.eletrico),("Funcionamento",test.funcionamento),("Sob carga",test.carga),("Ventilação",test.ventilacao),("Painel",test.painel)]:
            test_story.append(p(label+": "+value.replace("_"," ")))
        test_story.append(p(test.observacoes))
    if not order.testes: test_story.append(p("Ainda não realizado"))
    story.append(KeepTogether(test_story))
    story += [p("Serviço executado","Heading2"),p(order.servico_realizado),p("Observações","Heading2"),p(order.observacoes),Spacer(1,12),p(f"Custo interno: peças R$ {order.valor_pecas:.2f} | mão de obra R$ {order.valor_mao_obra:.2f} | total R$ {order.valor_total:.2f}"),Spacer(1,18)]
    story.append(KeepTogether([p("Técnico responsável: "+(order.tecnico.nome if order.tecnico else "-")),Spacer(1,20),p("TÉCNICO: __________________________________________"),Spacer(1,20),p("RESPONSÁVEL: ______________________________________"),Spacer(1,15),p("Data: ____/____/____")]))
    def footer(canvas,doc):
        canvas.setFont("Helvetica",8); canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(36,23,order.numero_os); canvas.drawRightString(A4[0]-36,23,f"Página {doc.page}")
    doc.build(story,onFirstPage=footer,onLaterPages=footer); buffer.seek(0); return buffer
