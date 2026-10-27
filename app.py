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

def adequar_banco_e_migrar():
    try:
        cursor = conn.cursor()
        
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
                dias_licenca INTEGER DEFAULT 30
            )
        """)
        
        cursor.execute("PRAGMA table_info(empresas_dispositivos)")
        cols_emp = [col[1] for col in cursor.fetchall()]
        if "ativado" not in cols_emp:
            cursor.execute("ALTER TABLE empresas_dispositivos ADD COLUMN ativado INTEGER DEFAULT 0")
        if "dias_licenca" not in cols_emp:
            cursor.execute("ALTER TABLE empresas_dispositivos ADD COLUMN dias_licenca INTEGER DEFAULT 30")

        cursor.execute("CREATE TABLE IF NOT EXISTS produtos (id INTEGER PRIMARY KEY AUTOINCREMENT, produto TEXT)")
        for col in ["fornecedor", "grupo", "preco_compra", "preco_venda", "venda", "quantidade", "estoque", "codigo"]:
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
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT,
                cargo TEXT,
                salario REAL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pagamentos_funcionarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                colaborador TEXT,
                valor REAL,
                data_pagamento TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT,
                login TEXT UNIQUE,
                senha TEXT,
                cargo TEXT,
                perm_pdv INTEGER DEFAULT 1,
                perm_financeiro INTEGER DEFAULT 1,
                perm_registrar_venda INTEGER DEFAULT 1,
                perm_compras INTEGER DEFAULT 0,
                perm_cadastros INTEGER DEFAULT 1,
                perm_rh INTEGER DEFAULT 0,
                perm_usuarios INTEGER DEFAULT 0,
                perm_backup INTEGER DEFAULT 0,
                perm_contas_receber INTEGER DEFAULT 1,
                perm_estoque INTEGER DEFAULT 1,
                perm_configuracoes INTEGER DEFAULT 0
            )
        """)

        conn.commit()
    except Exception as e:
        pass

adequar_banco_e_migrar()

# --- DISPOSITIVO E IDENTIFICADOR ÚNICO FIXO ---
if "device_id" not in st.query_params or not st.query_params["device_id"]:
    st.query_params["device_id"] = "padrao_rey_da_cebola"
device_id = st.query_params["device_id"]

