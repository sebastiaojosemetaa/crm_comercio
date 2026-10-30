import streamlit as st
import streamlit.components.v1 as components
import sqlite3
import pandas as pd
import base64
from datetime import datetime, date, timedelta
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
import io
import datetime as dt
import hashlib
import uuid
import string

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="CRM Comércio - REY DA CEBOLA", layout="wide", page_icon="🛍️")

# --- CONEXÃO E FUNÇÕES DE SUPORTE ---
def get_connection():
    return sqlite3.connect("crm_comercio.db", check_same_thread=False)

conn = get_connection()

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

def salvar_simples(tabela, coluna, valor):
    cursor = conn.cursor()
    cursor.execute(f"CREATE TABLE IF NOT EXISTS {tabela} (id INTEGER PRIMARY KEY AUTOINCREMENT, {coluna} TEXT)")
    cursor.execute(f"INSERT INTO {tabela} ({coluna}) VALUES (?)", (valor,))
    conn.commit()

def salvar_cliente_completo(nome, tel, doc, endereco, cidade):
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente TEXT, nome TEXT, cpf TEXT, endereco TEXT, email TEXT, fone TEXT, cidade TEXT
            )
        """)
        cursor.execute("""
            INSERT INTO clientes (cliente, nome, cpf, endereco, fone, cidade)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (nome, nome, doc, endereco, tel, cidade))
        conn.commit()
        return True, f"Cliente '{nome}' cadastrado com sucesso!"
    except Exception as e:
        return False, f"Erro ao cadastrar cliente: {e}"

def obter_dados_produto(nome_prod):
    try:
        df_prod_pdv = pd.read_sql_query("SELECT * FROM produtos", conn)
        if not df_prod_pdv.empty and 'produto' in df_prod_pdv.columns:
            match = df_prod_pdv[df_prod_pdv['produto'] == nome_prod]
            if not match.empty:
                p_row = match.iloc[0]
                val_v = float(p_row.get('valor_venda', 0.0) or p_row.get('venda', 0.0) or 0.0)
                cod_prod = str(p_row.get('codigo', ''))
                return val_v, str(p_row.get('fornecedor', '')), str(p_row.get('grupo', '')), cod_prod
    except Exception:
        pass
    return 0.0, "", "", ""

def obter_produto_por_codigo(cod):
    try:
        df_prod_pdv = pd.read_sql_query("SELECT * FROM produtos", conn)
        if not df_prod_pdv.empty and 'codigo' in df_prod_pdv.columns:
            match = df_prod_pdv[df_prod_pdv['codigo'].astype(str).str.strip() == str(cod).strip()]
            if not match.empty:
                return str(match.iloc[0]['produto'])
    except Exception:
        pass
    return ""

