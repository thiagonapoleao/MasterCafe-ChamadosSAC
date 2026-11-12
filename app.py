import os
import json
from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlalchemy import (
    create_engine, Column, Integer, String, Numeric,
    Text, func, desc, text, inspect
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# ==============================================================================
# INICIALIZAÇÃO FASTAPI, STATIC FILES & JINJA2 TEMPLATES
# ==============================================================================
app = FastAPI(title="Dashboard Executivo - Gestão SAC")

if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

# ==============================================================================
# CONFIGURAÇÃO DE BANCO DE DADOS (SUPABASE POSTGRESQL POOLER)
# ==============================================================================
RAW_DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres.asptoykwjnpxwvnixslw:napoleao140205@aws-1-us-east-1.pooler.supabase.com:6543/postgres"
).strip()

if RAW_DB_URL.startswith("postgres://"):
    RAW_DB_URL = RAW_DB_URL.replace("postgres://", "postgresql://", 1)

try:
    import psycopg  # psycopg v3
    DATABASE_URL = RAW_DB_URL.replace("postgresql://", "postgresql+psycopg://", 1)
    CONNECT_ARGS = {
        "connect_timeout": 30,
        "sslmode": "require",
        "prepare_threshold": None
    }
except ImportError:
    DATABASE_URL = RAW_DB_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
    CONNECT_ARGS = {
        "connect_timeout": 30,
        "sslmode": "require"
    }

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=5,
    max_overflow=10,
    connect_args=CONNECT_ARGS
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ==============================================================================
# MODELOS DE DADOS
# ==============================================================================
class ChamadoModel(Base):
    __tablename__ = "chamados"

    id = Column(Integer, primary_key=True, index=True)
    chamado = Column(String(50), unique=True, index=True, nullable=False)
    data = Column(String(50), index=True)
    cliente = Column(String(150), index=True)
    local_interno = Column(String(150))
    cidade = Column(String(100), index=True)
    descricao = Column(String(255))
    produto = Column(String(50), index=True)
    data_transacao = Column(String(50))
    hora_transacao = Column(String(20))
    valor = Column(Numeric(10, 2), default=0.0)
    nome_sobrenome = Column(String(150))
    celular = Column(String(50))
    problemas = Column(String(255))
    forma_pgto = Column(String(100))
    reembolso = Column(String(100))
    pix = Column(String(150))
    atendente = Column(String(100), index=True)
    reembolso_realizado = Column(String(10), default="Não")
    financeiro_responsavel = Column(String(100))
    observacao = Column(Text)
    data_hora_lancamento = Column(String(50))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "linha": self.id,
            "chamado": self.chamado,
            "data": self.data,
            "cliente": self.cliente,
            "local_interno": self.local_interno,
            "localInterno": self.local_interno,
            "cidade": self.cidade,
            "descricao": self.descricao,
            "produto": self.produto,
            "data_transacao": self.data_transacao,
            "dataTransacao": self.data_transacao,
            "hora_transacao": self.hora_transacao,
            "horaTransacao": self.hora_transacao,
            "valor": float(self.valor) if self.valor is not None else 0.0,
            "nome_sobrenome": self.nome_sobrenome,
            "nomeSobrenome": self.nome_sobrenome,
            "celular": self.celular,
            "problemas": self.problemas,
            "forma_pgto": self.forma_pgto,
            "formaPgto": self.forma_pgto,
            "reembolso": self.reembolso,
            "pix": self.pix,
            "atendente": self.atendente,
            "reembolso_realizado": self.reembolso_realizado,
            "reembolsoRealizado": self.reembolso_realizado,
            "financeiro_responsavel": self.financeiro_responsavel,
            "financeiroResponsavel": self.financeiro_responsavel,
            "observacao": self.observacao,
            "data_hora_lancamento": self.data_hora_lancamento,
            "dataHoraLancamento": self.data_hora_lancamento
        }


class ClienteModel(Base):
    __tablename__ = "cadastro_clientes"

    id = Column(Integer, primary_key=True, index=True)
    cliente = Column(String(150), nullable=False, index=True)
    local = Column(String(150))
    local_interno = Column(String(150))
    maquina = Column(String(100))
    modelo_maquina = Column(String(100))
    filial_responsavel = Column(String(100), index=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "linha": self.id,
            "cliente": self.cliente,
            "local": self.local,
            "localInterno": self.local_interno,
            "local_interno": self.local_interno,
            "maquina": self.maquina,
            "modeloMaquina": self.modelo_maquina,
            "modelo_maquina": self.modelo_maquina,
            "filialResponsavel": self.filial_responsavel,
            "filial_responsavel": self.filial_responsavel,
            "cidade": self.filial_responsavel
        }


