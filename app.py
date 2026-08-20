import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date
import io
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="CRM Comércio - Rey da Cebola",
    page_icon="📦",
    layout="wide"
)

# --- BANCO DE DADOS (SQLITE) ---
conn = sqlite3.connect("crm_comercio.db", check_same_thread=False)

def criar_tabelas():
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

criar_tabelas()

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

def gerar_pdf_relatorio(titulo, dataframe):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    
    styles = getSampleStyleSheet()
    title_style = styles['Heading1']
    title_style.alignment = 1
    
    elements.append(Paragraph(titulo, title_style))
    elements.append(Spacer(1, 20))
    
    if not dataframe.empty:
        dados = [dataframe.columns.tolist()] + dataframe.astype(str).values.tolist()
        tabela = Table(dados)
        tabela.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1E3A8A')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 10),
            ('BOTTOMPADDING', (0,0), (-1,0), 8),
            ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#F3F4F6')),
            ('GRID', (0,0), (-1,-1), 1, colors.grey)
        ]))
        elements.append(tabela)
    else:
        elements.append(Paragraph("Nenhum dado encontrado.", styles['Normal']))
        
    doc.build(elements)
    buffer.seek(0)
    return buffer

# --- ESTADO DA SESSÃO (PDV) ---
if "carrinho_pdv" not in st.session_state:
    st.session_state.carrinho_pdv = []

if "pdv_v_unit" not in st.session_state:
    st.session_state.pdv_v_unit = 0.0

if "pdv_forn" not in st.session_state:
    st.session_state.pdv_forn = ""

if "pdv_grupo" not in st.session_state:
    st.session_state.pdv_grupo = ""

# --- MENU LATERAL (TODAS AS 10 TELAS PRESERVADAS) ---
st.sidebar.title("📌 Menu Principal")
menu_admin = st.sidebar.radio(
    "Navegação",
    [
        "🛒 PDV — Frente de Caixa",
        "📂 Vendas / Pedidos Solicitados",
        "🔓 Abertura e Fechamento de Caixa",
        "📦 Cadastrar Produtos",
        "👥 Cadastrar Clientes",
        "🚚 Cadastrar Fornecedores",
        "🏷️ Cadastrar Grupos",
        "📊 Relatório de Vendas",
        "📑 Fiado / Contas a Receber",
        "📄 Relatórios Gerenciais (PDF)"
    ]
)

# --- 1. PDV — FRENTE DE CAIXA ---
if menu_admin == "🛒 PDV — Frente de Caixa":
    st.title("🛒 PDV — Frente de Caixa")

    df_caixa_aberto = carregar_dados("SELECT * FROM caixa_sessoes WHERE status = 'ABERTO'")
    if df_caixa_aberto.empty:
        st.warning("⚠️ Atenção: O caixa está fechado. Abra o caixa antes de realizar vendas.")

    clientes_opt = carregar_coluna("clientes", "nome") or ["Cliente Geral"]
    produtos_opt = carregar_coluna("produtos", "nome") or ["Nenhum produto cadastrado"]
    fornecedores_opt = carregar_coluna("fornecedores", "fornecedor") or ["Geral"]
    grupos_opt = carregar_coluna("grupos", "grupo") or ["GERAL"]

    cliente_pdv = st.selectbox("Selecione o Cliente", clientes_opt)

    st.markdown("#### ➕ Adicionar Item ao Carrinho")

    def atualizar_dados_produto():
        prod_selecionado = st.session_state.pdv_select_produto
        df_prod_info = carregar_dados(f"SELECT * FROM produtos WHERE TRIM(nome) = TRIM('{prod_selecionado}')")
        
        if not df_prod_info.empty:
            linha_prod = df_prod_info.iloc[0]
            cols_p = df_prod_info.columns.tolist()

            precos = [linha_prod[col] for col in ["valor_venda", "preco_venda"] if col in cols_p and pd.notna(linha_prod[col])]
            st.session_state.pdv_v_unit = float(precos[0]) if precos else 0.0

            fornecs = [str(linha_prod[col]) for col in ["fornecedor"] if col in cols_p and pd.notna(linha_prod[col])]
            if fornecs and fornecs[0] in fornecedores_opt:
                st.session_state.pdv_forn = fornecs[0]

            grps = [str(linha_prod[col]) for col in ["grupo"] if col in cols_p and pd.notna(linha_prod[col])]
            if grps and grps[0] in grupos_opt:
                st.session_state.pdv_grupo = grps[0]

    prod_item = st.selectbox("Selecione o Produto", produtos_opt, key="pdv_select_produto", on_change=atualizar_dados_produto)

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

        if st.form_submit_button("➕ Incluir no Carrinho"):
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
    st.subheader("🛒 Carrinho de Compras")

    if st.session_state.carrinho_pdv:
        df_carrinho = pd.DataFrame(st.session_state.carrinho_pdv)
        st.dataframe(df_carrinho, use_container_width=True)

        if st.button("🗑️ Limpar Carrinho"):
            st.session_state.carrinho_pdv = []
            st.rerun()

        total_geral_carrinho = df_carrinho['valor_total'].sum()

        with st.form("form_finalizar_pagamento_pdv"):
            f_pag = st.selectbox("Forma de Pagamento", ["Dinheiro", "Pix", "Cartão de Crédito", "Cartão de Débito", "Crediário / Fiado"])
            v_rec = st.number_input("Valor Recebido (R$)", min_value=0.0, step=1.0, value=total_geral_carrinho)
            troco = max(0.0, v_rec - total_geral_carrinho)

            st.metric("Valor Total", f"R$ {total_geral_carrinho:,.2f}")
            st.metric("Troco", f"R$ {troco:,.2f}")

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

