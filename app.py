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
import unicodedata

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

    # TABELA DE PRODUTOS EM PROMOÇÃO
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
    cursor.execute("PRAGMA table_info(produtos_promocao)")
    cols_promo = [col[1] for col in cursor.fetchall()]
    if "quantidade_minima" not in cols_promo:
        try: cursor.execute("ALTER TABLE produtos_promocao ADD COLUMN quantidade_minima REAL DEFAULT 1")
        except Exception: pass
    
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
    
    # TABELA DE CHAVES PIX MULTIPLAS
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

    cursor.execute("PRAGMA table_info(empresas_dispositivos)")
    cols_emp = [col[1] for col in cursor.fetchall()]
    if "ativado" not in cols_emp:
        cursor.execute("ALTER TABLE empresas_dispositivos ADD COLUMN ativado INTEGER DEFAULT 0")
    if "dias_licenca" not in cols_emp:
        cursor.execute("ALTER TABLE empresas_dispositivos ADD COLUMN dias_licenca INTEGER DEFAULT 30")
    if "limite_dispositivos" not in cols_emp:
        cursor.execute("ALTER TABLE empresas_dispositivos ADD COLUMN limite_dispositivos INTEGER DEFAULT 1")

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
    
    cursor.execute("PRAGMA table_info(usuarios)")
    cols_usr = [col[1] for col in cursor.fetchall()]
    colunas_necessarias_usr = {
        "usuario": "TEXT", "login": "TEXT", "senha": "TEXT", "cargo": "TEXT",
        "perm_pdv": "INTEGER DEFAULT 1", "perm_financeiro": "INTEGER DEFAULT 1",
        "perm_registrar_venda": "INTEGER DEFAULT 1", "perm_compras": "INTEGER DEFAULT 0",
        "perm_cadastros": "INTEGER DEFAULT 1", "perm_rh": "INTEGER DEFAULT 0",
        "perm_usuarios": "INTEGER DEFAULT 0", "perm_backup": "INTEGER DEFAULT 0",
        "perm_contas_receber": "INTEGER DEFAULT 1", "perm_estoque": "INTEGER DEFAULT 1",
        "perm_configuracoes": "INTEGER DEFAULT 0"
    }
    for coluna, tipo in colunas_necessarias_usr.items():
        if coluna not in cols_usr:
            try: cursor.execute(f"ALTER TABLE usuarios ADD COLUMN {coluna} {tipo}")
            except Exception: pass

    conn.commit()
except Exception as e:
    pass


adequar_banco_e_migrar()

# --- DISPOSITIVO E IDENTIFICADOR ÚNICO REAL POR APARELHO ---

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
dias_licenca_atual = int(reg_emp.get('dias_licenca', 30))
limite_dispositivos_atual = int(reg_emp.get('limite_dispositivos', 1))

st.session_state["dispositivo_ativado"] = dispositivo_esta_ativado
st.session_state["dias_licenca"] = dias_licenca_atual
st.session_state["limite_dispositivos"] = limite_dispositivos_atual

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

if 'tela_checkout_ativa' not in st.session_state:
st.session_state.tela_checkout_ativa = False

# --- ESTILO VISUAL METÁLICO ---

st.markdown("""

""", unsafe_allow_html=True)

# --- PAINEL LATERAL (DEV) — GERADOR DE CHAVES ---

