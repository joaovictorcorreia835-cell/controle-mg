import os
import click
from datetime import timedelta
from app.extensions import db
from app.models import *
from app.utils.time import now
from app.services.operations import *
def register(app):
    @app.cli.command("init-production")
    def init_production():
        """Initialize a clean installation without demo records or password resets."""
        from app.services.equipamento_service import cadastrar_modelos_iniciais
        if not db.session.scalar(db.select(Usuario.id)):
            password = os.getenv("INITIAL_ADMIN_PASSWORD", "")
            email = os.getenv("INITIAL_ADMIN_EMAIL", "adm@controlemg.local").strip().lower()
            if len(password) < 10 or "@" not in email:
                raise click.ClickException("Configure INITIAL_ADMIN_EMAIL e INITIAL_ADMIN_PASSWORD com pelo menos 10 caracteres.")
            user = Usuario(nome="Administrador Controle MG", email=email, perfil="ADMINISTRADOR", ativo=True, trocar_senha=True)
            user.set_password(password)
            db.session.add(user)
        if not db.session.get(ConfiguracaoEmpresa, 1):
            db.session.add(ConfiguracaoEmpresa(id=1, nome_empresa="MG Soldas"))
        cadastrar_modelos_iniciais()
        db.session.commit()
        click.echo("Instalação inicializada sem dados demonstrativos; acessos existentes preservados.")

    @app.cli.command("create-admin")
    @click.option("--email",prompt=True)
    @click.option("--nome",default="Administrador")
    @click.password_option()
    def create_admin(email,nome,password):
        if len(password)<10: raise click.ClickException("Use pelo menos 10 caracteres.")
        if db.session.scalar(db.select(Usuario.id).where(Usuario.email==email.lower())): raise click.ClickException("Email já existe.")
        user=Usuario(nome=nome,email=email.lower(),perfil="ADMINISTRADOR",trocar_senha=True)
        user.set_password(password); db.session.add(user); db.session.commit()
        click.echo("Administrador criado. Troca de senha exigida no login.")
    @app.cli.command("seed")
    def seed():
        if db.session.scalar(db.select(Usuario.id)): raise click.ClickException("Seed exige banco vazio; não modifica dados existentes.")
        password=os.getenv("SEED_ADMIN_PASSWORD")
        if not password or len(password)<8: raise click.ClickException("Defina SEED_ADMIN_PASSWORD apenas para desenvolvimento.")
        admin=Usuario(nome="Administrador",email=os.getenv("SEED_ADMIN_EMAIL","admin@admin.com"),perfil="ADMINISTRADOR")
        admin.set_password(password); db.session.add(admin); db.session.flush()
        db.session.add(ConfiguracaoEmpresa(id=1,nome_empresa="Controle MG",razao_social="Controle MG - Oficina",alerta_dias=7))
        from app.services.equipamento_service import cadastrar_modelos_iniciais
        cadastrar_modelos_iniciais()
        tipos=db.session.scalars(db.select(TipoEquipamento).order_by(TipoEquipamento.id)).all()
        for i in range(1,16):
            m=Maquina(codigo_patrimonio=f"MS-{i:04d}",numero_serie=f"SERIE-{i:05d}",marca=["Lincoln","ESAB","Miller"][i%3],modelo=["Inversora 250","MIG 350","TIG 200"][i%3],tipo=tipos[(i-1)%len(tipos)].nome,tipo_equipamento_id=tipos[(i-1)%len(tipos)].id,tensao="220V",potencia="350 A",localizacao="Oficina A",horimetro=i*50,ano=2024)
            db.session.add(m); db.session.flush(); audit(admin.id,"Máquina cadastrada",m.id,m.id,entity="maquina")
        for i in range(1,21):
            part=Peca(codigo=f"P-{i:04d}",descricao=["Cabo de solda","Ventilador","Conector","Placa eletrônica","Tocha MIG"][i%5]+f" {i}",estoque_minimo=5,custo_unitario=i*12,unidade="UN",localizacao="Prateleira B")
            db.session.add(part); db.session.flush(); movimentar(part.id,"ENTRADA",2 if i==1 else 20,admin.id,"Saldo inicial fictício")
        db.session.flush(); machines=db.session.scalars(db.select(Maquina).order_by(Maquina.id)).all()
        for idx in range(7):
            m=machines[idx]
            maintenance=criar_entrada(m.id,admin.id,now()-timedelta(days=idx+1),m.horimetro,["Cabo danificado","Ventilador parado","Falha no painel"][idx%3],"Carcaça com marcas de uso")
            db.session.flush()
            if idx==0: continue
            items=maintenance.checklist.itens
            salvar_checklist(maintenance.id,[dict(id=items[2].id,acao="SUBSTITUIR",observacao="Isolação danificada",quantidade=1),dict(id=items[14].id,acao="REPARAR",observacao="Ventilador parado",quantidade=1)],admin.id)
            order=gerar_os(maintenance.id,admin.id); db.session.flush()
            if idx==1: continue
            salvar_diagnostico(order.id,admin.id,admin.id,"Cabo e ventilação precisam de reparo",[],)
            substitution=next(i for i in order.itens if i.acao=="SUBSTITUIR")
            request=solicitar_peca(substitution.id,1 if idx==2 else 2,1,admin.id); db.session.flush()
            if idx==2: continue
            if idx==3:
                # Pending item without parts: workshop repair example.
                entregar_peca(request.id,admin.id); iniciar_reparo(order.id,admin.id)
                continue
            entregar_peca(request.id,admin.id); iniciar_reparo(order.id,admin.id)
            for item in order.itens: concluir_item(item.id,admin.id)
            enviar_teste(order.id,admin.id)
            if idx==4: continue
            registrar_teste(order.id,admin.id,dict(eletrico="APROVADO",funcionamento="APROVADO",carga="APROVADO",ventilacao="APROVADO",painel="APROVADO"),"Teste funcional OK"); db.session.flush()
            finalizar_os(order.id,admin.id,admin.id,"Falha corrigida","Cabo substituído e ventilador reparado","Demonstração",m.horimetro+1,80)
        db.session.commit()
        click.echo("Seed criado: 15 máquinas, 20 peças, 5 manutenções ativas e 2 finalizadas. Troca de senha obrigatória.")
