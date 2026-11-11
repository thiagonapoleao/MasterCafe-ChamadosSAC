import pandas as pd
from sqlalchemy import create_engine

# Cole a URI completa do seu banco Supabase
DATABASE_URL = "postgresql://postgres.asptoykwjnpxwvnixslw:napoleao140205@aws-1-us-east-1.pooler.supabase.com:6543/postgres"

# Nome do seu arquivo CSV local
NOME_ARQUIVO = "dados.csv"

# Nome exato da tabela no Supabase (se tiver maiúsculas, precisa bater)
NOME_TABELA = "Chamados"

print("1. Lendo arquivo CSV...")
df = pd.read_csv(NOME_ARQUIVO)

# REGRA DE OURO: Remova a coluna 'id' se o banco já gera automaticamente,
# para evitar o erro de chave primária duplicada
if "id" in df.columns:
    df = df.drop(columns=["id"])

print(f"Total de linhas carregadas na memória: {len(df)}")

print("2. Conectando ao Supabase...")
engine = create_engine(DATABASE_URL)

print("3. Enviando dados em blocos de 1.000 linhas...")
df.to_sql(
    name=NOME_TABELA,
    con=engine,
    if_exists="append",  # Insere sem apagar o que já existe
    index=False,
    chunksize=1000,
    method="multi"
)

print("✅ Sucesso! Todas as 11.000 linhas foram inseridas.")