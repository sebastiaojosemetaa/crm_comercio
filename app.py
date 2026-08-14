import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import urllib.parse
import io
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# Configuração da página
st.set_page_config(page_title="CRM Comércio", page_icon="📦", layout="wide")

# Inicialização do Banco de Dados
def init_db():
    conn = sqlite3.connect('crm_comercio.db', check_same_thread=False)
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE,
            telefone TEXT,
            email TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS fornecedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS grupos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT,
            nome TEXT,
            produto TEXT,
            fornecedor TEXT,
            grupo TEXT,
            preco_custo REAL,
            valor_compra REAL,
            preco_venda REAL,
            valor_venda REAL,
            estoque REAL,
            quantidade REAL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS vendas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo_venda TEXT,
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
            status_pagamento TEXT DEFAULT 'PAGO',
            tipo TEXT DEFAULT 'VENDA'
        )
    ''')
    
    # Auto-patch para garantir colunas necessárias
    try:
        c.execute("PRAGMA table_info(vendas)")
        cols_existentes = [column[1] for column in c.fetchall()]
        colunas_necessarias = {
            'valor_total': "REAL DEFAULT 0",
            'forma_pagamento': "TEXT DEFAULT 'Dinheiro'",
            'valor_recebido': "REAL DEFAULT 0",
            'tipo': "TEXT DEFAULT 'VENDA'",
            'codigo_venda': "TEXT DEFAULT ''",
            'data': "TEXT DEFAULT ''"
        }
        for col, col_type in colunas_necessarias.items():
            if col not in cols_existentes and len(cols_existentes) > 0:
                c.execute(f"ALTER TABLE vendas ADD COLUMN {col} {col_type}")
    except Exception:
        pass
        
    conn.commit()
    return conn

conn = init_db()

# Leitura segura
def safe_read_sql(sql, params=None):
    try:
        return pd.read_sql_query(sql, conn, params=params)
    except Exception:
        return pd.DataFrame()

# Helper para ler produtos mapeando nomes antigos e novos
def get_produtos_df():
    df = safe_read_sql("SELECT * FROM produtos")
    if not df.empty:
        cols = df.columns
        if 'produto' in cols and 'nome' not in cols:
            df['nome'] = df['produto']
        elif 'nome' in cols and 'produto' not in cols:
            df['produto'] = df['nome']
            
        if 'quantidade' in cols and 'estoque' not in cols:
            df['estoque'] = df['quantidade']
        elif 'estoque' in cols and 'quantidade' not in cols:
            df['quantidade'] = df['estoque']
            
        if 'valor_venda' in cols and 'preco_venda' not in cols:
            df['preco_venda'] = df['valor_venda']
        elif 'preco_venda' in cols and 'valor_venda' not in cols:
            df['valor_venda'] = df['preco_venda']
            
        if 'valor_compra' in cols and 'preco_custo' not in cols:
            df['preco_custo'] = df['valor_compra']
        elif 'preco_custo' in cols and 'valor_compra' not in cols:
            df['valor_compra'] = df['preco_custo']
    return df

# Helper para ler vendas com compatibilidade de nomes de colunas
def get_vendas_df():
    df = safe_read_sql("SELECT * FROM vendas")
    if not df.empty:
        cols = df.columns
        df['quantidade'] = pd.to_numeric(df.get('quantidade', 0), errors='coerce').fillna(0.0)
        df['valor_venda'] = pd.to_numeric(df.get('valor_venda', 0), errors='coerce').fillna(0.0)
        
        if 'valor_total' not in cols:
            df['valor_total'] = df['quantidade'] * df['valor_venda']
        else:
            df['valor_total'] = pd.to_numeric(df['valor_total'], errors='coerce').fillna(df['quantidade'] * df['valor_venda'])
            
        if 'valor_recebido' not in cols:
            if 'forma_pagamento' in cols:
                df['valor_recebido'] = df.apply(
                    lambda r: 0.0 if 'fiado' in str(r.get('forma_pagamento', '')).lower() else r['valor_total'], axis=1
                )
            else:
                df['valor_recebido'] = df['valor_total']
        else:
            df['valor_recebido'] = pd.to_numeric(df['valor_recebido'], errors='coerce').fillna(0.0)
            
        if 'tipo' not in cols:
            df['tipo'] = 'VENDA'
            
        if 'forma_pagamento' not in cols:
            df['forma_pagamento'] = 'Dinheiro'
            
    return df

# Helper para atualizar estoque
def update_estoque_db(prod_id, novo_estoque):
    c = conn.cursor()
    c.execute("PRAGMA table_info(produtos)")
    cols = [col[1] for col in c.fetchall()]
    
    if 'quantidade' in cols:
        c.execute("UPDATE produtos SET quantidade = ? WHERE id = ?", (novo_estoque, prod_id))
    if 'estoque' in cols:
        c.execute("UPDATE produtos SET estoque = ? WHERE id = ?", (novo_estoque, prod_id))
    conn.commit()

# Gerar PDF
def gerar_pdf_pedido(codigo_pedido, df_itens, cliente):
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, 750, f"ORÇAMENTO / PEDIDO: {codigo_pedido}")
    p.setFont("Helvetica", 12)
    p.drawString(50, 730, f"Cliente: {cliente}")
    p.drawString(50, 715, f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    
    y = 670
    p.setFont("Helvetica-Bold", 10)
    p.drawString(50, y, "Produto")
    p.drawString(280, y, "Qtd")
    p.drawString(360, y, "Valor Unit. (R$)")
    p.drawString(460, y, "Total (R$)")
    p.line(50, y-5, 550, y-5)
    
    y -= 25
    p.setFont("Helvetica", 10)
    total_geral = 0
    for idx, row in df_itens.iterrows():
        prod = str(row.get('produto', ''))[:28]
        qtd = float(row.get('quantidade', 0))
        val = float(row.get('valor_venda', 0))
        subtotal = float(row.get('valor_total', qtd * val))
        total_geral += subtotal
        
        p.drawString(50, y, prod)
        p.drawString(280, y, f"{qtd:.2f}")
        p.drawString(360, y, f"{val:.2f}")
        p.drawString(460, y, f"{subtotal:.2f}")
        y -= 20
        if y < 100:
            p.showPage()
            y = 750
            
    p.line(50, y, 550, y)
    p.setFont("Helvetica-Bold", 12)
    p.drawString(360, y - 25, f"TOTAL: R$ {total_geral:.2f}")
    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer

# ==============================================================================
# MODO CLIENTE (VIA LINK)
# ==============================================================================
params = st.query_params
cliente_url = params.get("cliente", None) or params.get("cliente_id", None)

if cliente_url:
    st.markdown("""
        <style>
            [data-testid="stSidebar"] { display: none; }
        </style>
    """, unsafe_allow_html=True)
    
    st.title("📦 Área do Cliente - Meus Pedidos & Orçamentos")
    st.subheader(f"👋 Olá, {cliente_url}!")
    st.info("Abaixo você encontra o histórico exclusivo dos seus pedidos e orçamentos conosco.")
    
    df_pedidos_cliente = safe_read_sql(
        "SELECT * FROM vendas WHERE cliente = ? AND tipo = 'PEDIDO' ORDER BY id DESC", 
        params=(cliente_url,)
    )
    
    if df_pedidos_cliente.empty or 'codigo_venda' not in df_pedidos_cliente.columns:
        st.warning("Nenhum pedido ou orçamento encontrado para o seu cadastro no momento.")
    else:
        codigos = df_pedidos_cliente['codigo_venda'].unique()
        for cod in codigos:
            itens = df_pedidos_cliente[df_pedidos_cliente['codigo_venda'] == cod]
            qtds = pd.to_numeric(itens.get('quantidade', 0), errors='coerce').fillna(0)
            vals = pd.to_numeric(itens.get('valor_venda', 0), errors='coerce').fillna(0)
            total_pedido = (qtds * vals).sum()
            data_ped = itens['data'].iloc[0] if 'data' in itens.columns and not itens.empty else "N/A"
            
            with st.expander(f"📋 Pedido: {cod} | Data: {data_ped} | Total: R$ {total_pedido:.2f}", expanded=True):
                cols_to_show = [c for c in ['produto', 'quantidade', 'valor_venda', 'valor_total'] if c in itens.columns]
                st.dataframe(
                    itens[cols_to_show].rename(
                        columns={'produto': 'Produto', 'quantidade': 'Quantidade', 'valor_venda': 'Preço Unitário (R$)', 'valor_total': 'Total (R$)'}
                    ),
                    use_container_width=True
                )
                
                pdf_data = gerar_pdf_pedido(cod, itens, cliente_url)
                st.download_button(
                    label=f"📥 Baixar PDF do Pedido ({cod})",
                    data=pdf_data,
                    file_name=f"pedido_{cod}.pdf",
                    mime="application/pdf",
                    key=f"pdf_client_{cod}"
                )
    
    st.stop()

# ==============================================================================
# PAINEL ADMINISTRATIVO
# ==============================================================================

st.sidebar.title("CRM Comércio 📦")
menu = st.sidebar.radio(
    "Navegação",
    [
        "📊 Fechamento & Financeiro",
        "📑 Pedidos / Orçamentos",
        "🛒 Registrar Venda",
        "📥 Entrada de Estoque (Compras)",
        "📦 Estoque de Produtos",
        "👥 Cadastros (Clientes / Fornecedores / Grupos)"
    ]
)

# ------------------------------------------------------------------------------
# 1. FECHAMENTO & FINANCEIRO
# ------------------------------------------------------------------------------
if menu == "📊 Fechamento & Financeiro":
    st.title("📊 Painel Financeiro & Fechamento")
    
    df_vendas_all = get_vendas_df()
    
    if not df_vendas_all.empty:
        df_vendas = df_vendas_all[df_vendas_all['tipo'] != 'PEDIDO'].copy()
    else:
        df_vendas = pd.DataFrame()

    if df_vendas.empty:
        tot_faturamento = 0.0
        tot_caixa = 0.0
        tot_pendente = 0.0
    else:
        tot_faturamento = float(df_vendas['valor_total'].sum())
        tot_caixa = float(df_vendas['valor_recebido'].sum())
        tot_pendente = float(tot_faturamento - tot_caixa)
        
    c1, c2, c3 = st.columns(3)
    c1.metric("Faturamento Total", f"R$ {tot_faturamento:.2f}")
    c2.metric("Total Recebido em Caixa", f"R$ {tot_caixa:.2f}")
    c3.metric("Total a Receber (Fiado/Pendente)", f"R$ {tot_pendente:.2f}")
    
    st.subheader("📜 Resumo do Histórico de Vendas")
    st.dataframe(df_vendas, use_container_width=True)

# ------------------------------------------------------------------------------
# 2. PEDIDOS / ORÇAMENTOS
# ------------------------------------------------------------------------------
elif menu == "📑 Pedidos / Orçamentos":
    st.title("📑 Gestão de Pedidos e Orçamentos")
    
    st.markdown("---")
    st.subheader("🔗 Gerar Link Exclusivo para o Cliente")
    st.write("Envie este link para seu cliente visualizar apenas os próprios pedidos.")
    
    df_clientes_cad = safe_read_sql("SELECT nome FROM clientes")
    lista_cli = df_clientes_cad['nome'].dropna().tolist() if not df_clientes_cad.empty and 'nome' in df_clientes_cad.columns else []
    
    if lista_cli:
        cliente_sel = st.selectbox("Selecione o Cliente:", lista_cli)
        if cliente_sel:
            base_url = "https://crmcomercio-bqofgjfpnvferb7cw4rike.streamlit.app"
            link_cliente = f"{base_url}/?cliente={urllib.parse.quote(cliente_sel)}"
            st.code(link_cliente, language="text")
            
            msg_wa = urllib.parse.quote(f"Olá {cliente_sel}! Acompanhe seus pedidos e orçamentos pelo link exclusivo: {link_cliente}")
            st.markdown(f"[📲 **Clique aqui para enviar no WhatsApp do Cliente**](https://wa.me/?text={msg_wa})", unsafe_allow_html=True)
    else:
        st.info("Cadastre clientes na aba 'Cadastros' para gerar links individuais.")
        
    st.markdown("---")
    st.subheader("📋 Pedidos Cadastrados no Sistema")
    
    df_pedidos = safe_read_sql("SELECT * FROM vendas WHERE tipo = 'PEDIDO' ORDER BY id DESC")
    
    if df_pedidos.empty or 'codigo_venda' not in df_pedidos.columns:
        st.info("Nenhum pedido/orçamento registrado no momento.")
    else:
        codigos = df_pedidos['codigo_venda'].dropna().unique()
        for cod in codigos:
            itens = df_pedidos[df_pedidos['codigo_venda'] == cod]
            cli = itens['cliente'].iloc[0] if 'cliente' in itens.columns and not itens.empty else "Cliente N/A"
            qtds = pd.to_numeric(itens.get('quantidade', 0), errors='coerce').fillna(0)
            vals = pd.to_numeric(itens.get('valor_venda', 0), errors='coerce').fillna(0)
            total_ped = (qtds * vals).sum()
            
            with st.expander(f"Pedido: {cod} | Cliente: {cli} | Total: R$ {total_ped:.2f}"):
                cols_show = [c for c in ['produto', 'quantidade', 'valor_venda', 'valor_total'] if c in itens.columns]
                st.dataframe(itens[cols_show], use_container_width=True)
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button(f"✅ Converter Pedido {cod} em Venda Final", key=f"conv_{cod}"):
                        c = conn.cursor()
                        c.execute("UPDATE vendas SET tipo = 'VENDA' WHERE codigo_venda = ?", (cod,))
                        conn.commit()
                        st.success(f"Pedido {cod} convertido em Venda com sucesso!")
                        st.rerun()
                with col2:
                    pdf_bytes = gerar_pdf_pedido(cod, itens, cli)
                    st.download_button(
                        label="📥 Baixar PDF do Orçamento",
                        data=pdf_bytes,
                        file_name=f"orcamento_{cod}.pdf",
                        mime="application/pdf",
                        key=f"pdf_admin_{cod}"
                    )

# ------------------------------------------------------------------------------
# 3. REGISTRAR VENDA / PEDIDO
# ------------------------------------------------------------------------------
elif menu == "🛒 Registrar Venda":
    st.title("🛒 Nova Venda / Novo Pedido")
    
    df_clientes = safe_read_sql("SELECT nome FROM clientes")
    df_prods = get_produtos_df()
    
    if df_prods.empty or 'nome' not in df_prods.columns:
        st.warning("Cadastre produtos no estoque antes de registrar vendas.")
    else:
        tipo_registro = st.radio("Tipo de Registro:", ["VENDA", "PEDIDO"], horizontal=True)
        list_cli_venda = df_clientes['nome'].dropna().tolist() if not df_clientes.empty and 'nome' in df_clientes.columns else ["Consumidor Final"]
        cliente_venda = st.selectbox("Cliente:", list_cli_venda)
        
        forma_pag = st.selectbox("Forma de Pagamento:", ["Dinheiro", "PIX", "Cartão de Crédito", "Cartão de Débito", "Crediário / Fiado"])
        
        st.subheader("Adicionar Itens")
        lista_produtos = df_prods['nome'].dropna().unique().tolist()
        prod_sel = st.selectbox("Selecione o Produto:", lista_produtos)
        
        prod_info = df_prods[df_prods['nome'] == prod_sel].iloc[0]
        
        qtd_venda = st.number_input("Quantidade:", min_value=0.1, value=1.0, step=0.5)
        val_venda = st.number_input("Preço de Venda (R$):", min_value=0.0, value=float(prod_info.get('preco_venda', 0.0)))
        val_total = qtd_venda * val_venda
        
        st.info(f"💰 Valor Total: **R$ {val_total:.2f}**")
        
        # Define valor recebido padrão de acordo com a forma de pagamento
        val_recebido_default = 0.0 if forma_pag == "Crediário / Fiado" else val_total
        val_recebido = st.number_input("Valor Recebido (R$):", min_value=0.0, value=float(val_recebido_default))
        
        if st.button("➕ Confirmar Venda / Pedido"):
            cod_doc = f"DOC-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            data_atual = datetime.now().strftime('%Y-%m-%d %H:%M')
            fornecedor_prod = prod_info.get('fornecedor', 'BAHIA')
            grupo_prod = prod_info.get('grupo', 'Geral')
            
            c = conn.cursor()
            c.execute('''
                INSERT INTO vendas (codigo_venda, data, cliente, produto, fornecedor, grupo, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, tipo)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (cod_doc, data_atual, cliente_venda, prod_sel, fornecedor_prod, grupo_prod, qtd_venda, val_venda, val_total, forma_pag, val_recebido, tipo_registro))
            
            if tipo_registro == "VENDA":
                novo_est = float(prod_info.get('estoque', 0.0)) - qtd_venda
                update_estoque_db(prod_info['id'], novo_est)
                
            conn.commit()
            st.success(f"{tipo_registro} cadastrado(a) com sucesso! Código: {cod_doc}")

