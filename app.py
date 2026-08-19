import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import io
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet

st.set_page_config(page_title="CRM Rey da Cebola", layout="wide")

def get_connection():
    return sqlite3.connect("crm_comercio.db", check_same_thread=False)

conn = get_connection()

# Função para ler dados de forma segura (ignora erro se a tabela não existir)
def ler_tabela_seguro(nome_tabela):
    try:
        return pd.read_sql_query(f"SELECT * FROM {nome_tabela}", conn)
    except:
        return pd.DataFrame() # Retorna dataframe vazio se der erro

# -----------------------------------------------------------------------------
# GERADOR DE PDF
# -----------------------------------------------------------------------------
def gerar_pdf(df_dados):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    elements.append(Paragraph("Relatório de Pedidos", styles['Title']))
    
    # Tenta usar colunas comuns
    cols = [c for c in ['id', 'cliente', 'produto', 'quantidade', 'valor_total', 'data'] if c in df_dados.columns]
    df_pdf = df_dados[cols]
    
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
        df = ler_tabela_seguro("vendas")
        if not df.empty:
            st.dataframe(df, use_container_width=True)
            pdf_data = gerar_pdf(df)
            st.download_button("📥 Baixar PDF", pdf_data, "pedidos.pdf", "application/pdf")
        else:
            st.warning("Nenhum dado encontrado na tabela de vendas.")

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
                try:
                    cursor.execute("INSERT INTO vendas (cliente, produto, quantidade, valor_venda, valor_total, codigo_venda, data, tipo) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                   (cli, prod, qtd, valor, total, cod, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "VENDA"))
                    conn.commit()
                    st.success("Venda registrada!")
                except Exception as e:
                    st.error(f"Erro ao salvar: {e}")

    elif menu == "📦 Estoque de Produtos":
        st.title("📦 Estoque")
        df_prod = ler_tabela_seguro("produtos")
        st.dataframe(df_prod, use_container_width=True)

    elif menu == "🔓 Abertura/Fechamento de Caixa":
        st.title("🔓 Controle de Caixa")
        df_caixa = ler_tabela_seguro("caixa_sessoes")
        if not df_caixa.empty:
            st.dataframe(df_caixa, use_container_width=True)
        else:
            st.info("Nenhuma sessão de caixa registrada.")
        
    elif menu == "👥 Cadastros":
        st.title("👥 Cadastros")
        tab1, tab2 = st.tabs(["Clientes", "Fornecedores"])
        with tab1: st.dataframe(ler_tabela_seguro("clientes"))
        with tab2: st.dataframe(ler_tabela_seguro("fornecedores"))