class UsuarioModel(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    usuario = Column(String(100), unique=True, index=True, nullable=False)
    senha = Column(String(100), nullable=False)
    nome = Column(String(150), nullable=False)
    acesso = Column(String(50), default="Atendente")

    def to_dict(self) -> Dict[str, Any]:
        u = (self.usuario or "").strip()
        s = (self.senha or "").strip()
        n = (self.nome or "").strip()
        a = (self.acesso or "Atendente").strip()
        return {
            "id": self.id,
            "usuario": u,
            "Usuario": u,
            "login": u,
            "senha": s,
            "Senha": s,
            "nome": n,
            "Nome": n,
            "acesso": a,
            "Acesso": a,
            "perfil": a,
            "Perfil": a
        }

# ==============================================================================
# INICIALIZAÇÃO DE TABELAS, ÍNDICES E USUÁRIOS PADRÃO
# ==============================================================================
USUARIOS_FALLBACK = [
    {"usuario": "admin", "senha": "123", "nome": "Administrador Geral", "acesso": "Geral"},
    {"usuario": "atendente", "senha": "123", "nome": "Atendente SAC", "acesso": "Atendente"},
    {"usuario": "thiago", "senha": "123", "nome": "Thiago Napoleão", "acesso": "Geral"}
]

def inicializar_banco():
    """Cria tabelas, garante índices de performance e popula usuários iniciais se a tabela estiver vazia."""
    queries_indices = [
        "CREATE INDEX IF NOT EXISTS idx_chamados_cliente ON chamados (cliente);",
        "CREATE INDEX IF NOT EXISTS idx_chamados_data ON chamados (data);",
        "CREATE INDEX IF NOT EXISTS idx_chamados_atendente ON chamados (atendente);",
        "CREATE INDEX IF NOT EXISTS idx_chamados_produto ON chamados (produto);",
        "CREATE INDEX IF NOT EXISTS idx_chamados_cidade ON chamados (cidade);",
        "CREATE INDEX IF NOT EXISTS idx_chamados_chamado ON chamados (chamado);"
    ]
    try:
        Base.metadata.create_all(bind=engine)
        with engine.begin() as conn:
            for sql in queries_indices:
                conn.execute(text(sql))

        # Popula tabela de usuários caso esteja vazia
        db = SessionLocal()
        try:
            if db.query(func.count(UsuarioModel.id)).scalar() == 0:
                for u in USUARIOS_FALLBACK:
                    db.add(UsuarioModel(**u))
                db.commit()
        finally:
            db.close()

        print("✅ Banco de dados, índices e usuários verificados com sucesso.")
    except Exception as e:
        print(f"⚠️ Aviso na inicialização do banco: {e}")

inicializar_banco()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def carregar_lista_usuarios(db: Session) -> List[Dict[str, Any]]:
    """Busca usuários da tabela 'usuarios' no Supabase e garante fallback seguro."""
    try:
        usuarios_db = db.query(UsuarioModel).all()
        if usuarios_db:
            return [u.to_dict() for u in usuarios_db]
    except Exception as e:
        print(f"⚠️ Erro ao ler tabela usuarios (usando fallback): {e}")

    return [
        {
            "usuario": u["usuario"], "Usuario": u["usuario"], "login": u["usuario"],
            "senha": u["senha"], "Senha": u["senha"],
            "nome": u["nome"], "Nome": u["nome"],
            "acesso": u["acesso"], "Acesso": u["acesso"],
            "perfil": u["acesso"], "Perfil": u["acesso"]
        }
        for u in USUARIOS_FALLBACK
    ]

# ==============================================================================
# ROTA PRINCIPAL
# ==============================================================================
@app.get("/", response_class=HTMLResponse)
def index_page(request: Request, db: Session = Depends(get_db)):
    try:
        total_chamados = db.query(func.count(ChamadoModel.id)).scalar() or 0

        chamados_recentes = (
            db.query(ChamadoModel)
            .order_by(desc(ChamadoModel.id))
            .limit(300)
            .all()
        )
        lista_chamados = [c.to_dict() for c in chamados_recentes]

        clientes_db = db.query(ClienteModel).order_by(ClienteModel.cliente).all()
        lista_clientes = [cli.to_dict() for cli in clientes_db]

        lista_usuarios = carregar_lista_usuarios(db)

        descricoes_padrao = [
            "Café Expresso", "Café com Leite", "Cappuccino", "Mocaccino",
            "Chocolate Quente", "Chá", "Salgadinho", "Refrigerante", "Suco", "Água Mineral"
        ]
        problemas_padrao = [
            "Não liberou produto", "Cobrou e não liberou", "Produto gelado/frio",
            "Nota/Moeda presa", "Produto travado na mola", "Pagamento não reconhecido",
            "Máquina sem energia", "Outro"
        ]
        formas_pgto_padrao = [
            "Cartão de Débito", "Cartão de Crédito", "Pix", "Dinheiro/Moeda",
            "Crédito Remoto", "Voucher"
        ]

        ano_atual = datetime.now().year
        maior_seq = 0
        ultimo_chamado_ano = (
            db.query(ChamadoModel.chamado)
            .filter(ChamadoModel.chamado.like(f"SAC-{ano_atual}-%"))
            .order_by(desc(ChamadoModel.chamado))
            .first()
        )
        if ultimo_chamado_ano and ultimo_chamado_ano[0]:
            try:
                maior_seq = int(ultimo_chamado_ano[0].split("-")[-1])
            except ValueError:
                pass

        dados_sac_payload = {
            "chamados": lista_chamados,
            "cadastro_clientes": lista_clientes,
            "clientes": lista_clientes,
            "usuarios": lista_usuarios,
            "descricoes": descricoes_padrao,
            "produtos": descricoes_padrao,
            "problemas": problemas_padrao,
            "formas_pgt": formas_pgto_padrao,
            "formas_pagamento": formas_pgto_padrao,
            "maior_sac_ano": {str(ano_atual): maior_seq}
        }

        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "dados_sac_json": json.dumps(dados_sac_payload, default=str),
                "total_chamados_carregados": total_chamados,
                "logo_base64_src": ""
            }
        )

    except Exception as e:
        return HTMLResponse(
            content=f"""
            <div style="font-family: sans-serif; padding: 40px; text-align: center;">
                <h2>Erro ao carregar a aplicação</h2>
                <p style="color: #dc2626;">{str(e)}</p>
                <button onclick="window.location.reload()" style="padding: 10px 20px; background: #0284c7; color: white; border: none; border-radius: 8px; cursor: pointer;">
                    Tentar Novamente 🔄
                </button>
            </div>
            """,
            status_code=500
        )

