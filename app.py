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
            valor_recebido TEXT,
            tipo TEXT DEFAULT 'PEDIDO',
            codigo TEXT DEFAULT 'PED',
            data TEXT
        )
    """)
    cursor.execute("PRAGMA table_info(vendas)")
    colunas_vendas = [col[1] for col in cursor.fetchall()]

    if 'forma_pagamento' not in colunas_vendas:
        try:
            cursor.execute("ALTER TABLE vendas ADD COLUMN forma_pagamento TEXT")
        except:
            pass

    if 'valor_recebido' not in colunas_vendas:
        try:
            cursor.execute("ALTER TABLE vendas ADD COLUMN valor_recebido TEXT")
        except:
            pass

    if 'tipo' not in colunas_vendas:
        try:
            cursor.execute("ALTER TABLE vendas ADD COLUMN tipo TEXT DEFAULT 'PEDIDO'")
        except:
            pass

    if 'codigo' not in colunas_vendas:
        try:
            cursor.execute("ALTER TABLE vendas ADD COLUMN codigo TEXT DEFAULT 'PED'")
        except:
            pass

    if 'data' not in colunas_vendas:
        try:
            cursor.execute("ALTER TABLE vendas ADD COLUMN data TEXT")
        except:
            pass
            
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE,
            fornecedor TEXT,
            grupo TEXT,
            valor_compra REAL,
            valor_venda REAL,
            estoque_atual REAL
        )
    """)
    cursor.execute("PRAGMA table_info(produtos)")
    colunas_produtos = [col[1] for col in cursor.fetchall()]

    for col_nome, col_tipo in [('fornecedor', 'TEXT'), ('grupo', 'TEXT'), ('valor_compra', 'REAL'), ('valor_venda', 'REAL'), ('estoque_atual', 'REAL')]:
        if col_nome not in colunas_produtos:
            try:
                cursor.execute(f"ALTER TABLE produtos ADD COLUMN {col_nome} {col_tipo}")
            except:
                pass
            
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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fornecedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fornecedor TEXT UNIQUE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS grupos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grupo TEXT UNIQUE
        )
    """)

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
    conn.commit()

adequar_banco_e_migrar()

def carregar_dados(query):
    try:
        return pd.read_sql_query(query, conn)
    except Exception:
        return pd.DataFrame()

def carregar_coluna(tabela, coluna):
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({tabela})")
    cols = [col[1] for col in cursor.fetchall()]
    col_alvo = coluna if coluna in cols else (cols[1] if len(cols) > 1 else coluna)
    
    df = carregar_dados(f"SELECT DISTINCT TRIM({col_alvo}) as {col_alvo} FROM {tabela} WHERE {col_alvo} IS NOT NULL AND {col_alvo} != ''")
    if not df.empty:
        return df[col_alvo].tolist()
    return []

def salvar_cliente_completo(nome, telefone, doc, endereco, cidade):
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO clientes (nome, telefone, doc, endereco, cidade) VALUES (?, ?, ?, ?, ?)",
                       (nome.strip(), telefone, doc, endereco, cidade))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def salvar_produto_completo(nome, fornecedor, grupo, preco_custo, preco_venda, estoque_inicial):
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO produtos (nome, fornecedor, grupo, valor_compra, valor_venda, estoque_atual) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (nome.strip(), fornecedor, grupo, preco_custo, preco_venda, estoque_inicial))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        cursor.execute("""
            UPDATE produtos 
            SET fornecedor = ?, grupo = ?, valor_compra = ?, valor_venda = ?, estoque_atual = ?
            WHERE TRIM(nome) = TRIM(?)
        """, (fornecedor, grupo, preco_custo, preco_venda, estoque_inicial, nome.strip()))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Erro ao salvar produto: {e}")
        return False

def salvar_simples(tabela, coluna, valor):
    cursor = conn.cursor()
    try:
        cursor.execute(f"INSERT INTO {tabela} ({coluna}) VALUES (?)", (valor.strip(),))
        conn.commit()
        return True
    except:
        return False

def salvar_pedido_ou_venda(cliente, produto, fornecedor, grupo, quantidade, valor_venda, forma_pagamento="", valor_recebido=0.0, tipo="PEDIDO"):
    cursor = conn.cursor()
    valor_total = quantidade * valor_venda
    data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cod_status = "VEN" if tipo.upper() in ["VENDA", "VENDAS", "VEN"] else "PED"
    
    cursor.execute("""
        INSERT INTO vendas (cliente, produto, fornecedor, grupo, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, tipo, codigo, data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (cliente.strip(), produto, fornecedor, grupo, quantidade, valor_venda, valor_total, forma_pagamento, str(valor_recebido), tipo, cod_status, data_atual))
    conn.commit()

