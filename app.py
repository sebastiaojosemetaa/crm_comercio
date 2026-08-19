import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import io
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# --- CONFIGURAÇÃO E BANCO DE DADOS ---
st.set_page_config(page_title="CRM Comércio - Rey da Cebola", layout="wide")
conn = sqlite3.connect("crm_comercio.db", check_same_thread=False)

def carregar_dados(query):
    try: return pd.read_sql_query(query, conn)
    except: return pd.DataFrame()

# --- GERADOR DE PDF ---
def gerar_pdf(df_dados):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)
    elements = []
    styles = getSampleStyleSheet()
    elements.append(Paragraph("Relatório de Vendas - Rey da Cebola", styles['Title']))
    elements.append(Spacer(1, 12))
    
    # Prepara dados para tabela
    table_data = [df_dados.columns.tolist()] + df_dados.values.tolist()
    t = Table(table_data)
    t.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 0.5, colors.black), ('FONTSIZE', (0,0), (-1,-1), 8)]))
    elements.append(t)
    doc.build(elements)
    buffer.seek(0)
    return buffer

# --- INTERFACE ---
if 'admin_logged' not in st.session_state: st.session_state.admin_logged = False

if not st.session_state.admin_logged:
    st.title("🔑 Acesso ao Sistema")
    senha = st.sidebar.text_input("Senha Admin:", type="password")
    if st.sidebar.button("Entrar"):
        if senha == "1234":
            st.session_state.admin_logged = True
            st.rerun()
else:
    # A ESTRUTURA ORIGINAL DA BARRA LATERAL RESTAURADA
    menu_admin = st.sidebar.radio(
        "Navegação",
        [
            "🔓 Abertura e Fechamento de Caixa",
            "🛒 PDV — Frente de Caixa",
            "📊 Fechamento & Financeiro",
            "📋 Pedidos / Orçamentos",
            "📥 Entrada de Estoque (Compras)",
            "📦 Estoque de Produtos",
            "👥 Cadastros (Clientes / Fornecedores / Grupos)"
        ]
    )
    if st.sidebar.button("Sair"):
        st.session_state.admin_logged = False
        st.rerun()

    # --- LÓGICA DOS MENUS ---
    if menu_admin == "📋 Pedidos / Orçamentos":
        st.title("📋 Pedidos / Orçamentos")
        df = carregar_dados("SELECT * FROM vendas")
        st.dataframe(df, use_container_width=True)
        if not df.empty:
            st.download_button("📥 Baixar PDF", gerar_pdf(df), "pedidos.pdf", "application/pdf")

    elif menu_admin == "🛒 PDV — Frente de Caixa":
        st.title("🛒 PDV — Frente de Caixa")
        with st.form("form_pdv"):
            col1, col2 = st.columns(2)
            cli = col1.text_input("Cliente")
            prod = col2.text_input("Produto")
            qtd = col1.number_input("Quantidade", value=1.0)
            valor = col2.number_input("Valor Unitário", value=0.0)
            if st.form_submit_button("Finalizar Venda"):
                cursor = conn.cursor()
                cursor.execute("INSERT INTO vendas (cliente, produto, quantidade, valor_venda, valor_total, data, tipo) VALUES (?,?,?,?,?,?,?)",
                               (cli, prod, qtd, valor, qtd*valor, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "VENDA"))
                conn.commit()
                st.success("Venda registrada!")

    elif menu_admin == "📦 Estoque de Produtos":
        st.title("📦 Estoque")
        st.dataframe(carregar_dados("SELECT * FROM produtos"), use_container_width=True)

    elif menu_admin == "🔓 Abertura e Fechamento de Caixa":
        st.title("🔓 Controle de Caixa")
        st.dataframe(carregar_dados("SELECT * FROM caixa_sessoes"), use_container_width=True)
        
    elif menu_admin == "📊 Fechamento & Financeiro":
        st.title("📊 Fechamento & Financeiro")
        st.dataframe(carregar_dados("SELECT * FROM vendas"), use_container_width=True)

    elif menu_admin == "📥 Entrada de Estoque (Compras)":
        st.title("📥 Entrada de Estoque")
        
    elif menu_admin == "👥 Cadastros (Clientes / Fornecedores / Grupos)":
        st.title("👥 Cadastros Gerais")
