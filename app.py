import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import io
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet

st.set_page_config(page_title="CRM Rey da Cebola", layout="wide")

def get_connection():
    return sqlite3.connect("crm_comercio.db", check_same_thread=False)

conn = get_connection()

# -----------------------------------------------------------------------------
# GERADOR DE PDF
# -----------------------------------------------------------------------------
def gerar_pdf(df_dados):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    elements.append(Paragraph("Relatório de Pedidos - Rey da Cebola", styles['Title']))
    
    # Seleciona colunas principais para o PDF
    colunas_pdf = ['id', 'cliente', 'produto', 'quantidade', 'valor_total', 'data']
    df_pdf = df_dados[colunas_pdf]
    
    data = [df_pdf.columns.tolist()] + df_pdf.values.tolist()
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
    st.title("Login de Administração")
    senha = st.text_input("Senha", type="password")
    if st.button("Entrar"):
        if senha == "1234":
            st.session_state.admin_logged = True
            st.rerun()
else:
    menu = st.sidebar.radio("Menu Principal", [
        "📋 Pedidos / Orçamentos", 
        "🛒 PDV — Frente de Caixa", 
        "📦 Estoque de Produtos",
        "🔓 Abertura/Fechamento de Caixa",
        "👥 Cadastros"
    ])

    if menu == "📋 Pedidos / Orçamentos":
        st.title("📋 Pedidos / Orçamentos")
        df = pd.read_sql_query("SELECT * FROM vendas", conn)
        st.dataframe(df, use_container_width=True)
        if not df.empty:
            pdf_data = gerar_pdf(df)
            st.download_button("📥 Baixar PDF dos Pedidos", pdf_data, "pedidos.pdf", "application/pdf")

    elif menu == "🛒 PDV — Frente de Caixa":
        st.title("🛒 PDV — Frente de Caixa")
        with st.form("form_pdv"):
            cli = st.text_input("Cliente")
            prod = st.text_input("Produto")
            qtd = st.number_input("Quantidade", value=1.0)
            valor = st.number_input("Valor Unitário", value=0.0)
            if st.form_submit_button("Finalizar Venda"):
                cursor = conn.cursor()
                total = qtd * valor
                cod = f"PED-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                cursor.execute("""
                    INSERT INTO vendas (cliente, produto, quantidade, valor_venda, valor_total, codigo_venda, data, tipo)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (cli, prod, qtd, valor, total, cod, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "VENDA"))
                conn.commit()
                st.success("Venda registrada com sucesso!")

    elif menu == "📦 Estoque de Produtos":
        st.title("📦 Estoque")
        df_prod = pd.read_sql_query("SELECT * FROM produtos", conn)
        st.dataframe(df_prod, use_container_width=True)

    elif menu == "🔓 Abertura/Fechamento de Caixa":
        st.title("🔓 Controle de Caixa")
        df_caixa = pd.read_sql_query("SELECT * FROM caixa_sessoes", conn)
        st.dataframe(df_caixa, use_container_width=True)
        
    elif menu == "👥 Cadastros":
        st.title("👥 Cadastros")
        tab1, tab2 = st.tabs(["Clientes", "Fornecedores"])
        with tab1: st.dataframe(pd.read_sql_query("SELECT * FROM clientes", conn))
        with tab2: st.dataframe(pd.read_sql_query("SELECT * FROM fornecedores", conn))
