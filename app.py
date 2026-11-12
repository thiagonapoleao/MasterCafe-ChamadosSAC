import os
import json
import unicodedata
from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, Request, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlalchemy import (
    create_engine, Column, Integer, String, Numeric,
    Text, func, desc, text, or_, inspect
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# ==============================================================================
# UTILITÁRIOS DE CODIFICAÇÃO UTF-8 E SANITIZAÇÃO DE ACENTOS (~, ^, ´, ç, º, ª)
# ==============================================================================
def normalizar_utf8(valor: Any) -> Any:
    """Corrige eventuais falhas de codificação (mojibake) e normaliza strings em NFC UTF-8."""
    if valor is None or not isinstance(valor, str):
        return valor

    texto = valor
    # Tenta reverter leitura equivocada de UTF-8 como Latin-1 / Windows-1252
    if any(seq in texto for seq in ("Ã", "Â", "â€")):
        try:
            reparado = texto.encode("latin-1").decode("utf-8")
            if "\ufffd" not in reparado:
                texto = reparado
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass

    return unicodedata.normalize("NFC", texto).strip()


def normalizar_dict_utf8(dados: Dict[str, Any]) -> Dict[str, Any]:
    return {
        normalizar_utf8(k): (normalizar_utf8(v) if isinstance(v, str) else v)
        for k, v in dados.items()
    }


def formatar_data_ptbr(data_str: Optional[str]) -> str:
    """Converte YYYY-MM-DD para DD/MM/YYYY mantendo DD/MM/YYYY intacto."""
    if not data_str:
        return ""
    s = normalizar_utf8(str(data_str))
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        ano, mes, dia = s[:10].split("-")
        return f"{dia}/{mes}/{ano}"
    return s


def parse_valor_monetario(valor_bruto: Any) -> float:
    if valor_bruto is None or valor_bruto == "":
        return 0.0
    if isinstance(valor_bruto, (int, float)):
        return float(valor_bruto)
    s = str(valor_bruto).replace("R$", "").replace(" ", "").strip()
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


# ==============================================================================
# CONFIGURAÇÃO DE BANCO DE DADOS (SUPABASE POSTGRESQL POOLER)
# ==============================================================================
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres.asptoykwjnpxwvnixslw:napoleao140205@aws-1-us-east-1.pooler.supabase.com:6543/postgres"
)

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=5,
    max_overflow=10,
    connect_args={
        "connect_timeout": 30,
        "options": "-c client_encoding=UTF8"
    }
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ==============================================================================
# MODELOS DE DADOS (SUPABASE / POSTGRESQL)
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
        local_int = normalizar_utf8(self.local_interno or "")
        filial = normalizar_utf8(self.cidade or "")
        reemb_real = normalizar_utf8(self.reembolso_realizado or "Não")
        fin_resp = normalizar_utf8(self.financeiro_responsavel or "")
        obs = normalizar_utf8(self.observacao or "")
        dt_lanc = normalizar_utf8(self.data_hora_lancamento or "")

        return {
            "id": self.id,
            "linha": self.id,
            "chamado": normalizar_utf8(self.chamado or ""),
            "data": normalizar_utf8(self.data or ""),
            "cliente": normalizar_utf8(self.cliente or ""),
            "local_interno": local_int,
            "localInterno": local_int,
            "local": local_int,
            "cidade": filial,
            "filial": filial,
            "descricao": normalizar_utf8(self.descricao or ""),
            "produto": normalizar_utf8(self.produto or ""),
            "data_transacao": normalizar_utf8(self.data_transacao or ""),
            "dataTransacao": normalizar_utf8(self.data_transacao or ""),
            "hora_transacao": normalizar_utf8(self.hora_transacao or ""),
            "horaTransacao": normalizar_utf8(self.hora_transacao or ""),
            "valor": float(self.valor) if self.valor is not None else 0.0,
            "nome_sobrenome": normalizar_utf8(self.nome_sobrenome or ""),
            "nomeSobrenome": normalizar_utf8(self.nome_sobrenome or ""),
            "celular": normalizar_utf8(self.celular or ""),
            "problemas": normalizar_utf8(self.problemas or ""),
            "forma_pgto": normalizar_utf8(self.forma_pgto or ""),
            "formaPgto": normalizar_utf8(self.forma_pgto or ""),
            "reembolso": normalizar_utf8(self.reembolso or ""),
            "pix": normalizar_utf8(self.pix or ""),
            "atendente": normalizar_utf8(self.atendente or ""),
            "reembolso_realizado": reemb_real,
            "reembolsoRealizado": reemb_real,
            "financeiro_responsavel": fin_resp,
            "financeiroResponsavel": fin_resp,
            "observacao": obs,
            "obs": obs,
            "data_hora_lancamento": dt_lanc,
            "dataHoraLancamento": dt_lanc
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
        cli_nome = normalizar_utf8(self.cliente or "")
        loc_geral = normalizar_utf8(self.local or "")
        loc_int = normalizar_utf8(self.local_interno or self.local or "")
        filial = normalizar_utf8(self.filial_responsavel or "")

        return {
            "id": self.id,
            "linha": self.id,
            "cliente": cli_nome,
            "local": loc_geral or loc_int,
            "localInterno": loc_int,
            "local_interno": loc_int,
            "maquina": normalizar_utf8(self.maquina or ""),
            "modeloMaquina": normalizar_utf8(self.modelo_maquina or ""),
            "modelo_maquina": normalizar_utf8(self.modelo_maquina or ""),
            "filialResponsavel": filial,
            "filial_responsavel": filial,
            "cidade": filial
        }


# ==============================================================================
# CRIAÇÃO E GARANTIA DOS ÍNDICES NO POSTGRESQL (SUPABASE)
# ==============================================================================
def criar_indices_de_alta_performance():
    queries_indices = [
        "CREATE INDEX IF NOT EXISTS idx_chamados_cliente ON chamados (cliente);",
        "CREATE INDEX IF NOT EXISTS idx_chamados_data ON chamados (data);",
        "CREATE INDEX IF NOT EXISTS idx_chamados_atendente ON chamados (atendente);",
        "CREATE INDEX IF NOT EXISTS idx_chamados_produto ON chamados (produto);",
        "CREATE INDEX IF NOT EXISTS idx_chamados_cidade ON chamados (cidade);",
        "CREATE INDEX IF NOT EXISTS idx_chamados_chamado ON chamados (chamado);",
        "CREATE INDEX IF NOT EXISTS idx_clientes_cliente ON cadastro_clientes (cliente);"
    ]
    try:
        Base.metadata.create_all(bind=engine)
        with engine.begin() as conn:
            conn.execute(text("SET CLIENT_ENCODING TO 'UTF8';"))
            for sql in queries_indices:
                conn.execute(text(sql))
        print("✅ Índices e encoding UTF-8 verificados no Supabase.")
    except Exception as e:
        print(f"⚠️ Aviso na inicialização do banco: {e}")


criar_indices_de_alta_performance()

# ==============================================================================
# INICIALIZAÇÃO FASTAPI & JINJA2 TEMPLATES (CAMINHOS ABSOLUTOS PARA RENDER)
# ==============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

app = FastAPI(title="Gestão SAC MasterCafé", version="2.2.1")

if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)