# --- 2. VENDAS / PEDIDOS SOLICITADOS ---
elif menu_admin == "📂 Vendas / Pedidos Solicitados":
    st.title("📂 Vendas e Pedidos Solicitados")
    df_pedidos = carregar_dados("SELECT * FROM pedidos ORDER BY id DESC")
    st.dataframe(df_pedidos if not df_pedidos.empty else pd.DataFrame(), use_container_width=True)

# --- 3. ABERTURA E FECHAMENTO DE CAIXA ---
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
                st.success("Caixa aberto!")
                st.rerun()
    else:
        sessao_id = int(df_caixa_atual.iloc[0]['id'])
        saldo_inicial = float(df_caixa_atual.iloc[0]['saldo_inicial'])
        st.success(f"🟢 **Caixa ABERTO** desde: {df_caixa_atual.iloc[0]['data_abertura']}")
        
        df_movs = carregar_dados(f"SELECT * FROM caixa_movimentacoes WHERE sessao_id = {sessao_id}")
        total_mov = df_movs['valor'].sum() if not df_movs.empty and 'valor' in df_movs.columns else 0.0
        st.metric("Total Movimentado", f"R$ {total_mov:,.2f}")

        if st.button("🔴 Fechar Caixa"):
            cursor = conn.cursor()
            cursor.execute("UPDATE caixa_sessoes SET status = 'FECHADO', data_fechamento = ?, saldo_final = ? WHERE id = ?", 
                           (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), saldo_inicial + total_mov, sessao_id))
            conn.commit()
            st.success("Caixa fechado!")
            st.rerun()

# --- 4. CADASTRO DE PRODUTOS ---
elif menu_admin == "📦 Cadastrar Produtos":
    st.title("📦 Cadastrar Produtos")
    fornecedores_opt = carregar_coluna("fornecedores", "fornecedor") or ["Geral"]
    grupos_opt = carregar_coluna("grupos", "grupo") or ["GERAL"]
    
    with st.form("form_produto"):
        nome_prod = st.text_input("Nome do Produto")
        col_p1, col_p2 = st.columns(2)
        fornec_prod = col_p1.selectbox("Fornecedor", fornecedores_opt)
        grupo_prod = col_p2.selectbox("Grupo", grupos_opt)
        
        col_p3, col_p4, col_p5 = st.columns(3)
        p_custo = col_p3.number_input("Preço Custo (R$)", min_value=0.0, step=0.10)
        v_venda = col_p4.number_input("Preço Venda (R$)", min_value=0.0, step=0.10)
        qtd_estoque = col_p5.number_input("Estoque Inicial", min_value=0.0, step=1.0)
        
        if st.form_submit_button("Salvar Produto"):
            cursor = conn.cursor()
            cursor.execute("INSERT INTO produtos (nome, fornecedor, grupo, preco_custo, valor_venda, estoque) VALUES (?, ?, ?, ?, ?, ?)",
                           (nome_prod, fornec_prod, grupo_prod, p_custo, v_venda, qtd_estoque))
            conn.commit()
            st.success(f"Produto '{nome_prod}' cadastrado!")
            st.rerun()

    st.dataframe(carregar_dados("SELECT * FROM produtos"), use_container_width=True)

