import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date
import io
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# -----------------------------------------------------------------------------
# 1. CONFIGURAÇÃO E CONEXÃO COM O BANCO DE DADOS
# -----------------------------------------------------------------------------
st.set_page_config(page_title="CRM Comércio - Rey da Cebola", layout="wide")

def get_connection():
    return sqlite3.connect("crm_comercio.db", check_same_thread=False)

conn = get_connection()

def adequar_banco_e_migrar():
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
            codigo TEXT DEFAULT 'PED',
            data TEXT
        )
    """)
    try:
        cursor.execute("ALTER TABLE vendas ADD COLUMN tipo TEXT DEFAULT 'PEDIDO'")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE vendas ADD COLUMN codigo TEXT DEFAULT 'PED'")
    except sqlite3.OperationalError:
        pass
    conn.commit()

    # CORREÇÃO AUTOMÁTICA: Converte todo o histórico antigo de PED/PEDIDO para VEN/VENDA
    cursor.execute("""
        UPDATE vendas 
        SET tipo = 'VENDA', codigo = 'VEN' 
        WHERE UPPER(TRIM(COALESCE(tipo, ''))) IN ('PEDIDO', 'PED', '') 
           OR UPPER(TRIM(COALESCE(codigo, ''))) IN ('PED', 'PEDIDO', '')
    """)
    conn.commit()

adequar_banco_e_migrar()

def carregar_dados(query):
    try:
        return pd.read_sql_query(query, conn)
    except Exception:
        return pd.DataFrame()

def carregar_coluna(tabela, coluna):
    df = carregar_dados(f"SELECT DISTINCT TRIM({coluna}) as {coluna} FROM {tabela} WHERE {coluna} IS NOT NULL AND {coluna} != ''")
    if not df.empty:
        return df[coluna].tolist()
    return []

# -----------------------------------------------------------------------------
# FUNÇÕES DE REGISTRO E CONVERSÃO
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
                       (nome.strip(), telefone, doc, endereco, cidade))
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
                       (nome.strip(), grupo, preco_custo, preco_venda, estoque_inicial))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def salvar_simples(tabela, coluna, valor):
    cursor = conn.cursor()
    cursor.execute(f"CREATE TABLE IF NOT EXISTS {tabela} (id INTEGER PRIMARY KEY AUTOINCREMENT, {coluna} TEXT UNIQUE)")
    try:
        cursor.execute(f"INSERT INTO {tabela} ({coluna}) VALUES (?)", (valor.strip(),))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def salvar_pedido_ou_venda(cliente, produto, fornecedor, grupo, quantidade, valor_venda, forma_pagamento, valor_recebido, tipo="PEDIDO"):
    cursor = conn.cursor()
    valor_total = quantidade * valor_venda
    data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cod_status = "VEN" if tipo.upper() in ["VENDA", "VENDAS", "VEN"] else "PED"
    
    cursor.execute("""
        INSERT INTO vendas (cliente, produto, fornecedor, grupo, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, tipo, codigo, data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (cliente.strip(), produto, fornecedor, grupo, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, tipo, cod_status, data_atual))
    conn.commit()

