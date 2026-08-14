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

# Conexão com o banco de dados
def get_db():
    conn = sqlite3.connect('crm_comercio.db', check_same_thread=False)
    return conn

conn = get_db()
c = conn.cursor()

# Criação das tabelas
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
        codigo TEXT UNIQUE,
        nome TEXT,
        fornecedor TEXT,
        grupo TEXT,
        preco_custo REAL,
        preco_venda REAL,
        estoque REAL
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
        status_pagamento TEXT,
        tipo TEXT DEFAULT 'VENDA'
    )
''')
conn.commit()

# Função para Gerar PDF de Pedidos
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
        prod = str(row['produto'])[:28]
        qtd = float(row['quantidade'])
        val = float(row['valor_venda'])
        subtotal = qtd * val
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
# VERIFICAÇÃO DE MODO CLIENTE (VIA LINK / URL)
# ==============================================================================
params = st.query_params
cliente_url = params.get("cliente", None) or params.get("cliente_id", None)

if cliente_url:
    # Oculta a barra lateral para o cliente não navegar no seu sistema
    st.markdown("""
        <style>
            [data-testid="stSidebar"] { display: none; }
        </style>
    """, unsafe_allow_html=True)
    
    st.title("📦 Área do Cliente - Meus Pedidos & Orçamentos")
    st.subheader(f"👋 Olá, {cliente_url}!")
    st.info("Abaixo você encontra o histórico exclusivo dos seus pedidos e orçamentos conosco.")
    
    # Busca apenas os pedidos do cliente específico
    df_pedidos_cliente = pd.read_sql_query(
        "SELECT * FROM vendas WHERE cliente = ? AND tipo = 'PEDIDO' ORDER BY id DESC", 
        conn, 
        params=(cliente_url,)
    )
    
    if df_pedidos_cliente.empty:
        st.warning("Nenhum pedido ou orçamento encontrado para o seu cadastro no momento.")
    else:
        codigos = df_pedidos_cliente['codigo_venda'].unique()
        for cod in codigos:
            itens = df_pedidos_cliente[df_pedidos_cliente['codigo_venda'] == cod]
            total_pedido = (itens['quantidade'] * itens['valor_venda']).sum()
            data_ped = itens['data'].iloc[0]
            
            with st.expander(f"📋 Pedido: {cod} | Data: {data_ped} | Total: R$ {total_pedido:.2f}", expanded=True):
                st.dataframe(
                    itens[['produto', 'quantidade', 'valor_venda']].rename(
                        columns={'produto': 'Produto', 'quantidade': 'Quantidade', 'valor_venda': 'Preço Unitário (R$)'}
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
    
    st.stop() # Encerra o script para garantir que o cliente não veja o resto do painel admin

# ==============================================================================
# PAINEL ADMINISTRATIVO (SISTEMA COMPLETO)
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
    
    df_vendas = pd.read_sql_query("SELECT * FROM vendas WHERE tipo = 'VENDA'", conn)
    
    if df_vendas.empty:
        tot_faturamento = 0.0
        tot_caixa = 0.0
        tot_pendente = 0.0
    else:
        df_vendas['total'] = df_vendas['quantidade'] * df_vendas['valor_venda']
        tot_faturamento = df_vendas['total'].sum()
        tot_caixa = df_vendas[df_vendas['status_pagamento'] == 'PAGO']['total'].sum()
        tot_pendente = df_vendas[df_vendas['status_pagamento'] != 'PAGO']['total'].sum()
        
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
    
    # SEÇÃO PARA GERAR LINK PARA CLIENTE
    st.markdown("---")
    st.subheader("🔗 Gerar Link Exclusivo para o Cliente")
    st.write("Envie este link para seu cliente visualizar **apenas os próprios pedidos**, sem acesso ao financeiro ou opção de converter vendas.")
    
    df_clientes_cad = pd.read_sql_query("SELECT nome FROM clientes", conn)
    lista_cli = df_clientes_cad['nome'].tolist() if not df_clientes_cad.empty else []
    
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
    
    df_pedidos = pd.read_sql_query("SELECT * FROM vendas WHERE tipo = 'PEDIDO' ORDER BY id DESC", conn)
    
    if df_pedidos.empty:
        st.info("Nenhum pedido/orçamento registrado no momento.")
    else:
        codigos = df_pedidos['codigo_venda'].unique()
        for cod in codigos:
            itens = df_pedidos[df_pedidos['codigo_venda'] == cod]
            cli = itens['cliente'].iloc[0]
            total_ped = (itens['quantidade'] * itens['valor_venda']).sum()
            
            with st.expander(f"Pedido: {cod} | Cliente: {cli} | Total: R$ {total_ped:.2f}"):
                st.dataframe(itens[['produto', 'quantidade', 'valor_venda']], use_container_width=True)
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button(f"✅ Converter Pedido {cod} em Venda Final", key=f"conv_{cod}"):
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
    
    df_clientes = pd.read_sql_query("SELECT nome FROM clientes", conn)
    df_prods = pd.read_sql_query("SELECT * FROM produtos", conn)
    
    if df_prods.empty:
        st.warning("Cadastre produtos no estoque antes de registrar vendas.")
    else:
        tipo_registro = st.radio("Tipo de Registro:", ["VENDA", "PEDIDO"], horizontal=True)
        cliente_venda = st.selectbox("Cliente:", df_clientes['nome'].tolist() if not df_clientes.empty else ["Consumidor Final"])
        status_pag = st.selectbox("Status do Pagamento:", ["PAGO", "PENDENTE (FIADO)"])
        
        st.subheader("Adicionar Itens")
        prod_sel = st.selectbox("Selecione o Produto:", df_prods['nome'].tolist())
        prod_info = df_prods[df_prods['nome'] == prod_sel].iloc[0]
        
        qtd_venda = st.number_input("Quantidade:", min_value=0.1, value=1.0, step=0.5)
        val_venda = st.number_input("Preço de Venda (R$):", min_value=0.0, value=float(prod_info['preco_venda']))
        
        if st.button("➕ Confirmar Venda / Pedido"):
            cod_doc = f"DOC-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            data_atual = datetime.now().strftime('%Y-%m-%d %H:%M')
            
            c.execute('''
                INSERT INTO vendas (codigo_venda, data, cliente, produto, fornecedor, grupo, quantidade, valor_venda, status_pagamento, tipo)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (cod_doc, data_atual, cliente_venda, prod_sel, prod_info['fornecedor'], prod_info['grupo'], qtd_venda, val_venda, status_pag, tipo_registro))
            
            # Baixa estoque apenas se for VENDA
            if tipo_registro == "VENDA":
                novo_est = prod_info['estoque'] - qtd_venda
                c.execute("UPDATE produtos SET estoque = ? WHERE id = ?", (novo_est, prod_info['id']))
                
            conn.commit()
            st.success(f"{tipo_registro} cadastrado(a) com sucesso! Código: {cod_doc}")

