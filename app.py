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
    # check_same_thread=False é necessário para Streamlit
    return sqlite3.connect("crm_comercio.db", check_same_thread=False)

conn = get_connection()

def inicializar_banco():
    cursor = conn.cursor()
    # Criar todas as tabelas necessárias logo no início
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vendas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente TEXT, produto TEXT, fornecedor TEXT, grupo TEXT,
            quantidade REAL, valor_venda REAL, valor_total REAL,
            forma_pagamento TEXT, valor_recebido TEXT,
            tipo TEXT DEFAULT 'PEDIDO', codigo TEXT DEFAULT 'PED', data TEXT
        )
    """)
    cursor.execute("CREATE TABLE IF NOT EXISTS produtos (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE, fornecedor TEXT, grupo TEXT, preco_custo REAL, preco_venda REAL, estoque_atual REAL)")
    cursor.execute("CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE, telefone TEXT, doc TEXT, endereco TEXT, cidade TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS fornecedores (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE)")
    cursor.execute("CREATE TABLE IF NOT EXISTS grupos (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE)")
    cursor.execute("CREATE TABLE IF NOT EXISTS compras (id INTEGER PRIMARY KEY AUTOINCREMENT, produto TEXT, fornecedor TEXT, grupo TEXT, quantidade REAL, valor_custo REAL, valor_total REAL, data TEXT)")
    conn.commit()

inicializar_banco()

# -----------------------------------------------------------------------------
# FUNÇÕES DE BANCO DE DADOS CORRIGIDAS
# -----------------------------------------------------------------------------

def salvar_simples(tabela, coluna, valor):
    """Versão corrigida para evitar erro de tabela inexistente."""
    cursor = conn.cursor()
    try:
        # Garante que a tabela exista
        cursor.execute(f"CREATE TABLE IF NOT EXISTS {tabela} (id INTEGER PRIMARY KEY AUTOINCREMENT, {coluna} TEXT UNIQUE)")
        conn.commit()
        # Insere o valor
        cursor.execute(f"INSERT INTO {tabela} ({coluna}) VALUES (?)", (valor.strip(),))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    except Exception as e:
        st.error(f"Erro ao salvar em {tabela}: {e}")
        return False

def carregar_dados(query):
    try:
        return pd.read_sql_query(query, conn)
    except Exception:
        return pd.DataFrame()

def carregar_coluna(tabela, coluna):
    df = carregar_dados(f"SELECT DISTINCT {coluna} FROM {tabela} WHERE {coluna} IS NOT NULL AND {coluna} != ''")
    return df[coluna].tolist() if not df.empty else []

def salvar_pedido_ou_venda(cliente, produto, fornecedor, grupo, quantidade, valor_venda, forma_pagamento, valor_recebido, tipo="PEDIDO"):
    cursor = conn.cursor()
    valor_total = quantidade * valor_venda
    data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cod_status = "VEN" if tipo.upper() in ["VENDA", "VEN"] else "PED"
    cursor.execute("""
        INSERT INTO vendas (cliente, produto, fornecedor, grupo, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, tipo, codigo, data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (cliente.strip(), produto, fornecedor, grupo, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, tipo, cod_status, data_atual))
    conn.commit()

# -----------------------------------------------------------------------------
# INTERFACE
# -----------------------------------------------------------------------------
st.sidebar.title("🔑 Acesso ao Sistema")
perfil = st.sidebar.radio("Selecione o Perfil:", ["👤 Portal do Cliente", "🔒 Administração / Vendedor"])

if perfil == "👤 Portal do Cliente":
    st.title("🛍️ Portal do Cliente")
    # ... (restante da lógica do portal)
    st.info("Funcionalidades do portal ativas.")

elif perfil == "🔒 Administração / Vendedor":
    if 'admin_logged' not in st.session_state: st.session_state.admin_logged = False
    
    if not st.session_state.admin_logged:
        senha = st.sidebar.text_input("Senha Admin:", type="password")
        if st.sidebar.button("Entrar"):
            if senha == "1234": st.session_state.admin_logged = True; st.rerun()
    else:
        menu = st.sidebar.radio("Navegação", ["📋 Pedidos", "📦 Estoque", "👥 Cadastros"])
        
        if menu == "👥 Cadastros":
            tab_cli, tab_prod, tab_forn, tab_grup = st.tabs(["Clientes", "Produtos", "Fornecedores", "Grupos"])
            
            with tab_forn:
                st.subheader("Cadastrar Novo Fornecedor")
                with st.form("form_cad_fornecedor"):
                    novo_forn = st.text_input("Nome do Fornecedor")
                    if st.form_submit_button("Salvar Fornecedor"):
                        if salvar_simples("fornecedores", "nome", novo_forn):
                            st.success("Fornecedor salvo!")
                            st.rerun()
                st.dataframe(carregar_dados("SELECT * FROM fornecedores"))

            with tab_grup:
                st.subheader("Cadastrar Novo Grupo")
                with st.form("form_cad_grupo"):
                    novo_grup = st.text_input("Nome do Grupo")
                    if st.form_submit_button("Salvar Grupo"):
                        if salvar_simples("grupos", "nome", novo_grup):
                            st.success("Grupo salvo!")
                            st.rerun()
                st.dataframe(carregar_dados("SELECT * FROM grupos"))

# (Mantenha o restante das suas funções de lógica e PDF abaixo)
