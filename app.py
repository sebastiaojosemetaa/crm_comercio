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

# FUNÇÕES DE SALVAMENTO NO BANCO
def salvar_cadastro(tabela, coluna, valor):
    cursor = conn.cursor()
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {tabela} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            {coluna} TEXT UNIQUE
        )
    """)
    try:
        cursor.execute(f"INSERT INTO {tabela} ({coluna}) VALUES (?)", (valor,))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

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

def registrar_compra(produto, fornecedor, grupo, quantidade, valor_custo):
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS compras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            produto TEXT,
            fornecedor TEXT,
            grupo TEXT,
            quantidade REAL,
            valor_custo REAL,
            valor_total REAL,
            data TEXT
        )
    """)
    valor_total = quantidade * valor_custo
    data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute("""
        INSERT INTO compras (produto, fornecedor, grupo, quantidade, valor_custo, valor_total, data)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (produto, fornecedor, grupo, quantidade, valor_custo, valor_total, data_atual))
    
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
        
        lista_clientes = carregar_coluna("clientes", "nome") or carregar_coluna("vendas", "cliente") or ["Carlos Alberto", "Sebastião"]
        
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
            st.title("📥 Entrada de Estoque (Compras)")
            
            aba_compra, aba_historico_compras = st.tabs(["➕ Dar Entrada em Estoque", "📜 Histórico de Entradas / Compras"])
            
            produtos_opt = carregar_coluna("produtos", "nome") or carregar_coluna("vendas", "produto") or ["AMEIXA IMPORTADA", "ABACATE", "CEBOLA CAIXA 1"]
            fornecedores_opt = carregar_coluna("fornecedores", "nome") or carregar_coluna("vendas", "fornecedor") or ["BAHIA"]
            grupos_opt = carregar_coluna("grupos", "nome") or carregar_coluna("vendas", "grupo") or ["GERAL"]
            
            with aba_compra:
                with st.form("form_entrada_estoque"):
                    col1, col2 = st.columns(2)
                    with col1:
                        prod = st.selectbox("Selecione o Produto", produtos_opt)
                        fornec = st.selectbox("Selecione o Fornecedor", fornecedores_opt)
                        grupo = st.selectbox("Selecione o Grupo", grupos_opt)
                    
                    with col2:
                        qtd = st.number_input("Quantidade Comprada", min_value=0.1, step=0.5, value=10.0)
                        v_custo = st.number_input("Valor do Custo Unitário (R$)", min_value=0.0, step=1.0, value=50.0)
                        v_total_calc = qtd * v_custo
                        st.markdown(f"**Custo Total do Lote:** R$ {v_total_calc:,.2f}")
                    
                    if st.form_submit_button("Registrar Entrada no Estoque"):
                        registrar_compra(prod, fornec, grupo, qtd, v_custo)
                        st.success("Entrada de estoque gravada com sucesso!")
                        st.rerun()
                        
            with aba_historico_compras:
                df_compras = carregar_dados("SELECT * FROM compras")
                if not df_compras.empty:
                    st.dataframe(df_compras, use_container_width=True)
                else:
                    st.info("Nenhuma entrada de estoque registrada até o momento.")

        elif menu_admin == "📦 Estoque de Produtos":
            st.title("📦 Estoque de Produtos")
            
            # Mostra o inventário concatenado das compras e cadastros de produtos
            df_prods = carregar_dados("SELECT * FROM produtos")
            if not df_prods.empty:
                st.dataframe(df_prods, use_container_width=True)
            else:
                df_compras_prod = carregar_dados("SELECT produto, SUM(quantidade) as quantidade_total FROM compras GROUP BY produto")
                st.dataframe(df_compras_prod, use_container_width=True)

        elif menu_admin == "👥 Cadastros (Clientes / Fornecedores / Grupos)":
            st.title("👥 Cadastros Gerais")
            
            tab_cli, tab_prod, tab_forn, tab_grup = st.tabs(["👥 Clientes", "📦 Produtos", "🏭 Fornecedores", "🏷️ Grupos"])
            
            with tab_cli:
                st.subheader("Cadastrar Novo Cliente")
                with st.form("form_cad_cliente"):
                    novo_cli = st.text_input("Nome do Cliente / Empresa")
                    if st.form_submit_button("Salvar Cliente"):
                        if novo_cli.strip():
                            if salvar_cadastro("clientes", "nome", novo_cli.strip()):
                                st.success("Cliente cadastrado com sucesso!")
                                st.rerun()
                            else:
                                st.warning("Este cliente já está cadastrado.")
                
                st.markdown("---")
                st.subheader("Clientes Cadastrados")
                st.dataframe(carregar_dados("SELECT * FROM clientes"), use_container_width=True)

            with tab_prod:
                st.subheader("Cadastrar Novo Produto")
                with st.form("form_cad_produto"):
                    novo_prod = st.text_input("Nome do Produto")
                    if st.form_submit_button("Salvar Produto"):
                        if novo_prod.strip():
                            if salvar_cadastro("produtos", "nome", novo_prod.strip()):
                                st.success("Produto cadastrado com sucesso!")
                                st.rerun()
                            else:
                                st.warning("Este produto já está cadastrado.")
                
                st.markdown("---")
                st.subheader("Produtos Cadastrados")
                st.dataframe(carregar_dados("SELECT * FROM produtos"), use_container_width=True)

            with tab_forn:
                st.subheader("Cadastrar Novo Fornecedor")
                with st.form("form_cad_fornecedor"):
                    novo_forn = st.text_input("Nome do Fornecedor")
                    if st.form_submit_button("Salvar Fornecedor"):
                        if novo_forn.strip():
                            if salvar_cadastro("fornecedores", "nome", novo_forn.strip()):
                                st.success("Fornecedor cadastrado com sucesso!")
                                st.rerun()
                            else:
                                st.warning("Este fornecedor já está cadastrado.")
                
                st.markdown("---")
                st.subheader("Fornecedores Cadastrados")
                st.dataframe(carregar_dados("SELECT * FROM fornecedores"), use_container_width=True)

            with tab_grup:
                st.subheader("Cadastrar Novo Grupo")
                with st.form("form_cad_grupo"):
                    novo_grup = st.text_input("Nome do Grupo")
                    if st.form_submit_button("Salvar Grupo"):
                        if novo_grup.strip():
                            if salvar_cadastro("grupos", "nome", novo_grup.strip()):
                                st.success("Grupo cadastrado com sucesso!")
                                st.rerun()
                            else:
                                st.warning("Este grupo já está cadastrado.")
                
                st.markdown("---")
                st.subheader("Grupos Cadastrados")
                st.dataframe(carregar_dados("SELECT * FROM grupos"), use_container_width=True)
