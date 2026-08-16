import streamlit as st
import pandas as pd

# -----------------------------------------------------------------------------
# CONFIGURAÇÃO DA PÁGINA E ESTADOS DA SESSÃO
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Sistema de Vendas & CRM", layout="wide")

if 'admin_logged' not in st.session_state:
    st.session_state.admin_logged = False

if 'cliente_autenticado' not in st.session_state:
    st.session_state.cliente_autenticado = None

# Exemplo de carregamento/mock dos dados de clientes (Ajuste para o seu DataFrame se usar banco de dados)
if 'df_clientes' not in st.session_state:
    st.session_state.df_clientes = pd.DataFrame({
        'nome': ['Carlos Alberto', 'Sebastião', 'Valeilde Loja 01'],
        'senha': ['123', '123', '123']  # Senhas dos clientes
    })

df_clientes = st.session_state.df_clientes

# -----------------------------------------------------------------------------
# MENU LATERAL - SELEÇÃO DE PERFIL
# -----------------------------------------------------------------------------
st.sidebar.title("🔑 Acesso ao Sistema")

opcoes_perfil = ["👤 Portal do Cliente", "🔒 Administração / Vendedor"]
perfil_selecionado = st.sidebar.radio("Selecione o Perfil:", opcoes_perfil)

st.sidebar.markdown("---")

# -----------------------------------------------------------------------------
# 1. AMBIENTE: PORTAL DO CLIENTE
# -----------------------------------------------------------------------------
if perfil_selecionado == "👤 Portal do Cliente":
    
    # Se o cliente NÃO estiver logado
    if not st.session_state.cliente_autenticado:
        st.title("🔒 Portal do Cliente")
        st.info("Por favor, selecione seu nome no menu à esquerda e insira sua senha para acessar seus pedidos.")
        
        lista_nomes = df_clientes['nome'].unique().tolist() if not df_clientes.empty else []
        
        if lista_nomes:
            cliente_nome = st.sidebar.selectbox("Identifique seu Nome/Empresa:", lista_nomes)
            senha_cliente = st.sidebar.text_input("Digite sua Senha de Cliente:", type="password")
            
            if st.sidebar.button("Acessar Meus Pedidos"):
                # Validação simples da senha do cliente
                senha_correta = df_clientes.loc[df_clientes['nome'] == cliente_nome, 'senha'].values
                if len(senha_correta) > 0 and senha_cliente == senha_correta[0]:
                    st.session_state.cliente_autenticado = cliente_nome
                    st.rerun()
                else:
                    st.sidebar.error("Senha incorreta!")
        else:
            st.sidebar.warning("Nenhum cliente cadastrado no sistema.")

    # Se o cliente JÁ estiver logado
    else:
        st.sidebar.success(f"Logado como: {st.session_state.cliente_autenticado}")
        if st.sidebar.button("Sair / Trocar Cliente"):
            st.session_state.cliente_autenticado = None
            st.rerun()
            
        st.title(f"🛍️ Portal do Cliente — Meus Pedidos ({st.session_state.cliente_autenticado})")
        st.write("Exibindo o histórico de pedidos e faturamento exclusivo para este cliente.")
        # --- INSIRA AQUI A SUA TABELA/LÓGICA DE PEDIDOS DO CLIENTE ---


# -----------------------------------------------------------------------------
# 2. AMBIENTE: ADMINISTRAÇÃO / VENDEDOR
# -----------------------------------------------------------------------------
elif perfil_selecionado == "🔒 Administração / Vendedor":
    
    # Se o Admin NÃO estiver logado
    if not st.session_state.admin_logged:
        st.title("🔑 Autenticação Administrativa")
        senha_admin = st.sidebar.text_input("Digite a Senha do Admin:", type="password")
        
        if st.sidebar.button("Entrar como Admin"):
            if senha_admin == "1234":  # <--- Altere para a sua senha de Admin
                st.session_state.admin_logged = True
                st.rerun()
            else:
                st.sidebar.error("Senha incorreta!")
                
    # Se o Admin JÁ estiver logado
    else:
        st.sidebar.subheader("🔒 Área Restrita")
        if st.sidebar.button("Sair do Modo Admin"):
            st.session_state.admin_logged = False
            st.rerun()
            
        menu = st.sidebar.radio(
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
        
        # Telas Internas do Administrador
        if menu == "📊 Fechamento & Financeiro":
            st.title("📊 Painel Financeiro & Fechamento")
            # --- INSIRA AQUI O CÓDIGO DO SEU PAINEL FINANCEIRO ---
            
        elif menu == "📋 Pedidos / Orçamentos":
            st.title("📋 Pedidos / Orçamentos")
            
        elif menu == "🛒 Registrar Venda":
            st.title("🛒 Registrar Venda")
            
        elif menu == "📥 Entrada de Estoque (Compras)":
            st.title("📥 Entrada de Estoque")
            
        elif menu == "📦 Estoque de Produtos":
            st.title("📦 Estoque de Produtos")
            
        elif menu == "👥 Cadastros (Clientes / Fornecedores / Grupos)":
            st.title("👥 Cadastros Gerais")
