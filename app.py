import os
import re
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
# UTILITÁRIOS DE CODIFICAÇÃO UTF-8 E REPARO DE ACENTOS (~, ^, ´, ç, º, ª)
# ==============================================================================
MAPA_REPARO_MOJIBAKE = {
    "Ã¡": "á", "Ã ": "à", "Ã¢": "â", "Ã£": "ã", "Ã¤": "ä",
    "Ã": "Á", "Ã€": "À", "Ã‚": "Â", "Ãƒ": "Ã", "Ã„": "Ä",
    "Ã©": "é", "Ã¨": "è", "Ãª": "ê", "Ã«": "ë",
    "Ã‰": "É", "Ãˆ": "È", "ÃŠ": "Ê", "Ã‹": "Ë",
    "Ã­": "í", "Ã¬": "ì", "Ã®": "î", "Ã¯": "ï",
    "Ã": "Í", "ÃŒ": "Ì", "ÃŽ": "Î", "Ã": "Ï",
    "Ã³": "ó", "Ã²": "ò", "Ã´": "ô", "Ãµ": "õ", "Ã¶": "ö",
    "Ã“": "Ó", "Ã’": "Ò", "Ã”": "Ô", "Ã•": "Õ", "Ã–": "Ö",
    "Ãº": "ú", "Ã¹": "ù", "Ã»": "û", "Ã¼": "ü",
    "Ãš": "Ú", "Ã™": "Ù", "Ã›": "Û", "Ãœ": "Ü",
    "Ã§": "ç", "Ã‡": "Ç", "Ã±": "ñ", "Ã‘": "Ñ",
    "Âº": "º", "Âª": "ª", "Â°": "°", "â€“": "–", "â€”": "—"
}


def normalizar_utf8(valor: Any) -> Any:
    """Corrige falhas de codificação (UTF-8 lido como Latin-1/CP1252) e normaliza em NFC."""
    if valor is None or not isinstance(valor, str):
        return valor

    texto = valor

    # 1. Tenta decodificação reversa binária (cp1252 e latin-1 -> utf-8)
    if any(seq in texto for seq in ("Ã", "Â", "â€")):
        for enc in ("cp1252", "latin-1"):
            try:
                reparado = texto.encode(enc).decode("utf-8")
                if "\ufffd" not in reparado:
                    texto = reparado
                    break
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue

        # 2. Varredura residual para pares mojibake mistos na mesma string
        if any(seq in texto for seq in ("Ã", "Â", "â€")):
            for errado, certo in MAPA_REPARO_MOJIBAKE.items():
                if errado in texto:
                    texto = texto.replace(errado, certo)

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
RAW_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres.asptoykwjnpxwvnixslw:napoleao140205@aws-1-us-east-1.pooler.supabase.com:6543/postgres"
).strip()

if RAW_DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = RAW_DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif RAW_DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = RAW_DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
else:
    DATABASE_URL = RAW_DATABASE_URL

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
        "CREATE INDEX IF NOT EXISTS idx_chamados_chamado ON chamados (chamado);"
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

app = FastAPI(title="Gestão SAC MasterCafé", version="2.4.0")

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


