# -----------------------------------------------------------------------------
# AUTENTICAÇÃO E PERFIS DE ACESSO (COM SENHA DE SEGURANÇA)
# -----------------------------------------------------------------------------
# DEFINA A SUA SENHA DE ADMINISTRADOR AQUI:
SENHA_ADMIN = "1234"  # <-- Altere para a senha que você desejar!

st.sidebar.title("🔑 Acesso ao Sistema")

# Utiliza session_state para manter o estado do perfil
if 'perfil_ativo' not in st.session_state:
    st.session_state.perfil_ativo = "👤 Portal do Cliente"

opcoes_perfil = ["👤 Portal do Cliente", "🔒 Administração / Vendedor"]
index_atual = opcoes_perfil.index(st.session_state.perfil_ativo)

perfil_selecionado = st.sidebar.radio("Selecione o Perfil:", opcoes_perfil, index=index_atual)

# Trava de segurança com senha
if perfil_selecionado == "🔒 Administração / Vendedor":
    if st.session_state.get('admin_autenticado') != True:
        st.sidebar.markdown("---")
        st.sidebar.subheader("🔒 Área Restrita")
        senha_digitada = st.sidebar.text_input("Digite a Senha do Admin:", type="password", key="pwd_admin")
        
        if st.sidebar.button("Entrar como Admin"):
            if senha_digitada == SENHA_ADMIN:
                st.session_state.admin_autenticado = True
                st.session_state.perfil_ativo = "🔒 Administração / Vendedor"
                st.sidebar.success("Acesso liberado!")
                st.rerun()
            else:
                st.sidebar.error("Senha incorreta!")
        
        # Enquanto não digitar a senha correta, força o modo cliente
        tipo_acesso = "👤 Portal do Cliente"
    else:
        tipo_acesso = "🔒 Administração / Vendedor"
        if st.sidebar.button("🚪 Sair do Modo Admin"):
            st.session_state.admin_autenticado = False
            st.session_state.perfil_ativo = "👤 Portal do Cliente"
            st.rerun()
else:
    # Se mudar manualmente para cliente, limpa o login admin
    st.session_state.admin_autenticado = False
    st.session_state.perfil_ativo = "👤 Portal do Cliente"
    tipo_acesso = "👤 Portal do Cliente"

cliente_autenticado = None

if tipo_acesso == "👤 Portal do Cliente":
    st.sidebar.markdown("---")
    cliente_autenticado = st.sidebar.selectbox("Identifique seu Nome/Empresa:", list_clientes, key="cli_login")
    st.sidebar.info(f"Bem-vindo(a), **{cliente_autenticado}**!")
    menu = "📋 Pedidos / Orçamentos"
else:
    st.sidebar.markdown("---")
    st.sidebar.title("CRM Comércio 📦")
    menu = st.sidebar.radio("Navegação", [
        "📊 Fechamento & Financeiro",
        "📋 Pedidos / Orçamentos",
        "🛒 Registrar Venda",
        "📥 Entrada de Estoque (Compras)",
        "📦 Estoque de Produtos",
        "👥 Cadastros (Clientes / Fornecedores / Grupos)"
    ])