def adequar_banco_e_migrar():
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS produtos_promocao (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                produto TEXT,
                quantidade REAL,
                quantidade_minima REAL DEFAULT 1,
                preco_promocional REAL,
                grupo TEXT,
                fornecedor TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS empresas_dispositivos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT UNIQUE,
                nome_empresa TEXT,
                cnpj TEXT,
                ie TEXT,
                fone TEXT,
                endereco TEXT,
                ativado INTEGER DEFAULT 0,
                dias_licenca INTEGER DEFAULT 30,
                limite_dispositivos INTEGER DEFAULT 1
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chaves_pix (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo TEXT,
                chave TEXT,
                favorecido TEXT,
                cidade TEXT,
                padrao INTEGER DEFAULT 0
            )
        """)
        cursor.execute("CREATE TABLE IF NOT EXISTS produtos (id INTEGER PRIMARY KEY AUTOINCREMENT, produto TEXT)")
        for col in ["fornecedor", "grupo", "preco_compra", "preco_venda", "venda", "quantidade", "estoque", "codigo", "unidade"]:
            try: cursor.execute(f"ALTER TABLE produtos ADD COLUMN {col} TEXT")
            except Exception: pass

        cursor.execute("CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente TEXT)")
        for col in ["cliente", "nome", "cpf", "doc", "endereco", "email", "fone", "telefone", "cidade", "senha"]:
            try: cursor.execute(f"ALTER TABLE clientes ADD COLUMN {col} TEXT")
            except Exception: pass

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vendas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente TEXT, produto TEXT, data TEXT
            )
        """)
        for col in ["fornecedor", "grupo", "quantidade", "valor_venda", "valor_total", "forma_pagamento", "valor_recebido", "troco", "restante", "status", "tipo", "codigo", "codigo_venda", "vendedor"]:
            try: cursor.execute(f"ALTER TABLE vendas ADD COLUMN {col} TEXT")
            except Exception: pass

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pedidos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente TEXT, produto TEXT, fornecedor TEXT, grupo TEXT,
                quantidade REAL, valor_unitario REAL, valor_total REAL, status TEXT, data TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS caixa_sessoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT, data_abertura TEXT, data_fechamento TEXT,
                saldo_inicial REAL, saldo_final REAL, status TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS caixa_movimentacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT, sessao_id INTEGER, tipo TEXT,
                valor REAL, descricao TEXT, data TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS funcionarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, cargo TEXT, salario REAL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pagamentos_funcionarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT, colaborador TEXT, valor REAL, data_pagamento TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT, login TEXT UNIQUE, senha TEXT, cargo TEXT,
                perm_pdv INTEGER DEFAULT 1, perm_financeiro INTEGER DEFAULT 1,
                perm_registrar_venda INTEGER DEFAULT 1, perm_compras INTEGER DEFAULT 0,
                perm_cadastros INTEGER DEFAULT 1, perm_rh INTEGER DEFAULT 0,
                perm_usuarios INTEGER DEFAULT 0, perm_backup INTEGER DEFAULT 0,
                perm_contas_receber INTEGER DEFAULT 1, perm_estoque INTEGER DEFAULT 1,
                perm_configuracoes INTEGER DEFAULT 0
            )
        """)
        conn.commit()
    except Exception as e:
        pass

adequar_banco_e_migrar()

if "device_id" not in st.query_params or not st.query_params["device_id"]:
    st.query_params["device_id"] = str(uuid.uuid4())
device_id = st.query_params["device_id"]

df_emp_dev = carregar_dados(f"SELECT * FROM empresas_dispositivos WHERE device_id = '{device_id}'")
if df_emp_dev.empty:
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO empresas_dispositivos (device_id, nome_empresa, cnpj, ie, fone, endereco, ativado, dias_licenca, limite_dispositivos)
        VALUES (?, 'REY DA CEBOLA', '19417439000142', '', '(99) 98501-6050', 'RUA CAIPIRA, Nº 174', 0, 30, 1)
    """, (device_id,))
    conn.commit()
    df_emp_dev = carregar_dados(f"SELECT * FROM empresas_dispositivos WHERE device_id = '{device_id}'")

reg_emp = df_emp_dev.iloc[0] if not df_emp_dev.empty else {}
nome_empresa_header = str(reg_emp.get('nome_empresa', 'REY DA CEBOLA'))
dispositivo_esta_ativado = bool(reg_emp.get('ativado', 0) == 1)

if 'autenticado' not in st.session_state:
    st.session_state['autenticado'] = False
if 'usuario_logado' not in st.session_state:
    st.session_state['usuario_logado'] = ""
if 'login_efetuado' not in st.session_state:
    st.session_state['login_efetuado'] = ""
if 'cargo_logado' not in st.session_state:
    st.session_state['cargo_logado'] = ""
if 'carrinho_pdv' not in st.session_state:
    st.session_state.carrinho_pdv = []

st.markdown("""
<style>
    .stApp { background: linear-gradient(135deg, #e0e0e0 0%, #b0b0b0 100%) !important; color: #000000 !important; }
    div[data-testid="stVerticalBlock"] > div { background-color: #d8d8d8; border: 2px solid #a6a6a6; border-radius: 12px; padding: 12px; box-shadow: inset 1px 1px 3px #ffffff, 3px 3px 8px rgba(0,0,0,0.2); }
    div[data-baseweb="input"] { background-color: #ffffff !important; border: 2px solid #888888 !important; border-radius: 8px !important; }
    div[data-baseweb="input"] input { color: #000000 !important; font-weight: bold !important; font-size: 16px !important; }
    label, p, h1, h2, h3, h4, span { color: #111111 !important; font-weight: bold !important; }
    div[data-testid="stTable"], div[data-testid="stDataFrame"] { background-color: #ffffff !important; border-radius: 8px !important; border: 1px solid #999999 !important; }
    button[kind="primary"] { background-color: #008000 !important; color: #ffffff !important; font-size: 18px !important; font-weight: bold !important; border-radius: 8px !important; }
</style>
""", unsafe_allow_html=True)

