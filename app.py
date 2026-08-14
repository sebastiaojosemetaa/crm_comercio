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
# CONEXÃO E CRIAÇÃO DO BANCO DE DADOS
# -----------------------------------------------------------------------------
conn = sqlite3.connect('crm_comercio.db', check_same_thread=False)
cursor = conn.cursor()

# Tabelas do sistema
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

# Compatibilidade e Migração de Colunas Existentes
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

# CARGA INICIAL
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

# Inicializar Carrinho
if 'carrinho_pedido' not in st.session_state:
    st.session_state.carrinho_pedido = []

# -----------------------------------------------------------------------------
# FUNÇÃO GERADORA DE PDF INTELIGENTE
# -----------------------------------------------------------------------------
def gerar_pdf_relatorio(df_dados, titulo="Relatório de Vendas"):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=10, bottomMargin=20)
    elements = []

    styles = getSampleStyleSheet()

    header_company = ParagraphStyle(
        'HeaderCompany', parent=styles['Normal'], 
        fontName='Helvetica-BoldOblique', fontSize=15, leading=16, 
        alignment=1, textColor=colors.black, spaceAfter=1, spaceBefore=0
    )
    header_info = ParagraphStyle(
        'HeaderInfo', parent=styles['Normal'], 
        fontName='Helvetica-Bold', fontSize=8.5, leading=10, 
        alignment=1, textColor=colors.black, spaceAfter=0, spaceBefore=0
    )
    
    title_style = ParagraphStyle(
        'TitleStyle', parent=styles['Heading1'], 
        fontSize=13, leading=15, alignment=1, 
        textColor=colors.HexColor('#1E3A8A'), spaceAfter=1, spaceBefore=0
    )
    sub_title_style = ParagraphStyle(
        'SubTitleStyle', parent=styles['Normal'], 
        fontSize=8.5, leading=10, alignment=1, 
        textColor=colors.HexColor('#475569'), spaceAfter=0, spaceBefore=0
    )

    # Cabeçalho REY DA CEBOLA Super Compacto
    elements.append(Paragraph("REY DA CEBOLA", header_company))
    elements.append(Paragraph("CNPJ: 194.174.39/000-42 INSC.EST.: 12.426725-4", header_info))
    elements.append(Paragraph("CONTATO: (99) 98814-9722 OU (99) 98414-3943", header_info))
    
    elements.append(Spacer(1, 6))

    # Título do Relatório
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
            data.append([
                str(row['cliente']),
                str(row['produto']),
                f"{qtd:,.2f}",
                f"R$ {unit_m:,.2f}",
                f"R$ {val_total:,.2f}"
            ])
        else:
            data.append([
                str(row['produto']),
                f"{qtd:,.2f}",
                f"R$ {unit_m:,.2f}",
                f"R$ {val_total:,.2f}"
            ])

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
        ('ALIGN', (0, 1), (1 if has_cliente else 0, -2), 'LEFT'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#1E293B')),
        ('TEXTCOLOR', (0, -1), (-1, -1), colors.white),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, -1), (-1, -1), 10),
        ('SPAN', (0, -1), (span_end, -1)),
    ])
    table.setStyle(t_style)
    elements.append(table)

    doc.build(elements)
    buffer.seek(0)
    return buffer

# -----------------------------------------------------------------------------
# MENU LATERAL
# -----------------------------------------------------------------------------
st.sidebar.title("CRM Comércio 📦")
menu = st.sidebar.radio("Navegação", [
    "📊 Fechamento & Financeiro",
    "📋 Pedidos / Orçamentos",
    "🛒 Registrar Venda",
    "📥 Entrada de Estoque (Compras)",
    "📦 Estoque de Produtos",
    "👥 Cadastros (Clientes / Fornecedores / Grupos)"
])

# -----------------------------------------------------------------------------
# LISTAS GERAIS PARA FILTROS
# -----------------------------------------------------------------------------
clientes_df = pd.read_sql_query("SELECT cliente FROM clientes", conn)
fornecedores_df = pd.read_sql_query("SELECT fornecedor FROM fornecedores", conn)
grupos_df = pd.read_sql_query("SELECT grupo FROM grupos", conn)

