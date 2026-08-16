import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import io
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# -----------------------------------------------------------------------------
# 1. CONFIGURAÇÃO E CONEXÃO COM O BANCO DE DADOS
# -----------------------------------------------------------------------------
st.set_page_config(page_title="CRM Comércio", layout="wide")

def get_connection():
    return sqlite3.connect("crm_comercio.db", check_same_thread=False)

conn = get_connection()

def adequar_banco():
    """Garante que todas as tabelas e colunas necessárias existam."""
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
            tipo TEXT DEFAULT 'PEDIDO',
            data TEXT
        )
    """)
    # Adiciona a coluna 'tipo' em bancos antigos que ainda não a possuem
    try:
        cursor.execute("ALTER TABLE vendas ADD COLUMN tipo TEXT DEFAULT 'PEDIDO'")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # A coluna já existe

adequar_banco()

def carregar_dados(query):
    try:
        return pd.read_sql_query(query, conn)
    except Exception:
        return pd.DataFrame()

def carregar_coluna(tabela, coluna):
    df = carregar_dados(f"SELECT DISTINCT {coluna} FROM {tabela} WHERE {coluna} IS NOT NULL AND {coluna} != ''")
    if not df.empty:
        return df[coluna].tolist()
    return []

# -----------------------------------------------------------------------------
# FUNÇÕES DE BANCO DE DADOS E REGISTROS
# -----------------------------------------------------------------------------
def salvar_cliente_completo(nome, telefone, doc, endereco, cidade):
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE,
            telefone TEXT,
            doc TEXT,
            endereco TEXT,
            cidade TEXT
        )
    """)
    try:
        cursor.execute("INSERT INTO clientes (nome, telefone, doc, endereco, cidade) VALUES (?, ?, ?, ?, ?)",
                       (nome, telefone, doc, endereco, cidade))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def salvar_produto_completo(nome, grupo, preco_custo, preco_venda, estoque_inicial):
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE,
            grupo TEXT,
            preco_custo REAL,
            preco_venda REAL,
            estoque_atual REAL
        )
    """)
    try:
        cursor.execute("INSERT INTO produtos (nome, grupo, preco_custo, preco_venda, estoque_atual) VALUES (?, ?, ?, ?, ?)",
                       (nome, grupo, preco_custo, preco_venda, estoque_inicial))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def salvar_simples(tabela, coluna, valor):
    cursor = conn.cursor()
    cursor.execute(f"CREATE TABLE IF NOT EXISTS {tabela} (id INTEGER PRIMARY KEY AUTOINCREMENT, {coluna} TEXT UNIQUE)")
    try:
        cursor.execute(f"INSERT INTO {tabela} ({coluna}) VALUES (?)", (valor,))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def salvar_pedido_ou_venda(cliente, produto, fornecedor, grupo, quantidade, valor_venda, forma_pagamento, valor_recebido, tipo="PEDIDO"):
    cursor = conn.cursor()
    valor_total = quantidade * valor_venda
    data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO vendas (cliente, produto, fornecedor, grupo, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, tipo, data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (cliente, produto, fornecedor, grupo, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, tipo, data_atual))
    conn.commit()

def converter_pedido_para_venda(pedido_id):
    cursor = conn.cursor()
    cursor.execute("UPDATE vendas SET tipo = 'VENDA' WHERE id = ?", (pedido_id,))
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
# GERADOR DE PDF
# -----------------------------------------------------------------------------
def gerar_pdf_pedido(row):
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    
    tipo_registro = row.get('tipo', 'PEDIDO')
    if pd.isna(tipo_registro) or not tipo_registro:
        tipo_registro = 'PEDIDO'
        
    p.setFont("Helvetica-Bold", 16)
    p.drawString(100, 750, f"COMPROVANTE DE {tipo_registro} - Nº #{row['id']}")
    p.setLineWidth(1)
    p.line(100, 740, 500, 740)
    
    p.setFont("Helvetica", 12)
    p.drawString(100, 710, f"Data: {row.get('data', '')}")
    p.drawString(100, 690, f"Cliente: {row.get('cliente', '')}")
    p.drawString(100, 670, f"Produto: {row.get('produto', '')}")
    p.drawString(100, 650, f"Grupo: {row.get('grupo', '')} | Fornecedor: {row.get('fornecedor', '')}")
    p.drawString(100, 630, f"Quantidade: {row.get('quantidade', 0)}")
    p.drawString(100, 610, f"Valor Unitário: R$ {row.get('valor_venda', 0.0):,.2f}")
    p.drawString(100, 590, f"Valor Total: R$ {row.get('valor_total', 0.0):,.2f}")
    p.drawString(100, 570, f"Forma de Pagamento: {row.get('forma_pagamento', '')}")
    p.drawString(100, 550, f"Status: {tipo_registro}")
    
    p.line(100, 530, 500, 530)
    p.drawString(100, 500, "Obrigado pela preferência!")
    
    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer

# -----------------------------------------------------------------------------
# 2. INICIALIZAÇÃO DE SESSÃO E PERFIL
# -----------------------------------------------------------------------------
if 'admin_logged' not in st.session_state:
    st.session_state.admin_logged = False

if 'cliente_autenticado' not in st.session_state:
    st.session_state.cliente_autenticado = None

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
            produtos_opt = carregar_coluna("produtos", "nome") or ["AMEIXA IMPORTADA", "ABACATE", "CEBOLA CAIXA 1"]
            fornecedores_opt = carregar_coluna("fornecedores", "nome") or ["BAHIA"]
            grupos_opt = carregar_coluna("grupos", "nome") or ["GERAL"]
            
            with st.form("form_novo_pedido_cliente"):
                prod = st.selectbox("Selecione o Produto", produtos_opt)
                fornec = st.selectbox("Selecione o Fornecedor", fornecedores_opt)
                grupo = st.selectbox("Selecione o Grupo", grupos_opt)
                qtd = st.number_input("Quantidade", min_value=0.1, step=0.5, value=1.0)
                v_unit = st.number_input("Valor Unitário (R$)", min_value=0.0, step=1.0, value=100.0)
                f_pag = st.selectbox("Forma de Pagamento", ["Dinheiro", "Crediário / Fiado", "Pix"])
                
                if st.form_submit_button("Confirmar Pedido"):
                    salvar_pedido_ou_venda(st.session_state.cliente_autenticado, prod, fornec, grupo, qtd, v_unit, f_pag, v_unit * qtd, tipo="PEDIDO")
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
            df_vendas = carregar_dados("SELECT * FROM vendas WHERE tipo = 'VENDA'")
            if not df_vendas.empty:
                col1, col2, col3 = st.columns(3)
                faturamento = df_vendas['valor_total'].sum() if 'valor_total' in df_vendas.columns else 0.0
                col1.metric("Faturamento Total", f"R$ {faturamento:,.2f}")
                col2.metric("Total Recebido em Caixa", f"R$ {faturamento * 0.15:,.2f}")
                col3.metric("Total a Receber (Fiado/Pendente)", f"R$ {faturamento * 0.85:,.2f}")
                st.markdown("---")
                st.subheader("📊 Resumo do Histórico de Vendas Concluídas")
                st.dataframe(df_vendas, use_container_width=True)
            else:
                st.info("Nenhuma venda confirmada cadastrada.")

        elif menu_admin in ["📋 Pedidos / Orçamentos", "🛒 Registrar Venda"]:
            st.title(f"📋 {menu_admin}")
            aba_cad, aba_list = st.tabs(["➕ Novo Registro / Pedido", "📜 Gestão de Pedidos e Vendas"])
            
            with aba_cad:
                clientes_opt = carregar_coluna("clientes", "nome") or ["Carlos Alberto", "Sebastião"]
                produtos_opt = carregar_coluna("produtos", "nome") or ["AMEIXA IMPORTADA", "ABACATE"]
                fornecedores_opt = carregar_coluna("fornecedores", "nome") or ["BAHIA"]
                grupos_opt = carregar_coluna("grupos", "nome") or ["GERAL"]
                
                tipo_registro = "VENDA" if menu_admin == "🛒 Registrar Venda" else "PEDIDO"
                
                with st.form("form_admin_pedido"):
                    col_a, col_b = st.columns(2)
                    with col_a:
                        cli = st.selectbox("Selecione o Cliente", clientes_opt)
                        prod = st.selectbox("Selecione o Produto", produtos_opt)
                        qtd = st.number_input("Quantidade", min_value=0.1, step=0.5, value=1.0)
                        v_unit = st.number_input("Valor Unitário (R$)", min_value=0.0, step=1.0, value=100.0)
                    with col_b:
                        fornec = st.selectbox("Selecione o Fornecedor", fornecedores_opt)
                        grupo = st.selectbox("Selecione o Grupo", grupos_opt)
                        f_pag = st.selectbox("Forma de Pagamento", ["Dinheiro", "Crediário / Fiado", "Pix"])
                        v_rec = st.number_input("Valor Recebido (R$)", min_value=0.0, step=1.0, value=0.0)
                    
                    if st.form_submit_button(f"Salvar como {tipo_registro}"):
                        salvar_pedido_ou_venda(cli, prod, fornec, grupo, qtd, v_unit, f_pag, v_rec, tipo=tipo_registro)
                        st.success(f"{tipo_registro} gravado com sucesso!")
                        st.rerun()

            with aba_list:
                st.subheader("🔍 Consultar e Gerenciar Registros")
                
                clientes_filtro = ["TODOS"] + (carregar_coluna("clientes", "nome") or carregar_coluna("vendas", "cliente"))
                cliente_sel = st.selectbox("Filtrar por Cliente Individual:", clientes_filtro)
                
                if cliente_sel == "TODOS":
                    df_registros = carregar_dados("SELECT * FROM vendas")
                else:
                    df_registros = carregar_dados(f"SELECT * FROM vendas WHERE cliente = '{cliente_sel}'")
                
                if not df_registros.empty:
                    st.dataframe(df_registros, use_container_width=True)
                    
                    st.markdown("---")
                    st.subheader("⚙️ Ações para o Pedido Selecionado")
                    
                    pedido_id_sel = st.selectbox("Selecione o ID do Pedido/Venda:", df_registros['id'].tolist())
                    row_sel = df_registros[df_registros['id'] == pedido_id_sel].iloc[0]
                    
                    col_btn1, col_btn2 = st.columns(2)
                    
                    with col_btn1:
                        pdf_data = gerar_pdf_pedido(row_sel)
                        st.download_button(
                            label=f"📄 Baixar PDF do Registro #{row_sel['id']}",
                            data=pdf_data,
                            file_name=f"Pedido_{row_sel['id']}_{row_sel['cliente']}.pdf",
                            mime="application/pdf"
                        )
                    
                    with col_btn2:
                        tipo_atual = row_sel.get('tipo', 'PEDIDO')
                        if tipo_atual == "PEDIDO" or pd.isna(tipo_atual):
                            if st.button(f"🔄 Converter Pedido #{row_sel['id']} para VENDA"):
                                converter_pedido_para_venda(row_sel['id'])
                                st.success("Pedido convertido em Venda com sucesso!")
                                st.rerun()
                        else:
                            st.info("Este registro já é uma Venda confirmada.")
                else:
                    st.info("Nenhum registro encontrado para a seleção.")

        elif menu_admin == "📥 Entrada de Estoque (Compras)":
            st.title("📥 Entrada de Estoque (Compras)")
            aba_compra, aba_historico_compras = st.tabs(["➕ Dar Entrada em Estoque", "📜 Histórico de Entradas / Compras"])
            
            produtos_opt = carregar_coluna("produtos", "nome") or ["AMEIXA IMPORTADA", "ABACATE"]
            fornecedores_opt = carregar_coluna("fornecedores", "nome") or ["BAHIA"]
            grupos_opt = carregar_coluna("grupos", "nome") or ["GERAL"]
            
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
                        st.markdown(f"**Custo Total do Lote:** R$ {qtd * v_custo:,.2f}")
                    
                    if st.form_submit_button("Registrar Entrada no Estoque"):
                        registrar_compra(prod, fornec, grupo, qtd, v_custo)
                        st.success("Entrada de estoque gravada com sucesso!")
                        st.rerun()
                        
            with aba_historico_compras:
                st.dataframe(carregar_dados("SELECT * FROM compras"), use_container_width=True)

        elif menu_admin == "📦 Estoque de Produtos":
            st.title("📦 Estoque de Produtos e Preços")
            df_prods = carregar_dados("SELECT id, nome as produto, grupo, preco_custo, preco_venda, estoque_atual FROM produtos")
            if not df_prods.empty:
                st.dataframe(df_prods, use_container_width=True)
            else:
                st.info("Nenhum produto cadastrado.")

        elif menu_admin == "👥 Cadastros (Clientes / Fornecedores / Grupos)":
            st.title("👥 Cadastros Gerais")
            tab_cli, tab_prod, tab_forn, tab_grup = st.tabs(["👥 Clientes", "📦 Produtos", "🏭 Fornecedores", "🏷️ Grupos"])
            
            with tab_cli:
                st.subheader("Cadastrar Novo Cliente")
                with st.form("form_cad_cliente_completo"):
                    col1, col2 = st.columns(2)
                    with col1:
                        novo_cli = st.text_input("Nome do Cliente / Razão Social")
                        telefone = st.text_input("Telefone / WhatsApp")
                        doc = st.text_input("CPF / CNPJ")
                    with col2:
                        endereco = st.text_input("Endereço / Logradouro")
                        cidade = st.text_input("Cidade / UF")
                    
                    if st.form_submit_button("Salvar Cliente"):
                        if novo_cli.strip() and salvar_cliente_completo(novo_cli.strip(), telefone, doc, endereco, cidade):
                            st.success("Cliente cadastrado com sucesso!")
                            st.rerun()
                st.markdown("---")
                st.dataframe(carregar_dados("SELECT * FROM clientes"), use_container_width=True)

            with tab_prod:
                st.subheader("Cadastrar Novo Produto e Estoque")
                grupos_opt = carregar_coluna("grupos", "nome") or ["GERAL"]
                with st.form("form_cad_produto_completo"):
                    col1, col2 = st.columns(2)
                    with col1:
                        novo_prod = st.text_input("Nome do Produto")
                        grupo_prod = st.selectbox("Grupo / Categoria", grupos_opt)
                        estoque_ini = st.number_input("Estoque Inicial", min_value=0.0, step=1.0, value=0.0)
                    with col2:
                        p_custo = st.number_input("Preço de Custo (R$)", min_value=0.0, step=1.0, value=10.0)
                        p_venda = st.number_input("Preço de Venda (R$)", min_value=0.0, step=1.0, value=20.0)
                    
                    if st.form_submit_button("Salvar Produto no Estoque"):
                        if novo_prod.strip() and salvar_produto_completo(novo_prod.strip(), grupo_prod, p_custo, p_venda, estoque_ini):
                            st.success("Produto cadastrado com sucesso!")
                            st.rerun()
                st.markdown("---")
                st.dataframe(carregar_dados("SELECT * FROM produtos"), use_container_width=True)

            with tab_forn:
                st.subheader("Cadastrar Novo Fornecedor")
                with st.form("form_cad_fornecedor"):
                    novo_forn = st.text_input("Nome do Fornecedor")
                    if st.form_submit_button("Salvar Fornecedor"):
                        if novo_forn.strip() and salvar_simples("fornecedores", "nome", novo_forn.strip()):
                            st.success("Fornecedor cadastrado com sucesso!")
                            st.rerun()
                st.markdown("---")
                st.dataframe(carregar_dados("SELECT * FROM fornecedores"), use_container_width=True)

            with tab_grup:
                st.subheader("Cadastrar Novo Grupo")
                with st.form("form_cad_grupo"):
                    novo_grup = st.text_input("Nome do Grupo")
                    if st.form_submit_button("Salvar Grupo"):
                        if novo_grup.strip() and salvar_simples("grupos", "nome", novo_grup.strip()):
                            st.success("Grupo cadastrado com sucesso!")
                            st.rerun()
                st.markdown("---")
                st.dataframe(carregar_dados("SELECT * FROM grupos"), use_container_width=True)