st.sidebar.title("🔑 Acesso ao Sistema")
st.sidebar.radio("Selecione o Perfil:", ["🔒 Administração / Vendedor"], key="perfil_principal_radio")
st.sidebar.markdown("---")

if st.session_state.get('dispositivo_ativado', False):
    st.sidebar.success("🟢 Dispositivo Ativado")
else:
    st.sidebar.error("🔴 Dispositivo Não Ativado")
st.sidebar.markdown("---")

if not st.session_state['autenticado']:
    st.markdown("## 🔐 Autenticação do Sistema")
    with st.form("form_login_sistema"):
        usuario_input = st.text_input("Usuário / Login", key="login_usuario").strip().lower()
        senha_input = st.text_input("Senha", type="password", key="login_senha")
        btn_entrar = st.form_submit_button("🟢 Entrar no Sistema", type="primary", use_container_width=True)
        
        if btn_entrar:
            if (usuario_input == "administrador" and senha_input == "admin") or (usuario_input == "admin" and senha_input == "123456"):
                st.session_state['autenticado'] = True
                st.session_state['usuario_logado'] = "administrador"
                st.session_state['login_efetuado'] = "administrador"
                st.session_state['cargo_logado'] = "Administrador"
                st.success("Login efetuado com sucesso!")
                st.rerun()
            else:
                try:
                    cursor = conn.cursor()
                    cursor.execute("SELECT id, usuario, login, senha, cargo FROM usuarios WHERE LOWER(TRIM(login)) = ? AND senha = ?", (usuario_input, senha_input))
                    user_row = cursor.fetchone()
                    cursor.close()
                    if user_row:
                        st.session_state['autenticado'] = True
                        st.session_state['login_efetuado'] = str(user_row[2] if user_row[2] else usuario_input)
                        st.session_state['usuario_logado'] = str(user_row[1] if user_row[1] else usuario_input)
                        st.session_state['cargo_logado'] = str(user_row[4] if user_row[4] else "Funcionário")
                        st.success("Login efetuado com sucesso!")
                        st.rerun()
                    else:
                        st.error("❌ Usuário ou senha incorretos.")
                except Exception as e:
                    st.error(f"Erro ao autenticar: {e}")
