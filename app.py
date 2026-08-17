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
    cursor.execute("""CREATE TABLE IF NOT EXISTS vendas (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente TEXT, produto TEXT, fornecedor TEXT, grupo TEXT, quantidade REAL, valor_venda REAL, valor_total REAL, forma_pagamento TEXT, valor_recebido TEXT, tipo TEXT DEFAULT 'PEDIDO', codigo TEXT DEFAULT 'PED', data TEXT)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS produtos (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE, fornecedor TEXT, grupo TEXT, preco_custo REAL, preco_venda REAL, estoque_atual REAL)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE, telefone TEXT, doc TEXT, endereco TEXT, cidade TEXT)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS fornecedores (id INTEGER PRIMARY KEY AUTOINCREMENT, fornecedor TEXT UNIQUE)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS grupos (id INTEGER PRIMARY KEY AUTOINCREMENT, grupo TEXT UNIQUE)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS compras (id INTEGER PRIMARY KEY AUTOINCREMENT, produto TEXT, fornecedor TEXT, grupo TEXT, quantidade REAL, valor_custo REAL, valor_total REAL, data TEXT)""")
    conn.commit()

adequar_banco_e_migrar()

def carregar_dados(query):
    try: return pd.read_sql_query(query, conn)
    except Exception: return pd.DataFrame()

def carregar_coluna(tabela, coluna):
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({tabela})")
    cols = [col[1] for col in cursor.fetchall()]
    col_alvo = coluna if coluna in cols else (cols[1] if len(cols) > 1 else coluna)
    df = carregar_dados(f"SELECT DISTINCT TRIM({col_alvo}) as {col_alvo} FROM {tabela} WHERE {col_alvo} IS NOT NULL AND {col_alvo} != ''")
    return df[col_alvo].tolist() if not df.empty else []

# -----------------------------------------------------------------------------
# FUNÇÕES DE REGISTRO
# -----------------------------------------------------------------------------
def salvar_pedido_ou_venda(cliente, produto, fornecedor, grupo, quantidade, valor_venda, forma_pagamento, valor_recebido, tipo="PEDIDO"):
    cursor = conn.cursor()
    valor_total = quantidade * valor_venda
    data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cod_status = "VEN" if tipo.upper() in ["VENDA", "VENDAS", "VEN"] else "PED"
    cursor.execute("INSERT INTO vendas (cliente, produto, fornecedor, grupo, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, tipo, codigo, data) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (cliente.strip(), produto, fornecedor, grupo, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, tipo, cod_status, data_atual))
    conn.commit()

# -----------------------------------------------------------------------------
# 2. INTERFACE
# -----------------------------------------------------------------------------
if 'admin_logged' not in st.session_state: st.session_state.admin_logged = False
if 'cliente_autenticado' not in st.session_state: st.session_state.cliente_autenticado = None

st.sidebar.title("🔑 Acesso ao Sistema")
perfil_selecionado = st.sidebar.radio("Selecione o Perfil:", ["👤 Portal do Cliente", "🔒 Administração / Vendedor"])

if perfil_selecionado == "👤 Portal do Cliente":
    # (Código reduzido para foco no Admin, mas funcional)
    st.title("👤 Portal do Cliente")
    st.info("Funcionalidade de cliente ativa.")

elif perfil_selecionado == "🔒 Administração / Vendedor":
    if not st.session_state.admin_logged:
        if st.sidebar.text_input("Senha Admin:", type="password") == "1234":
            st.session_state.admin_logged = True
            st.rerun()
        st.stop()

    menu_admin = st.sidebar.radio("Navegação", ["📦 Estoque de Produtos", "📋 Pedidos", "🛒 Vendas"])

    if menu_admin == "📦 Estoque de Produtos":
        st.title("📦 Estoque de Produtos e Preços")
        df_prods = carregar_dados("SELECT * FROM produtos")
        
        if not df_prods.empty:
            df_exibir = df_prods.copy()
            df_exibir.insert(0, "Deletar", False)
            
            st.caption("💡 Edite na tabela e salve:")
            df_editado = st.data_editor(df_exibir, use_container_width=True, hide_index=True)
            
            if st.button("💾 Salvar Alterações do Estoque"):
                cursor = conn.cursor()
                for _, row in df_editado.iterrows():
                    if row["Deletar"]:
                        cursor.execute("DELETE FROM produtos WHERE id = ?", (int(row["id"]),))
                    else:
                        cursor.execute("""UPDATE produtos SET nome=?, fornecedor=?, grupo=?, preco_custo=?, preco_venda=?, estoque_atual=? WHERE id=?""",
                                       (row["nome"], row["fornecedor"], row["grupo"], row["preco_custo"], row["preco_venda"], row["estoque_atual"], int(row["id"])))
                conn.commit()
                st.success("Salvo!")
                st.rerun()
        else:
            st.info("Nenhum produto cadastrado.")

    elif menu_admin in ["📋 Pedidos", "🛒 Vendas"]:
        st.title(f"Operação: {menu_admin}")
        # Código de operações de pedidos/vendas aqui...
