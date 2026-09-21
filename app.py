import streamlit as st
import pandas as pd
import sqlite3
import io
from datetime import datetime, date, timedelta
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

def gerar_pdf_cupom(cliente_selecionado, itens):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    elementos = []
    styles = getSampleStyleSheet()

    titulo_estilo = ParagraphStyle(
        'TituloCupom',
        parent=styles['Heading1'],
        fontSize=18,
        alignment=1,
        spaceAfter=10
    )
    
    elementos.append(Paragraph("<b>CRM Comércio — Cupom de Venda</b>", titulo_estilo))
    elementos.append(Spacer(1, 10))
    elementos.append(Paragraph(f"<b>Cliente:</b> {cliente_selecionado}", styles['Normal']))
    elementos.append(Paragraph(f"<b>Data/Hora:</b> {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", styles['Normal']))
    elementos.append(Spacer(1, 15))

    dados_tabela = [["Produto", "Fornecedor", "Grupo", "Qtd", "Unit. (R$)", "Total (R$)"]]
    total_geral = 0.0

    for item in itens:
        qtd = float(item.get('quantidade', 1))
        v_venda = float(item.get('valor_venda', 0))
        v_tot = qtd * v_venda
        total_geral += v_tot

        dados_tabela.append([
            str(item.get('produto', '')),
            str(item.get('fornecedor', '')),
            str(item.get('grupo', '')),
            str(qtd),
            f"R$ {v_venda:.2f}",
            f"R$ {v_tot:.2f}"
        ])

    tabela = Table(dados_tabela, colWidths=[130, 80, 80, 40, 70, 70])
    tabela.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#333333")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    
    elementos.append(tabela)
    elementos.append(Spacer(1, 15))
    elementos.append(Paragraph(f"<b>Total Geral da Venda: R$ {total_geral:.2f}</b>", styles['Heading2']))

    doc.build(elementos)
    buffer.seek(0)
    return buffer.getvalue()

def sanear_df_vendas(df):
    """Trata campos nulos (None) e ajusta o cálculo do valor restante por item."""
    if df is None or df.empty:
        return df
    df = df.copy()
    
    if 'forma_pagamento' in df.columns:
        df['forma_pagamento'] = df['forma_pagamento'].fillna('-').replace({'None': '-', '': '-'})
    
    for col in ['quantidade', 'valor_venda', 'valor_total', 'valor_recebido', 'troco', 'restante']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
            
    if 'valor_total' in df.columns and 'valor_recebido' in df.columns and 'restante' in df.columns:
        mask_excesso = df['restante'] > df['valor_total']
        df.loc[mask_excesso, 'restante'] = (df.loc[mask_excesso, 'valor_total'] - df.loc[mask_excesso, 'valor_recebido']).clip(lower=0.0)

    return df