list_clientes = clientes_df['cliente'].tolist() if not clientes_df.empty else ["Cliente Geral"]
list_fornecedores = fornecedores_df['fornecedor'].tolist() if not fornecedores_df.empty else ["Geral"]
list_grupos = grupos_df['grupo'].tolist() if not grupos_df.empty else ["GERAL"]

# -----------------------------------------------------------------------------
# 1. FECHAMENTO & FINANCEIRO
# -----------------------------------------------------------------------------
if menu == "📊 Fechamento & Financeiro":
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

# -----------------------------------------------------------------------------
# 2. PEDIDOS / ORÇAMENTOS
# -----------------------------------------------------------------------------
elif menu == "📋 Pedidos / Orçamentos":
    st.title("📋 Gerenciamento de Pedidos e Orçamentos")
    
    tab_novo, tab_lista = st.tabs(["➕ Criar Novo Pedido", "📑 Pedidos Registrados & Relatórios"])
    produtos_df = pd.read_sql_query("SELECT * FROM produtos", conn)

    with tab_novo:
        if produtos_df.empty:
            st.warning("Cadastre produtos no estoque antes de realizar pedidos.")
        else:
            col_head1, col_head2 = st.columns(2)
            with col_head1:
                ped_cliente = st.selectbox("Cliente do Pedido", list_clientes, key="ped_cli_multi")
            with col_head2:
                ped_status = st.selectbox("Status Inicial", ["Pendente", "Em Andamento", "Cancelado"], key="ped_stat_multi")

            st.markdown("---")
            st.write("#### 🛒 Adicionar Produtos ao Pedido")
            
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
            with c_qtd2:
                st.write("")
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
                st.dataframe(df_cart[['produto', 'fornecedor', 'grupo', 'quantidade', 'valor_unitario', 'valor_total']], use_container_width=True)
                
                total_geral_pedido = df_cart['valor_total'].sum()
                st.markdown(f"### 💰 **Valor Total do Pedido: R$ {total_geral_pedido:,.2f}**")
                
                ped_obs = st.text_area("Observações Gerais do Pedido")

                col_b1, col_b2 = st.columns(2)
                with col_b1:
                    if st.button("✅ Finalizar e Salvar Pedido"):
                        data_hoje = datetime.now().strftime('%Y-%m-%d %H:%M')
                        codigo_ped = f"PED-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                        
                        for item in st.session_state.carrinho_pedido:
                            cursor.execute('''
                                INSERT INTO pedidos (codigo_pedido, cliente, produto, fornecedor, grupo, quantidade, valor_unitario, valor_total, status, observacoes, data)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (codigo_ped, ped_cliente, item['produto'], item['fornecedor'], item['grupo'], item['quantidade'], item['valor_unitario'], item['valor_total'], ped_status, ped_obs, data_hoje))
                        
                        conn.commit()
                        st.session_state.carrinho_pedido = []
                        st.success(f"Pedido registrado com sucesso! (Código: {codigo_ped})")
                        st.rerun()

                with col_b2:
                    if st.button("🗑️ Limpar Lista"):
                        st.session_state.carrinho_pedido = []
                        st.rerun()

    with tab_lista:
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

        query_ped = "SELECT * FROM pedidos WHERE 1=1"
        params = []
        
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
        
        if not pedidos_df.empty and 'data' in pedidos_df.columns:
            pedidos_df['data_dt'] = pd.to_datetime(pedidos_df['data'], errors='coerce').dt.date
            pedidos_df = pedidos_df[(pedidos_df['data_dt'] >= data_ini) & (pedidos_df['data_dt'] <= data_fim)]
            pedidos_df = pedidos_df.drop(columns=['data_dt'])

        st.markdown("---")
        
        if pedidos_df.empty:
            st.warning("Nenhum pedido encontrado para os filtros selecionados.")
        else:
            total_filtrado = pedidos_df['valor_total'].sum()
            st.write(f"**Itens Registrados:** {len(pedidos_df)} | **Soma dos Valores:** R$ {total_filtrado:,.2f}")
            
            st.info("💡 **Dica:** Clique duas vezes em qualquer valor da coluna **`quantidade`** OU **`valor_unitario`** na tabela abaixo para editar diretamente.", icon="✏️")

            if 'valor_unitario' not in pedidos_df.columns or pedidos_df['valor_unitario'].isnull().all():
                pedidos_df['valor_unitario'] = pedidos_df['valor_total'] / pedidos_df['quantidade']

            cols_exibicao = ['id', 'codigo_pedido', 'data', 'cliente', 'produto', 'fornecedor', 'grupo', 'quantidade', 'valor_unitario', 'valor_total', 'status']
            
            df_editavel = st.data_editor(
                pedidos_df[cols_exibicao],
                key="editor_pedidos_direto",
                use_container_width=True,
                disabled=['id', 'codigo_pedido', 'data', 'cliente', 'produto', 'fornecedor', 'grupo', 'valor_total', 'status'],
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

            # RESUMO AGRUPADO POR PRODUTO E GERADOR DE PDF
            st.markdown("---")
            st.subheader("📊 Agrupamento do Período / Seleção (Sem Repetição)")
            
            df_agrupado = pedidos_df.groupby('produto', as_index=False).agg({
                'quantidade': 'sum',
                'valor_total': 'sum'
            })
            
            df_agrupado['valor_unitario_medio'] = df_agrupado['valor_total'] / df_agrupado['quantidade']
            df_agrupado_exibicao = df_agrupado[['produto', 'quantidade', 'valor_unitario_medio', 'valor_total']].copy()
            
            st.dataframe(
                df_agrupado_exibicao,
                column_config={
                    "produto": "Produto",
                    "quantidade": st.column_config.NumberColumn("Quantidade Total", format="%.2f"),
                    "valor_unitario_medio": st.column_config.NumberColumn("Valor Unitário Médio (R$)", format="R$ %.2f"),
                    "valor_total": st.column_config.NumberColumn("Valor Total (R$)", format="R$ %.2f"),
                },
                hide_index=True,
                use_container_width=True
            )

            pdf_bytes = gerar_pdf_relatorio(df_agrupado, titulo="Relatório de Pedido Geral")
            
            st.download_button(
                label="📄 Baixar Relatório Consolidado de Pedidos em PDF",
                data=pdf_bytes,
                file_name=f"Relatorio_Pedido_Geral_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                mime="application/pdf",
                use_container_width=True
            )

            # FERRAMENTAS ADICIONAIS
            st.markdown("---")
            st.subheader("🛠️ Outras Opções de Gerenciamento")
            
            tab_del, tab_add, tab_status = st.tabs([
                "🗑️ Remover Item do Pedido",
                "➕ Adicionar Produto ao Pedido",
                "⚡ Alterar Status / Converter Pedido Completo em Venda"
            ])

            with tab_del:
                st.write("**Remova uma linha específica de um pedido pelo seu ID:**")
                col_d1, col_d2 = st.columns([3, 1])
                with col_d1:
                    id_para_remover = st.selectbox("Selecione o ID da linha que deseja excluir", pedidos_df['id'].tolist(), key="del_item_id")
                    item_info = pedidos_df[pedidos_df['id'] == id_para_remover].iloc[0]
                    st.info(f"<b>Item Selecionado:</b> {item_info['produto']} | Qtd: {item_info['quantidade']} | Total: R$ {item_info['valor_total']:,.2f} | Pedido: {item_info['codigo_pedido']}", icon="ℹ️")
                with col_d2:
                    st.write("")
                    st.write("")
                    if st.button("🗑️ Excluir Este Item", type="primary", key="btn_del_item"):
                        cursor.execute("DELETE FROM pedidos WHERE id = ?", (id_para_remover,))
                        conn.commit()
                        st.success(f"Item ID #{id_para_remover} removido!")
                        st.rerun()

            with tab_add:
                st.write("**Adicione mais um produto a um pedido já criado:**")
                codigos_unicos = pedidos_df['codigo_pedido'].unique().tolist()
                
                cod_ped_sel = st.selectbox("Selecione o Código do Pedido", codigos_unicos, key="add_cod_ped")
                ped_ref = pedidos_df[pedidos_df['codigo_pedido'] == cod_ped_sel].iloc[0]
                
                col_a1, col_a2, col_a3, col_a4 = st.columns(4)
                with col_a1:
                    add_prod = st.selectbox("Produto a Adicionar", produtos_df['produto'].tolist(), key="add_p_name")
                    p_info_add = produtos_df[produtos_df['produto'] == add_prod].iloc[0]
                with col_a2:
                    add_forn = st.selectbox("Fornecedor", list_fornecedores, key="add_f_name")
                with col_a3:
                    add_qtd = st.number_input("Quantidade", min_value=0.01, value=1.0, step=0.1, key="add_q_val")
                with col_a4:
                    add_preco = st.number_input("Valor Unitário Venda (R$)", value=float(p_info_add['valor_venda']), min_value=0.0, key="add_v_val")
                
                if st.button("➕ Confirmar Inclusão no Pedido"):
                    val_tot_item = add_qtd * add_preco
                    data_add = ped_ref['data']
                    cli_add = ped_ref['cliente']
                    grp_add = p_info_add.get('grupo', 'GERAL')
                    status_add = ped_ref['status']
                    obs_add = ped_ref.get('observacoes', '')

                    cursor.execute('''
                        INSERT INTO pedidos (codigo_pedido, cliente, produto, fornecedor, grupo, quantidade, valor_unitario, valor_total, status, observacoes, data)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (cod_ped_sel, cli_add, add_prod, add_forn, grp_add, add_qtd, add_preco, val_tot_item, status_add, obs_add, data_add))
                    
                    conn.commit()
                    st.success(f"Novo item '{add_prod}' adicionado ao pedido {cod_ped_sel}!")
                    st.rerun()

            with tab_status:
                st.markdown("### 🏷️ Converter Pedido Completo em Venda")
                
                codigos_pedidos_unicos = pedidos_df['codigo_pedido'].dropna().unique().tolist()
                
                if not codigos_pedidos_unicos:
                    st.warning("Nenhum pedido encontrado.")
                else:
                    col_ped1, col_ped2 = st.columns(2)
                    
                    with col_ped1:
                        codigo_sel = st.selectbox("Selecione o Código do Pedido para Converter", codigos_pedidos_unicos, key="cod_ped_converter")
                        
                        df_itens_pedido = pedidos_df[pedidos_df['codigo_pedido'] == codigo_sel]
                        cliente_do_pedido = df_itens_pedido['cliente'].iloc[0] if not df_itens_pedido.empty else "N/A"
                        val_total_pedido = df_itens_pedido['valor_total'].sum()
                        
                        st.info(f"**Cliente:** {cliente_do_pedido} | **Itens:** {len(df_itens_pedido)} | **Valor Total:** R$ {val_total_pedido:,.2f}")
                        
                        novo_status_massa = st.selectbox("Ou altere apenas o Status do Pedido Completo", ["Pendente", "Em Andamento", "Cancelado"])
                        if st.button("Atualizar Status do Pedido Completo"):
                            cursor.execute("UPDATE pedidos SET status = ? WHERE codigo_pedido = ?", (novo_status_massa, codigo_sel))
                            conn.commit()
                            st.success(f"Status do pedido {codigo_sel} alterado para '{novo_status_massa}'!")
                            st.rerun()
                    
                    with col_ped2:
                        st.write("---")
                        forma_pag_conv = st.selectbox("Forma de Pagamento da Venda", ["Dinheiro", "Pix", "Cartão de Débito", "Cartão de Crédito", "Crediário / Fiado"], key="conv_pag_massa")
                        
                        if st.button("🚀 CONVERTER PEDIDO COMPLETO EM VENDA", type="primary"):
                            data_hoje = datetime.now().strftime('%Y-%m-%d %H:%M')
                            
                            for idx, row in df_itens_pedido.iterrows():
                                p_nome = row['produto']
                                p_qtd = float(row['quantidade'])
                                p_cli = row['cliente']
                                p_forn = row.get('fornecedor', 'Geral')
                                p_grp = row.get('grupo', 'GERAL')
                                
                                cursor.execute("SELECT valor_venda FROM produtos WHERE produto = ?", (p_nome,))
                                res_est = cursor.fetchone()
                                if res_est and res_est[0] is not None and res_est[0] > 0:
                                    p_val_un = float(res_est[0])
                                else:
                                    p_val_un = float(row['valor_unitario'])
                                
                                p_val_tot = p_qtd * p_val_un
                                
                                val_rec = p_val_tot if forma_pag_conv != "Crediário / Fiado" else 0.0
                                val_rest = 0.0 if forma_pag_conv != "Crediário / Fiado" else p_val_tot
                                
                                cursor.execute('''
                                    INSERT INTO vendas (codigo_venda, cliente, produto, fornecedor, grupo, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, troco, restante, data)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, ?, ?)
                                ''', (codigo_sel, p_cli, p_nome, p_forn, p_grp, p_qtd, p_val_un, p_val_tot, forma_pag_conv, val_rec, val_rest, data_hoje))
                                
                                cursor.execute("UPDATE produtos SET quantidade = quantidade - ? WHERE produto = ?", (p_qtd, p_nome))
                            
                            cursor.execute("UPDATE pedidos SET status = 'Concluído (Convertido)' WHERE codigo_pedido = ?", (codigo_sel,))
                            conn.commit()
                            
                            st.success(f"✅ Pedido {codigo_sel} ({cliente_do_pedido}) convertido em VENDA!")
                            st.rerun()

