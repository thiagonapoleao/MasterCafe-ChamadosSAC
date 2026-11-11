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

def buscar_primeira_coluna_texto(cur, tabela: str, colunas_preferenciais: list) -> list:
    """Busca registros de uma tabela testando colunas existentes de forma segura."""
    try:
        cur.execute(f"SELECT * FROM {tabela} LIMIT 0")
        colunas_reais = [desc[0].lower() for desc in (cur.description or [])]
        
        col_alvo = None
        for col in colunas_preferenciais:
            if col.lower() in colunas_reais:
                col_alvo = col
                break
        
        if not col_alvo and colunas_reais:
            # Pega a primeira coluna textual ou que não seja 'id'
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

        # autocommit=True evita que erro em uma consulta aborte toda a transação
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
                # A. Descrição -> tabela "produtos"
                descricoes = buscar_primeira_coluna_texto(cur, "produtos", ["descricao", "produto", "nome", "item"])

                # B. Problemas -> tabela "problemas"
                problemas = buscar_primeira_coluna_texto(cur, "problemas", ["problema", "descricao", "nome", "motivo"])

                # C. Formas de Pagamento -> tabela "formas_pgt"
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

        # Fallbacks: se as tabelas auxiliares estiverem vazias, busca históricos existentes em chamados
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
    acao = payload.get("acao") or payload.get("action") or payload.get("tipo")
    
    conn = None
    try:
        conn = get_db_connection(autocommit=False)
        with conn.cursor() as cur:
            # 1. Inserir ou Editar Chamado
            if acao in ["inserir", "editar"]:
                data_parts = str(payload.get("Data", "")).split("/")
                data_sql = f"{data_parts[2]}-{data_parts[1]}-{data_parts[0]}" if len(data_parts) == 3 else datetime.now().strftime("%Y-%m-%d")
                
                dt_tr_parts = str(payload.get("Data da Transação", "")).split("/")
                dt_transacao_sql = f"{dt_tr_parts[2]}-{dt_tr_parts[1]}-{dt_tr_parts[0]}" if len(dt_tr_parts) == 3 else None
                
                if acao == "inserir":
                    cur.execute("""
                        INSERT INTO chamados (chamado, data, cliente, local_interno, cidade, descricao, produto,
                                              data_transacao, hora_transacao, valor, nome_sobrenome, celular,
                                              problemas, forma_pgto, reembolso, pix, atendente, data_hora_lancamento,
                                              reembolso_realizado, financeiro_responsavel, observacao)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        payload.get("Chamado"), data_sql, payload.get("Cliente"), payload.get("Local Interno"),
                        payload.get("Cidade"), payload.get("Descrição"), payload.get("Produto"),
                        dt_transacao_sql, payload.get("Hora da Transação"), payload.get("Valor", 0),
                        payload.get("Nome/Sobrenome"), payload.get("Celular"), payload.get("Problemas"),
                        payload.get("Forma de Pagamento"), payload.get("Reembolso"), payload.get("Pix - Reembolso"),
                        payload.get("Atendente"), payload.get("Data/Hora do lançamento"), payload.get("Reembolso Realizado"),
                        payload.get("Financeiro Responsavel"), payload.get("Observação")
                    ))
                else:
                    cur.execute("""
                        UPDATE chamados SET 
                            data = %s, cliente = %s, local_interno = %s, cidade = %s, descricao = %s, produto = %s,
                            data_transacao = %s, hora_transacao = %s, valor = %s, nome_sobrenome = %s, celular = %s,
                            problemas = %s, forma_pgto = %s, reembolso = %s, pix = %s, atendente = %s,
                            reembolso_realizado = %s, financeiro_responsavel = %s, observacao = %s
                        WHERE chamado = %s
                    """, (
                        data_sql, payload.get("Cliente"), payload.get("Local Interno"),
                        payload.get("Cidade"), payload.get("Descrição"), payload.get("Produto"),
                        dt_transacao_sql, payload.get("Hora da Transação"), payload.get("Valor", 0),
                        payload.get("Nome/Sobrenome"), payload.get("Celular"), payload.get("Problemas"),
                        payload.get("Forma de Pagamento"), payload.get("Reembolso"), payload.get("Pix - Reembolso"),
                        payload.get("Atendente"), payload.get("Reembolso Realizado"),
                        payload.get("Financeiro Responsavel"), payload.get("Observação"),
                        payload.get("Chamado")
                    ))
                conn.commit()
                return {"status": "success"}

            # 2. Excluir Chamado
            elif acao == "excluir":
                chamado_num = payload.get("Chamado") or payload.get("chamado")
                cur.execute("DELETE FROM chamados WHERE chamado = %s", (chamado_num,))
                conn.commit()
                return {"status": "success"}

            # 3. Inserir ou Editar Cliente
            elif acao in ["inserir_cliente", "editar_cliente"]:
                cli = payload.get("Cliente")
                loc = payload.get("Local")
                loc_int = payload.get("Local interno")
                maq = payload.get("Máquina")
                mod = payload.get("Modelo de máquina")
                fil = payload.get("Filial Responsavel")
                
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

            # 4. Excluir Cliente
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
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()

    return {"status": "ignored"}