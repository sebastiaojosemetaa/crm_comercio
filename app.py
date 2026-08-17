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

def inicializar_banco():
    cursor = conn.cursor()
    # Tabelas base
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vendas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente TEXT, produto TEXT, fornecedor TEXT, grupo TEXT,
            quantidade REAL, valor_venda REAL, valor_total REAL,
            forma_pagamento TEXT, valor_recebido TEXT,
            tipo TEXT, codigo TEXT, data TEXT
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
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE, 
            telefone TEXT, doc TEXT, endereco TEXT, cidade TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fornecedores (id INTEGER PRIMARY KEY AUTOINCREMENT, fornecedor TEXT UNIQUE)
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS grupos (id INTEGER PRIMARY KEY AUTOINCREMENT, grupo TEXT UNIQUE)
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS compras (
            id INTEGER PRIMARY KEY AUTOINCREMENT, produto TEXT, fornecedor TEXT,
            grupo TEXT, quantidade REAL, valor_custo REAL, valor_total REAL, data TEXT
        )
    """)
    conn.commit()

inicializar_banco()

# -----------------------------------------------------------------------------
# FUNÇÕES AUXILIARES
# -----------------------------------------------------------------------------
def carregar_dados(query):
    try: return pd.read_sql_query(query, conn)
    except: return pd.DataFrame()

def carregar_coluna(tabela, coluna):
    df = carregar_dados(f"SELECT DISTINCT {coluna} FROM {tabela} WHERE {coluna} IS NOT NULL")
    return df[coluna].tolist() if not df.empty else []

# -----------------------------------------------------------------------------
# INTERFACE PRINCIPAL
# -----------------------------------------------------------------------------
st.sidebar.title("🔑 Acesso ao Sistema")
perfil = st.sidebar.radio("Selecione o Perfil:", ["👤 Portal do Cliente", "🔒 Administração / Vendedor"])

if perfil == "👤 Portal do Cliente":
    st.title("🛍️ Portal do Cliente")
    st.info("Funcionalidade em desenvolvimento.")

elif perfil == "🔒 Administração / Vendedor":
    if 'admin_logged' not in st.session_state: st.session_state.admin_logged = False
    
    if not st.session_state.admin_logged:
        senha = st.sidebar.text_input("Senha Admin:", type="password")
        if st.sidebar.button("Entrar"):
            if senha == "1234": st.session_state.admin_logged = True; st.rerun()
    else:
        menu = st.sidebar.radio("Navegação", ["🛒 Registrar Venda", "📦 Estoque de Produtos"])
        
        if menu == "🛒 Registrar Venda":
            st.title("📋 Edição Direta de Vendas")
            
            # Filtro
            df_registros = carregar_dados("SELECT * FROM vendas")
            if not df_registros.empty:
                df_registros.insert(0, "Deletar", False)
                
                # Editor com cálculo automático embutido
                df_editado = st.data_editor(
                    df_registros,
                    column_config={
                        "Deletar": st.column_config.CheckboxColumn(default=False),
                        "valor_total": st.column_config.NumberColumn(disabled=True, format="R$ %.2f"),
                        "valor_venda": st.column_config.NumberColumn(format="R$ %.2f")
                    },
                    hide_index=True, use_container_width=True
                )
                
                # Recalcula totais automaticamente
                for idx in df_editado.index:
                    df_editado.loc[idx, "valor_total"] = float(df_editado.loc[idx, "quantidade"]) * float(df_editado.loc[idx, "valor_venda"])
                
                if st.button("💾 Salvar Alterações na Tabela"):
                    cursor = conn.cursor()
                    for _, row in df_editado.iterrows():
                        if row["Deletar"]:
                            cursor.execute("DELETE FROM vendas WHERE id = ?", (int(row["id"]),))
                        else:
                            cursor.execute("""UPDATE vendas SET cliente=?, produto=?, quantidade=?, valor_venda=?, valor_total=? WHERE id=?""",
                                           (str(row["cliente"]), str(row["produto"]), float(row["quantidade"]), float(row["valor_venda"]), float(row["valor_total"]), int(row["id"])))
                    conn.commit()
                    st.success("Dados salvos!")
                    st.rerun()

        elif menu == "📦 Estoque de Produtos":
            st.title("📦 Gestão de Estoque")
            df_prod = carregar_dados("SELECT * FROM produtos")
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