# -----------------------------------------------------------------------------
# 3. REGISTRAR VENDA & GERENCIAR VENDAS
# -----------------------------------------------------------------------------
elif menu == "🛒 Registrar Venda":
    st.title("🛒 Gerenciamento & Lançamento de Vendas")
    
    tab_venda_nova, tab_venda_lista = st.tabs(["➕ Lançar Venda Avulsa", "📑 Vendas Realizadas & Relatórios"])
    produtos_df = pd.read_sql_query("SELECT * FROM produtos", conn)

    with tab_venda_nova:
        with st.expander("➕ Cadastrar Novo Produto Rapidamente no Estoque"):
            col_np1, col_np2, col_np3, col_np4 = st.columns(4)
            with col_np1:
                rapido_nome = st.text_input("Nome do Novo Produto").strip().upper()
            with col_np2:
                rapido_grupo = st.selectbox("Grupo", list_grupos, key="g_rap_v")
            with col_np3:
                rapido_custo = st.number_input("Custo Compra (R$)", min_value=0.0, key="c_rap_v")
            with col_np4:
                rapido_venda = st.number_input("Preço Venda (R$)", min_value=0.0, key="v_rap_v")
                
            if st.button("Salvar Produto no Estoque"):
                if rapido_nome:
                    try:
                        cursor.execute("INSERT INTO produtos (produto, grupo, quantidade, valor_compra, valor_venda) VALUES (?, ?, 0.0, ?, ?)", 
                                       (rapido_nome, rapido_grupo, rapido_custo, rapido_venda))
                        conn.commit()
                        st.success(f"Produto '{rapido_nome}' cadastrado com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao cadastrar produto: {e}")
                else:
                    st.warning("Informe o nome do produto.")

        st.markdown("---")
        st.subheader("🛒 Lançar Nova Venda Direta")

        if produtos_df.empty:
            st.warning("Nenhum produto cadastrado no estoque.")
        else:
            col_v1, col_v2 = st.columns(2)
            with col_v1:
                v_cliente = st.selectbox("Cliente", list_clientes, key="v_cli_sel")
                v_produto = st.selectbox("Produto", produtos_df['produto'].tolist(), key="v_prod_sel")
                
                prod_row = produtos_df[produtos_df['produto'] == v_produto].iloc[0]
                v_grupo_padrao = prod_row.get('grupo', 'GERAL')
                v_preco_padrao = float(prod_row['valor_venda'])
            
            with col_v2:
                v_fornecedor = st.selectbox("Fornecedor", list_fornecedores, key="v_forn_sel")
                v_grupo = st.selectbox("Grupo", list_grupos, index=list_grupos.index(v_grupo_padrao) if v_grupo_padrao in list_grupos else 0, key="v_grp_sel")

            c_pv1, c_pv2, c_pv3 = st.columns(3)
            with c_pv1:
                v_quantidade = st.number_input("Quantidade", min_value=0.01, value=1.0, step=0.1, key="v_qtd_val")
            with c_pv2:
                v_preco_unit = st.number_input("Preço de Venda (R$)", min_value=0.0, value=v_preco_padrao, step=0.5, key="v_prc_val")
            with c_pv3:
                v_total_calc = v_quantidade * v_preco_unit
                st.markdown(f"### Total: **R$ {v_total_calc:,.2f}**")

            c_pag1, c_pag2 = st.columns(2)
            with c_pag1:
                v_forma_pag = st.selectbox("Forma de Pagamento", ["Dinheiro", "Pix", "Cartão de Débito", "Cartão de Crédito", "Crediário / Fiado"], key="v_fpag_sel")
            with c_pag2:
                val_default_rec = 0.0 if v_forma_pag == "Crediário / Fiado" else v_total_calc
                v_valor_recebido = st.number_input("Valor Recebido (R$)", min_value=0.0, value=float(val_default_rec), step=1.0, key="v_vrec_val")

            if st.button("✅ Registrar Venda Direta", type="primary", use_container_width=True):
                data_hoje = datetime.now().strftime('%Y-%m-%d %H:%M')
                codigo_venda = f"VEN-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                
                troco = max(0.0, v_valor_recebido - v_total_calc) if v_forma_pag != "Crediário / Fiado" else 0.0
                restante = max(0.0, v_total_calc - v_valor_recebido) if v_forma_pag == "Crediário / Fiado" else 0.0

                cursor.execute('''
                    INSERT INTO vendas (codigo_venda, cliente, produto, fornecedor, grupo, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, troco, restante, data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (codigo_venda, v_cliente, v_produto, v_fornecedor, v_grupo, v_quantidade, v_preco_unit, v_total_calc, v_forma_pag, v_valor_recebido, troco, restante, data_hoje))

                cursor.execute("UPDATE produtos SET quantidade = quantidade - ? WHERE produto = ?", (v_quantidade, v_produto))
                conn.commit()

                st.success(f"Venda {codigo_venda} registrada com sucesso!")
                st.rerun()

    with tab_venda_lista:
        st.subheader("🔍 Filtros de Relatório de Vendas")
        col_fv1, col_fv2, col_fv3 = st.columns(3)
        with col_fv1:
            f_v_cli = st.selectbox("Cliente", ["Todos"] + list_clientes, key="fv_cli")
            f_v_forn = st.selectbox("Fornecedor", ["Todos"] + list_fornecedores, key="fv_forn")
        with col_fv2:
            f_v_grp = st.selectbox("Grupo", ["Todos"] + list_grupos, key="fv_grp")
            f_v_fpag = st.selectbox("Forma de Pagamento", ["Todas", "Dinheiro", "Pix", "Cartão de Débito", "Cartão de Crédito", "Crediário / Fiado"], key="fv_fpag")
        with col_fv3:
            f_v_dini = st.date_input("Data Inicial", value=date(2024, 1, 1), key="fv_dini")
            f_v_dfim = st.date_input("Data Final", value=date.today(), key="fv_dfim")

        q_v = "SELECT * FROM vendas WHERE 1=1"
        p_v = []
        if f_v_cli != "Todos":
            q_v += " AND cliente = ?"
            p_v.append(f_v_cli)
        if f_v_forn != "Todos":
            q_v += " AND fornecedor = ?"
            p_v.append(f_v_forn)
        if f_v_grp != "Todos":
            q_v += " AND grupo = ?"
            p_v.append(f_v_grp)
        if f_v_fpag != "Todas":
            q_v += " AND forma_pagamento = ?"
            p_v.append(f_v_fpag)

        q_v += " ORDER BY id DESC"
        df_vendas_fil = pd.read_sql_query(q_v, conn, params=p_v)

        if not df_vendas_fil.empty and 'data' in df_vendas_fil.columns:
            df_vendas_fil['data_dt'] = pd.to_datetime(df_vendas_fil['data'], errors='coerce').dt.date
            df_vendas_fil = df_vendas_fil[(df_vendas_fil['data_dt'] >= f_v_dini) & (df_vendas_fil['data_dt'] <= f_v_dfim)]
            df_vendas_fil = df_vendas_fil.drop(columns=['data_dt'])

        st.markdown("---")
        if df_vendas_fil.empty:
            st.warning("Nenhuma venda encontrada para os filtros selecionados.")
        else:
            st.dataframe(df_vendas_fil, use_container_width=True)

            df_v_agrupado = df_vendas_fil.groupby('produto', as_index=False).agg({
                'quantidade': 'sum',
                'valor_total': 'sum'
            })
            df_v_agrupado['valor_unitario_medio'] = df_v_agrupado['valor_total'] / df_v_agrupado['quantidade']

            pdf_bytes_vendas = gerar_pdf_relatorio(df_v_agrupado, titulo="Relatório Consolidado de Vendas")
            st.download_button(
                label="📄 Baixar Relatório de Vendas em PDF",
                data=pdf_bytes_vendas,
                file_name=f"Relatorio_Vendas_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                mime="application/pdf",
                use_container_width=True
            )

# -----------------------------------------------------------------------------
# 4. ENTRADA DE ESTOQUE (COMPRAS)
# -----------------------------------------------------------------------------
elif menu == "📥 Entrada de Estoque (Compras)":
    st.title("📥 Lançamento de Compras / Entrada de Estoque")
    
    produtos_df = pd.read_sql_query("SELECT * FROM produtos", conn)

    if produtos_df.empty:
        st.warning("Cadastre produtos primeiro na aba 'Estoque de Produtos'.")
    else:
        c_e1, c_e2 = st.columns(2)
        with c_e1:
            ent_produto = st.selectbox("Produto que deu Entrada", produtos_df['produto'].tolist(), key="ent_p_sel")
            p_inf_ent = produtos_df[produtos_df['produto'] == ent_produto].iloc[0]
            ent_fornecedor = st.selectbox("Fornecedor / Origem", list_fornecedores, key="ent_f_sel")
        with c_e2:
            ent_grupo = st.selectbox("Grupo", list_grupos, index=list_grupos.index(p_inf_ent.get('grupo', 'GERAL')) if p_inf_ent.get('grupo', 'GERAL') in list_grupos else 0, key="ent_g_sel")
            ent_qtd = st.number_input("Quantidade Entrada", min_value=0.01, value=10.0, step=1.0, key="ent_q_val")

        c_ec1, c_ec2 = st.columns(2)
        with c_ec1:
            ent_vcompra = st.number_input("Preço Custo Compra Unit. (R$)", min_value=0.0, value=float(p_inf_ent['valor_compra']), step=1.0)
        with c_ec2:
            ent_vvenda = st.number_input("Novo Preço Venda Unit. (R$)", min_value=0.0, value=float(p_inf_ent['valor_venda']), step=1.0)

        total_compra = ent_qtd * ent_vcompra
        st.markdown(f"### Valor Total do Lote de Compra: **R$ {total_compra:,.2f}**")

        if st.button("📥 Confirmar Entrada no Estoque", type="primary", use_container_width=True):
            data_hoje = datetime.now().strftime('%Y-%m-%d %H:%M')

            cursor.execute('''
                INSERT INTO compras (produto, fornecedor, grupo, quantidade, valor_compra, valor_venda, valor_total, data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (ent_produto, ent_fornecedor, ent_grupo, ent_qtd, ent_vcompra, ent_vvenda, total_compra, data_hoje))

            cursor.execute('''
                UPDATE produtos 
                SET quantidade = quantidade + ?, valor_compra = ?, valor_venda = ?
                WHERE produto = ?
            ''', (ent_qtd, ent_vcompra, ent_vvenda, ent_produto))

            conn.commit()
            st.success(f"Estoque do produto '{ent_produto}' atualizado (+{ent_qtd}) com sucesso!")
            st.rerun()

    st.markdown("---")
    st.subheader("📜 Histórico Recente de Compras e Entradas")
    df_compras = pd.read_sql_query("SELECT * FROM compras ORDER BY id DESC", conn)
    st.dataframe(df_compras, use_container_width=True)

# -----------------------------------------------------------------------------
# 5. ESTOQUE DE PRODUTOS
# -----------------------------------------------------------------------------
elif menu == "📦 Estoque de Produtos":
    st.title("📦 Cadastro & Consulta de Estoque")

    with st.expander("➕ Cadastrar Novo Produto Completo"):
        cp1, cp2, cp3 = st.columns(3)
        with cp1:
            np_nome = st.text_input("Nome do Produto", key="cad_p_nome").strip().upper()
            np_grupo = st.selectbox("Grupo", list_grupos, key="cad_p_grp")
        with cp2:
            np_qtd = st.number_input("Estoque Inicial", min_value=0.0, value=0.0, step=1.0, key="cad_p_qtd")
            np_custo = st.number_input("Preço de Compra / Custo (R$)", min_value=0.0, value=0.0, step=1.0, key="cad_p_custo")
        with cp3:
            np_venda = st.number_input("Preço de Venda (R$)", min_value=0.0, value=0.0, step=1.0, key="cad_p_venda")

        if st.button("Salvar Novo Produto", type="primary"):
            if np_nome:
                try:
                    cursor.execute('''
                        INSERT INTO produtos (produto, grupo, quantidade, valor_compra, valor_venda)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (np_nome, np_grupo, np_qtd, np_custo, np_venda))
                    conn.commit()
                    st.success(f"Produto '{np_nome}' cadastrado!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao salvar produto: {e}")
            else:
                st.warning("Preencha o nome do produto.")

    st.markdown("---")
    st.subheader("📋 Estoque Atual de Produtos")
    df_produtos_all = pd.read_sql_query("SELECT * FROM produtos ORDER BY produto ASC", conn)

    if not df_produtos_all.empty:
        df_produtos_all['Valor Total Estoque (R$)'] = df_produtos_all['quantidade'] * df_produtos_all['valor_venda']
        st.dataframe(df_produtos_all, use_container_width=True)

        st.metric("Total em Dinheiro no Estoque (Preço de Venda)", f"R$ {df_produtos_all['Valor Total Estoque (R$)'].sum():,.2f}")
    else:
        st.info("Nenhum produto cadastrado.")

# -----------------------------------------------------------------------------
# 6. CADASTROS (CLIENTES / FORNECEDORES / GRUPOS)
# -----------------------------------------------------------------------------
elif menu == "👥 Cadastros (Clientes / Fornecedores / Grupos)":
    st.title("👥 Central de Cadastros")

    tab_cli, tab_forn, tab_grp = st.tabs(["👤 Clientes", "🏭 Fornecedores", "🏷️ Grupos de Produtos"])

    with tab_cli:
        st.subheader("Cadastrar Cliente")
        cc1, cc2, cc3 = st.columns(3)
        with cc1:
            c_nome = st.text_input("Nome do Cliente", key="c_nome")
            c_cpf = st.text_input("CPF / CNPJ", key="c_cpf")
        with cc2:
            c_fone = st.text_input("Telefone / WhatsApp", key="c_fone")
            c_email = st.text_input("E-mail", key="c_email")
        with cc3:
            c_end = st.text_input("Endereço", key="c_end")

        if st.button("💾 Salvar Cliente"):
            if c_nome:
                try:
                    cursor.execute('''
                        INSERT INTO clientes (cliente, cpf, endereco, email, fone)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (c_nome, c_cpf, c_end, c_email, c_fone))
                    conn.commit()
                    st.success("Cliente cadastrado!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao cadastrar: {e}")
            else:
                st.warning("Nome é obrigatório.")

        st.markdown("---")
        st.dataframe(pd.read_sql_query("SELECT * FROM clientes", conn), use_container_width=True)

    with tab_forn:
        st.subheader("Cadastrar Fornecedor")
        f_nome = st.text_input("Nome do Fornecedor", key="f_nome").strip().upper()
        if st.button("💾 Salvar Fornecedor"):
            if f_nome:
                try:
                    cursor.execute("INSERT INTO fornecedores (fornecedor) VALUES (?)", (f_nome,))
                    conn.commit()
                    st.success("Fornecedor cadastrado!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao cadastrar: {e}")

        st.markdown("---")
        st.dataframe(pd.read_sql_query("SELECT * FROM fornecedores", conn), use_container_width=True)

    with tab_grp:
        st.subheader("Cadastrar Grupo de Produtos")
        g_nome = st.text_input("Nome do Grupo", key="g_nome").strip().upper()
        if st.button("💾 Salvar Grupo"):
            if g_nome:
                try:
                    cursor.execute("INSERT INTO grupos (grupo) VALUES (?)", (g_nome,))
                    conn.commit()
                    st.success("Grupo cadastrado!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao cadastrar: {e}")

        st.markdown("---")
        st.dataframe(pd.read_sql_query("SELECT * FROM grupos", conn), use_container_width=True)
