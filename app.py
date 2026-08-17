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

def registrar_compra(produto, fornecedor, grupo, quantidade, valor_custo):
    cursor = conn.cursor()
    valor_total = quantidade * valor_custo
    data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO compras (produto, fornecedor, grupo, quantidade, valor_custo, valor_total, data)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (produto, fornecedor, grupo, quantidade, valor_custo, valor_total, data_atual))
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
            st.title("📊 Painel Financeiro & Fechamento por Data")
            col_d1, col_d2, col_d3 = st.columns(3)
            with col_d1: data_inicio = st.date_input("Data Inicial", value=date(2025, 1, 1))
            with col_d2: data_fim = st.date_input("Data Final", value=date.today())
            with col_d3: status_filtro = st.selectbox("Status", ["Todos", "Somente Vendas Concluídas", "Incluir Pedidos Pendentes"])
            
            str_d1 = data_inicio.strftime("%Y-%m-%d")
            str_d2 = data_fim.strftime("%Y-%m-%d")
            
            query_fin = f"SELECT * FROM vendas WHERE (substr(data, 1, 10) >= '{str_d1}' AND substr(data, 1, 10) <= '{str_d2}' OR data IS NULL OR data = '')"
            df_vendas = carregar_dados(query_fin)
            
            if not df_vendas.empty:
                faturamento = df_vendas['valor_total'].sum() if 'valor_total' in df_vendas.columns else 0.0
                st.metric("Faturamento do Período", f"R$ {faturamento:,.2f}")
                st.dataframe(df_vendas, use_container_width=True)
            else:
                st.info("Nenhum registro encontrado para este período.")

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

        elif menu_admin == "📥 Entrada de Estoque (Compras)":
            st.title("📥 Entrada de Estoque (Compras)")
            aba_compra, aba_hist = st.tabs(["➕ Dar Entrada", "📜 Histórico"])
            produtos_opt = carregar_coluna("produtos", "nome") or ["ABACATE"]
            fornecedores_opt = carregar_coluna("fornecedores", "fornecedor") or ["BAHIA"]
            grupos_opt = carregar_coluna("grupos", "grupo") or ["GERAL"]
            
            with aba_compra:
                with st.form("form_compra"):
                    p = st.selectbox("Produto", produtos_opt)
                    f = st.selectbox("Fornecedor", fornecedores_opt)
                    g = st.selectbox("Grupo", grupos_opt)
                    q = st.number_input("Quantidade", min_value=0.1, value=10.0)
                    vc = st.number_input("Valor Custo Unitário", min_value=0.0, value=50.0)
                    if st.form_submit_button("Registrar Entrada"):
                        registrar_compra(p, f, g, q, vc)
                        cursor = conn.cursor()
                        cursor.execute("UPDATE produtos SET estoque_atual = COALESCE(estoque_atual, 0) + ? WHERE TRIM(nome) = TRIM(?)", (q, p))
                        conn.commit()
                        st.success("Entrada registrada!")
                        st.rerun()
            with aba_hist:
                df_c = carregar_dados("SELECT * FROM compras")
                if not df_c.empty: st.dataframe(df_c, use_container_width=True)
                else: st.info("Nenhuma compra registrada.")

        elif menu_admin == "📦 Estoque de Produtos":
            st.title("📦 Gestão de Estoque e Produtos")
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

        elif menu_admin == "👥 Cadastros (Clientes / Fornecedores / Grupos)":
            st.title("👥 Cadastros Gerais")
            aba_cli, aba_forn, aba_grp = st.tabs(["👤 Clientes", "🚚 Fornecedores", "🏷️ Grupos"])
            with aba_cli:
                with st.form("fc"):
                    cn = st.text_input("Nome do Cliente")
                    if st.form_submit_button("Salvar"):
                        if cn:
                            cursor = conn.cursor()
                            cursor.execute("INSERT OR IGNORE INTO clientes (nome) VALUES (?)", (cn,))
                            conn.commit()
                            st.success("Cliente salvo!")
                            st.rerun()
            with aba_forn:
                with st.form("ff"):
                    fn = st.text_input("Nome do Fornecedor")
                    if st.form_submit_button("Salvar"):
                        if fn:
                            cursor = conn.cursor()
                            cursor.execute("INSERT OR IGNORE INTO fornecedores (fornecedor) VALUES (?)", (fn,))
                            conn.commit()
                            st.success("Fornecedor salvo!")
                            st.rerun()
            with aba_grp:
                with st.form("fg"):
                    gn = st.text_input("Nome do Grupo")
                    if st.form_submit_button("Salvar"):
                        if gn:
                            cursor = conn.cursor()
                            cursor.execute("INSERT OR IGNORE INTO grupos (grupo) VALUES (?)", (gn,))
                            conn.commit()
                            st.success("Grupo salvo!")
                            st.rerun()