# -----------------------------------------------------------------------------
# GERADOR DE PDF
# -----------------------------------------------------------------------------
def gerar_pdf_tabela_pedidos(df_dados, cliente_nome="Geral"):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=15, bottomMargin=30)
    story = []

    styles = getSampleStyleSheet()

    style_empresa = ParagraphStyle(
        'Empresa', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=16, 
        leading=20, alignment=1, textColor=colors.HexColor("#0f2a4a"), spaceAfter=4
    )
    style_sub = ParagraphStyle(
        'Sub', parent=styles['Normal'], fontName='Helvetica', fontSize=9, 
        leading=12, alignment=1, spaceAfter=10
    )
    style_titulo = ParagraphStyle(
        'Titulo', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=12, 
        leading=15, alignment=1, textColor=colors.HexColor("#0f2a4a"), spaceAfter=4
    )
    style_info = ParagraphStyle(
        'Info', parent=styles['Normal'], fontName='Helvetica', fontSize=9, 
        leading=12, alignment=1, spaceAfter=15
    )

    story.append(Paragraph("REY DA CEBOLA", style_empresa))
    story.append(Paragraph("CNPJ: 194.174.39/000-42 INSC.EST.: 12.426725-4<br/>CONTATO: (99) 98814-9722 OU (99) 98414-3943", style_sub))

    data_atual = (datetime.utcnow() - timedelta(hours=3)).strftime('%Y-%m-%d %H:%M:%S')

    if cliente_nome not in ["Todos", "Geral", ""]:
        story.append(Paragraph("Relatório de Pedidos / Orçamentos", style_titulo))
        story.append(Paragraph(f"<b>Cliente:</b> {cliente_nome} | <b>Gerado em:</b> {data_atual}", style_info))
    else:
        story.append(Paragraph("Relatório de Pedidos / Orçamentos - Geral", style_titulo))
        story.append(Paragraph(f"<b>Gerado em:</b> {data_atual}", style_info))

    if not df_dados.empty:
        df_proc = df_dados.copy()
        col_qtd = 'quantidade' if 'quantidade' in df_proc.columns else df_proc.columns[3]
        col_unit = 'valor_venda' if 'valor_venda' in df_proc.columns else ('Valor Unitário (R$)' if 'Valor Unitário (R$)' in df_proc.columns else df_proc.columns[4])
        col_tot = 'valor_total' if 'valor_total' in df_proc.columns else ('Total (R$)' if 'Total (R$)' in df_proc.columns else df_proc.columns[5])

        def tratar_num(val):
            if pd.isna(val) or val == '':
                return 0.0
            if isinstance(val, (int, float)):
                return float(val)
            s = str(val).replace('R$', '').strip()
            if ',' in s and '.' in s:
                s = s.replace('.', '').replace(',', '.')
            elif ',' in s:
                s = s.replace(',', '.')
            try:
                return float(s)
            except:
                return 0.0

        df_proc[col_qtd] = df_proc[col_qtd].apply(tratar_num)
        df_proc[col_unit] = df_proc[col_unit].apply(tratar_num)
        df_proc[col_tot] = df_proc[col_tot].apply(tratar_num)

        df_agrupado = df_proc.groupby('produto', as_index=False).agg({
            col_qtd: 'sum',
            col_unit: 'mean',
            col_tot: 'sum'
        })
    else:
        df_agrupado = pd.DataFrame(columns=['produto', 'quantidade', 'valor_venda', 'valor_total'])

    table_data = [["Produto", "Qtd Total", "Preço Unitário (R$)", "Valor Total (R$)"]]
    total_geral = 0.0

    for _, row in df_agrupado.iterrows():
        qtd = float(row[col_qtd])
        unit = float(row[col_unit])
        tot = float(row[col_tot])
        total_geral += tot

        table_data.append([
            str(row['produto']),
            f"{qtd:.2f}",
            f"R$ {unit:.2f}",
            f"R$ {tot:.2f}"
        ])

    table_data.append(["VALOR TOTAL GERAL", "", "", f"R$ {total_geral:.2f}"])

    tabela = Table(table_data, colWidths=[240, 80, 110, 120])
    tabela.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1f4e8c")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor("#d3d3d3")),
        ('SPAN', (0, -1), (2, -1)),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#0d1b2a")),
        ('TEXTCOLOR', (0, -1), (-1, -1), colors.white),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('ALIGN', (0, -1), (0, -1), 'LEFT'),
        ('ALIGN', (-1, -1), (-1, -1), 'RIGHT'),
    ]))

    story.append(tabela)
    doc.build(story)
    buffer.seek(0)
    return buffer

# -----------------------------------------------------------------------------
# CONFIGURAÇÃO E CONEXÃO COM BANCO DE DADOS
# -----------------------------------------------------------------------------
st.set_page_config(page_title="CRM Comércio - Rey da Cebola", layout="wide")

def get_connection():
    return sqlite3.connect("crm_comercio.db", check_same_thread=False)

conn = get_connection()

