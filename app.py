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
        CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE, telefone TEXT, doc TEXT, endereco TEXT, cidade TEXT)
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

def carregar_dados(query):
    try: return pd.read_sql_query(query, conn)
    except: return pd.DataFrame()

def carregar_coluna(tabela, coluna):
    try:
        df = pd.read_sql_query(f"SELECT DISTINCT {coluna} FROM {tabela} WHERE {coluna} IS NOT NULL", conn)
        return df[coluna].tolist() if not df.empty else []
    except: return []

def salvar_pedido_ou_venda(cliente, produto, fornecedor, grupo, quantidade, valor_venda, forma_pagamento, valor_recebido, tipo="PEDIDO"):
    cursor = conn.cursor()
    valor_total = quantidade * valor_venda
    data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cod_status = "VEN" if tipo.upper() in ["VENDA", "VENDAS", "VEN"] else "PED"
    cursor.execute("""
        INSERT INTO vendas (cliente, produto, fornecedor, grupo, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, tipo, codigo, data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (cliente.strip(), produto, fornecedor, grupo, quantidade, valor_venda, valor_total, forma_pagamento, str(valor_recebido), tipo, cod_status, data_atual))
    conn.commit()

# -----------------------------------------------------------------------------
# INTERFACE PRINCIPAL
# -----------------------------------------------------------------------------
st.sidebar.title("🔑 Acesso ao Sistema")
perfil_selecionado = st.sidebar.radio("Selecione o Perfil:", ["👤 Portal do Cliente", "🔒 Administração / Vendedor"])

if perfil_selecionado == "👤 Portal do Cliente":
    st.title("🛍️ Portal do Cliente")
    st.info("Faça login na barra lateral para ver seus pedidos.")

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
        
        if menu_admin == "📊 Fechamento & Financeiro":
            st.title("📊 Painel Financeiro & Fechamento")
            df_v = carregar_dados("SELECT * FROM vendas")
            if not df_v.empty:
                st.dataframe(df_v, use_container_width=True)
            else:
                st.info("Nenhuma venda registrada.")

        elif menu_admin in ["🛒 Registrar Venda", "📋 Pedidos / Orçamentos"]:
            st.title(f"📋 {menu_admin}")
            aba_cad, aba_list = st.tabs(["➕ Novo Registro", "✏️ Tabela Editável"])
            
            with aba_list:
                df_registros = carregar_dados("SELECT * FROM vendas")
                if not df_registros.empty:
                    df_registros.insert(0, "Deletar", False)
                    df_editado = st.data_editor(df_registros, use_container_width=True, hide_index=True)
                    
                    c_btn1, c_btn2 = st.columns([1, 1])
                    with c_btn1:
                        if st.button("🔄 Atualizar Valores Totais da Tabela"):
                            st.rerun()
                    with c_btn2:
                        if st.button("💾 Salvar Alterações Feitas na Tabela"):
                            cursor = conn.cursor()
                            for _, row in df_editado.iterrows():
                                if row["Deletar"]:
                                    cursor.execute("DELETE FROM vendas WHERE id = ?", (int(row["id"]),))
                                else:
                                    v_tot = float(row["quantidade"]) * float(row["valor_venda"])
                                    cursor.execute("""UPDATE vendas SET cliente=?, produto=?, quantidade=?, valor_venda=?, valor_total=? WHERE id=?""",
                                                   (str(row["cliente"]), str(row["produto"]), float(row["quantidade"]), float(row["valor_venda"]), v_tot, int(row["id"])))
                            conn.commit()
                            st.success("Salvo com sucesso!")
                            st.rerun()

        elif menu_admin == "📦 Estoque de Produtos":
            st.title("📦 Gestão de Estoque")
            df_prod = carregar_dados("SELECT id, nome, fornecedor, grupo, preco_custo, preco_venda, estoque_atual FROM produtos")
            if not df_prod.empty:
                df_prod.insert(0, "Deletar", False)
                df_prod_edit = st.data_editor(df_prod, hide_index=True, use_container_width=True)
                
                if st.button("💾 Salvar Estoque"):
                    cursor = conn.cursor()
                    for _, row in df_prod_edit.iterrows():
                        if row["Deletar"]:
                            cursor.execute("DELETE FROM produtos WHERE id = ?", (int(row["id"]),))
                        else:
                            cursor.execute("""UPDATE produtos SET nome=?, preco_custo=?, preco_venda=?, estoque_atual=? WHERE id=?""",
                                           (str(row["nome"]), float(row["preco_custo"]), float(row["preco_venda"]), float(row["estoque_atual"]), int(row["id"])))
                    conn.commit()
                    st.success("Estoque atualizado!")
                    st.rerun()

        elif menu_admin == "📥 Entrada de Estoque (Compras)":
            st.title("📥 Entrada de Estoque (Compras)")
            st.info("Módulo de compras e entrada de mercadorias.")

        elif menu_admin == "👥 Cadastros (Clientes / Fornecedores / Grupos)":
            st.title("👥 Cadastros Gerais")
            st.info("Gerenciamento de clientes, fornecedores e grupos.")
