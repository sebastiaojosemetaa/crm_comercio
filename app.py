import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# -----------------------------------------------------------------------------
# CONFIGURAÇÃO E CONEXÃO COM BANCO
# -----------------------------------------------------------------------------
st.set_page_config(page_title="CRM Comércio", layout="wide")

def get_connection():
    return sqlite3.connect("crm_comercio.db", check_same_thread=False)

conn = get_connection()

def carregar_dados(query):
    try:
        return pd.read_sql_query(query, conn)
    except Exception:
        return pd.DataFrame()

def salvar_pedido(cliente, produto, fornecedor, quantidade, valor_venda, forma_pagamento, valor_recebido):
    cursor = conn.cursor()
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
            data TEXT
        )
    """)
    valor_total = quantidade * valor_venda
    data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute("""
        INSERT INTO vendas (cliente, produto, fornecedor, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (cliente, produto, fornecedor, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, data_atual))
    
    conn.commit()

# -----------------------------------------------------------------------------
# INICIALIZAÇÃO DE SESSÃO
# -----------------------------------------------------------------------------
if 'admin_logged' not in st.session_state:
    st.session_state.admin_logged = False

if 'cliente_autenticado' not in st.session_state:
    st.session_state.cliente_autenticado = None

# -----------------------------------------------------------------------------
# SELEÇÃO DE PERFIL
# -----------------------------------------------------------------------------
st.sidebar.title("🔑 Acesso ao Sistema")

opcoes_perfil = ["👤 Portal do Cliente", "🔒 Administração / Vendedor"]
perfil_selecionado = st.sidebar.radio("Selecione o Perfil:", opcoes_perfil)

st.sidebar.markdown("---")

# ==========================================
# 1. PORTAL DO CLIENTE
# ==========================================
if perfil_selecionado == "👤 Portal do Cliente":
    
    if not st.session_state.cliente_autenticado:
        st.title("🔒 Portal do Cliente")
        st.info("Por favor, selecione seu nome no menu à esquerda e insira sua senha para acessar seus pedidos.")
        
        df_cli = carregar_dados("SELECT DISTINCT cliente FROM vendas WHERE cliente IS NOT NULL AND cliente != ''")
        lista_clientes = df_cli['cliente'].tolist() if not df_cli.empty else ["Carlos Alberto", "Sebastião", "Valeilde Loja 01"]
        
        cliente_nome = st.sidebar.selectbox("Identifique seu Nome/Empresa:", lista_clientes)
        senha_cliente = st.sidebar.text_input("Digite sua Senha de Cliente:", type="password")
        
        if st.sidebar.button("Acessar Meus Pedidos"):
            if senha_cliente == "123":
                st.session_state.cliente_autenticado = cliente_nome
                st.rerun()
            else:
                st.sidebar.error("Senha incorreta!")
                
    else:
        st.sidebar.success(f"Logado como:\n**{st.session_state.cliente_autenticado}**")
        if st.sidebar.button("Sair / Trocar Cliente"):
            st.session_state.cliente_autenticado = None
            st.rerun()
            
        st.title(f"🛍️ Portal do Cliente — Meus Pedidos ({st.session_state.cliente_autenticado})")
        
        aba_novo, aba_historico = st.tabs(["➕ Criar Novo Pedido", "📜 Pedidos Registrados & Relatórios"])
        
        with aba_novo:
            st.subheader("➕ Registrar Novo Pedido")
            with st.form("form_novo_pedido_cliente"):
                prod = st.text_input("Produto / Item")
                fornec = st.text_input("Fornecedor", value="BAHIA")
                qtd = st.number_input("Quantidade", min_value=0.1, step=0.5, value=1.0)
                v_unit = st.number_input("Valor Unitário (R$)", min_value=0.0, step=1.0, value=100.0)
                f_pag = st.selectbox("Forma de Pagamento", ["Dinheiro", "Crediário / Fiado", "Pix"])
                
                if st.form_submit_button("Confirmar Pedido"):
                    salvar_pedido(st.session_state.cliente_autenticado, prod, fornec, qtd, v_unit, f_pag, v_unit * qtd)
                    st.success("Pedido registrado com sucesso!")
                    st.rerun()
            
        with aba_historico:
            query_cli = f"SELECT * FROM vendas WHERE cliente = '{st.session_state.cliente_autenticado}'"
            df_pedidos = carregar_dados(query_cli)
            
            if not df_pedidos.empty:
                soma_total = df_pedidos['valor_total'].sum() if 'valor_total' in df_pedidos.columns else 0.0
                st.markdown(f"**Itens Registrados:** {len(df_pedidos)} | **Soma dos Valores:** R$ {soma_total:,.2f}")
                st.dataframe(df_pedidos, use_container_width=True)
            else:
                st.warning("Nenhum pedido encontrado para o seu usuário.")

