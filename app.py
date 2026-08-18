import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date
import io
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# -----------------------------------------------------------------------------
# 1. CONFIGURAÇÃO E CONEXÃO COM O BANCO DE DADOS
# -----------------------------------------------------------------------------
st.set_page_config(page_title="CRM Comércio - Rey da Cebola", layout="wide")

def get_connection():
    return sqlite3.connect("./crm_comercio.db", check_same_thread=False)

conn = get_connection()

def adequar_banco_e_migrar():
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vendas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente TEXT,
            produto TEXT,
            fornecedor TEXT,
            grupo TEXT,
            quantidade REAL,
            valor_venda REAL,
            valor_total REAL,
            forma_pagamento TEXT,
            valor_recebido REAL,
            troco REAL DEFAULT 0,
            restante REAL DEFAULT 0,
            tipo TEXT DEFAULT 'PEDIDO',
            codigo TEXT DEFAULT 'PED',
            data TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE,
            fornecedor TEXT,
            grupo TEXT,
            preco_custo REAL,
            preco_venda REAL,
            estoque_atual REAL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE,
            telefone TEXT,
            doc TEXT,
            endereco TEXT,
            cidade TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fornecedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fornecedor TEXT UNIQUE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS grupos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grupo TEXT UNIQUE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS compras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            produto TEXT,
            fornecedor TEXT,
            grupo TEXT,
            quantidade REAL,
            valor_custo REAL,
            valor_total REAL,
            data TEXT
        )
    """)
    conn.commit()

try:
    adequar_banco_e_migrar()
except Exception as e:
    st.error(f"Erro ao inicializar o Banco de Dados: {e}")

# -----------------------------------------------------------------------------
# 2. FUNÇÕES DE SUPORTE E CONSULTAS DO BANCO
# -----------------------------------------------------------------------------
def carregar_dados(query, params=()):
    try:
        return pd.read_sql_query(query, conn, params=params)
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")
        return pd.DataFrame()

def carregar_coluna(tabela, coluna):
    try:
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info({tabela})")
        cols = [col for col in cursor.fetchall()]
        col_alvo = coluna if coluna in cols else (cols if len(cols) > 1 else coluna)
        
        df = carregar_dados(f"SELECT DISTINCT TRIM({col_alvo}) as {col_alvo} FROM {tabela} WHERE {col_alvo} IS NOT NULL AND {col_alvo} != ''")
        if not df.empty:
            return df[col_alvo].tolist()
    except Exception:
        pass
    return []

def obter_preco_produto(nome_produto, campo="preco_venda"):
    try:
        cursor = conn.cursor()
        cursor.execute(f"SELECT {campo} FROM produtos WHERE TRIM(nome) = TRIM(?)", (nome_produto.strip(),))
        res = cursor.fetchone()
        return res if res else 0.0
    except Exception:
        return 0.0

# -----------------------------------------------------------------------------
# 3. FUNÇÕES DE SALVAMENTO E ATUALIZAÇÃO EM LOTE
# -----------------------------------------------------------------------------
def salvar_cliente_completo(nome, telefone, doc, endereco, city):
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO clientes (nome, telefone, doc, endereco, cidade) VALUES (?, ?, ?, ?, ?)",
                       (nome.strip(), telefone, doc, endereco, city))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def salvar_produto_completo(nome, fornecedor, group, preco_custo, preco_venda, estoque_inicial):
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO produtos (nome, fornecedor, grupo, preco_custo, preco_venda, estoque_atual) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (nome.strip(), fornecedor, group, preco_custo, preco_venda, estoque_inicial))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        cursor.execute("""
            UPDATE produtos 
            SET fornecedor = ?, grupo = ?, preco_custo = ?, preco_venda = ?, estoque_atual = ?
            WHERE TRIM(nome) = TRIM(?)
        """, (fornecedor, group, preco_custo, preco_venda, estoque_inicial, nome.strip()))
        conn.commit()
        return True

def salvar_alteracoes_lote_vendas(df_editado):
    cursor = conn.cursor()
    for _, row in df_editado.iterrows():
        if "Deletar" in row and row["Deletar"] == True:
            cursor.execute("DELETE FROM vendas WHERE id = ?", (int(row["id"]),))
        else:
            qtd = float(row.get("quantidade", 0))
            v_venda = float(row.get("valor_venda", 0))
            v_total = qtd * v_venda
            
            try:
                v_recebido = float(row.get("valor_recebido", 0))
            except:
                v_recebido = 0.0
                
            troco = max(0.0, v_recebido - v_total)
            restante = max(0.0, v_total - v_recebido)
            
            cursor.execute("""
                UPDATE vendas 
                SET quantidade = ?, valor_venda = ?, valor_total = ?, 
                    forma_pagamento = ?, valor_recebido = ?, troco = ?, restante = ?
                WHERE id = ?
            """, (qtd, v_venda, v_total, str(row.get("forma_pagamento", "Dinheiro")), v_recebido, troco, restante, int(row["id"])))
    conn.commit()

def salvar_alteracoes_lote_compras(df_editado):
    cursor = conn.cursor()
    for _, row in df_editado.iterrows():
        if "Deletar" in row and row["Deletar"] == True:
            cursor.execute("DELETE FROM compras WHERE id = ?", (int(row["id"]),))
        else:
            qtd = float(row.get("quantidade", 0))
            v_custo = float(row.get("valor_custo", 0))
            v_total = qtd * v_custo
            cursor.execute("""
                UPDATE compras 
                SET quantidade = ?, valor_custo = ?, valor_total = ?
                WHERE id = ?
            """, (qtd, v_custo, v_total, int(row["id"])))
    conn.commit()

def salvar_pedido_ou_venda(cliente, produto, fornecedor, group, quantidade, valor_venda, forma_pagamento, valor_recebido, tipo="PEDIDO"):
    cursor = conn.cursor()
    valor_total = quantity = quantidade * valor_venda
    try:
        v_rec = float(valor_recebido)
    except:
        v_rec = 0.0
    troco = max(0.0, v_rec - valor_total)
    restante = max(0.0, valor_total - v_rec)
    data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cod_status = "VEN" if tipo.upper() in ["VENDA", "VENDAS", "VEN"] else "PED"
    
    cursor.execute("""
        INSERT INTO vendas (cliente, produto, fornecedor, grupo, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, troco, restante, tipo, codigo, data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (cliente.strip(), produto, fornecedor, group, quantidade, valor_venda, valor_total, forma_pagamento, v_rec, troco, restante, tipo, cod_status, data_atual))
    conn.commit()

