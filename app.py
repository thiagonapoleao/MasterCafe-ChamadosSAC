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
    Text, func, desc, text, Index
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# ==============================================================================
# INICIALIZAÇÃO FASTAPI, STATIC FILES & JINJA2 TEMPLATES
# ==============================================================================
# 1º: Cria o objeto 'app'
app = FastAPI(title="Dashboard Executivo - Gestão SAC")

# 2º: Monta a rota '/static' apenas após a criação do 'app'
if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

# ==============================================================================
# CONFIGURAÇÃO DE BANCO DE DADOS (SUPABASE POSTGRESQL POOLER)
# ==============================================================================
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres.asptoykwjnpxwvnixslw:napoleao140205@aws-1-us-east-1.pooler.supabase.com:6543/postgres"
)

# Adequação de driver se fornecido apenas postgresql://
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,      # Evita conexões mortas no pooler do Supabase
    pool_recycle=300,        # Recicla conexões a cada 5 minutos
    pool_size=5,             # Respeita o teto de 512 MB de RAM do Render
    max_overflow=10,
    connect_args={"connect_timeout": 30}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ==============================================================================
# MODELOS DE DADOS COM ÍNDICES INTEGRADOS (PASSO 3)
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

# ==============================================================================
# PASSO 3: CRIAÇÃO E GARANTIA DOS ÍNDICES NO POSTGRESQL (SUPABASE)
# ==============================================================================
def criar_indices_de_alta_performance():
    """Garante que as 11.000+ linhas utilizem indexação B-Tree para buscas em sub-segundos."""
    queries_indices = [
        "CREATE INDEX IF NOT EXISTS idx_chamados_cliente ON chamados (cliente);",
        "CREATE INDEX IF NOT EXISTS idx_chamados_data ON chamados (data);",
        "CREATE INDEX IF NOT EXISTS idx_chamados_atendente ON chamados (atendente);",
        "CREATE INDEX IF NOT EXISTS idx_chamados_produto ON chamados (produto);",
        "CREATE INDEX IF NOT EXISTS idx_chamados_cidade ON chamados (cidade);",
        "CREATE INDEX IF NOT EXISTS idx_chamados_chamado ON chamados (chamado);"
    ]
    try:
        # Cria as tabelas caso não existam
        Base.metadata.create_all(bind=engine)
        
        # Executa a criação idempotente dos índices
        with engine.begin() as conn:
            for sql in queries_indices:
                conn.execute(text(sql))
        print("✅ [Passo 3 Concluído] Índices de performance verificados no Supabase.")
    except Exception as e:
        print(f"⚠️ Aviso na criação de índices: {e}")

# Executa a validação dos índices no carregamento do módulo
criar_indices_de_alta_performance()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

USUARIOS_SISTEMA = [
    {"usuario": "admin", "senha": "123", "nome": "Administrador Geral", "acesso": "Geral"},
    {"usuario": "atendente", "senha": "123", "nome": "Atendente SAC", "acesso": "Atendente"},
    {"usuario": "thiago", "senha": "123", "nome": "Thiago Napoleão", "acesso": "Geral"}
]

# ==============================================================================
# ROTA PRINCIPAL (INDEX COM LIMITE DE CARGA PARA PREVENIR TRAVAMENTOS)
# ==============================================================================
@app.get("/", response_class=HTMLResponse)
def index_page(request: Request, db: Session = Depends(get_db)):
    try:
        # 1. Total real de chamados no banco (COUNT otimizado pelo índice)
        total_chamados = db.query(func.count(ChamadoModel.id)).scalar() or 0

        # 2. Busca apenas os últimos 300 chamados para não esgotar a memória do Render
        chamados_recentes = (
            db.query(ChamadoModel)
            .order_by(desc(ChamadoModel.id))
            .limit(300)
            .all()
        )
        lista_chamados = [c.to_dict() for c in chamados_recentes]

        # 3. Base cadastral de Clientes
        clientes_db = db.query(ClienteModel).order_by(ClienteModel.cliente).all()
        lista_clientes = [cli.to_dict() for cli in clientes_db]

        # 4. Listagens de apoio aos seletores
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

        # 5. Sequencial de chamado automático para o ano corrente
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
            "usuarios": USUARIOS_SISTEMA,
            "descricoes": descricoes_padrao,
            "produtos": descricoes_padrao,
            "problemas": problemas_padrao,
            "formas_pgt": formas_pgto_padrao,
            "formas_pagamento": formas_pgto_padrao,
            "maior_sac_ano": {str(ano_atual): maior_seq}
        }

        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "dados_sac_json": json.dumps(dados_sac_payload, default=str),
                "total_chamados_carregados": total_chamados,
                "logo_base64_src": ""
            }
        )

    except Exception as e:
        return HTMLResponse(
            content=f"""
            <div style="font-family: sans-serif; padding: 40px; text-align: center;">
                <h2>Erro ao conectar com o banco de dados</h2>
                <p style="color: #dc2626;">{str(e)}</p>
                <button onclick="window.location.reload()" style="padding: 10px 20px; background: #0284c7; color: white; border: none; border-radius: 8px; cursor: pointer;">
                    Tentar Novamente 🔄
                </button>
            </div>
            """,
            status_code=500
        )

# ==============================================================================
# ROTA DE AÇÃO CENTRALIZADA (INSERT, EDIT, DELETE)
# ==============================================================================
@app.post("/api/action")
async def handle_action(request: Request, db: Session = Depends(get_db)):
    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"status": "error", "message": "Payload JSON inválido."})

    action = (body.get("action") or body.get("acao") or "").lower()
    tipo = (body.get("tipo") or "").lower()

    try:
        # ----------------------------------------------------------------------
        # 1. EXCLUIR CHAMADO SAC
        # ----------------------------------------------------------------------
        if action == "excluir" or tipo == "excluir_sac":
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