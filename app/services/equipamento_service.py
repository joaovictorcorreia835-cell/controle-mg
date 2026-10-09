import json
from pathlib import Path
from app.extensions import db
from app.models import TipoEquipamento, CategoriaChecklist, ModeloChecklist, ModeloChecklistItem, Maquina
from .common import BusinessError, audit
from uuid import uuid4

def equipamento_por_serie(tipo_id, serie, uid, patrimonio="", localizacao="", maquina_id=None):
    serie, patrimonio, localizacao = serie.strip(), patrimonio.strip(), localizacao.strip()
    if not serie or len(serie)>120:
        raise BusinessError("Digite o número de série, com até 120 caracteres.")
    if len(patrimonio)>60 or len(localizacao)>120:
        raise BusinessError("Patrimônio ou localização excede o tamanho permitido.")
    tipo=db.session.get(TipoEquipamento,tipo_id)
    if not tipo or not tipo.ativo: raise BusinessError("Selecione um tipo de equipamento ativo.")
    machine=db.session.scalar(db.select(Maquina).where(db.func.lower(Maquina.numero_serie)==serie.lower()).with_for_update())
    if maquina_id:
        selected=db.session.get(Maquina,maquina_id)
        if not selected or (machine and selected.id!=machine.id): raise BusinessError("O número de série pertence a outro equipamento.")
        if selected.numero_serie and selected.numero_serie.lower()!=serie.lower(): raise BusinessError("O número de série não corresponde ao equipamento selecionado.")
        machine=selected
    if machine:
        if not machine.ativo: raise BusinessError("Equipamento inativo. Solicite a revisão do cadastro.")
        if machine.tipo_equipamento_id!=tipo.id: raise BusinessError("O número de série já está cadastrado em outro tipo de equipamento.")
        if patrimonio and patrimonio!=machine.codigo_patrimonio: raise BusinessError("O patrimônio não corresponde ao cadastro desse número de série.")
        if not machine.numero_serie:
            machine.numero_serie=serie
            audit(uid,"Número de série registrado na entrada",machine.id,machine.id,entity="maquina")
        return machine
    if patrimonio and db.session.scalar(db.select(Maquina.id).where(Maquina.codigo_patrimonio==patrimonio)):
        raise BusinessError("Patrimônio já cadastrado. Confira o número de série do equipamento.")
    machine=Maquina(numero_serie=serie,codigo_patrimonio=patrimonio or "EQ-"+uuid4().hex[:12].upper(),modelo=tipo.nome,tipo=tipo.nome,tipo_equipamento_id=tipo.id,localizacao=localizacao or None)
    db.session.add(machine);db.session.flush()
    audit(uid,"Equipamento cadastrado na entrada por número de série",machine.id,machine.id,entity="maquina")
    return machine


def dados_iniciais():
    return json.loads((Path(__file__).parents[1] / "data" / "checklist_inicial_v1.json").read_text(encoding="utf-8"))


def cadastrar_modelos_iniciais():
    """Seed idempotente: nunca sobrescreve modelos editados ou itens desativados."""
    dados = dados_iniciais()
    categorias = {c.nome: c for c in db.session.scalars(db.select(CategoriaChecklist))}
    for nome in dados["categorias"]:
        if nome not in categorias:
            categorias[nome] = CategoriaChecklist(nome=nome)
            db.session.add(categorias[nome])
    db.session.flush()
    for spec in dados["tipos"]:
        tipo = db.session.scalar(db.select(TipoEquipamento).where(TipoEquipamento.nome == spec["nome"]))
        if tipo is not None:
            continue
        tipo = TipoEquipamento(nome=spec["nome"])
        modelo = ModeloChecklist(tipo=tipo)
        db.session.add_all([tipo, modelo])
        for item in spec["itens"]:
            valores = {k: v for k, v in item.items() if k != "categoria"}
            db.session.add(ModeloChecklistItem(modelo=modelo, categoria=categorias[item["categoria"]], **valores))
    db.session.flush()


def identificar_tipo(machine):
    if machine.tipo_equipamento_id:
        tipo = db.session.get(TipoEquipamento, machine.tipo_equipamento_id)
    else:
        # Compatibilidade com máquinas legadas: somente nomes conhecidos e prefixos de modelo.
        textos = [(machine.tipo or "").upper().strip(), (machine.modelo or "").upper().strip()]
        aliases = dados_iniciais().get("aliases", {})
        textos = [aliases.get(texto, texto) for texto in textos]
        tipos = db.session.scalars(db.select(TipoEquipamento)).all()
        matches = [t for t in tipos if any(texto == t.nome.upper() or texto.startswith(t.nome.upper() + " ") for texto in textos)]
        tipo = matches[0] if len(matches) == 1 else None
    if not tipo or not tipo.ativo:
        raise BusinessError("Selecione um tipo de equipamento ativo no cadastro da máquina antes de abrir a manutenção.")
    if not tipo.modelo_checklist or not any(i.ativo for i in tipo.modelo_checklist.itens):
        raise BusinessError("O tipo de equipamento não possui itens ativos no modelo de checklist.")
    return tipo
