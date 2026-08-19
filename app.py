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

# -----------------------------------------------------------------------------
# FUNÇÕES DE REGISTRO E BANCO
# -----------------------------------------------------------------------------
def sincronizar_valores_com_estoque(tabela_alvo, tipo_preco="venda"):
    cursor = conn.cursor()
    df_produtos = carregar_dados("SELECT * FROM produtos")
    if df_produtos.empty:
        return
    
    cols_prod = df_produtos.columns.tolist()
    col_p_nome = 'nome' if 'nome' in cols_prod else cols_prod[1]
    
    if tipo_preco == "venda":
        col_p_preco = 'valor_venda' if 'valor_venda' in cols_prod else ('preco_venda' if 'preco_venda' in cols_prod else [c for c in cols_prod if 'venda' in c or 'preco' in c][-1])
    else:
        col_p_preco = 'valor_compra' if 'valor_compra' in cols_prod else ('preco_custo' if 'preco_custo' in cols_prod else [c for c in cols_prod if 'custo' in c or 'compra' in c][-1])

    df_registros = carregar_dados(f"SELECT id, produto, quantidade as qtd FROM {tabela_alvo}")
    
    for _, row in df_registros.iterrows():
        prod_nome = row['produto']
        mask = df_produtos[col_p_nome].astype(str).str.strip() == str(prod_nome).strip()
        preco_atual = df_produtos.loc[mask, col_p_preco]
        
        if not preco_atual.empty:
            p = float(preco_atual.iloc[0])
            total = p * row['qtd']
            cursor.execute(f"UPDATE {tabela_alvo} SET valor_venda = ?, valor_total = ? WHERE id = ?", (p, total, row['id']))
    
    conn.commit()

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
        cursor.execute(f"PRAGMA table_info({tabela})")
        colunas_existentes = [col[1] for col in cursor.fetchall()]
        
        if not colunas_existentes:
            cursor.execute(f"CREATE TABLE IF NOT EXISTS {tabela} (id INTEGER PRIMARY KEY AUTOINCREMENT, {coluna} TEXT UNIQUE)")
            conn.commit()
            coluna_alvo = coluna
        else:
            coluna_alvo = coluna if coluna in colunas_existentes else colunas_existentes[-1]

        cursor.execute(f"INSERT INTO {tabela} ({coluna_alvo}) VALUES (?)", (valor.strip(),))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    except Exception as e:
        st.error(f"Erro ao salvar em {tabela}: {e}")
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

def converter_pedido_completo_para_venda(cliente_nome):
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE vendas 
        SET tipo = 'VENDA', codigo = 'VEN' 
        WHERE TRIM(cliente) = TRIM(?)
    """, (cliente_nome,))
    conn.commit()
    return cursor.rowcount

def deletar_pedidos_cliente(cliente_nome, s_d1, s_d2):
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM vendas 
        WHERE TRIM(cliente) = TRIM(?) 
          AND (substr(data, 1, 10) >= ? AND substr(data, 1, 10) <= ? OR data IS NULL OR data = '')
    """, (cliente_nome, s_d1, s_d2))
    conn.commit()
    return cursor.rowcount

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
# GERADOR DE PDF COMPACTO
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

    table_data = [["Produto", "Qtd Total", "Preço Custo Médio (R$)", "Valor Total (R$)"]]
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
        ('ALIGN', (0, 1), (0, -2), 'LEFT'),
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
# 2. SESSÃO E PERFIS
# -----------------------------------------------------------------------------
if 'admin_logged' not in st.session_state:
    st.session_state.admin_logged = False

if 'cliente_autenticado' not in st.session_state:
    st.session_state.cliente_autenticado = None