# ------------------------------------------------------------------------------
# 4. ENTRADA DE ESTOQUE
# ------------------------------------------------------------------------------
elif menu == "📥 Entrada de Estoque (Compras)":
    st.title("📥 Entrada de Estoque")
    
    df_prods = pd.read_sql_query("SELECT * FROM produtos", conn)
    if not df_prods.empty:
        prod_compra = st.selectbox("Selecione o Produto para dar Entrada:", df_prods['nome'].tolist())
        qtd_compra = st.number_input("Quantidade Comprada:", min_value=0.1, value=10.0)
        
        if st.button("📥 Dar Entrada no Estoque"):
            prod_atual = df_prods[df_prods['nome'] == prod_compra].iloc[0]
            novo_est = prod_atual['estoque'] + qtd_compra
            c.execute("UPDATE produtos SET estoque = ? WHERE id = ?", (novo_est, prod_atual['id']))
            conn.commit()
            st.success(f"Estoque atualizado! Novo estoque de {prod_compra}: {novo_est}")

# ------------------------------------------------------------------------------
# 5. ESTOQUE DE PRODUTOS
# ------------------------------------------------------------------------------
elif menu == "📦 Estoque de Produtos":
    st.title("📦 Cadastro & Consulta de Produtos")
    
    with st.expander("➕ Cadastrar Novo Produto"):
        c_cod = st.text_input("Código do Produto")
        c_nome = st.text_input("Nome do Produto")
        c_forn = st.text_input("Fornecedor")
        c_grup = st.text_input("Grupo")
        c_custo = st.number_input("Preço de Custo (R$)", min_value=0.0)
        c_venda = st.number_input("Preço de Venda (R$)", min_value=0.0)
        c_est = st.number_input("Estoque Inicial", min_value=0.0)
        
        if st.button("Salvar Produto"):
            c.execute('''
                INSERT INTO produtos (codigo, nome, fornecedor, grupo, preco_custo, preco_venda, estoque)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (c_cod, c_nome, c_forn, c_grup, c_custo, c_venda, c_est))
            conn.commit()
            st.success("Produto cadastrado!")
            st.rerun()
            
    df_prods = pd.read_sql_query("SELECT * FROM produtos", conn)
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
                c.execute("INSERT INTO clientes (nome, telefone) VALUES (?, ?)", (nome_cli, tel_cli))
                conn.commit()
                st.success("Cliente cadastrado com sucesso!")
                st.rerun()
            except:
                st.error("Cliente já existente.")
        st.dataframe(pd.read_sql_query("SELECT * FROM clientes", conn), use_container_width=True)

    with tab2:
        st.subheader("Cadastrar Fornecedor")
        nome_forn = st.text_input("Nome do Fornecedor")
        if st.button("Salvar Fornecedor"):
            try:
                c.execute("INSERT INTO fornecedores (nome) VALUES (?)", (nome_forn,))
                conn.commit()
                st.success("Fornecedor cadastrado!")
                st.rerun()
            except:
                st.error("Fornecedor já existente.")
        st.dataframe(pd.read_sql_query("SELECT * FROM fornecedores", conn), use_container_width=True)

    with tab3:
        st.subheader("Cadastrar Grupo")
        nome_grup = st.text_input("Nome do Grupo")
        if st.button("Salvar Grupo"):
            try:
                c.execute("INSERT INTO grupos (nome) VALUES (?)", (nome_grup,))
                conn.commit()
                st.success("Grupo cadastrado!")
                st.rerun()
            except:
                st.error("Grupo já existente.")
        st.dataframe(pd.read_sql_query("SELECT * FROM grupos", conn), use_container_width=True)