with st.sidebar.expander("⚙️ Gerador de Chaves (Dev)"):
senha_dev = st.text_input("Senha Mestre Dev", type="password", key="pwd_dev_topo")
if senha_dev == "13142715":
tipo_plano = st.selectbox("Tipo de Chave:", ["Teste (7 Dias)", "Mensal (30 Dias)", "Anual (365 Dias)"], key="select_tipo_plano_dev")
doc_cliente = st.text_input("CNPJ ou CPF do Cliente:", key="doc_dev_topo_doc")
limite_dev_topo = st.number_input("Limite de Dispositivos:", min_value=1, max_value=50, value=1, key="limite_dev_topo_num")

    if st.button("Gerar Chave", key="btn_dev_topo_acao"):
        if doc_cliente.strip():
            sufixo_tipo = "TESTE" if "Teste" in tipo_plano else ("MENSAL" if "Mensal" in tipo_plano else "ANUAL")
            doc_limpo = ''.join(filter(str.isdigit, str(doc_cliente)))
            
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE empresas_dispositivos 
                SET limite_dispositivos = ? 
                WHERE REPLACE(REPLACE(REPLACE(cnpj, '.', ''), '/', ''), '-', '') = ?
            """, (limite_dev_topo, doc_limpo))
            conn.commit()

            base_hash_str = doc_limpo + "REY_CEBOLA_2026" + sufixo_tipo + str(limite_dev_topo)
            hash_hex = hashlib.md5(base_hash_str.encode()).hexdigest().upper()
            st.code(f"CRM-{sufixo_tipo}-{limite_dev_topo}D-{hash_hex[:4]}-{hash_hex[4:8]}", language="text")
            st.success(f"Chave gerada! Limite definido: {limite_dev_topo} dispositivo(s).")


st.sidebar.title("🔑 Acesso ao Sistema")
st.sidebar.radio("Selecione o Perfil:", ["🔒 Administração / Vendedor"], key="perfil_principal_radio")
st.sidebar.markdown("---")

if st.session_state.get('dispositivo_ativado', False):
st.sidebar.success("🟢 Dispositivo Ativado")
else:
st.sidebar.error("🔴 Dispositivo Não Ativado")
st.sidebar.markdown("---")

==========================================

ECRÃ DE LOGIN OU INTERFACE PRINCIPAL

==========================================

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

# --- TRAVA DE SEGURANÇA DE LICENÇA POR DISPOSITIVO ---
df_check_ativado = carregar_dados(f"SELECT ativado FROM empresas_dispositivos WHERE device_id = '{device_id}'")
status_disp_real = int(df_check_ativado.iloc[0]['ativado']) if not df_check_ativado.empty else 0

if status_disp_real == 0 and menu_admin != "🏢 Configurações da Empresa":
    st.error("🚫 **ACESSO BLOQUEADO:** Este dispositivo não está ativado na licença. Vá em **Configurações da Empresa** para inserir a chave de ativação.")
    st.stop()

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
        
        st.dataframe(df_exibicao, use_container_width=True, height=200)

        col_b1, col_b2 = st.columns(2)
        with col_b1:
            if st.button("❌ Limpar Carrinho", use_container_width=True, key="btn_limpar_cart_alin"):
                st.session_state.carrinho_pdv = []
                st.session_state.tela_checkout_ativa = False
                st.rerun()
        with col_b2:
            if st.button("🟢 Finalizar Venda (Pagamento)", type="primary", use_container_width=True, key="btn_fin_venda_alin"):
                if not df_caixa_aberto.empty:
                    st.session_state.tela_checkout_ativa = True
                    st.rerun()
                else:
                    st.error("Abra o caixa antes de finalizar.")

        # --- TELA DE CHECKOUT / FORMA DE PAGAMENTO DINÂMICA ---
        if st.session_state.get('tela_checkout_ativa', False):
            st.markdown("---")
            st.markdown("### 💳 Ecrã de Pagamento / Checkout")
            
            forma_pagto = st.radio(
                "Selecione a Forma de Pagamento:", 
                ["Dinheiro", "Cartão Débito", "Cartão Crédito", "Fiado", "Parcelado", "Pix"], 
                horizontal=True, 
                key="radio_forma_pagto_checkout"
            )

            valor_recebido = 0.0
            troco = 0.0
            detalhes_pagto = forma_pagto

            if forma_pagto == "Dinheiro":
                valor_recebido = st.number_input("Valor Recebido em Dinheiro (R$)", min_value=0.0, value=total_geral_carrinho, format="%.2f", key="input_val_recebido_dinheiro")
                troco = valor_recebido - total_geral_carrinho
                if troco >= 0:
                    st.success(f"💵 **Troco a Devolver:** R$ {troco:,.2f}")
                else:
                    st.warning(f"⚠️ Falta R$ {abs(troco):,.2f} para completar o pagamento.")

            elif forma_pagto == "Cartão Crédito":
                parcelas = st.selectbox("Número de Parcelas:", ["1x (À vista)", "2x", "3x", "4x", "5x", "6x", "10x", "12x"], key="select_parcelas_cartao")
                detalhes_pagto = f"Cartão Crédito ({parcelas})"
                st.info(f"💳 Pagamento selecionado: **Cartão Crédito em {parcelas}**")

            elif forma_pagto == "Cartão Débito":
                st.info("💳 Pagamento via **Cartão de Débito** à vista.")

            elif forma_pagto == "Fiado":
                cliente_fiado = st.selectbox("Selecione o Cliente para o Fiado:", carregar_coluna("clientes", "nome") or ["Cliente Balcão"], key="select_cliente_fiado_pdv")
                detalhes_pagto = f"Fiado ({cliente_fiado})"
                st.warning(f"⚠️ Esta venda será registada como **Fiado** para o cliente: **{cliente_fiado}**")

            elif forma_pagto == "Parcelado":
                num_parc = st.number_input("Quantidade de Parcelas Próprias:", min_value=2, max_value=24, value=2, step=1, key="num_parc_proprias")
                valor_parc = total_geral_carrinho / num_parc
                detalhes_pagto = f"Parcelado ({num_parc}x de R$ {valor_parc:,.2f})"
                st.info(f"📅 Venda dividida em **{num_parc}x** de **R$ {valor_parc:,.2f}**.")

            elif forma_pagto == "Pix":
                st.markdown("#### 📱 Pague com Pix (QR Code Oficial)")
                
                df_chaves_db = carregar_dados("SELECT * FROM chaves_pix")
                
                if df_chaves_db.empty:
                    st.info("ℹ️ Nenhuma chave cadastrada em Configurações. Usando o CNPJ padrão da empresa.")
                    lista_opcoes_pix = ["CNPJ Padrão: 19417439000142"]
                    dict_chaves = {"CNPJ Padrão: 19417439000142": {"tipo": "CNPJ", "chave": "19417439000142", "favorecido": nome_empresa_header, "cidade": "SAO LUIS"}}
                else:
                    dict_chaves = {}
                    lista_opcoes_pix = []
                    for idx, row in df_chaves_db.iterrows():
                        rotulo = f"[{row['tipo']}] {row['chave']} - {row['favorecido']}"
                        lista_opcoes_pix.append(rotulo)
                        dict_chaves[rotulo] = row

                chave_escolhida_label = st.selectbox("Escolha a Chave Pix para esta venda:", lista_opcoes_pix, key="select_chave_pix_venda")
                dados_chave_atual = dict_chaves[chave_escolhida_label]

                pix_key_val = str(dados_chave_atual['chave'])
                fav_val = str(dados_chave_atual['favorecido'])
                cidade_val = str(dados_chave_atual['cidade'])
                tipo_val = str(dados_chave_atual['tipo'])

                st.info("Aponte a câmara do telemóvel para o QR Code abaixo ou utilize a chave selecionada.")

                def gerar_payload_pix(pix_key, nome_recebedor, cidade, valor_str, tipo_chave_pix):
                    def montar_campo(id_campo, valor_campo):
                        return f"{id_campo}{len(valor_campo):02d}{valor_campo}"

                    if tipo_chave_pix in ["CNPJ", "CPF"]:
                        chave_tratada = ''.join(filter(str.isdigit, pix_key))
                    elif tipo_chave_pix == "Celular":
                        digitos = ''.join(filter(str.isdigit, pix_key))
                        if digitos.startswith("55") and len(digitos) >= 12:
                            chave_tratada = "+" + digitos
                        else:
                            chave_tratada = "+55" + digitos
                    else:
                        chave_tratada = pix_key.strip()

                    def limpar_texto(texto):
                        nfkd = unicodedata.normalize('NFKD', texto)
                        return "".join([c for c in nfkd if not unicodedata.combining(c)]).upper()

                    nome_tratado = limpar_texto(nome_recebedor)[:25]
                    cidade_tratada = limpar_texto(cidade)[:15]

                    gui = montar_campo("00", "br.gov.bcb.pix")
                    chave_f = montar_campo("01", chave_tratada)
                    merchant_account = montar_campo("26", gui + chave_f)

                    payload = (
                        montar_campo("00", "01") +
                        montar_campo("01", "12") +
                        merchant_account +
                        montar_campo("52", "0000") +
                        montar_campo("53", "986") +
                        montar_campo("54", valor_str) +
                        montar_campo("58", "BR") +
                        montar_campo("60", nome_tratado) +
                        montar_campo("61", cidade_tratada) +
                        montar_campo("62", montar_campo("05", "***")) +
                        "6304"
                    )

                    crc = 0xFFFF
                    for char in payload:
                        crc ^= (ord(char) << 8)
                        for _ in range(8):
                            if crc & 0x8000:
                                crc = (crc << 1) ^ 0x1021
                            else:
                                crc = crc << 1
                            crc &= 0xFFFF

                    return payload + f"{crc:04X}"

                valor_formatado = f"{total_geral_carrinho:.2f}"
                
                pix_payload = gerar_payload_pix(
                    pix_key=pix_key_val,
                    nome_recebedor=fav_val,
                    cidade=cidade_val,
                    valor_str=valor_formatado,
                    tipo_chave_pix=tipo_val
                )
                
                qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={pix_payload}"
                
                col_qr_img, col_qr_info = st.columns([1, 2], gap="medium")
                with col_qr_img:
                    st.image(qr_url, width=190, caption="Escaneie o QR Code")
                with col_qr_info:
                    st.markdown(f"**Valor a Pagar:** R$ {total_geral_carrinho:,.2f}")
                    st.markdown(f"**Favorecido:** `{fav_val}`")
                    st.markdown(f"**Chave ({tipo_val}):** `{pix_key_val}`")
                    st.text_input("Chave Pix Copia e Cola:", value=pix_payload, key="input_pix_copia_cola_detalhe")
                    st.success("🟢 Aguardando confirmação do pagamento Pix...")

            col_chk1, col_chk2 = st.columns(2)
            with col_chk1:
                if st.button("⬅️ Voltar ao PDV", use_container_width=True, key="btn_voltar_pdv_check"):
                    st.session_state.tela_checkout_ativa = False
                    st.rerun()
            with col_chk2:
                if st.button("✅ Confirmar e Concluir Venda", type="primary", use_container_width=True, key="btn_confirmar_pagto_final"):
                    cursor = conn.cursor()
                    sessao_id = int(df_caixa_aberto.iloc[0]['id'])
                    data_venda = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    vendedor_atual = usr_exibicao
                    
                    v_rec = valor_recebido if forma_pagto == "Dinheiro" else total_geral_carrinho
                    t_val = troco if (forma_pagto == "Dinheiro" and troco >= 0) else 0.0

                    for item in st.session_state.carrinho_pdv:
                        cursor.execute("""
                            INSERT INTO vendas (
                                cliente, produto, fornecedor, grupo, quantidade, 
                                valor_venda, valor_total, forma_pagamento, 
                                valor_recebido, troco, status, tipo, data, vendedor
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Concluído', 'VENDA', ?, ?)
                        """, (
                            "Cliente Balcão", 
                            item['produto'], 
                            item['fornecedor'], 
                            item['grupo'], 
                            item['quantidade'], 
                            item['valor_unitario'], 
                            item['valor_total'], 
                            detalhes_pagto, 
                            v_rec, 
                            t_val, 
                            data_venda, 
                            vendedor_atual
                        ))

                        # Baixa no estoque promocional se pertencer à promoção
                        if item.get('grupo') == "PROMOÇÃO":
                            cursor.execute("""
                                UPDATE produtos_promocao 
                                SET quantidade = quantidade - ? 
                                WHERE UPPER(TRIM(produto)) = UPPER(TRIM(?)) AND quantidade >= ?
                            """, (item['quantidade'], item['produto'], item['quantidade']))

                    cursor.execute(
                        "INSERT INTO caixa_movimentacoes (sessao_id, tipo, valor, descricao, data) VALUES (?, 'VENDA', ?, ?, ?)",
                        (sessao_id, float(total_geral_carrinho), f"Venda PDV ({detalhes_pagto}) por {vendedor_atual}", data_venda)
                    )
                    conn.commit()
                    
                    st.session_state.carrinho_pdv = []
                    st.session_state.tela_checkout_ativa = False
                    st.success(f"🎉 Venda de R$ {total_geral_carrinho:,.2f} via **{detalhes_pagto}** concluída com sucesso!")
                    st.rerun()

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

    # --- VERIFICAÇÃO DE PROMOÇÃO INTELIGENTE (QUANTIDADE MÍNIMA) ---
    prod_limpo_sel = str(prod_selecionado).strip().replace("'", "''")
    df_promo_ativo = carregar_dados(f"SELECT * FROM produtos_promocao WHERE UPPER(TRIM(produto)) = UPPER(TRIM('{prod_limpo_sel}')) AND quantidade > 0")
    
    preco_unit_venda = val_venda_sug
    is_promocional = False
    qtd_minima_promo = 0.0

    if not df_promo_ativo.empty:
        row_p = df_promo_ativo.iloc[0]
        preco_promo = float(row_p['preco_promocional'])
        qtd_minima_promo = float(row_p['quantidade_minima'])
        
        if is_simples:
            if 1.0 >= qtd_minima_promo:
                preco_unit_venda = preco_promo
                is_promocional = True

    if is_simples:
        subtotal_item = preco_unit_venda
        if is_promocional:
            st.info(f"🏷️ **Promoção Ativa!** Preço promocional aplicado: R$ {preco_unit_venda:,.2f}")
        elif not df_promo_ativo.empty:
            st.info(f"ℹ️ Promoção disponível a partir de {qtd_minima_promo} un/kg (Preço normal aplicado).")

        if st.button("➕ [ Enter ] Incluir Produto", type="primary", use_container_width=True, key="btn_inc_prod_simples"):
            if not prod_selecionado:
                st.error("Selecione um produto.")
            else:
                st.session_state.carrinho_pdv.append({
                    "codigo": cod_sug, "produto": prod_selecionado, "quantidade": 1.0,
                    "valor_unitario": preco_unit_venda, "valor_total": subtotal_item,
                    "fornecedor": forn_sug, "grupo": "PROMOÇÃO" if is_promocional else grupo_sug
                })
                st.success(f"✅ '{prod_selecionado}' adicionado!")
                st.rerun()
    else:
        col_q1, col_q2, col_q3 = st.columns([1, 1, 2], gap="medium")
        with col_q1:
            qtd_venda = st.number_input("Qtd", min_value=0.01, value=1.0, step=1.0, key="qtd_prod_pdv_alin")
        
        with col_q2:
            # Validação dinâmica da quantidade mínima para desconto no modo completo
            preco_calculado_final = val_venda_sug
            if not df_promo_ativo.empty:
                row_p = df_promo_ativo.iloc[0]
                qtd_minima_promo = float(row_p['quantidade_minima'])
                if qtd_venda >= qtd_minima_promo:
                    preco_calculado_final = float(row_p['preco_promocional'])
                    is_promocional = True
            
            preco_unit_venda = st.number_input("Preço Unit. (R$)", min_value=0.0, value=float(preco_calculado_final), format="%.2f")
        
        with col_q3:
            subtotal_item = qtd_venda * preco_unit_venda
            if is_promocional:
                st.success(f"🏷️ **Promoção Ativa!** (A partir de {qtd_minima_promo})")
            elif not df_promo_ativo.empty:
                st.info(f"ℹ️ Promoção a partir de {qtd_minima_promo} un/kg.")

            st.markdown(f"**Subtotal:** R$ {subtotal_item:,.2f}")
            if st.button("➕ [ Enter ] Incluir Produto", type="primary", use_container_width=True, key="btn_inc_prod_completo"):
                if not prod_selecionado:
                    st.error("Selecione um produto.")
                else:
                    st.session_state.carrinho_pdv.append({
                        "codigo": cod_sug, "produto": prod_selecionado, "quantidade": qtd_venda,
                        "valor_unitario": preco_unit_venda, "valor_total": subtotal_item,
                        "fornecedor": forn_sug, "grupo": "PROMOÇÃO" if is_promocional else grupo_sug
                    })
                    st.success(f"✅ '{prod_selecionado}' adicionado!")
                    st.rerun()

# -------------------------------------------------------------
# 2. MÓDULO FECHAMENTO & FINANCEIRO
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

            st.markdown("### 👥 Desempenho de Vendas por Utilizador")
            df_vendas_usuario = carregar_dados("""
                SELECT 
                    COALESCE(vendedor, 'Desconhecido') as Utilizador, 
                    COUNT(id) as Total_Vendas, 
                    SUM(valor_total) as Valor_Total 
                FROM vendas 
                WHERE tipo = 'VENDA' 
                GROUP BY vendedor
            """)
            
            if not df_vendas_usuario.empty:
                df_vendas_usuario.columns = ['Utilizador', 'Qtd. Vendas', 'Total Vendido (R$)']
                st.dataframe(df_vendas_usuario, use_container_width=True)
            else:
                st.info("ℹ️ Nenhuma venda registada por utilizador até o momento.")

            st.markdown("### 💳 Vendas Separadas por Forma de Pagamento")
            df_vendas_pagto = carregar_dados("""
                SELECT 
                    COALESCE(forma_pagamento, 'Não Informado') as Forma_Pagamento, 
                    COUNT(id) as Total_Vendas, 
                    SUM(valor_total) as Valor_Total 
                FROM vendas 
                WHERE tipo = 'VENDA' 
                GROUP BY forma_pagamento
            """)
            
            if not df_vendas_pagto.empty:
                df_vendas_pagto.columns = ['Forma de Pagamento', 'Qtd. Vendas', 'Total Arrecadado (R$)']
                st.dataframe(df_vendas_pagto, use_container_width=True)
            else:
                st.info("ℹ️ Nenhuma venda registada por forma de pagamento até o momento.")

            st.markdown("---")
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
            
            st.markdown("#### 🔍 Detalhes das Movimentações por Sessão de Caixa")
            id_sessao_consulta = st.selectbox("Selecione o ID do Caixa para ver detalhes:", df_historico['id'].tolist(), key="sel_id_sessao_hist")
            
            if id_sessao_consulta:
                df_movs_detalhe = carregar_dados(f"SELECT * FROM caixa_movimentacoes WHERE sessao_id = {id_sessao_consulta}")
                if not df_movs_detalhe.empty:
                    st.dataframe(df_movs_detalhe, use_container_width=True)
                else:
                    st.info("Nenhuma movimentação registada para este caixa.")
        else:
            st.info("ℹ️ Nenhum caixa fechado registado no histórico até o momento.")

# -------------------------------------------------------------
# 3. MÓDULO REGISTRAR VENDA
# -------------------------------------------------------------
elif menu_admin == "🛒 Registrar Venda":
    st.subheader(f"🛒 Registrar Venda / Pedido — {nome_empresa_header} | 👤 Utilizador: {usr_exibicao}")
    clientes_opt = carregar_coluna("clientes", "nome") or ["Cliente Balcão"]
    df_p_admin = carregar_dados("SELECT * FROM produtos")
    produtos_base = df_p_admin['produto'].tolist() if not df_p_admin.empty else ["ABACATE", "AMEIXA IMPORTADA"]
    
    cliente_ped = st.selectbox("Cliente", clientes_opt)
    prod_item = st.selectbox("Selecione o Produto", produtos_base)
    qtd_ped = st.number_input("Quantidade", min_value=0.01, value=1.0)
    v_venda_ped = st.number_input("Preço Unitário (R$)", min_value=0.0, value=10.0)

    if st.button("➕ Incluir no Pedido", type="primary"):
        st.session_state.carrinho_cliente.append({
            "produto": prod_item, "quantidade": qtd_ped, "valor_unitario": v_venda_ped, "valor_total": qtd_ped * v_venda_ped
        })
        st.success(f"'{prod_item}' incluído no pedido!")
        st.rerun()

    if st.session_state.carrinho_cliente:
        st.dataframe(pd.DataFrame(st.session_state.carrinho_cliente), use_container_width=True)
        if st.button("🔴 Finalizar e Salvar Pedido", type="primary"):
            cursor = conn.cursor()
            data_agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for item in st.session_state.carrinho_cliente:
                cursor.execute("""
                    INSERT INTO pedidos (cliente, produto, quantidade, valor_unitario, valor_total, status, data)
                    VALUES (?, ?, ?, ?, ?, 'Pendente', ?)
                """, (cliente_ped, item['produto'], item['quantidade'], item['valor_unitario'], item['valor_total'], data_agora))
            conn.commit()
            st.session_state.carrinho_cliente = []
            st.success("✅ Pedido gravado com sucesso!")
            st.rerun()

# -------------------------------------------------------------
# 4. MÓDULO ENTRADA DE ESTOQUE (COMPRAS)
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
        st.number_input(
            "Margem de Lucro (%)", 
            value=float(st.session_state.margem_perc), 
            format="%.2f", 
            key="widget_margem",
            on_change=atualizar_por_margem
        )
    with col_m2:
        st.number_input(
            "Preço Venda Unitário (R$)", 
            min_value=0.0, 
            value=float(st.session_state.preco_venda), 
            format="%.2f", 
            key="widget_venda",
            on_change=atualizar_por_preco
        )

    st.success(f"🟢 Preço de Venda Ativo: **R$ {st.session_state.preco_venda:,.2f}** | Margem Atual: **{st.session_state.margem_perc:,.2f}%**")

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🛒 Adicionar ao Carrinho de Compras", type="primary", use_container_width=True):
        st.session_state.carrinho_compras.append({
            "produto": prod_compra, 
            "grupo": grp_compra, 
            "fornecedor": forn_compra,
            "unidade": unidade_medida,
            "quantidade": qtd_compra, 
            "valor_compra": pr_compra, 
            "valor_venda": st.session_state.preco_venda
        })
        st.success(f"✅ '{prod_compra}' adicionado ao carrinho!")
        st.rerun()

    if st.session_state.carrinho_compras:
        st.markdown("### 📋 Itens no Carrinho de Compras")
        
        for item in st.session_state.carrinho_compras:
            if 'unidade' not in item:
                item['unidade'] = 'UNIDADE'

        df_carrinho_compras = pd.DataFrame(st.session_state.carrinho_compras)
        
        df_exib_compras = pd.DataFrame()
        df_exib_compras['Produto'] = df_carrinho_compras['produto']
        df_exib_compras['Grupo'] = df_carrinho_compras['grupo']
        df_exib_compras['Fornecedor'] = df_carrinho_compras['fornecedor']
        df_exib_compras['Unidade'] = df_carrinho_compras['unidade']
        df_exib_compras['Qtd'] = df_carrinho_compras['quantidade']
        df_exib_compras['Preço Compra'] = df_carrinho_compras['valor_compra'].apply(lambda x: f"R$ {float(x):,.2f}")
        df_exib_compras['Preço Venda'] = df_carrinho_compras['valor_venda'].apply(lambda x: f"R$ {float(x):,.2f}")
        
        st.dataframe(df_exib_compras, use_container_width=True)

        col_del1, col_del2, col_del3 = st.columns(3)
        with col_del1:
            item_remover_idx = st.number_input("Índice do item para remover:", min_value=0, max_value=max(0, len(st.session_state.carrinho_compras)-1), step=1, key="num_idx_remover_compra")
            if st.button("❌ Remover Item Selecionado", use_container_width=True):
                if len(st.session_state.carrinho_compras) > 0:
                    st.session_state.carrinho_compras.pop(item_remover_idx)
                    st.success("🗑️ Item removido do carrinho!")
                    st.rerun()
        with col_del2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🧹 Limpar Todo o Carrinho", use_container_width=True):
                st.session_state.carrinho_compras = []
                st.success("🧹 Carrinho limpo com sucesso!")
                st.rerun()
        with col_del3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("💾 Finalizar Todas as Entradas", type="primary", use_container_width=True):
                cursor = conn.cursor()
                
                cursor.execute("PRAGMA table_info(produtos)")
                cols_prod = [c[1] for c in cursor.fetchall()]
                if "unidade" not in cols_prod:
                    try: cursor.execute("ALTER TABLE produtos ADD COLUMN unidade TEXT")
                    except Exception: pass

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
                st.success("✅ Entrada registrada no banco de dados e estoque atualizado com sucesso!")
                st.rerun()
    else:
        st.info("ℹ️ Nenhum item adicionado ao carrinho de compras ainda.")

# -------------------------------------------------------------
# 5. MÓDULO CADASTROS
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
# 6. MÓDULO RH (RECURSOS HUMANOS)
# -------------------------------------------------------------
elif menu_admin == "👥 Gestão de Recursos Humanos (RH)":
    st.subheader("👥 Gestão de Recursos Humanos (RH)")
    aba_colab, aba_pag = st.tabs(["👥 Colaboradores", "💸 Registar Pagamentos / Vales"])

    with aba_colab:
        sub_tab_cad, sub_tab_ger = st.tabs(["➕ Cadastrar Novo Colaborador", "🛠️ Editar / Excluir Colaboradores"])

        with sub_tab_cad:
            with st.form("form_cad_func"):
                n_func = st.text_input("Nome Completo")
                c_func = st.text_input("Cargo")
                s_func = st.number_input("Salário Base (R$)", value=1412.00)
                if st.form_submit_button("Salvar Colaborador", type="primary"):
                    if n_func.strip():
                        cursor = conn.cursor()
                        cursor.execute("INSERT INTO funcionarios (nome, cargo, salario) VALUES (?, ?, ?)", (n_func, c_func, s_func))
                        conn.commit()
                        st.success("Colaborador cadastrado com sucesso!")
                        st.rerun()
                    else:
                        st.error("Preencha o nome do colaborador.")

            st.markdown("### 📋 Colaboradores Cadastrados")
            st.dataframe(carregar_dados("SELECT * FROM funcionarios"), use_container_width=True)

        with sub_tab_ger:
            st.markdown("### 📋 Selecione um Colaborador para Editar ou Excluir")
            df_funcs_all = carregar_dados("SELECT * FROM funcionarios")
            if not df_funcs_all.empty:
                df_funcs_all['label'] = df_funcs_all['id'].astype(str) + " - " + df_funcs_all['nome'] + " (" + df_funcs_all['cargo'] + ")"
                lista_labels = df_funcs_all['label'].tolist()
                
                colab_selecionado_edit = st.selectbox("Selecione o Colaborador", lista_labels, key="sel_colab_edit_key")
                
                f_row = df_funcs_all[df_funcs_all['label'] == colab_selecionado_edit].iloc[0]
                
                with st.form("form_edit_colaborador"):
                    ed_nome_f = st.text_input("Nome Completo", value=str(f_row.get('nome', '')))
                    ed_cargo_f = st.text_input("Cargo", value=str(f_row.get('cargo', '')))
                    ed_salario_f = st.number_input("Salário Base (R$)", value=float(f_row.get('salario', 1412.00)), format="%.2f")

                    col_btn_f1, col_btn_f2 = st.columns(2)
                    with col_btn_f1:
                        btn_salvar_alt_f = st.form_submit_button("✏️ Salvar / Alterar Colaborador", type="primary")
                    with col_btn_f2:
                        btn_excluir_f = st.form_submit_button("🗑️ Excluir Colaborador")

                    if btn_salvar_alt_f:
                        try:
                            cursor = conn.cursor()
                            cursor.execute("""
                                UPDATE funcionarios SET nome = ?, cargo = ?, salario = ? WHERE id = ?
                            """, (ed_nome_f, ed_cargo_f, ed_salario_f, int(f_row['id'])))
                            conn.commit()
                            st.success("✅ Colaborador atualizado com sucesso!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao atualizar colaborador: {e}")

                    if btn_excluir_f:
                        try:
                            cursor = conn.cursor()
                            cursor.execute("DELETE FROM funcionarios WHERE id = ?", (int(f_row['id']),))
                            conn.commit()
                            st.success("🗑️ Colaborador excluído com sucesso!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao excluir colaborador: {e}")
            else:
                st.info("Nenhum colaborador cadastrado.")

    with aba_pag:
        funcs = carregar_coluna("funcionarios", "nome")
        if funcs:
            colab_sel = st.selectbox("Colaborador", funcs)
            val_pag = st.number_input("Valor Pagamento (R$)", min_value=0.0)
            if st.button("Registar Pagamento"):
                cursor = conn.cursor()
                cursor.execute("INSERT INTO pagamentos_funcionarios (colaborador, valor, data_pagamento) VALUES (?, ?, ?)",
                               (colab_sel, val_pag, datetime.now().strftime("%Y-%m-%d")))
                conn.commit()
                st.success("Pagamento efetuado com sucesso!")
                st.rerun()

# -------------------------------------------------------------
# 7. GESTÃO DE UTILIZADORES E LOGINS
# -------------------------------------------------------------
elif menu_admin == "🔐 Gestão de Utilizadores e Logins":
    st.subheader("🔐 Gestão de Logins e Permissões de Acesso aos Menus")
    
    tab_novo_usr, tab_ger_usr = st.tabs(["➕ Cadastrar Novo Utilizador", "🛠️ Editar / Excluir Utilizadores"])

    with tab_novo_usr:
        with st.form("form_cad_usuario_novo"):
            st.markdown("### Preencha os dados do novo funcionário")
            col_u1, col_u2 = st.columns(2)
            with col_u1:
                nome_usuario = st.text_input("Nome Completo do Funcionário")
                login_usuario = st.text_input("Login de Acesso (ex: joao.silva)")
            with col_u2:
                senha_usuario = st.text_input("Senha de Acesso", type="password")
                cargo_usuario = st.selectbox("Cargo / Nível", ["Vendedor", "Caixa", "Gerente", "Administrador"])

            st.markdown("#### 🎯 Permissões de Acesso (Menus Laterais)")
            col_p1, col_p2, col_p3 = st.columns(3)
            with col_p1:
                p_pdv = st.checkbox("🛒 PDV — Frente de Caixa", value=True)
                p_fin = st.checkbox("📊 Fechamento & Financeiro", value=False)
                p_reg_v = st.checkbox("🛒 Registrar Venda", value=True)
                p_comp = st.checkbox("📦 Entrada de Estoque", value=False)
            with col_p2:
                p_cad = st.checkbox("👥 Cadastros (Clientes/Forn)", value=True)
                p_rh = st.checkbox("👥 Recursos Humanos (RH)", value=False)
                p_usr = st.checkbox("🔐 Gestão de Utilizadores", value=False)
                p_bkp = st.checkbox("💾 Backup e Restauração", value=False)
            with col_p3:
                p_cr = st.checkbox("💸 Contas a Receber", value=True)
                p_est = st.checkbox("📦 Estoque de Produtos", value=True)
                p_cfg = st.checkbox("🏢 Configurações Empresa", value=False)

            if st.form_submit_button("💾 Salvar Novo Utilizador", type="primary"):
                if not login_usuario.strip() or not senha_usuario.strip():
                    st.error("Preencha o login e a senha.")
                else:
                    try:
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT INTO usuarios (
                                usuario, login, senha, cargo, 
                                perm_pdv, perm_financeiro, perm_registrar_venda, perm_compras, 
                                perm_cadastros, perm_rh, perm_usuarios, perm_backup, 
                                perm_contas_receber, perm_estoque, perm_configuracoes
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            nome_usuario, login_usuario.strip().lower(), senha_usuario, cargo_usuario,
                            1 if p_pdv else 0, 1 if p_fin else 0, 1 if p_reg_v else 0, 1 if p_comp else 0,
                            1 if p_cad else 0, 1 if p_rh else 0, 1 if p_usr else 0, 1 if p_bkp else 0,
                            1 if p_cr else 0, 1 if p_est else 0, 1 if p_cfg else 0
                        ))
                        conn.commit()
                        st.success(f"✅ Utilizador '{login_usuario}' criado com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar utilizador (talvez o login já exista): {e}")

    with tab_ger_usr:
        st.markdown("### 📋 Selecione um Utilizador para Editar ou Excluir")
        df_users_all = carregar_dados("SELECT * FROM usuarios")
        if not df_users_all.empty:
            lista_logins = df_users_all['login'].tolist()
            user_selecionado_edit = st.selectbox("Selecione o Login do Utilizador", lista_logins, key="sel_user_edit_key")
            
            u_row = df_users_all[df_users_all['login'] == user_selecionado_edit].iloc[0]
            
            with st.form("form_edit_usuario"):
                ed_nome = st.text_input("Nome Completo", value=str(u_row.get('usuario', '')))
                ed_login = st.text_input("Login de Acesso", value=str(u_row.get('login', '')))
                ed_senha = st.text_input("Nova Senha (ou mantenha a atual)", value=str(u_row.get('senha', '')))
                ed_cargo = st.selectbox("Cargo", ["Vendedor", "Caixa", "Gerente", "Administrador"], index=["Vendedor", "Caixa", "Gerente", "Administrador"].index(str(u_row.get('cargo', 'Vendedor'))) if str(u_row.get('cargo', 'Vendedor')) in ["Vendedor", "Caixa", "Gerente", "Administrador"] else 0)

                st.markdown("#### 🎯 Atualizar Permissões de Acesso")
                ep_pdv = st.checkbox("🛒 PDV — Frente de Caixa", value=bool(u_row.get('perm_pdv', 1)))
                ep_fin = st.checkbox("📊 Fechamento & Financeiro", value=bool(u_row.get('perm_financeiro', 0)))
                ep_reg_v = st.checkbox("🛒 Registrar Venda", value=bool(u_row.get('perm_registrar_venda', 1)))
                ep_comp = st.checkbox("📦 Entrada de Estoque", value=bool(u_row.get('perm_compras', 0)))
                ep_cad = st.checkbox("👥 Cadastros (Clientes/Forn)", value=bool(u_row.get('perm_cadastros', 1)))
                ep_rh = st.checkbox("👥 Recursos Humanos (RH)", value=bool(u_row.get('perm_rh', 0)))
                ep_usr = st.checkbox("🔐 Gestão de Utilizadores", value=bool(u_row.get('perm_usuarios', 0)))
                ep_bkp = st.checkbox("💾 Backup e Restauração", value=bool(u_row.get('perm_backup', 0)))
                ep_cr = st.checkbox("💸 Contas a Receber", value=bool(u_row.get('perm_contas_receber', 1)))
                ep_est = st.checkbox("📦 Estoque de Produtos", value=bool(u_row.get('perm_estoque', 1)))
                ep_cfg = st.checkbox("🏢 Configurações Empresa", value=bool(u_row.get('perm_configuracoes', 0)))

                col_btn_ed1, col_btn_ed2 = st.columns(2)
                with col_btn_ed1:
                    btn_salvar_alt = st.form_submit_button("✏️ Salvar / Alterar Utilizador", type="primary")
                with col_btn_ed2:
                    btn_excluir_usr = st.form_submit_button("🗑️ Excluir Utilizador")

                if btn_salvar_alt:
                    try:
                        cursor = conn.cursor()
                        cursor.execute("""
                            UPDATE usuarios SET 
                                usuario = ?, login = ?, senha = ?, cargo = ?,
                                perm_pdv = ?, perm_financeiro = ?, perm_registrar_venda = ?, perm_compras = ?,
                                perm_cadastros = ?, perm_rh = ?, perm_usuarios = ?, perm_backup = ?,
                                perm_contas_receber = ?, perm_estoque = ?, perm_configuracoes = ?
                            WHERE id = ?
                        """, (
                            ed_nome, ed_login.strip().lower(), ed_senha, ed_cargo,
                            1 if ep_pdv else 0, 1 if ep_fin else 0, 1 if ep_reg_v else 0, 1 if ep_comp else 0,
                            1 if ep_cad else 0, 1 if ep_rh else 0, 1 if ep_usr else 0, 1 if ep_bkp else 0,
                            1 if ep_cr else 0, 1 if ep_est else 0, 1 if ep_cfg else 0, int(u_row['id'])
                        ))
                        conn.commit()
                        st.success("✅ Utilizador atualizado com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao atualizar utilizador: {e}")

                if btn_excluir_usr:
                    if ed_login.strip().lower() == "administrador":
                        st.error("❌ Não é permitido excluir o administrador principal do sistema.")
                    else:
                        try:
                            cursor = conn.cursor()
                            cursor.execute("DELETE FROM usuarios WHERE id = ?", (int(u_row['id']),))
                            conn.commit()
                            st.success("🗑️ Utilizador excluído com sucesso!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao excluir utilizador: {e}")
        else:
            st.info("Nenhum utilizador cadastrado além do administrador padrão.")

# -------------------------------------------------------------
# 8. BACKUP E RESTAURAÇÃO
# -------------------------------------------------------------
elif menu_admin == "💾 Backup e Restauração":
    st.subheader("💾 Central de Backup e Restauração")
    
    tab_bkp_down, tab_bkp_up = st.tabs(["📥 Baixar Backup", "📤 Restaurar Backup"])

    with tab_bkp_down:
        st.markdown("### 📥 Fazer Backup dos Dados Atualizados")
        st.info("Descarregue o ficheiro de cópia de segurança para guardar uma cópia do seu banco de dados.")
        try:
            with open("crm_comercio.db", "rb") as f:
                bytes_db = f.read()
            st.download_button(
                label="📥 Baixar Arquivo de Backup (.db)",
                data=bytes_db,
                file_name=f"backup_crm_{datetime.now().strftime('%Y-%m-%d')}.db",
                mime="application/octet-stream",
                type="primary"
            )
        except Exception as e:
            st.warning(f"Erro ao localizar o banco de dados: {e}")

    with tab_bkp_up:
        st.markdown("### 📤 Restaurar Ficheiro de Backup (.db)")
        st.warning("⚠️ **ATENÇÃO:** A restauração irá substituir todos os dados atuais pelo conteúdo do ficheiro de backup selecionado.")
        
        uploaded_db = st.file_uploader("Selecione o ficheiro de backup (.db)", type=["db"])
        
        if uploaded_db is not None:
            if st.button("🔴 Confirmar e Restaurar Backup Agora", type="primary"):
                try:
                    conn.close()
                    with open("crm_comercio.db", "wb") as f:
                        f.write(uploaded_db.getbuffer())
                    
                    conn = get_connection()
                    st.success("🎉 Backup restaurado com sucesso! Recarregando o sistema...")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Erro ao restaurar o banco de dados: {e}")

# -------------------------------------------------------------
# 9. CONTAS A RECEBER
# -------------------------------------------------------------
elif menu_admin == "💸 Contas a Receber":
    st.subheader("💸 Contas a Receber")
    df_pedidos_pendentes = carregar_dados("SELECT * FROM pedidos WHERE status = 'Pendente'")
    if not df_pedidos_pendentes.empty:
        st.dataframe(df_pedidos_pendentes, use_container_width=True)
        st.metric("Total Pendente a Receber", f"R$ {df_pedidos_pendentes['valor_total'].sum():,.2f}")
    else:
        st.info("Nenhuma conta pendente a receber no momento.")

# -------------------------------------------------------------
# 10. ESTOQUE E PROMOÇÕES
# -------------------------------------------------------------
elif menu_admin == "📦 Estoque de Produtos":
    st.subheader("📦 Estoque de Produtos e Promoções")
    
    tab_estoque_geral, tab_deposito_promo = st.tabs(["📋 Estoque Geral", "🏷️ Depósito / Produtos para Promoção"])
    
    with tab_estoque_geral:
        st.markdown("### 📋 Produtos no Estoque Geral")
        df_prods = carregar_dados("SELECT * FROM produtos")
        
        if not df_prods.empty:
            df_exib_est = pd.DataFrame()
            df_exib_est['ID'] = df_prods['id']
            df_exib_est['Código'] = df_prods['codigo']
            df_exib_est['Produto'] = df_prods['produto']
            df_exib_est['Qtd. Estoque'] = df_prods['quantidade']
            df_exib_est['Preço Compra (R$)'] = df_prods['valor_compra'].apply(lambda x: f"R$ {float(x):,.2f}" if pd.notnull(x) and str(x).strip() != '' else "R$ 0,00")
            df_exib_est['Preço Venda (R$)'] = df_prods['valor_venda'].apply(lambda x: f"R$ {float(x):,.2f}" if pd.notnull(x) and str(x).strip() != '' else "R$ 0,00")
            df_exib_est['Grupo'] = df_prods['grupo']
            df_exib_est['Fornecedor'] = df_prods['fornecedor']
            
            st.dataframe(df_exib_est, use_container_width=True)

            st.markdown("---")
            st.markdown("### 🛠️ Editar ou Excluir Produto do Estoque")
            
            df_prods['label_prod'] = df_prods['id'].astype(str) + " - " + df_prods['produto'].astype(str)
            lista_prods_edit = df_prods['label_prod'].tolist()
            
            prod_selecionado_est = st.selectbox("Selecione o Produto para Gerenciar:", lista_prods_edit, key="select_prod_gerenciar_est")
            
            p_row_est = df_prods[df_prods['label_prod'] == prod_selecionado_est].iloc[0]
            id_prod_atual = int(p_row_est['id'])

            with st.form("form_editar_produto_estoque"):
                col_e1, col_e2, col_e3 = st.columns(3)
                with col_e1:
                    ed_codigo = st.text_input("Código / Código de Barras", value=str(p_row_est.get('codigo', '') or ''))
                    ed_produto = st.text_input("Nome do Produto", value=str(p_row_est.get('produto', '') or ''))
                with col_e2:
                    ed_qtd = st.number_input("Quantidade em Estoque", value=float(p_row_est.get('quantidade', 0) or 0), step=1.0)
                    ed_pr_compra = st.number_input("Preço de Compra (R$)", value=float(p_row_est.get('valor_compra', 0.0) or 0.0), format="%.2f")
                with col_e3:
                    ed_pr_venda = st.number_input("Preço de Venda (R$)", value=float(p_row_est.get('valor_venda', 0.0) or 0.0), format="%.2f")
                    ed_grupo = st.selectbox("Grupo", carregar_coluna("grupos", "grupo") or ["GERAL"], index=0)

                col_btn_est1, col_btn_est2 = st.columns(2)
                with col_btn_est1:
                    btn_salvar_prod = st.form_submit_button("✏️ Salvar Alterações", type="primary", use_container_width=True)
                with col_btn_est2:
                    btn_excluir_prod = st.form_submit_button("🗑️ Excluir Produto", use_container_width=True)

                if btn_salvar_prod:
                    try:
                        cursor = conn.cursor()
                        cursor.execute("""
                            UPDATE produtos 
                            SET codigo = ?, produto = ?, quantidade = ?, valor_compra = ?, valor_venda = ?, grupo = ?
                            WHERE id = ?
                        """, (ed_codigo.strip(), ed_produto.strip().upper(), ed_qtd, ed_pr_compra, ed_pr_venda, ed_grupo, id_prod_atual))
                        conn.commit()
                        st.success(f"✅ Produto '{ed_produto}' atualizado com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Erro ao atualizar produto: {e}")

                if btn_excluir_prod:
                    try:
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM produtos WHERE id = ?", (id_prod_atual,))
                        conn.commit()
                        st.success(f"🗑️ Produto removido do estoque com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Erro ao excluir produto: {e}")
        else:
            st.info("ℹ️ Nenhum produto cadastrado no estoque geral.")

# -------------------------------------------------------------
# 11. CONFIGURAÇÕES
# -------------------------------------------------------------
elif menu_admin == "🏢 Configurações da Empresa":
    st.subheader("🏢 Configurações e Dados da Empresa")

    st.markdown("### 🔑 Ativação e Limite de Dispositivos")
    
    df_devs_count = carregar_dados("SELECT COUNT(*) as total FROM empresas_dispositivos WHERE ativado = 1")
    total_ativados = int(df_devs_count.iloc[0]['total']) if not df_devs_count.empty else 0
    
    limite_permitido = int(reg_emp.get('limite_dispositivos', 1))
    st.info(f"📊 **Status de Licença de Dispositivos:** {total_ativados} de {limite_permitido} dispositivo(s) autorizados.")

    if dispositivo_esta_ativado:
        dias_val = st.session_state.get('dias_licenca', 30)
        st.success(f"✅ Este dispositivo está **ATIVADO**! Licença válida por {dias_val} dias.")
        if st.button("🔄 Inserir Nova Chave / Renovar"):
            cursor = conn.cursor()
            cursor.execute("UPDATE empresas_dispositivos SET ativado = 0 WHERE device_id = ?", (device_id,))
            conn.commit()
            st.session_state['dispositivo_ativado'] = False
            st.rerun()
    else:
        if total_ativados >= limite_permitido:
            st.error(f"❌ Limite atingido! O limite máximo de {limite_permitido} dispositivo(s) já foi alcançado. Para ligar mais aparelhos, gere uma chave com um limite maior.")
        else:
            st.warning("⚠️ Insira a chave de ativação para liberar este dispositivo.")
            doc_atual = str(reg_emp.get('cnpj', '19417439000142'))
            st.info(f"Empresa Atual (CNPJ/CPF): `{doc_atual}`")

            chave_digitada = st.text_input("Chave de Ativação:", key="input_chave_ativacao_config")

            if st.button("🔓 Ativar Este Dispositivo", type="primary", key="btn_ativar_dispositivo_config"):
                apenas_digitos = ''.join(filter(str.isdigit, str(doc_atual)))
                chave_limpa = str(chave_digitada).strip().upper()

                sucesso = False
                dias_validade = 0
                limite_extraido = 1

                for sufixo, dias in [("TESTE", 7), ("MENSAL", 30), ("ANUAL", 365)]:
                    for lim_test in range(1, 20):
                        base_hash_str = apenas_digitos + "REY_CEBOLA_2026" + sufixo + str(lim_test)
                        hash_hex = hashlib.md5(base_hash_str.encode()).hexdigest().upper()
                        chave_esperada = f"CRM-{sufixo}-{lim_test}D-{hash_hex[:4]}-{hash_hex[4:8]}"

                        if chave_limpa == chave_esperada:
                            sucesso = True
                            dias_validade = dias
                            limite_extraido = lim_test
                            break
                    if sucesso:
                        break

                if sucesso:
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE empresas_dispositivos 
                        SET ativado = 1, dias_licenca = ?, limite_dispositivos = ? 
                        WHERE device_id = ?
                    """, (dias_validade, limite_extraido, device_id))
                    conn.commit()

                    st.session_state['dispositivo_ativado'] = True
                    st.session_state['dias_licenca'] = dias_validade
                    st.session_state['limite_dispositivos'] = limite_extraido
                    st.success(f"🎉 Dispositivo ativado com sucesso! Validade: {dias_validade} dias (Limite: {limite_extraido} disp.).")
                    st.rerun()
                else:
                    st.error("❌ Chave inválida para este CNPJ/CPF ou limite de dispositivos incorreto.")

    st.markdown("---")
    with st.form("form_cfg_emp"):
        st.markdown("### 📝 Dados Gerais e Limites da Empresa")
        nome_emp = st.text_input("Razão Social / Nome Fantasia", value=str(reg_emp.get('nome_empresa', 'REY DA CEBOLA')))
        cnpj_emp = st.text_input("CNPJ ou CPF", value=str(reg_emp.get('cnpj', '19417439000142')))
        tel_emp = st.text_input("Telefone de Contato", value=str(reg_emp.get('fone', '(99) 98501-6050')))
        end_emp = st.text_input("Endereço Completo", value=str(reg_emp.get('endereco', 'RUA CAIPIRA, Nº 174')))
        lim_disp = st.number_input("💻 Limite Máximo de Dispositivos Permitidos", min_value=1, max_value=50, value=int(reg_emp.get('limite_dispositivos', 1)))
        
        if st.form_submit_button("💾 Salvar Configurações", type="primary"):
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO empresas_dispositivos (device_id, nome_empresa, cnpj, fone, endereco, ativado, dias_licenca, limite_dispositivos)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (device_id, nome_emp, cnpj_emp, tel_emp, end_emp, 1 if st.session_state.get('dispositivo_ativado') else 0, st.session_state.get('dias_licenca', 30), lim_disp))
            conn.commit()
            st.session_state['limite_dispositivos'] = lim_disp
            st.success("✅ Configurações e limites salvos com sucesso!")
            st.rerun()

    # --- GESTÃO DE CHAVES PIX MÚLTIPLAS NAS CONFIGURAÇÕES ---
    st.markdown("---")
    st.markdown("### 💳 Gestão de Chaves Pix")
    
    with st.form("form_cad_chave_pix"):
        col_cp1, col_cp2 = st.columns(2)
        with col_cp1:
            tipo_chave = st.selectbox("Tipo de Chave", ["CNPJ", "CPF", "Celular", "E-mail", "Chave Aleatória"])
            valor_chave = st.text_input("Valor da Chave (ex: seu e-mail, celular ou CNPJ)")
        with col_cp2:
            favorecido_chave = st.text_input("Nome do Favorecido", value=nome_empresa_header)
            cidade_chave = st.text_input("Cidade", value="SAO LUIS")
        
        if st.form_submit_button("➕ Cadastrar Nova Chave Pix", type="primary"):
            if valor_chave.strip():
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO chaves_pix (tipo, chave, favorecido, cidade)
                    VALUES (?, ?, ?, ?)
                """, (tipo_chave, valor_chave.strip(), favorecido_chave.strip(), cidade_chave.strip()))
                conn.commit()
                st.success("✅ Chave Pix cadastrada com sucesso!")
                st.rerun()
            else:
                st.error("Preencha o valor da chave Pix.")

    df_chaves_cadastradas = carregar_dados("SELECT * FROM chaves_pix")
    if not df_chaves_cadastradas.empty:
        st.markdown("#### 📋 Chaves Pix Já Cadastradas")
        st.dataframe(df_chaves_cadastradas, use_container_width=True)
        
        id_para_excluir = st.number_input("ID da Chave para Excluir (opcional):", min_value=0, step=1)
        if st.button("🗑️ Excluir Chave Selecionada"):
            if id_para_excluir > 0:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM chaves_pix WHERE id = ?", (int(id_para_excluir),))
                conn.commit()
                st.success(f"Chave ID {id_para_excluir} excluída com sucesso!")
                st.rerun()