def adequar_banco_e_migrar():
    try:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente TEXT,
                nome TEXT,
                cpf TEXT,
                doc TEXT,
                endereco TEXT,
                email TEXT,
                fone TEXT,
                telefone TEXT,
                cidade TEXT
            )
        """)
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
                troco REAL,
                restante REAL,
                status TEXT,
                tipo TEXT,
                codigo TEXT,
                codigo_venda TEXT,
                data TEXT
            )
        """)
        cursor.execute("""
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
        """)
        
        for col_nome, col_tipo in [
            ("forma_pagamento", "TEXT"), ("valor_recebido", "REAL"), ("troco", "REAL"),
            ("restante", "REAL"), ("status", "TEXT"), ("tipo", "TEXT"),
            ("fornecedor", "TEXT"), ("grupo", "TEXT"), ("codigo", "TEXT"), ("codigo_venda", "TEXT")
        ]:
            try:
                cursor.execute(f"ALTER TABLE vendas ADD COLUMN {col_nome} {col_tipo};")
                conn.commit()
            except:
                pass

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
            CREATE TABLE IF NOT EXISTS caixa_sessoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_abertura TEXT,
                data_fechamento TEXT,
                saldo_inicial REAL,
                saldo_final REAL,
                status TEXT
            )
        """)
        conn.commit()
    except Exception as e:
        print(f"Aviso de migração: {e}")

adequar_banco_e_migrar()

def executar_limpeza_banco():
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE vendas SET forma_pagamento = '-' WHERE forma_pagamento IS NULL OR forma_pagamento = 'None' OR forma_pagamento = ''")
        cursor.execute("UPDATE vendas SET valor_recebido = 0.0 WHERE valor_recebido IS NULL")
        cursor.execute("UPDATE vendas SET troco = 0.0 WHERE troco IS NULL")
        cursor.execute("UPDATE vendas SET restante = (valor_total - valor_recebido) WHERE restante IS NULL OR restante > valor_total")
        cursor.execute("UPDATE vendas SET restante = 0.0 WHERE restante < 0")
        conn.commit()
    except Exception:
        pass

executar_limpeza_banco()

def carregar_dados(query):
    try:
        return pd.read_sql_query(query, conn)
    except Exception:
        return pd.DataFrame()

def carregar_coluna(tabela, coluna):
    cursor = conn.cursor()
    try:
        cursor.execute(f"PRAGMA table_info({tabela})")
        cols = [col[1] for col in cursor.fetchall()]
        col_alvo = coluna if coluna in cols else (cols[1] if len(cols) > 1 else coluna)
        df = carregar_dados(f"SELECT DISTINCT TRIM({col_alvo}) as {col_alvo} FROM {tabela} WHERE {col_alvo} IS NOT NULL AND {col_alvo} != ''")
        if not df.empty:
            return df[col_alvo].tolist()
    except Exception:
        pass
    return []

def salvar_cliente_completo(nome, telefone, doc, endereco, cidade):
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO clientes (cliente, nome, fone, telefone, cpf, doc, endereco, email, cidade)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (nome.strip(), nome.strip(), telefone, telefone, doc, doc, endereco, cidade, cidade))
        conn.commit()
        st.cache_data.clear()
        return True, "✅ Cliente cadastrado com sucesso!"
    except Exception as e:
        return False, f"Erro ao salvar cliente: {e}"

def salvar_simples(tabela, coluna, valor):
    cursor = conn.cursor()
    try:
        cursor.execute(f"INSERT INTO {tabela} ({coluna}) VALUES (?)", (valor.strip(),))
        conn.commit()
        return True
    except Exception:
        return False

# -----------------------------------------------------------------------------
# NAVEGAÇÃO E PERFIL DE ACESSO
# -----------------------------------------------------------------------------
if 'admin_logged' not in st.session_state:
    st.session_state.admin_logged = False

if 'cliente_autenticado' not in st.session_state:
    st.session_state.cliente_autenticado = None

if 'carrinho_pdv' not in st.session_state:
    st.session_state.carrinho_pdv = []

st.sidebar.title("🔑 Acesso ao Sistema")
opcoes_perfil = ["👤 Portal do Cliente", "🔒 Administração / Vendedor"]
perfil_selecionado = st.sidebar.radio("Selecione o Perfil:", opcoes_perfil, key="perfil_principal_radio")
st.sidebar.markdown("---")

# ==========================================
# AMBIENTE 1: PORTAL DO CLIENTE
# ==========================================
if perfil_selecionado == "👤 Portal do Cliente":
    if not st.session_state.cliente_autenticado:
        st.title("🔒 Portal do Cliente")
        st.info("Por favor, selecione seu nome no menu à esquerda e insira sua senha para acessar seus pedidos.")
        
        df_cli_select = carregar_dados("""
            SELECT DISTINCT COALESCE(NULLIF(cliente, ''), nome) AS cliente_nome 
            FROM clientes 
            WHERE cliente_nome IS NOT NULL AND cliente_nome != '' 
            ORDER BY cliente_nome
        """)
        lista_clientes = df_cli_select['cliente_nome'].tolist() if not df_cli_select.empty else []
        
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
        st.info("Área do cliente ativa. Utilize as abas de navegação internas conforme necessário.")

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
                "🛒 PDV — Frente de Caixa",
                "🔓 Abertura e Fechamento de Caixa",
                "📊 Fechamento & Financeiro",
                "📋 Pedidos / Orçamentos",
                "🛒 Registrar Venda",
                "📥 Entrada de Estoque (Compras)",
                "📦 Estoque de Produtos",
                "👥 Cadastros (Clientes / Fornecedores / Grupos)"
            ]
        )
        
        if menu_admin == "📥 Entrada de Estoque (Compras)":
            st.title("📥 Entrada de Estoque (Compras)")
            st.subheader("Registrar Entrada de Estoque")

            if "carrinho_compras" not in st.session_state:
                st.session_state.carrinho_compras = []

            produtos_opt = carregar_coluna("produtos", "produto") or ["AMEIXA IMPORTADA", "ABACATE"]
            fornecedores_opt = carregar_coluna("fornecedores", "fornecedor") or ["BAHIA"]
            grupos_opt = carregar_coluna("grupos", "grupo") or ["GERAL"]

            col_c1, col_c2 = st.columns(2)
            with col_c1:
                prod_compra = st.selectbox("Produto", produtos_opt, key="compra_prod")
                forn_compra = st.selectbox("Fornecedor", fornecedores_opt, key="compra_forn")
            with col_c2:
                grupo_compra = st.selectbox("Grupo", grupos_opt, key="compra_grupo")
                qtd_compra = st.number_input("Quantidade", min_value=0.01, step=1.0, value=1.0, key="compra_qtd")

            col_c3, col_c4 = st.columns(2)
            with col_c3:
                v_compra = st.number_input("Preço de Compra Unitário (R$)", min_value=0.0, step=0.5, value=0.0, key="compra_v_compra")
            with col_c4:
                v_venda_compra = st.number_input("Novo Preço de Venda (R$)", min_value=0.0, step=0.5, value=0.0, key="compra_v_venda")

            if st.button("➕ Adicionar à Lista de Compras", type="primary"):
                st.session_state.carrinho_compras.append({
                    "produto": prod_compra,
                    "fornecedor": forn_compra,
                    "grupo": grupo_compra,
                    "quantidade": qtd_compra,
                    "valor_compra": v_compra,
                    "valor_venda": v_venda_compra,
                    "valor_total": qtd_compra * v_compra
                })
                st.success("Item adicionado à lista de compras!")
                st.rerun()

            if st.session_state.carrinho_compras:
                st.markdown("---")
                st.subheader("📋 Itens da Compra Atual")
                df_compras_carrinho = pd.DataFrame(st.session_state.carrinho_compras)
                st.dataframe(df_compras_carrinho, use_container_width=True)

                if st.button("💾 Finalizar Entrada de Estoque", type="primary"):
                    try:
                        cursor = conn.cursor()
                        data_agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                        for item in st.session_state.carrinho_compras:
                            # 1. Registra na tabela compras
                            cursor.execute("""
                                INSERT INTO compras (produto, fornecedor, grupo, quantidade, valor_compra, valor_venda, valor_total, data)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                item['produto'], item['fornecedor'], item['grupo'],
                                item['quantidade'], item['valor_compra'], item['valor_venda'],
                                item['valor_total'], data_agora
                            ))

                            # 2. Atualiza ou insere o estoque do produto
                            cursor.execute("""
                                UPDATE produtos 
                                SET quantidade = quantidade + ?, valor_compra = ?, valor_venda = ?
                                WHERE produto = ?
                            """, (item['quantidade'], item['valor_compra'], item['valor_venda'], item['produto']))

                        conn.commit()
                        st.session_state.carrinho_compras = []
                        st.cache_data.clear()
                        st.success("✅ Entrada de estoque finalizada e produtos atualizados com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar compra: {e}")
            else:
                st.info("Nenhum item adicionado à compra ainda.")