def baixar_debito_cliente(cliente_nome, valor_haver, forma_pagamento="Dinheiro"):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, valor_total, valor_recebido 
        FROM vendas 
        WHERE TRIM(cliente) = TRIM(?)
    """, (cliente_nome,))
    registros = cursor.fetchall()
    
    saldo_haver = float(valor_haver)
    
    for reg in registros:
        reg_id, v_total, v_rec_atual = reg
        v_rec_atual = float(v_rec_atual) if v_rec_atual else 0.0
        pendente_linha = v_total - v_rec_atual
        
        if pendente_linha > 0 and saldo_haver > 0:
            if saldo_haver >= pendente_linha:
                novo_recebido = v_total
                saldo_haver -= pendente_linha
            else:
                novo_recebido = v_rec_atual + saldo_haver
                saldo_haver = 0.0
            
            cursor.execute("""
                UPDATE vendas 
                SET valor_recebido = ?, forma_pagamento = ? 
                WHERE id = ?
            """, (str(novo_recebido), forma_pagamento, reg_id))
            
    conn.commit()

def registrar_compra(produto, fornecedor, grupo, quantidade, valor_custo):
    cursor = conn.cursor()
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
def gerar_pdf_tabela_pedidos(df_dados, cliente_nome="Geral", d_inicio=None, d_fim=None, titulo_custom=None):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=20, leftMargin=20, topMargin=15, bottomMargin=15)
    elements = []
    styles = getSampleStyleSheet()
    
    style_empresa = ParagraphStyle('EmpresaStyle', parent=styles['Heading1'], fontName='Helvetica-BoldOblique', fontSize=18, leading=20, alignment=1, textColor=colors.black)
    style_sub = ParagraphStyle('SubStyle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, leading=10, alignment=1)
    style_titulo_relatorio = ParagraphStyle('RelatorioStyle', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=13, leading=16, alignment=1, textColor=colors.HexColor('#1E50A2'))
    style_data = ParagraphStyle('DataStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=10, alignment=1, textColor=colors.HexColor('#333333'))

    elements.append(Paragraph("REY DA CEBOLA", style_empresa))
    elements.append(Paragraph("CNPJ: 194.174.39/000-42 INSC.EST.: 12.426725-4", style_sub))
    elements.append(Paragraph("CONTATO: (99) 98814-9722 OU (99) 98414-3943", style_sub))
    elements.append(Spacer(1, 4))
    
    titulo_doc = titulo_custom if titulo_custom else f"Relatório de Pedidos / Orçamentos - {cliente_nome}"
    elements.append(Paragraph(titulo_doc, style_titulo_relatorio))
    periodo_str = f"Período: {d_inicio.strftime('%d/%m/%Y')} até {d_fim.strftime('%d/%m/%Y')}" if d_inicio and d_fim else f"Data de Emissão: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    elements.append(Paragraph(periodo_str, style_data))
    elements.append(Spacer(1, 6))
    
    if not df_dados.empty:
        df_resumo = df_dados.groupby('produto').agg({
            'quantidade': 'sum',
            'valor_venda': 'mean',
            'valor_total': 'sum'
        }).reset_index()
    else:
        df_resumo = pd.DataFrame(columns=['produto', 'quantidade', 'valor_venda', 'valor_total'])

    table_data = [["Produto", "Qtd Total", "Preço Unitário (R$)", "Valor Total (R$)"]]
    valor_total_geral = 0.0
    for _, row in df_resumo.iterrows():
        prod = str(row['produto'])
        qtd = f"{row['quantidade']:.2f}"
        v_unit = f"R$ {row['valor_venda']:,.2f}"
        v_tot = row['valor_total']
        valor_total_geral += v_tot
        table_data.append([prod, qtd, v_unit, f"R$ {v_tot:,.2f}"])
        
    table_data.append(["VALOR TOTAL GERAL", "", "", f"R$ {valor_total_geral:,.2f}"])
    
    t = Table(table_data, colWidths=[240, 90, 130, 130])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2A65F0')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#CCCCCC')),
        ('SPAN', (0, -1), (2, -1)),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#1B2A4A')),
        ('TEXTCOLOR', (0, -1), (-1, -1), colors.white),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, -1), (-1, -1), 10),
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
            
            df_p_cli = carregar_dados("SELECT * FROM produtos")
            if not df_p_cli.empty:
                df_p_cli.columns = [c.lower() for c in df_p_cli.columns]
                col_nome_p = 'produto' if 'produto' in df_p_cli.columns else ('nome' if 'nome' in df_p_cli.columns else df_p_cli.columns[1])
                produtos_opt = df_p_cli[col_nome_p].dropna().astype(str).str.strip().unique().tolist()
            else:
                produtos_opt = ["AMEIXA IMPORTADA", "ABACATE", "CEBOLA CAIXA 1"]
                df_p_cli = pd.DataFrame()

            fornecedores_opt = carregar_coluna("fornecedores", "fornecedor") or ["BAHIA"]
            grupos_opt = carregar_coluna("grupos", "grupo") or ["GERAL"]
            
            prod = st.selectbox("Selecione o Produto", produtos_opt, key="cliente_sel_produto")
            
            preco_sugerido_cli = 0.0
            forn_sugerido_cli = fornecedores_opt[0]
            grupo_sugerido_cli = grupos_opt[0]

            if not df_p_cli.empty:
                df_p_cli['_nome_limpo'] = df_p_cli[col_nome_p].astype(str).str.strip().str.upper()
                target_nome = str(prod).strip().upper()
                df_filtrado_cli = df_p_cli[df_p_cli['_nome_limpo'] == target_nome]
                
                if not df_filtrado_cli.empty:
                    row_cli = df_filtrado_cli.iloc[0]
                    for col_v in ['valor_compra', 'preco_compra', 'custo', 'valor_venda', 'preco_venda', 'venda']:
                        if col_v in df_p_cli.columns:
                            try:
                                val_aux = float(row_cli[col_v])
                                if val_aux > 0:
                                    preco_sugerido_cli = val_aux
                                    break
                            except:
                                pass

                    if 'fornecedor' in df_p_cli.columns and pd.notna(row_cli['fornecedor']):
                        forn_sugerido_cli = str(row_cli['fornecedor'])
                    if 'grupo' in df_p_cli.columns and pd.notna(row_cli['grupo']):
                        grupo_sugerido_cli = str(row_cli['grupo'])

            with st.form("form_novo_pedido_cliente"):
                idx_f_cli = fornecedores_opt.index(forn_sugerido_cli) if fornecedores_opt and forn_sugerido_cli in fornecedores_opt else 0
                fornec = st.selectbox("Selecione o Fornecedor", fornecedores_opt, index=idx_f_cli)
                
                idx_g_cli = grupos_opt.index(grupo_sugerido_cli) if grupos_opt and grupo_sugerido_cli in grupos_opt else 0
                grupo = st.selectbox("Selecione o Grupo", grupos_opt, index=idx_g_cli)
                
                qtd = st.number_input("Quantidade", min_value=0.1, step=0.5, value=1.0)
                v_unit = st.number_input("Preço Unitário (R$)", min_value=0.0, step=1.0, value=float(preco_sugerido_cli))
                
                if st.form_submit_button("Confirmar Pedido"):
                    salvar_pedido_ou_venda(st.session_state.cliente_autenticado, prod, fornec, grupo, qtd, v_unit, tipo="PEDIDO")
                    st.success("Pedido registrado com sucesso!")
                    st.rerun()

        with aba_historico:
            st.subheader(f"Meus Pedidos e Orçamentos ({st.session_state.cliente_autenticado})")
            
            df_cli_pedidos = carregar_dados("SELECT * FROM vendas")
            
            if not df_cli_pedidos.empty and 'cliente' in df_cli_pedidos.columns:
                nome_pesq = str(st.session_state.cliente_autenticado).strip().lower()
                df_cli_pedidos = df_cli_pedidos[df_cli_pedidos['cliente'].astype(str).str.strip().str.lower().str.contains(nome_pesq, na=False)]
            
            if not df_cli_pedidos.empty:
                col_codigo = next((c for c in df_cli_pedidos.columns if 'codigo' in c.lower()), 'codigo')
                codigos = df_cli_pedidos[col_codigo].dropna().unique() if col_codigo in df_cli_pedidos.columns else []
                
                for cod in codigos:
                    df_item_venda = df_cli_pedidos[df_cli_pedidos[col_codigo] == cod]
                    if not df_item_venda.empty:
                        data_venda = str(df_item_venda['data'].iloc[0]) if 'data' in df_item_venda.columns else ""
                        col_t_item = next((c for c in df_item_venda.columns if "total" in c.lower()), 'valor_total')
                        val_total = pd.to_numeric(df_item_venda[col_t_item], errors='coerce').sum() if col_t_item in df_item_venda.columns else 0.0
                        
                        with st.expander(f"🛒 Pedido ID: {cod} | Data: {data_venda} | Total: R$ {val_total:,.2f}"):
                            cols_desejadas = ['id', 'produto', 'fornecedor', 'quantidade', 'valor_total', 'grupo']
                            cols_existentes = [c for c in cols_desejadas if c in df_item_venda.columns]
                            st.dataframe(df_item_venda[cols_existentes], use_container_width=True)
                
                st.markdown("---")
                st.markdown(f"### 📄 Relatório do Cliente ({st.session_state.cliente_autenticado})")
                try:
                    pdf_bytes = gerar_pdf_tabela_pedidos(df_cli_pedidos, st.session_state.cliente_autenticado)
                    st.download_button(
                        label=f"📥 Baixar Relatório em PDF - {st.session_state.cliente_autenticado}",
                        data=pdf_bytes,
                        file_name=f"Relatorio_Pedidos_{st.session_state.cliente_autenticado}.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                        key="btn_baixar_pdf_cliente"
                    )
                except Exception as e:
                    st.error(f"Erro ao gerar o PDF: {e}")
            else:
                st.info(f"Nenhum pedido encontrado para '{st.session_state.cliente_autenticado}'.")

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
        
        # --- LÓGICA: PDV — FRENTE DE CAIXA ---
        if menu_admin == "🛒 PDV — Frente de Caixa":
            st.title("🛒 PDV — Frente de Caixa (Múltiplos Produtos)")
            
            df_caixa_aberto = carregar_dados("SELECT * FROM caixa_sessoes WHERE status = 'ABERTO'")
            if df_caixa_aberto.empty:
                st.warning("⚠️ Atenção: Não há nenhum caixa aberto no momento. Vá em '🔓 Abertura e Fechamento de Caixa' para abrir o caixa.")
            
            clientes_opt = carregar_coluna("clientes", "nome") or ["Carlos Alberto"]
            fornecedores_opt = carregar_coluna("fornecedores", "fornecedor") or ["BAHIA"]
            grupos_opt = carregar_coluna("grupos", "grupo") or ["GERAL"]

            df_p = carregar_dados("SELECT * FROM produtos")
            if not df_p.empty:
                df_p.columns = [c.lower() for c in df_p.columns]
                col_nome_p = 'produto' if 'produto' in df_p.columns else ('nome' if 'nome' in df_p.columns else df_p.columns[1])
                produtos_opt = df_p[col_nome_p].dropna().astype(str).str.strip().unique().tolist()
            else:
                produtos_opt = ["AMEIXA IMPORTADA", "ABACATE"]

            cliente_pdv = st.selectbox("Selecione o Cliente do Atendimento", clientes_opt)

            st.markdown("#### + Adicionar Item ao Carrinho")
            prod_item = st.selectbox("Produto", produtos_opt, key="pdv_select_produto")

            preco_sugerido = 0.0
            forn_sugerido = fornecedores_opt[0]
            grupo_sugerido = grupos_opt[0]

            if not df_p.empty:
                df_p['_nome_limpo'] = df_p[col_nome_p].astype(str).str.strip().str.upper()
                target_nome = str(prod_item).strip().upper()
                df_filtrado_p = df_p[df_p['_nome_limpo'] == target_nome]
                
                if not df_filtrado_p.empty:
                    row_p = df_filtrado_p.iloc[0]
                    for col_v in ['valor_venda', 'preco_venda', 'venda']:
                        if col_v in df_p.columns:
                            try:
                                val_aux = float(row_p[col_v])
                                if val_aux > 0:
                                    preco_sugerido = val_aux
                                    break
                            except:
                                pass

                    if 'fornecedor' in df_p.columns and pd.notna(row_p['fornecedor']):
                        forn_sugerido = str(row_p['fornecedor'])
                    if 'grupo' in df_p.columns and pd.notna(row_p['grupo']):
                        grupo_sugerido = str(row_p['grupo'])

            col_s1, col_s2 = st.columns(2)
            with col_s1:
                idx_f = fornecedores_opt.index(forn_sugerido) if fornecedores_opt and forn_sugerido in fornecedores_opt else 0
                fornec_item = st.selectbox("Fornecedor", fornecedores_opt, index=idx_f, key="pdv_forn_input")
                idx_g = grupos_opt.index(grupo_sugerido) if grupo_sugerido in grupos_opt else 0
                grupo_item = st.selectbox("Grupo", grupos_opt, index=idx_g, key="pdv_grupo_input")
            
            with col_s2:
                qtd_item = st.number_input("Quantidade", min_value=0.1, step=1.0, value=1.0, key="pdv_qtd")
                v_unit_item = st.number_input("Preço de Venda (R$)", min_value=0.0, step=1.0, value=float(preco_sugerido), key=f"vunit_{prod_item}")
            
            valor_total_item = qtd_item * v_unit_item
            st.metric("Valor Total do Item", f"R$ {valor_total_item:.2f}")
            
            if st.button("➕ Incluir Produto no Carrinho", type="primary"):
                st.session_state.carrinho_pdv.append({
                    "produto": prod_item,
                    "fornecedor": fornec_item,
                    "grupo": grupo_item,
                    "quantidade": qtd_item,
                    "valor_venda": v_unit_item,
                    "valor_total": valor_total_item
                })
                st.success(f"Item '{prod_item}' adicionado ao carrinho!")
                st.rerun()

            st.markdown("---")
            st.subheader("🛒 Itens Atuais no Carrinho")
            if len(st.session_state.carrinho_pdv) > 0:
                df_carrinho = pd.DataFrame(st.session_state.carrinho_pdv)
                st.dataframe(df_carrinho, use_container_width=True)
                total_geral_carrinho = df_carrinho['valor_total'].sum()
            else:
                total_geral_carrinho = 0.0

            if st.button("🗑️ Limpar Carrinho"):
                st.session_state.carrinho_pdv = []
                st.rerun()

            st.markdown("---")        
            with st.form("form_finalizar_pagamento_pdv"):
                f_pag = st.selectbox("Forma de Pagamento", ["Dinheiro", "Pix", "Cartão de Crédito à Vista", "Cartão de Débito", "Crediário / Fiado"])
                v_rec = st.number_input("Valor Recebido (R$)", min_value=0.0, step=1.0, value=float(total_geral_carrinho))
                troco = v_rec - total_geral_carrinho
                
                st.markdown("---")
                c_inf1, c_inf2 = st.columns(2)
                c_inf1.metric("Valor Total da Venda", f"R$ {total_geral_carrinho:,.2f}")
                c_inf2.metric("Troco", f"R$ {max(0.0, troco):,.2f}", delta_color="normal" if troco >= 0 else "inverse")
                
                if st.form_submit_button("Finalizar Venda no PDV"):
                    if not df_caixa_aberto.empty and len(st.session_state.carrinho_pdv) > 0:
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
                        cursor.execute("INSERT INTO caixa_movimentacoes (sessao_id, tipo, valor, descricao, data) VALUES (?, ?, ?, ?, ?)",
                            (sessao_id, "VENDA", total_geral_carrinho, f"Venda PDV - Cliente: {cliente_pdv}", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                        conn.commit()
                        
                        st.session_state.carrinho_pdv = []
                        st.success(f"Venda realizada com sucesso! Troco: R$ {max(0.0, troco):,.2f}")
                        st.rerun()
                    else:
                        st.error("Verifique se o caixa está aberto e se há itens no carrinho.")

        editor_key = f"editor_reg_{menu_admin}"
if editor_key in st.session_state:
    del st.session_state[editor_key]
    
if linhas_afetadas > 0:
    st.success(f"Preços atualizados com sucesso! ({linhas_afetadas} itens modificados)")
else:
    st.warning("Nenhum produto correspondente foi encontrado na tabela de estoque para atualizar.")

st.markdown("---")

s_d1, s_d2 = d_inicio.strftime("%Y-%m-%d"), d_fim.strftime("%Y-%m-%d")
query_filt = f"SELECT * FROM vendas WHERE substr(data, 1, 10) >= '{s_d1}' AND substr(data, 1, 10) <= '{s_d2}'"
if cliente_sel != "TODOS":
    query_filt += f" AND TRIM(cliente) = TRIM('{cliente_sel}')"

df_registros = carregar_dados(query_filt)
if not df_registros.empty:
    df_registros.insert(0, "Deletar", False)
    df_editado = st.data_editor(df_registros, key=f"editor_reg_{menu_admin}", use_container_width=True, hide_index=True)
    
    col_b1, col_b2 = st.columns([1, 3])
    with col_b1:
        btn_salvar_superior = st.button("💾 Atualizar Valores / Salvar", type="primary", key=f"btn_salvar_edicao_{menu_admin}")
    
    if btn_salvar_superior:
        cursor = conn.cursor()
        for _, row in df_editado.iterrows():
            if row["Deletar"]:
                cursor.execute("DELETE FROM vendas WHERE id = ?", (int(row["id"]),))
            else:
                v_tot = float(row["quantidade"]) * float(row["valor_venda"])
                cursor.execute("""
                    UPDATE vendas SET cliente = ?, produto = ?, fornecedor = ?, quantidade = ?, 
                        valor_venda = ?, valor_total = ?, grupo = ? WHERE id = ?
                """, (str(row["cliente"]), str(row["produto"]), str(row["fornecedor"]), 
                    float(row["quantidade"]), float(row["valor_venda"]), v_tot, str(row["grupo"]), int(row["id"])))
        conn.commit()
        st.success("Alterações e exclusões por item salvas com sucesso!")
        st.rerun()

    st.divider()
    st.subheader("⚡ Ações Rápidas por Pedido Completo")
    
    if 'data' in df_registros.columns and 'cliente' in df_registros.columns:
        df_registros['pedido_id'] = df_registros['cliente'].astype(str) + " — " + df_registros['data'].astype(str)
        pedidos_unicos = df_registros['pedido_id'].unique().tolist()
        
        col_p_sel, col_btn_conv, col_btn_exc, col_btn_pdf = st.columns([2, 1, 1, 1])
        with col_p_sel:
            pedido_escolhido = st.selectbox("Selecione o Pedido (Cliente + Data):", pedidos_unicos, key=f"sel_pedido_completo_{menu_admin}")
            df_itens_pedido = df_registros[df_registros['pedido_id'] == pedido_escolhido]

        st.dataframe(df_itens_pedido, use_container_width=True, hide_index=True)

        with col_btn_conv:
            st.write("")
            if not is_modo_pedido:
                st.empty()
            else:
                if st.button("🔄 Converter Pedido", key=f"btn_conv_inteiro_{menu_admin}", type="primary"):
                    cursor = conn.cursor()
                    for _, itm in df_itens_pedido.iterrows():
                        cursor.execute("UPDATE vendas SET tipo = 'VENDA' WHERE id = ?", (int(itm['id']),))
                    conn.commit()
                    st.success("Pedido inteiro convertido em Venda!")
                    st.rerun()

        with col_btn_exc:
            st.write("")
            if st.button("🗑️ Excluir Pedido", key=f"btn_exc_inteiro_{menu_admin}"):
                cursor = conn.cursor()
                for _, itm in df_itens_pedido.iterrows():
                    cursor.execute("DELETE FROM vendas WHERE id = ?", (int(itm['id']),))
                conn.commit()
                st.success("Pedido excluído com sucesso!")
                st.rerun()

        with col_btn_pdf:
            st.write("") 
            try:
                buffer = io.BytesIO()
                doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=15, bottomMargin=30)
                elementos = []
                estilos = getSampleStyleSheet()

                titulo_estilo = ParagraphStyle('Titulo', parent=estilos['Heading1'], fontName='Helvetica-Bold', fontSize=15, leading=16, alignment=1, textColor=colors.HexColor('#111111'), spaceAfter=2)
                subtitulo_estilo = ParagraphStyle('SubTitulo', parent=estilos['Normal'], fontName='Helvetica', fontSize=8.5, leading=10, alignment=1, textColor=colors.HexColor('#333333'), spaceAfter=1)
                
                elementos.append(Paragraph("<b>REY DA CEBOLA</b>", titulo_estilo))
                elementos.append(Paragraph("CNPJ: 194.174.39/000-42 INSC.EST.: 12.426725-4", subtitulo_estilo))
                elementos.append(Paragraph("CONTATO: (99) 98814-9722 OU (99) 98414-3943", subtitulo_estilo))
                elementos.append(Spacer(1, 4))
                
                elementos.append(Paragraph(f"<b>Relatório de Pedidos / Orçamentos</b><br/>{pedido_escolhido}", ParagraphStyle('Cab', parent=subtitulo_estilo, fontSize=10, leading=12, fontName='Helvetica-Bold', alignment=1, spaceAfter=6)))

                dados_tabela = [["Produto", "Qtd Total", "Preço Unitário (R$)", "Valor Total (R$)"]]
                total_geral = 0.0

                for _, itm in df_itens_pedido.iterrows():
                    prod = str(itm.get('produto', ''))
                    qtd = float(itm.get('quantidade', 0))
                    v_unit = float(itm.get('valor_venda', 0))
                    v_tot = qtd * v_unit
                    total_geral += v_tot
                    dados_tabela.append([prod, f"{qtd:.2f}", f"R$ {v_unit:,.2f}", f"R$ {v_tot:,.2f}"])

                dados_tabela.append(["VALOR TOTAL GERAL", "", "", f"R$ {total_geral:,.2f}"])

                t = Table(dados_tabela, colWidths=[210, 80, 110, 110])
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2b579a')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9.5),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                    ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#111111')),
                    ('TEXTCOLOR', (0, -1), (-1, -1), colors.whitesmoke),
                    ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('FONTSIZE', (0, 1), (-1, -1), 8.5),
                ]))

                elementos.append(t)
                doc.build(elementos)
                buffer.seek(0)
                pdf_bytes = buffer.getvalue()

                st.download_button(
                    label="📄 Baixar PDF",
                    data=pdf_bytes,
                    file_name=f"pedido_{pedido_escolhido.replace('—', '_').strip()}.pdf",
                    mime="application/pdf",
                    key=f"download_pdf_{menu_admin}"
                )
            except Exception as e:
                st.error(f"Erro ao gerar PDF: {e}")
else:
    st.info("Nenhum registro encontrado.")