def get_db():
    db = SessionLocal()
    try:
        db.execute(text("SET CLIENT_ENCODING TO 'UTF8';"))
        yield db
    finally:
        db.close()


USUARIOS_PADRAO = [
    {"usuario": "admin", "senha": "123", "nome": "Administrador Geral", "acesso": "Geral"},
    {"usuario": "atendente", "senha": "123", "nome": "Atendente SAC", "acesso": "Atendente"},
    {"usuario": "thiago", "senha": "123", "nome": "Thiago Napoleão", "acesso": "Geral"}
]


def carregar_tabela_auxiliar(db: Session, nome_tabela: str, colunas_candidatas: List[str]) -> List[str]:
    """Lê tabelas auxiliares opcionais no Supabase (produtos, problemas, formas_pgt) com segurança."""
    try:
        insp = inspect(db.bind)
        if not insp.has_table(nome_tabela):
            return []
        rows = db.execute(text(f"SELECT * FROM {nome_tabela}")).mappings().all()
        itens = []
        for r in rows:
            for col in colunas_candidatas:
                if col in r and r[col]:
                    itens.append(normalizar_utf8(str(r[col])))
                    break
        return sorted(list(set(filter(None, itens))))
    except Exception:
        return []


def gerar_proximo_numero_chamado(db: Session, ano: Optional[int] = None) -> str:
    ano_ref = ano or datetime.now().year
    prefixo = f"SAC-{ano_ref}-"
    chamados_ano = (
        db.query(ChamadoModel.chamado)
        .filter(ChamadoModel.chamado.like(f"{prefixo}%"))
        .all()
    )
    maior_seq = 0
    for (codigo,) in chamados_ano:
        if codigo:
            try:
                seq = int(str(codigo).split("-")[-1])
                if seq > maior_seq:
                    maior_seq = seq
            except ValueError:
                continue
    return f"{prefixo}{str(maior_seq + 1).zfill(4)}"


