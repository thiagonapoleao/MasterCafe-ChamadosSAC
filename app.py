import os
import json
import base64
import traceback
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import psycopg
from psycopg.rows import dict_row

app = FastAPI(title="Painel Executivo de Gestão & SAC")

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

DEFAULT_DB_URL = "postgresql://postgres.asptoykwjnpxwvnixslw:[SUA-SENHA]@aws-0-sa-east-1.pooler.supabase.com:5432/postgres"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DB_URL)

def get_db_connection(autocommit: bool = False):
    return psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=15, autocommit=autocommit)

def obter_logo_base64():
    nomes_alvo = [
        "Logotipo.PNG", "Logotipo.png", "logotipo.PNG", "logotipo.png",
        "LOGOTIPO.PNG", "logo.PNG", "logo.png"
    ]
    for nome in nomes_alvo:
        caminho = BASE_DIR / nome
        if caminho.is_file():
            ext = caminho.suffix.lower().replace(".", "")
            mime = "jpeg" if ext in ["jpg", "jpeg"] else "png"
            with open(caminho, "rb") as f:
                return f"data:image/{mime};base64,{base64.b64encode(f.read()).decode('utf-8')}"
    return ""

def format_currency_br(val):
    try:
        n = float(val) if val is not None else 0.0
        return f"R$ {n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"

def converter_para_data_iso(data_str: Any) -> Optional[str]:
    """Converte datas em DD/MM/AAAA ou YYYY-MM-DD para YYYY-MM-DD aceito pelo Postgres."""
    if not data_str:
        return None
    s = str(data_str).strip()
    if not s or s.lower() in ["none", "null"]:
        return None
    if len(s) >= 10 and s[4] == '-' and s[7] == '-':
        return s[:10]
    partes = s.split("/")
    if len(partes) == 3 and len(partes[2]) == 4:
        return f"{partes[2]}-{partes[1].zfill(2)}-{partes[0].zfill(2)}"
    return None

def buscar_primeira_coluna_texto(cur, tabela: str, colunas_preferenciais: list) -> list:
    """Carrega dados para datalists de forma segura sem abortar a transação caso colunas mudem."""
    try:
        cur.execute(f"SELECT * FROM {tabela} LIMIT 0")
        colunas_reais = [desc[0].lower() for desc in (cur.description or [])]
        col_alvo = next((col for col in colunas_preferenciais if col.lower() in colunas_reais), None)
        if not col_alvo and colunas_reais:
            candidatos = [c for c in colunas_reais if c != 'id']
            col_alvo = candidatos[0] if candidatos else colunas_reais[0]
        if col_alvo:
            cur.execute(f"SELECT DISTINCT {col_alvo} AS valor FROM {tabela} WHERE {col_alvo} IS NOT NULL AND TRIM({col_alvo}::text) <> '' ORDER BY 1 ASC")
            return [str(r["valor"]).strip() for r in (cur.fetchall() or []) if str(r.get("valor", "")).strip()]
    except Exception:
        pass
    return []