# --- 5. CADASTRO DE CLIENTES ---
elif menu_admin == "👥 Cadastrar Clientes":
    st.title("👥 Cadastrar Clientes")
    with st.form("form_cliente"):
        nome_cli = st.text_input("Nome Completo")
        col_c1, col_c2 = st.columns(2)
        tel_cli = col_c1.text_input("Telefone")
        email_cli = col_c2.text_input("E-mail")
        cpf_cli = st.text_input("CPF / CNPJ")
        end_cli = st.text_input("Endereço")
        limite_credito = st.number_input("Limite de Crédito Fiado (R$)", min_value=0.0, step=50.0)
        
        if st.form_submit_button("Salvar Cliente"):
            cursor = conn.cursor()
            cursor.execute("INSERT INTO clientes (nome, telefone, email, cpf_cnpj, endereco, limite_credito) VALUES (?, ?, ?, ?, ?, ?)",
                           (nome_cli, tel_cli, email_cli, cpf_cli, end_cli, limite_credito))
            conn.commit()
            st.success(f"Cliente '{nome_cli}' cadastrado!")
            st.rerun()

    st.dataframe(carregar_dados("SELECT * FROM clientes"), use_container_width=True)

# --- 6. CADASTRO DE FORNECEDORES ---
elif menu_admin == "🚚 Cadastrar Fornecedores":
    st.title("🚚 Cadastrar Fornecedores")
    with st.form("form_fornecedor"):
        nome_forn = st.text_input("Nome Fornecedor")
        cnpj_forn = st.text_input("CNPJ")
        tel_forn = st.text_input("Telefone")
        email_forn = st.text_input("E-mail")
        
        if st.form_submit_button("Salvar Fornecedor"):
            cursor = conn.cursor()
            cursor.execute("INSERT INTO fornecedores (fornecedor, cnpj, telefone, email) VALUES (?, ?, ?, ?)",
                           (nome_forn, cnpj_forn, tel_forn, email_forn))
            conn.commit()
            st.success("Fornecedor cadastrado!")
            st.rerun()

    st.dataframe(carregar_dados("SELECT * FROM fornecedores"), use_container_width=True)

# --- 7. CADASTRO DE GRUPOS ---
elif menu_admin == "🏷️ Cadastrar Grupos":
    st.title("🏷️ Cadastrar Grupos")
    with st.form("form_grupo"):
        nome_grupo = st.text_input("Nome do Grupo")
        if st.form_submit_button("Salvar Grupo"):
            cursor = conn.cursor()
            cursor.execute("INSERT INTO grupos (grupo) VALUES (?)", (nome_grupo,))
            conn.commit()
            st.success("Grupo cadastrado!")
            st.rerun()

    st.dataframe(carregar_dados("SELECT * FROM grupos"), use_container_width=True)

# --- 8. RELATÓRIO DE VENDAS ---
elif menu_admin == "📊 Relatório de Vendas":
    st.title("📊 Relatório de Vendas")
    df_vendas = carregar_dados("SELECT * FROM pedidos ORDER BY id DESC")
    st.dataframe(df_vendas, use_container_width=True)

# --- 9. FIADO / CONTAS A RECEBER ---
elif menu_admin == "📑 Fiado / Contas a Receber":
    st.title("📑 Contas Fiado Pendentes")
    df_fiado = carregar_dados("SELECT * FROM fiado_contas WHERE status = 'Pendente'")
    st.dataframe(df_fiado, use_container_width=True)

# --- 10. RELATÓRIOS GERENCIAIS (PDF) ---
elif menu_admin == "📄 Relatórios Gerenciais (PDF)":
    st.title("📄 Relatórios Gerenciais com Exportação em PDF")
    
    tipo_relatorio = st.selectbox("Selecione o Relatório", ["Vendas Realizadas", "Estoque de Produtos", "Fiados Pendentes"])
    
    df_export = pd.DataFrame()
    if tipo_relatorio == "Vendas Realizadas":
        df_export = carregar_dados("SELECT id, data, cliente, produto, quantidade, valor_total FROM pedidos")
    elif tipo_relatorio == "Estoque de Produtos":
        df_export = carregar_dados("SELECT id, nome, fornecedor, grupo, valor_venda, estoque FROM produtos")
    elif tipo_relatorio == "Fiados Pendentes":
        df_export = carregar_dados("SELECT id, cliente, valor, data, observacao FROM fiado_contas WHERE status = 'Pendente'")

    st.dataframe(df_export, use_container_width=True)

    if not df_export.empty:
        pdf_data = gerar_pdf_relatorio(f"Relatório de {tipo_relatorio}", df_export)
        st.download_button(
            label="📥 Baixar Relatório em PDF",
            data=pdf_data,
            file_name=f"relatorio_{tipo_relatorio.lower().replace(' ', '_')}.pdf",
            mime="application/pdf"
        )
