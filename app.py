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
# 1. CONFIGURAÇÃO E CONEXÃO
# -----------------------------------------------------------------------------
st.set_page_config(page_title="CRM Comércio - Rey da Cebola", layout="wide")

def get_connection():
    return sqlite3.connect("crm_comercio.db", check_same_thread=False)

conn = get_connection()

# Funções de banco e auxiliares mantidas para integridade...
def adequar_banco_e_migrar():
    cursor = conn.cursor()
    # Tabela de vendas armazena o histórico de operações
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vendas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente TEXT, produto TEXT, fornecedor TEXT, grupo TEXT,
            quantidade REAL, valor_venda REAL, valor_total REAL,
            forma_pagamento TEXT, valor_recebido TEXT,
            tipo TEXT DEFAULT 'PEDIDO', codigo TEXT DEFAULT 'PED',
            data TEXT
        )
    """)
    # Tabela de produtos para custo/preço
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE, fornecedor TEXT, grupo TEXT,
            preco_custo REAL, preco_venda REAL, estoque_atual REAL
        )
    """)
    # ... (demais tabelas clientes, fornecedores, etc permanecem iguais)
    conn.commit()

adequar_banco_e_migrar()

# --- Funções de registro adaptadas para Custo ---
def salvar_registro(cliente, produto, fornecedor, grupo, quantidade, valor, tipo="PEDIDO"):
    """Salva registro focando no valor de custo quando é pedido."""
    cursor = conn.cursor()
    valor_total = quantidade * valor
    data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cod_status = "VEN" if tipo == "VENDA" else "PED"
    
    cursor.execute("""
        INSERT INTO vendas (cliente, produto, fornecedor, grupo, quantidade, valor_venda, valor_total, tipo, codigo, data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (cliente, produto, fornecedor, grupo, quantidade, valor, valor_total, tipo, cod_status, data_atual))
    conn.commit()

# --- Funções de carregamento ---
def carregar_dados(query):
    try: return pd.read_sql_query(query, conn)
    except: return pd.DataFrame()

def carregar_coluna(tabela, coluna):
    df = carregar_dados(f"SELECT DISTINCT {coluna} FROM {tabela}")
    return df[coluna].tolist() if not df.empty else []

# -----------------------------------------------------------------------------
# INTERFACE (TRECHO PEDIDOS / ORÇAMENTOS AJUSTADO)
# -----------------------------------------------------------------------------
# ... (código anterior mantido até a navegação)

# Dentro da parte de "Pedidos / Orçamentos":
# Substituí o formulário para usar o campo 'valor_custo' dos produtos
if 'menu_admin' in locals() and menu_admin == "📋 Pedidos / Orçamentos":
    st.title("📋 Pedidos / Orçamentos (Baseado em Custo)")
    
    with st.form("form_admin_pedido_custo"):
        col1, col2 = st.columns(2)
        with col1:
            prod = st.selectbox("Produto", carregar_coluna("produtos", "nome"))
            # Puxa automaticamente o custo do produto
            custo_atual = carregar_dados(f"SELECT preco_custo FROM produtos WHERE nome = '{prod}'")
            valor_ref = custo_atual.iloc[0,0] if not custo_atual.empty else 0.0
            
            qtd = st.number_input("Quantidade", value=1.0)
            valor_custo_input = st.number_input("Valor de Custo (R$)", value=float(valor_ref))
        with col2:
            cli = st.selectbox("Cliente", carregar_coluna("clientes", "nome"))
            fornec = st.selectbox("Fornecedor", carregar_coluna("fornecedores", "fornecedor"))
            
        if st.form_submit_button("Registrar Pedido de Custo"):
            salvar_registro(cli, prod, fornec, "GERAL", qtd, valor_custo_input, "PEDIDO")
            st.success("Pedido registrado com valor de custo!")

    # Na tabela editável de Pedidos:
    # A lógica de cálculo do valor_total deve usar o valor_custo agora
    st.subheader("Edição de Pedidos")
    df_ped = carregar_dados("SELECT * FROM vendas WHERE tipo = 'PEDIDO'")
    
    # Adicionando botão de recalculo para custo
    if st.button("🔄 Atualizar Totais (Custo x Qtd)"):
        for idx in df_ped.index:
            df_ped.loc[idx, "valor_total"] = df_ped.loc[idx, "quantidade"] * df_ped.loc[idx, "valor_venda"]
        st.rerun()
        
    st.data_editor(df_ped)