@app.get("/", response_class=HTMLResponse)
async def carregar_pagina_principal(request: Request):
    logo_base64_src = obter_logo_base64()
    
    try:
        usuarios = []
        lista_clientes = []
        formas_pgto = []
        problemas = []
        descricoes = []
        chamados_raw = []

        # autocommit=True evita que eventuais erros em consultas secundárias abortem o carregamento
        with get_db_connection(autocommit=True) as conn:
            with conn.cursor() as cur:
                # 1. Usuários
                try:
                    cur.execute("SELECT nome, usuario, senha, acesso FROM usuarios")
                    usuarios = [dict(u) for u in (cur.fetchall() or [])]
                except Exception:
                    usuarios = []
                
                # 2. Clientes
                try:
                    cur.execute("""
                        SELECT id as linha, 
                               COALESCE(cliente, '') as cliente, 
                               COALESCE(local, '') as local, 
                               COALESCE(local_interno, '') as "localInterno", 
                               COALESCE(maquina, '') as maquina, 
                               COALESCE(modelo_maquina, '') as "modeloMaquina", 
                               COALESCE(filial_responsavel, '') as "filialResponsavel" 
                        FROM clientes 
                        ORDER BY cliente ASC
                    """)
                    lista_clientes = [dict(c) for c in (cur.fetchall() or [])]
                except Exception:
                    lista_clientes = []
                
                # 3. Listas dinâmicas a partir das tabelas dedicadas
                descricoes = buscar_primeira_coluna_texto(cur, "produtos", ["descricao", "produto", "nome", "item"])
                problemas = buscar_primeira_coluna_texto(cur, "problemas", ["problema", "descricao", "nome", "motivo"])
                formas_pgto = buscar_primeira_coluna_texto(cur, "formas_pgt", ["forma_pgt", "forma", "descricao", "nome"])
                
                # 4. Chamados
                cur.execute("""
                    SELECT id as linha, 
                           COALESCE(chamado, '') as chamado, 
                           COALESCE(to_char(data, 'DD/MM/YYYY'), '') as data,
                           COALESCE(cliente, '') as cliente, 
                           COALESCE(local_interno, '') as "localInterno", 
                           COALESCE(cidade, '') as cidade, 
                           COALESCE(descricao, '') as descricao, 
                           COALESCE(produto, '') as produto, 
                           COALESCE(to_char(data_transacao, 'DD/MM/YYYY'), '') as "dataTransacao", 
                           COALESCE(hora_transacao, '') as "horaTransacao", 
                           COALESCE(valor, 0) as valor, 
                           COALESCE(nome_sobrenome, '') as "nomeSobrenome", 
                           COALESCE(celular, '') as celular, 
                           COALESCE(problemas, '') as problemas, 
                           COALESCE(forma_pgto, '') as "formaPgto", 
                           COALESCE(reembolso, '') as reembolso, 
                           COALESCE(pix, '') as pix, 
                           COALESCE(atendente, '') as atendente, 
                           COALESCE(data_hora_lancamento, '') as "dataHoraLancamento", 
                           COALESCE(reembolso_realizado, 'Não') as "reembolsoRealizado", 
                           COALESCE(financeiro_responsavel, '') as "financeiroResponsavel", 
                           COALESCE(observacao, '') as observacao
                    FROM chamados 
                    ORDER BY id DESC
                """)
                chamados_raw = cur.fetchall() or []

        # Fallbacks: se tabelas auxiliares estiverem vazias, preenche com histórico da tabela chamados
        if not descricoes:
            descricoes = sorted(list(set([str(c.get("descricao", "")).strip() for c in chamados_raw if str(c.get("descricao", "")).strip()])))
        if not problemas:
            problemas = sorted(list(set([str(c.get("problemas", "")).strip() for c in chamados_raw if str(c.get("problemas", "")).strip()])))
        if not formas_pgto:
            formas_pgto = sorted(list(set([str(c.get("formaPgto", "")).strip() for c in chamados_raw if str(c.get("formaPgto", "")).strip()])))

        maior_sac_ano = {}
        chamados_formatados = []
        for c in chamados_raw:
            item = dict(c)
            item["valor"] = format_currency_br(item.get("valor", 0))
            chamados_formatados.append(item)
            
            ch_str = str(item.get("chamado", ""))
            if ch_str.startswith("SAC-"):
                partes = ch_str.split("-")
                if len(partes) == 3 and partes[2].isdigit():
                    ano, seq = partes[1], int(partes[2])
                    maior_sac_ano[ano] = max(maior_sac_ano.get(ano, 0), seq)

        cidades = sorted(list(set([c["filialResponsavel"] for c in lista_clientes if c.get("filialResponsavel")])))
        
        dados_sac = {
            "clientes": [{"cliente": c.get("cliente", ""), "local": c.get("localInterno", ""), "cidade": c.get("filialResponsavel", "")} for c in lista_clientes],
            "cadastro_clientes": lista_clientes,
            "formas_pagamento": sorted(list(set(formas_pgto))),
            "formas_pgt": sorted(list(set(formas_pgto))),
            "produtos": sorted(list(set(descricoes))),
            "descricoes": sorted(list(set(descricoes))),
            "problemas": sorted(list(set(problemas))),
            "cidades": cidades,
            "usuarios": usuarios,
            "maior_sac_ano": maior_sac_ano,
            "chamados": chamados_formatados
        }
        
        dados_sac_json = json.dumps(dados_sac, default=str, ensure_ascii=False)
        total_chamados = len(chamados_formatados)
        
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "logo_base64_src": logo_base64_src,
                "dados_sac_json": dados_sac_json,
                "total_chamados_carregados": total_chamados
            }
        )

    except Exception as e:
        tb = traceback.format_exc()
        return HTMLResponse(
            content=f"""
            <div style="font-family: monospace; padding: 2rem; background: #0f172a; color: #f87171; min-height: 100vh;">
                <h2 style="color: #ef4444; margin-top: 0;">Traceback do Erro:</h2>
                <pre style="white-space: pre-wrap; word-break: break-all; font-size: 13px; line-height: 1.5;">{tb}</pre>
            </div>
            """,
            status_code=500
        )

