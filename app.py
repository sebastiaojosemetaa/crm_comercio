import streamlit as st
import sqlite3
import pandas as pd

# -----------------------------------------------------------------------------
# 1. CONFIGURAÇÃO E CONEXÃO COM O BANCO DE DADOS
# -----------------------------------------------------------------------------
st.set_page_config(page_title="CRM Comércio", layout="wide")

def get_connection():
    # Ajuste o nome do arquivo .db para o seu banco SQLite real se for diferente
    return sqlite3.connect("crm_comercio.db", check_same_thread=False)

conn = get_connection()

def carregar_dados(query):
    try:
        return pd.read_sql_query(query, conn)
    except Exception:
        return pd.DataFrame()

# -----------------------------------------------------------------------------
# 2. INICIALIZAÇÃO DE ESTADOS DE SESSÃO
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
    
    # 1.1 CLIENTE NÃO AUTENTICADO
    if not st.session_state.cliente_autenticado:
        st.title("🔒 Portal do Cliente")
        st.info("Por favor, selecione seu nome no menu à esquerda e insira sua senha para acessar seus pedidos.")
        
        # Busca lista de clientes no banco
        df_cli = carregar_dados("SELECT DISTINCT cliente FROM vendas WHERE cliente IS NOT NULL AND cliente != ''")
        lista_clientes = df_cli['cliente'].tolist() if not df_cli.empty else ["Carlos Alberto"]
        
        cliente_nome = st.sidebar.selectbox("Identifique seu Nome/Empresa:", lista_clientes)
        senha_cliente = st.sidebar.text_input("Digite sua Senha de Cliente:", type="password")
        
        if st.sidebar.button("Acessar Meus Pedidos"):
            # Validação simples (pode ser ajustada para consultar tabela de senhas do SQLite)
            if senha_cliente == "123":
                st.session_state.cliente_autenticado = cliente_nome
                st.rerun()
            else:
                st.sidebar.error("Senha incorreta!")

    # 1.2 CLIENTE AUTENTICADO
    else:
        st.sidebar.success(f"Logado como:\n**{st.session_state.cliente_autenticado}**")
        if st.sidebar.button("Sair / Trocar Cliente"):
            st.session_state.cliente_autenticado = None
            st.rerun()
            
        st.title(f"🛍️ Portal do Cliente — Meus Pedidos ({st.session_state.cliente_autenticado})")
        
        # Consulta apenas as vendas/pedidos do cliente logado
        query_cli = f"SELECT * FROM vendas WHERE cliente = '{st.session_state.cliente_autenticado}'"
        df_pedidos = carregar_dados(query_cli)
        
        if not df_pedidos.empty:
            total_itens = len(df_pedidos)
            
            # Tenta calcular o valor total tratando a coluna se existir
            col_valor = [c for c in df_pedidos.columns if 'valor' in c.lower() or 'total' in c.lower()]
            soma_total = df_pedidos[col_valor[0]].sum() if col_valor else 0.0
            
            st.markdown(f"**Itens Registrados:** {total_itens} | **Soma dos Valores:** R$ {soma_total:,.2f}")
            st.dataframe(df_pedidos, use_container_width=True)
        else:
            st.warning("Nenhum pedido encontrado para o seu usuário.")


# ==========================================
# AMBIENTE 2: ADMINISTRAÇÃO / VENDEDOR
# ==========================================
elif perfil_selecionado == "🔒 Administração / Vendedor":
    
    # 2.1 ADMIN NÃO LOGADO
    if not st.session_state.admin_logged:
        st.title("🔑 Autenticação Administrativa")
        senha_admin = st.sidebar.text_input("Digite a Senha do Admin:", type="password")
        
        if st.sidebar.button("Entrar como Admin"):
            if senha_admin == "1234":  # <--- Altere para a sua senha de Admin preferida
                st.session_state.admin_logged = True
                st.rerun()
            else:
                st.sidebar.error("Senha incorreta!")
                
    # 2.2 ADMIN LOGADO
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
        
        # ---------------------------------------------------------------------
        # PAGINAS INTERNAS DO ADMIN
        # ---------------------------------------------------------------------
        if menu_admin == "📊 Fechamento & Financeiro":
            st.title("📊 Painel Financeiro & Fechamento")
            
            df_vendas = carregar_dados("SELECT * FROM vendas")
            if not df_vendas.empty:
                col1, col2, col3 = st.columns(3)
                
                # Procura colunas de valor
                col_val = [c for c in df_vendas.columns if 'valor' in c.lower() or 'total' in c.lower()]
                faturamento = df_vendas[col_val[0]].sum() if col_val else 0.0
                
                col1.metric("Faturamento Total", f"R$ {faturamento:,.2f}")
                col2.metric("Total Recebido em Caixa", f"R$ {faturamento * 0.15:,.2f}") # Exemplo
                col3.metric("Total a Receber (Fiado/Pendente)", f"R$ {faturamento * 0.85:,.2f}") # Exemplo
                
                st.markdown("---")
                st.subheader("📊 Resumo do Histórico de Vendas")
                st.dataframe(df_vendas, use_container_width=True)
            else:
                st.info("Nenhuma venda cadastrada no banco de dados.")

        elif menu_admin == "📋 Pedidos / Orçamentos":
            st.title("📋 Pedidos / Orçamentos")
            df_pedidos = carregar_dados("SELECT * FROM vendas")
            st.dataframe(df_pedidos, use_container_width=True)

        elif menu_admin == "🛒 Registrar Venda":
            st.title("🛒 Registrar Venda")
            st.info("Formulário de lançamento de vendas aqui.")

        elif menu_admin == "📥 Entrada de Estoque (Compras)":
            st.title("📥 Entrada de Estoque")
            st.info("Formulário de compras e reposição de estoque aqui.")

        elif menu_admin == "📦 Estoque de Produtos":
            st.title("📦 Estoque de Produtos")
            df_estoque = carregar_dados("SELECT * FROM produtos") if 'produtos' in carregar_dados("SELECT name FROM sqlite_master WHERE type='table'")['name'].values else pd.DataFrame()
            st.dataframe(df_estoque, use_container_width=True)

        elif menu_admin == "👥 Cadastros (Clientes / Fornecedores / Grupos)":
            st.title("👥 Cadastros Gerais")
            st.info("Gerenciamento de Clientes, Fornecedores e Grupos.")