# ==============================================================================
# ROTA PRINCIPAL (INDEX COM CARGA INICIAL OTIMIZADA E UTF-8 GARANTIDO)
# ==============================================================================
@app.get("/", response_class=HTMLResponse)
def index_page(request: Request, db: Session = Depends(get_db)):
    try:
        total_chamados = db.query(func.count(ChamadoModel.id)).scalar() or 0

        # Carrega os 500 mais recentes para KPIs/Gráficos rápidos sem estourar a RAM do Render
        chamados_recentes = (
            db.query(ChamadoModel)
            .order_by(desc(ChamadoModel.id))
            .limit(500)
            .all()
        )
        lista_chamados = [c.to_dict() for c in chamados_recentes]

        # Base cadastral completa de clientes (para vínculo automático de Local Interno e Filial)
        clientes_db = db.query(ClienteModel).order_by(ClienteModel.cliente, ClienteModel.local_interno).all()
        lista_clientes = [cli.to_dict() for cli in clientes_db]

        # Listagens auxiliares (tenta ler do banco; se não existir tabela, usa padrão)
        descricoes_db = carregar_tabela_auxiliar(db, "produtos", ["descricao", "produto", "nome"])
        descricoes_padrao = descricoes_db or [
            "Café Expresso", "Café com Leite", "Cappuccino", "Mocaccino",
            "Chocolate Quente", "Chá", "Salgadinho", "Refrigerante", "Suco", "Água Mineral"
        ]

        problemas_db = carregar_tabela_auxiliar(db, "problemas", ["problema", "problemas", "descricao", "nome"])
        problemas_padrao = problemas_db or [
            "Não liberou produto", "Cobrou e não liberou", "Produto gelado/frio",
            "Nota/Moeda presa", "Produto travado na mola", "Pagamento não reconhecido",
            "Máquina sem energia", "Outro"
        ]

        formas_db = carregar_tabela_auxiliar(db, "formas_pgt", ["forma_pgt", "forma_pagamento", "descricao", "nome"])
        formas_pgto_padrao = formas_db or [
            "Cartão de Débito", "Cartão de Crédito", "Pix", "Dinheiro/Moeda",
            "Crédito Remoto", "Voucher"
        ]

        # Cidades / Filiais únicas a partir do cadastro de clientes e chamados
        cidades_clientes = {c["filialResponsavel"] for c in lista_clientes if c.get("filialResponsavel")}
        cidades_chamados = {c["cidade"] for c in lista_chamados if c.get("cidade")}
        lista_cidades = sorted(list(cidades_clientes.union(cidades_chamados)))

        ano_atual = datetime.now().year
        proximo_sac = gerar_proximo_numero_chamado(db, ano_atual)
        maior_seq = int(proximo_sac.split("-")[-1]) - 1

        dados_sac_payload = {
            "chamados": lista_chamados,
            "total_chamados": total_chamados,
            "cadastro_clientes": lista_clientes,
            "clientes": lista_clientes,
            "cidades": lista_cidades,
            "usuarios": USUARIOS_PADRAO,
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
                "dados_sac_json": json.dumps(dados_sac_payload, ensure_ascii=False, default=str),
                "total_chamados_carregados": total_chamados,
                "logo_base64_src": ""
            },
            media_type="text/html; charset=utf-8"
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
            status_code=500,
            media_type="text/html; charset=utf-8"
        )


