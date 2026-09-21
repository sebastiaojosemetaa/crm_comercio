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
    
    # Preenche valores nulos em colunas de texto
    if 'forma_pagamento' in df.columns:
        df['forma_pagamento'] = df['forma_pagamento'].fillna('-').replace({'None': '-', '': '-'})
    
    # Garante conversão numérica e substitui None/NaN por 0.0
    for col in ['quantidade', 'valor_venda', 'valor_total', 'valor_recebido', 'troco', 'restante']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
            
    # Corrige o valor 'restante' caso tenha sido gravado o total do pedido em cada linha do item
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

# Restante do código da aplicação...
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

        # 1. Tabela de Clientes
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
        # Garante a existência de todas as colunas na tabela vendas
        for col_nome, col_tipo in [
            ("forma_pagamento", "TEXT"),
            ("valor_recebido", "REAL"),
            ("troco", "REAL"),
            ("restante", "REAL"),
            ("status", "TEXT"),
            ("tipo", "TEXT"),
            ("fornecedor", "TEXT"),
            ("grupo", "TEXT"),
            ("codigo", "TEXT"),
            ("codigo_venda", "TEXT")
        ]:
            try:
                cursor.execute(f"ALTER TABLE vendas ADD COLUMN {col_nome} {col_tipo};")
                conn.commit()
            except:
                pass
                # Garante a criação da tabela caixa_movimentacoes e colunas necessárias
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
    
        for col_nome, col_tipo in [
            ("sessao_id", "INTEGER"),
            ("tipo", "TEXT"),
            ("valor", "REAL"),
            ("descricao", "TEXT"),
            ("data", "TEXT")
        ]:
            try:
                cursor.execute(f"ALTER TABLE caixa_movimentacoes ADD COLUMN {col_nome} {col_tipo};")
                conn.commit()
            except:
                pass
# Garante a criação da tabela caixa_sessoes e colunas necessárias
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
        for col in ["data_abertura", "data_fechamento", "saldo_inicial", "saldo_final", "status"]:
            try:
                cursor.execute(f"ALTER TABLE caixa_sessoes ADD COLUMN {col} TEXT")
            except Exception:
                pass
        # Adiciona colunas faltantes se for banco antigo
        for col in ["cliente", "nome", "cpf", "doc", "endereco", "email", "fone", "telefone", "cidade"]:
            try:
                cursor.execute(f"ALTER TABLE clientes ADD COLUMN {col} TEXT")
            except Exception:
                pass

        # 🔄 CORREÇÃO/SINCRONIZAÇÃO: Copia 'cliente' para 'nome' e vice-versa se estiver vazio
        cursor.execute("UPDATE clientes SET nome = cliente WHERE (nome IS NULL OR nome = '') AND (cliente IS NOT NULL AND cliente != '')")
        cursor.execute("UPDATE clientes SET cliente = nome WHERE (cliente IS NULL OR cliente = '') AND (nome IS NOT NULL AND nome != '')")
    # Garante que a coluna 'status' existe na tabela vendas
        try:
            cursor.execute("ALTER TABLE vendas ADD COLUMN status TEXT")
        except Exception:
            pass
        conn.commit()
    except Exception as e:
        print(f"Aviso de migração de clientes: {e}")

# Executa a migração/sincronização
adequar_banco_e_migrar()
# --- FUNÇÃO DE LIMPEZA E SANITIÇÃO DO BANCO DE DADOS ---
def executar_limpeza_banco():
    """Aplica correções nos registros antigos salvos no banco SQLite."""
    try:
        cursor = conn.cursor()
        
        # 0. Apaga especificamente os registros duplicados de teste (IDs 16, 17 e 18)
        cursor.execute("DELETE FROM vendas WHERE id IN (16, 17, 18)")
        
        # 1. Substitui valores nulos/None/vazios por padrão seguro
        cursor.execute("UPDATE vendas SET forma_pagamento = '-' WHERE forma_pagamento IS NULL OR forma_pagamento = 'None' OR forma_pagamento = ''")
        cursor.execute("UPDATE vendas SET valor_recebido = 0.0 WHERE valor_recebido IS NULL")
        cursor.execute("UPDATE vendas SET troco = 0.0 WHERE troco IS NULL")
        
        # 2. Reajusta o restante de registros inconsistentes antigos
        cursor.execute("UPDATE vendas SET restante = (valor_total - valor_recebido) WHERE restante IS NULL OR restante > valor_total")
        cursor.execute("UPDATE vendas SET restante = 0.0 WHERE restante < 0")
        
        conn.commit()
    except Exception as e:
        pass