# Carrega e valida persistência da licença diretamente na Base de Dados
df_emp_dev = carregar_dados(f"SELECT * FROM empresas_dispositivos WHERE device_id = '{device_id}'")
if df_emp_dev.empty:
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO empresas_dispositivos (device_id, nome_empresa, cnpj, ie, fone, endereco, ativado, dias_licenca)
        VALUES (?, 'REY DA CEBOLA', '19417439000142', '', '(99) 98501-6050', 'RUA CAIPIRA, Nº 174', 0, 30)
    """, (device_id,))
    conn.commit()
    df_emp_dev = carregar_dados(f"SELECT * FROM empresas_dispositivos WHERE device_id = '{device_id}'")

reg_emp = df_emp_dev.iloc[0] if not df_emp_dev.empty else {}
nome_empresa_header = str(reg_emp.get('nome_empresa', 'REY DA CEBOLA'))

# Garante a ativação persistente
dispositivo_esta_ativado = bool(reg_emp.get('ativado', 0) == 1)
dias_licenca_atual = int(reg_emp.get('dias_licenca', 30))

st.session_state["dispositivo_ativado"] = dispositivo_esta_ativado
st.session_state["dias_licenca"] = dias_licenca_atual

# --- OUTROS ESTADOS DE SESSÃO ---
if 'autenticado' not in st.session_state:
    st.session_state['autenticado'] = False

if 'usuario_logado' not in st.session_state:
    st.session_state['usuario_logado'] = ""

if 'login_efetuado' not in st.session_state:
    st.session_state['login_efetuado'] = ""

if 'cargo_logado' not in st.session_state:
    st.session_state['cargo_logado'] = ""

if 'permissoes_usuario' not in st.session_state:
    st.session_state['permissoes_usuario'] = {}

if 'carrinho_pdv' not in st.session_state:
    st.session_state.carrinho_pdv = []

if "carrinho_cliente" not in st.session_state:
    st.session_state.carrinho_cliente = []

# --- ESTILO VISUAL METÁLICO ---
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

# --- PAINEL LATERAL (DEV) ---
with st.sidebar.expander("⚙️ Gerador de Chaves (Dev)"):
    senha_dev = st.text_input("Senha Mestre Dev", type="password", key="pwd_dev_topo")
    if senha_dev == "13142715":
        tipo_plano = st.selectbox("Tipo de Chave:", ["Teste (7 Dias)", "Mensal (30 Dias)", "Anual (365 Dias)"], key="select_tipo_plano_dev")
        doc_cliente = st.text_input("CNPJ ou CPF do Cliente:", key="doc_dev_topo_doc")
        if st.button("Gerar Chave", key="btn_dev_topo_acao"):
            if doc_cliente.strip():
                sufixo_tipo = "TESTE" if "Teste" in tipo_plano else ("MENSAL" if "Mensal" in tipo_plano else "ANUAL")
                doc_limpo = ''.join(filter(str.isdigit, str(doc_cliente)))
                hash_hex = hashlib.md5((doc_limpo + "REY_CEBOLA_2026" + sufixo_tipo).encode()).hexdigest().upper()
                st.code(f"CRM-{sufixo_tipo}-{hash_hex[:4]}-{hash_hex[4:8]}-{hash_hex[8:12]}", language="text")
                st.success("Chave gerada com sucesso!")

st.sidebar.title("🔑 Acesso ao Sistema")
st.sidebar.radio("Selecione o Perfil:", ["🔒 Administração / Vendedor"], key="perfil_principal_radio")
st.sidebar.markdown("---")

if st.session_state.get('dispositivo_ativado', False):
    st.sidebar.success("🟢 Dispositivo Ativado")
else:
    st.sidebar.error("🔴 Dispositivo Não Ativado")
st.sidebar.markdown("---")

# ==========================================
# ECRÃ DE LOGIN OU INTERFACE PRINCIPAL
# ==========================================
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
                st.session_state['permissoes_usuario'] = {
                    "pdv": 1, "financeiro": 1, "registrar_venda": 1, "compras": 1,
                    "cadastros": 1, "rh": 1, "usuarios": 1, "backup": 1,
                    "contas_receber": 1, "estoque": 1, "configuracoes": 1
                }
                st.success("Login efetuado com sucesso!")
                st.rerun()
            else:
                try:
                    cursor = conn.cursor()
                    cursor.execute("SELECT id, usuario, login, senha, cargo, perm_pdv, perm_financeiro, perm_registrar_venda, perm_compras, perm_cadastros, perm_rh, perm_usuarios, perm_backup, perm_contas_receber, perm_estoque, perm_configuracoes FROM usuarios WHERE LOWER(TRIM(login)) = ? AND senha = ?", (usuario_input, senha_input))
                    user_row = cursor.fetchone()
                    cursor.close()
                    if user_row:
                        st.session_state['autenticado'] = True
                        st.session_state['login_efetuado'] = str(user_row[2] if user_row[2] else usuario_input)
                        st.session_state['usuario_logado'] = str(user_row[1] if user_row[1] else usuario_input)
                        st.session_state['cargo_logado'] = str(user_row[4] if user_row[4] else "Funcionário")
                        
                        def safe_int(val):
                            try: return int(val) if val is not None else 0
                            except: return 0

                        st.session_state['permissoes_usuario'] = {
                            "pdv": safe_int(user_row[5]),
                            "financeiro": safe_int(user_row[6]),
                            "registrar_venda": safe_int(user_row[7]),
                            "compras": safe_int(user_row[8]),
                            "cadastros": safe_int(user_row[9]),
                            "rh": safe_int(user_row[10]),
                            "usuarios": safe_int(user_row[11]),
                            "backup": safe_int(user_row[12]),
                            "contas_receber": safe_int(user_row[13]),
                            "estoque": safe_int(user_row[14]),
                            "configuracoes": safe_int(user_row[15])
                        }
                        st.success("Login efetuado com sucesso!")
                        st.rerun()
                    else:
                        st.error("❌ Usuário ou senha incorretos. Verifique os dados.")
                except Exception as e:
                    st.error(f"Erro ao autenticar: {e}")

else:
    # --- INTERFACE PRINCIPAL APÓS O LOGIN ---
    usr_exibicao = str(st.session_state.get('usuario_logado') or "Utilizador")
    login_atual = str(st.session_state.get('login_efetuado') or '').lower()
    
    st.sidebar.write(f"👤 **Utilizador:** `{usr_exibicao}`")
    
    if st.sidebar.button("🚪 Sair do Sistema"):
        st.session_state['autenticado'] = False
        st.session_state['usuario_logado'] = ""
        st.session_state['login_efetuado'] = ""
        st.session_state['cargo_logado'] = ""
        st.session_state['permissoes_usuario'] = {}
        st.rerun()

    # VERIFICAÇÃO DE MESTRE OU PERMISSÕES PERSONALIZADAS
    is_admin_master = (login_atual == "administrador" or st.session_state.get('cargo_logado') == "Administrador")
    perms = st.session_state.get('permissoes_usuario', {})

    opcoes_menu_disponiveis = []
    
    if is_admin_master or perms.get("pdv", 1) == 1:
        opcoes_menu_disponiveis.append("🛒 PDV — Frente de Caixa")
    if is_admin_master or perms.get("financeiro", 0) == 1:
        opcoes_menu_disponiveis.append("📊 Fechamento & Financeiro")
    if is_admin_master or perms.get("registrar_venda", 1) == 1:
        opcoes_menu_disponiveis.append("🛒 Registrar Venda")
    if is_admin_master or perms.get("compras", 0) == 1:
        opcoes_menu_disponiveis.append("📦 Entrada de Estoque (Compras)")
    if is_admin_master or perms.get("cadastros", 1) == 1:
        opcoes_menu_disponiveis.append("👥 Cadastros (Clientes / Fornecedores / Grupos)")
    if is_admin_master or perms.get("rh", 0) == 1:
        opcoes_menu_disponiveis.append("👥 Gestão de Recursos Humanos (RH)")
    if is_admin_master or perms.get("usuarios", 0) == 1:
        opcoes_menu_disponiveis.append("🔐 Gestão de Utilizadores e Logins")
    if is_admin_master or perms.get("backup", 0) == 1:
        opcoes_menu_disponiveis.append("💾 Backup e Restauração")
    if is_admin_master or perms.get("contas_receber", 1) == 1:
        opcoes_menu_disponiveis.append("💸 Contas a Receber")
    if is_admin_master or perms.get("estoque", 1) == 1:
        opcoes_menu_disponiveis.append("📦 Estoque de Produtos")
    if is_admin_master or perms.get("configuracoes", 0) == 1:
        opcoes_menu_disponiveis.append("🏢 Configurações da Empresa")

    if not opcoes_menu_disponiveis:
        opcoes_menu_disponiveis = ["🛒 PDV — Frente de Caixa"]

    menu_admin = st.sidebar.radio("Navegação", opcoes_menu_disponiveis, key="radio_menu_admin_opcoes")

    # -------------------------------------------------------------
    # 1. MÓDULO PDV — FRENTE DE CAIXA
    # -------------------------------------------------------------
    if menu_admin == "🛒 PDV — Frente de Caixa":
        col_tit_pdv, col_modo_pdv = st.columns([2, 1], gap="small")
        with col_tit_pdv:
            st.markdown(f"### 🛒 PDV — Frente de Caixa — {nome_empresa_header} | 👤 Utilizador: {usr_exibicao}")
        with col_modo_pdv:
            modo_pdv_selecionado = st.radio(
                "⚡ Alternar Modo do Sistema:",
                ["Modo Simples", "Modo Completo"],
                horizontal=True,
                key="radio_modo_pdv_topo"
            )
        is_simples = (modo_pdv_selecionado == "Modo Simples")

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

        def obter_dados_produto(nome_prod):
            if not df_prod_pdv.empty and nome_prod in lista_produtos_pdv:
                p_row = df_prod_pdv[df_prod_pdv['produto'] == nome_prod].iloc[0]
                val_v = float(p_row.get('valor_venda', 0.0) or p_row.get('venda', 0.0) or 0.0)
                cod_prod = str(p_row.get('codigo', ''))
                return val_v, str(p_row.get('fornecedor', '')), str(p_row.get('grupo', '')), cod_prod
            return 0.0, "", "", ""

        def obter_produto_por_codigo(cod):
            if not df_prod_pdv.empty and 'codigo' in df_prod_pdv.columns:
                match = df_prod_pdv[df_prod_pdv['codigo'].astype(str).str.strip() == str(cod).strip()]
                if not match.empty:
                    return str(match.iloc[0]['produto'])
            return ""

        total_geral_carrinho = sum(item['valor_total'] for item in st.session_state.carrinho_pdv) if st.session_state.carrinho_pdv else 0.0
        st.markdown(f"### 🛒 Itens Lançados no Carrinho | Subtotal / Total Geral: **R$ {total_geral_carrinho:,.2f}**")

        if st.session_state.carrinho_pdv:
            df_carrinho = pd.DataFrame(st.session_state.carrinho_pdv)
            df_exibicao = df_carrinho[['codigo', 'produto', 'quantidade', 'valor_unitario', 'valor_total']].copy()
            df_exibicao.columns = ['Cód. Prod', 'Produto', 'Qtd', 'Preço Unit.', 'Total Itens']
            
            st.dataframe(df_exibicao, use_container_width=True, height=240)

            col_b1, col_b2 = st.columns(2)
            with col_b1:
                if st.button("❌ Limpar Carrinho", use_container_width=True, key="btn_limpar_cart_alin"):
                    st.session_state.carrinho_pdv = []
                    st.rerun()
            with col_b2:
                if st.button("🟢 Finalizar Venda", type="primary", use_container_width=True, key="btn_fin_venda_alin"):
                    if not df_caixa_aberto.empty:
                        cursor = conn.cursor()
                        sessao_id = int(df_caixa_aberto.iloc[0]['id'])
                        data_venda = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        vendedor_atual = usr_exibicao

                        for item in st.session_state.carrinho_pdv:
                            cursor.execute("""
                                INSERT INTO vendas (cliente, produto, fornecedor, grupo, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, status, tipo, data, vendedor)
                                VALUES (?, ?, ?, ?, ?, ?, ?, 'Dinheiro', ?, 'Concluído', 'VENDA', ?, ?)
                            """, ("Cliente Balcão", item['produto'], item['fornecedor'], item['grupo'], item['quantidade'], item['valor_unitario'], item['valor_total'], item['valor_total'], data_venda, vendedor_atual))

                        cursor.execute("INSERT INTO caixa_movimentacoes (sessao_id, tipo, valor, descricao, data) VALUES (?, 'VENDA', ?, ?, ?)",
                                       (sessao_id, float(total_geral_carrinho), f"Venda PDV por {vendedor_atual}", data_venda))
                        conn.commit()
                        st.session_state.carrinho_pdv = []
                        st.success(f"✅ Venda de R$ {total_geral_carrinho:.2f} concluída com sucesso!")
                        st.rerun()
                    else:
                        st.error("Abra o caixa antes de finalizar.")
        else:
            st.info("Nenhum item lançado no carrinho ainda.")

        col_bus1, col_bus2 = st.columns([1, 1], gap="medium")
        with col_bus1:
            codigo_barras_input = st.text_input("Código de Barras (Leitor / Digitação)", key="input_cod_barras_pdv")
        with col_bus2:
            prod_por_codigo = ""
            if codigo_barras_input.strip():
                prod_por_codigo = obter_produto_por_codigo(codigo_barras_input.strip())
                if prod_por_codigo:
                    st.success(f"🎯 Produto: **{prod_por_codigo}**")
                else:
                    st.warning("⚠️ Código não encontrado.")

            idx_padrao = 0
            if prod_por_codigo in lista_produtos_pdv:
                idx_padrao = lista_produtos_pdv.index(prod_por_codigo) + 1

            prod_selecionado = st.selectbox("Pesquisar / Selecionar Produto", [""] + lista_produtos_pdv, index=idx_padrao, key="sel_prod_pdv_alin")

        val_venda_sug, forn_sug, grupo_sug, cod_sug = obter_dados_produto(prod_selecionado) if prod_selecionado else (0.0, "", "", "")

        if is_simples:
            qtd_venda = 1.0
            preco_unit_venda = val_venda_sug
            subtotal_item =