# ------------------------------------------------------------------------------
# 4. ENTRADA DE ESTOQUE
# ------------------------------------------------------------------------------
elif menu == "📥 Entrada de Estoque (Compras)":
    st.title("📥 Entrada de Estoque")
    
    df_prods = get_produtos_df()
    if not df_prods.empty and 'nome' in df_prods.columns:
        prod_compra = st.selectbox("Selecione o Produto para dar Entrada:", df_prods['nome'].tolist())
        qtd_compra = st.number_input("Quantidade Comprada:", min_value=0.1, value=10.0)
        
        if st.button("📥 Dar Entrada no Estoque"):
            prod_atual = df_prods[df_prods['nome'] == prod_compra].iloc[0]
            novo_est = float(prod_atual.get('estoque', 0.0)) + qtd_compra
            update_estoque_db(prod_atual['id'], novo_est)
            st.success(f"Estoque atualizado! Novo estoque de {prod_compra}: {novo_est}")
    else:
        st.info("Nenhum produto cadastrado para dar entrada.")

# ------------------------------------------------------------------------------
# 5. ESTOQUE DE PRODUTOS
# ------------------------------------------------------------------------------
elif menu == "📦 Estoque de Produtos":
    st.title("📦 Cadastro & Consulta de Produtos")
    
    with st.expander("➕ Cadastrar Novo Produto"):
        c_cod = st.text_input("Código do Produto")
        c_nome = st.text_input("Nome do Produto")
        c_forn = st.text_input("Fornecedor", value="BAHIA")
        c_grup = st.text_input("Grupo", value="Geral")
        c_custo = st.number_input("Preço de Custo (R$)", min_value=0.0)
        c_venda = st.number_input("Preço de Venda (R$)", min_value=0.0)
        c_est = st.number_input("Estoque Inicial", min_value=0.0)
        
        if st.button("Salvar Produto"):
            c = conn.cursor()
            c.execute("PRAGMA table_info(produtos)")
            cols_db = [col[1] for col in c.fetchall()]
            
            if 'produto' in cols_db and 'nome' not in cols_db:
                c.execute('''
                    INSERT INTO produtos (produto, quantidade, valor_compra, valor_venda, grupo)
                    VALUES (?, ?, ?, ?, ?)
                ''', (c_nome, c_est, c_custo, c_venda, c_grup))
            else:
                c.execute('''
                    INSERT INTO produtos (codigo, nome, fornecedor, grupo, preco_custo, preco_venda, estoque)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (c_cod, c_nome, c_forn, c_grup, c_custo, c_venda, c_est))
                
            conn.commit()
            st.success("Produto cadastrado!")
            st.rerun()
            
    df_prods = safe_read_sql("SELECT * FROM produtos")
    st.dataframe(df_prods, use_container_width=True)

# ------------------------------------------------------------------------------
# 6. CADASTROS
# ------------------------------------------------------------------------------
elif menu == "👥 Cadastros (Clientes / Fornecedores / Grupos)":
    st.title("👥 Cadastros do Sistema")
    
    tab1, tab2, tab3 = st.tabs(["Clientes", "Fornecedores", "Grupos"])
    
    with tab1:
        st.subheader("Cadastrar Cliente")
        nome_cli = st.text_input("Nome do Cliente")
        tel_cli = st.text_input("Telefone / WhatsApp")
        if st.button("Salvar Cliente"):
            try:
                c = conn.cursor()
                c.execute("INSERT INTO clientes (nome, telefone) VALUES (?, ?)", (nome_cli, tel_cli))
                conn.commit()
                st.success("Cliente cadastrado com sucesso!")
                st.rerun()
            except:
                st.error("Cliente já existente ou erro ao salvar.")
        st.dataframe(safe_read_sql("SELECT * FROM clientes"), use_container_width=True)

    with tab2:
        st.subheader("Cadastrar Fornecedor")
        nome_forn = st.text_input("Nome do Fornecedor")
        if st.button("Salvar Fornecedor"):
            try:
                c = conn.cursor()
                c.execute("INSERT INTO fornecedores (nome) VALUES (?)", (nome_forn,))
                conn.commit()
                st.success("Fornecedor cadastrado!")
                st.rerun()
            except:
                st.error("Fornecedor já existente ou erro ao salvar.")
        st.dataframe(safe_read_sql("SELECT * FROM fornecedores"), use_container_width=True)

    with tab3:
        st.subheader("Cadastrar Grupo")
        nome_grup = st.text_input("Nome do Grupo")
        if st.button("Salvar Grupo"):
            try:
                c = conn.cursor()
                c.execute("INSERT INTO grupos (nome) VALUES (?)", (nome_grup,))
                conn.commit()
                st.success("Grupo cadastrado!")
                st.rerun()
            except:
                st.error("Grupo já existente ou erro ao salvar.")
        st.dataframe(safe_read_sql("SELECT * FROM grupos"), use_container_width=True)
