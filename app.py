import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date
import io

# Tenta importar o ReportLab com tratamento para não derrubar o app se faltar
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="CRM Comércio - Rey da Cebola",
    page_icon="📦",
    layout="wide"
)

# --- BANCO DE DADOS ---
def get_connection():
    return sqlite3.connect("crm_comercio.db", check_same_thread=False)

conn = get_connection()

def adequar_banco_e_migrar():
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            telefone TEXT,
            email TEXT,
            cpf_cnpj TEXT,
            endereco TEXT,
            limite_credito REAL DEFAULT 0.0,
            saldo_devedor REAL DEFAULT 0.0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            fornecedor TEXT,
            grupo TEXT,
            preco_custo REAL,
            valor_venda REAL,
            estoque REAL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fornecedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fornecedor TEXT,
            cnpj TEXT,
            telefone TEXT,
            email TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS grupos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grupo TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pedidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT,
            cliente TEXT,
            produto TEXT,
            fornecedor TEXT,
            grupo TEXT,
            quantidade REAL,
            valor_venda REAL,
            valor_total REAL,
            forma_pagamento TEXT,
            valor_recebido REAL,
            troco REAL,
            status TEXT,
            tipo TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS caixa_sessoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_abertura TEXT,
            data_fechamento TEXT,
            saldo_inicial REAL,
            saldo_final REAL,
            status TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS caixa_movimentacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sessao_id INTEGER,
            tipo TEXT,
            valor REAL,
            descricao TEXT,
            data TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fiado_contas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente TEXT,
            valor TEXT,
            data TEXT,
            status TEXT,
            observacao TEXT
        )
    """)
    conn.commit()

adequar_banco_e_migrar()

# --- FUNÇÕES DE SUPORTE ---
def carregar_dados(query):
    try:
        return pd.read_sql_query(query, conn)
    except Exception:
        return pd.DataFrame()

def carregar_coluna(tabela, coluna):
    df = carregar_dados(f"SELECT {coluna} FROM {tabela}")
    if not df.empty and coluna in df.columns:
        return df[coluna].dropna().unique().tolist()
    return []

def salvar_pedido_ou_venda(cliente, produto, fornecedor, grupo, quantidade, valor_venda, forma_pagamento, valor_recebido, tipo="VENDA"):
    valor_total = quantidade * valor_venda
    troco = max(0.0, valor_recebido - valor_total)
    data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO pedidos (data, cliente, produto, fornecedor, grupo, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, troco, status, tipo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (data_atual, cliente, produto, fornecedor, grupo, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, troco, "Concluído", tipo))
    
    cursor.execute("UPDATE produtos SET estoque = estoque - ? WHERE TRIM(nome) = TRIM(?)", (quantidade, produto))
    
    if forma_pagamento == "Crediário / Fiado":
        cursor.execute("UPDATE clientes SET saldo_devedor = saldo_devedor + ? WHERE TRIM(nome) = TRIM(?)", (valor_total, cliente))
        cursor.execute("INSERT INTO fiado_contas (cliente, valor, data, status, observacao) VALUES (?, ?, ?, ?, ?)",
                       (cliente, str(valor_total), data_atual, "Pendente", f"Venda PDV - Produto: {produto} x {quantidade}"))
    
    conn.commit()

# --- ESTADO DA SESSÃO ---
if "carrinho_pdv" not in st.session_state:
    st.session_state.carrinho_pdv = []

if "pdv_v_unit" not in st.session_state:
    st.session_state.pdv_v_unit = 0.0

if "pdv_forn" not in st.session_state:
    st.session_state.pdv_forn = ""

if "pdv_grupo" not in st.session_state:
    st.session_state.pdv_grupo = ""

# --- MENU LATERAL ---
st.sidebar.title("📌 CRM Comércio - Menu")

if not HAS_REPORTLAB:
    st.sidebar.warning("⚠️ Instale 'reportlab' no requirements.txt para habilitar a geração de PDFs.")

menu_admin = st.sidebar.radio(
    "Navegação",
    [
        "🛒 PDV — Frente de Caixa",
        "🔓 Abertura e Fechamento de Caixa",
        "📦 Cadastrar Produtos",
        "👥 Cadastrar Clientes",
        "🚚 Cadastrar Fornecedores",
        "🏷️ Cadastrar Grupos",
        "📊 Relatório de Vendas",
        "📑 Fiado / Contas a Receber"
    ]
)

# --- TELAS ---
if menu_admin == "🛒 PDV — Frente de Caixa":
    st.title("🛒 PDV — Frente de Caixa")

    df_caixa_aberto = carregar_dados("SELECT * FROM caixa_sessoes WHERE status = 'ABERTO'")
    if df_caixa_aberto.empty:
        st.warning("⚠️ Atenção: Caixa FECHADO! Abra o caixa para registrar vendas.")

    clientes_opt = carregar_coluna("clientes", "nome") or ["Cliente Geral"]
    produtos_opt = carregar_coluna("produtos", "nome") or ["Nenhum produto cadastrado"]
    fornecedores_opt = carregar_coluna("fornecedores", "fornecedor") or ["Geral"]
    grupos_opt = carregar_coluna("grupos", "grupo") or ["GERAL"]

    cliente_pdv = st.selectbox("Selecione o Cliente do Atendimento", clientes_opt)

    st.markdown("#### ➕ Adicionar Item ao Carrinho")

    def atualizar_dados_produto():
        prod_selecionado = st.session_state.pdv_select_produto
        df_prod_info = carregar_dados(f"SELECT * FROM produtos WHERE TRIM(nome) = TRIM('{prod_selecionado}')")
        
        if not df_prod_info.empty:
            linha_prod = df_prod_info.iloc[0]
            cols_p = df_prod_info.columns.tolist()

            precos = [linha_prod[col] for col in ["valor_venda", "preco_venda"] if col in cols_p and pd.notna(linha_prod[col])]
            if precos:
                st.session_state.pdv_v_unit = float(precos[0])
            else:
                st.session_state.pdv_v_unit = 0.0

            fornecs = [str(linha_prod[col]) for col in ["fornecedor"] if col in cols_p and pd.notna(linha_prod[col])]
            if fornecs and fornecs[0] in fornecedores_opt:
                st.session_state.pdv_forn = fornecs[0]

            grps = [str(linha_prod[col]) for col in ["grupo"] if col in cols_p and pd.notna(linha_prod[col])]
            if grps and grps[0] in grupos_opt:
                st.session_state.pdv_grupo = grps[0]

    prod_item = st.selectbox(
        "Selecione o Produto", 
        produtos_opt, 
        key="pdv_select_produto", 
        on_change=atualizar_dados_produto
    )

    if st.session_state.pdv_v_unit == 0.0 and produtos_opt and produtos_opt[0] != "Nenhum produto cadastrado":
        atualizar_dados_produto()

    with st.form("form_adicionar_item_pdv", clear_on_submit=False):
        col_i1, col_i2, col_i3 = st.columns(3)

        with col_i1:
            qtd_item = st.number_input("Quantidade", min_value=0.1, step=1.0, value=1.0, key="pdv_qtd")

        with col_i2:
            fornec_item = st.selectbox("Fornecedor", fornecedores_opt, key="pdv_forn")
            v_unit_item = st.number_input("Preço Venda (R$)", min_value=0.0, step=0.10, format="%.2f", key="pdv_v_unit")

        with col_i3:
            grupo_item = st.selectbox("Grupo", grupos_opt, key="pdv_grupo")
            valor_total_item = qtd_item * v_unit_item
            st.metric("Valor Total do Item", f"R$ {valor_total_item:.2f}")

        if st.form_submit_button("➕ Incluir Produto no Carrinho"):
            st.session_state.carrinho_pdv.append({
                "produto": prod_item,
                "fornecedor": fornec_item,
                "grupo": grupo_item,
                "quantidade": qtd_item,
                "valor_venda": v_unit_item,
                "valor_total": valor_total_item
            })
            st.success(f"Item '{prod_item}' adicionado!")
            st.rerun()

    st.markdown("---")
    st.subheader("🛒 Itens Atuais no Carrinho")

    if len(st.session_state.carrinho_pdv) > 0:
        df_carrinho = pd.DataFrame(st.session_state.carrinho_pdv)
        st.dataframe(df_carrinho, use_container_width=True)

        if st.button("🗑️ Limpar Carrinho"):
            st.session_state.carrinho_pdv = []
            st.rerun()

        st.markdown("---")
        total_geral_carrinho = df_carrinho['valor_total'].sum()

        with st.form("form_finalizar_pagamento_pdv"):
            f_pag = st.selectbox("Forma de Pagamento", ["Dinheiro", "Pix", "Cartão de Crédito", "Cartão de Débito", "Crediário / Fiado"])
            v_rec = st.number_input("Valor Recebido (R$)", min_value=0.0, step=1.0, value=total_geral_carrinho)
            troco = v_rec - total_geral_carrinho

            st.markdown("---")
            c_inf1, c_inf2 = st.columns(2)
            c_inf1.metric("Total Venda", f"R$ {total_geral_carrinho:,.2f}")
            c_inf2.metric("Troco", f"R$ {max(0.0, troco):,.2f}")

            if st.form_submit_button("Finalizar Venda"):
                if not df_caixa_aberto.empty:
                    sessao_id = int(df_caixa_aberto.iloc[0]['id'])
                    for item in st.session_state.carrinho_pdv:
                        salvar_pedido_ou_venda(
                            cliente=cliente_pdv,
                            produto=item['produto'],
                            fornecedor=item['fornecedor'],
                            grupo=item['grupo'],
                            quantidade=item['quantidade'],
                            valor_venda=item['valor_venda'],
                            forma_pagamento=f_pag,
                            valor_recebido=v_rec,
                            tipo="VENDA"
                        )
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO caixa_movimentacoes (sessao_id, tipo, valor, descricao, data) VALUES (?, ?, ?, ?, ?)",
                        (sessao_id, "VENDA", total_geral_carrinho, f"Venda PDV - Cliente: {cliente_pdv}", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    )
                    conn.commit()
                    st.session_state.carrinho_pdv = []
                    st.success("Venda realizada com sucesso!")
                    st.rerun()

elif menu_admin == "🔓 Abertura e Fechamento de Caixa":
    st.title("🔓 Abertura e Fechamento de Caixa")
    df_caixa_atual = carregar_dados("SELECT * FROM caixa_sessoes WHERE status = 'ABERTO'")
    
    if df_caixa_atual.empty:
        st.info("O caixa está **FECHADO**.")
        with st.form("form_abrir_caixa"):
            saldo_inicial = st.number_input("Saldo Inicial (R$)", min_value=0.0, step=10.0, value=0.0)
            if st.form_submit_button("Abrir Caixa"):
                cursor = conn.cursor()
                cursor.execute("INSERT INTO caixa_sessoes (data_abertura, saldo_inicial, status) VALUES (?, ?, ?)", 
                               (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), saldo_inicial, "ABERTO"))
                conn.commit()
                st.success("Caixa aberto com sucesso!")
                st.rerun()
    else:
        sessao_id = int(df_caixa_atual.iloc[0]['id'])
        st.success(f"🟢 **Caixa ABERTO** desde: {df_caixa_atual.iloc[0]['data_abertura']}")
        
        df_movs = carregar_dados(f"SELECT * FROM caixa_movimentacoes WHERE sessao_id = {sessao_id}")
        total_mov = df_movs['valor'].sum() if not df_movs.empty and 'valor' in df_movs.columns else 0.0
        st.metric("Total Movimentado", f"R$ {total_mov:,.2f}")
        
        if st.button("🔴 Fechar Caixa"):
            cursor = conn.cursor()
            cursor.execute("UPDATE caixa_sessoes SET status = 'FECHADO', data_fechamento = ? WHERE id = ?", 
                           (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), sessao_id))
            conn.commit()
            st.success("Caixa fechado!")
            st.rerun()

elif menu_admin == "📦 Cadastrar Produtos":
    st.title("📦 Cadastrar e Gerenciar Produtos")
    fornecedores_opt = carregar_coluna("fornecedores", "fornecedor") or ["Geral"]
    grupos_opt = carregar_coluna("grupos", "grupo") or ["GERAL"]
    
    with st.form("form_produto"):
        nome_prod = st.text_input("Nome do Produto")
        col_p1, col_p2 = st.columns(2)
        fornec_prod = col_p1.selectbox("Fornecedor", fornecedores_opt)
        grupo_prod = col_p2.selectbox("Grupo", grupos_opt)
        col_p3, col_p4, col_p5 = st.columns(3)
        p_custo = col_p3.number_input("Preço de Custo (R$)", min_value=0.0)
        v_venda = col_p4.number_input("Valor de Venda (R$)", min_value=0.0)
        qtd_estoque = col_p5.number_input("Estoque", min_value=0.0)
        
        if st.form_submit_button("Salvar Produto"):
            cursor = conn.cursor()
            cursor.execute("INSERT INTO produtos (nome, fornecedor, grupo, preco_custo, valor_venda, estoque) VALUES (?, ?, ?, ?, ?, ?)",
                           (nome_prod, fornec_prod, grupo_prod, p_custo, v_venda, qtd_estoque))
            conn.commit()
            st.success(f"Produto '{nome_prod}' salvo!")
            st.rerun()

    st.dataframe(carregar_dados("SELECT * FROM produtos"), use_container_width=True)

elif menu_admin == "👥 Cadastrar Clientes":
    st.title("👥 Cadastrar e Gerenciar Clientes")
    with st.form("form_cliente"):
        nome_cli = st.text_input("Nome")
        tel_cli = st.text_input("Telefone")
        email_cli = st.text_input("E-mail")
        if st.form_submit_button("Salvar Cliente"):
            cursor = conn.cursor()
            cursor.execute("INSERT INTO clientes (nome, telefone, email) VALUES (?, ?, ?)", (nome_cli, tel_cli, email_cli))
            conn.commit()
            st.success("Cliente cadastrado!")
            st.rerun()

    st.dataframe(carregar_dados("SELECT * FROM clientes"), use_container_width=True)

elif menu_admin == "🚚 Cadastrar Fornecedores":
    st.title("🚚 Cadastrar Fornecedores")
    with st.form("form_fornecedor"):
        nome_forn = st.text_input("Nome Fornecedor")
        if st.form_submit_button("Salvar Fornecedor"):
            cursor = conn.cursor()
            cursor.execute("INSERT INTO fornecedores (fornecedor) VALUES (?)", (nome_forn,))
            conn.commit()
            st.success("Fornecedor cadastrado!")
            st.rerun()

    st.dataframe(carregar_dados("SELECT * FROM fornecedores"), use_container_width=True)

elif menu_admin == "🏷️ Cadastrar Grupos":
    st.title("🏷️ Cadastrar Grupos / Categorias")
    with st.form("form_grupo"):
        nome_grupo = st.text_input("Nome do Grupo")
        if st.form_submit_button("Salvar Grupo"):
            cursor = conn.cursor()
            cursor.execute("INSERT INTO grupos (grupo) VALUES (?)", (nome_grupo,))
            conn.commit()
            st.success("Grupo cadastrado!")
            st.rerun()

    st.dataframe(carregar_dados("SELECT * FROM grupos"), use_container_width=True)

elif menu_admin == "📊 Relatório de Vendas":
    st.title("📊 Relatório de Vendas")
    df_vendas = carregar_dados("SELECT * FROM pedidos ORDER BY id DESC")
    st.dataframe(df_vendas, use_container_width=True)

elif menu_admin == "📑 Fiado / Contas a Receber":
    st.title("📑 Contas a Receber")
    df_fiado = carregar_dados("SELECT * FROM fiado_contas WHERE status = 'Pendente'")
    st.dataframe(df_fiado, use_container_width=True)