def descobrir_tabela_clientes(db: Session) -> str:
    """Identifica dinamicamente se a tabela no Supabase se chama 'clientes' ou 'cadastro_clientes'."""
    try:
        insp = inspect(db.bind)
        if insp.has_table("clientes"):
            return "clientes"
        if insp.has_table("cadastro_clientes"):
            return "cadastro_clientes"
        # Cria tabela 'clientes' caso nenhuma exista ainda
        with db.bind.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS clientes (
                    id SERIAL PRIMARY KEY,
                    cliente VARCHAR(150) NOT NULL,
                    local VARCHAR(150),
                    local_interno VARCHAR(150),
                    maquina VARCHAR(100),
                    modelo_maquina VARCHAR(100),
                    filial_responsavel VARCHAR(100)
                );
            """))
        return "clientes"
    except Exception:
        return "clientes"


def normalizar_chave_coluna(col: str) -> str:
    """Remove acentos e espaços para mapear qualquer nome de coluna do PostgreSQL."""
    s = normalizar_utf8(str(col)).lower()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def carregar_clientes_banco(db: Session) -> List[Dict[str, Any]]:
    """Lê todos os registros da tabela 'clientes' (ou 'cadastro_clientes') no Supabase com UTF-8."""
    tabela = descobrir_tabela_clientes(db)
    lista_final: List[Dict[str, Any]] = []
    try:
        rows = db.execute(text(f"SELECT * FROM {tabela}")).mappings().all()
        for r in rows:
            m = {normalizar_chave_coluna(k): v for k, v in r.items()}
            item_id = m.get("id") or m.get("linha") or len(lista_final) + 1
            cli_nome = normalizar_utf8(str(m.get("cliente") or m.get("nome_cliente") or m.get("empresa") or ""))
            loc_geral = normalizar_utf8(str(m.get("local") or m.get("unidade") or ""))
            loc_int = normalizar_utf8(
                str(m.get("local_interno") or m.get("localinterno") or m.get("ponto") or m.get("setor") or loc_geral)
            )
            filial = normalizar_utf8(
                str(m.get("filial_responsavel") or m.get("filialresponsavel") or m.get("filial") or m.get("cidade") or "")
            )
            maquina = normalizar_utf8(str(m.get("maquina") or m.get("equipamento") or ""))
            modelo = normalizar_utf8(str(m.get("modelo_maquina") or m.get("modelomaquina") or m.get("modelo") or ""))

            if cli_nome:
                lista_final.append({
                    "id": item_id,
                    "linha": item_id,
                    "cliente": cli_nome,
                    "local": loc_geral or loc_int,
                    "localInterno": loc_int,
                    "local_interno": loc_int,
                    "maquina": maquina,
                    "modeloMaquina": modelo,
                    "modelo_maquina": modelo,
                    "filialResponsavel": filial,
                    "filial_responsavel": filial,
                    "cidade": filial
                })

        lista_final.sort(key=lambda x: (x["cliente"].lower(), x["localInterno"].lower()))
    except Exception as e:
        print(f"⚠️ Erro ao ler tabela '{tabela}': {e}")

    return lista_final


def carregar_produtos_banco(db: Session) -> List[str]:
    """Lê todos os registros da tabela 'produtos' no Supabase para preencher Descrição *."""
    itens: List[str] = []
    try:
        insp = inspect(db.bind)
        for nome_tabela in ["produtos", "produto", "descricoes"]:
            if not insp.has_table(nome_tabela):
                continue
            rows = db.execute(text(f"SELECT * FROM {nome_tabela}")).mappings().all()
            for r in rows:
                m = {normalizar_chave_coluna(k): v for k, v in r.items()}
                val = (
                    m.get("descricao")
                    or m.get("produto")
                    or m.get("nome")
                    or m.get("descricao_produto")
                    or m.get("item")
                )
                if not val:
                    # Fallback: pega a primeira coluna textual não-id da linha
                    for k_orig, v_orig in r.items():
                        if normalizar_chave_coluna(k_orig) != "id" and isinstance(v_orig, str) and v_orig.strip():
                            val = v_orig
                            break
                if val:
                    texto_limpo = normalizar_utf8(str(val))
                    if texto_limpo:
                        itens.append(texto_limpo)
            if itens:
                break
    except Exception as e:
        print(f"⚠️ Erro ao ler tabela 'produtos': {e}")

    return sorted(list(set(itens)), key=lambda s: s.lower())


def carregar_tabela_auxiliar(db: Session, nome_tabela: str, colunas_candidatas: List[str]) -> List[str]:
    """Lê tabelas auxiliares no Supabase (problemas, formas_pgt) com sanitização UTF-8."""
    try:
        insp = inspect(db.bind)
        if not insp.has_table(nome_tabela):
            return []
        rows = db.execute(text(f"SELECT * FROM {nome_tabela}")).mappings().all()
        itens = []
        for r in rows:
            m = {normalizar_chave_coluna(k): v for k, v in r.items()}
            for col in colunas_candidatas:
                col_norm = normalizar_chave_coluna(col)
                if col_norm in m and m[col_norm]:
                    itens.append(normalizar_utf8(str(m[col_norm])))
                    break
        return sorted(list(set(filter(None, itens))), key=lambda s: s.lower())
    except Exception:
        return []


def carregar_usuarios_banco(db: Session) -> List[Dict[str, str]]:
    """Lê os usuários cadastrados no Supabase e mescla com os usuários padrão."""
    usuarios_final = {u["usuario"].lower(): u for u in USUARIOS_PADRAO}
    try:
        insp = inspect(db.bind)
        for nome_tabela in ["usuarios", "usuario", "atendentes", "acessos", "login", "users"]:
            if not insp.has_table(nome_tabela):
                continue
            rows = db.execute(text(f"SELECT * FROM {nome_tabela}")).mappings().all()
            for r in rows:
                r_norm = {normalizar_chave_coluna(k): v for k, v in r.items()}
                user_login = normalizar_utf8(
                    str(r_norm.get("usuario") or r_norm.get("login") or r_norm.get("user") or r_norm.get("username") or "")
                ).lower()
                user_senha = normalizar_utf8(
                    str(r_norm.get("senha") or r_norm.get("password") or r_norm.get("pass") or "")
                )
                user_nome = normalizar_utf8(
                    str(r_norm.get("nome") or r_norm.get("atendente") or r_norm.get("funcionario") or user_login)
                )
                user_acesso = normalizar_utf8(
                    str(r_norm.get("acesso") or r_norm.get("nivel") or r_norm.get("perfil") or r_norm.get("role") or "Atendente")
                )

                if user_login and user_senha:
                    usuarios_final[user_login] = {
                        "usuario": user_login,
                        "senha": user_senha,
                        "nome": user_nome,
                        "acesso": user_acesso
                    }
    except Exception as e:
        print(f"⚠️ Aviso ao carregar usuários do banco: {e}")

    return list(usuarios_final.values())


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

        # 1. Busca base cadastral diretamente na tabela "clientes" do Supabase
        lista_clientes = carregar_clientes_banco(db)

        # 2. Busca descrições diretamente na tabela "produtos" do Supabase
        produtos_db = carregar_produtos_banco(db)
        descricoes_padrao = produtos_db or [
            "Café Expresso", "Café com Leite", "Cappuccino", "Mocaccino",
            "Chocolate Quente", "Chá", "Salgadinho", "Refrigerante", "Suco", "Água Mineral"
        ]

        # 3. Usuários cadastrados no Supabase + fallback padrão
        lista_usuarios = carregar_usuarios_banco(db)

        # 4. Tabelas auxiliares de problemas e formas de pagamento
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

        # 5. Cidades / Filiais únicas a partir da tabela "clientes" e chamados
        cidades_clientes = {c["filialResponsavel"] for c in lista_clientes if c.get("filialResponsavel")}
        cidades_chamados = {c["cidade"] for c in lista_chamados if c.get("cidade")}
        lista_cidades = sorted(list(cidades_clientes.union(cidades_chamados)), key=lambda s: s.lower())

        ano_atual = datetime.now().year
        proximo_sac = gerar_proximo_numero_chamado(db, ano_atual)
        maior_seq = int(proximo_sac.split("-")[-1]) - 1

        dados_sac_payload = {
            "chamados": lista_chamados,
            "total_chamados": total_chamados,
            "cadastro_clientes": lista_clientes,
            "clientes": lista_clientes,
            "cidades": lista_cidades,
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
        # 3. CADASTRO DE CLIENTES (TABELA "clientes" NO SUPABASE)
        # ----------------------------------------------------------------------
        elif action in ["inserir_cliente", "editar_cliente", "excluir_cliente"] or tipo in ["cadastro_cliente", "excluir_cliente"]:
            tabela_cli = descobrir_tabela_clientes(db)
            insp = inspect(db.bind)
            colunas_tabela = {c["name"] for c in insp.get_columns(tabela_cli)}

            cli_val = normalizar_utf8(body.get("Cliente") or body.get("cliente") or "")
            loc_val = normalizar_utf8(body.get("Local") or body.get("local") or "")
            loc_int_val = normalizar_utf8(
                body.get("Local interno") or body.get("localInterno") or body.get("local_interno") or ""
            )
            maq_val = normalizar_utf8(body.get("Máquina") or body.get("maquina") or "")
            mod_val = normalizar_utf8(
                body.get("Modelo de máquina") or body.get("modeloMaquina") or body.get("modelo_maquina") or ""
            )
            fil_val = normalizar_utf8(
                body.get("Filial Responsavel") or body.get("filialResponsavel") or body.get("filial_responsavel") or ""
            )

            if action == "excluir_cliente" or tipo == "excluir_cliente":
                item_id = body.get("id") or body.get("linha")
                if item_id is not None and str(item_id).strip().isdigit() and "id" in colunas_tabela:
                    db.execute(text(f"DELETE FROM {tabela_cli} WHERE id = :id"), {"id": int(item_id)})
                else:
                    db.execute(
                        text(f"DELETE FROM {tabela_cli} WHERE cliente = :cli AND local_interno = :loc"),
                        {"cli": cli_val, "loc": loc_int_val}
                    )
                db.commit()
                return JSONResponse(
                    content={"status": "success", "message": "Cliente excluído com sucesso."},
                    media_type="application/json; charset=utf-8"
                )

            elif action == "editar_cliente":
                item_id = body.get("id") or body.get("linha")
                if item_id is None or not str(item_id).strip().isdigit():
                    return JSONResponse(
                        status_code=400,
                        content={"status": "error", "message": "ID do cliente inválido para edição."},
                        media_type="application/json; charset=utf-8"
                    )

                campos_map = {
                    "cliente": cli_val,
                    "local": loc_val,
                    "local_interno": loc_int_val,
                    "maquina": maq_val,
                    "modelo_maquina": mod_val,
                    "filial_responsavel": fil_val
                }
                sets = [f"{k} = :{k}" for k in campos_map if k in colunas_tabela]
                params = {k: v for k, v in campos_map.items() if k in colunas_tabela}
                params["id"] = int(item_id)

                if sets:
                    db.execute(text(f"UPDATE {tabela_cli} SET {', '.join(sets)} WHERE id = :id"), params)
                    db.commit()

                return JSONResponse(
                    content={
                        "status": "success",
                        "message": "Cliente atualizado com sucesso.",
                        "linha": int(item_id)
                    },
                    media_type="application/json; charset=utf-8"
                )

            else:  # Inserir cliente
                campos_map = {
                    "cliente": cli_val,
                    "local": loc_val,
                    "local_interno": loc_int_val,
                    "maquina": maq_val,
                    "modelo_maquina": mod_val,
                    "filial_responsavel": fil_val
                }
                cols_validas = [k for k in campos_map if k in colunas_tabela]
                vals_validas = [f":{k}" for k in cols_validas]
                params = {k: campos_map[k] for k in cols_validas}

                returning = " RETURNING id" if "id" in colunas_tabela else ""
                res = db.execute(
                    text(f"INSERT INTO {tabela_cli} ({', '.join(cols_validas)}) VALUES ({', '.join(vals_validas)}){returning}"),
                    params
                )
                novo_id = res.scalar() if returning else None
                db.commit()

                return JSONResponse(
                    content={
                        "status": "success",
                        "message": "Cliente cadastrado com sucesso.",
                        "linha": novo_id
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