# ==========================================
# 2. ADMINISTRADOR / VENDEDOR
# ==========================================
elif perfil_selecionado == "🔒 Administração / Vendedor":
    
    if not st.session_state.admin_logged:
        st.title("🔑 Autenticação Administrativa")
        senha_admin = st.sidebar.text_input("Digite a Senha do Admin:", type="password")
        
        if st.sidebar.button("Entrar como Admin"):
            if senha_admin == "1234":
                st.session_state.admin_logged = True
                st.rerun()
            else:
                st.sidebar.error("Senha incorreta!")
                
    else:
        st.sidebar.subheader("🔒 Área Restrita")
        if st.sidebar.button("Sair do Modo Admin"):
            st.session_state.admin_logged = False
            st.rerun()
            
        menu_admin = st.sidebar.radio(
            "Navegação",
            [
                "📊 Fechamento & Financeiro",
                "📋 Pedidos / Orçamentos",
                "🛒 Registrar Venda",
                "📥 Entrada de Estoque (Compras)",
                "📦 Estoque de Produtos",
                "👥 Cadastros (Clientes / Fornecedores / Grupos)"
            ]
        )
        
        if menu_admin == "📊 Fechamento & Financeiro":
            st.title("📊 Painel Financeiro & Fechamento")
            df_vendas = carregar_dados("SELECT * FROM vendas")
            
            if not df_vendas.empty:
                col1, col2, col3 = st.columns(3)
                faturamento = df_vendas['valor_total'].sum() if 'valor_total' in df_vendas.columns else 0.0
                
                col1.metric("Faturamento Total", f"R$ {faturamento:,.2f}")
                col2.metric("Total Recebido em Caixa", f"R$ {faturamento * 0.15:,.2f}")
                col3.metric("Total a Receber (Fiado/Pendente)", f"R$ {faturamento * 0.85:,.2f}")
                
                st.markdown("---")
                st.subheader("📊 Resumo do Histórico de Vendas")
                st.dataframe(df_vendas, use_container_width=True)
            else:
                st.info("Nenhuma venda cadastrada.")

        elif menu_admin in ["📋 Pedidos / Orçamentos", "🛒 Registrar Venda"]:
            st.title(f"📋 {menu_admin}")
            
            aba_cad, aba_list = st.tabs(["➕ Novo Registro / Pedido", "📜 Todos os Pedidos Cadastrados"])
            
            with aba_cad:
                with st.form("form_admin_pedido"):
                    cli = st.text_input("Nome do Cliente", value="Carlos Alberto")
                    prod = st.text_input("Produto")
                    fornec = st.text_input("Fornecedor", value="BAHIA")
                    qtd = st.number_input("Quantidade", min_value=0.1, step=0.5, value=1.0)
                    v_unit = st.number_input("Valor da Venda (R$)", min_value=0.0, step=1.0, value=100.0)
                    f_pag = st.selectbox("Forma de Pagamento", ["Dinheiro", "Crediário / Fiado", "Pix"])
                    v_rec = st.number_input("Valor Recebido (R$)", min_value=0.0, step=1.0, value=0.0)
                    
                    if st.form_submit_button("Salvar Registro"):
                        salvar_pedido(cli, prod, fornec, qtd, v_unit, f_pag, v_rec)
                        st.success("Venda/Pedido gravado no banco de dados!")
                        st.rerun()

            with aba_list:
                df_pedidos = carregar_dados("SELECT * FROM vendas")
                st.dataframe(df_pedidos, use_container_width=True)

        elif menu_admin == "📥 Entrada de Estoque (Compras)":
            st.title("📥 Entrada de Estoque")

        elif menu_admin == "📦 Estoque de Produtos":
            st.title("📦 Estoque de Produtos")
            st.dataframe(carregar_dados("SELECT * FROM produtos"), use_container_width=True)

        elif menu_admin == "👥 Cadastros (Clientes / Fornecedores / Grupos)":
            st.title("👥 Cadastros Gerais")
