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
    return sqlite3.connect("crm_comercio.db", check_same_thread=False)

conn = get_connection()

def adequar_banco_e_migrar():
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vendas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente TEXT, produto TEXT, fornecedor TEXT, grupo TEXT,
            quantidade REAL, valor_venda REAL, valor_total REAL,
            forma_pagamento TEXT, valor_recebido TEXT,
            tipo TEXT DEFAULT 'PEDIDO', codigo TEXT DEFAULT 'PED', data TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE, fornecedor TEXT, grupo TEXT,
            preco_custo REAL, preco_venda REAL, estoque_atual REAL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE)
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fornecedores (id INTEGER PRIMARY KEY AUTOINCREMENT, fornecedor TEXT UNIQUE)
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS grupos (id INTEGER PRIMARY KEY AUTOINCREMENT, grupo TEXT UNIQUE)
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS compras (id INTEGER PRIMARY KEY AUTOINCREMENT, produto TEXT, fornecedor TEXT, grupo TEXT, quantidade REAL, valor_custo REAL, valor_total REAL, data TEXT)
    """)
    conn.commit()

adequar_banco_e_migrar()

# -----------------------------------------------------------------------------
# FUNÇÕES AUXILIARES
# -----------------------------------------------------------------------------
def carregar_dados(query):
    try: return pd.read_sql_query(query, conn)
    except: return pd.DataFrame()

def carregar_coluna(tabela, coluna):
    try:
        df = pd.read_sql_query(f"SELECT DISTINCT {coluna} FROM {tabela} WHERE {coluna} IS NOT NULL", conn)
        return df[coluna].tolist() if not df.empty else []
    except: return []

# -----------------------------------------------------------------------------
# INTERFACE PRINCIPAL
# -----------------------------------------------------------------------------
st.sidebar.title("🔑 Acesso ao Sistema")
perfil_selecionado = st.sidebar.radio("Selecione o Perfil:", ["👤 Portal do Cliente", "🔒 Administração / Vendedor"])

if perfil_selecionado == "👤 Portal do Cliente":
    st.title("🛍️ Portal do Cliente")
    st.info("Acesse a área administrativa para visualizar o sistema.")

elif perfil_selecionado == "🔒 Administração / Vendedor":
    if 'admin_logged' not in st.session_state: st.session_state.admin_logged = False
    
    if not st.session_state.admin_logged:
        senha = st.sidebar.text_input("Senha Admin:", type="password")
        if st.sidebar.button("Entrar"):
            if senha == "1234": st.session_state.admin_logged = True; st.rerun()
    else:
        menu_admin = st.sidebar.radio("Navegação", [
            "📊 Fechamento & Financeiro",
            "🛒 Registrar Venda",
            "📋 Pedidos / Orçamentos",
            "📥 Entrada de Estoque (Compras)",
            "📦 Estoque de Produtos",
            "👥 Cadastros (Clientes / Fornecedores / Grupos)"
        ])
        
        # --- TELA FINANCEIRO ---
        if menu_admin == "📊 Fechamento & Financeiro":
            st.title("📊 Painel Financeiro")
            c1, c2 = st.columns(2)
            d_inicio = c1.date_input("Data Inicial", value=date(2025, 1, 1))
            d_fim = c2.date_input("Data Final", value=date.today())
            
            query = f"SELECT * FROM vendas WHERE date(data) BETWEEN '{d_inicio}' AND '{d_fim}'"
            df = carregar_dados(query)
            if not df.empty:
                st.metric("Total Vendido", f"R$ {df['valor_total'].sum():,.2f}")
                st.dataframe(df, use_container_width=True)
            else: st.info("Nenhum dado no período.")

        # --- TELA VENDAS/PEDIDOS ---
        elif menu_admin in ["🛒 Registrar Venda", "📋 Pedidos / Orçamentos"]:
            st.title(f"📋 {menu_admin}")
            tabs = st.tabs(["➕ Novo Registro", "✏️ Tabela Editável"])
            
            with tabs[0]:
                with st.form("form_venda"):
                    cli = st.selectbox("Cliente", carregar_coluna("clientes", "nome") or ["Geral"])
                    prod = st.selectbox("Produto", carregar_coluna("produtos", "nome") or ["Produto"])
                    qtd = st.number_input("Quantidade", value=1.0)
                    v_uni = st.number_input("Valor Unitário", value=0.0)
                    if st.form_submit_button("Salvar Venda"):
                        data_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        conn.execute("INSERT INTO vendas (cliente, produto, quantidade, valor_venda, valor_total, data) VALUES (?,?,?,?,?,?)",
                                     (cli, prod, qtd, v_uni, qtd * v_uni, data_str))
                        conn.commit()
                        st.rerun()
            
            with tabs[1]:
                df = carregar_dados("SELECT * FROM vendas")
                if not df.empty: st.data_editor(df, use_container_width=True)

        # --- TELA ESTOQUE ---
        elif menu_admin == "📦 Estoque de Produtos":
            st.title("📦 Estoque de Produtos")
            tabs = st.tabs(["📋 Lista de Produtos", "➕ Novo Produto"])
            with tabs[1]:
                with st.form("form_prod"):
                    nome = st.text_input("Nome")
                    v_custo = st.number_input("Custo")
                    v_venda = st.number_input("Venda")
                    if st.form_submit_button("Cadastrar"):
                        conn.execute("INSERT INTO produtos (nome, preco_custo, preco_venda) VALUES (?,?,?)", (nome, v_custo, v_venda))
                        conn.commit()
                        st.rerun()
            with tabs[0]:
                df = carregar_dados("SELECT * FROM produtos")
                if not df.empty: st.data_editor(df, use_container_width=True)

        # --- TELA COMPRAS ---
        elif menu_admin == "📥 Entrada de Estoque (Compras)":
            st.title("📥 Entrada de Estoque")
            with st.form("form_compra"):
                p = st.selectbox("Produto", carregar_coluna("produtos", "nome") or [])
                q = st.number_input("Quantidade", value=1.0)
                if st.form_submit_button("Registrar Entrada"):
                    conn.execute("UPDATE produtos SET estoque_atual = estoque_atual + ? WHERE nome = ?", (q, p))
                    conn.commit()
                    st.success("Estoque atualizado!")