def converter_pedido_completo_para_venda(cliente_nome):
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE vendas 
        SET tipo = 'VENDA', codigo = 'VEN' 
        WHERE TRIM(cliente) = TRIM(?)
    """, (cliente_nome,))
    conn.commit()
    return cursor.rowcount

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
# GERADOR DE PDF CUSTOMIZADO (MODELO REY DA CEBOLA)
# -----------------------------------------------------------------------------
def gerar_pdf_tabela_pedidos(df_dados, cliente_nome="Geral", d_inicio=None, d_fim=None, titulo_custom=None):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    elements = []
    styles = getSampleStyleSheet()
    
    style_empresa = ParagraphStyle(
        'EmpresaStyle', parent=styles['Heading1'], fontName='Helvetica-BoldOblique', fontSize=20, leading=22, alignment=1, textColor=colors.black
    )
    style_sub = ParagraphStyle(
        'SubStyle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9, leading=11, alignment=1
    )
    style_titulo_relatorio = ParagraphStyle(
        'RelatorioStyle', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=15, leading=18, alignment=1, textColor=colors.HexColor('#1E50A2')
    )
    style_data = ParagraphStyle(
        'DataStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=9, leading=11, alignment=1, textColor=colors.HexColor('#333333')
    )

    elements.append(Paragraph("REY DA CEBOLA", style_empresa))
    elements.append(Paragraph("CNPJ: 194.174.39/000-42 INSC.EST.: 12.426725-4", style_sub))
    elements.append(Paragraph("CONTATO: (99) 98814-9722 OU (99) 98414-3943", style_sub))
    elements.append(Spacer(1, 10))
    
    titulo_doc = titulo_custom if titulo_custom else f"Relatório de Pedidos / Vendas - {cliente_nome}"
    elements.append(Paragraph(titulo_doc, style_titulo_relatorio))
    periodo_str = f"Período: {d_inicio.strftime('%d/%m/%Y')} até {d_fim.strftime('%d/%m/%Y')}" if d_inicio and d_fim else f"Data de Emissão: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    elements.append(Spacer(1, 4))
    elements.append(Paragraph(periodo_str, style_data))
    elements.append(Spacer(1, 15))
    
    if not df_dados.empty:
        df_resumo = df_dados.groupby('produto').agg({
            'quantidade': 'sum',
            'valor_venda': 'mean',
            'valor_total': 'sum'
        }).reset_index()
    else:
        df_resumo = pd.DataFrame(columns=['produto', 'quantidade', 'valor_venda', 'valor_total'])

    table_data = [["Produto", "Qtd Total", "Valor Unit. Médio (R$)", "Valor Total (R$)"]]
    valor_total_geral = 0.0
    for _, row in df_resumo.iterrows():
        prod = str(row['produto'])
        qtd = f"{row['quantidade']:.2f}"
        v_unit = f"R$ {row['valor_venda']:,.2f}"
        v_tot = row['valor_total']
        valor_total_geral += v_tot
        table_data.append([prod, qtd, v_unit, f"R$ {v_tot:,.2f}"])
        
    table_data.append(["VALOR TOTAL GERAL", "", "", f"R$ {valor_total_geral:,.2f}"])
    
    t = Table(table_data, colWidths=[220, 90, 120, 120])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2A65F0')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (0, 1), (0, -2), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#CCCCCC')),
        ('SPAN', (0, -1), (2, -1)),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#1B2A4A')),
        ('TEXTCOLOR', (0, -1), (-1, -1), colors.white),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, -1), (-1, -1), 11),
        ('ALIGN', (0, -1), (2, -1), 'RIGHT'),
        ('ALIGN', (-1, -1), (-1, -1), 'CENTER'),
    ]))
    
    elements.append(t)
    doc.build(elements)
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
        
        lista_clientes = carregar_coluna("clientes", "nome") or carregar_coluna("vendas", "cliente") or ["Carlos Alberto"]
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
            query_cli = f"SELECT * FROM vendas WHERE TRIM(cliente) = TRIM('{st.session_state.cliente_autenticado}')"
            df_pedidos = carregar_dados(query_cli)
            if not df_pedidos.empty:
                soma_total = df_pedidos['valor_total'].sum() if 'valor_total' in df_pedidos.columns else 0.0
                st.markdown(f"**Itens Registrados:** {len(df_pedidos)} | **Soma dos Valores:** R$ {soma_total:,.2f}")
                st.dataframe(df_pedidos, use_container_width=True)
                
                st.markdown("---")
                pdf_cli = gerar_pdf_tabela_pedidos(df_pedidos, cliente_nome=st.session_state.cliente_autenticado)
                st.download_button(
                    label=f"📄 Baixar Relatório de Pedidos ({st.session_state.cliente_autenticado}) em PDF",
                    data=pdf_cli,
                    file_name=f"Relatorio_Pedidos_{st.session_state.cliente_autenticado}.pdf",
                    mime="application/pdf"
                )
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
            st.title("📊 Painel Financeiro & Fechamento por Data")
            
            col_d1, col_d2, col_d3 = st.columns(3)
            with col_d1:
                data_inicio = st.date_input("Data Inicial", value=date(2025, 1, 1))
            with col_d2:
                data_fim = st.date_input("Data Final", value=date.today())
            with col_d3:
                status_filtro = st.selectbox("Status dos Registros", ["Somente Vendas Concluídas", "Incluir Pedidos Pendentes", "Todos"])
                
            str_d1 = data_inicio.strftime("%Y-%m-%d")
            str_d2 = data_fim.strftime("%Y-%m-%d")
            
            df_todas = carregar_dados("SELECT * FROM vendas")
            
            if not df_todas.empty:
                # Se for "Somente Vendas Concluídas", padroniza a exibição visual para VEN/VENDA
                if status_filtro == "Somente Vendas Concluídas":
                    df_todas['tipo'] = 'VENDA'
                    df_todas['codigo'] = 'VEN'

                df_todas['tipo_str'] = df_todas['tipo'].fillna('').astype(str).str.strip().str.upper() if 'tipo' in df_todas.columns else ''
                df_todas['codigo_str'] = df_todas['codigo'].fillna('').astype(str).str.strip().str.upper() if 'codigo' in df_todas.columns else ''
                
                is_venda = df_todas['tipo_str'].isin(['VENDA', 'VENDAS', 'VEN']) | df_todas['codigo_str'].isin(['VEN', 'VENDA'])
                
                if status_filtro == "Somente Vendas Concluídas":
                    df_vendas = df_todas[is_venda]
                elif status_filtro == "Incluir Pedidos Pendentes":
                    df_vendas = df_todas[~is_venda]
                else:
                    df_vendas = df_todas.copy()
                
                if 'data' in df_vendas.columns:
                    df_vendas['data_curta'] = df_vendas['data'].fillna('').astype(str).str.slice(0, 10)
                    mask_data = (df_vendas['data_curta'] >= str_d1) & (df_vendas['data_curta'] <= str_d2)
                    df_vendas = df_vendas[mask_data | (df_vendas['data_curta'] == '')]
                    df_vendas = df_vendas.drop(columns=['data_curta', 'tipo_str', 'codigo_str'], errors='ignore')
            else:
                df_vendas = pd.DataFrame()
            
            if not df_vendas.empty:
                col1, col2, col3 = st.columns(3)
                faturamento = df_vendas['valor_total'].sum() if 'valor_total' in df_vendas.columns else 0.0
                valor_rec = df_vendas['valor_recebido'].sum() if 'valor_recebido' in df_vendas.columns else 0.0
                col1.metric("Faturamento do Período", f"R$ {faturamento:,.2f}")
                col2.metric("Total Recebido em Caixa", f"R$ {valor_rec:,.2f}")
                col3.metric("Total Pendente / Fiado", f"R$ {faturamento - valor_rec:,.2f}")
                st.markdown("---")
                
                st.subheader("📊 Registros Encontrados")
                st.dataframe(df_vendas, use_container_width=True)
                
                st.markdown("---")
                st.subheader("📄 Gerar Relatório do Fechamento Financeiro em PDF")
                pdf_fechamento = gerar_pdf_tabela_pedidos(
                    df_vendas, 
                    cliente_nome="Geral", 
                    d_inicio=data_inicio, 
                    d_fim=data_fim,
                    titulo_custom=f"Fechamento Financeiro ({status_filtro})"
                )
                
                st.download_button(
                    label="📥 Baixar Relatório de Fechamento Financeiro (PDF)",
                    data=pdf_fechamento,
                    file_name=f"Fechamento_Financeiro_{str_d1}_a_{str_d2}.pdf",
                    mime="application/pdf"
                )
            else:
                st.info("Nenhum registro encontrado para os filtros selecionados. Tente alterar o status ou o intervalo de datas.")

        elif menu_admin in ["📋 Pedidos / Orçamentos", "🛒 Registrar Venda"]:
            st.title(f"📋 {menu_admin}")
            aba_cad, aba_list = st.tabs(["➕ Novo Registro / Pedido", "📜 Gestão de Pedidos e Vendas"])
            
            with aba_cad:
                clientes_opt = carregar_coluna("clientes", "nome") or ["Carlos Alberto"]
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
                        v_rec = st.number_input("Valor Recebido (R$)", min_value=0.0, step=1.0, value=v_unit * qtd)
                    
                    if st.form_submit_button(f"Salvar como {tipo_registro}"):
                        salvar_pedido_ou_venda(cli, prod, fornec, grupo, qtd, v_unit, f_pag, v_rec, tipo=tipo_registro)
                        st.success(f"{tipo_registro} gravado com sucesso!")
                        st.rerun()

            with aba_list:
                st.subheader("🔍 Consultar e Gerenciar Registros por Data e Cliente")
                
                col_f1, col_f2, col_f3 = st.columns(3)
                with col_f1:
                    clientes_filtro = ["TODOS"] + (carregar_coluna("clientes", "nome") or carregar_coluna("vendas", "cliente"))
                    cliente_sel = st.selectbox("Filtrar por Cliente:", clientes_filtro)
                with col_f2:
                    d_inicio = st.date_input("Data Inicial do Filtro", value=date(2025, 1, 1))
                with col_f3:
                    d_fim = st.date_input("Data Final do Filtro", value=date.today())
                
                s_d1 = d_inicio.strftime("%Y-%m-%d")
                s_d2 = d_fim.strftime("%Y-%m-%d")
                
                query_filt = f"SELECT * FROM vendas WHERE (substr(data, 1, 10) >= '{s_d1}' AND substr(data, 1, 10) <= '{s_d2}' OR data IS NULL OR data = '')"
                if cliente_sel != "TODOS":
                    query_filt += f" AND TRIM(cliente) = TRIM('{cliente_sel}')"
                    nome_relatorio = cliente_sel
                else:
                    nome_relatorio = "Geral"
                    
                df_registros = carregar_dados(query_filt)
                
                if not df_registros.empty:
                    st.dataframe(df_registros, use_container_width=True)
                    
                    st.markdown("---")
                    st.subheader(f"📄 Gerar Relatório em PDF ({nome_relatorio})")
                    
                    pdf_gerado = gerar_pdf_tabela_pedidos(df_registros, cliente_nome=nome_relatorio, d_inicio=d_inicio, d_fim=d_fim)
                    
                    st.download_button(
                        label=f"📥 Baixar Relatório de Pedidos - {nome_relatorio} (PDF)",
                        data=pdf_gerado,
                        file_name=f"Relatorio_Pedidos_{nome_relatorio}.pdf",
                        mime="application/pdf"
                    )
                    
                    st.markdown("---")
                    
                    if cliente_sel != "TODOS":
                        tipo_str = df_registros['tipo'].fillna('').astype(str).str.strip().str.upper() if 'tipo' in df_registros.columns else pd.Series([''] * len(df_registros))
                        codigo_str = df_registros['codigo'].fillna('').astype(str).str.strip().str.upper() if 'codigo' in df_registros.columns else pd.Series([''] * len(df_registros))
                        
                        mask_pedidos = (~tipo_str.isin(['VENDA', 'VENDAS', 'VEN'])) & (~codigo_str.isin(['VEN', 'VENDA']))
                        pedidos_pendentes = df_registros[mask_pedidos]
                        
                        if not pedidos_pendentes.empty:
                            st.subheader("⚙️ Converter Pedido Completo em Venda")
                            total_ped = pedidos_pendentes['valor_total'].sum()
                            qtd_itens = len(pedidos_pendentes)
                            st.write(f"O cliente **{cliente_sel}** possui **{qtd_itens} item(ns)** pendente(s) como pedido, somando **R$ {total_ped:,.2f}**.")
                            
                            if st.button(f"🔄 Converter Pedido Completo de {cliente_sel} para VENDA", key="btn_converter_venda"):
                                linhas_afetadas = converter_pedido_completo_para_venda(cliente_sel)
                                st.success(f"Sucesso! {linhas_afetadas} registro(s) do cliente {cliente_sel} foram convertidos para VENDA!")
                                st.rerun()
                        else:
                            st.info(f"✅ Todos os registros exibidos para **{cliente_sel}** já estão confirmados como **VENDA**.")
                    else:
                        st.info("Para converter um pedido em venda, selecione um cliente específico no filtro acima.")
                else:
                    st.info("Nenhum registro encontrado para o período e cliente selecionados.")

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
                        p_venda = st.number_input("Preço de Venda (R$)", min_value=0.0, step=20.0, value=20.0)
                    
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