# Executa a limpeza da base de dados ao iniciar
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

# --- FUNÇÃO CORRIGIDA PARA SALVAR CLIENTE ---
def salvar_cliente_completo(nome, telefone, doc, endereco, cidade):
    try:
        cursor = conn.cursor()
        
        # 1. Garante a criação da tabela 'clientes'
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente TEXT,
                cpf TEXT,
                endereco TEXT,
                email TEXT,
                fone TEXT
            )
        """)
        
        # 2. Adiciona colunas para compatibilidade se não existirem
        colunas_necessarias = ["cliente", "nome", "cpf", "doc", "endereco", "email", "fone", "telefone", "cidade"]
        for col in colunas_necessarias:
            try:
                cursor.execute(f"ALTER TABLE clientes ADD COLUMN {col} TEXT")
            except Exception:
                pass  # Coluna já existe
                
        # 3. Insere dados preenchendo ambas as colunas (cliente/nome, fone/telefone, cpf/doc)
        cursor.execute("""
            INSERT INTO clientes (cliente, nome, fone, telefone, cpf, doc, endereco, email, cidade)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (nome.strip(), nome.strip(), telefone, telefone, doc, doc, endereco, cidade, cidade))
        
        conn.commit()
        st.cache_data.clear()
        return True, "✅ Cliente cadastrado com sucesso!"
    except Exception as e:
        return False, f"Erro ao salvar cliente: {e}"

# --- FORMULÁRIO ALINHADO EM 2 COLUNAS ---

    col_cli1, col_cli2 = st.columns(2)
    
    with col_cli1:
        txt_nome_cli = st.text_input("Nome do Cliente / Razão Social", key="cli_nome_cad")
        txt_doc_cli = st.text_input("CPF / CNPJ", key="cli_doc_cad")
        txt_cidade_cli = st.text_input("Cidade / Email", key="cli_cidade_cad")
        
    with col_cli2:
        txt_tel_cli = st.text_input("Telefone / WhatsApp", key="cli_tel_cad")
        txt_end_cli = st.text_input("Endereço", key="cli_end_cad")

    btn_salvar_cli = st.form_submit_button("💾 Salvar Cliente")

    if btn_salvar_cli:
        if not txt_nome_cli.strip():
            st.warning("Por favor, informe o nome do cliente.")
        else:
            sucesso, msg = salvar_cliente_completo(
                txt_nome_cli, txt_tel_cli, txt_doc_cli, txt_end_cli, txt_cidade_cli
            )
            if sucesso:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)
def salvar_produto_completo(nome, fornecedor, grupo, preco_compra, preco_venda, estoque_inicial):
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO produtos (nome, produto, fornecedor, grupo, valor_compra, valor_venda, quantidade, estoque_atual) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (nome.strip(), nome.strip(), fornecedor, grupo, preco_compra, preco_venda, estoque_inicial, estoque_inicial))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        cursor.execute("""
            UPDATE produtos 
            SET fornecedor = ?, grupo = ?, valor_compra = ?, valor_venda = ?, quantidade = ?, estoque_atual = ?
            WHERE TRIM(nome) = TRIM(?) OR TRIM(produto) = TRIM(?)
        """, (fornecedor, grupo, preco_compra, preco_venda, estoque_inicial, estoque_inicial, nome.strip(), nome.strip()))
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
    except Exception:
        return False