else:
    usr_exibicao = str(st.session_state.get('usuario_logado') or "Utilizador")
    
    st.sidebar.write(f"👤 **Utilizador:** `{usr_exibicao}`")
    if st.sidebar.button("🚪 Sair do Sistema"):
        st.session_state['autenticado'] = False
        st.rerun()

    menu_admin = st.sidebar.radio("Navegação", [
        "🛒 PDV — Frente de Caixa",
        "📊 Fechamento & Financeiro",
        "🛒 Registrar Venda",
        "📦 Entrada de Estoque (Compras)",
        "👥 Cadastros (Clientes / Fornecedores / Grupos)",
        "👥 Gestão de Recursos Humanos (RH)",
        "🔐 Gestão de Utilizadores e Logins",
        "💾 Backup e Restauração",
        "💸 Contas a Receber",
        "📦 Estoque de Produtos",
        "🏢 Configurações da Empresa"
    ], key="radio_menu_admin_opcoes")

    # -------------------------------------------------------------
    # 1. MÓDULO PDV
    # -------------------------------------------------------------
    if menu_admin == "🛒 PDV — Frente de Caixa":
        st.subheader(f"🛒 PDV — Frente de Caixa — {nome_empresa_header} | 👤 Utilizador: {usr_exibicao}")
        
        df_caixa_aberto = carregar_dados("SELECT * FROM caixa_sessoes WHERE status = 'ABERTO'")
        if not df_caixa_aberto.empty:
            st.success("🟢 Caixa Aberto e Operacional")
        else:
            st.warning("⚠️ Atenção: Não há nenhum caixa aberto no momento.")

        try:
            df_prod_pdv = pd.read_sql_query("SELECT * FROM produtos", conn)
            lista_produtos_pdv = df_prod_pdv['produto'].tolist() if not df_prod_pdv.empty else []
        except Exception:
            lista_produtos_pdv = []
            df_prod_pdv = pd.DataFrame()

        total_geral_carrinho = sum(item['valor_total'] for item in st.session_state.carrinho_pdv) if st.session_state.carrinho_pdv else 0.0
        st.markdown(f"### 🛒 Itens Lançados no Carrinho | Total Geral: **R$ {total_geral_carrinho:,.2f}**")

        if st.session_state.carrinho_pdv:
            df_carrinho = pd.DataFrame(st.session_state.carrinho_pdv)
            st.dataframe(df_carrinho[['codigo', 'produto', 'quantidade', 'valor_unitario', 'valor_total']], use_container_width=True)

            if st.button("❌ Limpar Carrinho PDV", use_container_width=True):
                st.session_state.carrinho_pdv = []
                st.rerun()
        else:
            st.info("Nenhum item lançado no carrinho PDV ainda.")

        prod_selecionado = st.selectbox("Pesquisar / Selecionar Produto", [""] + lista_produtos_pdv, key="sel_prod_pdv_alin")
        val_venda_sug, forn_sug, grupo_sug, cod_sug = obter_dados_produto(prod_selecionado) if prod_selecionado else (0.0, "", "", "")

        col_q1, col_q2 = st.columns(2)
        with col_q1:
            qtd_venda = st.number_input("Qtd", min_value=0.01, value=1.0, step=1.0)
        with col_q2:
            preco_unit_venda = st.number_input("Preço Unit. (R$)", min_value=0.0, value=float(val_venda_sug), format="%.2f")

        subtotal_item = qtd_venda * preco_unit_venda
        if st.button("➕ [ Enter ] Incluir Produto no PDV", type="primary", use_container_width=True):
            if not prod_selecionado:
                st.error("Selecione um produto.")
            else:
                st.session_state.carrinho_pdv.append({
                    "codigo": cod_sug, "produto": prod_selecionado, "quantidade": qtd_venda,
                    "valor_unitario": preco_unit_venda, "valor_total": subtotal_item,
                    "fornecedor": forn_sug, "grupo": grupo_sug
                })
                st.success(f"✅ '{prod_selecionado}' adicionado!")
                st.rerun()

    # -------------------------------------------------------------
    # 2. FECHAMENTO & FINANCEIRO
    # -------------------------------------------------------------
    elif menu_admin == "📊 Fechamento & Financeiro":
        st.subheader(f"📊 Fechamento & Financeiro — {nome_empresa_header} | 👤 Utilizador: {usr_exibicao}")
        aba_caixa_atual, aba_historico_caixas = st.tabs(["🟢 Caixa Atual & Operação", "📚 Histórico de Caixas Fechados"])

        with aba_caixa_atual:
            df_caixa_atual = carregar_dados("SELECT * FROM caixa_sessoes WHERE status = 'ABERTO'")
            if df_caixa_atual.empty:
                st.info("O caixa encontra-se **FECHADO**. Insira o valor inicial para abri-lo.")
                with st.form("form_abrir_caixa"):
                    saldo_inicial = st.number_input("Saldo Inicial em Dinheiro (Troco)", min_value=0.0, step=10.0)
                    if st.form_submit_button("Abrir Caixa"):
                        cursor = conn.cursor()
                        cursor.execute("INSERT INTO caixa_sessoes (data_abertura, saldo_inicial, status) VALUES (?, ?, 'ABERTO')",
                                       (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), saldo_inicial))
                        conn.commit()
                        st.success("Caixa aberto com sucesso!")
                        st.rerun()
            else:
                sessao_id = int(df_caixa_atual.iloc[0]['id'])
                saldo_inicial = float(df_caixa_atual.iloc[0]['saldo_inicial'])
                st.success(f"🟢 **Caixa ABERTO** | Saldo Inicial: R$ {saldo_inicial:,.2f}")
                
                df_movs = carregar_dados(f"SELECT * FROM caixa_movimentacoes WHERE sessao_id = {sessao_id}")
                total_movimentado = df_movs['valor'].sum() if not df_movs.empty else 0.0
                st.metric("Total Movimentado neste Caixa", f"R$ {total_movimentado:,.2f}")

                with st.form("form_fechar_caixa"):
                    saldo_final = st.number_input("Conferência de Saldo Final (Dinheiro)", min_value=0.0, value=saldo_inicial + total_movimentado)
                    if st.form_submit_button("🔒 Fechar Caixa"):
                        cursor = conn.cursor()
                        cursor.execute("UPDATE caixa_sessoes SET data_fechamento = ?, saldo_final = ?, status = 'FECHADO' WHERE id = ?",
                                       (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), saldo_final, sessao_id))
                        conn.commit()
                        st.success("Caixa fechado com sucesso!")
                        st.rerun()

        with aba_historico_caixas:
            st.markdown("### 📚 Histórico de Caixas Fechados")
            df_historico = carregar_dados("SELECT * FROM caixa_sessoes WHERE status = 'FECHADO' ORDER BY id DESC")
            if not df_historico.empty:
                st.dataframe(df_historico, use_container_width=True)
            else:
                st.info("ℹ️ Nenhum caixa fechado registado no histórico.")

    # -------------------------------------------------------------
    # 3. REGISTRAR VENDA (VENDA BALCÃO)
    # -------------------------------------------------------------
    elif menu_admin == "🛒 Registrar Venda":
        st.subheader(f"🛒 Registrar Venda / Balcão — {nome_empresa_header} | 👤 Utilizador: {usr_exibicao}")
        
        if "carrinho_reg_venda" not in st.session_state:
            st.session_state.carrinho_reg_venda = []

        clientes_opt = carregar_coluna("clientes", "cliente") or ["Cliente Balcão"]
        lista_produtos_reg = carregar_coluna("produtos", "produto") or ["ABACATE", "CEBOLA CAIXA 1"]

        cliente_venda = st.selectbox("Cliente", clientes_opt, key="cliente_reg_venda_sel")
        st.markdown("---")

        col_r1, col_r2, col_r3 = st.columns([2, 1, 1], gap="medium")
        with col_r1:
            prod_selecionado_reg = st.selectbox("Selecione o Produto", [""] + lista_produtos_reg, key="sel_prod_reg_venda")
        with col_r2:
            qtd_reg = st.number_input("Quantidade", min_value=0.01, value=1.0, step=1.0, key="qtd_reg_venda")
        
        val_venda_sug, forn_sug, grupo_sug, cod_sug = obter_dados_produto(prod_selecionado_reg) if prod_selecionado_reg else (0.0, "", "", "")

        with col_r3:
            preco_unit_reg = st.number_input("Preço Unitário (R$)", min_value=0.0, value=float(val_venda_sug), format="%.2f", key="preco_unit_reg_venda")

        subtotal_reg = qtd_reg * preco_unit_reg
        st.markdown(f"**Subtotal do Item:** R$ {subtotal_reg:,.2f}")

        if st.button("➕ Incluir no Pedido / Carrinho", type="primary", use_container_width=True):
            if not prod_selecionado_reg:
                st.error("⚠️ Selecione um produto antes de incluir.")
            else:
                st.session_state.carrinho_reg_venda.append({
                    "codigo": cod_sug, "produto": prod_selecionado_reg, "quantidade": qtd_reg,
                    "valor_unitario": preco_unit_reg, "valor_total": subtotal_reg,
                    "fornecedor": forn_sug, "grupo": grupo_sug
                })
                st.success(f"✅ '{prod_selecionado_reg}' adicionado ao pedido!")
                st.rerun()

        st.markdown("---")
        if st.session_state.carrinho_reg_venda:
            st.markdown("### 📋 Itens Lançados no Pedido")
            df_carrinho_reg = pd.DataFrame(st.session_state.carrinho_reg_venda)
            df_exib_reg = pd.DataFrame()
            df_exib_reg['Produto'] = df_carrinho_reg['produto']
            df_exib_reg['Qtd'] = df_carrinho_reg['quantidade']
            df_exib_reg['Preço Unit.'] = df_carrinho_reg['valor_unitario'].apply(lambda x: f"R$ {float(x):,.2f}")
            df_exib_reg['Subtotal'] = df_carrinho_reg['valor_total'].apply(lambda x: f"R$ {float(x):,.2f}")
            
            st.dataframe(df_exib_reg, use_container_width=True)

            total_geral_reg = df_carrinho_reg['valor_total'].sum()
            st.markdown(f"### 💰 **Total Geral do Pedido: R$ {total_geral_reg:,.2f}**")

            col_A, col_B = st.columns(2)
            with col_A:
                idx_del = st.number_input("Índice do item para remover:", min_value=0, max_value=max(0, len(st.session_state.carrinho_reg_venda)-1), step=1, key="idx_rem_reg")
                if st.button("❌ Remover Item Selecionado", use_container_width=True):
                    if st.session_state.carrinho_reg_venda:
                        st.session_state.carrinho_reg_venda.pop(idx_del)
                        st.success("🗑️ Item removido!")
                        st.rerun()
            with col_B:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("🧹 Limpar Todo o Carrinho", use_container_width=True):
                    st.session_state.carrinho_reg_venda = []
                    st.success("🧹 Carrinho limpo!")
                    st.rerun()

            st.markdown("---")
            st.markdown("### 💳 Forma de Pagamento e Fechamento")
            forma_pagto_reg = st.selectbox("Forma de Pagamento", ["Dinheiro", "PIX", "Cartão de Crédito", "Cartão de Débito", "Fiado / Prazo"], key="pagto_reg_sel")
            
            v_rec_reg = total_geral_reg
            troco_reg = 0.0

            if forma_pagto_reg == "Dinheiro":
                v_rec_reg = st.number_input("Valor Recebido em Dinheiro (R$)", min_value=0.0, value=float(total_geral_reg), format="%.2f", key="v_rec_reg_din")
                troco_reg = max(0.0, v_rec_reg - total_geral_reg)
                st.markdown(f"**Troco:** R$ {troco_reg:,.2f}")

            if st.button("💾 Finalizar Venda Balcão", type="primary", use_container_width=True):
                try:
                    cursor = conn.cursor()
                    data_venda_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    cursor.execute("SELECT id FROM caixa_sessoes WHERE status = 'ABERTO' ORDER BY id DESC LIMIT 1")
                    sessao_aberta = cursor.fetchone()
                    sessao_id = sessao_aberta[0] if sessao_aberta else 1

                    for item in st.session_state.carrinho_reg_venda:
                        cursor.execute("""
                            INSERT INTO vendas (
                                cliente, produto, fornecedor, grupo, quantidade, 
                                valor_venda, valor_total, forma_pagamento, 
                                valor_recebido, troco, status, tipo, data, vendedor
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Concluído', 'VENDA', ?, ?)
                        """, (
                            cliente_venda, item['produto'], item['fornecedor'], item['grupo'], 
                            item['quantidade'], item['valor_unitario'], item['valor_total'], 
                            forma_pagto_reg, v_rec_reg, troco_reg, data_venda_atual, usr_exibicao
                        ))

                        cursor.execute("""
                            UPDATE produtos 
                            SET quantidade = quantidade - ? 
                            WHERE UPPER(TRIM(produto)) = UPPER(TRIM(?))
                        """, (item['quantidade'], item['produto']))

                    cursor.execute(
                        "INSERT INTO caixa_movimentacoes (sessao_id, tipo, valor, descricao, data) VALUES (?, 'VENDA', ?, ?, ?)",
                        (sessao_id, float(total_geral_reg), f"Venda Balcão ({forma_pagto_reg}) - Cliente: {cliente_venda}", data_venda_atual)
                    )
                    conn.commit()

                    st.session_state.carrinho_reg_venda = []
                    st.success(f"🎉 Venda Balcão de **R$ {total_geral_reg:,.2f}** concluída e estoque atualizado!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Erro ao finalizar venda: {e}")
        else:
            st.info("ℹ️ Nenhum item adicionado ao pedido/carrinho ainda.")

    # -------------------------------------------------------------
    # 4. ENTRADA DE ESTOQUE (COMPRAS)
    # -------------------------------------------------------------
    elif menu_admin == "📦 Entrada de Estoque (Compras)":
        st.subheader("📦 Entrada de Estoque (Compras)")
        if "carrinho_compras" not in st.session_state:
            st.session_state.carrinho_compras = []

        produtos_opt = carregar_coluna("produtos", "produto") or ["ABACATE", "AMEIXA IMPORTADA"]
        fornecedores_opt = carregar_coluna("fornecedores", "fornecedor") or ["BAHIA"]
        grupos_opt = carregar_coluna("grupos", "grupo") or ["GERAL"]
        unidades_opt = ["KG", "CAIXA", "UNIDADE", "METRO", "LITRO", "PACOTE", "SACO", "GRAMAS"]

        col1, col2, col3 = st.columns(3)
        with col1:
            prod_compra = st.selectbox("Selecione o Produto", produtos_opt, key="prod_compra_sel")
            forn_compra = st.selectbox("Fornecedor", fornecedores_opt, key="forn_compra_sel")
        with col2:
            grp_compra = st.selectbox("Grupo", grupos_opt, key="grp_compra_sel")
            unidade_medida = st.selectbox("Unidade de Medida", unidades_opt, key="unidade_medida_sel")
        with col3:
            qtd_compra = st.number_input("Quantidade", min_value=0.01, value=6.0, key="qtd_compra_num")
            pr_compra = st.number_input("Preço Compra Unitário (R$)", min_value=0.0, value=90.0, format="%.2f", key="pr_compra_form")

        if 'margem_perc' not in st.session_state:
            st.session_state.margem_perc = 30.0
        if 'preco_venda' not in st.session_state:
            st.session_state.preco_venda = pr_compra * (1 + (st.session_state.margem_perc / 100))
        if 'ultimo_preco_compra' not in st.session_state:
            st.session_state.ultimo_preco_compra = pr_compra

        if pr_compra != st.session_state.ultimo_preco_compra:
            st.session_state.ultimo_preco_compra = pr_compra
            st.session_state.preco_venda = pr_compra * (1 + (st.session_state.margem_perc / 100))

        def atualizar_por_margem():
            m = st.session_state.widget_margem
            st.session_state.margem_perc = m
            st.session_state.preco_venda = pr_compra * (1 + (m / 100))

        def atualizar_por_preco():
            v = st.session_state.widget_venda
            st.session_state.preco_venda = v
            if pr_compra > 0:
                st.session_state.margem_perc = ((v - pr_compra) / pr_compra) * 100

        col_m1, col_m2 = st.columns(2)
        with col_m1:
            st.number_input("Margem de Lucro (%)", value=float(st.session_state.margem_perc), format="%.2f", key="widget_margem", on_change=atualizar_por_margem)
        with col_m2:
            st.number_input("Preço Venda Unitário (R$)", min_value=0.0, value=float(st.session_state.preco_venda), format="%.2f", key="widget_venda", on_change=atualizar_por_preco)

        st.success(f"🟢 Preço de Venda Ativo: **R$ {st.session_state.preco_venda:,.2f}** | Margem Atual: **{st.session_state.margem_perc:,.2f}%**")

        if st.button("🛒 Adicionar ao Carrinho de Compras", type="primary", use_container_width=True):
            st.session_state.carrinho_compras.append({
                "produto": prod_compra, "grupo": grp_compra, "fornecedor": forn_compra,
                "unidade": unidade_medida, "quantidade": qtd_compra, "valor_compra": pr_compra, "valor_venda": st.session_state.preco_venda
            })
            st.success(f"✅ '{prod_compra}' adicionado ao carrinho!")
            st.rerun()

        if st.session_state.carrinho_compras:
            st.markdown("### 📋 Itens no Carrinho de Compras")
            df_carrinho_compras = pd.DataFrame(st.session_state.carrinho_compras)
            st.dataframe(df_carrinho_compras, use_container_width=True)

            if st.button("💾 Finalizar Todas as Entradas", type="primary", use_container_width=True):
                cursor = conn.cursor()
                for item in st.session_state.carrinho_compras:
                    cursor.execute("SELECT id FROM produtos WHERE produto = ?", (item['produto'],))
                    if cursor.fetchone():
                        cursor.execute("""
                            UPDATE produtos 
                            SET quantidade = quantidade + ?, valor_compra = ?, valor_venda = ?, grupo = ?, fornecedor = ?, unidade = ?
                            WHERE produto = ?
                        """, (item['quantidade'], item['valor_compra'], item['valor_venda'], item['grupo'], item['fornecedor'], item['unidade'], item['produto']))
                    else:
                        cursor.execute("""
                            INSERT INTO produtos (produto, grupo, fornecedor, quantidade, valor_compra, valor_venda, unidade) 
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (item['produto'], item['grupo'], item['fornecedor'], item['quantidade'], item['valor_compra'], item['valor_venda'], item['unidade']))
                conn.commit()
                st.session_state.carrinho_compras = []
                st.success("✅ Estoque atualizado com sucesso!")
                st.rerun()

    # -------------------------------------------------------------
    # 5. CADASTROS
    # -------------------------------------------------------------
    elif menu_admin == "👥 Cadastros (Clientes / Fornecedores / Grupos)":
        st.subheader("👥 Cadastros (Clientes / Fornecedores / Grupos)")
        tab_cli, tab_forn, tab_grup = st.tabs(["👤 Clientes", "🏢 Fornecedores", "🏷️ Grupos"])

        with tab_cli:
            with st.form("form_cad_cli"):
                n_cli = st.text_input("Nome do Cliente")
                t_cli = st.text_input("Telefone")
                if st.form_submit_button("Salvar Cliente"):
                    if n_cli.strip():
                        salvar_cliente_completo(n_cli, t_cli, "", "", "")
                        st.success("Cliente cadastrado com sucesso!")
                        st.rerun()
            st.dataframe(carregar_dados("SELECT * FROM clientes"), use_container_width=True)

        with tab_forn:
            with st.form("form_cad_forn"):
                n_forn = st.text_input("Nome do Fornecedor")
                if st.form_submit_button("Salvar Fornecedor"):
                    salvar_simples("fornecedores", "fornecedor", n_forn.upper())
                    st.success("Fornecedor cadastrado com sucesso!")
                    st.rerun()
            st.dataframe(carregar_dados("SELECT * FROM fornecedores"), use_container_width=True)

        with tab_grup:
            with st.form("form_cad_grup"):
                n_grup = st.text_input("Nome do Grupo")
                if st.form_submit_button("Salvar Grupo"):
                    salvar_simples("grupos", "grupo", n_grup.upper())
                    st.success("Grupo cadastrado com sucesso!")
                    st.rerun()
            st.dataframe(carregar_dados("SELECT * FROM grupos"), use_container_width=True)

    # -------------------------------------------------------------
    # 6. ESTOQUE DE PRODUTOS
    # -------------------------------------------------------------
    elif menu_admin == "📦 Estoque de Produtos":
        st.subheader("📦 Estoque de Produtos e Promoções")
        tab_estoque_geral, tab_deposito_promo = st.tabs(["📋 Estoque Geral", "🏷️ Depósito / Produtos para Promoção"])
        
        with tab_estoque_geral:
            st.markdown("### 📋 Produtos no Estoque Geral")
            df_prods = carregar_dados("SELECT * FROM produtos")
            if not df_prods.empty:
                st.dataframe(df_prods, use_container_width=True)
            else:
                st.info("ℹ️ Nenhum produto cadastrado no estoque geral.")

        with tab_deposito_promo:
            st.markdown("### 🏷️ Produtos para Promoção")
            df_promo = carregar_dados("SELECT * FROM produtos_promocao")
            if not df_promo.empty:
                st.dataframe(df_promo, use_container_width=True)
            else:
                st.info("ℹ️ Nenhum produto promocional registado.")
