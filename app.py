import os
import json
import base64
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import psycopg
from psycopg.rows import dict_row

app = FastAPI(title="Painel Executivo de Gestão & SAC")

# Localização absoluta do diretório templates para evitar erro no deploy
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Conexão padrão com fallback para variável de ambiente DATABASE_URL
DEFAULT_DB_URL = "postgresql://postgres:[YOUR-PASSWORD]@db.asptoykwjnpxwvnixslw.supabase.co:5432/postgres"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DB_URL)

def get_db_connection():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=15)

def obter_logo_base64():
    nomes_alvo = ["Logotipo.PNG", "Logotipo.png", "logotipo.PNG", "logotipo.png", "logo.png"]
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
        n = float(val)
        return f"R$ {n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"

@app.get("/", response_class=HTMLResponse)
async def carregar_pagina_principal(request: Request):
    logo_base64_src = obter_logo_base64()
    
    usuarios = []
    lista_clientes = []
    formas_pgto = []
    problemas = []
    descricoes = []
    chamados_raw = []
    
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # 1. Usuários
                cur.execute("SELECT nome, usuario, senha, acesso FROM usuarios")
                usuarios = cur.fetchall() or []
                
                # 2. Clientes
                cur.execute("""
                    SELECT id as linha, cliente, local, local_interno as "localInterno", 
                           maquina, modelo_maquina as "modeloMaquina", 
                           filial_responsavel as "filialResponsavel" 
                    FROM clientes 
                    ORDER BY cliente ASC
                """)
                lista_clientes = cur.fetchall() or []
                
                # 3. Configurações
                cur.execute("SELECT tipo, valor FROM sac_configs")
                configs = cur.fetchall() or []
                formas_pgto = [c["valor"] for c in configs if c.get("tipo") == "forma_pagamento"]
                problemas = [c["valor"] for c in configs if c.get("tipo") == "problema"]
                descricoes = [c["valor"] for c in configs if c.get("tipo") == "descricao"]
                
                # 4. Chamados
                cur.execute("""
                    SELECT id as linha, chamado, 
                           to_char(data, 'DD/MM/YYYY') as data,
                           cliente, local_interno as "localInterno", cidade, descricao, produto,
                           to_char(data_transacao, 'DD/MM/YYYY') as "dataTransacao",
                           hora_transacao as "horaTransacao", valor, nome_sobrenome as "nomeSobrenome",
                           celular, problemas, forma_pgto as "formaPgto", reembolso, pix,
                           atendente, data_hora_lancamento as "dataHoraLancamento",
                           reembolso_realizado as "reembolsoRealizado",
                           financeiro_responsavel as "financeiroResponsavel",
                           observacao
                    FROM chamados 
                    ORDER BY id DESC
                """)
                chamados_raw = cur.fetchall() or []
    except Exception as e:
        return HTMLResponse(
            content=f"""
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 2.5rem; max-width: 650px; margin: 3rem auto; background: #fff; border: 1px solid #e2e8f0; border-radius: 1rem; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1);">
                <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1rem;">
                    <div style="background: #fee2e2; color: #dc2626; padding: 0.5rem; border-radius: 0.5rem; font-size: 1.5rem;">⚠️</div>
                    <h2 style="color: #0f172a; margin: 0; font-size: 1.25rem;">Falha ao Conectar com o Banco SQL</h2>
                </div>
                <p style="color: #475569; font-size: 0.875rem; line-height: 1.5;">O servidor FastAPI não conseguiu estabelecer conexão com o PostgreSQL do Supabase. Detalhes técnicos retornados:</p>
                <pre style="background: #0f172a; color: #f87171; padding: 1rem; border-radius: 0.5rem; font-size: 0.75rem; overflow-x: auto; margin: 1rem 0;">{str(e)}</pre>
                <div style="background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 0.5rem; padding: 0.875rem; font-size: 0.8125rem; color: #334155;">
                    <strong>O que fazer:</strong><br>
                    1. Verifique se configurou a variável de ambiente <code>DATABASE_URL</code> no painel do <strong>Render (Environment)</strong>.<br>
                    2. Certifique-se de substituir o trecho <code>[YOUR-PASSWORD]</code> pela sua senha real definida no Supabase.
                </div>
            </div>
            """, 
            status_code=500
        )

    # Organização de dados para o Frontend
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

    dados_sac = {
        "clientes": [{"cliente": c["cliente"], "local": c.get("localInterno", ""), "cidade": c.get("filialResponsavel", "")} for c in lista_clientes],
        "cadastro_clientes": lista_clientes,
        "formas_pagamento": sorted(list(set(formas_pgto))),
        "cidades": sorted(list(set([c["filialResponsavel"] for c in lista_clientes if c.get("filialResponsavel")]))),
        "problemas": sorted(list(set(problemas))),
        "descricoes": sorted(list(set(descricoes))),
        "usuarios": usuarios,
        "maior_sac_ano": maior_sac_ano,
        "chamados": chamados_formatados
    }
    
    dados_sac_json = json.dumps(dados_sac, default=str, ensure_ascii=False)
    total_chamados = len(chamados_formatados)
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "logo_base64_src": logo_base64_src,
        "dados_sac_json": dados_sac_json,
        "total_chamados_carregados": total_chamados
    })

# Endpoint para Operações CRUD
@app.post("/api/action")
async def processar_acao_api(payload: Dict[str, Any]):
    acao = payload.get("acao") or payload.get("action") or payload.get("tipo")
    
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Inserir ou Editar Chamado
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

                # Excluir Chamado
                elif acao == "excluir":
                    chamado_num = payload.get("Chamado") or payload.get("chamado")
                    cur.execute("DELETE FROM chamados WHERE chamado = %s", (chamado_num,))
                    conn.commit()
                    return {"status": "success"}

                # Inserir ou Editar Cliente
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

                # Excluir Cliente
                elif acao == "excluir_cliente":
                    linha_id = payload.get("linha")
                    if linha_id:
                        cur.execute("DELETE FROM clientes WHERE id = %s", (linha_id,))
                    else:
                        cur.execute("DELETE FROM clientes WHERE cliente = %s AND local_interno = %s", (payload.get("Cliente"), payload.get("Local interno")))
                    conn.commit()
                    return {"status": "success"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"status": "ignored"}