# -----------------------------------------------------------------------------
# 4. INTERFACE DO USUÁRIO (STREAMLIT)
# -----------------------------------------------------------------------------
st.sidebar.title("🔑 Acesso ao Sistema")
perfil = st.sidebar.radio("Selecione o Perfil:", ["Portal do Cliente", "Administração/Vendedor"])

if perfil == "Administração/Vendedor":
    st.sidebar.markdown("### 🖥️ Área Restrita")
    navegacao = st.sidebar.radio(
        "Navegação",
        ["📊 Fechamento & Financeiro", "📌 Pedidos / Orçamentos", "🛒 Registrar Venda", "📦 Entrada de Estoque (Compras)", "🥦 Estoque de Produtos", "🗂️ Cadastros"]
    )

    # -------------------------------------------------------------------------
    # TELA: FECHAMENTO & FINANCEIRO
    # -------------------------------------------------------------------------
    if navegacao == "📊 Fechamento & Financeiro":
        st.title("📊 Painel de Fechamento Financeiro")
        st.markdown("Visualização simplificada de rendimentos e cálculo de lucro líquido real.")

        df_vendas_fin = carregar_dados("SELECT produto, quantidade, valor_total FROM vendas WHERE tipo = 'VENDA'")
        
        faturamento_bruto = 0.0
        custo_total_mercadoria = 0.0

        if not df_vendas_fin.empty:
            faturamento_bruto = df_vendas_fin["valor_total"].sum()
            for idx, row in df_vendas_fin.iterrows():
                preco_custo_unidade = obter_preco_produto(row["produto"], "preco_custo")
                custo_total_mercadoria += row["whitespace"] = row["quantidade"] * preco_custo_unidade

        lucro_liquido = faturamento_bruto - custo_total_mercadoria

        m1, m2, m3 = st.columns(3)
        m1.metric(label="📈 Faturamento Bruto (Vendas)", value=f"R$ {faturamento_bruto:,.2f}")
