import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, date
import io

# Importação para geração de PDF
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

st.set_page_config(page_title="CRM Comércio - Gestão Completa", layout="wide", page_icon="📦")

# -----------------------------------------------------------------------------
# DEFINIÇÃO DE SENHAS (ADMIN E CLIENTES)
# -----------------------------------------------------------------------------
SENHA_ADMIN = "13142715"  # Senha da Administração/Vendedor

SENHAS_CLIENTES = {
    "Carlos Alberto": "1234",
    "Sebastião": "123456",
    "Valeilde Loja 01": "112345"
}
SENHA_CLIENTE_PADRAO = "0000"

# -----------------------------------------------------------------------------
# CONEXÃO E CRIAÇÃO DO BANCO DE DADOS
# -----------------------------------------------------------------------------
conn = sqlite3.connect('crm_comercio.db', check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''
    CREATE TABLE IF NOT EXISTS produtos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        produto TEXT UNIQUE,
        grupo TEXT DEFAULT 'Geral',
        quantidade REAL DEFAULT 0.0,
        valor_compra REAL DEFAULT 0.0,
        valor_venda REAL DEFAULT 0.0
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS clientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente TEXT UNIQUE,
        cpf TEXT,
        endereco TEXT,
        email TEXT,
        fone TEXT
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS fornecedores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fornecedor TEXT UNIQUE
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS grupos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        grupo TEXT UNIQUE
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS compras (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        produto TEXT,
        fornecedor TEXT,
        grupo TEXT,
        quantidade REAL,
        valor_compra REAL,
        valor_venda REAL,
        valor_total REAL,
        data TEXT
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS vendas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo_venda TEXT,
        cliente TEXT,
        produto TEXT,
        fornecedor TEXT DEFAULT 'Geral',
        grupo TEXT DEFAULT 'Geral',
        quantidade REAL,
        valor_venda REAL,
        valor_total REAL,
        forma_pagamento TEXT,
        valor_recebido REAL,
        troco REAL,
        restante REAL,
        data TEXT
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS pedidos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo_pedido TEXT,
        cliente TEXT,
        produto TEXT,
        fornecedor TEXT DEFAULT 'Geral',
        grupo TEXT DEFAULT 'Geral',
        quantidade REAL,
        valor_unitario REAL,
        valor_total REAL,
        status TEXT,
        observacoes TEXT,
        data TEXT
    )
''')
conn.commit()

# Compatibilidade de colunas
for query in [
    "ALTER TABLE pedidos ADD COLUMN codigo_pedido TEXT",
    "ALTER TABLE produtos ADD COLUMN grupo TEXT DEFAULT 'Geral'",
    "ALTER TABLE pedidos ADD COLUMN fornecedor TEXT DEFAULT 'Geral'",
    "ALTER TABLE pedidos ADD COLUMN grupo TEXT DEFAULT 'Geral'",
    "ALTER TABLE vendas ADD COLUMN grupo TEXT DEFAULT 'Geral'",
    "ALTER TABLE vendas ADD COLUMN fornecedor TEXT DEFAULT 'Geral'",
    "ALTER TABLE vendas ADD COLUMN codigo_venda TEXT"
]:
    try:
        cursor.execute(query)
    except:
        pass

conn.commit()

# CARGA INICIAL SE ESTIVER VAZIO
cursor.execute("SELECT COUNT(*) FROM produtos")
if cursor.fetchone()[0] == 0:
    PRODUTOS_INICIAIS = [
        ("ABACATE", "FRUTAS", 10.0, 80.0, 117.0),
        ("ABACAXI PEQUENO", "FRUTAS", 10.0, 5.0, 6.0),
        ("CEBOLA CAIXA 1", "VERDURAS", 10.0, 55.0, 70.0),
        ("TOMATE 1ª", "VERDURAS", 10.0, 40.0, 70.0)
    ]
    for p, g, q, vc, vv in PRODUTOS_INICIAIS:
        cursor.execute("INSERT INTO produtos (produto, grupo, quantidade, valor_compra, valor_venda) VALUES (?, ?, ?, ?, ?)", (p, g, q, vc, vv))

cursor.execute("SELECT COUNT(*) FROM clientes")
if cursor.fetchone()[0] == 0:
    CLIENTES_INICIAIS = [
        ("Sebastião", "95451160000", "Rua Caipira, 174 Centro", "sebastiaoappsheet@gmail.com", "99985020000"),
        ("Carlos Alberto", "", "", "midiapura07@gmail.com", ""),
        ("Valeilde Loja 01", "", "", "", "")
    ]
    for cli, cpf, end, em, fn in CLIENTES_INICIAIS:
        cursor.execute("INSERT INTO clientes (cliente, cpf, endereco, email, fone) VALUES (?, ?, ?, ?, ?)", (cli, cpf, end, em, fn))

cursor.execute("SELECT COUNT(*) FROM fornecedores")
if cursor.fetchone()[0] == 0:
    FORNECEDORES_INICIAIS = [("BAHIA",), ("TIANGUA",)]
    for f in FORNECEDORES_INICIAIS:
        cursor.execute("INSERT INTO fornecedores (fornecedor) VALUES (?)", f)

cursor.execute("SELECT COUNT(*) FROM grupos")
if cursor.fetchone()[0] == 0:
    GRUPOS_INICIAIS = [("FRUTAS",), ("VERDURAS",), ("LEGUMES",), ("GERAL",)]
    for g in GRUPOS_INICIAIS:
        cursor.execute("INSERT INTO grupos (grupo) VALUES (?)", g)

conn.commit()

# Inicializar Carrinhos na sessão
if 'carrinho_pedido' not in st.session_state:
    st.session_state.carrinho_pedido = []
if 'carrinho_venda' not in st.session_state:
    st.session_state.carrinho_venda = []

# CARREGAR LISTAS ATUALIZADAS
clientes_df = pd.read_sql_query("SELECT cliente FROM clientes ORDER BY cliente ASC", conn)
fornecedores_df = pd.read_sql_query("SELECT fornecedor FROM fornecedores ORDER BY fornecedor ASC", conn)
grupos_df = pd.read_sql_query("SELECT grupo FROM grupos ORDER BY grupo ASC", conn)

list_clientes = clientes_df['cliente'].tolist() if not clientes_df.empty else ["Cliente Geral"]
list_fornecedores = fornecedores_df['fornecedor'].tolist() if not fornecedores_df.empty else ["Geral"]
list_grupos = grupos_df['grupo'].tolist() if not grupos_df.empty else ["GERAL"]

# -----------------------------------------------------------------------------
# AUTENTICAÇÃO E PERFIS DE ACESSO
# -----------------------------------------------------------------------------
st.sidebar.title("🔑 Acesso ao Sistema")

if 'perfil_ativo' not in st.session_state:
    st.session_state.perfil_ativo = "👤 Portal do Cliente"

opcoes_perfil = ["👤 Portal do Cliente", "🔒 Administração / Vendedor"]
index_atual = opcoes_perfil.index(st.session_state.perfil_ativo)

perfil_selecionado = st.sidebar.radio("Selecione o Perfil:", opcoes_perfil, index=index_atual)

cliente_autenticado = None
menu = None

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
        
        tipo_acesso = "👤 Portal do Cliente"
        menu = "📋 Pedidos / Orçamentos"
    else:
        tipo_acesso = "🔒 Administração / Vendedor"
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
        
        if st.sidebar.button("🚪 Sair do Modo Admin"):
            st.session_state.admin_autenticado = False
            st.session_state.perfil_ativo = "👤 Portal do Cliente"
            st.rerun()

else:
    st.session_state.admin_autenticado = False
    st.session_state.perfil_ativo = "👤 Portal do Cliente"
    tipo_acesso = "👤 Portal do Cliente"
    
    st.sidebar.markdown("---")
    cliente_sel = st.sidebar.selectbox("Identifique seu Nome/Empresa:", list_clientes, key="cli_login")
    
    if st.session_state.get('cliente_logado') != cliente_sel:
        st.session_state.cliente_autenticado_status = False
    
    senha_esperada = SENHAS_CLIENTES.get(cliente_sel, SENHA_CLIENTE_PADRAO)
    
    if not st.session_state.get('cliente_autenticado_status', False):
        st.sidebar.subheader(f"🔒 Login — {cliente_sel}")
        pin_cliente = st.sidebar.text_input("Digite sua Senha de Cliente:", type="password", key=f"pwd_cli_{cliente_sel}")
        
        if st.sidebar.button("Acessar Meus Pedidos"):
            if pin_cliente == senha_esperada:
                st.session_state.cliente_autenticado_status = True
                st.session_state.cliente_logado = cliente_sel
                st.sidebar.success("Acesso confirmado!")
                st.rerun()
            else:
                st.sidebar.error("Senha incorreta!")
    else:
        cliente_autenticado = cliente_sel
        st.sidebar.success(f"Logado como: **{cliente_autenticado}**")
        if st.sidebar.button("🚪 Sair / Trocar Cliente"):
            st.session_state.cliente_autenticado_status = False
            st.session_state.cliente_logado = None
            st.rerun()

    menu = "📋 Pedidos / Orçamentos"

# -----------------------------------------------------------------------------
# GERADOR DE PDF
# -----------------------------------------------------------------------------
def gerar_pdf_relatorio(df_dados, titulo="Relatório de Vendas"):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=10, bottomMargin=20)
    elements = []

    styles = getSampleStyleSheet()

    header_company = ParagraphStyle('HeaderCompany', parent=styles['Normal'], fontName='Helvetica-BoldOblique', fontSize=15, leading=16, alignment=1, textColor=colors.black)
    header_info = ParagraphStyle('HeaderInfo', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8.5, leading=10, alignment=1, textColor=colors.black)
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=13, leading=15, alignment=1, textColor=colors.HexColor('#1E3A8A'))
    sub_title_style = ParagraphStyle('SubTitleStyle', parent=styles['Normal'], fontSize=8.5, leading=10, alignment=1, textColor=colors.HexColor('#475569'))

    elements.append(Paragraph("REY DA CEBOLA", header_company))
    elements.append(Paragraph("CNPJ: 194.174.39/000-42 INSC.EST.: 12.426725-4", header_info))
    elements.append(Paragraph("CONTATO: (99) 98814-9722 OU (99) 98414-3943", header_info))
    elements.append(Spacer(1, 6))

    elements.append(Paragraph(f"<b>{titulo}</b>", title_style))
    elements.append(Paragraph(f"Data de Emissão: {datetime.now().strftime('%d/%m/%Y %H:%M')}", sub_title_style))
    elements.append(Spacer(1, 8))

    has_cliente = 'cliente' in df_dados.columns

    if has_cliente:
        data = [["Cliente", "Produto", "Qtd Total", "Valor Unit. Médio (R$)", "Valor Total (R$)"]]
        col_widths = [130, 140, 70, 105, 105]
    else:
        data = [["Produto", "Qtd Total", "Valor Unit. Médio (R$)", "Valor Total (R$)"]]
        col_widths = [220, 90, 120, 120]
    
    total_geral = 0.0
    for idx, row in df_dados.iterrows():
        qtd = float(row['quantidade'])
        val_total = float(row['valor_total'])
        unit_m = val_total / qtd if qtd > 0 else 0.0
        total_geral += val_total

        if has_cliente:
            data.append([str(row['cliente']), str(row['produto']), f"{qtd:,.2f}", f"R$ {unit_m:,.2f}", f"R$ {val_total:,.2f}"])
        else:
            data.append([str(row['produto']), f"{qtd:,.2f}", f"R$ {unit_m:,.2f}", f"R$ {val_total:,.2f}"])

    if has_cliente:
        data.append(["VALOR TOTAL GERAL", "", "", "", f"R$ {total_geral:,.2f}"])
        span_end = 3
    else:
        data.append(["VALOR TOTAL GERAL", "", "", f"R$ {total_geral:,.2f}"])
        span_end = 2

    table = Table(data, colWidths=col_widths)
    t_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2563EB')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9.0),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#1E293B')),
        ('TEXTCOLOR', (0, -1), (-1, -1), colors.white),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('SPAN', (0, -1), (span_end, -1)),
    ])
    table.setStyle(t_style)
    elements.append(table)

    doc.build(elements)
    buffer.seek(0)
    return buffer

# -----------------------------------------------------------------------------
# IMPLEMENTAÇÃO DAS TELAS
# -----------------------------------------------------------------------------
if tipo_acesso == "👤 Portal do Cliente" and not cliente_autenticado:
    st.title("🔒 Portal do Cliente")
    st.warning("Por favor, selecione seu nome no menu à esquerda e insira sua senha para acessar seus pedidos.")

# --- FECHAMENTO & FINANCEIRO ---
elif menu == "📊 Fechamento & Financeiro":
    st.title("📊 Painel Financeiro & Fechamento")
    
    df_vendas = pd.read_sql_query("SELECT * FROM vendas", conn)
    
    if not df_vendas.empty:
        total_faturado = df_vendas['valor_total'].sum()
        total_recebido = df_vendas['valor_recebido'].sum()
        total_fiado = df_vendas['restante'].sum()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Faturamento Total", f"R$ {total_faturado:,.2f}")
        c2.metric("Total Recebido em Caixa", f"R$ {total_recebido:,.2f}")
        c3.metric("Total a Receber (Fiado/Pendente)", f"R$ {total_fiado:,.2f}")
        
        st.markdown("---")
        st.subheader("📋 Resumo do Histórico de Vendas")
        cols_exib = [c for c in ['id', 'codigo_venda', 'data', 'cliente', 'produto', 'fornecedor', 'grupo', 'quantidade', 'valor_venda', 'valor_total', 'forma_pagamento', 'restante'] if c in df_vendas.columns]
        st.dataframe(df_vendas[cols_exib], use_container_width=True)
    else:
        st.info("Nenhuma venda registrada até o momento.")

# --- PEDIDOS / ORÇAMENTOS ---
elif menu == "📋 Pedidos / Orçamentos":
    if tipo_acesso == "👤 Portal do Cliente":
        st.title(f"🛍️ Portal do Cliente — Meus Pedidos ({cliente_autenticado})")
    else:
        st.title("📋 Gerenciamento de Pedidos e Orçamentos")
    
    tab_novo, tab_lista = st.tabs(["➕ Criar Novo Pedido", "📑 Pedidos Registrados & Relatórios"])
    produtos_df = pd.read_sql_query("SELECT * FROM produtos", conn)

    with tab_novo:
        if produtos_df.empty:
            st.warning("Nenhum produto disponível no momento.")
        else:
            col_head1, col_head2 = st.columns(2)
            with col_head1:
                if tipo_acesso == "👤 Portal do Cliente":
                    st.text_input("Cliente do Pedido", value=cliente_autenticado, disabled=True)
                    ped_cliente = cliente_autenticado
                else:
                    ped_cliente = st.selectbox("Cliente do Pedido", list_clientes, key="ped_cli_multi")
            
            with col_head2:
                if tipo_acesso == "👤 Portal do Cliente":
                    st.text_input("Status Inicial", value="Pendente", disabled=True)
                    ped_status = "Pendente"
                else:
                    ped_status = st.selectbox("Status Inicial", ["Pendente", "Em Andamento", "Cancelado"], key="ped_stat_multi")

            st.markdown("---")
            st.write("#### 🛒 Adicionar Produtos ao Pedido")
            
            if tipo_acesso == "👤 Portal do Cliente":
                c_prod1, c_prod2, c_prod3 = st.columns([4, 2, 2])
                with c_prod1:
                    item_produto = st.selectbox("Selecione o Produto", produtos_df['produto'].tolist(), key="item_prod")
                    prod_info = produtos_df[produtos_df['produto'] == item_produto].iloc[0]
                    grupo_padrao = prod_info.get('grupo', 'GERAL')
                    item_fornecedor = "Geral"
                    item_grupo = grupo_padrao
                
                with c_prod2:
                    item_preco = float(prod_info['valor_venda'])
                    st.number_input("Preço Unit. Venda (R$)", value=item_preco, disabled=True, key="item_prec")

                with c_prod3:
                    item_qtd = st.number_input("Quantidade", min_value=0.01, value=1.0, step=0.1, key="item_qtd")
            else:
                c_prod1, c_prod2, c_prod3, c_prod4 = st.columns([3, 2, 2, 2])
                with c_prod1:
                    item_produto = st.selectbox("Selecione o Produto", produtos_df['produto'].tolist(), key="item_prod")
                    prod_info = produtos_df[produtos_df['produto'] == item_produto].iloc[0]
                    grupo_padrao = prod_info.get('grupo', 'GERAL')
                
                with c_prod2:
                    item_fornecedor = st.selectbox("Fornecedor", list_fornecedores, key="item_forn")
                
                with c_prod3:
                    item_grupo = st.selectbox("Grupo", list_grupos, index=list_grupos.index(grupo_padrao) if grupo_padrao in list_grupos else 0, key="item_grup")

                with c_prod4:
                    item_preco = st.number_input("Preço Unit. Venda (R$)", value=float(prod_info['valor_venda']), min_value=0.0, key="item_prec")

                c_qtd1, c_qtd2 = st.columns([2, 2])
                with c_qtd1:
                    item_qtd = st.number_input("Quantidade", min_value=0.01, value=1.0, step=0.1, key="item_qtd")

            st.write("")
            if st.button("➕ Adicionar Produto à Lista"):
                total_item = item_qtd * item_preco
                st.session_state.carrinho_pedido.append({
                    'produto': item_produto,
                    'fornecedor': item_fornecedor,
                    'grupo': item_grupo,
                    'quantidade': item_qtd,
                    'valor_unitario': item_preco,
                    'valor_total': total_item
                })
                st.success(f"'{item_produto}' adicionado!")

            st.markdown("---")
            st.write("### 📜 Lista de Itens no Pedido Atual")
            
            if len(st.session_state.carrinho_pedido) == 0:
                st.info("Sua lista está vazia. Adicione produtos acima.")
            else:
                df_cart = pd.DataFrame(st.session_state.carrinho_pedido)
                st.dataframe(df_cart[['produto', 'quantidade', 'valor_unitario', 'valor_total']], use_container_width=True)
                
                total_geral_pedido = df_cart['valor_total'].sum()
                st.markdown(f"### 💰 **Valor Total do Pedido: R$ {total_geral_pedido:,.2f}**")
                
                ped_obs = st.text_area("Observações Gerais do Pedido")

                col_b1, col_b2 = st.columns(2)
                with col_b1:
                    if st.button("✅ Finalizar e Enviar Pedido"):
                        data_hoje = datetime.now().strftime('%Y-%m-%d %H:%M')
                        codigo_ped = f"PED-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                        
                        for item in st.session_state.carrinho_pedido:
                            cursor.execute('''
                                INSERT INTO pedidos (codigo_pedido, cliente, produto, fornecedor, grupo, quantidade, valor_unitario, valor_total, status, observacoes, data)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (codigo_ped, ped_cliente, item['produto'], item['fornecedor'], item['grupo'], item['quantidade'], item['valor_unitario'], item['valor_total'], ped_status, ped_obs, data_hoje))
                        
                        conn.commit()
                        st.session_state.carrinho_pedido = []
                        st.success(f"Pedido enviado com sucesso! (Código: {codigo_ped})")
                        st.rerun()

                with col_b2:
                    if st.button("🗑️ Limpar Lista"):
                        st.session_state.carrinho_pedido = []
                        st.rerun()

    with tab_lista:
        query_ped = "SELECT * FROM pedidos WHERE 1=1"
        params = []

        if tipo_acesso == "👤 Portal do Cliente":
            query_ped += " AND cliente = ?"
            params.append(cliente_autenticado)
        else:
            st.subheader("🔍 Filtros de Relatório de Pedidos")
            col_f1, col_f2, col_f3 = st.columns(3)
            with col_f1:
                filtro_cliente = st.selectbox("Filtrar por Cliente", ["Todas as vendas"] + list_clientes, key="f_cli_p")
                filtro_fornecedor = st.selectbox("Filtrar por Fornecedor", ["Todos os fornecedores"] + list_fornecedores, key="f_forn_p")
            with col_f2:
                filtro_grupo = st.selectbox("Filtrar por Grupo", ["Todos os grupos"] + list_grupos, key="f_grp_p")
                filtro_status = st.selectbox("Filtrar por Status", ["Todos", "Pendente", "Em Andamento", "Concluído (Convertido)", "Cancelado"], key="f_stat_p")
            with col_f3:
                data_ini = st.date_input("Data Inicial", value=date(2024, 1, 1), key="d_ini_p")
                data_fim = st.date_input("Data Final", value=date.today(), key="d_fim_p")

            if filtro_cliente != "Todas as vendas":
                query_ped += " AND cliente = ?"
                params.append(filtro_cliente)
                
            if filtro_fornecedor != "Todos os fornecedores":
                query_ped += " AND fornecedor = ?"
                params.append(filtro_fornecedor)
                
            if filtro_grupo != "Todos os grupos":
                query_ped += " AND grupo = ?"
                params.append(filtro_grupo)

            if filtro_status != "Todos":
                query_ped += " AND status = ?"
                params.append(filtro_status)
            
        query_ped += " ORDER BY id DESC"
        
        pedidos_df = pd.read_sql_query(query_ped, conn, params=params)
        
        if tipo_acesso != "👤 Portal do Cliente" and not pedidos_df.empty and 'data' in pedidos_df.columns:
            pedidos_df['data_dt'] = pd.to_datetime(pedidos_df['data'], errors='coerce').dt.date
            pedidos_df = pedidos_df[(pedidos_df['data_dt'] >= data_ini) & (pedidos_df['data_dt'] <= data_fim)]
            pedidos_df = pedidos_df.drop(columns=['data_dt'])

        st.markdown("---")
        
        if pedidos_df.empty:
            st.warning("Nenhum pedido encontrado.")
        else:
            total_filtrado = pedidos_df['valor_total'].sum()
            st.write(f"**Itens Registrados:** {len(pedidos_df)} | **Soma dos Valores:** R$ {total_filtrado:,.2f}")
            
            if 'valor_unitario' not in pedidos_df.columns or pedidos_df['valor_unitario'].isnull().all():
                pedidos_df['valor_unitario'] = pedidos_df['valor_total'] / pedidos_df['quantidade']

            cols_exibicao = ['id', 'codigo_pedido', 'data', 'cliente', 'produto', 'quantidade', 'valor_unitario', 'valor_total', 'status']
            
            if tipo_acesso == "👤 Portal do Cliente":
                st.dataframe(pedidos_df[cols_exibicao], use_container_width=True)
            else:
                st.info("💡 **Dica:** Clique duas vezes em qualquer valor da coluna **`quantidade`** OU **`valor_unitario`** para editar diretamente.", icon="✏️")
                df_editavel = st.data_editor(
                    pedidos_df[cols_exibicao],
                    key="editor_pedidos_direto",
                    use_container_width=True,
                    disabled=['id', 'codigo_pedido', 'data', 'cliente', 'produto', 'valor_total', 'status'],
                    column_config={
                        "quantidade": st.column_config.NumberColumn("Quantidade", min_value=0.01, step=0.1, format="%.2f"),
                        "valor_unitario": st.column_config.NumberColumn("Valor Unitário (R$)", min_value=0.0, step=0.5, format="R$ %.2f"),
                        "valor_total": st.column_config.NumberColumn("Valor Total (R$)", format="R$ %.2f")
                    }
                )

                if st.button("💾 Salvar Alterações da Tabela", type="primary", key="btn_save_pedidos"):
                    for idx, row in df_editavel.iterrows():
                        id_row = int(row['id'])
                        q_nova = float(row['quantidade'])
                        v_unit_novo = float(row['valor_unitario'])
                        v_tot_novo = q_nova * v_unit_novo
                        
                        cursor.execute('''
                            UPDATE pedidos 
                            SET quantidade = ?, valor_unitario = ?, valor_total = ? 
                            WHERE id = ?
                        ''', (q_nova, v_unit_novo, v_tot_novo, id_row))
                    
                    conn.commit()
                    st.success("✅ Alterações salvas com sucesso!")
                    st.rerun()

            st.markdown("---")
            st.subheader("📊 Agrupamento do Período / Seleção")
            
            df_agrupado = pedidos_df.groupby('produto', as_index=False).agg({
                'quantidade': 'sum',
                'valor_total': 'sum'
            })
            
            df_agrupado['valor_unitario_medio'] = df_agrupado['valor_total'] / df_agrupado['quantidade']
            
            st.dataframe(
                df_agrupado[['produto', 'quantidade', 'valor_unitario_medio', 'valor_total']],
                column_config={
                    "produto": "Produto",
                    "quantidade": st.column_config.NumberColumn("Quantidade Total", format="%.2f"),
                    "valor_unitario_medio": st.column_config.NumberColumn("Valor Unitário Médio (R$)", format="R$ %.2f"),
                    "valor_total": st.column_config.NumberColumn("Valor Total (R$)", format="R$ %.2f"),
                },
                hide_index=True,
                use_container_width=True
            )

            pdf_bytes = gerar_pdf_relatorio(df_agrupado, titulo=f"Relatório de Pedidos - {cliente_autenticado if tipo_acesso == '👤 Portal do Cliente' else 'Geral'}")
            
            st.download_button(
                label="📄 Baixar Relatório Consolidado em PDF",
                data=pdf_bytes,
                file_name=f"Relatorio_Pedidos_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                mime="application/pdf",
                use_container_width=True
            )

