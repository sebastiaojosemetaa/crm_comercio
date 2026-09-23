import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date, timedelta
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
import io
import pandas as pd
import datetime as dt

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

        # 1. Tabela de Produtos (Garanti a criação básica e as colunas extras)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS produtos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                produto TEXT
            )
        """)
        
        colunas_produtos = [
            "fornecedor", "grupo", "preco_compra", "preco_venda", 
            "venda", "quantidade", "estoque", "codigo"
        ]
        for col in colunas_produtos:
            try:
                cursor.execute(f"ALTER TABLE produtos ADD COLUMN {col} TEXT")
            except Exception:
                pass  # Se a coluna já existir, o SQLite ignora

        # 2. Tabela de Clientes
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
        # Exemplo dentro da sua função de migração do banco:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente TEXT,
                cpf TEXT,
                telefone TEXT,
                endereco TEXT,
                cidade TEXT,
                email TEXT,
                senha TEXT
            )
        """)

        # 3. Tabela de Vendas
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vendas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente TEXT,
                produto TEXT,
                data TEXT
            )
        """)
        colunas_vendas = [
            "fornecedor", "grupo", "quantidade", "valor_venda", 
            "valor_total", "forma_pagamento", "valor_recebido", 
            "troco", "restante", "status", "tipo", "codigo", "codigo_venda"
        ]
        for col in colunas_vendas:
            try:
                cursor.execute(f"ALTER TABLE vendas ADD COLUMN {col} TEXT")
            except Exception:
                pass

        # 4. Tabela de Sessões de Caixa
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

        # 5. Tabela de Movimentações de Caixa
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
    except Exception as e:
        print(f"Aviso de migração: {e}")

# Executa a migração ao iniciar
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

import datetime as dt
import pandas as pd
import streamlit as st

# Configuração da página (deve ser a primeira chamada do Streamlit)
st.set_page_config(
    page_title="CRM Comércio - Rey da Cebola", page_icon="🛍️", layout="wide"
)

# ==========================================
# BARRA LATERAL ÚNICA (MENU PRINCIPAL)
# ==========================================
st.sidebar.title("🔑 Acesso ao Sistema")
st.sidebar.write("Selecione o Perfil:")

# Apenas um único rádio para definir o perfil em todo o app
perfil_selecionado = st.sidebar.radio(
    "Selecione o Perfil:",
    ["Portal do Cliente", "Administração / Vendedor"],
    label_visibility="collapsed",
)

st.sidebar.markdown("---")

# ==========================================
# AMBIENTE 1: PORTAL DO CLIENTE
# ==========================================
if perfil_selecionado == "Portal do Cliente":

  if "ativar_recuperacao" not in st.session_state:
    st.session_state.ativar_recuperacao = False

  # 1. Botão para acionar a recuperação na barra lateral
  if not st.session_state.ativar_recuperacao:
    if st.sidebar.button("🔑 Esqueci minha senha", key="btn_esqueci_senha_sidebar"):
      st.session_state.ativar_recuperacao = True
      st.rerun()

  # 2. Se a recuperação estiver ativa, mostra o formulário na barra lateral
  if st.session_state.ativar_recuperacao:
    if "fluxo_recuperacao_cliente" in globals():
      fluxo_recuperacao_cliente(conn)
    else:
      st.sidebar.warning("Função de recuperação não definida.")
      if st.sidebar.button("Voltar ao Login"):
        st.session_state.ativar_recuperacao = False
        st.rerun()

  # 3. Se NÃO estiver em recuperação, gerencia a autenticação e o painel principal
  else:
    if "cliente_autenticado" not in st.session_state:
      st.session_state.cliente_autenticado = None

    # Se não estiver autenticado, exibe a tela de login
    if not st.session_state.cliente_autenticado:
      st.title("🔒 Portal do Cliente")
      st.info(
          "Por favor, selecione seu nome na barra lateral e insira sua senha"
          " para acessar seus pedidos."
      )

      # Carrega os clientes da base de dados
      try:
        df_cli_select = carregar_dados("SELECT * FROM clientes")
      except Exception:
        df_cli_select = pd.DataFrame()

      lista_clientes = []
      if not df_cli_select.empty:
        df_cli_select.columns = [c.lower() for c in df_cli_select.columns]
        for col_cand in ["cliente", "nome", "razao_social"]:
          if col_cand in df_cli_select.columns:
            vals = df_cli_select[col_cand].dropna().astype(str).str.strip()
            lista_clientes.extend(vals[vals != ""].unique().tolist())
        lista_clientes = list(dict.fromkeys(lista_clientes))

      if not lista_clientes:
        lista_clientes = ["Sebastião"]

      # Campos de seleção e senha na barra lateral
      cliente_nome = st.sidebar.selectbox(
          "Identifique seu Nome/Empresa:", lista_clientes
      )
      senha_cliente = st.sidebar.text_input(
          "Digite sua Senha de Cliente:", type="password"
      )

      if st.sidebar.button("Acessar Meus Pedidos"):
        if senha_cliente == "123":  # Substitua pela validação real da senha
          st.session_state.cliente_autenticado = cliente_nome
          st.rerun()
        else:
          st.sidebar.error("Senha incorreta!")

    # Se já estiver autenticado, exibe o painel principal do cliente
    else:
      st.sidebar.success(
          f"Logado como:\n**{st.session_state.cliente_autenticado}**"
      )
      if st.sidebar.button("Sair / Trocar Cliente"):
        st.session_state.cliente_autenticado = None
        st.rerun()

      st.title(
          "🛍️ Portal do Cliente — Meus Pedidos"
          f" ({st.session_state.cliente_autenticado})"
      )

      # (Insira aqui o restante do código das abas de pedidos...)

# ==========================================
# AMBIENTE 2: ADMINISTRAÇÃO / VENDEDOR
# ==========================================
elif perfil_selecionado == "Administração / Vendedor":
  st.title("⚙️ Painel da Administração / Vendedor")
  st.info("Área administrativa do sistema.")
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
                "👥 Cadastros (Clientes / Fornecedores / Grupos)",
                "💾 Backup e Restauração"
            ]
        )
        
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
            col_pdv_esq, col_pdv_dir = st.columns([1.1, 1.9])
    
            with col_pdv_esq:
                st.markdown("#### ➕ Adicionar Item ao Carrinho")
                prod_item = st.selectbox("Produto", produtos_opt, key="pdv_select_produto")
                
                preco_sugerido = 0.0
                forn_sugerido = fornecedores_opt[0]
                grupo_sugerido = grupos_opt[0]
    
                if not df_p.empty:
                    df_p['nome_limpo'] = df_p[col_nome_p].astype(str).str.strip().str.upper()
                    target_nome = str(prod_item).strip().upper()
                    df_filtrado_p = df_p[df_p['nome_limpo'] == target_nome]
    
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
                    forn_item = st.selectbox("Fornecedor", fornecedores_opt, index=idx_f, key="pdv_forn_input")
                    idx_g = grupos_opt.index(grupo_sugerido) if grupos_opt and grupo_sugerido in grupos_opt else 0
                    grupo_item = st.selectbox("Grupo", grupos_opt, index=idx_g, key="pdv_grupo_input")
    
                with col_s2:
                    qtd_item = st.number_input("Quantidade", min_value=0.1, step=1.0, value=1.0, key="pdv_qtd")
                    v_unit_item = st.number_input("Preço de Venda (R$)", min_value=0.0, step=1.0, value=float(preco_sugerido), key=f"vunit_{prod_item}")
    
                valor_total_item = qtd_item * v_unit_item
                st.metric("Valor Total do Item", f"R$ {valor_total_item:.2f}")
    
                if st.button("➕ Incluir Produto no Carrinho", type="primary"):
                    st.session_state.carrinho_pdv.append({
                        "produto": prod_item,
                        "fornecedor": forn_item,
                        "grupo": grupo_item,
                        "quantidade": qtd_item,
                        "valor_venda": v_unit_item,
                        "valor_total": valor_total_item
                    })
                    st.success(f"Item '{prod_item}' adicionado ao carrinho!")
                    st.rerun()
    
            with col_pdv_dir:
                st.markdown("#### 🛒 Itens Atuais no Carrinho")
                if len(st.session_state.carrinho_pdv) > 0:
                    df_carrinho = pd.DataFrame(st.session_state.carrinho_pdv)
                    st.dataframe(df_carrinho, use_container_width=True, hide_index=True)
                    total_geral_carrinho = df_carrinho['valor_total'].sum()
                else:
                    st.info("O carrinho está vazio.")
                    total_geral_carrinho = 0.0
    
                if st.button("🗑️ Limpar Carrinho"):
                    st.session_state.carrinho_pdv = []
                    st.rerun()
    
                st.markdown("---")
                st.markdown("#### 💳 Forma de Pagamento e Finalização")
                
                f_pag = st.selectbox("Forma de Pagamento", ["Dinheiro", "Pix", "Cartão de Crédito", "Cartão de Débito", "Fiado / Prazo"], key="pdv_forma_pagto")
                v_rec = st.number_input("Valor Recebido (R$)", min_value=0.0, step=1.0, value=float(total_geral_carrinho), key="pdv_val_rec")
                troco = v_rec - total_geral_carrinho if v_rec > total_geral_carrinho else 0.0
    
                col_t1, col_t2 = st.columns(2)
                with col_t1:
                    st.metric("Valor Total da Venda", f"R$ {total_geral_carrinho:.2f}")
                with col_t2:
                    st.metric("Troco", f"R$ {troco:.2f}")
    
                if st.button("Finalizar Venda no PDV", type="primary"):
                    if not df_caixa_aberto.empty and len(st.session_state.carrinho_pdv) > 0:
                        cursor = conn.cursor()
                        sessao_id = int(df_caixa_aberto.iloc[0]['id'])
                        data_venda = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                        # 1. Grava cada item na tabela de vendas
                        for item in st.session_state.carrinho_pdv:
                            cursor.execute("""
                                INSERT INTO vendas (cliente, produto, fornecedor, grupo, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, status, tipo, data)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                cliente_pdv, 
                                item['produto'], 
                                item['fornecedor'], 
                                item['grupo'],
                                item['quantidade'], 
                                item['valor_venda'], 
                                item['valor_total'],
                                f_pag, 
                                v_rec, 
                                'Concluído', 
                                'VENDA', 
                                data_venda
                            ))
                
                        # 2. Insere obrigatoriamente a movimentação vinculada ao caixa aberto para somar no total
                        cursor.execute("""
                            INSERT INTO caixa_movimentacoes (sessao_id, tipo, valor, descricao, data) 
                            VALUES (?, ?, ?, ?, ?)
                        """, (
                            sessao_id, 
                            "VENDA", 
                            float(total_geral_carrinho), 
                            f"Venda PDV - Cliente: {cliente_pdv}", 
                            data_venda
                        ))
                        
                        conn.commit()
                
                        # 3. Limpa o carrinho e avisa o utilizador
                        st.session_state.carrinho_pdv = []
                        st.success(f"Venda realizada com sucesso! Troco: R$ {max(0.0, troco):.2f}")
                        st.rerun()
                    else:
                        st.error("Verifique se o caixa está aberto e se há itens no carrinho.")

        elif menu_admin == "🔓 Abertura e Fechamento de Caixa":
            st.title("🔓 Abertura e Fechamento de Caixa")
            df_caixa_atual = carregar_dados("SELECT * FROM caixa_sessoes WHERE status = 'ABERTO'")

            if df_caixa_atual.empty:
                st.info("O caixa encontra-se **FECHADO**. Insira o valor inicial para abri-lo.")
                with st.form("form_abrir_caixa"):
                    saldo_inicial = st.number_input("Saldo Inicial em Dinheiro (Troco / Fundo de Caixa)", min_value=0.0, step=10.0)
                    if st.form_submit_button("Abrir Caixa"):
                        cursor = conn.cursor()
                        data_agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        cursor.execute("INSERT INTO caixa_sessoes (data_abertura, saldo_inicial, status) VALUES (?, ?, ?)",
                                       (data_agora, saldo_inicial, "ABERTO"))
                        conn.commit()
                        st.success("Caixa aberto com sucesso!")
                        st.rerun()
            else:
                # CORREÇÃO AQUI: Usando df_caixa_atual em vez de df_caixa_aberto
                sessao_id = int(df_caixa_atual.iloc[0]['id'])
                data_abertura = df_caixa_atual.iloc[0]['data_abertura']
                saldo_inicial = float(df_caixa_atual.iloc[0]['saldo_inicial'])
                
                st.success(f"🟢 **Caixa ABERTO** desde: {data_abertura} | Saldo Inicial: R$ {saldo_inicial:,.2f}")
                df_movs = carregar_dados(f"SELECT * FROM caixa_movimentacoes WHERE sessao_id = {sessao_id}")
                total_movimentado = df_movs['valor'].sum() if not df_movs.empty else 0.0
                
                st.metric("Total Movimentado neste Caixa", f"R$ {total_movimentado:,.2f}")
                if not df_movs.empty:
                    st.dataframe(df_movs, use_container_width=True)
                
                st.markdown("---")
                with st.form("form_fechar_caixa"):
                    saldo_final_informado = st.number_input("Conferência de Saldo Final (Dinheiro em Caixa)", min_value=0.0, step=10.0, value=saldo_inicial + total_movimentado)
                    if st.form_submit_button("🔒 Fechar Caixa"):
                        cursor = conn.cursor()
                        data_fechamento = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        cursor.execute("UPDATE caixa_sessoes SET data_fechamento = ?, saldo_final = ?, status = ? WHERE id = ?",
                                       (data_fechamento, saldo_final_informado, "FECHADO", sessao_id))
                        conn.commit()
                        st.success("Caixa fechado com sucesso!")
                        st.rerun()

        elif menu_admin == "📊 Fechamento & Financeiro":
            import datetime as dt

            # --- PAINEL FINANCEIRO & FECHAMENTO POR DATA ---
            st.header("📊 Painel Financeiro & Fechamento por Data")
            
            st.subheader("💳 Contas a Receber (Parcelas / Fiado)")

            # 1. Carrega vendas e pedidos
            df_vendas_fin = carregar_dados("SELECT id, cliente, produto, fornecedor, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, troco, restante, data, grupo FROM vendas ORDER BY id DESC")
            df_pedidos_fin = carregar_dados("SELECT * FROM pedidos ORDER BY id DESC")
            
            # Trata e identifica pendências (Crediário / Fiado)
            if not df_vendas_fin.empty and 'restante' in df_vendas_fin.columns:
                df_vendas_fin['restante'] = pd.to_numeric(df_vendas_fin['restante'], errors='coerce').fillna(0.0)
                df_pendentes_fin = df_vendas_fin[df_vendas_fin['restante'] > 0]
                if not df_pendentes_fin.empty:
                    st.warning(f"⚠️ Existem {len(df_pendentes_fin)} registro(s) de crediário com saldo pendente.")
                else:
                    st.info("Nenhuma parcela pendente de recebimento no momento.")
            else:
                st.info("Nenhuma parcela pendente de recebimento no momento.")
            
            st.markdown("---")
            
            # 2. Monta lista de clientes para o filtro
            clientes_vendas = df_vendas_fin['cliente'].dropna().astype(str).unique().tolist() if not df_vendas_fin.empty and 'cliente' in df_vendas_fin.columns else []
            clientes_pedidos = df_pedidos_fin['cliente'].dropna().astype(str).unique().tolist() if not df_pedidos_fin.empty and 'cliente' in df_pedidos_fin.columns else []
            todos_clientes = sorted(list(set(clientes_vendas + clientes_pedidos)))
            lista_clientes_fin = ["Todos"] + todos_clientes
            
            # 3. Filtros no Topo
            col_f1, col_f2, col_f3, col_f4 = st.columns([2.5, 2, 2, 2.5])
            
            with col_f1:
                f_cliente_fin = st.selectbox("Filtrar por Cliente:", lista_clientes_fin, key="f_cli_painel_fin")
            
            with col_f2:
                data_inicio_def = dt.date(2025, 1, 1)
                data_inicio = st.date_input("Data Inicial", value=data_inicio_def, key="dt_inicio_fin")
            
            with col_f3:
                data_fim = st.date_input("Data Final", value=dt.date.today(), key="dt_fim_fin")
            
            with col_f4:
                opcao_status = st.selectbox(
                    "Status dos Registros",
                    ["Incluir Pedidos Pendentes", "Apenas Vendas Concluídas", "Apenas Pedidos Pendentes"],
                    key="status_registros_fin"
                )
            
            dfs_para_concatenar = []
            
            # Trata Vendas
            if not df_vendas_fin.empty and opcao_status != "Apenas Pedidos Pendentes":
                df_v = df_vendas_fin.copy()
                if 'data' in df_v.columns:
                    # Converte para data simples evitando falhas de fuso ou hora
                    df_v['dt_formatada'] = pd.to_datetime(df_v['data'], errors='coerce').dt.date
                    df_v['dt_formatada'] = df_v['dt_formatada'].fillna(
                        pd.to_datetime(df_v['data'].astype(str).str[:10], errors='coerce').dt.date
                    )
                dfs_para_concatenar.append(df_v)
            
            # Trata Pedidos Pendentes
            if not df_pedidos_fin.empty and opcao_status in ["Incluir Pedidos Pendentes", "Apenas Pedidos Pendentes"]:
                df_p = df_pedidos_fin[df_pedidos_fin['status'].astype(str).str.upper().str.contains("PENDENTE")].copy()
                if not df_p.empty:
                    if 'data' in df_p.columns:
                        df_p['dt_formatada'] = pd.to_datetime(df_p['data'], errors='coerce').dt.date
                        df_p['dt_formatada'] = df_p['dt_formatada'].fillna(
                            pd.to_datetime(df_p['data'].astype(str).str[:10], errors='coerce').dt.date
                        )
            
                    if 'valor_unitario' in df_p.columns and 'valor_venda' not in df_p.columns:
                        df_p['valor_venda'] = df_p['valor_unitario']
                    if 'forma_pagamento' not in df_p.columns:
                        df_p['forma_pagamento'] = "PENDENTE"
                    if 'valor_recebido' not in df_p.columns:
                        df_p['valor_recebido'] = 0.0
                    if 'troco' not in df_p.columns:
                        df_p['troco'] = 0.0
                    if 'restante' not in df_p.columns:
                        df_p['restante'] = df_p['valor_total']
            
                    dfs_para_concatenar.append(df_p)
            
            # Unifica dados
            if dfs_para_concatenar:
                df_fin_geral = pd.concat(dfs_para_concatenar, ignore_index=True)
            else:
                df_fin_geral = pd.DataFrame()
            
            # Aplica Filtros de Cliente e Intervalo de Datas
            if not df_fin_geral.empty:
                if f_cliente_fin != "Todos":
                    df_fin_geral = df_fin_geral[df_fin_geral['cliente'].astype(str) == str(f_cliente_fin)]
            
                if 'dt_formatada' in df_fin_geral.columns:
                    # Filtra considerando apenas o intervalo de dias (inclusivo)
                    df_fin_geral = df_fin_geral[
                        (df_fin_geral['dt_formatada'] >= data_inicio) & 
                        (df_fin_geral['dt_formatada'] <= data_fim)
                    ]
            
            # Converte valores numéricos para cálculo dos totais
            if not df_fin_geral.empty:
                for c in ['valor_total', 'valor_recebido', 'restante']:
                    if c in df_fin_geral.columns:
                        df_fin_geral[c] = pd.to_numeric(df_fin_geral[c], errors='coerce').fillna(0.0)
            
                fat_periodo = float(df_fin_geral['valor_total'].sum())
                rec_caixa = float(df_fin_geral['valor_recebido'].sum())
                tot_pendente = float(df_fin_geral['restante'].sum())
            else:
                fat_periodo = 0.0
                rec_caixa = 0.0
                tot_pendente = 0.0
            
            # Exibição das Métricas Financeiras
            col_m1, col_m2, col_m3 = st.columns(3)
            
            with col_m1:
                st.markdown("**Faturamento do Período**")
                st.markdown(f"### R$ {fat_periodo:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            
            with col_m2:
                st.markdown("**Total Recebido em Caixa**")
                st.markdown(f"### R$ {rec_caixa:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            
            with col_m3:
                st.markdown("**Total Pendente / Fiado**")
                st.markdown(f"### R$ {tot_pendente:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            
            st.markdown("---")
            
            # Exibição da Tabela Final
            if not df_fin_geral.empty:
                cols_ordem = ['id', 'cliente', 'produto', 'fornecedor', 'quantidade', 'valor_venda', 'valor_total', 'forma_pagamento', 'valor_recebido', 'troco', 'restante', 'data', 'grupo']
                cols_presentes = [c for c in cols_ordem if c in df_fin_geral.columns]
            
                st.dataframe(df_fin_geral[cols_presentes], use_container_width=True)
            else:
                st.info("Nenhum registro encontrado para os filtros selecionados.")

        elif menu_admin in ["📋 Pedidos / Orçamentos", "🛒 Registrar Venda"]:
            is_modo_pedido = (menu_admin == "📋 Pedidos / Orçamentos")
            st.title(f"🛒 {menu_admin}")
            
            if "carrinho_admin" not in st.session_state:
                st.session_state.carrinho_admin = []
        
            aba_cad, aba_list = st.tabs(["+ Novo Registro / Pedido", "🔧 Tabela Editável"])
        
            with aba_cad:
                clientes_opt = carregar_coluna("clientes", "nome") or ["Carlos Alberto"]
                
                df_p_admin = carregar_dados("SELECT * FROM produtos")
                if not df_p_admin.empty:
                    df_p_admin.columns = [c.lower() for c in df_p_admin.columns]
                    col_nome_p = 'produto' if 'produto' in df_p_admin.columns else ('nome' if 'nome' in df_p_admin.columns else df_p_admin.columns[1])
                    produtos_base = df_p_admin[col_nome_p].dropna().astype(str).str.strip().unique().tolist()
                else:
                    produtos_base = ["AMEIXA IMPORTADA", "ABACATE"]
                    df_p_admin = pd.DataFrame()
        
                produtos_opt = list(produtos_base) + ["➕ Cadastrar Novo Produto..."]
                fornecedores_opt = carregar_coluna("fornecedores", "fornecedor") or ["BAHIA"]
                grupos_opt = carregar_coluna("grupos", "grupo") or ["GERAL"]
        
                # 1. Trata a seleção do produto recém-cadastrado na sessão
                if "prod_selecionado_temp" in st.session_state:
                    st.session_state["ped_select_produto"] = st.session_state.pop("prod_selecionado_temp")
                
                # 2. Cria a lista com a opção de cadastro (Corrige o NameError)
                opcoes_produtos_com_novo = ["+ Cadastrar Novo Produto..."] + list(produtos_opt)
                
                # --- LINHA 1: CLIENTE ---
                cliente_ped = st.selectbox("Cliente", clientes_opt, key="ped_cli_ind")
                
                # --- LINHA 2: PRODUTO E GRUPO LADO A LADO ---
                col_l2_1, col_l2_2 = st.columns(2)
                with col_l2_1:
                    prod_item = st.selectbox("Selecione o Produto", opcoes_produtos_com_novo, key="ped_select_produto")
                with col_l2_2:
                    grupo_ped = st.selectbox("Grupo", grupos_opt, key="ped_grupo_ind")
                
                # --- BLOCO EXCLUSIVO PARA CADASTRAR NOVO PRODUTO ---
                if prod_item == "+ Cadastrar Novo Produto...":
                    st.warning("⚠️ Preencha os dados abaixo para cadastrar o novo produto:")
                
                    c_cad1, c_cad2, c_cad3 = st.columns([2, 1, 1])
                    with c_cad1:
                        novo_nome_prod = st.text_input("Nome do Novo Produto", key="cad_novo_nome_ped").strip().upper()
                    with c_cad2:
                        c_g_r = st.selectbox("Grupo", grupos_opt, key="cad_g_rapido")
                    with c_cad3:
                        c_f_r = st.selectbox("Fornecedor", fornecedores_opt, key="cad_f_rapido")
                
                    c_cad4, c_cad5, c_cad6 = st.columns([1, 1, 1])
                    with c_cad4:
                        c_qtd_r = st.number_input("Qtd Inicial em Estoque", min_value=0.0, value=0.0, key="cad_q_rapido")
                    with c_cad5:
                        c_compra_r = st.number_input("Preço de Compra (R$)", min_value=0.0, value=0.0, key="cad_c_rapido")
                    with c_cad6:
                        c_venda_r = st.number_input("Preço de Venda (R$)", min_value=0.0, value=0.0, key="cad_v_rapido")
                
                    if st.button("💾 Salvar e Selecionar Produto", key="btn_salvar_novo_prod_ped"):
                        if novo_nome_prod:
                            try:
                                cursor = conn.cursor()
                                cursor.execute("SELECT id FROM produtos WHERE UPPER(produto) = UPPER(?)", (novo_nome_prod,))
                                existe = cursor.fetchone()
                
                                if existe:
                                    st.warning(f"⚠️ O produto '{novo_nome_prod}' já está cadastrado!")
                                    st.session_state["prod_selecionado_temp"] = novo_nome_prod
                                    st.rerun()
                                else:
                                    cursor.execute("""
                                        INSERT INTO produtos (produto, grupo, fornecedor, quantidade, valor_compra, valor_venda)
                                        VALUES (?, ?, ?, ?, ?, ?)
                                    """, (novo_nome_prod, c_g_r, c_f_r, c_qtd_r, c_compra_r, c_venda_r))
                                    conn.commit()
                                    st.cache_data.clear()
                                    st.session_state["prod_selecionado_temp"] = novo_nome_prod
                                    st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao cadastrar: {e}")
                        else:
                            st.error("Digite o nome do produto.")
                        st.stop()
                
                # --- BUSCA DO PREÇO SUGERIDO DO BANCO ---
                preco_sugerido_admin = 0.0
                if not df_p_admin.empty and prod_item != "+ Cadastrar Novo Produto...":
                    df_p_admin['_nome_limpo'] = df_p_admin[col_nome_p].astype(str).str.strip().str.upper()
                    df_filtrado_admin = df_p_admin[df_p_admin['_nome_limpo'] == str(prod_item).strip().upper()]
                
                    if not df_filtrado_admin.empty:
                        row_adm = df_filtrado_admin.iloc[0]
                        for col_v in ['valor_venda', 'preco_venda', 'venda', 'valor_compra']:
                            if col_v in df_p_admin.columns:
                                try:
                                    val_aux = float(row_adm[col_v])
                                    if val_aux > 0:
                                        preco_sugerido_admin = val_aux
                                        break
                                except:
                                    pass
                
                # --- LINHA 3: FORNECEDOR E QUANTIDADE LADO A LADO ---
                col_l3_1, col_l3_2 = st.columns(2)
                with col_l3_1:
                    fornec_ped = st.selectbox("Fornecedor", fornecedores_opt, key="ped_forn_ind")
                with col_l3_2:
                    qtd_ped = st.number_input("Quantidade", min_value=0.01, step=1.0, value=1.0, key="ped_qtd_ind")
                
                # --- LINHA 4: PREÇO UNITÁRIO E VALOR TOTAL LADO A LADO ---
                col_l4_1, col_l4_2 = st.columns(2)
                with col_l4_1:
                    v_venda_ped = st.number_input("Preço Unitário (R$)", min_value=0.0, value=float(preco_sugerido_admin), key=f"ped_v_ind_{prod_item}")
                with col_l4_2:
                    valor_total_item = qtd_ped * v_venda_ped
                    st.info(f"**Valor Total do Item:** R$ {valor_total_item:.2f}")
                
                # --- BOTÃO DE INCLUSÃO NO CARRINHO ---
                if st.button("➕ Incluir Produto no Pedido", type="primary", key="btn_incluir_prod_pedido"):
                    if prod_item == "+ Cadastrar Novo Produto...":
                        st.error("Por favor, selecione ou cadastre o produto antes de incluir no pedido.")
                    else:
                        if "carrinho_admin" not in st.session_state:
                            st.session_state.carrinho_admin = []
                
                        st.session_state.carrinho_admin.append({
                            "produto": prod_item,
                            "fornecedor": fornec_ped,
                            "grupo": grupo_ped,
                            "quantidade": qtd_ped,
                            "valor_unitario": v_venda_ped,
                            "valor_total": valor_total_item
                        })
                        st.success(f"✅ '{prod_item}' adicionado ao pedido com sucesso!")
                        st.rerun()
        
                st.markdown("---")
                # --- SEÇÃO: ITENS ATUAIS NO PEDIDO ---
                st.subheader("📋 Itens Atuais no Pedido")
            
                # Inicializa a variável de controle do modo de edição
                if 'modo_edicao_carrinho' not in st.session_state:
                    st.session_state.modo_edicao_carrinho = False
            
                # Define qual carrinho usar (ajuste o nome da variável se for diferente no seu código)
                carrinho_atual = st.session_state.get('carrinho_admin', st.session_state.get('carrinho', []))
            
                if carrinho_atual:
                    df_carrinho = pd.DataFrame(carrinho_atual)
            
                    # Se o botão 'Alterar' foi clicado, exibe a tabela editável
                    if st.session_state.modo_edicao_carrinho:
                        st.info("💡 **Modo de Edição Ativo:** Altere as quantidades ou valores diretamente na tabela abaixo e depois clique em **'💾 Salvar'**.")
                        df_editado = st.data_editor(
                            df_carrinho,
                            use_container_width=True,
                            key="editor_itens_carrinho"
                        )
                    else:
                        st.dataframe(df_carrinho, use_container_width=True)
            
                    # --- LINHA COM OS 4 BOTÕES LADO A LADO ---
                    col_btn1, col_btn2, col_btn3, col_btn4 = st.columns(4)
            
                    # 1. BOTÃO LIMPAR CARRINHO
                    with col_btn1:
                        if st.button("🗑️ Limpar Carrinho", use_container_width=True, key="btn_limpar_carrinho_v2"):
                            if 'carrinho_admin' in st.session_state:
                                st.session_state.carrinho_admin = []
                            if 'carrinho' in st.session_state:
                                st.session_state.carrinho = []
                            st.session_state.modo_edicao_carrinho = False
                            st.rerun()
            
                    # 2. BOTÃO ALTERAR (NOVO)
                    with col_btn2:
                        if st.button("✏️ Alterar", use_container_width=True, key="btn_alterar_carrinho_v2"):
                            st.session_state.modo_edicao_carrinho = True
                            st.rerun()
            
                    # 3. BOTÃO SALVAR (NOVO)
                    with col_btn3:
                        if st.button("💾 Salvar", use_container_width=True, key="btn_salvar_carrinho_v2"):
                            if st.session_state.modo_edicao_carrinho and 'df_editado' in locals():
                                # Recalcula os totais após a edição
                                if 'quantidade' in df_editado.columns and 'valor_unitario' in df_editado.columns:
                                    df_editado['quantidade'] = pd.to_numeric(df_editado['quantidade'], errors='coerce').fillna(1)
                                    df_editado['valor_unitario'] = pd.to_numeric(df_editado['valor_unitario'], errors='coerce').fillna(0)
                                    df_editado['valor_total'] = df_editado['quantidade'] * df_editado['valor_unitario']
            
                                novos_itens = df_editado.to_dict('records')
                                if 'carrinho_admin' in st.session_state:
                                    st.session_state.carrinho_admin = novos_itens
                                if 'carrinho' in st.session_state:
                                    st.session_state.carrinho = novos_itens
            
                                st.session_state.modo_edicao_carrinho = False
                                st.success("✅ Alterações do carrinho salvas!")
                                st.rerun()
                            else:
                                st.warning("Clique em '✏️ Alterar' primeiro para editar a tabela.")
            
                    # 4. BOTÃO FINALIZAR E ENVIAR PEDIDO
                    with col_btn4:
                        if st.button("🔴 Finalizar e Enviar Pedido", type="primary", use_container_width=True, key="btn_finalizar_pedido_v2"):
                            try:
                                cursor = conn.cursor()
                                data_agora = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
                                # Salva cada item no banco de dados
                                for item in carrinho_atual:
                                    qtd_item = float(item.get("quantidade", 1))
                                    prod_nome = str(item.get("produto", ""))
            
                                    cursor.execute("""
                                        INSERT INTO pedidos (cliente, produto, fornecedor, grupo, quantidade, valor_unitario, valor_total, status, data)
                                        VALUES (?, ?, ?, ?, ?, ?, ?, 'Pendente', ?)
                                    """, (
                                        cliente_ped, prod_nome, item.get("fornecedor", ""), item.get("grupo", ""),
                                        qtd_item, float(item.get("valor_unitario", 0)), float(item.get("valor_total", 0)), data_agora
                                    ))
            
                                    # DÁ ENTRADA / SOMA A QUANTIDADE NO ESTOQUE DE PRODUTOS
                                    cursor.execute("""
                                        UPDATE produtos 
                                        SET quantidade = quantidade + ? 
                                        WHERE produto = ?
                                    """, (qtd_item, prod_nome))
            
                                conn.commit()
            
                                # Esvazia o carrinho
                                if 'carrinho_admin' in st.session_state:
                                    st.session_state.carrinho_admin = []
                                if 'carrinho' in st.session_state:
                                    st.session_state.carrinho = []
            
                                st.session_state.modo_edicao_carrinho = False
                                st.cache_data.clear()
                                st.success("✅ Pedido enviado com sucesso!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao salvar pedido: {e}")
                else:
                    st.info("Nenhum item adicionado ao carrinho ainda.")
        
            import datetime as dt

            with aba_list:
                st.subheader("🟢 Pedidos do Dia Pendentes (Editáveis)")
            
                # Carrega apenas pedidos PENDENTES para a tela principal de edição/baixa
                df_todos_pedidos = carregar_dados("SELECT * FROM pedidos WHERE status = 'PENDENTE' OR status = 'Pendente' ORDER BY id DESC")
            
                if not df_todos_pedidos.empty:
                    df_filtrado = df_todos_pedidos.copy()
            
                    if 'Excluir' not in df_filtrado.columns:
                        df_filtrado.insert(0, 'Excluir', False)
            
                    if 'data' in df_filtrado.columns:
                        df_filtrado['data_formatada'] = df_filtrado['data'].astype(str).str.slice(0, 10)
            
                    col_f1, col_f2, col_f3, col_f4 = st.columns(4)
            
                    lista_cli = ["Todos"] + sorted(list(df_filtrado['cliente'].dropna().astype(str).unique())) if 'cliente' in df_filtrado.columns else ["Todos"]
                    lista_forn = ["Todos"] + sorted(list(df_filtrado['fornecedor'].dropna().astype(str).unique())) if 'fornecedor' in df_filtrado.columns else ["Todos"]
                    lista_grp = ["Todos"] + sorted(list(df_filtrado['grupo'].dropna().astype(str).unique())) if 'grupo' in df_filtrado.columns else ["Todos"]
            
                    with col_f1:
                        f_cli = st.selectbox("Filtrar por Cliente:", lista_cli, key="f_cli_pedidos")
                    with col_f2:
                        f_forn = st.selectbox("Filtrar por Fornecedor:", lista_forn, key="f_forn_pedidos")
                    with col_f3:
                        f_grp = st.selectbox("Filtrar por Grupo:", lista_grp, key="f_grp_pedidos")
                    with col_f4:
                        f_data = st.date_input("Filtrar por Data:", value=None, key="f_data_pedidos")
            
                    if f_cli != "Todos":
                        df_filtrado = df_filtrado[df_filtrado['cliente'].astype(str) == str(f_cli)]
                    if f_forn != "Todos":
                        df_filtrado = df_filtrado[df_filtrado['fornecedor'].astype(str) == str(f_forn)]
                    if f_grp != "Todos":
                        df_filtrado = df_filtrado[df_filtrado['grupo'].astype(str) == str(f_grp)]
                    if f_data is not None and 'data_formatada' in df_filtrado.columns:
                        df_filtrado = df_filtrado[df_filtrado['data_formatada'] == str(f_data)]
            
                    if not df_filtrado.empty:
                        cols_exibir = [c for c in df_filtrado.columns if c != 'data_formatada']
                        
                        st.caption("💡 *Edite os dados diretamente na tabela abaixo ou marque a caixa 'Excluir' para remover.*")
                        
                        df_editado = st.data_editor(
                            df_filtrado[cols_exibir],
                            disabled=["id", "data"],
                            use_container_width=True,
                            column_config={
                                "valor_unitario": st.column_config.NumberColumn(
                                    "Valor Unitário",
                                    format="R$ %.2f"
                                ),
                                "valor_total": st.column_config.NumberColumn(
                                    "Valor Total",
                                    format="R$ %.2f"
                                )
                            },
                            key="editor_pedidos_dia"
                        )
            
                        col_b1, col_b2, col_b3 = st.columns(3)
            
                        with col_b1:
                            if st.button("💾 Salvar Alterações", type="primary", key="btn_salvar_edicoes_pedidos"):
                                try:
                                    cursor = conn.cursor()
                                    for index, row in df_editado.iterrows():
                                        ped_id = row['id']
                                        qtd = float(row.get('quantidade', 1))
                                        v_unit = float(row.get('valor_unitario', 0.0))
                                        v_tot = qtd * v_unit
                                        cli = str(row.get('cliente', '')).strip()
                                        prod = str(row.get('produto', '')).strip()
                                        fornec = str(row.get('fornecedor', '')).strip()
                                        grp = str(row.get('grupo', '')).strip()
                                        stts = str(row.get('status', 'PENDENTE')).strip()
            
                                        cursor.execute("""
                                            UPDATE pedidos
                                            SET cliente = ?, produto = ?, quantidade = ?, valor_unitario = ?, valor_total = ?, fornecedor = ?, grupo = ?, status = ?
                                            WHERE id = ?
                                        """, (cli, prod, qtd, v_unit, v_tot, fornec, grp, stts, ped_id))
            
                                    conn.commit()
                                    st.cache_data.clear()
                                    st.success("✅ Alterações salvas com sucesso!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Erro ao salvar alterações: {e}")
                            if st.button("🔄 Atualizar Preços dos Pedidos com o Estoque", key="btn_atualizar_precos_pedidos"):
                                try:
                                    with conn:
                                        cursor = conn.cursor()
                                        cursor.execute("""
                                            UPDATE pedidos
                                            SET valor_unitario = (
                                                SELECT valor_venda FROM produtos
                                                WHERE produtos.produto = pedidos.produto
                                            ),
                                            valor_total = quantidade * (
                                                SELECT valor_venda FROM produtos
                                                WHERE produtos.produto = pedidos.produto
                                            )
                                            WHERE status = 'Pendente' AND EXISTS (
                                                SELECT 1 FROM produtos
                                                WHERE produtos.produto = pedidos.produto
                                            )
                                        """)
                                    st.cache_data.clear()
                                    st.success("✅ Preços dos pedidos pendentes atualizados com o estoque com sucesso!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Erro ao atualizar preços dos pedidos: {e}")
                        with col_b2:
                            if st.button("🗑️ Excluir Marcados", type="secondary", key="btn_excluir_pedidos_marcados"):
                                try:
                                    pedidos_para_excluir = df_editado[df_editado['Excluir'] == True]['id'].tolist()
                                    if pedidos_para_excluir:
                                        cursor = conn.cursor()
                                        cursor.executemany("DELETE FROM pedidos WHERE id = ?", [(pid,) for pid in pedidos_para_excluir])
                                        conn.commit()
                                        st.cache_data.clear()
                                        st.success(f"✅ {len(pedidos_para_excluir)} pedido(s) excluído(s)!")
                                        st.rerun()
                                    else:
                                        st.warning("Nenhum pedido marcado na coluna 'Excluir'.")
                                except Exception as e:
                                    st.error(f"Erro ao excluir pedido(s): {e}")
            
                        with col_b3:
                            try:
                                df_pdf = df_editado.drop(columns=['Excluir'], errors='ignore')
                                pdf_buf = gerar_pdf_tabela_pedidos(df_pdf, cliente_nome=f_cli)
                                nome_arq = f"relatorio_pedidos_{f_cli.lower().replace(' ', '_')}.pdf" if f_cli != "Todos" else "relatorio_pedidos_geral.pdf"
                                
                                st.download_button(
                                    label="📄 Baixar PDF do Dia",
                                    data=pdf_buf.getvalue(),
                                    file_name=nome_arq,
                                    mime="application/pdf",
                                    key="btn_pdf_dia_admin_v7"
                                )
                            except Exception as e:
                                st.error(f"Erro ao gerar PDF: {e}")
            
                    else:
                        st.warning("Nenhum pedido pendente encontrado com os filtros selecionados.")
                else:
                    st.info("Nenhum pedido pendente registrado no sistema.")
            
                st.divider()
            
                # --- SEÇÃO: CONFIRMAR RECEBIMENTO / DAR BAIXA NO PEDIDO ---
                st.subheader("💳 Confirmar Recebimento / Dar Baixa no Pedido")
            
                df_baixa = carregar_dados("SELECT * FROM pedidos WHERE status = 'PENDENTE' OR status = 'Pendente'")
            
                if not df_baixa.empty:
                    clientes_com_pendencia = sorted(list(df_baixa['cliente'].dropna().astype(str).unique()))
                    cliente_sel_baixa = st.selectbox("Selecione o Cliente:", clientes_com_pendencia, key="sel_cli_baixa_pedidos")
            
                    df_cli_pedidos = df_baixa[df_baixa['cliente'].astype(str) == str(cliente_sel_baixa)].copy()
            
                    if not df_cli_pedidos.empty:
                        st.dataframe(df_cli_pedidos, use_container_width=True)
            
                        valor_total_debito = float(df_cli_pedidos['valor_total'].sum())
                        st.info(f"💳 **Débito Total Atual de {cliente_sel_baixa}: R$ {valor_total_debito:.2f}**")
            
                        col_p1, col_p2, col_p3 = st.columns([2, 2, 2])
                        with col_p1:
                            forma_pagamento = st.selectbox("Forma de Pagamento:", ["Dinheiro", "Pix", "Cartão de Crédito", "Cartão de Débito", "Crediário / Fiado"], key="fp_baixa_pedido")
                        with col_p2:
                            valor_recebido = st.number_input("Valor Recebido / Entrada (R$):", min_value=0.0, value=0.0 if forma_pagamento == "Crediário / Fiado" else float(valor_total_debito), step=1.0, key="vr_baixa_pedido")
                        with col_p3:
                            troco = valor_recebido - valor_total_debito if valor_recebido > valor_total_debito else 0.0
                            st.markdown(f"**Troco:**\n### R$ {troco:.2f}")
            
                        detalhe_pagamento = forma_pagamento
                        if forma_pagamento == "Crediário / Fiado":
                            st.markdown("---")
                            st.subheader("📅 Configuração das Parcelas do Crediário")
                            
                            valor_pendente = max(0.0, valor_total_debito - valor_recebido)
                            
                            col_parc1, col_parc2 = st.columns(2)
                            with col_parc1:
                                num_parcelas = st.number_input("Quantidade de Parcelas:", min_value=1, max_value=24, value=1, step=1, key="num_parc_fiado")
                            with col_parc2:
                                st.metric("Valor Total a Parcelar", f"R$ {valor_pendente:.2f}")
            
                            st.write("**Defina os Valores e Datas de Vencimento das Parcelas:**")
                            
                            val_sugerido_padrao = round(valor_pendente / int(num_parcelas), 2) if num_parcelas > 0 else 0.0
                            parcelas_info = []
            
                            for i in range(int(num_parcelas)):
                                col_v1, col_v2 = st.columns(2)
                                with col_v1:
                                    val_parc_input = st.number_input(f"Valor Parcela {i+1} (R$):", min_value=0.0, value=float(val_sugerido_padrao), step=1.0, key=f"val_parc_{i}")
                                with col_v2:
                                    data_sugerida = dt.date.today() + dt.timedelta(days=30 * (i + 1))
                                    dt_input = st.date_input(f"Venc. Parcela {i+1}:", value=data_sugerida, key=f"dt_venc_parc_{i}")
                                
                                parcelas_info.append(f"P{i+1}: R$ {val_parc_input:.2f} ({dt_input.strftime('%d/%m/%Y')})")
            
                            detalhe_pagamento = f"Crediário ({num_parcelas}x | " + ", ".join(parcelas_info) + ")"
            
                        if st.button("🔄 Converter Pedido em Venda (Fiado / Baixa)", type="primary", key="btn_converter_pedido_venda"):
                            try:
                                cursor = conn.cursor()
                                codigo_venda_gerado = f"PED-{dt.datetime.now().strftime('%Y%m%d%H%M%S')}"
            
                                for _, r in df_cli_pedidos.iterrows():
                                    item_tot = float(r.get('valor_total', 0.0))
                                    qtd_item = float(r.get('quantidade', 1))
                                    
                                    # Rateia o valor recebido proporcionalmente por item
                                    if valor_total_debito > 0:
                                        item_rec = round((item_tot / valor_total_debito) * valor_recebido, 2)
                                    else:
                                        item_rec = 0.0
                                    
                                    item_rest = round(max(0.0, item_tot - item_rec), 2)
            
                                    # 1. REMOVE O REGISTO PENDENTE ANTIGO DO HISTÓRICO PARA EVITAR DUPLICAÇÃO
                                    cursor.execute("""
                                        DELETE FROM vendas 
                                        WHERE cliente = ? AND produto = ? AND (forma_pagamento = '-' OR forma_pagamento IS NULL OR forma_pagamento = 'None')
                                    """, (str(r['cliente']), str(r['produto'])))
            
                                    # 2. SUBTRAI / DÁ BAIXA DA QUANTIDADE NO ESTOQUE DE PRODUTOS
                                    cursor.execute("""
                                        UPDATE produtos 
                                        SET quantidade = quantidade - ? 
                                        WHERE produto = ?
                                    """, (qtd_item, str(r['produto'])))
            
                                    # 3. INSERE A VENDA ATUALIZADA COM A FORMA DE PAGAMENTO E PARCELAS
                                    cursor.execute("""
                                        INSERT INTO vendas (cliente, produto, fornecedor, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, troco, restante, data, grupo, codigo_venda, status, tipo, codigo)
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    """, (
                                        str(r['cliente']),
                                        str(r['produto']),
                                        str(r.get('fornecedor', '')),
                                        qtd_item,
                                        float(r.get('valor_unitario', 0)),
                                        item_tot,
                                        detalhe_pagamento,
                                        item_rec,
                                        0.0,
                                        item_rest,
                                        dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                        str(r.get('grupo', '')),
                                        codigo_venda_gerado,
                                        "Concluído",
                                        "PEDIDO",
                                        f"PED-{r['id']}"
                                    ))
            
                                    cursor.execute("UPDATE pedidos SET status = 'Concluído (Convertido)' WHERE id = ?", (r['id'],))
            
                                conn.commit()
            
                                if 'executar_limpeza_banco' in globals():
                                    executar_limpeza_banco()
            
                                st.cache_data.clear()
                                st.success(f"✅ Pedido(s) de {cliente_sel_baixa} convertidos e estoque atualizado com sucesso!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao dar baixa no pedido: {e}")
                    else:
                        st.info("Nenhum pedido pendente para este cliente.")
                else:
                    st.info("Nenhum cliente possui pedidos pendentes para dar baixa no momento.")
            
                st.divider()
            
                # --- SEÇÃO: PEDIDOS ANTERIORES / HISTÓRICO GERAL ---
                st.subheader("📚 Pedidos Anteriores / Histórico Geral")
            
                df_historico = carregar_dados("SELECT id, cliente, produto, fornecedor, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, troco, restante, data, grupo FROM vendas ORDER BY id DESC")
            
                if not df_historico.empty:
                    # Garante substituição visual de qualquer NULL restante
                    df_historico['forma_pagamento'] = df_historico['forma_pagamento'].fillna('-').replace({'None': '-', '': '-'})
                    for c in ['valor_recebido', 'troco', 'restante']:
                        df_historico[c] = pd.to_numeric(df_historico[c], errors='coerce').fillna(0.0)
            
                    st.dataframe(df_historico, use_container_width=True)
            
                    col_hist1, col_hist2 = st.columns([1, 4])
                    with col_hist1:
                        if st.button("🗑️ Limpar Todo o Histórico", type="secondary", key="btn_limpar_historico"):
                            try:
                                cursor = conn.cursor()
                                
                                # 1. Limpa o histórico geral de vendas (Admin)
                                cursor.execute("DELETE FROM vendas")
                                
                                # 2. Limpa o histórico de pedidos antigos/concluídos (Portal do Cliente)
                                cursor.execute("DELETE FROM pedidos WHERE status LIKE '%Concluído%' OR status LIKE '%Convertido%'")
                                
                                conn.commit()
                                st.cache_data.clear()
                                st.success("✅ Histórico do Admin e do Portal do Cliente limpos com sucesso!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao limpar histórico: {e}")
                else:
                    st.info("Nenhum registro encontrado.")
            
        elif menu_admin == "📦 Estoque de Produtos":
            st.title("📦 Estoque de Produtos e Preços")
    
            # --- CARREGAMENTO SEGURO DA TABELA DE ESTOQUE ---
            try:
                df_produtos = pd.read_sql_query("SELECT * FROM produtos", conn)
            except Exception:
                df_produtos = pd.DataFrame()
    
            # Garante a existência de todas as colunas necessárias
            cols_esperadas = ['id', 'produto', 'quantidade', 'valor_compra', 'valor_venda', 'grupo', 'fornecedor']
            for c in cols_esperadas:
                if c not in df_produtos.columns:
                    df_produtos[c] = 0.0 if ('valor' in c or 'quantidade' in c) else ""
    
            if not df_produtos.empty:
                cols_finais = [c for c in cols_esperadas if c in df_produtos.columns]
                df_produtos = df_produtos[cols_finais]
    
            # Exibe a tabela editável
            df_estoque_editado = st.data_editor(
                df_produtos,
                use_container_width=True,
                hide_index=True,
                key="editor_estoque_produtos"
            )
    
            # DEFINIÇÃO DAS COLUNAS PARA OS BOTÕES (RESOLVE O NameError)
            col_salvar, col_atualizar = st.columns([1, 1])
    
            # Botão 1: Salvar Alterações
            with col_salvar:
                if st.button("💾 Salvar Alterações no Estoque", type="primary", key="btn_salvar_estoque"):
                    try:
                        cursor = conn.cursor()
    
                        # Garante que as colunas existem fisicamente na base de dados
                        for col in ["grupo", "fornecedor"]:
                            try:
                                cursor.execute(f"ALTER TABLE produtos ADD COLUMN {col} TEXT")
                            except Exception:
                                pass
    
                        for index, row in df_estoque_editado.iterrows():
                            cursor.execute("""
                                UPDATE produtos 
                                SET produto = ?, 
                                    quantidade = ?, 
                                    valor_compra = ?, 
                                    valor_venda = ?, 
                                    grupo = ?, 
                                    fornecedor = ?
                                WHERE id = ?
                            """, (
                                row['produto'], 
                                row['quantidade'], 
                                row['valor_compra'], 
                                row['valor_venda'], 
                                row.get('grupo', ''), 
                                row.get('fornecedor', ''), 
                                row['id']
                            ))
    
                        conn.commit()
                        st.cache_data.clear()
                        st.success("✅ Alterações do estoque salvas com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar: {e}")
    
            # Botão 2: Atualizar Preços de Compra
            with col_atualizar:
                if st.button("🔄 Atualizar Preços de Compra", key="btn_atualizar_precos"):
                    try:
                        with conn:
                            cursor = conn.cursor()
                            cursor.execute("""
                                UPDATE produtos
                                SET valor_compra = (
                                    SELECT valor_compra FROM compras
                                    WHERE compras.produto = produtos.produto
                                    ORDER BY id DESC LIMIT 1
                                )
                                WHERE EXISTS (
                                    SELECT 1 FROM compras
                                    WHERE compras.produto = produtos.produto
                                )
                            """)
                        st.cache_data.clear()
                        st.success("✅ Preços de compra atualizados com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao atualizar preço: {e}")
        
        elif menu_admin == "👥 Cadastros (Clientes / Fornecedores / Grupos)":
            st.title("👥 Cadastros Gerais")
            tab_cli, tab_prod, tab_forn, tab_grup = st.tabs(["👤 Clientes", "📦 Produtos", "🏢 Fornecedores", "🏷️ Grupos"])
    
            # --- ABA 1: CLIENTES ---
            with tab_cli:
                st.subheader("👤 Gerenciamento de Clientes")
    
                with st.form("form_cadastrar_cliente", clear_on_submit=True):
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
    
                st.markdown("---")
                st.subheader("Lista de Clientes")
                df_cli_view = carregar_dados("SELECT * FROM clientes")
                if not df_cli_view.empty:
                    st.dataframe(df_cli_view, use_container_width=True)
                    
                    # Seção para Atualizar e Excluir Clientes Existentes
                    st.markdown("---")
                    st.subheader("⚙️ Gerir Clientes Selecionados")
                    if 'id' in df_cli_view.columns:
                        lista_ids = df_cli_view['id'].tolist()
                        id_selecionado = st.selectbox("Selecione o ID do Cliente para Atualizar ou Excluir", lista_ids, key="sel_cli_gerir")
                        
                        cli_atual = df_cli_view[df_cli_view['id'] == id_selecionado].iloc[0]
                        
                        nome_atual = str(cli_atual.get('cliente', '')) if pd.notna(cli_atual.get('cliente')) else str(cli_atual.get('nome', ''))
                        cpf_atual = str(cli_atual.get('cpf', '')) if pd.notna(cli_atual.get('cpf')) else ''
                        end_atual = str(cli_atual.get('endereco', '')) if pd.notna(cli_atual.get('endereco')) else ''
                        email_atual = str(cli_atual.get('email', '')) if pd.notna(cli_atual.get('email')) else ''
                        fone_atual = str(cli_atual.get('fone', '')) if pd.notna(cli_atual.get('fone')) else ''
                        cidade_atual = str(cli_atual.get('cidade', '')) if pd.notna(cli_atual.get('cidade')) else ''
            
                        with st.form("form_gerir_cliente"):
                            novo_nome = st.text_input("Nome / Cliente", value=nome_atual)
                            novo_cpf = st.text_input("CPF / DOC", value=cpf_atual)
                            novo_end = st.text_input("Endereço", value=end_atual)
                            novo_email = st.text_input("E-mail", value=email_atual)
                            novo_fone = st.text_input("Telefone / Fone", value=fone_atual)
                            novo_cidade = st.text_input("Cidade", value=cidade_atual)
                            
                            col_b1, col_b2 = st.columns(2)
                            with col_b1:
                                btn_atualizar = st.form_submit_button("🔄 Atualizar Cliente", type="primary")
                            with col_b2:
                                btn_excluir = st.form_submit_button("🗑️ Excluir Cliente", type="secondary")
                                
                            if btn_atualizar:
                                cursor = conn.cursor()
                                cursor.execute("""
                                    UPDATE clientes 
                                    SET cliente = ?, nome = ?, cpf = ?, endereco = ?, email = ?, fone = ?, cidade = ?
                                    WHERE id = ?
                                """, (novo_nome, novo_nome, novo_cpf, novo_end, novo_email, novo_fone, novo_cidade, id_selecionado))
                                conn.commit()
                                st.success("Cliente atualizado com sucesso!")
                                st.rerun()
                                
                            if btn_excluir:
                                cursor = conn.cursor()
                                cursor.execute("DELETE FROM clientes WHERE id = ?", (id_selecionado,))
                                conn.commit()
                                st.success("Cliente excluído com sucesso!")
                                st.rerun()
                else:
                    st.info("Nenhum cliente cadastrado ainda.")
    
            # --- ABA 2: PRODUTOS ---
            with tab_prod:
                st.subheader("📝 Gerenciar Produtos (Cadastrar, Editar e Excluir)")
    
                # 🔍 Busca todos os Grupos cadastrados no banco
                try:
                    df_g = carregar_dados("SELECT DISTINCT grupo FROM grupos WHERE grupo IS NOT NULL AND grupo != '' ORDER BY grupo")
                    grupos_opt = df_g['grupo'].tolist() if not df_g.empty else ["GERAL"]
                except Exception:
                    grupos_opt = ["GERAL"]
    
                # 🔍 Busca todos os Fornecedores cadastrados no banco
                try:
                    df_f = carregar_dados("SELECT DISTINCT fornecedor FROM fornecedores WHERE fornecedor IS NOT NULL AND fornecedor != '' ORDER BY fornecedor")
                    fornecedores_opt = df_f['fornecedor'].tolist() if not df_f.empty else ["BAHIA"]
                except Exception:
                    fornecedores_opt = ["BAHIA"]
    
                with st.form("form_cadastrar_produto", clear_on_submit=True):
                    col1, col2 = st.columns(2)
    
                    with col1:
                        txt_nome_produto = st.text_input("Nome do Produto")
                        val_compra = st.number_input("Preço de Compra (R$)", min_value=0.0, value=0.0, step=0.5)
                        estoque_inicial = st.number_input("Estoque Inicial", min_value=0.0, value=0.0, step=1.0)
    
                    with col2:
                        grupo_produto = st.selectbox("Grupo / Categoria", grupos_opt)
                        val_venda = st.number_input("Preço de Venda (R$)", min_value=0.0, value=0.0, step=0.5)
                        fornecedor_produto = st.selectbox("Fornecedor", fornecedores_opt)
    
                    btn_salvar = st.form_submit_button("💾 Salvar Novo Produto")
    
                    if btn_salvar:
                        if not txt_nome_produto.strip():
                            st.warning("Por favor, informe o nome do produto.")
                        else:
                            try:
                                cursor = conn.cursor()
    
                                # Garante que as colunas existem na tabela do banco
                                for col in ["grupo", "fornecedor", "valor_compra", "valor_venda"]:
                                    try:
                                        cursor.execute(f"ALTER TABLE produtos ADD COLUMN {col} TEXT")
                                    except Exception:
                                        pass
    
                                cursor.execute("""
                                    INSERT INTO produtos (produto, grupo, fornecedor, quantidade, valor_compra, valor_venda)
                                    VALUES (?, ?, ?, ?, ?, ?)
                                """, (
                                    txt_nome_produto.strip().upper(),
                                    grupo_produto,
                                    fornecedor_produto,
                                    float(estoque_inicial),
                                    float(val_compra),
                                    float(val_venda)
                                ))
                                conn.commit()
                                st.cache_data.clear()
                                st.success(f"✅ Produto '{txt_nome_produto}' cadastrado com sucesso!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao cadastrar produto: {e}")
    
                st.markdown("---")
                st.subheader("📋 Lista de Produtos (Edite direto na tabela ou exclua abaixo)")
    
                try:
                    df_produtos_gerenciar = pd.read_sql_query("SELECT * FROM produtos", conn)
                except Exception:
                    df_produtos_gerenciar = pd.DataFrame()
    
                cols_esperadas = ['id', 'produto', 'quantidade', 'valor_compra', 'valor_venda', 'grupo', 'fornecedor']
                for c in cols_esperadas:
                    if c not in df_produtos_gerenciar.columns:
                        df_produtos_gerenciar[c] = 0.0 if ('valor' in c or 'quantidade' in c) else ""
    
                if not df_produtos_gerenciar.empty:
                    cols_finais = [c for c in cols_esperadas if c in df_produtos_gerenciar.columns]
                    df_produtos_gerenciar = df_produtos_gerenciar[cols_finais]
    
                df_gerenciar_editado = st.data_editor(
                    df_produtos_gerenciar,
                    use_container_width=True,
                    hide_index=True,
                    key="editor_gerenciar_produtos_tab"
                )
    
                col_btn_salvar, col_btn_excluir = st.columns([1, 1])
    
                with col_btn_salvar:
                    if st.button("💾 Salvar Alterações da Tabela", type="primary", key="btn_salvar_tabela_gerenciar"):
                        try:
                            with conn:
                                cursor = conn.cursor()
                                for index, row in df_gerenciar_editado.iterrows():
                                    cursor.execute("""
                                        UPDATE produtos 
                                        SET produto = ?, 
                                            quantidade = ?, 
                                            valor_compra = ?, 
                                            valor_venda = ?, 
                                            grupo = ?, 
                                            fornecedor = ?
                                        WHERE id = ?
                                    """, (
                                        row['produto'], 
                                        row['quantidade'], 
                                        row['valor_compra'], 
                                        row['valor_venda'], 
                                        row['grupo'], 
                                        row['fornecedor'], 
                                        row['id']
                                    ))
                            st.cache_data.clear()
                            st.success("✅ Alterações salvas com sucesso!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao salvar alterações: {e}")
    
                with col_btn_excluir:
                    lista_produtos_excluir = df_produtos_gerenciar['produto'].tolist() if not df_produtos_gerenciar.empty else []
                    prod_para_excluir = st.selectbox(
                        "Selecione um produto para excluir", 
                        options=lista_produtos_excluir, 
                        key="sel_prod_excluir"
                    )
    
                    if st.button("🗑️ Excluir Produto Selecionado", key="btn_excluir_produto"):
                        if prod_para_excluir:
                            try:
                                with conn:
                                    cursor = conn.cursor()
                                    cursor.execute("DELETE FROM produtos WHERE produto = ?", (prod_para_excluir,))
                                st.cache_data.clear()
                                st.success(f"✅ Produto '{prod_para_excluir}' excluído com sucesso!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao excluir produto: {e}")
                        else:
                            st.warning("Nenhum produto selecionado para exclusão.")
    
            # --- ABA 3: FORNECEDORES ---
            with tab_forn:
                st.subheader("🏢 Gerenciar Fornecedores")
    
                with st.form("form_cad_fornecedor", clear_on_submit=True):
                    nome_forn = st.text_input("Nome do Fornecedor / Empresa")
                    if st.form_submit_button("Salvar Novo Fornecedor"):
                        if nome_forn.strip():
                            try:
                                salvar_simples("fornecedores", "fornecedor", nome_forn.upper())
                                st.success(f"Fornecedor '{nome_forn}' cadastrado com sucesso!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao cadastrar fornecedor: {e}")
                        else:
                            st.warning("Informe o nome do fornecedor.")
    
                st.markdown("---")
                st.subheader("📋 Lista de Fornecedores (Edite ou Exclua)")
    
                df_forn_view = carregar_dados("SELECT * FROM fornecedores")
                if not df_forn_view.empty:
                    df_editado_forn = st.data_editor(
                        df_forn_view, 
                        use_container_width=True, 
                        hide_index=True,
                        key="editor_fornecedores"
                    )
    
                    col_f1, col_f2 = st.columns(2)
                    with col_f1:
                        if st.button("💾 Salvar Alterações de Fornecedores"):
                            try:
                                cursor = conn.cursor()
                                for index, row in df_editado_forn.iterrows():
                                    f_id = row.get('id')
                                    f_nome = row.get('fornecedor')
                                    cursor.execute("UPDATE fornecedores SET fornecedor = ? WHERE id = ?", (str(f_nome).upper(), f_id))
                                conn.commit()
                                st.success("Fornecedores atualizados com sucesso!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao salvar: {e}")
    
                    with col_f2:
                        forn_para_excluir = df_forn_view['fornecedor'].tolist()
                        forn_selecionado = st.selectbox("Selecione um fornecedor para excluir", forn_para_excluir, key="select_del_forn")
                        if st.button("🗑️ Excluir Fornecedor Selecionado"):
                            try:
                                cursor = conn.cursor()
                                cursor.execute("DELETE FROM fornecedores WHERE fornecedor = ?", (forn_selecionado,))
                                conn.commit()
                                st.success(f"Fornecedor '{forn_selecionado}' excluído com sucesso!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao excluir: {e}")
                else:
                    st.info("Nenhum fornecedor cadastrado.")
    
            # --- ABA 4: GRUPOS ---
            with tab_grup:
                st.subheader("🏷️ Gerenciar Grupos / Categorias")
    
                with st.form("form_cad_grupo", clear_on_submit=True):
                    nome_grupo = st.text_input("Nome do Grupo / Categoria")
                    if st.form_submit_button("Salvar Novo Grupo"):
                        if nome_grupo.strip():
                            try:
                                salvar_simples("grupos", "grupo", nome_grupo.upper())
                                st.success(f"Grupo '{nome_grupo}' cadastrado com sucesso!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao cadastrar grupo: {e}")
                        else:
                            st.warning("Informe o nome do grupo.")
    
                st.markdown("---")
                st.subheader("📋 Lista de Grupos (Edite ou Exclua)")
    
                df_grup_view = carregar_dados("SELECT * FROM grupos")
                if not df_grup_view.empty:
                    df_editado_grup = st.data_editor(
                        df_grup_view, 
                        use_container_width=True, 
                        hide_index=True,
                        key="editor_grupos"
                    )
    
                    col_g1, col_g2 = st.columns(2)
                    with col_g1:
                        if st.button("💾 Salvar Alterações de Grupos"):
                            try:
                                cursor = conn.cursor()
                                for index, row in df_editado_grup.iterrows():
                                    g_id = row.get('id')
                                    g_nome = row.get('grupo')
                                    cursor.execute("UPDATE grupos SET grupo = ? WHERE id = ?", (str(g_nome).upper(), g_id))
                                conn.commit()
                                st.success("Grupos atualizados com sucesso!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao salvar: {e}")
    
                    with col_g2:
                        grup_para_excluir = df_grup_view['grupo'].tolist()
                        grup_selecionado = st.selectbox("Selecione um grupo para excluir", grup_para_excluir, key="select_del_grup")
                        if st.button("🗑️ Excluir Grupo Selecionado"):
                            try:
                                cursor = conn.cursor()
                                cursor.execute("DELETE FROM grupos WHERE grupo = ?", (grup_selecionado,))
                                conn.commit()
                                st.success(f"Grupo '{grup_selecionado}' excluído com sucesso!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao excluir: {e}")
                else:
                    st.info("Nenhum grupo cadastrado.")
        elif menu_admin == "💾 Backup e Restauração":
                st.title("💾 Central de Backup e Restauração")
                st.info("Gerencie cópias de segurança do seu banco de dados com total segurança. Nenhum dado cadastrado será perdido.")

                tab_bk1, tab_bk2 = st.tabs(["📤 Fazer Backup", "📥 Restaurar Backup"])

                # --- ABA 1: FAZER BACKUP ---
                with tab_bk1:
                    st.subheader("Gerar Cópia de Segurança")
                    st.write("Clique no botão abaixo para baixar o arquivo contendo todos os seus produtos, clientes e vendas atualizados.")
                    
                    try:
                        with open("crm_comercio.db", "rb") as f:
                            bytes_db = f.read()
                        
                        data_hoje = datetime.now().strftime("%Y-%m-%d_%H-%M")
                        st.download_button(
                            label="📥 Baixar Arquivo de Backup (.db)",
                            data=bytes_db,
                            file_name=f"backup_crm_comercio_{data_hoje}.db",
                            mime="application/octet-stream",
                            type="primary"
                        )
                    except Exception as e:
                        st.warning("O arquivo do banco de dados ainda não foi criado ou não foi encontrado.")

                # --- ABA 2: RESTAURAR BACKUP ---
                with tab_bk2:
                    st.subheader("Restaurar Sistema por Arquivo de Backup")
                    st.warning("⚠️ **Atenção:** Enviar um arquivo de backup antigo irá substituir os dados atuais pelos dados contidos no arquivo enviado.")
                    
                    arquivo_upload = st.file_uploader("Selecione o arquivo de backup (.db)", type=["db"])
                    
                    if arquivo_upload is not None:
                        if st.button("🔄 Confirmar e Restaurar Banco de Dados", type="primary"):
                            try:
                                with open("crm_comercio.db", "wb") as f:
                                    f.write(arquivo_upload.getbuffer())
                                
                                st.success("✅ Backup restaurado com sucesso! Recarregando o sistema...")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao restaurar o backup: {e}")            
        elif menu_admin == "📥 Entrada de Estoque (Compras)":
            st.title("📥 Entrada de Estoque (Compras)")
            st.subheader("Registrar Entrada de Estoque")
        
            # Memory / Carrinho temporário na sessão do Streamlit
            if "carrinho_compras" not in st.session_state:
                st.session_state.carrinho_compras = []
        
            produtos_opt = carregar_coluna("produtos", "produto") or ["AMEIXA IMPORTADA", "ABACATE"]
            fornecedores_opt = carregar_coluna("fornecedores", "fornecedor") or ["BAHIA"]
            grupos_opt = carregar_coluna("grupos", "grupo") or ["GERAL"]
        
            tipo_cadastro = st.radio("Escolha a opção:", ["Produto Existente", "Novo Produto"], horizontal=True, key="radio_tipo_prod")
        
            col1, col2 = st.columns(2)
            with col1:
                if tipo_cadastro == "Produto Existente":
                    produto_escolhido = st.selectbox("Selecione o Produto", produtos_opt, key="prod_entrada_estoque")
                    produto_final = produto_escolhido
                else:
                    produto_final = st.text_input("Digite o Nome do NOVO Produto", key="input_novo_produto_compras").strip().upper()
        
                fornecedor_escolhido = st.selectbox("Fornecedor", fornecedores_opt, key="forn_entrada")
                quantidade_entrada = st.number_input("Quantidade", min_value=0.01, value=1.0, step=1.0, key="qtd_entrada")
        
            with col2:
                grupo_escolhido = st.selectbox("Grupo / Categoria", grupos_opt, key="grupo_entrada")
                preco_compra = st.number_input("Preço de compra Unitário (R$)", min_value=0.0, format="%.2f", key="compra_entrada")
                preco_venda = st.number_input("Preço de Venda Unitário (R$)", min_value=0.0, format="%.2f", key="venda_entrada")
        
            # 🛒 BOTÃO 1: Adiciona ao carrinho temporário
            if st.button("🛒 Adicionar ao Carrinho", type="primary"):
                if not produto_final:
                    st.error("Por favor, informe ou selecione o produto.")
                elif quantidade_entrada <= 0:
                    st.error("A quantidade deve ser maior que zero.")
                else:
                    st.session_state.carrinho_compras.append({
                        "produto": produto_final,
                        "grupo": grupo_escolhido,
                        "fornecedor": fornecedor_escolhido,
                        "quantidade": quantidade_entrada,
                        "valor_compra": preco_compra,
                        "valor_venda": preco_venda
                    })
                    st.success(f"✅ '{produto_final}' adicionado ao carrinho!")
                    st.rerun()
        
            # --- SEÇÃO DO CARRINHO DE COMPRAS ---
            if st.session_state.carrinho_compras:
                st.divider()
                st.subheader("📋 Itens no Carrinho de Entrada")
                st.caption("💡 **Dica**: Você pode editar os campos direto na tabela ou selecionar a linha e apertar `Delete` para excluir.")
        
                # Converte a lista em DataFrame para exibição interativa
                df_carrinho = pd.DataFrame(st.session_state.carrinho_compras)
        
                # Tabela editável: permite alterar valores diretamente e excluir linhas
                df_carrinho_editado = st.data_editor(
                    df_carrinho,
                    use_container_width=True,
                    num_rows="dynamic",
                    key="editor_carrinho_compras"
                )
        
                col_salvar_tudo, col_limpar = st.columns([2, 1])
        
                # 💾 BOTÃO 2: Salva tudo de uma vez no banco SQLite
                with col_salvar_tudo:
                    if st.button("💾 Finalizar e Salvar Todas as Entradas", type="primary", key="btn_salvar_carrinho_db"):
                        try:
                            with conn:
                                cursor = conn.cursor()
                                cursor.execute("""
                                    CREATE TABLE IF NOT EXISTS produtos (
                                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                                        produto TEXT,
                                        grupo TEXT,
                                        fornecedor TEXT,
                                        quantidade REAL DEFAULT 0,
                                        valor_compra REAL DEFAULT 0,
                                        valor_venda REAL DEFAULT 0
                                    )
                                """)
        
                                # Percorre todas as linhas que ficaram no carrinho
                                for index, item in df_carrinho_editado.iterrows():
                                    cursor.execute("SELECT id FROM produtos WHERE produto = ?", (item['produto'],))
                                    existe = cursor.fetchone()
        
                                    if existe:
                                        cursor.execute("""
                                            UPDATE produtos 
                                            SET quantidade = quantidade + ?, 
                                                valor_compra = ?, 
                                                valor_venda = ?, 
                                                grupo = ?, 
                                                fornecedor = ?
                                            WHERE produto = ?
                                        """, (item['quantidade'], item['valor_compra'], item['valor_venda'], item['grupo'], item['fornecedor'], item['produto']))
                                    else:
                                        cursor.execute("""
                                            INSERT INTO produtos (produto, grupo, fornecedor, quantidade, valor_compra, valor_venda)
                                            VALUES (?, ?, ?, ?, ?, ?)
                                        """, (item['produto'], item['grupo'], item['fornecedor'], item['quantidade'], item['valor_compra'], item['valor_venda']))
        
                            # Limpa o carrinho após gravar no banco
                            st.session_state.carrinho_compras = []
                            st.cache_data.clear()
                            st.success("✅ Todas as entradas foram registradas com sucesso no banco de dados!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao salvar compras no banco: {e}")
        
                with col_limpar:
                    if st.button("🗑️ Esvaziar Carrinho"):
                        st.session_state.carrinho_compras = []
                        st.rerun()