# ==============================================================================
# ROTA DE PAGINAÇÃO SERVER-SIDE (50 EM 50 CHAMADOS SEM RECARREGAR A PÁGINA)
# ==============================================================================
@app.get("/api/chamados")
def listar_chamados_paginados(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    search: str = Query(""),
    aba: str = Query("todos"),
    db: Session = Depends(get_db)
):
    try:
        query = db.query(ChamadoModel)

        termo = normalizar_utf8(search)
        if termo:
            like_pattern = f"%{termo}%"
            query = query.filter(
                or_(
                    ChamadoModel.chamado.ilike(like_pattern),
                    ChamadoModel.data.ilike(like_pattern),
                    ChamadoModel.cliente.ilike(like_pattern),
                    ChamadoModel.local_interno.ilike(like_pattern),
                    ChamadoModel.cidade.ilike(like_pattern),
                    ChamadoModel.produto.ilike(like_pattern),
                    ChamadoModel.nome_sobrenome.ilike(like_pattern),
                    ChamadoModel.forma_pgto.ilike(like_pattern),
                    ChamadoModel.reembolso.ilike(like_pattern),
                    ChamadoModel.pix.ilike(like_pattern),
                    ChamadoModel.financeiro_responsavel.ilike(like_pattern),
                    ChamadoModel.observacao.ilike(like_pattern),
                    ChamadoModel.atendente.ilike(like_pattern)
                )
            )

        total_registros = query.with_entities(func.count(ChamadoModel.id)).scalar() or 0
        total_paginas = max(1, (total_registros + limit - 1) // limit)
        pagina_ajustada = min(page, total_paginas)
        offset = (pagina_ajustada - 1) * limit

        registros = (
            query.order_by(desc(ChamadoModel.id))
            .offset(offset)
            .limit(limit)
            .all()
        )

        return JSONResponse(
            content={
                "status": "success",
                "items": [r.to_dict() for r in registros],
                "total": total_registros,
                "page": pagina_ajustada,
                "limit": limit,
                "total_pages": total_paginas
            },
            media_type="application/json; charset=utf-8"
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Erro ao paginar chamados: {str(e)}"},
            media_type="application/json; charset=utf-8"
        )


# ==============================================================================
# ROTA DE AÇÃO CENTRALIZADA (INSERT, EDIT, DELETE COM PERSISTÊNCIA GARANTIDA)
# ==============================================================================
@app.post("/api/action")
async def handle_action(request: Request, db: Session = Depends(get_db)):
    try:
        raw_bytes = await request.body()
        raw_text = raw_bytes.decode("utf-8")
        body_raw: Dict[str, Any] = json.loads(raw_text)
        body = normalizar_dict_utf8(body_raw)
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Payload JSON UTF-8 inválido."},
            media_type="application/json; charset=utf-8"
        )

    action = (body.get("action") or body.get("acao") or "").lower().strip()
    tipo = (body.get("tipo") or "").lower().strip()

    try:
        # ----------------------------------------------------------------------
        # 1. EXCLUIR CHAMADO SAC
        # ----------------------------------------------------------------------
        if action == "excluir" or tipo == "excluir_sac":
            num_chamado = normalizar_utf8(body.get("chamado") or body.get("Chamado") or "")
            item_id = body.get("id") or body.get("linha")

            chamado_obj = None
            if item_id is not None and str(item_id).strip().isdigit():
                chamado_obj = db.query(ChamadoModel).filter(ChamadoModel.id == int(item_id)).first()
            if not chamado_obj and num_chamado:
                chamado_obj = db.query(ChamadoModel).filter(ChamadoModel.chamado == num_chamado).first()

            if not chamado_obj:
                return JSONResponse(
                    status_code=404,
                    content={"status": "error", "message": f"Chamado '{num_chamado}' não encontrado."},
                    media_type="application/json; charset=utf-8"
                )

            db.delete(chamado_obj)
            db.commit()
            return JSONResponse(
                content={"status": "success", "message": f"Chamado {num_chamado} excluído com sucesso."},
                media_type="application/json; charset=utf-8"
            )

        # ----------------------------------------------------------------------
        # 2. INSERIR OU EDITAR CHAMADO SAC
        # ----------------------------------------------------------------------
        elif action in ["inserir", "editar"]:
            num_chamado = normalizar_utf8(body.get("chamado") or body.get("Chamado") or "")
            item_id = body.get("id") or body.get("linha")
            valor_float = parse_valor_monetario(body.get("valor") if body.get("valor") is not None else body.get("Valor"))

            data_fmt = formatar_data_ptbr(body.get("data") or body.get("Data"))
            cliente_val = normalizar_utf8(body.get("cliente") or body.get("Cliente") or "")
            local_int_val = normalizar_utf8(
                body.get("local_interno") or body.get("localInterno") or body.get("Local Interno") or body.get("local") or ""
            )
            cidade_val = normalizar_utf8(
                body.get("cidade") or body.get("Cidade") or body.get("filial") or body.get("Filial Responsavel") or ""
            )
            descricao_val = normalizar_utf8(body.get("descricao") or body.get("Descrição") or "")
            produto_val = normalizar_utf8(body.get("produto") or body.get("Produto") or "")
            dt_trans_val = formatar_data_ptbr(
                body.get("data_transacao") or body.get("dataTransacao") or body.get("Data da Transação") or ""
            )
            hr_trans_val = normalizar_utf8(
                body.get("hora_transacao") or body.get("horaTransacao") or body.get("Hora da Transação") or ""
            )
            nome_val = normalizar_utf8(
                body.get("nome_sobrenome") or body.get("nomeSobrenome") or body.get("Nome/Sobrenome") or ""
            )
            celular_val = normalizar_utf8(body.get("celular") or body.get("Celular") or "")
            problemas_val = normalizar_utf8(body.get("problemas") or body.get("Problemas") or "")
            forma_pgto_val = normalizar_utf8(
                body.get("forma_pgto") or body.get("formaPgto") or body.get("Forma de Pagamento") or ""
            )
            reembolso_val = normalizar_utf8(body.get("reembolso") or body.get("Reembolso") or "")
            pix_val = normalizar_utf8(body.get("pix") or body.get("Pix - Reembolso") or "")
            reemb_real_val = normalizar_utf8(
                body.get("reembolso_realizado") or body.get("reembolsoRealizado") or body.get("Reembolso Realizado") or "Não"
            )
            fin_resp_val = normalizar_utf8(
                body.get("financeiro_responsavel") or body.get("financeiroResponsavel") or body.get("Financeiro Responsavel") or ""
            )
            obs_val = normalizar_utf8(body.get("observacao") or body.get("Observação") or body.get("obs") or "")
            atendente_val = normalizar_utf8(body.get("atendente") or body.get("Atendente") or "Operador")
            dt_lanc_val = normalizar_utf8(
                body.get("data_hora_lancamento") or body.get("dataHoraLancamento") or body.get("Data/Hora do lançamento")
                or datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            )

            if action == "editar":
                chamado_obj = None
                if item_id is not None and str(item_id).strip().isdigit():
                    chamado_obj = db.query(ChamadoModel).filter(ChamadoModel.id == int(item_id)).first()
                if not chamado_obj and num_chamado:
                    chamado_obj = db.query(ChamadoModel).filter(ChamadoModel.chamado == num_chamado).first()

                if not chamado_obj:
                    return JSONResponse(
                        status_code=404,
                        content={"status": "error", "message": f"Chamado '{num_chamado}' não encontrado para alteração."},
                        media_type="application/json; charset=utf-8"
                    )

                if data_fmt:
                    chamado_obj.data = data_fmt
                if cliente_val:
                    chamado_obj.cliente = cliente_val
                chamado_obj.local_interno = local_int_val
                chamado_obj.cidade = cidade_val
                chamado_obj.descricao = descricao_val
                chamado_obj.produto = produto_val
                chamado_obj.data_transacao = dt_trans_val
                chamado_obj.hora_transacao = hr_trans_val
                chamado_obj.valor = valor_float
                chamado_obj.nome_sobrenome = nome_val
                chamado_obj.celular = celular_val
                chamado_obj.problemas = problemas_val
                chamado_obj.forma_pgto = forma_pgto_val
                chamado_obj.reembolso = reembolso_val
                chamado_obj.pix = pix_val
                chamado_obj.reembolso_realizado = reemb_real_val or "Não"
                chamado_obj.financeiro_responsavel = fin_resp_val
                chamado_obj.observacao = obs_val

                db.commit()
                db.refresh(chamado_obj)
                dados_salvos = chamado_obj.to_dict()
                return JSONResponse(
                    content={
                        "status": "success",
                        "message": "Chamado atualizado com sucesso.",
                        "chamado": dados_salvos["chamado"],
                        "linha": dados_salvos["id"],
                        "data": dados_salvos
                    },
                    media_type="application/json; charset=utf-8"
                )

            else:  # INSERÇÃO DE NOVO CHAMADO
                ano_corrente = datetime.now().year
                if not num_chamado or db.query(ChamadoModel).filter(ChamadoModel.chamado == num_chamado).first():
                    num_chamado = gerar_proximo_numero_chamado(db, ano_corrente)

                novo_chamado = ChamadoModel(
                    chamado=num_chamado,
                    data=data_fmt or datetime.now().strftime("%d/%m/%Y"),
                    cliente=cliente_val,
                    local_interno=local_int_val,
                    cidade=cidade_val,
                    descricao=descricao_val,
                    produto=produto_val,
                    data_transacao=dt_trans_val,
                    hora_transacao=hr_trans_val,
                    valor=valor_float,
                    nome_sobrenome=nome_val,
                    celular=celular_val,
                    problemas=problemas_val,
                    forma_pgto=forma_pgto_val,
                    reembolso=reembolso_val,
                    pix=pix_val,
                    atendente=atendente_val,
                    reembolso_realizado=reemb_real_val or "Não",
                    financeiro_responsavel=fin_resp_val,
                    observacao=obs_val,
                    data_hora_lancamento=dt_lanc_val
                )

                db.add(novo_chamado)
                db.commit()
                db.refresh(novo_chamado)
                dados_salvos = novo_chamado.to_dict()
                return JSONResponse(
                    content={
                        "status": "success",
                        "message": "Chamado cadastrado com sucesso.",
                        "chamado": dados_salvos["chamado"],
                        "linha": dados_salvos["id"],
                        "data": dados_salvos
                    },
                    media_type="application/json; charset=utf-8"
                )

        # ----------------------------------------------------------------------
        # 3. CADASTRO DE CLIENTES (INSERT, EDIT, DELETE)
        # ----------------------------------------------------------------------
        elif action in ["inserir_cliente", "editar_cliente", "excluir_cliente"] or tipo in ["cadastro_cliente", "excluir_cliente"]:
            if action == "excluir_cliente" or tipo == "excluir_cliente":
                item_id = body.get("id") or body.get("linha")
                cli_nome = normalizar_utf8(body.get("Cliente") or body.get("cliente") or "")
                loc_int = normalizar_utf8(body.get("Local interno") or body.get("local_interno") or "")

                cli_obj = None
                if item_id is not None and str(item_id).strip().isdigit():
                    cli_obj = db.query(ClienteModel).filter(ClienteModel.id == int(item_id)).first()
                if not cli_obj and cli_nome:
                    q = db.query(ClienteModel).filter(ClienteModel.cliente == cli_nome)
                    if loc_int:
                        q = q.filter(ClienteModel.local_interno == loc_int)
                    cli_obj = q.first()

                if not cli_obj:
                    return JSONResponse(
                        status_code=404,
                        content={"status": "error", "message": "Cliente não localizado para exclusão."},
                        media_type="application/json; charset=utf-8"
                    )

                db.delete(cli_obj)
                db.commit()
                return JSONResponse(
                    content={"status": "success", "message": "Cliente excluído com sucesso."},
                    media_type="application/json; charset=utf-8"
                )

            elif action == "editar_cliente":
                item_id = body.get("id") or body.get("linha")
                cli_obj = (
                    db.query(ClienteModel).filter(ClienteModel.id == int(item_id)).first()
                    if item_id is not None and str(item_id).strip().isdigit()
                    else None
                )

                if not cli_obj:
                    return JSONResponse(
                        status_code=404,
                        content={"status": "error", "message": "Registro de cliente não encontrado para edição."},
                        media_type="application/json; charset=utf-8"
                    )

                cli_obj.cliente = normalizar_utf8(body.get("Cliente") or body.get("cliente") or cli_obj.cliente)
                cli_obj.local = normalizar_utf8(body.get("Local") or body.get("local") or cli_obj.local)
                cli_obj.local_interno = normalizar_utf8(
                    body.get("Local interno") or body.get("localInterno") or body.get("local_interno") or cli_obj.local_interno
                )
                cli_obj.maquina = normalizar_utf8(body.get("Máquina") or body.get("maquina") or cli_obj.maquina)
                cli_obj.modelo_maquina = normalizar_utf8(
                    body.get("Modelo de máquina") or body.get("modeloMaquina") or body.get("modelo_maquina") or cli_obj.modelo_maquina
                )
                cli_obj.filial_responsavel = normalizar_utf8(
                    body.get("Filial Responsavel") or body.get("filialResponsavel") or body.get("filial_responsavel") or cli_obj.filial_responsavel
                )

                db.commit()
                db.refresh(cli_obj)
                dados_cli = cli_obj.to_dict()
                return JSONResponse(
                    content={
                        "status": "success",
                        "message": "Cliente atualizado com sucesso.",
                        "linha": dados_cli["id"],
                        "data": dados_cli
                    },
                    media_type="application/json; charset=utf-8"
                )

            else:  # Inserir cliente
                novo_cli = ClienteModel(
                    cliente=normalizar_utf8(body.get("Cliente") or body.get("cliente") or ""),
                    local=normalizar_utf8(body.get("Local") or body.get("local") or ""),
                    local_interno=normalizar_utf8(
                        body.get("Local interno") or body.get("localInterno") or body.get("local_interno") or ""
                    ),
                    maquina=normalizar_utf8(body.get("Máquina") or body.get("maquina") or ""),
                    modelo_maquina=normalizar_utf8(
                        body.get("Modelo de máquina") or body.get("modeloMaquina") or body.get("modelo_maquina") or ""
                    ),
                    filial_responsavel=normalizar_utf8(
                        body.get("Filial Responsavel") or body.get("filialResponsavel") or body.get("filial_responsavel") or ""
                    )
                )
                db.add(novo_cli)
                db.commit()
                db.refresh(novo_cli)
                dados_cli = novo_cli.to_dict()
                return JSONResponse(
                    content={
                        "status": "success",
                        "message": "Cliente cadastrado com sucesso.",
                        "linha": dados_cli["id"],
                        "data": dados_cli
                    },
                    media_type="application/json; charset=utf-8"
                )

        else:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": f"Ação '{action}' não suportada."},
                media_type="application/json; charset=utf-8"
            )

    except Exception as e:
        db.rollback()
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Erro interno do servidor: {str(e)}"},
            media_type="application/json; charset=utf-8"
        )


# ==============================================================================
# ROTA DE HEALTHCHECK (MONITORAMENTO DO RENDER)
# ==============================================================================
@app.get("/health")
def healthcheck(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected", "encoding": "UTF-8"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database unreachable: {str(e)}")


# ==============================================================================
# EXECUÇÃO DO SERVIDOR
# ==============================================================================
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)