def registrar_compra(produto, fornecedor, grupo, quantidade, valor_compra, valor_venda):
    cursor = conn.cursor()
    data_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    valor_total = quantidade * valor_compra
    cursor.execute("""
        INSERT INTO compras (produto, fornecedor, grupo, quantidade, valor_compra, valor_venda, valor_total, data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (produto, fornecedor, grupo, quantidade, valor_compra, valor_venda, valor_total, data_str))
    conn.commit()

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
        
        # 1. Carrega todos os clientes registados de forma segura
        df_cli_select = carregar_dados("""
            SELECT DISTINCT COALESCE(NULLIF(cliente, ''), nome) AS cliente_nome 
            FROM clientes 
            WHERE cliente_nome IS NOT NULL AND cliente_nome != '' 
            ORDER BY cliente_nome
        """)
        lista_clientes = df_cli_select['cliente_nome'].tolist() if not df_cli_select.empty else []
        
        # 2. Exibe o selectbox com a lista completa
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

        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pedidos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cliente TEXT,
                    produto TEXT,
                    quantidade REAL,
                    valor_unitario REAL,
                    valor_total REAL,
                    fornecedor TEXT,
                    grupo TEXT,
                    data TEXT,
                    status TEXT,
                    codigo_pedido TEXT
                )
            """)
            conn.commit()
        except Exception:
            pass
    
        aba_novo, aba_historico = st.tabs(["+ Criar Novo Pedido", "📋 Pedidos Registrados & Relatórios"])
    
        with aba_novo:
            st.subheader("Registrar Novo Pedido")
            
            try:
                df_p_cli = carregar_dados("SELECT * FROM produtos")
                if not df_p_cli.empty:
                    df_p_cli.columns = [c.lower() for c in df_p_cli.columns]
                    col_nome_p = 'produto' if 'produto' in df_p_cli.columns else ('nome' if 'nome' in df_p_cli.columns else df_p_cli.columns[1])
                    produtos_opt = df_p_cli[col_nome_p].dropna().astype(str).str.strip().unique().tolist()
                else:
                    produtos_opt = []
            except Exception:
                produtos_opt = []
            
            fornecedores_opt = carregar_coluna("fornecedores", "fornecedor") or ["BAHIA"]
            grupos_opt = carregar_coluna("produtos", "grupo") or ["GERAL"]
            
            # 1. Trata a seleção do produto recém-cadastrado na sessão (se houver)
            if "prod_selecionado_temp_cli" in st.session_state:
                st.session_state["cli_select_produto"] = st.session_state.pop("prod_selecionado_temp_cli")
            
            opcoes_produtos_com_novo_cli = ["+ Cadastrar Novo Produto..."] + list(produtos_opt)
            
            # --- LINHA 1: PRODUTO E GRUPO LADO A LADO ---
            col_cli_1, col_cli_2 = st.columns(2)
            with col_cli_1:
                prod_item = st.selectbox("Selecione o Produto", opcoes_produtos_com_novo_cli, key="cli_select_produto")
            with col_cli_2:
                grupo_ped = st.selectbox("Selecione o Grupo", grupos_opt, key="cli_grupo_ind")
            
            # --- BLOCO EXCLUSIVO PARA CADASTRAR NOVO PRODUTO ---
            if prod_item == "+ Cadastrar Novo Produto...":
                st.warning("⚠️ Preencha os dados abaixo para cadastrar o novo produto:")
                
                c_cad1, c_cad2, c_cad3 = st.columns([2, 1, 1])
                with c_cad1:
                    novo_nome_prod = st.text_input("Nome do Novo Produto", key="cad_novo_nome_cli").strip().upper()
                with c_cad2:
                    c_g_r = st.selectbox("Grupo", grupos_opt, key="cad_g_rapido_cli")
                with c_cad3:
                    c_f_r = st.selectbox("Fornecedor", fornecedores_opt, key="cad_f_rapido_cli")
                
                c_cad4, c_cad5, c_cad6 = st.columns([1, 1, 1])
                with c_cad4:
                    c_qtd_r = st.number_input("Qtd Inicial em Estoque", min_value=0.0, value=0.0, key="cad_q_rapido_cli")
                with c_cad5:
                    c_compra_r = st.number_input("Preço de Compra (R$)", min_value=0.0, value=0.0, key="cad_c_rapido_cli")
                with c_cad6:
                    c_venda_r = st.number_input("Preço de Venda (R$)", min_value=0.0, value=0.0, key="cad_v_rapido_cli")
                
                if st.button("💾 Salvar e Selecionar Produto", key="btn_salvar_novo_prod_cli"):
                    if novo_nome_prod:
                        try:
                            cursor = conn.cursor()
                            cursor.execute("SELECT id FROM produtos WHERE UPPER(produto) = UPPER(?)", (novo_nome_prod,))
                            existe = cursor.fetchone()
                            
                            if existe:
                                st.warning(f"⚠️ O produto '{novo_nome_prod}' já está cadastrado!")
                                st.session_state["prod_selecionado_temp_cli"] = novo_nome_prod
                                st.rerun()
                            else:
                                cursor.execute("""
                                    INSERT INTO produtos (produto, grupo, fornecedor, quantidade, valor_compra, valor_venda)
                                    VALUES (?, ?, ?, ?, ?, ?)
                                """, (novo_nome_prod, c_g_r, c_f_r, c_qtd_r, c_compra_r, c_venda_r))
                                conn.commit()
                                st.cache_data.clear()
                                st.session_state["prod_selecionado_temp_cli"] = novo_nome_prod
                                st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao cadastrar: {e}")
                    else:
                        st.error("Digite o nome do produto.")
                    st.stop()
            
            # --- BUSCA DO PREÇO SUGERIDO AUTOMÁTICO ---
            preco_sugerido_cli = 0.0
            if 'df_p_cli' in locals() and not df_p_cli.empty and prod_item != "+ Cadastrar Novo Produto...":
                col_nome_p_cli = 'produto' if 'produto' in df_p_cli.columns else df_p_cli.columns[1]
                df_p_cli['_nome_limpo'] = df_p_cli[col_nome_p_cli].astype(str).str.strip().str.upper()
                df_filtrado_cli = df_p_cli[df_p_cli['_nome_limpo'] == str(prod_item).strip().upper()]
                
                if not df_filtrado_cli.empty:
                    row_cli = df_filtrado_cli.iloc[0]
                    for col_v in ['valor_venda', 'preco_venda', 'venda', 'valor_compra']:
                        if col_v in df_p_cli.columns:
                            try:
                                val_aux = float(row_cli[col_v])
                                if val_aux > 0:
                                    preco_sugerido_cli = val_aux
                                    break
                            except:
                                pass
            
            # --- LINHA 2: FORNECEDOR E QUANTIDADE LADO A LADO ---
            col_cli_3, col_cli_4 = st.columns(2)
            with col_cli_3:
                fornec_ped = st.selectbox("Selecione o Fornecedor", fornecedores_opt, key="cli_forn_ind")
            with col_cli_4:
                qtd_ped = st.number_input("Quantidade", min_value=0.01, step=1.0, value=1.0, key="cli_qtd_ind")
            
            # --- LINHA 3: PREÇO UNITÁRIO E VALOR TOTAL LADO A LADO ---
            col_cli_5, col_cli_6 = st.columns(2)
            with col_cli_5:
                v_venda_ped = st.number_input("Preço Unitário (R$)", min_value=0.0, value=float(preco_sugerido_cli), key=f"cli_v_ind_{prod_item}")
            with col_cli_6:
                valor_total_item = qtd_ped * v_venda_ped
                st.info(f"**Valor Total do Item:** R$ {valor_total_item:.2f}")
            
            # --- INICIALIZAÇÃO DO CARRINHO E MODO DE EDIÇÃO DO CLIENTE ---
            if "carrinho_cliente" not in st.session_state:
                st.session_state.carrinho_cliente = []
            
            if "modo_edicao_cli" not in st.session_state:
                st.session_state.modo_edicao_cli = False

            # --- BOTÃO DE INCLUSÃO NO CARRINHO ---
            if st.button("➕ Incluir Produto no Pedido", type="primary", key="btn_incluir_prod_cli"):
                if prod_item == "+ Cadastrar Novo Produto...":
                    st.error("Por favor, selecione ou cadastre o produto antes de incluir no pedido.")
                else:
                    st.session_state.carrinho_cliente.append({
                        "produto": prod_item,
                        "fornecedor": fornec_ped,
                        "grupo": grupo_ped,
                        "quantidade": float(qtd_ped),
                        "valor_unitario": float(v_venda_ped),
                        "preco_unitario": float(v_venda_ped),
                        "valor_total": float(valor_total_item)
                    })
                    st.success(f"✅ '{prod_item}' adicionado ao pedido com sucesso!")
                    st.rerun()

            st.markdown("---")

            # --- SEÇÃO: ITENS ATUAIS NO PEDIDO ---
            st.subheader("📋 Itens Atuais no Pedido")

            if st.session_state.carrinho_cliente:
                df_carrinho_cli = pd.DataFrame(st.session_state.carrinho_cliente)

                # Se o botão 'Alterar' foi clicado, mostra editor
                if st.session_state.modo_edicao_cli:
                    st.info("💡 **Modo de Edição Ativo:** Altere as quantidades ou valores diretamente na tabela abaixo e clique em **'💾 Salvar'**.")
                    df_editado_cli = st.data_editor(
                        df_carrinho_cli,
                        use_container_width=True,
                        key="editor_itens_carrinho_cli"
                    )
                else:
                    st.dataframe(df_carrinho_cli, use_container_width=True)

                # --- LINHA COM OS 4 BOTÕES LADO A LADO ---
                col_btn1, col_btn2, col_btn3, col_btn4 = st.columns(4)

                # 1. BOTÃO LIMPAR CARRINHO
                with col_btn1:
                    if st.button("🗑️ Limpar Carrinho", use_container_width=True, key="btn_limpar_cli"):
                        st.session_state.carrinho_cliente = []
                        st.session_state.modo_edicao_cli = False
                        st.rerun()

                # 2. BOTÃO ALTERAR
                with col_btn2:
                    if st.button("✏️ Alterar", use_container_width=True, key="btn_alterar_cli"):
                        st.session_state.modo_edicao_cli = True
                        st.rerun()

                # 3. BOTÃO SALVAR
                with col_btn3:
                    if st.button("💾 Salvar", use_container_width=True, key="btn_salvar_cli"):
                        if st.session_state.modo_edicao_cli and 'df_editado_cli' in locals():
                            df_editado_cli['quantidade'] = pd.to_numeric(df_editado_cli['quantidade'], errors='coerce').fillna(1)
                            df_editado_cli['valor_unitario'] = pd.to_numeric(df_editado_cli['valor_unitario'], errors='coerce').fillna(0)
                            df_editado_cli['valor_total'] = df_editado_cli['quantidade'] * df_editado_cli['valor_unitario']

                            st.session_state.carrinho_cliente = df_editado_cli.to_dict('records')
                            st.session_state.modo_edicao_cli = False
                            st.success("✅ Pedido atualizado com sucesso!")
                            st.rerun()

                # 4. BOTÃO FINALIZAR E ENVIAR PEDIDO
                with col_btn4:
                    if st.button("🔴 Finalizar e Enviar Pedido", type="primary", use_container_width=True, key="btn_finalizar_cli"):
                        try:
                            cursor = conn.cursor()
                            data_agora = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            cliente_logado = st.session_state.get('cliente_autenticado', 'Cliente')

                            for item in st.session_state.carrinho_cliente:
                                qtd_item = float(item.get("quantidade", 1))
                                prod_nome = str(item.get("produto", ""))

                                cursor.execute("""
                                    INSERT INTO pedidos (cliente, produto, fornecedor, grupo, quantidade, valor_unitario, valor_total, status, data)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, 'Pendente', ?)
                                """, (
                                    cliente_logado, prod_nome, item.get("fornecedor", ""), item.get("grupo", ""),
                                    qtd_item, float(item.get("valor_unitario", 0)), float(item.get("valor_total", 0)), data_agora
                                ))

                                # DÁ ENTRADA / SOMA A QUANTIDADE NO ESTOQUE DE PRODUTOS
                                cursor.execute("""
                                    UPDATE produtos 
                                    SET quantidade = quantidade + ? 
                                    WHERE produto = ?
                                """, (qtd_item, prod_nome))

                            conn.commit()
                            st.session_state.carrinho_cliente = []
                            st.session_state.modo_edicao_cli = False
                            st.cache_data.clear()
                            st.success("✅ Pedido enviado com sucesso!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao enviar pedido: {e}")
            else:
                st.info("Nenhum item adicionado ao carrinho ainda.")
    
        with aba_historico:
            st.subheader("Histórico e Gestão de Meus Pedidos")
            
            try:
                query_dia = """
                    SELECT id, cliente, produto, quantidade, valor_venda AS valor_unitario, valor_total, fornecedor, grupo, data, status
                    FROM vendas
                    WHERE DATE(data) = DATE('now', 'localtime') AND cliente = ?
                """
                df_dia = pd.read_sql_query(query_dia, conn, params=(st.session_state.cliente_autenticado,))
        
                if not df_dia.empty:
                    st.markdown("### 🟢 Pedidos do Dia (Editáveis)")
                    df_dia.insert(0, "Excluir", False)
                    
                    df_editado = st.data_editor(
                        df_dia,
                        column_config={
                            "Excluir": st.column_config.CheckboxColumn("❌ Excluir?", default=False),
                            "id": st.column_config.NumberColumn("ID", disabled=True),
                            "cliente": st.column_config.TextColumn("Cliente", disabled=True),
                            "produto": st.column_config.TextColumn("Produto", disabled=True),
                            "quantidade": st.column_config.NumberColumn("Quantidade", min_value=0.01, step=0.01, format="%.2f"),
                            "valor_unitario": st.column_config.NumberColumn("Valor Unitário (R$)", disabled=True, format="R$ %.2f"),
                            "valor_total": st.column_config.NumberColumn("Total (R$)", disabled=True, format="R$ %.2f"),
                            "fornecedor": st.column_config.TextColumn("Fornecedor", disabled=True),
                            "grupo": st.column_config.TextColumn("Grupo", disabled=True),
                            "data": st.column_config.TextColumn("Data", disabled=True),
                            "status": st.column_config.TextColumn("Status", disabled=True),
                        },
                        hide_index=True,
                        key="tabela_pedidos_do_dia_unica"
                    )
        
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("💾 Salvar Alterações", type="primary", key="btn_salvar_tabela_unica"):
                            try:
                                cursor = conn.cursor()
                                for index, row in df_editado.iterrows():
                                    novo_total = float(row['quantidade']) * float(row['valor_unitario'])
                                    cursor.execute("""
                                        UPDATE vendas
                                        SET quantidade = ?, valor_total = ?
                                        WHERE id = ?
                                    """, (row['quantidade'], novo_total, row['id']))
                                conn.commit()
                                st.cache_data.clear()
                                st.success("Pedidos atualizados com sucesso!")
                                st.rerun()
                            except Exception as ex:
                                st.error(f"Erro ao atualizar os pedidos: {ex}")
        
                    with col_btn2:
                        if st.button("🗑️ Excluir Marcados", type="secondary", key="btn_excluir_selecionados"):
                            try:
                                cursor = conn.cursor()
                                itens_para_excluir = df_editado[df_editado['Excluir'] == True]
                                
                                if not itens_para_excluir.empty:
                                    for _, row in itens_para_excluir.iterrows():
                                        id_item = row['id']
                                        cliente_item = row.get('cliente', '')
                                        produto_item = row.get('produto', '')
                                        
                                        cursor.execute("DELETE FROM vendas WHERE id = ?", (id_item,))
                                        if cliente_item and produto_item:
                                            cursor.execute(
                                                "DELETE FROM pedidos WHERE cliente = ? AND produto = ?", 
                                                (cliente_item, produto_item)
                                            )
                                    
                                    conn.commit()
                                    st.warning("Itens excluídos com sucesso!")
                                    st.rerun()
                                else:
                                    st.info("Nenhum item foi marcado para exclusão.")
                            except Exception as ex:
                                st.error(f"Erro ao excluir os itens: {ex}")
                else:
                    st.info("Nenhum pedido registrado hoje para edição.")
                    
            except Exception as e:
                st.error(f"Erro ao carregar pedidos do dia: {e}")
                        
            st.markdown("---")
            st.subheader("📚 Pedidos Anteriores (Histórico)")
            try:
                query_hist_cliente = """
                    SELECT id, produto, quantidade, valor_unitario, valor_total, status, data, fornecedor, grupo, codigo_pedido
                    FROM pedidos
                    WHERE cliente = ?
                    ORDER BY id DESC
                """
                df_hist_cli = pd.read_sql_query(query_hist_cliente, conn, params=(st.session_state.cliente_autenticado,))
                if not df_hist_cli.empty:
                    st.dataframe(df_hist_cli, use_container_width=True, hide_index=True)
                else:
                    st.info("Nenhum pedido anterior encontrado.")
            except Exception as e_hist:
                st.error(f"Erro ao carregar histórico: {e_hist}")

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
        
        # --- BLINDAGEM E CORREÇÃO DE ROTAS DO MENU ---
        try:
            if menu_admin == "🛒 PDV — Frente de Caixa":
                st.title("🛒 PDV — Frente de Caixa")
                st.info("Painel de PDV carregado com sucesso. Adicione os produtos para iniciar a venda.")
                # Insira aqui os componentes do PDV

            elif menu_admin == "🔓 Abertura e Fechamento de Caixa":
                st.title("🔓 Abertura e Fechamento de Caixa")
                st.subheader("Controle de Caixa Diário")
                
                # Exemplo funcional para esta tela não ficar em branco
                col_ab1, col_ab2 = st.columns(2)
                with col_ab1:
                    saldo_inicial = st.number_input("Valor de Abertura do Caixa (R$)", min_value=0.0, step=10.0, value=0.0)
                    if st.button("Abrir Caixa", type="primary"):
                        st.success(f"Caixa aberto com sucesso com o saldo inicial de R$ {saldo_inicial:.2f}!")
                with col_ab2:
                    if st.button("Fechar Caixa Atual", type="secondary"):
                        st.warning("Caixa fechado.")

            elif menu_admin == "📊 Fechamento & Financeiro":
                st.title("📊 Fechamento & Financeiro")
                st.info("Painel de relatórios financeiros e fechamentos.")

            elif menu_admin == "📋 Pedidos / Orçamentos":
                st.title("📋 Pedidos e Orçamentos")
                df_pedidos = carregar_dados("SELECT * FROM vendas")
                if not df_pedidos.empty:
                    st.dataframe(df_pedidos, use_container_width=True)
                else:
                    st.warning("Nenhum pedido registrado no banco de dados.")

            elif menu_admin == "🛒 Registrar Venda":
                st.title("🛒 Registrar Venda Manual")
                st.info("Utilize este espaço para registrar vendas avulsas.")

            elif menu_admin == "📥 Entrada de Estoque (Compras)":
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
                        cursor = conn.cursor()
                        data_agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                        for item in st.session_state.carrinho_compras:
                            cursor.execute("""
                                INSERT INTO compras (produto, fornecedor, grupo, quantidade, valor_compra, valor_venda, valor_total, data)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                item['produto'], item['fornecedor'], item['grupo'],
                                item['quantidade'], item['valor_compra'], item['valor_venda'],
                                item['valor_total'], data_agora
                            ))

                        conn.commit()
                        st.session_state.carrinho_compras = []
                        st.cache_data.clear()
                        st.success("✅ Entrada de estoque finalizada com sucesso!")
                        st.rerun()

            elif menu_admin == "📦 Estoque de Produtos":
                st.title("📦 Consulta de Estoque")
                df_prod = carregar_dados("SELECT * FROM compras")
                if not df_prod.empty:
                    st.dataframe(df_prod, use_container_width=True)
                else:
                    st.info("Nenhum produto cadastrado no estoque.")

            elif menu_admin == "👥 Cadastros (Clientes / Fornecedores / Grupos)":
                st.title("👥 Central de Cadastros")
                tab1, tab2, tab3 = st.tabs(["Clientes", "Fornecedores", "Grupos"])
                with tab1:
                    st.subheader("Cadastrar Novo Cliente")
                    nome_cli = st.text_input("Nome do Cliente", key="cad_cli_nome")
                    fone_cli = st.text_input("Telefone", key="cad_cli_fone")
                    doc_cli = st.text_input("CPF/CNPJ", key="cad_cli_doc")
                    end_cli = st.text_input("Endereço", key="cad_cli_end")
                    cidade_cli = st.text_input("Cidade", key="cad_cli_cidade")
                    if st.button("Salvar Cliente"):
                        if nome_cli:
                            salvar_cliente_completo(nome_cli, fone_cli, doc_cli, end_cli, cidade_cli)
                            st.success("Cliente salvo com sucesso!")
                        else:
                            st.error("O nome do cliente é obrigatório.")
                with tab2:
                    st.subheader("Gerenciar Fornecedores")
                    novo_forn = st.text_input("Nome do Fornecedor", key="cad_forn_nome")
                    if st.button("Salvar Fornecedor"):
                        if novo_forn:
                            salvar_simples("fornecedores", "fornecedor", novo_forn)
                            st.success("Fornecedor cadastrado!")
                with tab3:
                    st.subheader("Gerenciar Grupos")
                    novo_grupo = st.text_input("Nome do Grupo", key="cad_grupo_nome")
                    if st.button("Salvar Grupo"):
                        if novo_grupo:
                            salvar_simples("grupos", "grupo", novo_grupo)
                            st.success("Grupo cadastrado!")

        except Exception as e:
            st.error(f"Ocorreu um erro ao renderizar esta tela: {e}")