if 'carrinho_pdv' not in st.session_state:
    st.session_state.carrinho_pdv = []

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
        st.info("Por favor, selecione seu nome no menu à esquerda e insira sua senha (123) para acessar seus pedidos.")
        
        lista_clientes = carregar_coluna("clientes", "nome") or carregar_coluna("vendas", "cliente") or ["Carlos Alberto"]
        cliente_nome = st.sidebar.selectbox("Identifique seu Nome/Empresa:", lista_clientes)
        senha_cliente = st.sidebar.text_input("Digite sua Senha de Cliente:", type="password")
        
        if st.sidebar.button("Acessar Meus Pedidos"):
            if senha_cliente == "123":
                st.session_state.cliente_autenticado = cliente_nome
                st.rerun()
            else:
                st.sidebar.error("Senha incorreta! (Use 123)")
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
            fornecedores_opt = carregar_coluna("fornecedores", "fornecedor") or ["BAHIA"]
            grupos_opt = carregar_coluna("grupos", "grupo") or ["GERAL"]
            
            with st.form("form_novo_pedido_cliente"):
                prod = st.selectbox("Selecione o Produto", produtos_opt)
                fornec = st.selectbox("Selecione o Fornecedor", fornecedores_opt)
                grupo = st.selectbox("Selecione o Grupo", grupos_opt)
                qtd = st.number_input("Quantidade", min_value=0.1, step=0.5, value=1.0)
                v_unit = st.number_input("Preço de Custo (R$)", min_value=0.0, step=1.0, value=100.0)
                
                if st.form_submit_button("Confirmar Pedido"):
                    salvar_pedido_ou_venda(st.session_state.cliente_autenticado, prod, fornec, grupo, qtd, v_unit, tipo="PEDIDO")
                    st.success("Pedido registrado com sucesso!")
                    st.rerun()

        with aba_historico:
            df_pedidos = carregar_dados(f"SELECT * FROM vendas WHERE TRIM(cliente) = TRIM('{st.session_state.cliente_autenticado}')")
            if not df_pedidos.empty:
                soma_total = df_pedidos['valor_total'].sum() if 'valor_total' in df_pedidos.columns else 0.0
                st.markdown(f"**Itens Registrados:** {len(df_pedidos)} | **Soma dos Valores:** R$ {soma_total:,.2f}")
                
                if st.button("🔄 Atualizar Valores com Estoque (Preço Custo)"):
                    sincronizar_valores_com_estoque("vendas", "compra")
                    st.success("Tabela atualizada com o Preço de Custo!")
                    st.rerun()

                st.markdown("---")
                cols_exibir = [c for c in ['id', 'cliente', 'produto', 'fornecedor', 'quantidade', 'valor_venda', 'valor_total', 'data'] if c in df_pedidos.columns]
                st.dataframe(df_pedidos[cols_exibir], use_container_width=True)
                pdf_cli = gerar_pdf_tabela_pedidos(df_pedidos, cliente_nome=st.session_state.cliente_autenticado)
                st.download_button(
                    label=f"Baixar Relatório de Pedidos ({st.session_state.cliente_autenticado}) em PDF",
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
                "💸 Frente de Caixa (PDV)",
                "📊 Fechamento & Financeiro",
                "📋 Pedidos / Orçamentos",
                "🛒 Registrar Venda",
                "📥 Entrada de Estoque (Compras)",
                "📦 Estoque de Produtos",
                "👥 Cadastros (Clientes / Fornecedores / Grupos)"
            ]
        )
        
        # ------------------------------------------------------------------
        # 1. FRENTE DE CAIXA (PDV INTEGRADO)
        # ------------------------------------------------------------------
        if menu_admin == "💸 Frente de Caixa (PDV)":
            st.title("💸 Frente de Caixa (PDV - Balcão)")
            st.info("Adicione produtos ao carrinho rápido, selecione a forma de pagamento e finalize para abater o estoque e registrar no financeiro automaticamente.")
            
            col_prod, col_qtd, col_add = st.columns([3, 1, 1])
            produtos_lista = carregar_coluna("produtos", "nome") or ["CEBOLA", "BATATA"]
            
            with col_prod:
                prod_sel = st.selectbox("Selecione o Produto", produtos_lista, key="pdv_prod")
            with col_qtd:
                qtd_sel = st.number_input("Qtd", min_value=0.1, step=1.0, value=1.0, key="pdv_qtd")
            with col_add:
                st.write("###")
                if st.button("➕ Adicionar ao Carrinho"):
                    df_p = carregar_dados(f"SELECT valor_venda FROM produtos WHERE TRIM(nome) = TRIM('{prod_sel}')")
                    preco = float(df_p.iloc[0, 0]) if not df_p.empty else 0.0
                    st.session_state.carrinho_pdv.append({
                        'produto': prod_sel, 
                        'quantidade': qtd_sel, 
                        'valor_unitario': preco, 
                        'valor_total': qtd_sel * preco
                    })
                    st.success(f"{prod_sel} adicionado!")
                    st.rerun()

            if st.session_state.carrinho_pdv:
                st.markdown("---")
                st.subheader("🛒 Carrinho Atual")
                df_carrinho = pd.DataFrame(st.session_state.carrinho_pdv)
                st.dataframe(df_carrinho, use_container_width=True)
                
                total_carrinho = df_carrinho['valor_total'].sum()
                st.metric("VALOR TOTAL DA VENDA", f"R$ {total_carrinho:,.2f}")
                
                clientes_opt = carregar_coluna("clientes", "nome") or ["Cliente Balcão"]
                cliente_pdv = st.selectbox("Cliente da Venda", clientes_opt, key="pdv_cliente")
                forma_pdv = st.selectbox("Forma de Pagamento", ["Dinheiro", "Pix", "Cartão de Crédito à Vista", "Cartão de Débito", "Crediário / Fiado"], key="pdv_pagamento")
                
                col_b1, col_b2 = st.columns(2)
                with col_b1:
                    if st.button("✅ FINALIZAR VENDA", type="primary"):
                        cursor = conn.cursor()
                        for item in st.session_state.carrinho_pdv:
                            # Salva como VENDA e preenche o valor recebido integralmente
                            salvar_pedido_ou_venda(
                                cliente_pdv, item['produto'], "GERAL", "GERAL", 
                                item['quantidade'], item['valor_unitario'], 
                                forma_pdv, item['valor_total'], "VENDA"
                            )
                            # Baixa imediata no estoque atual
                            cursor.execute("""
                                UPDATE produtos 
                                SET estoque_atual = COALESCE(estoque_atual, 0) - ? 
                                WHERE TRIM(nome) = TRIM(?)
                            """, (item['quantidade'], item['produto']))
                        conn.commit()
                        st.session_state.carrinho_pdv = []
                        st.success("Venda finalizada com sucesso! Estoque e financeiro atualizados.")
                        st.rerun()
                with col_b2:
                    if st.button("❌ Limpar Carrinho"):
                        st.session_state.carrinho_pdv = []
                        st.rerun()
            else:
                st.warning("O carrinho do PDV está vazio. Adicione itens acima.")

        # ------------------------------------------------------------------
        # 2. FECHAMENTO & FINANCEIRO
        # ------------------------------------------------------------------
        elif menu_admin == "📊 Fechamento & Financeiro":
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
                
                if 'valor_recebido' in df_vendas.columns:
                    valor_rec = pd.to_numeric(df_vendas['valor_recebido'], errors='coerce').sum()
                else:
                    valor_rec = 0.0
                    
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
                st.info("Nenhum registro encontrado para os filtros selecionados.")

        # ------------------------------------------------------------------
        # 3. PEDIDOS / ORÇAMENTOS & REGISTRAR VENDA
        # ------------------------------------------------------------------
        elif menu_admin in ["📋 Pedidos / Orçamentos", "🛒 Registrar Venda"]:
            is_modo_pedido = (menu_admin == "📋 Pedidos / Orçamentos")
            st.title(f"📋 {menu_admin}")
            
            if not is_modo_pedido:
                aba_cad, aba_baixa, aba_list = st.tabs(["➕ Novo Registro", "💵 Baixa de Débito / Haver", "✏️ Tabela Editável"])
            else:
                aba_cad, aba_list = st.tabs(["➕ Novo Registro / Pedido", "✏️ Tabela Editável"])
                aba_baixa = None
            
            with aba_cad:
                clientes_opt = carregar_coluna("clientes", "nome") or ["Carlos Alberto"]
                produtos_opt = carregar_coluna("produtos", "nome") or ["AMEIXA IMPORTADA", "ABACATE"]
                fornecedores_opt = carregar_coluna("fornecedores", "fornecedor") or ["BAHIA"]
                grupos_opt = carregar_coluna("grupos", "grupo") or ["GERAL"]
                
                tipo_registro = "PEDIDO" if is_modo_pedido else "VENDA"
                
                with st.form("form_admin_pedido"):
                    col_a, col_b = st.columns(2)
                    with col_a:
                        cli = st.selectbox("Selecione o Cliente", clientes_opt)
                        prod = st.selectbox("Selecione o Produto", produtos_opt)
                        qtd = st.number_input("Quantidade", min_value=0.1, step=0.5, value=1.0)
                        label_preco = "Preço Custo / Valor Compra (R$)" if is_modo_pedido else "Valor Venda (R$)"
                        v_unit = st.number_input(label_preco, min_value=0.0, step=1.0, value=100.0)
                    with col_b:
                        fornec = st.selectbox("Selecione o Fornecedor", fornecedores_opt)
                        grupo = st.selectbox("Selecione o Grupo", grupos_opt)
                        if not is_modo_pedido:
                            f_pag = st.selectbox("Forma de Pagamento", ["Dinheiro", "Pix", "Cartão de Crédito à Vista", "Cartão de Débito", "Crediário / Fiado"])
                            v_rec = st.number_input("Valor Recebido (R$)", min_value=0.0, step=1.0, value=v_unit * qtd)
                        else:
                            f_pag = ""
                            v_rec = 0.0
                    
                    if st.form_submit_button(f"Salvar como {tipo_registro}"):
                        salvar_pedido_ou_venda(cli, prod, fornec, grupo, qtd, v_unit, f_pag, v_rec, tipo=tipo_registro)
                        st.success(f"{tipo_registro} gravado com sucesso!")
                        st.rerun()

            if aba_baixa is not None:
                with aba_baixa:
                    st.subheader("💵 Baixa de Débitos & Lançamento de Haver")
                    clientes_com_divida = carregar_coluna("vendas", "cliente") or []
                    if clientes_com_divida:
                        cliente_baixa = st.selectbox("Selecione o Cliente para Baixa:", clientes_com_divida, key="sel_cli_baixa")
                        
                        df_cli_vendas = carregar_dados(f"SELECT * FROM vendas WHERE TRIM(cliente) = TRIM('{cliente_baixa}')")
                        if not df_cli_vendas.empty:
                            tot_vendas = df_cli_vendas['valor_total'].sum()
                            df_cli_vendas['v_rec_num'] = pd.to_numeric(df_cli_vendas['valor_recebido'], errors='coerce').fillna(0.0)
                            tot_recebido = df_cli_vendas['v_rec_num'].sum()
                            total_pendente = tot_vendas - tot_recebido
                            
                            col_m1, col_m2, col_m3 = st.columns(3)
                            col_m1.metric("Total de Compras", f"R$ {tot_vendas:,.2f}")
                            col_m2.metric("Total Já Pago", f"R$ {tot_recebido:,.2f}")
                            col_m3.metric("Saldo Devedor Restante", f"R$ {total_pendente:,.2f}", delta_color="inverse")
                            
                            st.markdown("---")
                            with st.form("form_lancar_haver"):
                                col_h1, col_h2 = st.columns(2)
                                with col_h1:
                                    valor_haver = st.number_input("Valor do Haver / Pagamento (R$)", min_value=0.0, step=1.0, value=0.0)
                                with col_h2:
                                    forma_pgto_baixa = st.selectbox("Forma de Pagamento", ["Dinheiro", "Pix", "Cartão de Crédito à Vista", "Cartão de Débito"])
                                
                                if st.form_submit_button("Aplicar Haver / Dar Baixa no Débito"):
                                    if valor_haver > 0:
                                        baixar_debito_cliente(cliente_baixa, valor_haver, forma_pagamento=forma_pgto_baixa)
                                        st.success(f"Haver de R$ {valor_haver:,.2f} aplicado para {cliente_baixa}!")
                                        st.rerun()
                                    else:
                                        st.warning("Insira um valor maior que zero.")
                                        
                            st.markdown("#### Histórico de Vendas/Tickets do Cliente")
                            df_tickets_agrupados = carregar_dados(f"""
                                SELECT MIN(id) as id, cliente, data 
                                FROM vendas 
                                WHERE TRIM(cliente) = TRIM('{cliente_baixa}') 
                                GROUP BY data, cliente 
                                ORDER BY data DESC
                            """)
                            cols_ver = [c for c in ['id', 'cliente', 'data'] if c in df_tickets_agrupados.columns]
                            
                            event_tabela = st.dataframe(
                                df_tickets_agrupados[cols_ver], 
                                use_container_width=True,
                                selection_mode="single-row",
                                on_select="rerun"
                            )
                            
                            st.markdown("---")
                            st.subheader("📦 Produtos Relacionados a esta Venda")
                            try:
                                selected_rows = event_tabela.selection.rows
                                if selected_rows:
                                    idx_sel = selected_rows[0]
                                    linha_escolhida = df_tickets_agrupados.iloc[idx_sel]
                                    id_venda_sel = linha_escolhida.get('id', None)
                                    data_venda_sel = str(linha_escolhida.get('data', ''))[:19]
                                    
                                    df_ticket_rel = carregar_dados(f"SELECT id, produto, quantidade, valor_venda, valor_total, forma_pagamento, data FROM vendas WHERE TRIM(cliente) = TRIM('{cliente_baixa}') AND data = '{data_venda_sel}'")
                                    st.dataframe(df_ticket_rel, use_container_width=True)
                                else:
                                    st.caption("👆 Clique em uma linha acima para carregar os produtos do ticket.")
                            except Exception:
                                st.caption("👆 Selecione uma linha na tabela acima.")
                        else:
                            st.warning("Este cliente não possui registros.")

            with aba_list:
                st.subheader("🔍 Edição Direta & Gestão por Cliente")
                col_f1, col_f2, col_f3 = st.columns(3)
                with col_f1:
                    clientes_filtro = ["TODOS"] + (carregar_coluna("clientes", "nome") or carregar_coluna("vendas", "cliente"))
                    cliente_sel = st.selectbox("Filtrar por Cliente:", clientes_filtro)
                with col_f2:
                    d_inicio = st.date_input("Data Inicial do Filtro", value=date(2025, 1, 1), key="f_d1")
                with col_f3:
                    d_fim = st.date_input("Data Final do Filtro", value=date.today(), key="f_d2")
                    
                s_d1 = d_inicio.strftime("%Y-%m-%d")
                s_d2 = d_fim.strftime("%Y-%m-%d")

                query_filt = f"SELECT * FROM vendas WHERE substr(data, 1, 10) >= '{s_d1}' AND substr(data, 1, 10) <= '{s_d2}'"
                if cliente_sel != "TODOS":
                    query_filt += f" AND TRIM(cliente) = TRIM('{cliente_sel}')"
                    nome_relatorio = cliente_sel
                else:
                    nome_relatorio = "Geral"

                df_registros = carregar_dados(query_filt)
                
                if not df_registros.empty:
                    df_registros.insert(0, "Deletar", False)
                    if 'valor_recebido' in df_registros.columns:
                        df_registros['valor_recebido'] = pd.to_numeric(df_registros['valor_recebido'], errors='coerce').fillna(0.0)
                    
                    config_cols = {
                        "Deletar": st.column_config.CheckboxColumn("Deletar", help="Marque para excluir"),
                        "id": st.column_config.NumberColumn("ID", disabled=True),
                        "cliente": st.column_config.TextColumn("Cliente"),
                        "produto": st.column_config.TextColumn("Produto"),
                        "quantidade": st.column_config.NumberColumn("Qtd", min_value=0.0, format="%.2f"),
                        "valor_total": st.column_config.NumberColumn("Valor Total", disabled=True, format="R$ %.2f"),
                        "data": st.column_config.TextColumn("Data", disabled=True),
                    }
                    
                    if is_modo_pedido:
                        config_cols["valor_venda"] = st.column_config.NumberColumn("Preço Custo", min_value=0.0, format="R$ %.2f")
                        for col_ocultar in ["forma_pagamento", "valor_recebido"]:
                            if col_ocultar in df_registros.columns:
                                df_registros = df_registros.drop(columns=[col_ocultar])
                    else:
                        config_cols["valor_venda"] = st.column_config.NumberColumn("Valor Venda", min_value=0.0, format="R$ %.2f")
                        config_cols["forma_pagamento"] = st.column_config.SelectboxColumn("Forma Pagamento", options=["Dinheiro", "Pix", "Cartão de Crédito à Vista", "Cartão de Débito", "Crediário / Fiado"])
                        config_cols["valor_recebido"] = st.column_config.NumberColumn("Valor Recebido", min_value=0.0, format="R$ %.2f")

                    df_editado = st.data_editor(df_registros, key=f"editor_{menu_admin}", use_container_width=True, hide_index=True, column_config=config_cols)
                    
                    if st.button("💾 Salvar Alterações na Tabela", type="primary"):
                        cursor = conn.cursor()
                        for _, row in df_editado.iterrows():
                            if not row["Deletar"]:
                                v_tot = float(row["quantidade"]) * float(row["valor_venda"])
                                f_pag = str(row["forma_pagamento"]) if "forma_pagamento" in row else ""
                                v_rec = float(row["valor_recebido"]) if "valor_recebido" in row else 0.0
                                
                                cursor.execute("""
                                    UPDATE vendas 
                                    SET cliente = ?, produto = ?, fornecedor = ?, quantidade = ?, 
                                        valor_venda = ?, valor_total = ?, forma_pagamento = ?, valor_recebido = ?
                                    WHERE id = ?
                                """, (
                                    str(row["cliente"]).strip(), str(row["produto"]), str(row["fornecedor"]),
                                    float(row["quantidade"]), float(row["valor_venda"]), v_tot,
                                    f_pag, str(v_rec), int(row["id"])
                                ))
                        conn.commit()
                        st.success("Alterações salvas com sucesso!")
                        st.rerun()

                    st.markdown("---")
                    pdf_gerado = gerar_pdf_tabela_pedidos(df_registros, cliente_nome=nome_relatorio, d_inicio=d_inicio, d_fim=d_fim)
                    st.download_button(
                        label=f"📥 Baixar Relatório - {nome_relatorio} (PDF)",
                        data=pdf_gerado,
                        file_name=f"Relatorio_{nome_relatorio}.pdf",
                        mime="application/pdf"
                    )
                else:
                    st.info("Nenhum registro encontrado.")

        # ------------------------------------------------------------------
        # 4. ENTRADA DE ESTOQUE (COMPRAS)
        # ------------------------------------------------------------------
        elif menu_admin == "📥 Entrada de Estoque (Compras)":
            st.title("📥 Entrada de Estoque (Compras)")
            aba_compra, aba_hist = st.tabs(["📦 Dar Entrada", "📋 Histórico"])
            
            produtos_opt = carregar_coluna("produtos", "nome") or ["AMEIXA"]
            fornecedores_opt = carregar_coluna("fornecedores", "fornecedor") or ["BAHIA"]
            grupos_opt = carregar_coluna("grupos", "grupo") or ["GERAL"]
            
            with aba_compra:
                with st.form("form_entrada"):
                    col1, col2 = st.columns(2)
                    with col1:
                        prod_c = st.selectbox("Produto", produtos_opt)
                        forn_c = st.selectbox("Fornecedor", fornecedores_opt)
                        qtd_c = st.number_input("Quantidade", min_value=0.0, format="%.2f")
                    with col2:
                        grup_c = st.selectbox("Grupo", grupos_opt)
                        custo_c = st.number_input("Preço Custo Unitário (R$)", min_value=0.0, format="%.2f")
                    
                    if st.form_submit_button("Registrar Entrada"):
                        registrar_compra(prod_c, forn_c, grup_c, qtd_c, custo_c)
                        cursor = conn.cursor()
                        cursor.execute("UPDATE produtos SET estoque_atual = COALESCE(estoque_atual, 0) + ? WHERE TRIM(nome) = TRIM(?)", (qtd_c, prod_c))
                        conn.commit()
                        st.success("Estoque atualizado com sucesso!")
                        st.rerun()
            with aba_hist:
                st.dataframe(carregar_dados("SELECT * FROM compras"), use_container_width=True)

        # ------------------------------------------------------------------
        # 5. ESTOQUE DE PRODUTOS
        # ------------------------------------------------------------------
        elif menu_admin == "📦 Estoque de Produtos":
            st.title("📦 Estoque de Produtos e Preços")
            df_prods = carregar_dados("SELECT * FROM produtos")
            if not df_prods.empty:
                st.dataframe(df_prods, use_container_width=True)
            else:
                st.info("Nenhum produto cadastrado.")

        # ------------------------------------------------------------------
        # 6. CADASTROS
        # ------------------------------------------------------------------
        elif menu_admin == "👥 Cadastros (Clientes / Fornecedores / Grupos)":
            st.title("👥 Cadastros Gerais")
            tab_cli, tab_prod, tab_forn, tab_grup = st.tabs(["👥 Clientes", "📦 Produtos", "🏢 Fornecedores", "🏷️ Grupos"])
            
            with tab_cli:
                with st.form("form_cli"):
                    c1, c2 = st.columns(2)
                    with c1:
                        nome_c = st.text_input("Nome")
                        tel_c = st.text_input("Telefone")
                    with c2:
                        doc_c = st.text_input("CPF/CNPJ")
                        end_c = st.text_input("Endereço")
                        cid_c = st.text_input("Cidade")
                    if st.form_submit_button("Salvar Cliente"):
                        if nome_c.strip() and salvar_cliente_completo(nome_c.strip(), tel_c, doc_c, end_c, cid_c):
                            st.success("Cliente salvo!")
                            st.rerun()
                st.dataframe(carregar_dados("SELECT * FROM clientes"), use_container_width=True)

            with tab_prod:
                grupos_opt = carregar_coluna("grupos", "grupo") or ["GERAL"]
                fornecedores_opt = carregar_coluna("fornecedores", "fornecedor") or ["BAHIA"]
                with st.form("form_prod"):
                    c1, c2 = st.columns(2)
                    with c1:
                        p_nome = st.text_input("Nome do Produto")
                        p_forn = st.selectbox("Fornecedor", fornecedores_opt)
                        p_grup = st.selectbox("Grupo", grupos_opt)
                    with c2:
                        p_cust = st.number_input("Custo (R$)", value=10.0)
                        p_vend = st.number_input("Venda (R$)", value=20.0)
                        p_estoq = st.number_input("Estoque Inicial", value=0.0)
                    if st.form_submit_button("Salvar Produto"):
                        if p_nome.strip() and salvar_produto_completo(p_nome.strip(), p_forn, p_grup, p_cust, p_vend, p_estoq):
                            st.success("Produto salvo!")
                            st.rerun()
                st.dataframe(carregar_dados("SELECT * FROM produtos"), use_container_width=True)

            with tab_forn:
                with st.form("form_forn"):
                    f_nome = st.text_input("Fornecedor")
                    if st.form_submit_button("Salvar"):
                        if f_nome.strip() and salvar_simples("fornecedores", "fornecedor", f_nome.strip()):
                            st.success("Fornecedor salvo!")
                            st.rerun()
                st.dataframe(carregar_dados("SELECT * FROM fornecedores"), use_container_width=True)

            with tab_grup:
                with st.form("form_grup"):
                    g_nome = st.text_input("Grupo")
                    if st.form_submit_button("Salvar"):
                        if g_nome.strip() and salvar_simples("grupos", "grupo", g_nome.strip()):
                            st.success("Grupo salvo!")
                            st.rerun()
                st.dataframe(carregar_dados("SELECT * FROM grupos"), use_container_width=True)
