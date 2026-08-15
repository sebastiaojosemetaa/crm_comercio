import streamlit as st
import pandas as pd
import sqlite3

# ==============================================================================
# 1. CONFIGURAÇÕES INICIAIS DA PÁGINA
# ==============================================================================
st.set_page_config(
    page_title="CRM Comércio",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==============================================================================
# 2. CONEXÃO COM O BANCO DE DADOS E CRIAÇÃO DAS TABELAS
# ==============================================================================
def conectar_banco():
    conn = sqlite3.connect("crm_comercio.db", check_same_thread=False)
    cursor = conn.cursor()
    # Tabela de Produtos
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            produto TEXT NOT NULL,
            quantidade INTEGER DEFAULT 0,
            valor_compra REAL DEFAULT 0.0,
            valor_venda REAL DEFAULT 0.0,
            grupo TEXT DEFAULT 'Geral'
        )
    """)
    conn.commit()
    return conn

conn = conectar_banco()

# ==============================================================================
# 3. BARRA LATERAL (AUTENTICAÇÃO / NAVEGAÇÃO / PERFIS DE ACESSO)
# ==============================================================================
st.sidebar.title("🔑 Acesso ao Sistema")

# Seleção de Perfil de Acesso
perfil = st.sidebar.radio(
    "Selecione o Perfil:",
    options=["Portal do Cliente", "Administração / Vendedor"],
    index=1
)

# Senha de Administração para Liberação de Recursos
if perfil == "Administração / Vendedor":
    if "admin_autenticado" not in st.session_state:
        st.session_state["admin_autenticado"] = False

    if not st.session_state["admin_autenticado"]:
        senha_input = st.sidebar.text_input("Senha de Acesso Admin:", type="password")
        if st.sidebar.button("Entrar no Modo Admin"):
            # DEFINA SUA SENHA AQUI (Exemplo: 1234)
            if senha_input == "1234":
                st.session_state["admin_autenticado"] = True
                st.sidebar.success("Acesso liberado!")
                st.rerun()
            else:
                st.sidebar.error("Senha incorreta!")
    else:
        st.sidebar.success("🔓 Autenticado como Admin")
        if st.sidebar.button("🚪 Sair do Modo Admin"):
            st.session_state["admin_autenticado"] = False
            st.rerun()

st.sidebar.markdown("---")
st.sidebar.title("CRM Comércio 📦")

# Menu de Navegação do Sistema
menu_opcoes = [
    "📊 Fechamento & Financeiro",
    "📝 Pedidos / Orçamentos",
    "🛒 Registrar Venda",
    "📥 Entrada de Estoque (Compras)",
    "📦 Estoque de Produtos",
    "👥 Cadastros (Clientes / Fornecedores / Grupos)"
]

menu_selecionado = st.sidebar.radio("Navegação", menu_opcoes, index=4)

# ==============================================================================
# 4. MÓDULO: ESTOQUE DE PRODUTOS (COM EDIÇÃO DIRETA E SALVAMENTO)
# ==============================================================================
if menu_selecionado == "📦 Estoque de Produtos":
    st.header("📦 Cadastro & Gestão de Estoque")

    # Botão Superior Vermelho de Salvar Alterações (conforme sua imagem)
    col_btn_salvar, col_espaco = st.columns([2, 8])
    with col_btn_salvar:
        btn_salvar_top = st.button("💾 Salvar Alterações da Tabela", type="primary", use_container_width=True)

    # Abas Internas de Navegação
    aba_lista, aba_novo = st.tabs(["📜 Lista de Produtos", "➕ Novo Produto"])

    # --------------------------------------------------------------------------
    # ABA 1: LISTA DE PRODUTOS (TABELA EDITÁVEL)
    # --------------------------------------------------------------------------
    with aba_lista:
        # Carrega dados do banco
        df_produtos = pd.read_sql("SELECT id, produto, quantidade, valor_compra, valor_venda, grupo FROM produtos", conn)

        # Lógica para salvar as edições
        if btn_salvar_top:
            if "editor_produtos" in st.session_state and st.session_state["editor_produtos"]["edited_rows"]:
                mudancas_dict = st.session_state["editor_produtos"]["edited_rows"]
                cursor = conn.cursor()
                
                for idx_linha, alteracoes in mudancas_dict.items():
                    prod_id = df_produtos.loc[idx_linha, "id"]
                    for coluna, novo_valor in alteracoes.items():
                        query = f"UPDATE produtos SET {coluna} = ? WHERE id = ?"
                        cursor.execute(query, (novo_valor, prod_id))
                
                conn.commit()
                st.success("✅ Alterações salvas com sucesso no banco de dados!")
                st.rerun()
            else:
                st.info("Nenhuma alteração pendente para salvar.")

        # Exibição do Editor de Tabela (st.data_editor)
        df_editado = st.data_editor(
            df_produtos,
            use_container_width=True,
            num_rows="fixed",
            key="editor_produtos",
            disabled=["id"], # Impede edição da coluna ID
            column_config={
                "id": st.column_config.NumberColumn("ID", disabled=True),
                "produto": st.column_config.TextColumn("produto", required=True),
                "quantidade": st.column_config.NumberColumn("quantidade", step=1),
                "valor_compra": st.column_config.NumberColumn("valor_compra", format="%.2f"),
                "valor_venda": st.column_config.NumberColumn("valor_venda", format="%.2f"),
                "grupo": st.column_config.TextColumn("grupo"),
            }
        )

    # --------------------------------------------------------------------------
    # ABA 2: NOVO PRODUTO (FORMULÁRIO MANTIDO INTACTO)
    # --------------------------------------------------------------------------
    with aba_novo:
        st.subheader("Cadastrar Novo Item no Estoque")
        
        with st.form(key="form_novo_produto", clear_on_submit=True):
            nome_prod = st.text_input("Nome do Produto")
            c1, c2, c3 = st.columns(3)
            with c1:
                qtd_ini = st.number_input("Quantidade Inicial", min_value=0, value=0, step=1)
            with c2:
                v_compra = st.number_input("Valor de Compra (R$)", min_value=0.0, format="%.2f")
            with c3:
                v_venda = st.number_input("Valor de Venda (R$)", min_value=0.0, format="%.2f")
            
            grupo_item = st.text_input("Grupo / Categoria", value="Geral")

            btn_cadastrar = st.form_submit_button("➕ Salvar Novo Produto")

            if btn_cadastrar:
                if not nome_prod.strip():
                    st.error("Por favor, digite o nome do produto.")
                else:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO produtos (produto, quantidade, valor_compra, valor_venda, grupo)
                        VALUES (?, ?, ?, ?, ?)
                    """, (nome_prod, qtd_ini, v_compra, v_venda, grupo_item))
                    conn.commit()
                    st.success(f"Produto '{nome_prod}' cadastrado com sucesso!")
                    st.rerun()

# ==============================================================================
# 5. DEMAIS MENUS (ESTRUTURA DE SUPORTE PARA NÃO QUEBRAR O FLUXO)
# ==============================================================================
elif menu_selecionado == "📊 Fechamento & Financeiro":
    st.header("📊 Fechamento & Financeiro")
    st.info("Módulo financeiro carregado.")

elif menu_selecionado == "📝 Pedidos / Orçamentos":
    st.header("📝 Pedidos & Orçamentos")
    st.info("Módulo de pedidos carregado.")

elif menu_selecionado == "🛒 Registrar Venda":
    st.header("🛒 Registrar Venda")
    st.info("Módulo de vendas carregado.")

elif menu_selecionado == "📥 Entrada de Estoque (Compras)":
    st.header("📥 Entrada de Estoque (Compras)")
    st.info("Módulo de compras carregado.")

elif menu_selecionado == "👥 Cadastros (Clientes / Fornecedores / Grupos)":
    st.header("👥 Cadastros Gerais")
    st.info("Módulo de cadastros carregado.")
