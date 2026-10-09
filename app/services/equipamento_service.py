import json
from pathlib import Path
from app.extensions import db
from app.models import TipoEquipamento, CategoriaChecklist, ModeloChecklist, ModeloChecklistItem
from .common import BusinessError


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