# ==============================================================================
# ROTA DEDICADA DE LOGIN (CASO O FRONTEND FAÇA POST /api/login)
# ==============================================================================
@app.post("/api/login")
async def login_endpoint(request: Request, db: Session = Depends(get_db)):
    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"status": "error", "message": "Payload JSON inválido."})

    login_input = (body.get("usuario") or body.get("Usuario") or body.get("login") or "").strip().lower()
    senha_input = str(body.get("senha") or body.get("Senha") or body.get("password") or "").strip()

    usuarios = carregar_lista_usuarios(db)
    for u in usuarios:
        if u["usuario"].lower() == login_input and str(u["senha"]).strip() == senha_input:
            return {
                "status": "success",
                "message": "Login realizado com sucesso.",
                "user": u,
                "data": u
            }

    return JSONResponse(status_code=401, content={"status": "error", "message": "Usuário ou senha incorretos!"})

# ==============================================================================
# ROTA DE AÇÃO CENTRALIZADA (LOGIN, CHAMADOS, CLIENTES E USUÁRIOS)
# ==============================================================================
@app.post("/api/action")
async def handle_action(request: Request, db: Session = Depends(get_db)):
    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"status": "error", "message": "Payload JSON inválido."})

    action = (body.get("action") or body.get("acao") or "").lower().strip()
    tipo = (body.get("tipo") or "").lower().strip()

    try:
        # ----------------------------------------------------------------------
        # 0. LOGIN VIA /api/action
        # ----------------------------------------------------------------------
        if action == "login" or tipo == "login":
            login_input = (body.get("usuario") or body.get("Usuario") or body.get("login") or "").strip().lower()
            senha_input = str(body.get("senha") or body.get("Senha") or body.get("password") or "").strip()

            usuarios = carregar_lista_usuarios(db)
            for u in usuarios:
                if u["usuario"].lower() == login_input and str(u["senha"]).strip() == senha_input:
                    return {"status": "success", "message": "Login realizado com sucesso.", "user": u, "data": u}

            return JSONResponse(status_code=401, content={"status": "error", "message": "Usuário ou senha incorretos!"})

        # ----------------------------------------------------------------------
        # 1. EXCLUIR CHAMADO SAC
        # ----------------------------------------------------------------------
        elif action == "excluir" or tipo == "excluir_sac":
            num_chamado = body.get("chamado") or body.get("Chamado")
            item_id = body.get("id") or body.get("linha")

            chamado_obj = None
            if item_id and str(item_id).isdigit():
                chamado_obj = db.query(ChamadoModel).filter(ChamadoModel.id == int(item_id)).first()
            if not chamado_obj and num_chamado:
                chamado_obj = db.query(ChamadoModel).filter(ChamadoModel.chamado == num_chamado).first()

            if not chamado_obj:
                return JSONResponse(status_code=404, content={"status": "error", "message": f"Chamado '{num_chamado}' não encontrado."})

            db.delete(chamado_obj)
            db.commit()
            return {"status": "success", "message": f"Chamado {num_chamado} excluído com sucesso."}

        # ----------------------------------------------------------------------
        # 2. INSERIR OU EDITAR CHAMADO SAC
        # ----------------------------------------------------------------------
        elif action in ["inserir", "editar"]:
            num_chamado = (body.get("chamado") or body.get("Chamado") or "").strip()
            item_id = body.get("id") or body.get("linha")

            valor_bruto = body.get("valor") or body.get("Valor") or 0.0
            try:
                valor_float = float(str(valor_bruto).replace("R$", "").replace(".", "").replace(",", ".").strip())
            except ValueError:
                valor_float = 0.0

            if action == "editar":
                chamado_obj = None
                if item_id and str(item_id).isdigit():
                    chamado_obj = db.query(ChamadoModel).filter(ChamadoModel.id == int(item_id)).first()
                if not chamado_obj and num_chamado:
                    chamado_obj = db.query(ChamadoModel).filter(ChamadoModel.chamado == num_chamado).first()

                if not chamado_obj:
                    return JSONResponse(status_code=404, content={"status": "error", "message": f"Chamado '{num_chamado}' não encontrado para alteração."})

                chamado_obj.data = body.get("data") or body.get("Data") or chamado_obj.data
                chamado_obj.cliente = body.get("cliente") or body.get("Cliente") or chamado_obj.cliente
                chamado_obj.local_interno = body.get("local_interno") or body.get("Local Interno") or chamado_obj.local_interno
                chamado_obj.cidade = body.get("cidade") or body.get("Cidade") or chamado_obj.cidade
                chamado_obj.descricao = body.get("descricao") or body.get("Descrição") or chamado_obj.descricao
                chamado_obj.produto = body.get("produto") or body.get("Produto") or chamado_obj.produto
                chamado_obj.data_transacao = body.get("data_transacao") or body.get("Data da Transação") or chamado_obj.data_transacao
                chamado_obj.hora_transacao = body.get("hora_transacao") or body.get("Hora da Transação") or chamado_obj.hora_transacao
                chamado_obj.valor = valor_float
                chamado_obj.nome_sobrenome = body.get("nome_sobrenome") or body.get("Nome/Sobrenome") or chamado_obj.nome_sobrenome
                chamado_obj.celular = body.get("celular") or body.get("Celular") or chamado_obj.celular
                chamado_obj.problemas = body.get("problemas") or body.get("Problemas") or chamado_obj.problemas
                chamado_obj.forma_pgto = body.get("forma_pgto") or body.get("Forma de Pagamento") or chamado_obj.forma_pgto
                chamado_obj.reembolso = body.get("reembolso") or body.get("Reembolso") or chamado_obj.reembolso
                chamado_obj.pix = body.get("pix") or body.get("Pix - Reembolso") or chamado_obj.pix
                chamado_obj.reembolso_realizado = body.get("reembolso_realizado") or body.get("Reembolso Realizado") or "Não"
                chamado_obj.financeiro_responsavel = body.get("financeiro_responsavel") or body.get("Financeiro Responsavel") or ""
                chamado_obj.observacao = body.get("observacao") or body.get("Observação") or ""

                db.commit()
                db.refresh(chamado_obj)
                return {"status": "success", "message": "Chamado atualizado com sucesso.", "data": chamado_obj.to_dict()}

            else:  # Inserção
                if num_chamado:
                    existe = db.query(ChamadoModel).filter(ChamadoModel.chamado == num_chamado).first()
                    if existe:
                        ano = datetime.now().year
                        total_ano = db.query(func.count(ChamadoModel.id)).filter(ChamadoModel.chamado.like(f"SAC-{ano}-%")).scalar() or 0
                        num_chamado = f"SAC-{ano}-{str(total_ano + 1).zfill(4)}"

                novo_chamado = ChamadoModel(
                    chamado=num_chamado,
                    data=body.get("data") or body.get("Data") or datetime.now().strftime("%d/%m/%Y"),
                    cliente=body.get("cliente") or body.get("Cliente") or "",
                    local_interno=body.get("local_interno") or body.get("Local Interno") or "",
                    cidade=body.get("cidade") or body.get("Cidade") or "",
                    descricao=body.get("descricao") or body.get("Descrição") or "",
                    produto=body.get("produto") or body.get("Produto") or "",
                    data_transacao=body.get("data_transacao") or body.get("Data da Transação") or "",
                    hora_transacao=body.get("hora_transacao") or body.get("Hora da Transação") or "",
                    valor=valor_float,
                    nome_sobrenome=body.get("nome_sobrenome") or body.get("Nome/Sobrenome") or "",
                    celular=body.get("celular") or body.get("Celular") or "",
                    problemas=body.get("problemas") or body.get("Problemas") or "",
                    forma_pgto=body.get("forma_pgto") or body.get("Forma de Pagamento") or "",
                    reembolso=body.get("reembolso") or body.get("Reembolso") or "",
                    pix=body.get("pix") or body.get("Pix - Reembolso") or "",
                    atendente=body.get("atendente") or body.get("Atendente") or "Operador",
                    reembolso_realizado=body.get("reembolso_realizado") or body.get("Reembolso Realizado") or "Não",
                    financeiro_responsavel=body.get("financeiro_responsavel") or body.get("Financeiro Responsavel") or "",
                    observacao=body.get("observacao") or body.get("Observação") or "",
                    data_hora_lancamento=body.get("data_hora_lancamento") or body.get("Data/Hora do lançamento") or datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                )

                db.add(novo_chamado)
                db.commit()
                db.refresh(novo_chamado)
                return {"status": "success", "message": "Chamado cadastrado com sucesso.", "data": novo_chamado.to_dict()}

        # ----------------------------------------------------------------------
        # 3. CADASTRO DE CLIENTES (INSERT, EDIT, DELETE)
        # ----------------------------------------------------------------------
        elif action in ["inserir_cliente", "editar_cliente", "excluir_cliente"] or tipo == "cadastro_cliente":
            if action == "excluir_cliente":
                item_id = body.get("id") or body.get("linha")
                cli_nome = body.get("Cliente") or body.get("cliente")
                
                cli_obj = None
                if item_id and str(item_id).isdigit():
                    cli_obj = db.query(ClienteModel).filter(ClienteModel.id == int(item_id)).first()
                if not cli_obj and cli_nome:
                    cli_obj = db.query(ClienteModel).filter(ClienteModel.cliente == cli_nome).first()

                if not cli_obj:
                    return JSONResponse(status_code=404, content={"status": "error", "message": "Cliente não localizado para exclusão."})

                db.delete(cli_obj)
                db.commit()
                return {"status": "success", "message": "Cliente excluído com sucesso."}

            elif action == "editar_cliente":
                item_id = body.get("id") or body.get("linha")
                cli_obj = db.query(ClienteModel).filter(ClienteModel.id == int(item_id)).first() if item_id else None

                if not cli_obj:
                    return JSONResponse(status_code=404, content={"status": "error", "message": "Registro de cliente não encontrado para edição."})

                cli_obj.cliente = body.get("Cliente") or body.get("cliente") or cli_obj.cliente
                cli_obj.local = body.get("Local") or body.get("local") or cli_obj.local
                cli_obj.local_interno = body.get("Local interno") or body.get("local_interno") or cli_obj.local_interno
                cli_obj.maquina = body.get("Máquina") or body.get("maquina") or cli_obj.maquina
                cli_obj.modelo_maquina = body.get("Modelo de máquina") or body.get("modelo_maquina") or cli_obj.modelo_maquina
                cli_obj.filial_responsavel = body.get("Filial Responsavel") or body.get("filial_responsavel") or cli_obj.filial_responsavel

                db.commit()
                db.refresh(cli_obj)
                return {"status": "success", "message": "Cliente atualizado com sucesso.", "data": cli_obj.to_dict()}

            else:  # Inserir cliente
                novo_cli = ClienteModel(
                    cliente=body.get("Cliente") or body.get("cliente") or "",
                    local=body.get("Local") or body.get("local") or "",
                    local_interno=body.get("Local interno") or body.get("local_interno") or "",
                    maquina=body.get("Máquina") or body.get("maquina") or "",
                    modelo_maquina=body.get("Modelo de máquina") or body.get("modelo_maquina") or "",
                    filial_responsavel=body.get("Filial Responsavel") or body.get("filial_responsavel") or ""
                )
                db.add(novo_cli)
                db.commit()
                db.refresh(novo_cli)
                return {"status": "success", "message": "Cliente cadastrado com sucesso.", "data": novo_cli.to_dict()}

        # ----------------------------------------------------------------------
        # 4. CADASTRO DE USUÁRIOS (INSERT, EDIT, DELETE)
        # ----------------------------------------------------------------------
        elif action in ["inserir_usuario", "editar_usuario", "excluir_usuario"] or tipo == "usuario":
            if action == "excluir_usuario":
                item_id = body.get("id")
                user_login = (body.get("usuario") or body.get("Usuario") or "").strip().lower()
                u_obj = None
                if item_id and str(item_id).isdigit():
                    u_obj = db.query(UsuarioModel).filter(UsuarioModel.id == int(item_id)).first()
                if not u_obj and user_login:
                    u_obj = db.query(UsuarioModel).filter(func.lower(UsuarioModel.usuario) == user_login).first()

                if not u_obj:
                    return JSONResponse(status_code=404, content={"status": "error", "message": "Usuário não encontrado."})

                db.delete(u_obj)
                db.commit()
                return {"status": "success", "message": "Usuário excluído com sucesso."}

            elif action == "editar_usuario":
                item_id = body.get("id")
                user_login = (body.get("usuario") or body.get("Usuario") or "").strip().lower()
                u_obj = None
                if item_id and str(item_id).isdigit():
                    u_obj = db.query(UsuarioModel).filter(UsuarioModel.id == int(item_id)).first()
                if not u_obj and user_login:
                    u_obj = db.query(UsuarioModel).filter(func.lower(UsuarioModel.usuario) == user_login).first()

                if not u_obj:
                    return JSONResponse(status_code=404, content={"status": "error", "message": "Usuário não encontrado para edição."})

                u_obj.nome = (body.get("nome") or body.get("Nome") or u_obj.nome).strip()
                u_obj.usuario = (body.get("usuario") or body.get("Usuario") or u_obj.usuario).strip().lower()
                if body.get("senha") or body.get("Senha"):
                    u_obj.senha = str(body.get("senha") or body.get("Senha")).strip()
                u_obj.acesso = (body.get("acesso") or body.get("Acesso") or u_obj.acesso).strip()

                db.commit()
                db.refresh(u_obj)
                return {"status": "success", "message": "Usuário atualizado com sucesso.", "data": u_obj.to_dict()}

            else:  # Inserir usuário
                novo_login = (body.get("usuario") or body.get("Usuario") or "").strip().lower()
                if not novo_login:
                    return JSONResponse(status_code=400, content={"status": "error", "message": "Login de usuário obrigatório."})

                existente = db.query(UsuarioModel).filter(func.lower(UsuarioModel.usuario) == novo_login).first()
                if existente:
                    return JSONResponse(status_code=400, content={"status": "error", "message": f"O usuário '{novo_login}' já existe."})

                novo_u = UsuarioModel(
                    usuario=novo_login,
                    senha=str(body.get("senha") or body.get("Senha") or "123").strip(),
                    nome=(body.get("nome") or body.get("Nome") or novo_login).strip(),
                    acesso=(body.get("acesso") or body.get("Acesso") or "Atendente").strip()
                )
                db.add(novo_u)
                db.commit()
                db.refresh(novo_u)
                return {"status": "success", "message": "Usuário cadastrado com sucesso.", "data": novo_u.to_dict()}

        else:
            return JSONResponse(status_code=400, content={"status": "error", "message": f"Ação '{action}' não suportada."})

    except Exception as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"status": "error", "message": f"Erro interno do servidor: {str(e)}"})

# ==============================================================================
# ROTA DE HEALTHCHECK (MONITORAMENTO DO RENDER)
# ==============================================================================
@app.get("/health")
def healthcheck(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database unreachable: {str(e)}")

# ==============================================================================
# EXECUÇÃO DO SERVIDOR
# ==============================================================================
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)