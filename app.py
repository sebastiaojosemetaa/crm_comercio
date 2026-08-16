import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# -----------------------------------------------------------------------------
# 1. CONFIGURAÇÃO E CONEXÃO COM O BANCO DE DADOS
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

def carregar_coluna(tabela, coluna):
    """Busca uma coluna específica do banco e retorna em lista limpa."""
    df = carregar_dados(f"SELECT DISTINCT {coluna} FROM {tabela} WHERE {coluna} IS NOT NULL AND {coluna} != ''")
    if not df.empty:
        return df[coluna].tolist()
    return []

def salvar_pedido(cliente, produto, fornecedor, grupo, quantidade, valor_venda, forma_pagamento, valor_recebido):
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vendas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente TEXT,
            produto TEXT,
            fornecedor TEXT,
            grupo TEXT,
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
        INSERT INTO vendas (cliente, produto, fornecedor, grupo, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (cliente, produto, fornecedor, grupo, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, data_atual))
    
    conn.commit()

# -----------------------------------------------------------------------------
# 2. INICIALIZAÇÃO DE SESSÃO
# -----------------------------------------------------------------------------
if 'admin_logged' not in st.session_state:
    st.session_state.admin_logged = False

if 'cliente_autenticado' not in st.session_state:
    st.session_state.cliente_autenticado = None

# -----------------------------------------------------------------------------
# 3. BARRA LATERAL: SELEÇÃO DE PERFIL
# -----------------------------------------------------------------------------
st.sidebar.title("🔑 Acesso ao Sistema")

opcoes_perfil = ["👤 Portal do Cliente", "🔒 Administração / Vendedor"]
perfil_selecionado = st.sidebar.radio("Selecione o Perfil:", opcoes_perfil)

st.sidebar.markdown("---")

# ==========================================
# AMBIENTE 1: PORTAL DO CLIENTE
# ==========================================
if perfil_selecionado == "👤 Portal do Cliente":
    
    if not st.session_state.cliente_autenticado:
        st.title("🔒 Portal do Cliente")
        st.info("Por favor, selecione seu nome no menu à esquerda e insira sua senha para acessar seus pedidos.")
        
        # Busca lista de clientes cadastrados
        lista_clientes = carregar_coluna("vendas", "cliente") or carregar_coluna("clientes", "nome") or ["Carlos Alberto", "Sebastião"]
        
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
            
            # Carrega listas do banco
            produtos_opt = carregar_coluna("produtos", "nome") or carregar_coluna("vendas", "produto") or ["AMEIXA IMPORTADA", "ABACATE", "CEBOLA CAIXA 1"]
            fornecedores_opt = carregar_coluna("fornecedores", "nome") or carregar_coluna("vendas", "fornecedor") or ["BAHIA"]
            grupos_opt = carregar_coluna("grupos", "nome") or carregar_coluna("vendas", "grupo") or ["GERAL"]
            
            with st.form("form_novo_pedido_cliente"):
                prod = st.selectbox("Selecione o Produto", produtos_opt)
                fornec = st.selectbox("Selecione o Fornecedor", fornecedores_opt)
                grupo = st.selectbox("Selecione o Grupo", grupos_opt)
                
                qtd = st.number_input("Quantidade", min_value=0.1, step=0.5, value=1.0)
                v_unit = st.number_input("Valor Unitário (R$)", min_value=0.0, step=1.0, value=100.0)
                f_pag = st.selectbox("Forma de Pagamento", ["Dinheiro", "Crediário / Fiado", "Pix"])
                
                if st.form_submit_button("Confirmar Pedido"):
                    salvar_pedido(st.session_state.cliente_autenticado, prod, fornec, grupo, qtd, v_unit, f_pag, v_unit * qtd)
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
# AMBIENTE 2: ADMINISTRADOR / VENDEDOR
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
                # Carregamento de listas cadastradas no banco
                clientes_opt = carregar_coluna("clientes", "nome") or carregar_coluna("vendas", "cliente") or ["Carlos Alberto", "Sebastião", "Valeilde Loja 01"]
                produtos_opt = carregar_coluna("produtos", "nome") or carregar_coluna("vendas", "produto") or ["AMEIXA IMPORTADA", "ABACATE", "CEBOLA CAIXA 1"]
                fornecedores_opt = carregar_coluna("fornecedores", "nome") or carregar_coluna("vendas", "fornecedor") or ["BAHIA"]
                grupos_opt = carregar_coluna("grupos", "nome") or carregar_coluna("vendas", "grupo") or ["GERAL"]
                
                with st.form("form_admin_pedido"):
                    col_a, col_b = st.columns(2)
                    with col_a:
                        cli = st.selectbox("Selecione o Cliente", clientes_opt)
                        prod = st.selectbox("Selecione o Produto", produtos_opt)
                        qtd = st.number_input("Quantidade", min_value=0.1, step=0.5, value=1.0)
                        v_unit = st.number_input("Valor da Venda (R$)", min_value=0.0, step=1.0, value=100.0)
                    
                    with col_b:
                        fornec = st.selectbox("Selecione o Fornecedor", fornecedores_opt)
                        grupo = st.selectbox("Selecione o Grupo", grupos_opt)
                        f_pag = st.selectbox("Forma de Pagamento", ["Dinheiro", "Crediário / Fiado", "Pix"])
                        v_rec = st.number_input("Valor Recebido (R$)", min_value=0.0, step=1.0, value=0.0)
                    
                    if st.form_submit_button("Salvar Registro"):
                        salvar_pedido(cli, prod, fornec, grupo, qtd, v_unit, f_pag, v_rec)
                        st.success("Venda/Pedido gravado no banco de dados com sucesso!")
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
