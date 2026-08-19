import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import io
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

st.set_page_config(page_title="CRM Rey da Cebola", layout="wide")

def get_connection():
    return sqlite3.connect("crm_comercio.db", check_same_thread=False)

conn = get_connection()

def garantir_estrutura_banco():
    cursor = conn.cursor()
    # Tabela principal de vendas/pedidos com todas as colunas necessárias
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vendas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente TEXT,
            produto TEXT,
            fornecedor TEXT,
            quantidade REAL,
            valor_venda REAL,
            valor_total REAL,
            forma_pagamento TEXT,
            valor_recebido REAL,
            troco REAL,
            restante REAL,
            data TEXT,
            grupo TEXT,
            codigo_venda TEXT,
            tipo TEXT
        )
    """)
    conn.commit()

garantir_estrutura_banco()

# Funções auxiliares
def carregar_dados(query):
    return pd.read_sql_query(query, conn)

# -----------------------------------------------------------------------------
# GERADOR DE PDF
# -----------------------------------------------------------------------------
def gerar_pdf(df_dados):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    elements.append(Paragraph("Relatório de Pedidos - Rey da Cebola", styles['Title']))
    
    data = [df_dados.columns.tolist()] + df_dados.values.tolist()
    t = Table(data)
    t.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 0.5, colors.black)]))
    elements.append(t)
    doc.build(elements)
    buffer.seek(0)
    return buffer

# -----------------------------------------------------------------------------
# INTERFACE
# -----------------------------------------------------------------------------
if 'admin_logged' not in st.session_state: st.session_state.admin_logged = False

if not st.session_state.admin_logged:
    senha = st.sidebar.text_input("Senha Admin", type="password")
    if st.sidebar.button("Entrar"):
        if senha == "1234":
            st.session_state.admin_logged = True
            st.rerun()
else:
    menu = st.sidebar.radio("Menu", ["📋 Pedidos / Orçamentos", "🛒 PDV"])

    if menu == "📋 Pedidos / Orçamentos":
        st.title("📋 Pedidos / Orçamentos")
        df = carregar_dados("SELECT * FROM vendas")
        st.dataframe(df, use_container_width=True)
        
        if not df.empty:
            pdf_data = gerar_pdf(df)
            st.download_button("📥 Baixar PDF dos Pedidos", pdf_data, "pedidos.pdf", "application/pdf")

    elif menu == "🛒 PDV":
        st.title("🛒 Nova Venda / Pedido")
        with st.form("form_venda"):
            cli = st.text_input("Cliente")
            prod = st.text_input("Produto")
            qtd = st.number_input("Quantidade", value=1.0)
            valor = st.number_input("Valor Unitário", value=0.0)
            tipo = st.selectbox("Tipo", ["PEDIDO", "VENDA"])
            
            if st.form_submit_button("Salvar Registro"):
                cursor = conn.cursor()
                total = qtd * valor
                cod = f"{tipo[:3]}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                cursor.execute("""
                    INSERT INTO vendas (cliente, produto, quantidade, valor_venda, valor_total, tipo, codigo_venda, data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (cli, prod, qtd, valor, total, tipo, cod, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                conn.commit()
                st.success("Salvo com sucesso!")