@app.post("/api/action")
async def processar_acao_api(payload: Dict[str, Any]):
    acao = (payload.get("acao") or payload.get("action") or payload.get("tipo") or "").lower()
    
    conn = None
    try:
        conn = get_db_connection(autocommit=False)
        with conn.cursor() as cur:
            
            # =========================================================================
            # 1. INSERIR OU EDITAR NA TABELA "chamados"
            # =========================================================================
            if acao in ["inserir", "editar"]:
                chamado_num = str(payload.get("Chamado") or payload.get("chamado") or "").strip()
                if not chamado_num:
                    raise ValueError("O identificador do chamado é obrigatório.")

                # Tratamento de datas
                data_br = payload.get("Data") or payload.get("data")
                data_sql = converter_para_data_iso(data_br) or datetime.now().strftime("%Y-%m-%d")

                dt_tr = payload.get("Data da Transação") or payload.get("data_transacao") or payload.get("dataTransacao")
                dt_transacao_sql = converter_para_data_iso(dt_tr)

                hr_tr = payload.get("Hora da Transação") or payload.get("hora_transacao") or payload.get("horaTransacao")
                hr_tr = str(hr_tr).strip() if hr_tr and str(hr_tr).strip() else None

                # Conversão de valores monetários
                val_raw = payload.get("Valor") if "Valor" in payload else payload.get("valor", 0)
                try:
                    if isinstance(val_raw, str):
                        val_raw = val_raw.replace("R$", "").replace(".", "").replace(",", ".").strip()
                    valor_sql = float(val_raw) if val_raw else 0.0
                except Exception:
                    valor_sql = 0.0

                # Dicionário normalizado
                dados_registro = {
                    "chamado": chamado_num,
                    "data": data_sql,
                    "cliente": payload.get("Cliente") or payload.get("cliente") or "",
                    "local_interno": payload.get("Local Interno") or payload.get("local_interno") or payload.get("localInterno") or "",
                    "cidade": payload.get("Cidade") or payload.get("cidade") or "",
                    "descricao": payload.get("Descrição") or payload.get("descricao") or "",
                    "produto": payload.get("Produto") or payload.get("produto") or "",
                    "data_transacao": dt_transacao_sql,
                    "hora_transacao": hr_tr,
                    "valor": valor_sql,
                    "nome_sobrenome": payload.get("Nome/Sobrenome") or payload.get("Nome Sobrenome") or payload.get("nome_sobrenome") or "",
                    "celular": payload.get("Celular") or payload.get("celular") or "",
                    "problemas": payload.get("Problemas") or payload.get("problemas") or "",
                    "forma_pgto": payload.get("Forma de Pagamento") or payload.get("forma_pgto") or payload.get("formaPgto") or "",
                    "reembolso": payload.get("Reembolso") or payload.get("reembolso") or "",
                    "pix": payload.get("Pix - Reembolso") or payload.get("pix") or "",
                    "atendente": payload.get("Atendente") or payload.get("atendente") or "",
                    "data_hora_lancamento": payload.get("Data/Hora do lançamento") or payload.get("data_hora_lancamento") or datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                    "reembolso_realizado": payload.get("Reembolso Realizado") or payload.get("reembolso_realizado") or "Não",
                    "financeiro_responsavel": payload.get("Financeiro Responsavel") or payload.get("financeiro_responsavel") or "",
                    "observacao": payload.get("Observação") or payload.get("observacao") or ""
                }

                # Inspeciona as colunas existentes na tabela chamados
                cur.execute("SELECT * FROM chamados LIMIT 0")
                colunas_tabela = [desc[0] for desc in (cur.description or [])]
                colunas_map = {c.lower(): c for c in colunas_tabela}

                col_chamado = colunas_map.get("chamado", "chamado")
                cur.execute(f'SELECT id FROM chamados WHERE "{col_chamado}" = %s', (chamado_num,))
                ja_existe = cur.fetchone()

                if acao == "inserir" and not ja_existe:
                    cols_inserir = []
                    valores_inserir = []
                    placeholders = []

                    for k, val in dados_registro.items():
                        if k in colunas_map:
                            nome_real = colunas_map[k]
                            cols_inserir.append(f'"{nome_real}"')
                            valores_inserir.append(val)
                            placeholders.append("%s")

                    query = f"""
                        INSERT INTO chamados ({', '.join(cols_inserir)})
                        VALUES ({', '.join(placeholders)})
                    """
                    cur.execute(query, tuple(valores_inserir))
                else:
                    sets = []
                    valores_update = []
                    for k, val in dados_registro.items():
                        if k != "chamado" and k in colunas_map:
                            nome_real = colunas_map[k]
                            sets.append(f'"{nome_real}" = %s')
                            valores_update.append(val)

                    valores_update.append(chamado_num)
                    query = f"""
                        UPDATE chamados SET {', '.join(sets)}
                        WHERE "{col_chamado}" = %s
                    """
                    cur.execute(query, tuple(valores_update))

                conn.commit()
                return {"status": "success", "message": f"Chamado {chamado_num} gravado com sucesso."}

            # =========================================================================
            # 2. EXCLUIR NA TABELA "chamados"
            # =========================================================================
            elif acao in ["excluir", "excluir_sac"]:
                chamado_num = str(payload.get("Chamado") or payload.get("chamado") or "").strip()
                if not chamado_num:
                    raise ValueError("Número do chamado ausente para exclusão.")

                cur.execute("SELECT * FROM chamados LIMIT 0")
                colunas_tabela = [desc[0] for desc in (cur.description or [])]
                colunas_map = {c.lower(): c for c in colunas_tabela}
                col_chamado = colunas_map.get("chamado", "chamado")

                cur.execute(f'DELETE FROM chamados WHERE "{col_chamado}" = %s', (chamado_num,))
                conn.commit()
                return {"status": "success", "message": f"Chamado {chamado_num} removido com sucesso."}

            # =========================================================================
            # 3. CLIENTES
            # =========================================================================
            elif acao in ["inserir_cliente", "editar_cliente"]:
                cli = payload.get("Cliente")
                loc = payload.get("Local")
                loc_int = payload.get("Local interno") or payload.get("local_interno")
                maq = payload.get("Máquina") or payload.get("maquina")
                mod = payload.get("Modelo de máquina") or payload.get("modelo_maquina")
                fil = payload.get("Filial Responsavel") or payload.get("filial_responsavel")

                if acao == "inserir_cliente":
                    cur.execute("""
                        INSERT INTO clientes (cliente, local, local_interno, maquina, modelo_maquina, filial_responsavel)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (cli, loc, loc_int, maq, mod, fil))
                else:
                    cur.execute("""
                        UPDATE clientes SET cliente=%s, local=%s, local_interno=%s, maquina=%s, modelo_maquina=%s, filial_responsavel=%s
                        WHERE id = %s
                    """, (cli, loc, loc_int, maq, mod, fil, payload.get("linha")))
                conn.commit()
                return {"status": "success"}

            elif acao == "excluir_cliente":
                linha_id = payload.get("linha")
                if linha_id:
                    cur.execute("DELETE FROM clientes WHERE id = %s", (linha_id,))
                else:
                    cur.execute("DELETE FROM clientes WHERE cliente = %s AND local_interno = %s", (payload.get("Cliente"), payload.get("Local interno")))
                conn.commit()
                return {"status": "success"}

    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        erro_detalhado = traceback.format_exc()
        print(f"ERRO SQL /api/action: {erro_detalhado}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()

    return {"status": "ignored"}