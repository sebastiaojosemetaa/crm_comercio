import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# ------------------------------------------------------------------------------
# 1. CONFIGURAÇÃO E CONEXÃO COM O BANCO DE DADOS
# ------------------------------------------------------------------------------

st.set_page_config(page_title="CRM Comércio - Rey da Cebola", layout="wide")

DB_FILE = "crm_comercio.db"

def get_connection():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def criar_tabelas():
    with get_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                telefone TEXT,
                cpf_cnpj TEXT,
                endereco TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fornecedores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fornecedor TEXT NOT NULL,
                contato TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS grupos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                grupo TEXT NOT NULL
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS produtos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT,
                produto TEXT,
                quantidade REAL DEFAULT 0,
                preco_custo REAL DEFAULT 0,
                preco_venda REAL DEFAULT 0,
                grupo TEXT,
                fornecedor TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vendas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT,
                cliente TEXT,
                produto TEXT,
                fornecedor TEXT,
                grupo TEXT,
                quantidade REAL DEFAULT 0,
                preco_unitario REAL DEFAULT 0,
                preco_total REAL DEFAULT 0,
                forma_pagamento TEXT,
                valor_recebido REAL DEFAULT 0,
                troco REAL DEFAULT 0,
                tipo TEXT DEFAULT 'VENDA'
            )
        """)
        
        # Migrações seguras de colunas
        cursor.execute("PRAGMA table_info(vendas)")
        colunas = [col[1].lower() for col in cursor.fetchall()]
        if "tipo" not in colunas:
            cursor.execute("ALTER TABLE vendas ADD COLUMN tipo TEXT DEFAULT 'VENDA'")
        if "preco_total" not in colunas:
            cursor.execute("ALTER TABLE vendas ADD COLUMN preco_total REAL DEFAULT 0")
            
        conn.commit()

criar_tabelas()

# ------------------------------------------------------------------------------
# 2. FUNÇÕES AUXILIARES DE BANCO DE DADOS
# ------------------------------------------------------------------------------

def carregar_coluna(tabela, coluna):
    try:
        with get_connection() as conn:
            df = pd.read_sql_query(f"SELECT DISTINCT {coluna} FROM {tabela} WHERE {coluna} IS NOT NULL AND {coluna} != ''", conn)
            return df[coluna].tolist()
    except Exception:
        return []

def carregar_dados(tabela):
    with get_connection() as conn:
        df = pd.read_sql_query(f"SELECT * FROM {tabela}", conn)
        df.columns = df.columns.str.lower()
        return df

def salvar_pedido_ou_venda(cliente, produto, fornecedor, grupo, quantidade, preco_unitario, forma_pagamento, valor_recebido, tipo="VENDA"):
    data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    preco_total = quantidade * preco_unitario
    troco = max(0.0, valor_recebido - preco_total)
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO vendas (data, cliente, produto, fornecedor, grupo, quantidade, preco_unitario, preco_total, forma_pagamento, valor_recebido, troco, tipo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (data_atual, cliente, produto, fornecedor, grupo, quantidade, preco_unitario, preco_total, forma_pagamento, valor_recebido, troco, tipo))
        conn.commit()

def atualizar_precos_na_tabela(tipo_registro):
    """Atualiza o valor unitario e recala o preco total na tabela de vendas com base no estoque atual"""
    is_venda = (tipo_registro == "VENDA")
    coluna_busca = "preco_venda" if is_venda else "preco_custo"
    
    with get_connection() as conn:
        cursor = conn.cursor()
        # Busca produtos cadastrados no estoque
        cursor.execute(f"SELECT nome, produto, {coluna_busca} FROM produtos")
        produtos = cursor.fetchall()
        
        mapa_precos = {}
        for row in produtos:
            p_nome, p_prod, p_valor = row[0], row[1], row[2]
            if p_nome: mapa_precos[str(p_nome).strip().lower()] = float(p_valor or 0.0)
            if p_prod: mapa_precos[str(p_prod).strip().lower()] = float(p_valor or 0.0)
            
        # Busca os registros de vendas/pedidos do tipo correspondente
        cursor.execute("SELECT id, produto, quantidade FROM vendas WHERE tipo = ?", (tipo_registro,))
        vendas = cursor.fetchall()
        
        qtd_atualizados = 0
        for v_id, v_prod, v_qtd in vendas:
            prod_key = str(v_prod).strip().lower() if v_prod else ""
            if prod_key in mapa_precos:
                novo_preco_unit = mapa_precos[prod_key]
                novo_preco_total = novo_preco_unit * float(v_qtd or 0.0)
                
                cursor.execute("""
                    UPDATE vendas 
                    SET preco_unitario = ?, preco_total = ? 
                    WHERE id = ?
                """, (novo_preco_unit, novo_preco_total, v_id))
                qtd_atualizados += 1
                
        conn.commit()
    return qtd_atualizados

# ------------------------------------------------------------------------------
# 3. INTERFACE PRINCIPAL E NAVEGAÇÃO
# ------------------------------------------------------------------------------

st.sidebar.title("📌 Menu Principal")
menu_admin = st.sidebar.radio(
    "Selecione uma opção:",
    [
        "📊 Dashboard",
        "🛒 Registrar Venda",
        "📋 Pedidos / Orçamentos",
        "📦 Estoque de Produtos",
        "👥 Clientes",
        "🏭 Fornecedores",
        "🏷️ Grupos"
    ]
)

# ------------------------------------------------------------------------------
# 4. TELAS DE PEDIDOS / ORÇAMENTOS E REGISTRAR VENDA
# ------------------------------------------------------------------------------

if menu_admin in ["📋 Pedidos / Orçamentos", "🛒 Registrar Venda"]:
    st.title(f"{menu_admin}")
    aba_cad, aba_list = st.tabs(["➕ Novo Registro / Pedido", "✏️ Tabela Editável (Edição Direta & Exclusão)"])
    
    is_venda = (menu_admin == "🛒 Registrar Venda")
    tipo_registro = "VENDA" if is_venda else "PEDIDO"
    
    with aba_cad:
        clientes_opt = carregar_coluna("clientes", "nome") or ["CLIENTE PADRÃO"]
        produtos_opt = carregar_coluna("produtos", "nome") or carregar_coluna("produtos", "produto") or ["CEBOLA"]
        fornecedores_opt = carregar_coluna("fornecedores", "fornecedor") or ["GERAL"]
        grupos_opt = carregar_coluna("grupos", "grupo") or ["GERAL"]
        
        with st.form("form_admin_pedido"):
            col1, col2 = st.columns(2)
            with col1:
                cli = st.selectbox("Selecione o Cliente", clientes_opt)
                prod = st.selectbox("Selecione o Produto", produtos_opt)
                qtd = st.number_input("Quantidade", min_value=0.1, step=0.5, value=1.0)
                v_unit = st.number_input("Valor Unitário (R$)", min_value=0.0, step=1.0, value=0.0)
            with col2:
                fornec = st.selectbox("Selecione o Fornecedor", fornecedores_opt)
                grupo = st.selectbox("Selecione o Grupo", grupos_opt)
                f_pag = st.selectbox("Forma de Pagamento", ["Dinheiro", "Crediário / Fiado", "Pix"])
                v_rec = st.number_input("Valor Recebido (R$)", min_value=0.0, step=1.0, value=0.0)
            
            v_total_calc = v_unit * qtd
            st.info(f"💰 **Valor Total Calculado:** R$ {v_total_calc:,.2f}")
            
            if st.form_submit_button(f"Salvar como {tipo_registro}"):
                salvar_pedido_ou_venda(cli, prod, fornec, grupo, qtd, v_unit, f_pag, v_rec, tipo=tipo_registro)
                st.success(f"{tipo_registro} gravado com sucesso!")
                st.rerun()

    with aba_list:
        st.subheader("✏️ Gerenciar Registros")
        
        # Botão posicionado dentro da Tabela Editável
        lbl_btn = "🔄 Buscar Preço de Venda do Estoque e Recalcular Totais" if is_venda else "🔄 Buscar Preço de Custo do Estoque e Recalcular Totais"
        if st.button(lbl_btn, type="primary"):
            atualizados = atualizar_precos_na_tabela(tipo_registro)
            st.success(f"Valores e totais recarregados com sucesso do estoque! ({atualizados} itens atualizados)")
            st.rerun()
            
        st.write("---")
        df_vendas = carregar_dados("vendas")
        
        if not df_vendas.empty and 'tipo' in df_vendas.columns:
            df_filtrado = df_vendas[df_vendas['tipo'] == tipo_registro]
            
            # Tabela editável
            df_editado = st.data_editor(
                df_filtrado, 
                num_rows="dynamic", 
                use_container_width=True,
                key=f"editor_{tipo_registro}"
            )
            
            if st.button("💾 Salvar Alterações da Tabela"):
                with get_connection() as conn:
                    # Atualização simples das alterações feitas na grid
                    df_editado.to_sql("vendas_temp", conn, if_exists="replace", index=False)
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM vendas WHERE tipo = ?", (tipo_registro,))
                    cursor.execute("INSERT INTO vendas SELECT * FROM vendas_temp")
                    cursor.execute("DROP TABLE vendas_temp")
                    conn.commit()
                st.success("Alterações salvas!")
                st.rerun()
        else:
            st.info("Nenhum registro encontrado.")

# ------------------------------------------------------------------------------
# 5. DEMAIS TELAS (ESTOQUE, CLIENTES, FORNECEDORES, GRUPOS, DASHBOARD)
# ------------------------------------------------------------------------------

elif menu_admin == "📦 Estoque de Produtos":
    st.title("📦 Estoque de Produtos")
    aba_cad, aba_list = st.tabs(["➕ Cadastrar Produto", "📋 Lista de Produtos"])
    
    with aba_cad:
        with st.form("form_produto"):
            nome_p = st.text_input("Nome do Produto")
            qtd_p = st.number_input("Quantidade em Estoque", min_value=0.0, step=1.0)
            p_custo = st.number_input("Preço de Custo (R$)", min_value=0.0, step=0.1)
            p_venda = st.number_input("Preço de Venda (R$)", min_value=0.0, step=0.1)
            grupo_p = st.selectbox("Grupo", carregar_coluna("grupos", "grupo") or ["GERAL"])
            fornec_p = st.selectbox("Fornecedor", carregar_coluna("fornecedores", "fornecedor") or ["GERAL"])
            
            if st.form_submit_button("Salvar Produto"):
                with get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO produtos (nome, produto, quantidade, preco_custo, preco_venda, grupo, fornecedor)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (nome_p, nome_p, qtd_p, p_custo, p_venda, grupo_p, fornec_p))
                    conn.commit()
                st.success("Produto cadastrado com sucesso!")
                st.rerun()
                
    with aba_list:
        df_prod = carregar_dados("produtos")
        st.data_editor(df_prod, num_rows="dynamic", use_container_width=True)

elif menu_admin == "👥 Clientes":
    st.title("👥 Gestão de Clientes")
    with st.form("form_cliente"):
        nome_c = st.text_input("Nome Completo")
        tel_c = st.text_input("Telefone")
        doc_c = st.text_input("CPF / CNPJ")
        end_c = st.text_input("Endereço")
        if st.form_submit_button("Salvar Cliente"):
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO clientes (nome, telefone, cpf_cnpj, endereco) VALUES (?, ?, ?, ?)", (nome_c, tel_c, doc_c, end_c))
                conn.commit()
            st.success("Cliente cadastrado!")
            st.rerun()
    st.dataframe(carregar_dados("clientes"), use_container_width=True)

elif menu_admin == "🏭 Fornecedores":
    st.title("🏭 Gestão de Fornecedores")
    with st.form("form_fornec"):
        nome_f = st.text_input("Razão Social / Nome")
        cont_f = st.text_input("Contato / Telefone")
        if st.form_submit_button("Salvar Fornecedor"):
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO fornecedores (fornecedor, contato) VALUES (?, ?)", (nome_f, cont_f))
                conn.commit()
            st.success("Fornecedor cadastrado!")
            st.rerun()
    st.dataframe(carregar_dados("fornecedores"), use_container_width=True)

elif menu_admin == "🏷️ Grupos":
    st.title("🏷️ Grupos de Produtos")
    with st.form("form_grupo"):
        nome_g = st.text_input("Nome do Grupo")
        if st.form_submit_button("Salvar Grupo"):
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO grupos (grupo) VALUES (?)", (nome_g,))
                conn.commit()
            st.success("Grupo cadastrado!")
            st.rerun()
    st.dataframe(carregar_dados("grupos"), use_container_width=True)

elif menu_admin == "📊 Dashboard":
    st.title("📊 Dashboard Financeiro")
    df_vendas = carregar_dados("vendas")
    
    if not df_vendas.empty and 'tipo' in df_vendas.columns and 'preco_total' in df_vendas.columns:
        col1, col2, col3 = st.columns(3)
        total_vendas = df_vendas[df_vendas['tipo'] == 'VENDA']['preco_total'].sum()
        total_pedidos = df_vendas[df_vendas['tipo'] == 'PEDIDO']['preco_total'].sum()
        qtd_total = df_vendas['quantidade'].sum() if 'quantidade' in df_vendas.columns else 0.0
        
        col1.metric("Total em Vendas", f"R$ {total_vendas:,.2f}")
        col2.metric("Total em Pedidos/Orçamentos", f"R$ {total_pedidos:,.2f}")
        col3.metric("Volume Negociado", f"{qtd_total:,.1f} un")
        
        st.subheader("Histórico de Transações")
        st.dataframe(df_vendas, use_container_width=True)
    else:
        st.info("Sem dados de transações registrados.")