# --- REGISTRAR VENDA (PDV) ---
elif menu == "🛒 Registrar Venda":
    st.title("🛒 Gerenciamento & Lançamento de Vendas (PDV)")
    
    produtos_df = pd.read_sql_query("SELECT * FROM produtos", conn)
    
    if produtos_df.empty:
        st.warning("⚠️ Nenhum produto cadastrado no estoque. Cadastre produtos na aba 'Estoque de Produtos' primeiro.")
    else:
        tab_venda, tab_hist = st.tabs(["🛒 Nova Venda (Balcão / PDV)", "📜 Histórico de Vendas Realizadas"])
        
        with tab_venda:
            col_v1, col_v2 = st.columns(2)
            with col_v1:
                venda_cliente = st.selectbox("Cliente", list_clientes, key="venda_cli_select")
            with col_v2:
                venda_forma_pagto = st.selectbox("Forma de Pagamento", ["Dinheiro", "PIX", "Cartão de Débito", "Cartão de Crédito", "A Prazo / Fiado"])

            st.markdown("---")
            st.subheader("➕ Adicionar Produtos à Venda")
            
            c_p1, c_p2, c_p3, c_p4 = st.columns([3, 2, 2, 2])
            with c_p1:
                prod_venda_sel = st.selectbox("Produto", produtos_df['produto'].tolist(), key="prod_venda_sel")
                p_info = produtos_df[produtos_df['produto'] == prod_venda_sel].iloc[0]
                est_atual = float(p_info['quantidade'])
                v_unit_padrao = float(p_info['valor_venda'])
                st.caption(f"Estoque disponível: **{est_atual:,.2f}**")
            
            with c_p2:
                qtd_venda = st.number_input("Quantidade", min_value=0.01, value=1.0, step=1.0, key="qtd_venda_input")
            with c_p3:
                val_unit_venda = st.number_input("Preço Unit. (R$)", min_value=0.0, value=v_unit_padrao, step=0.50, key="val_unit_venda_input")
            with c_p4:
                val_total_item = qtd_venda * val_unit_venda
                st.number_input("Subtotal (R$)", value=val_total_item, disabled=True, key="subtotal_item_disp")

            if st.button("➕ Adicionar à Venda"):
                st.session_state.carrinho_venda.append({
                    'produto': prod_venda_sel,
                    'fornecedor': p_info.get('fornecedor', 'Geral'),
                    'grupo': p_info.get('grupo', 'Geral'),
                    'quantidade': qtd_venda,
                    'valor_venda': val_unit_venda,
                    'valor_total': val_total_item
                })
                st.success(f"Item '{prod_venda_sel}' adicionado!")

            st.markdown("---")
            st.subheader("🛍️ Itens da Venda Atual")
            
            if not st.session_state.carrinho_venda:
                st.info("Nenhum item adicionado à venda ainda.")
            else:
                df_v_cart = pd.DataFrame(st.session_state.carrinho_venda)
                st.dataframe(df_v_cart[['produto', 'quantidade', 'valor_venda', 'valor_total']], use_container_width=True)
                
                total_venda_bruto = df_v_cart['valor_total'].sum()
                
                st.markdown(f"### 💰 **Total da Venda: R$ {total_venda_bruto:,.2f}**")
                
                col_pag1, col_pag2, col_pag3 = st.columns(3)
                with col_pag1:
                    valor_pago = st.number_input("Valor Recebido / Pago (R$)", min_value=0.0, value=total_venda_bruto if venda_forma_pagto != "A Prazo / Fiado" else 0.0)
                with col_pag2:
                    troco = max(0.0, valor_pago - total_venda_bruto)
                    st.metric("Troco (R$)", f"R$ {troco:,.2f}")
                with col_pag3:
                    restante = max(0.0, total_venda_bruto - valor_pago)
                    st.metric("Pendente / A Receber (R$)", f"R$ {restante:,.2f}")

                col_actions1, col_actions2 = st.columns(2)
                with col_actions1:
                    if st.button("✅ Concluir Venda e Dar Baixa no Estoque", type="primary"):
                        cod_venda = f"VEN-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                        data_venda = datetime.now().strftime('%Y-%m-%d %H:%M')
                        
                        for item in st.session_state.carrinho_venda:
                            # Registra no banco
                            cursor.execute('''
                                INSERT INTO vendas (codigo_venda, cliente, produto, fornecedor, grupo, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, troco, restante, data)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (cod_venda, venda_cliente, item['produto'], item['fornecedor'], item['grupo'], item['quantidade'], item['valor_venda'], item['valor_total'], venda_forma_pagto, valor_pago, troco, restante, data_venda))
                            
                            # Atualiza/Baixa estoque
                            cursor.execute('''
                                UPDATE produtos 
                                SET quantidade = quantidade - ? 
                                WHERE produto = ?
                            ''', (item['quantidade'], item['produto']))
                        
                        conn.commit()
                        st.session_state.carrinho_venda = []
                        st.success(f"🎉 Venda {cod_venda} registrada com sucesso!")
                        st.rerun()

                with col_actions2:
                    if st.button("🗑️ Cancelar / Limpar Venda"):
                        st.session_state.carrinho_venda = []
                        st.rerun()

        with tab_hist:
            df_vendas_all = pd.read_sql_query("SELECT * FROM vendas ORDER BY id DESC", conn)
            if df_vendas_all.empty:
                st.info("Nenhuma venda registrada até o momento.")
            else:
                st.dataframe(df_vendas_all, use_container_width=True)

# --- ENTRADA DE ESTOQUE (COMPRAS) ---
elif menu == "📥 Entrada de Estoque (Compras)":
    st.title("📥 Registro de Compras & Entrada de Estoque")
    
    tab_nova_compra, tab_hist_compras = st.tabs(["➕ Registrar Nova Compra (Entrada)", "📜 Histórico de Compras"])
    
    produtos_df = pd.read_sql_query("SELECT * FROM produtos", conn)
    
    with tab_nova_compra:
        st.subheader("➕ Nova Entrada de Mercadoria")
        
        with st.form("form_compra", clear_on_submit=True):
            col_cmp1, col_cmp2 = st.columns(2)
            with col_cmp1:
                if not produtos_df.empty:
                    prod_compra = st.selectbox("Selecione o Produto", produtos_df['produto'].tolist())
                else:
                    prod_compra = st.text_input("Nome do Produto")
                    
                forn_compra = st.selectbox("Fornecedor", list_fornecedores)
                grp_compra = st.selectbox("Grupo / Categoria", list_grupos)
                
            with col_cmp2:
                qtd_compra = st.number_input("Quantidade Comprada", min_value=0.01, value=10.0, step=1.0)
                val_compra_unit = st.number_input("Valor de Custo Unitário (R$)", min_value=0.0, value=10.0, step=0.50)
                val_venda_sug = st.number_input("Preço Sugerido de Venda Unit. (R$)", min_value=0.0, value=15.0, step=0.50)

            btn_reg_compra = st.form_submit_button("📥 Confirmar Entrada no Estoque")
            
            if btn_reg_compra:
                val_total_compra = qtd_compra * val_compra_unit
                data_compra = datetime.now().strftime('%Y-%m-%d %H:%M')
                
                # Inserir histórico de compras
                cursor.execute('''
                    INSERT INTO compras (produto, fornecedor, grupo, quantidade, valor_compra, valor_venda, valor_total, data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (prod_compra, forn_compra, grp_compra, qtd_compra, val_compra_unit, val_venda_sug, val_total_compra, data_compra))
                
                # Se o produto já existe no estoque, incrementa. Se não, insere.
                cursor.execute("SELECT id FROM produtos WHERE produto = ?", (prod_compra,))
                res_prod = cursor.fetchone()
                
                if res_prod:
                    cursor.execute('''
                        UPDATE produtos 
                        SET quantidade = quantidade + ?, valor_compra = ?, valor_venda = ?, grupo = ?
                        WHERE id = ?
                    ''', (qtd_compra, val_compra_unit, val_venda_sug, grp_compra, res_prod[0]))
                else:
                    cursor.execute('''
                        INSERT INTO produtos (produto, grupo, quantidade, valor_compra, valor_venda)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (prod_compra, grp_compra, qtd_compra, val_compra_unit, val_venda_sug))
                
                conn.commit()
                st.success(f"Entrada de {qtd_compra} unidades de '{prod_compra}' registrada com sucesso!")
                st.rerun()

    with tab_hist_compras:
        df_compras_all = pd.read_sql_query("SELECT * FROM compras ORDER BY id DESC", conn)
        if df_compras_all.empty:
            st.info("Nenhuma compra registrada ainda.")
        else:
            st.dataframe(df_compras_all, use_container_width=True)

# --- ESTOQUE DE PRODUTOS ---
elif menu == "📦 Estoque de Produtos":
    st.title("📦 Consulta & Atualização de Estoque")
    
    tab_cons, tab_cad_p = st.tabs(["📋 Consulta & Edição do Estoque", "➕ Novo Produto"])
    
    with tab_cons:
        st.subheader("📊 Produtos no Estoque")
        df_est = pd.read_sql_query("SELECT * FROM produtos ORDER BY produto ASC", conn)
        
        if df_est.empty:
            st.info("Nenhum produto cadastrado.")
        else:
            st.info("💡 **Edição Direta:** Você pode alterar os valores de **Preço de Compra, Venda, Quantidade ou Grupo** diretamente na tabela abaixo e clicar em salvar.", icon="✏️")
            
            df_est_edit = st.data_editor(
                df_est,
                key="editor_estoque_geral",
                use_container_width=True,
                disabled=['id'],
                column_config={
                    "produto": st.column_config.TextColumn("Nome do Produto", required=True),
                    "grupo": st.column_config.SelectboxColumn("Grupo", options=list_grupos),
                    "quantidade": st.column_config.NumberColumn("Qtd em Estoque", step=1.0, format="%.2f"),
                    "valor_compra": st.column_config.NumberColumn("Valor Compra (R$)", step=0.5, format="R$ %.2f"),
                    "valor_venda": st.column_config.NumberColumn("Valor Venda (R$)", step=0.5, format="R$ %.2f"),
                }
            )
            
            if st.button("💾 Salvar Alterações do Estoque", type="primary"):
                for idx, row in df_est_edit.iterrows():
                    cursor.execute('''
                        UPDATE produtos 
                        SET produto = ?, grupo = ?, quantidade = ?, valor_compra = ?, valor_venda = ?
                        WHERE id = ?
                    ''', (row['produto'], row['grupo'], row['quantidade'], row['valor_compra'], row['valor_venda'], int(row['id'])))
                conn.commit()
                st.success("Estoque atualizado com sucesso!")
                st.rerun()

            st.markdown("---")
            with st.expander("🗑️ Excluir um Produto do Estoque"):
                p_del = st.selectbox("Selecione o produto para apagar:", df_est['produto'].tolist())
                if st.button("Confirmar Exclusão de Produto", type="primary"):
                    cursor.execute("DELETE FROM produtos WHERE produto = ?", (p_del,))
                    conn.commit()
                    st.success(f"Produto '{p_del}' removido!")
                    st.rerun()

    with tab_cad_p:
        st.subheader("➕ Cadastrar Novo Produto")
        with st.form("form_novo_prod_direto", clear_on_submit=True):
            col_p1, col_p2 = st.columns(2)
            with col_p1:
                np_nome = st.text_input("Nome do Produto *")
                np_grupo = st.selectbox("Grupo / Categoria", list_grupos)
                np_qtd = st.number_input("Estoque Inicial", min_value=0.0, value=0.0, step=1.0)
            with col_p2:
                np_vc = st.number_input("Preço de Custo (R$)", min_value=0.0, value=0.0, step=0.5)
                np_vv = st.number_input("Preço de Venda (R$)", min_value=0.0, value=0.0, step=0.5)

            btn_cad_p = st.form_submit_button("💾 Salvar Produto")
            if btn_cad_p:
                if not np_nome.strip():
                    st.error("O nome do produto é obrigatório!")
                else:
                    try:
                        cursor.execute('''
                            INSERT INTO produtos (produto, grupo, quantidade, valor_compra, valor_venda)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (np_nome.strip(), np_grupo, np_qtd, np_vc, np_vv))
                        conn.commit()
                        st.success(f"Produto '{np_nome}' cadastrado!")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Já existe um produto com este nome.")

# --- CADASTROS GERAIS ---
elif menu == "👥 Cadastros (Clientes / Fornecedores / Grupos)":
    st.title("👥 Cadastros Gerais do Sistema")
    
    tab_cli, tab_forn, tab_grp = st.tabs(["👤 Cadastrar Clientes", "🚚 Cadastrar Fornecedores", "🏷️ Cadastrar Grupos"])

    # --- TAB CLIENTES ---
    with tab_cli:
        st.subheader("➕ Novo Cliente")
        with st.form("form_cad_cliente", clear_on_submit=True):
            col_c1, col_c2 = st.columns(2)
            with col_c1:
                novo_nome_cli = st.text_input("Nome do Cliente / Empresa *")
                novo_cpf_cli = st.text_input("CPF / CNPJ")
                novo_email_cli = st.text_input("E-mail")
            with col_c2:
                novo_fone_cli = st.text_input("Telefone / WhatsApp")
                novo_end_cli = st.text_input("Endereço Completo")
            
            btn_salvar_cli = st.form_submit_button("💾 Cadastrar Cliente")
            
            if btn_salvar_cli:
                if not novo_nome_cli.strip():
                    st.error("O nome do cliente é obrigatório!")
                else:
                    try:
                        cursor.execute(
                            "INSERT INTO clientes (cliente, cpf, endereco, email, fone) VALUES (?, ?, ?, ?, ?)",
                            (novo_nome_cli.strip(), novo_cpf_cli.strip(), novo_end_cli.strip(), novo_email_cli.strip(), novo_fone_cli.strip())
                        )
                        conn.commit()
                        st.success(f"Cliente '{novo_nome_cli}' cadastrado com sucesso!")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error(f"Já existe um cliente cadastrado com o nome '{novo_nome_cli}'.")

        st.markdown("---")
        st.subheader("📋 Clientes Cadastrados")
        df_cli_full = pd.read_sql_query("SELECT * FROM clientes ORDER BY cliente ASC", conn)
        st.dataframe(df_cli_full, use_container_width=True)

        if not df_cli_full.empty:
            with st.expander("🗑️ Excluir um Cliente"):
                cli_excluir = st.selectbox("Selecione o Cliente para excluir:", df_cli_full['cliente'].tolist())
                if st.button("Confirmar Exclusão de Cliente", type="primary"):
                    cursor.execute("DELETE FROM clientes WHERE cliente = ?", (cli_excluir,))
                    conn.commit()
                    st.success(f"Cliente '{cli_excluir}' foi removido!")
                    st.rerun()

    # --- TAB FORNECEDORES ---
    with tab_forn:
        st.subheader("➕ Novo Fornecedor")
        with st.form("form_cad_forn", clear_on_submit=True):
            novo_forn = st.text_input("Nome do Fornecedor *")
            btn_salvar_forn = st.form_submit_button("💾 Cadastrar Fornecedor")
            
            if btn_salvar_forn:
                if not novo_forn.strip():
                    st.error("O nome do fornecedor é obrigatório!")
                else:
                    try:
                        cursor.execute("INSERT INTO fornecedores (fornecedor) VALUES (?)", (novo_forn.strip(),))
                        conn.commit()
                        st.success(f"Fornecedor '{novo_forn}' cadastrado!")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Este fornecedor já existe.")

        st.markdown("---")
        st.subheader("📋 Fornecedores Cadastrados")
        df_forn_full = pd.read_sql_query("SELECT * FROM fornecedores ORDER BY fornecedor ASC", conn)
        st.dataframe(df_forn_full, use_container_width=True)

        if not df_forn_full.empty:
            with st.expander("🗑️ Excluir um Fornecedor"):
                forn_excluir = st.selectbox("Selecione o Fornecedor para excluir:", df_forn_full['fornecedor'].tolist())
                if st.button("Confirmar Exclusão de Fornecedor", type="primary"):
                    cursor.execute("DELETE FROM fornecedores WHERE fornecedor = ?", (forn_excluir,))
                    conn.commit()
                    st.success(f"Fornecedor '{forn_excluir}' removido!")
                    st.rerun()

    # --- TAB GRUPOS ---
    with tab_grp:
        st.subheader("➕ Novo Grupo / Categoria de Produto")
        with st.form("form_cad_grupo", clear_on_submit=True):
            novo_grp = st.text_input("Nome do Grupo (Ex: Frutas, Verduras, Bebidas) *")
            btn_salvar_grp = st.form_submit_button("💾 Cadastrar Grupo")
            
            if btn_salvar_grp:
                if not novo_grp.strip():
                    st.error("O nome do grupo é obrigatório!")
                else:
                    try:
                        cursor.execute("INSERT INTO grupos (grupo) VALUES (?)", (novo_grp.strip(),))
                        conn.commit()
                        st.success(f"Grupo '{novo_grp}' cadastrado!")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Este grupo já existe.")

        st.markdown("---")
        st.subheader("📋 Grupos Cadastrados")
        df_grp_full = pd.read_sql_query("SELECT * FROM grupos ORDER BY grupo ASC", conn)
        st.dataframe(df_grp_full, use_container_width=True)

        if not df_grp_full.empty:
            with st.expander("🗑️ Excluir um Grupo"):
                grp_excluir = st.selectbox("Selecione o Grupo para excluir:", df_grp_full['grupo'].tolist())
                if st.button("Confirmar Exclusão de Grupo", type="primary"):
                    cursor.execute("DELETE FROM grupos WHERE grupo = ?", (grp_excluir,))
                    conn.commit()
                    st.success(f"Grupo '{grp_excluir}' removido!")
                    st.rerun()
