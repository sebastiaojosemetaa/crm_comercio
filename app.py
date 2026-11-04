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
    return sqlite3.connect("crm_comercio.db", timeout=30.0, check_same_thread=False)

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
                dias_licenca INTEGER DEFAULT 30,
                limite_dispositivos INTEGER DEFAULT 1
            )
        """)
        
        # CONFIGURACAO INICIAL DA NFC-e (nao armazena certificado nem senhas)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS config_nfce (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                uf TEXT DEFAULT 'MA',
                ambiente TEXT DEFAULT 'Homologacao',
                serie TEXT DEFAULT '1',
                proximo_numero INTEGER DEFAULT 1,
                modelo TEXT DEFAULT '65',
                atualizado_em TEXT
            )
        """)
        cursor.execute("""
            INSERT OR IGNORE INTO config_nfce
                (id, uf, ambiente, serie, proximo_numero, modelo)
            VALUES (1, 'MA', 'Homologacao', '1', 1, '65')
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
        # Vincula cada movimento do caixa à venda que o originou.
        # A migração é compatível com bancos já existentes.
        cursor.execute("PRAGMA table_info(caixa_movimentacoes)")
        cols_mov_caixa = [col[1] for col in cursor.fetchall()]
        if "venda_id" not in cols_mov_caixa:
            cursor.execute("ALTER TABLE caixa_movimentacoes ADD COLUMN venda_id INTEGER")

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
if 'carrinho_compras' not in st.session_state:
    st.session_state.carrinho_compras = []
df_emp_dev = carregar_dados(f"SELECT * FROM empresas_dispositivos WHERE device_id = '{device_id}'")
if df_emp_dev.empty:
    cursor = conn.cursor()
    # Um aparelho novo herda as configurações gerais já salvas pela empresa.
    cursor.execute("""
        SELECT nome_empresa, cnpj, ie, fone, endereco, dias_licenca, limite_dispositivos
        FROM empresas_dispositivos ORDER BY id LIMIT 1
    """)
    cfg_empresa_existente = cursor.fetchone()
    if cfg_empresa_existente:
        nome_cfg, cnpj_cfg, ie_cfg, fone_cfg, endereco_cfg, dias_cfg_iniciais, limite_cfg_inicial = cfg_empresa_existente
    else:
        nome_cfg, cnpj_cfg, ie_cfg, fone_cfg, endereco_cfg, dias_cfg_iniciais, limite_cfg_inicial = (
            'REY DA CEBOLA', '19417439000142', '', '(99) 98501-6050', 'RUA CAIPIRA, Nº 174', 30, 2
        )
    cursor.execute("""
        INSERT OR IGNORE INTO empresas_dispositivos
            (device_id, nome_empresa, cnpj, ie, fone, endereco, ativado, dias_licenca, limite_dispositivos)
        VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
    """, (device_id, nome_cfg, cnpj_cfg, ie_cfg, fone_cfg, endereco_cfg,
          int(dias_cfg_iniciais or 30), int(limite_cfg_inicial or 2)))
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


# -------------------------------------------------------------
# PAINEL LATERAL (DEV) — GERADOR DE CHAVES E GESTÃO
# -------------------------------------------------------------
with st.sidebar.expander("⚙️ Gerador de Chaves (Dev)"):
    senha_dev = st.text_input("Senha Mestre Dev", type="password", key="pwd_dev_topo")

    if senha_dev == "13142715":
        tipo_plano = st.selectbox(
            "Tipo de Chave:",
            ["Teste (7 Dias)", "Mensal (30 Dias)", "Anual (365 Dias)", "Personalizado (Dias Livres)"],
            key="select_tipo_plano_dev"
        )
        # --- BOTÃO DE RESET TOTAL DE DISPOSITIVOS ---
        st.markdown("---")
        if st.button("🗑️ Forçar Limpeza de Dispositivos", type="primary", key="btn_forcar_limpeza_total"):
            try:
                cursor = conn.cursor()
                
                # Lista todas as tabelas para encontrarmos a correta
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tabelas = [row[0] for row in cursor.fetchall()]
                
                tabelas_limpas = []
                for tab in tabelas:
                    # Apaga dados de qualquer tabela ligada a dispositivos, ativação ou licenças
                    if any(k in tab.lower() for k in ["dispositivo", "device", "licenca", "ativacao", "token"]):
                        cursor.execute(f"DELETE FROM {tab}")
                        tabelas_limpas.append(tab)
                
                conn.commit()
                
                # Limpa a cache e o estado da sessão
                try:
                    st.cache_data.clear()
                except Exception:
                    pass
                
                st.session_state['dispositivo_ativado'] = False
                
                if tabelas_limpas:
                    st.success(f"✅ Sucesso! Tabelas limpas: {', '.join(tabelas_limpas)}. Atualize a página.")
                else:
                    st.warning("⚠️ Nenhuma tabela específica de dispositivos detetada. Verifique se o nome é diferente.")
                
                st.rerun()
                
            except Exception as e:
                st.error(f"❌ Erro ao limpar: {e}")
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

    # --- TRAVA DE SEGURANÇA DE LICENÇA POR DISPOSITIVO ---
    df_check_ativado = carregar_dados(f"SELECT ativado FROM empresas_dispositivos WHERE device_id = '{device_id}'")
    status_disp_real = int(df_check_ativado.iloc[0]['ativado']) if not df_check_ativado.empty else 0

    if status_disp_real == 0 and menu_admin != "🏢 Configurações da Empresa":
        st.error("🚫 **ACESSO BLOQUEADO:** Este dispositivo não está ativado na licença. Vá em **Configurações da Empresa** para inserir a chave de ativação.")
        st.stop()

    # -------------------------------------------------------------
    # 1. MÓDULO PDV — FRENTE DE CAIXA
    # -------------------------------------------------------------
    elif menu_admin == "🛒 PDV — Frente de Caixa":
        
        # Inicializa o estado de exibição do cupom
        if 'exibir_cupom_tela' not in st.session_state:
            st.session_state.exibir_cupom_tela = False
        if 'html_cupom_atual' not in st.session_state:
            st.session_state.html_cupom_atual = ""

        # SE O CUPOM ESTIVER ATIVO NA TELA
        if st.session_state.exibir_cupom_tela:
            st.success("🎉 Venda concluída com sucesso!")
            
            from datetime import datetime
            data_venda = st.session_state.get('data_venda_final', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            vendedor_atual = st.session_state.get('usuario_logado', st.session_state.get('vendedor', 'administrador'))
            
            # Resgata o cliente selecionado no PDV
            cliente_pdv_selecionado = st.session_state.get('cliente_pdv_selecionado', 'Cliente Balcão')
            
            # Busca o documento do cliente na base de dados
            cli_doc_final = "Não informado"
            try:
                if cliente_pdv_selecionado and cliente_pdv_selecionado != "Cliente Balcão":
                    df_cli_busca = carregar_dados(f"SELECT * FROM clientes WHERE nome = '{cliente_pdv_selecionado}' OR cliente = '{cliente_pdv_selecionado}' LIMIT 1")
                    if not df_cli_busca.empty:
                        cli_doc_final = str(df_cli_busca.iloc[0].get('cpf', df_cli_busca.iloc[0].get('cnpj', df_cli_busca.iloc[0].get('documento', 'Não informado'))))
            except Exception:
                pass

            detalhes_pagto = st.session_state.get('detalhes_pagto', 'Dinheiro / Pix')

            emp_nome = "REY DA CEBOLA"
            emp_cnpj = "19.417.439/0001-42"
            emp_end = "12.426.725-4"

            try:
                df_empresa_cupom = carregar_dados("SELECT * FROM empresa LIMIT 1")
                if not df_empresa_cupom.empty:
                    emp_nome = str(df_empresa_cupom.iloc[0].get('nome', emp_nome))
                    emp_end = str(df_empresa_cupom.iloc[0].get('endereco', ''))
            except Exception:
                pass

            carrinho_impresso = st.session_state.get('carrinho_temp_para_imprimir', [])
            
            texto_itens_cupom = ""
            total_geral_calculado = 0.0  
            
            for item in carrinho_impresso:
                prod_nome = str(item.get('produto', 'Item'))
                qtd_val = float(item.get('quantidade', 1.0))
                total_val = float(item.get('valor_total', 0.0))
                total_geral_calculado += total_val  
                total_fmt = f"R$ {total_val:,.2f}"
                texto_itens_cupom += f"- {prod_nome} | Qtd: {qtd_val}x | {total_fmt}\n"

            # 3. Monta o texto final do cupom
            conteudo_cupom_texto = f"""
========================================
           {emp_nome}
       CNPJ: {emp_cnpj}
       INCR. EST: {emp_end}
========================================
Data: {data_venda}
Vendedor: {vendedor_atual}
Cliente: {cliente_pdv_selecionado}
CPF/CNPJ: {cli_doc_final}
----------------------------------------
ITENS DA VENDA:
{texto_itens_cupom}
----------------------------------------
FORMA DE PAGAMENTO: {detalhes_pagto}
TOTAL GERAL: R$ {total_geral_calculado:,.2f}
========================================
Obrigado pela preferência volte sempre!
O Senhor é meu pastor nada mim faltarar.
========================================
"""

            # 4. Exibe o cupom e os botões
            st.code(conteudo_cupom_texto, language=None)
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            col_b_imp1, col_b_imp2, col_b_imp3 = st.columns([1, 1, 1])
            with col_b_imp1:
                if st.button("🖨️ Imprimir Cupom", use_container_width=True, key="btn_acao_imprimir_nativo"):
                    js_print = "<script>window.parent.print();</script>"
                    st.components.v1.html(js_print, height=0)
            with col_b_imp2:
                st.download_button(
                    label="📥 Baixar Comprovante (TXT)",
                    data=conteudo_cupom_texto,
                    file_name=f"cupom_venda_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain",
                    use_container_width=True,
                    key="btn_download_txt_direto"
                )
            with col_b_imp3:
                if st.button("➕ Iniciar Nova Venda", type="primary", use_container_width=True, key="btn_nova_venda_reset"):
                    st.session_state.exibir_cupom_tela = False
                    st.session_state.html_cupom_atual = ""
                    st.session_state.carrinho_temp_para_imprimir = []
                    st.rerun()
        
        else:
            # FLUXO NORMAL DO PDV
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

            # --- SELEÇÃO DE CLIENTE CADASTRADO NO TOPO DO PDV ---
            try:
                lista_cli_cadastrados = carregar_coluna("clientes", "nome")
                if not lista_cli_cadastrados:
                    lista_cli_cadastrados = carregar_coluna("clientes", "cliente") or carregar_coluna("clientes", "razao_social")
            except Exception:
                lista_cli_cadastrados = []

            opcoes_clientes = ["Cliente Balcão"]
            if lista_cli_cadastrados:
                for c in lista_cli_cadastrados:
                    if c and str(c) not in opcoes_clientes:
                        opcoes_clientes.append(str(c))

            col_c1, col_c2 = st.columns([2, 1])
            with col_c1:
                cliente_pdv_selecionado = st.selectbox(
                    "👤 Selecione o Cliente da Venda:", 
                    options=opcoes_clientes, 
                    key="select_cliente_pdv_topo_final"
                )
                # Salva na sessão para o cupom resgatar
                st.session_state['cliente_pdv_selecionado'] = cliente_pdv_selecionado

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
                    prod_id = int(p_row.get('id', 0))
                    return val_v, str(p_row.get('fornecedor', '')), str(p_row.get('grupo', '')), cod_prod, prod_id
                return 0.0, "", "", "", 0

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
                        valor_recebido = st.number_input("Valor Recebido em Dinheiro (R$)", min_value=0.0, value=float(total_geral_carrinho), format="%.2f", key="input_val_recebido_dinheiro")
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
                        from datetime import timedelta
                        data_venc_padrao = datetime.now().date() + timedelta(days=30)
                        data_vencimento_fiado = st.date_input(
                            "📅 Data de Vencimento do Fiado:",
                            value=data_venc_padrao,
                            format="DD/MM/YYYY",
                            key="input_data_venc_fiado"
                        )
                        data_venc_str = data_vencimento_fiado.strftime('%d/%m/%Y')
                        detalhes_pagto = f"Fiado (Venc: {data_venc_str})"
                        st.warning(f"⚠️ Esta venda será registada como **Fiado** para o cliente **{cliente_pdv_selecionado}** com vencimento em **{data_venc_str}**.")

                    elif forma_pagto == "Parcelado":
                        num_parc = st.number_input("Quantidade de Parcelas Próprias:", min_value=2, max_value=24, value=2, step=1, key="num_parc_proprias")
                        valor_parc = total_geral_carrinho / num_parc
                        detalhes_pagto = f"Parcelado ({num_parc}x de R$ {valor_parc:,.2f})"
                        st.info(f"📅 Venda dividida em **{num_parc}x** de **R$ {valor_parc:,.2f}**.")

                    elif forma_pagto == "Pix":
                        st.markdown("### 📱 Pague com Pix (QR Code Oficial)")
                        df_chaves_db = carregar_dados("SELECT * FROM chaves_pix")
                        
                        if df_chaves_db.empty:
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

                        def gerar_payload_pix(pix_key, nome_recebedor, cidade, valor_str, tipo_chave_pix):
                            if tipo_chave_pix in ["CNPJ", "CPF"]:
                                chave_tratada = ''.join(filter(str.isdigit, pix_key))
                            else:
                                chave_tratada = pix_key.strip()
                            import unicodedata
                            nfkd = unicodedata.normalize('NFKD', nome_recebedor)
                            nome_tratado = "".join([c for c in nfkd if not unicodedata.combining(c)]).upper()[:25]
                            cidade_tratada = "".join([c for c in unicodedata.normalize('NFKD', cidade) if not unicodedata.combining(c)]).upper()[:15]
                            def mc(id_c, val_c):
                                return f"{id_c}{len(val_c):02d}{val_c}"
                            gui = mc("00", "br.gov.bcb.pix")
                            chave_f = mc("01", chave_tratada)
                            merchant_account = mc("26", gui + chave_f)
                            payload = (
                                mc("00", "01") + mc("01", "12") + merchant_account +
                                mc("52", "0000") + mc("53", "986") + mc("54", valor_str) +
                                mc("58", "BR") + mc("60", nome_tratado) + mc("61", cidade_tratada) +
                                mc("62", mc("05", "***")) + "6304"
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
                        pix_payload = gerar_payload_pix(pix_key_val, fav_val, cidade_val, valor_formatado, tipo_val)
                        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={pix_payload}"
                        
                        col_qr_img, col_qr_info = st.columns([1, 2], gap="medium")
                        with col_qr_img:
                            st.image(qr_url, width=190, caption="Escaneie o QR Code")
                        with col_qr_info:
                            st.markdown(f"**Valor a Pagar:** R$ {total_geral_carrinho:,.2f}")
                            st.markdown(f"**Favorecido:** `{fav_val}`")
                            st.text_input("Chave Pix Copia e Cola:", value=pix_payload, key="input_pix_copia_cola_detalhe")

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
                            # Garante que a tabela existe com as colunas corretas
                            cursor.execute("""
                                CREATE TABLE IF NOT EXISTS vendas_cabecalho (
                                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                                    cliente TEXT,
                                    data TEXT,
                                    forma_pagamento TEXT,
                                    total REAL
                                )
                            """)
                            
                            # Define com segurança os valores
                            desc_pagamento = str(locals().get('forma_pagto', 'Dinheiro'))
                            
                            cursor.execute("""
                                INSERT INTO vendas_cabecalho (cliente, data, forma_pagamento, total)
                                VALUES (?, ?, ?, ?)
                            """, (
                                str(locals().get('cliente_pdv_selecionado', 'Cliente Balcão')), 
                                str(data_venda), 
                                desc_pagamento, 
                                float(total_geral_carrinho)
                            ))
                            
                            venda_id_gerado = cursor.lastrowid
                            v_rec = valor_recebido if forma_pagto == "Dinheiro" else total_geral_carrinho
                            t_val = troco if (forma_pagto == "Dinheiro" and troco >= 0) else 0.0

                            data_vencimento_fiado_val = None
                            if forma_pagto == "Fiado" and 'input_data_venc_fiado' in st.session_state:
                                data_vencimento_fiado_val = str(st.session_state.input_data_venc_fiado)

                            # BUSCA OS DADOS DA EMPRESA COM SEGURANÇA
                            try:
                                df_empresa_cupom = carregar_dados("SELECT * FROM empresa LIMIT 1")
                                if not df_empresa_cupom.empty:
                                    emp_nome = df_empresa_cupom.iloc[0].get('nome', nome_empresa_header)
                                    emp_cnpj = df_empresa_cupom.iloc[0].get('cnpj', '19.417.439/0001-42')
                                    emp_end = df_empresa_cupom.iloc[0].get('endereco', '')
                                else:
                                    emp_nome = nome_empresa_header
                                    emp_cnpj = '19.417.439/0001-42'
                                    emp_end = ''
                            except Exception:
                                emp_nome = nome_empresa_header
                                emp_cnpj = '19.417.439/0001-42'
                                emp_end = ''

                            cli_doc_final = "Não informado"
                            if cliente_pdv_selecionado != "Cliente Balcão":
                                try:
                                    df_cli_busca = carregar_dados(f"SELECT * FROM clientes WHERE nome = '{cliente_pdv_selecionado}' OR cliente = '{cliente_pdv_selecionado}'")
                                    if not df_cli_busca.empty:
                                        cli_doc_final = str(df_cli_busca.iloc[0].get('cpf_cnpj') or df_cli_busca.iloc[0].get('cpf') or df_cli_busca.iloc[0].get('cnpj') or 'Não informado')
                                except Exception:
                                    cli_doc_final = "Não informado"
                            
                            venda_id_gerado = None
                            for item in st.session_state.carrinho_pdv:
                                cursor.execute("""
                                    INSERT INTO vendas (
                                        cliente, produto, fornecedor, grupo, quantidade, 
                                        valor_venda, valor_total, forma_pagamento, 
                                        valor_recebido, troco, status, tipo, data, vendedor
                                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Concluído', 'VENDA', ?, ?)
                                """, (
                                    cliente_pdv_selecionado, 
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
                                if not venda_id_gerado:
                                    venda_id_gerado = cursor.lastrowid
                    
                                cursor.execute("""
                                    UPDATE produtos 
                                    SET quantidade = quantidade - ? 
                                    WHERE id = ? OR UPPER(TRIM(produto)) = UPPER(TRIM(?))
                                """, (item['quantidade'], item.get('produto_id', 0), item['produto']))
                    
                                if item.get('grupo') == "PROMOÇÃO":
                                    cursor.execute("""
                                        UPDATE promocoes 
                                        SET qtd_estoque_promo = qtd_estoque_promo - ? 
                                        WHERE produto_id = ? AND qtd_estoque_promo >= ?
                                    """, (item['quantidade'], item.get('produto_id'), item['quantidade']))
                    
                            # Registra o movimento com o ID da primeira linha
                            # da venda na tabela vendas, permitindo estorno exato.
                            cursor.execute(
                                """
                                INSERT INTO caixa_movimentacoes
                                    (sessao_id, tipo, valor, descricao, data, venda_id)
                                VALUES (?, 'VENDA', ?, ?, ?, ?)
                                """,
                                (
                                    sessao_id,
                                    float(total_geral_carrinho),
                                    f"Venda PDV ({detalhes_pagto}) por {vendedor_atual}",
                                    data_venda,
                                    int(venda_id_gerado)
                                )
                            )

                            if forma_pagto == "Fiado" and data_vencimento_fiado_val:
                                cursor.execute("""
                                    CREATE TABLE IF NOT EXISTS contas_receber (
                                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                                        cliente TEXT,
                                        valor REAL,
                                        vencimento TEXT,
                                        status TEXT,
                                        descricao TEXT
                                    )
                                """)
                                cursor.execute("""
                                    INSERT INTO contas_receber (cliente, valor, vencimento, status, descricao)
                                    VALUES (?, ?, ?, 'Pendente', ?)
                                """, (cliente_pdv_selecionado, total_geral_carrinho, data_vencimento_fiado_val, f"Venda PDV #{venda_id_gerado} - Fiado"))

                            # Insere os itens da venda no histórico para permitir o estorno
                            for item in st.session_state.get('carrinho_temp_para_imprimir', []):
                                cursor.execute("""
                                    INSERT INTO vendas_itens (venda_id, produto, quantidade, valor_unitario, valor_total)
                                    VALUES (?, ?, ?, ?, ?)
                                """, (
                                    venda_id_gerado, 
                                    item.get('produto'), 
                                    float(item.get('quantidade', 1.0)), 
                                    float(item.get('preco_unitario', 0.0)), 
                                    float(item.get('valor_total', 0.0))
                                ))
                            conn.commit()
                            
                            # MONTA A LISTA DE ITENS CORRETAMENTE FECHADA
                            carrinho_impresso = st.session_state.get('carrinho_temp_para_imprimir', [])
                            itens_html_cupom = ""
                            for item in carrinho_impresso:
                                prod_nome = str(item.get('produto', 'Item'))
                                qtd_val = float(item.get('quantidade', 1.0))
                                total_val = float(item.get('valor_total', 0.0))
                                total_fmt = f"R$ {total_val:,.2f}"
                                
                                itens_html_cupom += f"""
                                <tr>
                                    <td style="text-align: left; padding: 2px 0;">{prod_nome}</td>
                                    <td style="text-align: center; padding: 2px 0;">{qtd_val}x</td>
                                    <td style="text-align: right; padding: 2px 0;">{total_fmt}</td>
                                </tr>
                                """

                            # MONTA O HTML DO CUPOM COM A TABELA FECHADA CORRETAMENTE
                            html_cupom_gerado = f"""
                            <style>
                                @media print {{
                                    header, footer, nav, aside, .stSidebar, [data-testid="stSidebar"] {{
                                        display: none !important;
                                    }}
                                    body, html {{
                                        background-color: white !important;
                                    }}
                                }}
                            </style>

                            <div id="cupom_imprimir_exclusivo" style="background-color: #ffffff; padding: 20px; border-radius: 5px; border: 1px dashed #ccc; font-family: monospace; color: #000; max-width: 400px; margin: auto;">
                                <h3 style="text-align: center; margin: 0;">{emp_nome}</h3>
                                <p style="text-align: center; margin: 2px 0;">CNPJ: {emp_cnpj}</p>
                                <p style="text-align: center; margin: 2px 0;">{emp_end}</p>
                                <hr style="border-top: 1px dashed #bbb;">
                                <p><b>Data:</b> {data_venda} | <b>Vendedor:</b> {vendedor_atual}</p>
                                <p><b>Cliente:</b> {cliente_pdv_selecionado}</p>
                                <p><b>CPF/CNPJ:</b> {cli_doc_final}</p>
                                <hr style="border-top: 1px dashed #bbb;">
                                <table style="width: 100%; font-family: monospace; font-size: 13px; color: #000; border-collapse: collapse;">
                                    <tr style="border-bottom: 1px solid #ddd;">
                                        <th style="text-align: left; padding-bottom: 4px;">Item</th>
                                        <th style="text-align: center; padding-bottom: 4px;">Qtd</th>
                                        <th style="text-align: right; padding-bottom: 4px;">Total</th>
                                    </tr>
                                    {itens_html_cupom}
                                </table>
                                <hr style="border-top: 1px dashed #bbb;">
                                <p><b>FORMA DE PAGAMENTO:</b> {detalhes_pagto}</p>
                                <p style="font-size: 15px;"><b>TOTAL GERAL: R$ {total_geral_carrinho:,.2f}</b></p>
                                <hr style="border-top: 1px dashed #bbb;">
                                <p style="text-align: center; margin-bottom: 0;">Obrigado pela preferência!</p>
                            </div>
                            """

                            # Salva no estado e ativa a tela do cupom
                            st.session_state.html_cupom_atual = html_cupom_gerado
                            st.session_state.exibir_cupom_tela = True
                            st.session_state.carrinho_temp_para_imprimir = st.session_state.carrinho_pdv.copy()
                            st.session_state.carrinho_pdv = []
                            st.session_state.tela_checkout_ativa = False
                            st.rerun()

            else:
                st.info("Nenhum item lançado no carrinho ainda.")

            # --- SEÇÃO DE BUSCA E INCLUSÃO DE PRODUTOS ---
            st.markdown("---")
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

            val_venda_sug, forn_sug, grupo_sug, cod_sug, id_prod_sug = obter_dados_produto(prod_selecionado) if prod_selecionado else (0.0, "", "", "", 0)

            df_promo_ativo = carregar_dados(f"SELECT * FROM promocoes WHERE produto_id = {id_prod_sug} AND ativo = 1 AND qtd_estoque_promo > 0")
            
            qtd_ja_no_carrinho = 0.0
            if st.session_state.carrinho_pdv:
                for item_c in st.session_state.carrinho_pdv:
                    if item_c.get('produto_id') == id_prod_sug:
                        qtd_ja_no_carrinho += float(item_c.get('quantidade', 0.0))

            preco_unit_venda = val_venda_sug
            is_promocional = False
            qtd_minima_promo = 0.0

            if not df_promo_ativo.empty:
                row_p = df_promo_ativo.iloc[0]
                preco_promo = float(row_p['preco_promo'])
                qtd_minima_promo = float(row_p['qtd_minima'])
                estoque_promo_restante = float(row_p['qtd_estoque_promo']) - qtd_ja_no_carrinho
            else:
                estoque_promo_restante = 0.0

            if is_simples:
                subtotal_item = preco_unit_venda
                if estoque_promo_restante >= 1.0 and 1.0 >= qtd_minima_promo:
                    preco_unit_venda = preco_promo
                    subtotal_item = preco_unit_venda
                    is_promocional = True
                    st.info(f"🏷️ **Promoção Ativa!** Preço promocional aplicado: R$ {preco_unit_venda:,.2f}")
                elif not df_promo_ativo.empty:
                    if estoque_promo_restante <= 0:
                        st.warning("⚠️ Estoque da promoção esgotado! Aplicando preço normal.")
                    else:
                        st.info(f"ℹ️ Promoção disponível a partir de {qtd_minima_promo} un/kg (Preço normal aplicado).")

                if st.button("➕ [ Enter ] Incluir Produto", type="primary", use_container_width=True, key="btn_inc_prod_simples"):
                    if not prod_selecionado:
                        st.error("Selecione um produto.")
                    else:
                        st.session_state.carrinho_pdv.append({
                            "codigo": cod_sug, "produto": prod_selecionado, "quantidade": 1.0,
                            "valor_unitario": preco_unit_venda, "valor_total": subtotal_item,
                            "fornecedor": forn_sug, "grupo": "PROMOÇÃO" if is_promocional else grupo_sug,
                            "produto_id": id_prod_sug
                        })
                        st.success(f"✅ '{prod_selecionado}' adicionado!")
                        st.rerun()
            else:
                col_q1, col_q2, col_q3 = st.columns([1, 1, 2], gap="medium")
                with col_q1:
                    qtd_venda = st.number_input("Qtd", min_value=0.01, value=1.0, step=1.0, key="qtd_prod_pdv_alin")
                
                with col_q2:
                    preco_calculado_final = val_venda_sug
                    if not df_promo_ativo.empty:
                        if qtd_venda >= qtd_minima_promo and estoque_promo_restante >= qtd_venda:
                            preco_calculado_final = preco_promo
                            is_promocional = True
                    
                    preco_unit_venda = st.number_input("Preço Unit. (R$)", min_value=0.0, value=float(preco_calculado_final), format="%.2f")
                
                with col_q3:
                    subtotal_item = qtd_venda * preco_unit_venda
                    if is_promocional:
                        st.success(f"🏷️ **Promoção Ativa!** (Estoque Promo Restante: {estoque_promo_restante} un)")
                    elif not df_promo_ativo.empty:
                        if estoque_promo_restante <= 0 or qtd_venda > estoque_promo_restante:
                            st.warning(f"⚠️ Estoque da promoção esgotado/insuficiente! (Restante: {max(0.0, estoque_promo_restante)} un)")
                        else:
                            st.info(f"ℹ️ Promoção a partir de {qtd_minima_promo} un/kg.")

                    st.markdown(f"**Subtotal:** R$ {subtotal_item:,.2f}")
                    if st.button("➕ [ Enter ] Incluir Produto", type="primary", use_container_width=True, key="btn_inc_prod_completo"):
                        if not prod_selecionado:
                            st.error("Selecione um produto.")
                        else:
                            st.session_state.carrinho_pdv.append({
                                "codigo": cod_sug, "produto": prod_selecionado, "quantidade": qtd_venda,
                                "valor_unitario": preco_unit_venda, "valor_total": subtotal_item,
                                "fornecedor": forn_sug, "grupo": "PROMOÇÃO" if is_promocional else grupo_sug,
                                "produto_id": id_prod_sug
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
    # 3. MÓDULO REGISTRAR VENDA / PEDIDOS (COMPLETO E TELA ÚNICA)
    # -------------------------------------------------------------
    elif menu_admin == "🛒 Registrar Venda":
        st.subheader(f"🛒 Registrar Venda / Pedido — {nome_empresa_header} | 👤 Utilizador: {usr_exibicao}")
        
        try:
            df_cli_db = carregar_dados("SELECT * FROM clientes")
            if df_cli_db is not None and not df_cli_db.empty:
                col_nome_c = 'cliente' if 'cliente' in df_cli_db.columns else ('nome' if 'nome' in df_cli_db.columns else df_cli_db.columns[1])
                clientes_opt = df_cli_db[col_nome_c].dropna().astype(str).tolist()
            else:
                clientes_opt = ["Cliente Balcão"]
        except Exception:
            clientes_opt = ["Cliente Balcão"]

        if not clientes_opt:
            clientes_opt = ["Cliente Balcão"]

        df_p_admin = carregar_dados("SELECT * FROM produtos")
        produtos_base = df_p_admin['produto'].tolist() if not df_p_admin.empty else ["ABACATE", "AMEIXA IMPORTADA"]
        
        col_v1, col_v2 = st.columns(2)
        with col_v1:
            cliente_ped = st.selectbox("Selecione o Cliente", clientes_opt, key="sel_cliente_reg_venda")
        with col_v2:
            data_venda_input = st.date_input("Data da Venda", value=datetime.now(), key="input_data_reg_venda")

        st.markdown("---")
        
        # 1. ADICIONAR ITENS AO CARRINHO (NOVA VENDA)
        st.markdown("### ➕ Adicionar Produtos ao Pedido Atual")
        col_prod_r1, col_prod_r2, col_prod_r3 = st.columns([2, 1, 1])
        with col_prod_r1:
            prod_item = st.selectbox("Selecione o Produto", produtos_base, key="sel_prod_reg_venda")
        
        val_sugestao = 0.0
        if not df_p_admin.empty and prod_item in produtos_base:
            p_match = df_p_admin[df_p_admin['produto'] == prod_item]
            if not p_match.empty:
                val_sugestao = float(p_match.iloc[0].get('valor_venda', 0.0) or p_match.iloc[0].get('venda', 0.0) or 0.0)

        with col_prod_r2:
            qtd_ped = st.number_input("Quantidade", min_value=0.01, value=1.0, key="qtd_reg_venda")
        with col_prod_r3:
            v_venda_ped = st.number_input("Preço Unitário (R$)", min_value=0.0, value=float(val_sugestao), format="%.2f", key=f"preco_unit_{prod_item}")

        if st.button("➕ Incluir no Carrinho", type="primary", use_container_width=True, key="btn_incluir_reg_venda"):
            st.session_state.carrinho_cliente.append({
                "produto": prod_item, "quantidade": qtd_ped, "valor_unitario": v_venda_ped, "valor_total": qtd_ped * v_venda_ped
            })
            st.success(f"✅ '{prod_item}' incluído no pedido!")
            st.rerun()

        if st.session_state.carrinho_cliente:
            st.markdown("### 🛒 Itens do Pedido Atual")
            df_carrinho_reg = pd.DataFrame(st.session_state.carrinho_cliente)
            st.dataframe(df_carrinho_reg, use_container_width=True)

            item_para_remover = st.selectbox("Selecionar item para remover do carrinho atual (opcional):", [""] + df_carrinho_reg['produto'].tolist(), key="sel_remover_item_carrinho")
            if item_para_remover and item_para_remover != "":
                if st.button("🗑️ Remover Item Selecionado do Carrinho", key="btn_remover_item_carrinho"):
                    st.session_state.carrinho_cliente = [i for i in st.session_state.carrinho_cliente if i['produto'] != item_para_remover]
                    st.success("Item removido do carrinho!")
                    st.rerun()

            st.markdown("---")
            st.markdown("### 💳 Pagamento e Finalização do Carrinho Atual")
        
            forma_pagto_reg = st.selectbox(
                "Forma de Pagamento / Condição", 
                ["Dinheiro", "Pix", "Cartão Débito", "Cartão Crédito", "Fiado", "Parcelado"],
                key="sel_forma_pagto_reg_venda"
            )
    
            total_carrinho_atual = sum(i['valor_total'] for i in st.session_state.carrinho_cliente)
            detalhes_pagto_reg = forma_pagto_reg
            datas_vencimentos_parcelas_novas = []
            valores_parcelas_novas = []
            
            # Variável exclusiva para controlar o vencimento do fiado
            data_vencimento_fiado_val = None
    
            if forma_pagto_reg == "Parcelado":
                num_parc_reg = st.number_input("Quantidade de Parcelas:", min_value=1, max_value=24, value=2, step=1, key="num_parc_reg_venda")
                from datetime import timedelta
                
                for p_i in range(int(num_parc_reg)):
                    val_sug = total_carrinho_atual / num_parc_reg
                    col_p1, col_p2 = st.columns(2)
                    with col_p1:
                        v_p = st.number_input(f"Valor Parcela {p_i + 1} (R$)", value=float(val_sug), format="%.2f", key=f"val_novo_p_{p_i}")
                    with col_p2:
                        dt_sug = datetime.now().date() + timedelta(days=30 * (p_i + 1))
                        d_p = st.date_input(f"Vencimento Parcela {p_i + 1}", value=dt_sug, key=f"dt_novo_p_{p_i}")
                    valores_parcelas_novas.append(v_p)
                    datas_vencimentos_parcelas_novas.append(str(d_p))
    
                # Auto divisão inteligente para nova venda
                if int(num_parc_reg) > 1:
                    prim_v = valores_parcelas_novas[0]
                    rest = total_carrinho_atual - prim_v
                    if rest < 0: rest = 0.0
                    cada_rest = rest / (int(num_parc_reg) - 1)
                    for p_i in range(1, int(num_parc_reg)):
                        valores_parcelas_novas[p_i] = round(cada_rest, 2)
    
                detalhes_pagto_reg = f"Parcelado ({int(num_parc_reg)}x)"
    
            elif forma_pagto_reg == "Fiado":
                from datetime import timedelta
                data_venc_padrao = datetime.now().date() + timedelta(days=30)
                
                # Seletor de data interativo e editável para o Fiado
                data_vencimento_fiado = st.date_input(
                    "📅 Data de Vencimento do Fiado:",
                    value=data_venc_padrao,
                    format="DD/MM/YYYY",
                    key="input_data_venc_fiado_reg_venda"
                )
                data_vencimento_fiado_val = str(data_vencimento_fiado)
                
                detalhes_pagto_reg = f"Fiado ({cliente_ped}) - Venc: {data_vencimento_fiado.strftime('%d/%m/%Y')}"
    
            if st.button("🔴 Finalizar e Salvar Pedido", type="primary", use_container_width=True, key="btn_finalizar_reg_venda"):
                try:
                    with sqlite3.connect("crm_comercio.db", timeout=30.0) as conexao_transacao:
                        cursor = conexao_transacao.cursor()
                        
                        # Garante que todas as tabelas necessárias existem
                        cursor.execute("""
                            CREATE TABLE IF NOT EXISTS produtos (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                produto TEXT,
                                quantidade REAL,
                                valor_venda REAL
                            )
                        """)
                        cursor.execute("""
                            CREATE TABLE IF NOT EXISTS vendas_cabecalho (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                cliente TEXT,
                                forma_pagamento TEXT,
                                data TEXT,
                                total REAL
                            )
                        """)
                        cursor.execute("""
                            CREATE TABLE IF NOT EXISTS vendas_itens (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                venda_id INTEGER,
                                produto TEXT,
                                quantidade REAL,
                                valor_unitario REAL,
                                valor_total REAL
                            )
                        """)
                        cursor.execute("""
                            CREATE TABLE IF NOT EXISTS contas_receber (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                cliente TEXT,
                                valor REAL,
                                vencimento TEXT,
                                status TEXT,
                                descricao TEXT
                            )
                        """)
                        conexao_transacao.commit()
    
                        data_agora = f"{data_venda_input} " + datetime.now().strftime("%H:%M:%S")
                        
                        cursor.execute("""
                            INSERT INTO vendas_cabecalho (cliente, forma_pagamento, data, total)
                            VALUES (?, ?, ?, ?)
                        """, (cliente_ped, detalhes_pagto_reg, data_agora, total_carrinho_atual))
                        
                        venda_id_gerado = cursor.lastrowid
    
                        for item in st.session_state.carrinho_cliente:
                            cursor.execute("""
                                INSERT INTO vendas_itens (venda_id, produto, quantidade, valor_unitario, valor_total)
                                VALUES (?, ?, ?, ?, ?)
                            """, (venda_id_gerado, item['produto'], item['quantidade'], item['valor_unitario'], item['valor_total']))
                            
                            # Atualiza o estoque com segurança
                            cursor.execute("""
                                UPDATE produtos 
                                SET quantidade = quantidade - ? 
                                WHERE UPPER(TRIM(produto)) = UPPER(TRIM(?))
                            """, (item['quantidade'], item['produto']))
    
                        # Se for Parcelado, grava as parcelas no contas a receber
                        if forma_pagto_reg == "Parcelado" and valores_parcelas_novas:
                            for idx_p, (val_p_item, dt_v_item) in enumerate(zip(valores_parcelas_novas, datas_vencimentos_parcelas_novas)):
                                cursor.execute("""
                                    INSERT INTO contas_receber (cliente, valor, vencimento, status, descricao)
                                    VALUES (?, ?, ?, 'Pendente', ?)
                                """, (cliente_ped, val_p_item, dt_v_item, f"Venda #{venda_id_gerado} - Parcela {idx_p+1}/{len(valores_parcelas_novas)}"))
    
                        # Se for Fiado, grava o lançamento único no contas a receber com a data escolhida
                        elif forma_pagto_reg == "Fiado" and data_vencimento_fiado_val:
                            cursor.execute("""
                                INSERT INTO contas_receber (cliente, valor, vencimento, status, descricao)
                                VALUES (?, ?, ?, 'Pendente', ?)
                            """, (cliente_ped, total_carrinho_atual, data_vencimento_fiado_val, f"Venda #{venda_id_gerado} - Fiado"))
    
                        conexao_transacao.commit()
    
                    st.session_state.carrinho_cliente = []
                    st.success(f"✅ Venda #{venda_id_gerado} gravada com sucesso!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Erro ao gravar venda: {e}")

        # -------------------------------------------------------------
        # 2. HISTÓRICO E GESTÃO DE VENDAS (TELA ÚNICA COM EDIÇÃO TOTAL)
        # -------------------------------------------------------------
        st.markdown("---")
        st.markdown("### 📋 Histórico e Gestão de Vendas (Tela Única)")
        
        try:
            df_vendas_cab = carregar_dados("SELECT * FROM vendas_cabecalho ORDER BY id DESC")
        except Exception:
            df_vendas_cab = pd.DataFrame()

        if df_vendas_cab is not None and not df_vendas_cab.empty:
            st.dataframe(df_vendas_cab, use_container_width=True)

            df_vendas_cab['label_venda'] = "Venda #" + df_vendas_cab['id'].astype(str) + " - " + df_vendas_cab['cliente'].astype(str) + " (" + df_vendas_cab['data'].astype(str) + ")"
            lista_vendas_edit = df_vendas_cab['label_venda'].tolist()

            venda_selecionada_label = st.selectbox("🎯 Selecione a Venda para Gerenciar / Editar:", lista_vendas_edit, key="select_venda_gerenciar_master")

            row_venda_sel = df_vendas_cab[df_vendas_cab['label_venda'] == venda_selecionada_label].iloc[0]
            id_venda_atual = int(row_venda_sel['id'])

            st.markdown(f"---")
            st.markdown(f"## 🛠️ Editando Venda #{id_venda_atual}")
            
            col_cab1, col_cab2, col_cab3 = st.columns(3)
            with col_cab1:
                novo_cli_venda = st.text_input("Cliente", value=str(row_venda_sel.get('cliente', '')), key=f"edit_cli_v_{id_venda_atual}")
            with col_cab2:
                try:
                    data_val_dt = datetime.strptime(str(row_venda_sel.get('data', ''))[:10], "%Y-%m-%d")
                except Exception:
                    data_val_dt = datetime.now()
                nova_data_venda = st.date_input("Data da Venda", value=data_val_dt, key=f"edit_data_v_{id_venda_atual}")
            with col_cab3:
                forma_atual_db = str(row_venda_sel.get('forma_pagamento', ''))
                idx_fp = 0
                opcoes_fp = ["Dinheiro", "Pix", "Cartão Débito", "Cartão Crédito", "Fiado", "Parcelado"]
                for i_op, op_val in enumerate(opcoes_fp):
                    if op_val.lower() in forma_atual_db.lower():
                        idx_fp = i_op
                        break

                nova_forma_pagto = st.selectbox("Forma de Pagamento", opcoes_fp, index=idx_fp, key=f"edit_fp_v_{id_venda_atual}")

            st.markdown("#### 📦 Produtos da Venda")
            df_itens_venda = carregar_dados(f"SELECT * FROM vendas_itens WHERE venda_id = {id_venda_atual}")
            
            novos_dados_itens = []
            if df_itens_venda is not None and not df_itens_venda.empty:
                for idx, row_it in df_itens_venda.iterrows():
                    id_it = int(row_it['id'])
                    col_it1, col_it2, col_it3, col_it4 = st.columns([2, 1, 1, 1])
                    
                    with col_it1:
                        st.text(f"Prod: {row_it['produto']}")
                    with col_it2:
                        q_edit = st.number_input("Qtd", value=float(row_it['quantidade']), min_value=0.01, step=1.0, key=f"q_it_{id_it}")
                    with col_it3:
                        v_edit = st.number_input("Val. Unit.", value=float(row_it['valor_unitario']), min_value=0.0, format="%.2f", key=f"v_it_{id_it}")
                    with col_it4:
                        exc_it = st.checkbox("Excluir", key=f"del_it_{id_it}")

                    tot_it = q_edit * v_edit
                    novos_dados_itens.append({
                        "id": id_it, "produto": row_it['produto'], "quantidade": q_edit, "valor_unitario": v_edit, "valor_total": tot_it, "excluir": exc_it
                    })
            
            total_itens_calculado = sum(it['valor_total'] for it in novos_dados_itens if not it['excluir'])
            st.info(f"💡 **Valor Total Atual dos Produtos:** R$ {total_itens_calculado:,.2f}")

            novas_parcelas_editadas = []
            if nova_forma_pagto == "Parcelado":
                st.markdown("#### 📅 Gestão de Parcelas (Divisão Automática)")
                df_parc_exist = carregar_dados(f"SELECT * FROM contas_receber WHERE descricao LIKE '%Venda #{id_venda_atual}%'")
                
                qtd_parc_inicial = len(df_parc_exist) if (df_parc_exist is not None and not df_parc_exist.empty) else 2
                qtd_parc_input = st.number_input("Número de Parcelas:", min_value=1, max_value=24, value=qtd_parc_inicial, key=f"n_parc_edit_{id_venda_atual}")
                
                from datetime import timedelta
                valores_parcelas_temp = []

                for p_i in range(int(qtd_parc_input)):
                    val_sug = total_itens_calculado / qtd_parc_input
                    if df_parc_exist is not None and p_i < len(df_parc_exist):
                        val_sug = float(df_parc_exist.iloc[p_i].get('valor', val_sug))

                    col_p1, col_p2 = st.columns(2)
                    with col_p1:
                        val_parc_p = st.number_input(f"Valor Parcela {p_i + 1} (R$)", value=float(val_sug), format="%.2f", key=f"val_p_{id_venda_atual}_{p_i}")
                    with col_p2:
                        dt_def = datetime.now().date() + timedelta(days=30 * (p_i + 1))
                        if df_parc_exist is not None and p_i < len(df_parc_exist):
                            try:
                                dt_def = datetime.strptime(str(df_parc_exist.iloc[p_i].get('vencimento', ''))[:10], "%Y-%m-%d").date()
                            except Exception:
                                pass
                        dt_parc_p = st.date_input(f"Vencimento Parcela {p_i + 1}", value=dt_def, key=f"dt_p_{id_venda_atual}_{p_i}")

                    valores_parcelas_temp.append({"valor": val_parc_p, "vencimento": str(dt_parc_p)})

                if int(qtd_parc_input) > 1:
                    primeiro_valor = valores_parcelas_temp[0]["valor"]
                    restante_a_dividir = total_itens_calculado - primeiro_valor
                    if restante_a_dividir < 0: restante_a_dividir = 0.0
                    valor_cada_restante = restante_a_dividir / (int(qtd_parc_input) - 1)
                    
                    for p_i in range(1, int(qtd_parc_input)):
                        valores_parcelas_temp[p_i]["valor"] = round(valor_cada_restante, 2)

                for p_i, p_val_data in enumerate(valores_parcelas_temp):
                    novas_parcelas_editadas.append({
                        "numero": p_i + 1, "valor": p_val_data["valor"], "vencimento": p_val_data["vencimento"]
                    })
                    st.caption(f"➡️ Parcela {p_i+1}: **R$ {p_val_data['valor']:,.2f}** para {p_val_data['vencimento']}")

            st.markdown("---")
            col_b_main1, col_b_main2, col_b_estorno = st.columns(3)
            
            with col_b_main1:
                if st.button("💾 Salvar Alterações", type="primary", use_container_width=True, key=f"btn_save_all_{id_venda_atual}"):
                    try:
                        cursor = conn.cursor()
                        
                        total_venda_recalculado = 0.0
                        for it in novos_dados_itens:
                            if it['excluir']:
                                cursor.execute("DELETE FROM vendas_itens WHERE id = ?", (it['id'],))
                            else:
                                cursor.execute("""
                                    UPDATE vendas_itens 
                                    SET quantidade = ?, valor_unitario = ?, valor_total = ?
                                    WHERE id = ?
                                """, (it['quantidade'], it['valor_unitario'], it['valor_total'], it['id']))
                                total_venda_recalculado += it['valor_total']

                        fp_desc = nova_forma_pagto
                        if nova_forma_pagto == "Parcelado":
                            fp_desc = f"Parcelado ({len(novas_parcelas_editadas)}x)"
                        
                        dt_string_final = f"{nova_data_venda} " + datetime.now().strftime("%H:%M:%S")
                        
                        cursor.execute("""
                            UPDATE vendas_cabecalho 
                            SET cliente = ?, data = ?, forma_pagamento = ?, total = ?
                            WHERE id = ?
                        """, (novo_cli_venda.strip().upper(), dt_string_final, fp_desc, total_venda_recalculado, id_venda_atual))

                        cursor.execute("DELETE FROM contas_receber WHERE descricao LIKE ?", (f"%Venda #{id_venda_atual}%",))
                        if nova_forma_pagto == "Parcelado":
                            for p_item in novas_parcelas_editadas:
                                cursor.execute("""
                                    INSERT INTO contas_receber (cliente, valor, vencimento, status, descricao)
                                    VALUES (?, ?, ?, 'Pendente', ?)
                                """, (novo_cli_venda.strip().upper(), p_item['valor'], p_item['vencimento'], f"Venda #{id_venda_atual} - Parcela {p_item['numero']}/{len(novas_parcelas_editadas)}"))

                        conn.commit()
                        st.success(f"✅ Venda #{id_venda_atual} atualizada com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Erro ao salvar: {e}")

            with col_b_main2:
                if st.button("🗑️ Excluir Venda", use_container_width=True, key=f"btn_del_all_{id_venda_atual}"):
                    try:
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM vendas_itens WHERE venda_id = ?", (id_venda_atual,))
                        cursor.execute("DELETE FROM vendas_cabecalho WHERE id = ?", (id_venda_atual,))
                        cursor.execute("DELETE FROM contas_receber WHERE descricao LIKE ?", (f"%Venda #{id_venda_atual}%",))
                        conn.commit()
                        st.success(f"🗑️ Venda #{id_venda_atual} excluída com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Erro ao excluir: {e}")

            with col_b_estorno:
                if st.button("🔄 Estornar Venda", type="primary", use_container_width=True, key=f"btn_estornar_{id_venda_atual}"):
                    try:
                        cursor = conn.cursor()
                        
                        # Devolve as quantidades dos produtos de volta ao stock
                        df_itens_estorno = carregar_dados(f"SELECT produto, quantidade FROM vendas_itens WHERE venda_id = {id_venda_atual}")
                        if df_itens_estorno is not None and not df_itens_estorno.empty:
                            for _, item_est in df_itens_estorno.iterrows():
                                cursor.execute("""
                                    UPDATE produtos 
                                    SET quantidade = quantidade + ? 
                                    WHERE UPPER(TRIM(produto)) = UPPER(TRIM(?))
                                """, (float(item_est['quantidade']), item_est['produto']))

                        # Remove os registos da venda e contas a receber associadas
                        cursor.execute("DELETE FROM vendas_itens WHERE venda_id = ?", (id_venda_atual,))
                        cursor.execute("DELETE FROM vendas_cabecalho WHERE id = ?", (id_venda_atual,))
                        cursor.execute("DELETE FROM contas_receber WHERE descricao LIKE ?", (f"%Venda #{id_venda_atual}%",))
                        
                        conn.commit()
                        st.success(f"🔄 Venda #{id_venda_atual} estornada com sucesso e itens devolvidos ao stock!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Erro ao estornar: {e}")
        else:
            st.info("ℹ️ Nenhuma venda registrada até o momento.")

    # -------------------------------------------------------------
    # ENTRADA DE ESTOQUE E CADASTRO DE PRODUTOS
    # -------------------------------------------------------------
    elif menu_admin == "Entrada de Estoque (Compras)" or "Entrada de Estoque" in str(menu_admin):
        st.subheader("📦 Gestão de Produtos e Entradas de Estoque")
        
        # Criamos as abas para organizar o cadastro e as compras
        tab_cad_prod, tab_entrada_compra = st.tabs([
            "➕ Cadastrar Novo Produto", 
            "📥 Entrada de Estoque (Compras)"
        ])
        
        # -------------------------------------------------------------
        # ABA 1: CADASTRAR NOVO PRODUTO
        # -------------------------------------------------------------
        with tab_cad_prod:
            st.markdown("### ➕ Cadastro de Novo Produto no Sistema")
            
            with st.form("form_cadastro_produto_direto"):
                col_cp1, col_cp2 = st.columns(2)
                with col_cp1:
                    novo_cod_prod = st.text_input("Código / Código de Barras")
                    novo_nome_prod = st.text_input("Nome do Produto")
                with col_cp2:
                    try:
                        lista_grupos_cad = carregar_coluna("grupos", "grupo") or ["GERAL"]
                    except Exception:
                        lista_grupos_cad = ["GERAL"]
                    novo_grupo_prod = st.selectbox("Grupo / Categoria", lista_grupos_cad)
                    
                    try:
                        lista_forn_cad = carregar_coluna("fornecedores", "nome") or carregar_coluna("fornecedores", "fornecedor") or ["GERAL"]
                    except Exception:
                        lista_forn_cad = ["GERAL"]
                    novo_forn_prod = st.selectbox("Fornecedor Padrão", lista_forn_cad)
    
                col_cp3, col_cp4 = st.columns(2)
                with col_cp3:
                    novo_preco_compra = st.number_input("Preço de Compra Inicial (R$)", value=0.0, format="%.2f")
                with col_cp4:
                    novo_preco_venda = st.number_input("Preço de Venda Inicial (R$)", value=0.0, format="%.2f")
                
                qtd_inicial_prod = st.number_input("Quantidade Inicial em Estoque", value=0.0, step=1.0, min_value=0.0)
    
                btn_salvar_novo_prod = st.form_submit_button("💾 Salvar Novo Produto", type="primary", use_container_width=True)
                
                if btn_salvar_novo_prod:
                    if novo_nome_prod.strip():
                        try:
                            cursor = conn.cursor()
                            cursor.execute("""
                                INSERT INTO produtos (codigo, produto, quantidade, valor_compra, valor_venda, grupo, fornecedor)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (
                                novo_cod_prod.strip(), 
                                novo_nome_prod.strip().upper(), 
                                qtd_inicial_prod, 
                                novo_preco_compra, 
                                novo_preco_venda, 
                                novo_grupo_prod, 
                                novo_forn_prod
                            ))
                            conn.commit()
                            st.success(f"✅ Produto '{novo_nome_prod.strip().upper()}' cadastrado com sucesso!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Erro ao cadastrar produto: {e}")
                    else:
                        st.warning("⚠️ O nome do produto não pode estar vazio.")
    
        # -------------------------------------------------------------
        # ABA 2: ENTRADA DE ESTOQUE (COMPRAS) COM MARGEM AUTOMÁTICA
        # -------------------------------------------------------------
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

        # Inicializa o estado de cálculo na sessão
        if 'margem_perc' not in st.session_state:
            st.session_state.margem_perc = 30.0
        if 'preco_venda' not in st.session_state:
            st.session_state.preco_venda = pr_compra * (1.0 + (st.session_state.margem_perc / 100.0))
        if 'ultimo_pr_compra' not in st.session_state:
            st.session_state.ultimo_pr_compra = pr_compra

        # Se o preço de compra alterou, recalcula o preço de venda mantendo a margem atual
        if pr_compra != st.session_state.ultimo_pr_compra:
            st.session_state.ultimo_pr_compra = pr_compra
            st.session_state.preco_venda = pr_compra * (1.0 + (st.session_state.margem_perc / 100.0))

        # Funções de callback seguras ligadas à sessão
        def mudar_margem():
            m = st.session_state.widget_margem
            st.session_state.margem_perc = m
            st.session_state.preco_venda = pr_compra * (1.0 + (m / 100.0))

        def mudar_venda():
            v = st.session_state.widget_venda
            st.session_state.preco_venda = v
            if pr_compra > 0:
                st.session_state.margem_perc = ((v - pr_compra) / pr_compra) * 100.0

        col_m1, col_m2 = st.columns(2)
        with col_m1:
            st.number_input(
                "Margem de Lucro (%)", 
                value=float(st.session_state.margem_perc), 
                format="%.2f", 
                key="widget_margem",
                on_change=mudar_margem
            )
        with col_m2:
            st.number_input(
                "Preço Venda Unitário (R$)", 
                min_value=0.0, 
                value=float(st.session_state.preco_venda), 
                format="%.2f", 
                key="widget_venda",
                on_change=mudar_venda
            )

        st.success(f"🟢 Preço de Venda Ativo: **R$ {st.session_state.preco_venda:,.2f}** | Margem Atual: **{st.session_state.margem_perc:,.2f}%**")

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🛒 Adicionar ao Carrinho de Compras", type="primary", use_container_width=True):
            if 'carrinho_compras' not in st.session_state:
                st.session_state.carrinho_compras = []
                
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

        if 'carrinho_compras' in st.session_state and st.session_state.carrinho_compras:
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
                        st.session_state.carrinho_compras.pop(int(item_remover_idx))
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
                    
                    # Recria a tabela de compras com todas as colunas atualizadas para evitar erros de estrutura
                    cursor.execute("DROP TABLE IF EXISTS compras")
                    cursor.execute("""
                        CREATE TABLE compras (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            produto TEXT,
                            fornecedor TEXT,
                            grupo TEXT,
                            quantidade REAL,
                            preco_compra REAL,
                            preco_venda REAL,
                            unidade TEXT,
                            data TEXT
                        )
                    """)

                    # Garante que a tabela produtos tem a coluna unidade
                    cursor.execute("PRAGMA table_info(produtos)")
                    cols_prod = [c[1] for c in cursor.fetchall()]
                    if "unidade" not in cols_prod:
                        try: cursor.execute("ALTER TABLE produtos ADD COLUMN unidade TEXT")
                        except Exception: pass

                    data_atual_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    for item in st.session_state.carrinho_compras:
                        # Insere no histórico de compras
                        cursor.execute("""
                            INSERT INTO compras (produto, fornecedor, grupo, quantidade, preco_compra, preco_venda, unidade, data)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            item.get('produto'), 
                            item.get('fornecedor'), 
                            item.get('grupo'), 
                            item.get('quantidade'), 
                            item.get('valor_compra'), 
                            item.get('valor_venda'), 
                            item.get('unidade', 'UNIDADE'), 
                            data_atual_str
                        ))

                        # Atualiza ou insere o produto no estoque geral
                        cursor.execute("SELECT id FROM produtos WHERE produto = ?", (item['produto'],))
                        if cursor.fetchone():
                            cursor.execute("""
                                UPDATE produtos 
                                SET quantidade = quantidade + ?, valor_compra = ?, valor_venda = ?, grupo = ?, fornecedor = ?, unidade = ?
                                WHERE produto = ?
                            """, (item['quantidade'], item['valor_compra'], item['valor_venda'], item['grupo'], item['fornecedor'], item.get('unidade', 'UNIDADE'), item['produto']))
                        else:
                            cursor.execute("""
                                INSERT INTO produtos (produto, grupo, fornecedor, quantidade, valor_compra, valor_venda, unidade) 
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (item['produto'], item['grupo'], item['fornecedor'], item['quantidade'], item['valor_compra'], item['valor_venda'], item.get('unidade', 'UNIDADE')))
                    
                    conn.commit()
                    st.session_state.carrinho_compras = []
                    st.success("✅ Entrada registrada no banco de dados e histórico de compras atualizado com sucesso!")
                    st.rerun()

    # -------------------------------------------------------------
    # 5. MÓDULO CADASTROS (CLIENTES / FORNECEDORES / GRUPOS)
    # -------------------------------------------------------------
    elif menu_admin == "👥 Cadastros (Clientes / Fornecedores / Grupos)":
        st.subheader("👥 Cadastros (Clientes / Fornecedores / Grupos)")
        tab_cli, tab_forn, tab_grup = st.tabs(["👤 Clientes", "🏢 Fornecedores", "🏷️ Grupos"])
    
        # -------------------------------------------------------------
        # ABA 1: CLIENTES
        # -------------------------------------------------------------
        with tab_cli:
            st.markdown("### 👤 Cadastro de Clientes")
            with st.form("form_cad_cli"):
                n_cli = st.text_input("Nome do Cliente")
                c_cli = st.text_input("CPF / CNPJ")
                t_cli = st.text_input("Telefone")
                
                if st.form_submit_button("Salvar Cliente", type="primary"):
                    if n_cli.strip():
                        try:
                            cursor = conn.cursor()
                            cursor.execute("""
                                INSERT INTO clientes (nome, cpf, fone) 
                                VALUES (?, ?, ?)
                            """, (n_cli.strip().upper(), c_cli.strip(), t_cli.strip()))
                            conn.commit()
                            st.success("✅ Cliente cadastrado com sucesso!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Erro ao cadastrar cliente: {e}")
                    else:
                        st.warning("⚠️ O nome do cliente não pode estar vazio.")
    
            st.markdown("---")
            st.markdown("### 📋 Clientes Cadastrados (Editar / Excluir)")
            try:
                df_clientes = carregar_dados("SELECT * FROM clientes")
            except Exception:
                df_clientes = pd.DataFrame()
    
            if df_clientes is not None and not df_clientes.empty:
                st.dataframe(df_clientes, use_container_width=True)
                
                col_nome_cli = 'cliente' if 'cliente' in df_clientes.columns else ('nome' if 'nome' in df_clientes.columns else df_clientes.columns[1])
                df_clientes['label_cli'] = df_clientes['id'].astype(str) + " - " + df_clientes[col_nome_cli].astype(str)
                lista_cli_edit = df_clientes['label_cli'].tolist()
    
                cli_selecionado = st.selectbox("Selecione o Cliente para Gerenciar:", lista_cli_edit, key="select_cli_gerenciar_cad")
    
                p_row_cli = df_clientes[df_clientes['label_cli'] == cli_selecionado].iloc[0]
                id_cli_atual = int(p_row_cli['id'])
                nome_cli_atual = str(p_row_cli.get(col_nome_cli, ''))
                cpf_cli_atual = str(p_row_cli.get('cpf', p_row_cli.get('doc', '')) or '')
                fone_cli_atual = str(p_row_cli.get('fone', p_row_cli.get('telefone', '')) or '')
    
                with st.form("form_gerenciar_cliente_cad"):
                    col_c1, col_c2, col_c3 = st.columns(3)
                    with col_c1:
                        ed_nome_cli = st.text_input("Nome do Cliente", value=nome_cli_atual)
                    with col_c2:
                        ed_cpf_cli = st.text_input("CPF / CNPJ", value=cpf_cli_atual if cpf_cli_atual != 'None' else '')
                    with col_c3:
                        ed_fone_cli = st.text_input("Telefone", value=fone_cli_atual if fone_cli_atual != 'None' else '')
    
                    col_btn_c1, col_btn_c2 = st.columns(2)
                    with col_btn_c1:
                        btn_alt_cli = st.form_submit_button("✏️ Salvar Alterações", type="primary", use_container_width=True)
                    with col_btn_c2:
                        btn_del_cli = st.form_submit_button("🗑️ Excluir Cliente", use_container_width=True)
    
                    if btn_alt_cli:
                        if ed_nome_cli.strip():
                            try:
                                cursor = conn.cursor()
                                cursor.execute(f"UPDATE clientes SET {col_nome_cli} = ?, cpf = ?, fone = ? WHERE id = ?", (ed_nome_cli.strip().upper(), ed_cpf_cli.strip(), ed_fone_cli.strip(), id_cli_atual))
                                conn.commit()
                                st.success(f"✅ Cliente atualizado com sucesso!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Erro ao atualizar cliente: {e}")
                        else:
                            st.warning("⚠️ O nome não pode ser vazio.")
    
                    if btn_del_cli:
                        try:
                            cursor = conn.cursor()
                            cursor.execute("DELETE FROM clientes WHERE id = ?", (id_cli_atual,))
                            conn.commit()
                            st.success("🗑️ Cliente excluído com sucesso!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Erro ao excluir cliente: {e}")
            else:
                st.info("ℹ️ Nenhum cliente cadastrado no momento.")

        # -------------------------------------------------------------
        # ABA 2: FORNECEDORES
        # -------------------------------------------------------------
        with tab_forn:
            st.markdown("### 🏢 Cadastro de Fornecedores")
            with st.form("form_cad_forn"):
                n_forn = st.text_input("Nome do Fornecedor")
                t_forn = st.text_input("Telefone do Fornecedor")
                if st.form_submit_button("Salvar Fornecedor", type="primary"):
                    if n_forn.strip():
                        salvar_simples("fornecedores", "nome", n_forn.upper())
                        st.success("✅ Fornecedor cadastrado com sucesso!")
                        st.rerun()
                    else:
                        st.warning("⚠️ O nome do fornecedor não pode estar vazio.")

            st.markdown("---")
            st.markdown("### 📋 Fornecedores Cadastrados (Editar / Excluir)")
            try:
                df_fornecedores = carregar_dados("SELECT * FROM fornecedores")
            except Exception:
                df_fornecedores = pd.DataFrame()

            if df_fornecedores is not None and not df_fornecedores.empty:
                st.dataframe(df_fornecedores, use_container_width=True)
                
                col_fn = 'nome' if 'nome' in df_fornecedores.columns else df_fornecedores.columns[1]
                df_fornecedores['label_forn'] = df_fornecedores['id'].astype(str) + " - " + df_fornecedores[col_fn].astype(str)
                lista_forn_edit = df_fornecedores['label_forn'].tolist()

                forn_selecionado = st.selectbox("Selecione o Fornecedor para Gerenciar:", lista_forn_edit, key="select_forn_gerenciar_cad")
                p_row_forn = df_fornecedores[df_fornecedores['label_forn'] == forn_selecionado].iloc[0]
                id_forn_atual = int(p_row_forn['id'])
                nome_forn_atual = str(p_row_forn[col_fn])

                with st.form("form_gerenciar_fornecedor_cad"):
                    novo_nome_forn = st.text_input("Alterar Nome do Fornecedor", value=nome_forn_atual)
                    col_f1, col_f2 = st.columns(2)
                    with col_f1:
                        btn_alt_forn = st.form_submit_button("✏️ Salvar Alterações", type="primary", use_container_width=True)
                    with col_f2:
                        btn_del_forn = st.form_submit_button("🗑️ Excluir Fornecedor", use_container_width=True)

                    if btn_alt_forn:
                        if novo_nome_forn.strip():
                            cursor = conn.cursor()
                            cursor.execute(f"UPDATE fornecedores SET {col_fn} = ? WHERE id = ?", (novo_nome_forn.strip().upper(), id_forn_atual))
                            conn.commit()
                            st.success("✅ Fornecedor atualizado com sucesso!")
                            st.rerun()
                        else:
                            st.warning("⚠️ O nome não pode ser vazio.")

                    if btn_del_forn:
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM fornecedores WHERE id = ?", (id_forn_atual,))
                        conn.commit()
                        st.success("🗑️ Fornecedor excluído com sucesso!")
                        st.rerun()
            else:
                st.info("ℹ️ Nenhum fornecedor cadastrado no momento.")

        # -------------------------------------------------------------
        # ABA 3: GRUPOS
        # -------------------------------------------------------------
        with tab_grup:
            st.markdown("### 🏷️ Gestão de Grupos de Produtos")
            with st.form("form_cad_grup"):
                n_grup = st.text_input("Nome do Grupo")
                if st.form_submit_button("Salvar Grupo", type="primary"):
                    if n_grup.strip():
                        salvar_simples("grupos", "grupo", n_grup.upper())
                        st.success("✅ Grupo cadastrado com sucesso!")
                        st.rerun()
                    else:
                        st.warning("⚠️ O nome do grupo não pode estar vazio.")

            st.markdown("---")
            st.markdown("### 📋 Grupos Cadastrados (Editar / Excluir)")
            try:
                df_grupos = carregar_dados("SELECT * FROM grupos")
            except Exception:
                df_grupos = pd.DataFrame()

            if df_grupos is not None and not df_grupos.empty:
                st.dataframe(df_grupos, use_container_width=True)

                df_grupos['label_grup'] = df_grupos['id'].astype(str) + " - " + df_grupos['grupo'].astype(str)
                lista_grup_edit = df_grupos['label_grup'].tolist()

                grup_selecionado = st.selectbox("Selecione o Grupo para Gerenciar:", lista_grup_edit, key="select_grup_gerenciar_cad")
                p_row_grup = df_grupos[df_grupos['label_grup'] == grup_selecionado].iloc[0]
                id_grup_atual = int(p_row_grup['id'])
                nome_grup_atual = str(p_row_grup['grupo'])

                with st.form("form_gerenciar_grupo_cad"):
                    novo_nome_grupo = st.text_input("Alterar Nome do Grupo", value=nome_grup_atual)
                    col_g1, col_g2 = st.columns(2)
                    with col_g1:
                        btn_alt_grup = st.form_submit_button("✏️ Salvar Alterações", type="primary", use_container_width=True)
                    with col_g2:
                        btn_del_grup = st.form_submit_button("🗑️ Excluir Grupo", use_container_width=True)

                    if btn_alt_grup:
                        if novo_nome_grupo.strip():
                            cursor = conn.cursor()
                            cursor.execute("UPDATE grupos SET grupo = ? WHERE id = ?", (novo_nome_grupo.strip().upper(), id_grup_atual))
                            conn.commit()
                            st.success("✅ Grupo atualizado com sucesso!")
                            st.rerun()
                        else:
                            st.warning("⚠️ O nome não pode ser vazio.")

                    if btn_del_grup:
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM grupos WHERE id = ?", (id_grup_atual,))
                        conn.commit()
                        st.success("🗑️ Grupo excluído com sucesso!")
                        st.rerun()
            else:
                st.info("ℹ️ Nenhum grupo cadastrado no momento.")

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
    # MÓDULO CONTAS A RECEBER (COM COMPROVANTE / EXTRATO PDF)
    # -------------------------------------------------------------
    elif "Contas a Receber" in str(menu_admin):
        import io
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

        def gerar_pdf_comprovante_cliente(nome_cliente, df_contas_cliente):
            import io
            from datetime import datetime, timezone, timedelta
            from reportlab.lib.pagesizes import letter
            from reportlab.lib import colors
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

            buffer = io.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
            story = []

            styles = getSampleStyleSheet()
            
            style_header_title = ParagraphStyle(
                'HeaderTitle',
                parent=styles['Normal'],
                fontName='Helvetica-Bold',
                fontSize=18,
                textColor=colors.HexColor('#004085'),
                alignment=1,
                spaceAfter=8
            )
            style_header_sub = ParagraphStyle(
                'HeaderSub',
                parent=styles['Normal'],
                fontName='Helvetica',
                fontSize=9,
                alignment=1,
                spaceAfter=2
            )
            style_title = ParagraphStyle(
                'TitleDoc',
                parent=styles['Normal'],
                fontName='Helvetica-Bold',
                fontSize=12,
                alignment=1,
                spaceAfter=10
            )

            # Cabeçalho da Empresa
            story.append(Paragraph(f"<b>{nome_empresa_header}</b>", style_header_title))
            story.append(Paragraph("CNPJ: 194.174.39/000-42 &nbsp;&nbsp; INSC.EST.: 12.426725-4", style_header_sub))
            story.append(Paragraph("CONTATO: (99) 98814-9722 OU (99) 98414-3943", style_header_sub))
            story.append(Spacer(1, 4))
            story.append(Paragraph("Extrato Financeiro / Comprovante do Cliente", style_title))

            # Ajusta para o fuso horário do Brasil (UTC-3)
            fuso_brasil = timezone(timedelta(hours=-3))
            data_hora_atual = datetime.now(fuso_brasil).strftime("%d/%m/%Y %H:%M:%S")
            
            story.append(Paragraph(f"<b>Cliente: {nome_cliente}</b> | <b>Gerado em: {data_hora_atual}</b>", styles['Normal']))
            story.append(Spacer(1, 8))

            # Totais
            total_dev = df_contas_cliente['restante'].sum()
            total_pago = df_contas_cliente['valor_pago'].sum()

            data_totais = [
                [f"Saldo Devedor (Falta Pagar): R$ {total_dev:,.2f}", f"Total Ja Pago: R$ {total_pago:,.2f}"]
            ]
            t_totais = Table(data_totais, colWidths=[270, 270])
            t_totais.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#EAEAEA')),
                ('TEXTCOLOR', (0,0), (-1,-1), colors.black),
                ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
                ('FONTSIZE', (0,0), (-1,-1), 10),
                ('BOX', (0,0), (-1,-1), 1, colors.black),
                ('INNERGRID', (0,0), (-1,-1), 1, colors.black),
                ('PADDING', (0,0), (-1,-1), 6),
            ]))
            story.append(t_totais)
            story.append(Spacer(1, 12))

            # Tabela de Detalhamento com datas no formato DD/MM/YYYY
            data_tabela = [["ID", "Descrição / Parcela", "Total (R$)", "Pago (R$)", "Restante (R$)", "Vencimento", "Status"]]
            for _, r in df_contas_cliente.iterrows():
                venc_str = str(r['vencimento'])[:10]
                try:
                    dt_obj = datetime.strptime(venc_str, "%Y-%m-%d")
                    venc_str = dt_obj.strftime("%d/%m/%Y")
                except Exception:
                    pass

                data_tabela.append([
                    str(r['id']),
                    str(r['descricao']),
                    f"{r['valor']:,.2f}",
                    f"{r['valor_pago']:,.2f}",
                    f"{r['restante']:,.2f}",
                    venc_str,
                    str(r['status'])
                ])

            t_det = Table(data_tabela, colWidths=[30, 150, 70, 70, 70, 80, 70])
            t_det.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#004085')),
                ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE', (0,0), (-1,0), 9),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                ('PADDING', (0,0), (-1,-1), 4),
            ]))
            story.append(t_det)

            doc.build(story)
            buffer.seek(0)
            return buffer.getvalue()

        try:
            st.subheader(f"💰 Contas a Receber / Haveres — {nome_empresa_header} | 👤 Utilizador: {usr_exibicao}")
            
            conn_cr = sqlite3.connect("crm_comercio.db", timeout=30.0)
            cursor_cr = conn_cr.cursor()
            
            cursor_cr.execute("""
                CREATE TABLE IF NOT EXISTS contas_receber (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cliente TEXT,
                    valor REAL,
                    valor_pago REAL DEFAULT 0.0,
                    vencimento TEXT,
                    data_lancamento TEXT,
                    data_quitacao TEXT,
                    status TEXT,
                    descricao TEXT
                )
            """)
            conn_cr.commit()
            
            for sql_alt in [
                "ALTER TABLE contas_receber ADD COLUMN valor_pago REAL DEFAULT 0.0",
                "ALTER TABLE contas_receber ADD COLUMN data_quitacao TEXT",
                "ALTER TABLE contas_receber ADD COLUMN data_lancamento TEXT"
            ]:
                try:
                    cursor_cr.execute(sql_alt)
                    conn_cr.commit()
                except Exception:
                    pass

            df_contas = pd.read_sql_query("SELECT * FROM contas_receber ORDER BY id DESC", conn_cr)
            conn_cr.close()
            
            if df_contas is not None and not df_contas.empty:
                if 'valor_pago' not in df_contas.columns:
                    df_contas['valor_pago'] = 0.0
                
                df_contas['valor'] = pd.to_numeric(df_contas['valor'], errors='coerce').fillna(0.0)
                df_contas['valor_pago'] = pd.to_numeric(df_contas['valor_pago'], errors='coerce').fillna(0.0)
                df_contas['restante'] = df_contas['valor'] - df_contas['valor_pago']
                
                st.markdown("### 📋 Lista de Contas e Parcelas")
                st.dataframe(df_contas[['id', 'cliente', 'descricao', 'valor', 'valor_pago', 'restante', 'vencimento', 'status', 'data_quitacao']], use_container_width=True)

                st.markdown("### ⚙️ Gerenciar Conta / Registrar Haver ou Pagamento")

                df_contas['label_conta'] = "Conta #" + df_contas['id'].astype(str) + " - " + df_contas['cliente'].astype(str) + " (Restante: R$ " + df_contas['restante'].astype(str) + ")"
                lista_contas_sel = df_contas['label_conta'].tolist()

                conta_escolhida = st.selectbox("Selecione a Conta / Parcela para Baixa ou Haver:", lista_contas_sel, key="sel_conta_segura_coringa")

                row_conta_sel = df_contas[df_contas['label_conta'] == conta_escolhida].iloc[0]
                id_conta_atual = int(row_conta_sel['id'])
                valor_total_conta = float(row_conta_sel['valor'])
                valor_ja_pago = float(row_conta_sel.get('valor_pago', 0.0) or 0.0)
                restante_atual = valor_total_conta - valor_ja_pago

                st.info(f"📌 **Detalhes:** Cliente: **{row_conta_sel['cliente']}** | Total: **R$ {valor_total_conta:,.2f}** | Já Pago: **R$ {valor_ja_pago:,.2f}** | Restante: **R$ {restante_atual:,.2f}**")

                with st.form(f"form_baixa_conta_segura_{id_conta_atual}"):
                    tipo_operacao = st.radio("Escolha a Ação:", ["Receber Valor Total (Quitar)", "Dar Haver / Pagamento Parcial"], horizontal=True)
                    
                    valor_operacao = st.number_input("Valor da Operação (R$):", min_value=0.01, value=float(max(0.01, restante_atual)), format="%.2f")
                    data_pagto_input = st.date_input("Data do Pagamento / Haver:", value=datetime.now())

                    col_b1, col_b2 = st.columns(2)
                    with col_b1:
                        btn_executar = st.form_submit_button("✅ Confirmar Operação", type="primary", use_container_width=True)
                    with col_b2:
                        btn_excluir_conta = st.form_submit_button("🗑️ Excluir Conta", use_container_width=True)

                    if btn_executar:
                        try:
                            with sqlite3.connect("crm_comercio.db", timeout=30.0) as conn_up:
                                cursor_up = conn_up.cursor()
                                novo_valor_pago = valor_ja_pago + valor_operacao
                                novo_restante = valor_total_conta - novo_valor_pago
                                nova_data_str = str(data_pagto_input)

                                if tipo_operacao == "Receber Valor Total (Quitar)" or novo_restante <= 0.01:
                                    novo_status = "Quitado"
                                    data_quit_str = nova_data_str
                                    novo_valor_pago = valor_total_conta
                                else:
                                    novo_status = "Parcial"
                                    data_quit_str = "-"

                                cursor_up.execute("""
                                    UPDATE contas_receber 
                                    SET valor_pago = ?, status = ?, data_quitacao = ?
                                    WHERE id = ?
                                """, (novo_valor_pago, novo_status, data_quit_str, id_conta_atual))
                                conn_up.commit()

                            st.success(f"✅ Operação efetuada com sucesso! Restante atual: R$ {max(0.0, valor_total_conta - novo_valor_pago):,.2f}")
                            st.rerun()
                        except Exception as e_up:
                            st.error(f"❌ Erro ao atualizar: {e_up}")

                    if btn_excluir_conta:
                        try:
                            with sqlite3.connect("crm_comercio.db", timeout=30.0) as conn_del:
                                cursor_del = conn_del.cursor()
                                cursor_del.execute("DELETE FROM contas_receber WHERE id = ?", (id_conta_atual,))
                                conn_del.commit()
                            st.success("🗑️ Conta excluída com sucesso!")
                            st.rerun()
                        except Exception as e_del:
                            st.error(f"❌ Erro ao excluir: {e_del}")

                # Botão para gerar e baixar o Comprovante/Extrato do Cliente em PDF
                st.markdown("---")
                cliente_selecionado_nome = str(row_conta_sel['cliente'])
                df_cliente_filtrado = df_contas[df_contas['cliente'] == cliente_selecionado_nome]

                pdf_bytes = gerar_pdf_comprovante_cliente(cliente_selecionado_nome, df_cliente_filtrado)

                st.download_button(
                    label=f"📄 Baixar Extrato / Comprovante PDF ({cliente_selecionado_nome})",
                    data=pdf_bytes,
                    file_name=f"comprovante_{cliente_selecionado_nome.lower().replace(' ', '_')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )

            else:
                st.info("ℹ️ Nenhuma conta pendente encontrada.")
        except Exception as err_geral:
            st.error(f"❌ Ocorreu um erro ao carregar o módulo Contas a Receber: {err_geral}")
        
    # -------------------------------------------------------------
    # 10. ESTOQUE E PROMOÇÕES
    # -------------------------------------------------------------
    if "Estoque de Produtos" in str(menu_admin) or menu_admin == "📦 Estoque de Produtos":
        st.subheader("📦 Estoque de Produtos e Promoções")
        
        tab_estoque_geral, tab_deposito_promo, tab_comprados, tab_vendidos = st.tabs([
            "📋 Estoque Geral", 
            "🏷️ Depósito / Produtos para Promoção", 
            "📥 Produtos Comprados", 
            "📤 Produtos Vendidos"
        ])
        
        # -------------------------------------------------------------
        # ABA 1: ESTOQUE GERAL
        # -------------------------------------------------------------
        with tab_estoque_geral:
            st.markdown("### 📋 Produtos no Estoque Geral")
            
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS produtos (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        codigo TEXT,
                        produto TEXT,
                        quantidade REAL,
                        valor_compra REAL,
                        valor_venda REAL,
                        grupo TEXT,
                        fornecedor TEXT
                    )
                """)
                conn.commit()
            except Exception:
                pass
    
            try:
                df_prods = carregar_dados("SELECT * FROM produtos")
            except Exception:
                df_prods = pd.DataFrame()
    
            if df_prods is not None and not df_prods.empty:
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
    
                grupos_disponiveis = carregar_coluna("grupos", "grupo") or ["GERAL"]
                grupo_atual = str(p_row_est.get('grupo', 'GERAL'))
                indice_grupo = grupos_disponiveis.index(grupo_atual) if grupo_atual in grupos_disponiveis else 0
    
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
                        ed_grupo = st.selectbox("Grupo", grupos_disponiveis, index=indice_grupo)
    
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
                            st.success("🗑️ Produto removido do estoque com sucesso!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Erro ao excluir produto: {e}")
            else:
                st.warning("⚠️ Nenhum produto cadastrado no estoque geral.")
    
        # -------------------------------------------------------------
        # ABA 2: DEPÓSITO / PRODUTOS PARA PROMOÇÃO
        # -------------------------------------------------------------
        with tab_deposito_promo:
            st.markdown("### 🏷️ Enviar Produto para Promoção no PDV")
            st.markdown("Selecione um produto, defina o preço promocional, a quantidade mínima para ativação no PDV e o limite de estoque da promoção.")
            
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS promocoes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        produto_id INTEGER,
                        preco_promo REAL,
                        qtd_minima REAL,
                        qtd_estoque_promo REAL,
                        ativo INTEGER DEFAULT 1
                    )
                """)
                conn.commit()
            except Exception:
                pass
    
            df_prods_promo = carregar_dados("SELECT * FROM produtos")
            
            if df_prods_promo is not None and not df_prods_promo.empty:
                df_prods_promo['label_promo'] = df_prods_promo['id'].astype(str) + " - " + df_prods_promo['produto'].astype(str)
                lista_prods_promo = df_prods_promo['label_promo'].tolist()
                
                prod_selecionado_promo = st.selectbox("Selecione o Produto para Promoção:", lista_prods_promo, key="select_prod_promo_corrigido")
                
                p_row_promo = df_prods_promo[df_prods_promo['label_promo'] == prod_selecionado_promo].iloc[0]
                id_prod_promo = int(p_row_promo['id'])
                qtd_estoque_atual_geral = float(p_row_promo.get('quantidade', 0.0) or 0.0)
                
                col_p1, col_p2, col_p3 = st.columns(3)
                with col_p1:
                    preco_promocional = st.number_input("Preço Promocional (R$)", value=float(p_row_promo.get('valor_venda', 0.0) or 0.0), format="%.2f", key="input_preco_promo_corr")
                with col_p2:
                    qtd_minima_ativacao = st.number_input("Qtd. Mínima p/ Ativar PDV", value=1.0, step=1.0, min_value=1.0, key="input_qtd_min_corr")
                with col_p3:
                    qtd_estoque_promo = st.number_input(
                        "Qtd. Estoque da Promoção", 
                        value=float(max(0.0, qtd_estoque_atual_geral)), 
                        step=1.0, 
                        min_value=0.0, 
                        key="input_qtd_est_promo_corr"
                    )
                
                st.markdown("")
                btn_enviar_pdv = st.button("🚀 Enviar para o PDV (Ativar Promoção)", type="primary", use_container_width=True, key="btn_enviar_promo_corr")
                
                if btn_enviar_pdv:
                    try:
                        cursor = conn.cursor()
                        cursor.execute("SELECT id FROM promocoes WHERE produto_id = ?", (id_prod_promo,))
                        existe_promo = cursor.fetchone()
                        
                        if existe_promo:
                            cursor.execute("""
                                UPDATE promocoes 
                                SET preco_promo = ?, qtd_minima = ?, qtd_estoque_promo = ?, ativo = 1
                                WHERE produto_id = ?
                            """, (preco_promocional, qtd_minima_ativacao, qtd_estoque_promo, id_prod_promo))
                        else:
                            cursor.execute("""
                                INSERT INTO promocoes (produto_id, preco_promo, qtd_minima, qtd_estoque_promo, ativo)
                                VALUES (?, ?, ?, ?, 1)
                            """, (id_prod_promo, preco_promocional, qtd_minima_ativacao, qtd_estoque_promo))
                        
                        conn.commit()
                        st.success(f"✅ Promoção de '{p_row_promo['produto']}' ativada com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Erro ao salvar promoção: {e}")
                
                st.markdown("---")
                st.markdown("### 📋 Promoções Configuradas para o PDV")
                try:
                    df_promos_ativas = carregar_dados("""
                        SELECT 
                            p.id as ID, 
                            pr.produto as Produto, 
                            p.preco_promo as [Preço Promo (R$)], 
                            p.qtd_minima as [Qtd. Mínima PDV],
                            p.qtd_estoque_promo as [Estoque da Promoção]
                        FROM promocoes p 
                        JOIN produtos pr ON p.produto_id = pr.id 
                        WHERE p.ativo = 1
                    """)
                    if df_promos_ativas is not None and not df_promos_ativas.empty:
                        st.dataframe(df_promos_ativas, use_container_width=True)
    
                        st.markdown("---")
                        st.markdown("### 🛠️ Editar ou Excluir Promoção Configurada")
                        
                        df_promos_ativas['label_promo_edit'] = df_promos_ativas['ID'].astype(str) + " - " + df_promos_ativas['Produto'].astype(str)
                        lista_promos_edit = df_promos_ativas['label_promo_edit'].tolist()
                        
                        promo_selecionada_gerir = st.selectbox("Selecione a Promoção para Gerenciar:", lista_promos_edit, key="select_promo_gerenciar_admin")
                        
                        p_row_selecionada = df_promos_ativas[df_promos_ativas['label_promo_edit'] == promo_selecionada_gerir].iloc[0]
                        id_promo_atual = int(p_row_selecionada['ID'])
    
                        cursor = conn.cursor()
                        cursor.execute("SELECT preco_promo, qtd_minima, qtd_estoque_promo FROM promocoes WHERE id = ?", (id_promo_atual,))
                        dados_atuais_promo = cursor.fetchone()
    
                        val_ant_preco = float(dados_atuais_promo[0]) if dados_atuais_promo else 0.0
                        val_ant_min = float(dados_atuais_promo[1]) if dados_atuais_promo else 1.0
                        val_ant_est = float(dados_atuais_promo[2]) if dados_atuais_promo else 0.0
    
                        col_ed1, col_ed2, col_ed3 = st.columns(3)
                        with col_ed1:
                            edit_preco_promo = st.number_input("Novo Preço Promo (R$)", value=val_ant_preco, format="%.2f", key="edit_val_promo")
                        with col_ed2:
                            edit_qtd_min = st.number_input("Nova Qtd. Mínima PDV", value=val_ant_min, step=1.0, min_value=1.0, key="edit_qtd_min_promo")
                        with col_ed3:
                            edit_estoque_promo = st.number_input("Novo Estoque Promo", value=val_ant_est, step=1.0, min_value=0.0, key="edit_est_promo")
    
                        col_btn_p1, col_btn_p2 = st.columns(2)
                        with col_btn_p1:
                            if st.button("✏️ Salvar Alterações da Promoção", type="primary", use_container_width=True, key="btn_salvar_alt_promo"):
                                try:
                                    cursor.execute("""
                                        UPDATE promocoes 
                                        SET preco_promo = ?, qtd_minima = ?, qtd_estoque_promo = ?
                                        WHERE id = ?
                                    """, (edit_preco_promo, edit_qtd_min, edit_estoque_promo, id_promo_atual))
                                    conn.commit()
                                    st.success("✅ Promoção atualizada com sucesso!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Erro ao atualizar promoção: {e}")
    
                        with col_btn_p2:
                            if st.button("🗑️ Excluir / Desativar Promoção", use_container_width=True, key="btn_excluir_promo_pdv"):
                                try:
                                    cursor.execute("UPDATE promocoes SET ativo = 0 WHERE id = ?", (id_promo_atual,))
                                    conn.commit()
                                    st.success("🗑️ Promoção removida/desativada com sucesso!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Erro ao excluir promoção: {e}")
                    else:
                        st.info("ℹ️ Nenhuma promoção ativa configurada no momento.")
                except Exception:
                    st.info("ℹ️ Nenhuma promoção ativa encontrada.")
            else:
                st.warning("⚠️ Cadastre produtos no estoque geral primeiro.")
    
        # -------------------------------------------------------------
        # ABA 3: PRODUTOS COMPRADOS (Com Filtro e Botão de Limpar)
        # -------------------------------------------------------------
        with tab_comprados:
            st.markdown("### 📥 Histórico de Produtos Comprados")
            
            col_fc1, col_fc2, col_fc3 = st.columns(3)
            with col_fc1:
                try:
                    lista_forn_db = carregar_coluna("compras", "fornecedor") or carregar_coluna("produtos", "fornecedor") or []
                except Exception:
                    lista_forn_db = []
                opcoes_forn = ["Todos"] + [str(f) for f in lista_forn_db if f and str(f).strip() != '']
                fornecedor_selecionado = st.selectbox("Filtrar por Fornecedor:", sorted(list(set(opcoes_forn))), key="filtro_forn_compras_aba")
            with col_fc2:
                dt_inicio_compra = st.date_input("Data Inicial (Compra)", key="dt_ini_compra_filtro")
            with col_fc3:
                dt_fim_compra = st.date_input("Data Final (Compra)", key="dt_fim_compra_filtro")
    
            try:
                df_compras = carregar_dados("SELECT * FROM compras")
            except Exception:
                df_compras = pd.DataFrame()
    
            if df_compras is not None and not df_compras.empty:
                df_comp_filtrado = df_compras.copy()
                if fornecedor_selecionado != "Todos" and 'fornecedor' in df_comp_filtrado.columns:
                    df_comp_filtrado = df_comp_filtrado[df_comp_filtrado['fornecedor'] == fornecedor_selecionado]
                
                st.dataframe(df_comp_filtrado, use_container_width=True)
                
                st.markdown("---")
                if st.button("🗑️ Limpar Histórico de Compras", key="btn_limpar_hist_compras"):
                    try:
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM compras")
                        conn.commit()
                        st.success("✅ Histórico de compras limpo com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Erro ao limpar histórico de compras: {e}")
            else:
                st.info("ℹ️ Nenhum registo de compras encontrado na base de dados.")    
        # -------------------------------------------------------------
        # ABA 4: PRODUTOS VENDIDOS
        # -------------------------------------------------------------
        with tab_vendidos:
            st.markdown("### 📤 Histórico de Produtos Vendidos")

            col_fv1, col_fv2 = st.columns(2)

            with col_fv1:
                dt_inicio_venda = st.date_input(
                    "Data Inicial (Venda)",
                    key="dt_ini_venda_filtro"
                )

            with col_fv2:
                dt_fim_venda = st.date_input(
                    "Data Final (Venda)",
                    key="dt_fim_venda_filtro"
                )

            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
                tabelas_existentes = [
                    row[0] for row in cursor.fetchall()
                ]

                tabela_vendas_alvo = (
                    "itens_venda"
                    if "itens_venda" in tabelas_existentes
                    else "vendas"
                )

                df_vendas_hist = carregar_dados(
                    f"SELECT * FROM {tabela_vendas_alvo}"
                )

            except Exception:
                df_vendas_hist = pd.DataFrame()

            if df_vendas_hist is not None and not df_vendas_hist.empty:

                st.dataframe(
                    df_vendas_hist,
                    use_container_width=True
                )

                st.markdown("---")

                # LIMPAR HISTÓRICO
                if st.button(
                    "🗑️ Limpar Histórico de Vendas",
                    key="btn_limpar_hist_vendas"
                ):
                    try:
                        cursor.execute(
                            f"DELETE FROM {tabela_vendas_alvo}"
                        )
                        conn.commit()

                        st.success(
                            "✅ Histórico limpo com sucesso!"
                        )
                        st.rerun()

                    except Exception as e:
                        conn.rollback()
                        st.error(
                            f"❌ Erro ao limpar histórico: {e}"
                        )

                # -------------------------------------------------
                # ESTORNO DE VENDA — estoque + caixa, sem afetar outras vendas
                st.markdown("---")
                st.markdown("### 🔄 Estornar Venda e Atualizar Caixa")

                with st.form(key="form_estorno_venda_final"):
                    id_venda_estorno = st.number_input(
                        "Digite o ID da primeira linha da venda (coluna ID):",
                        min_value=1, step=1, value=1
                    )
                    submitted = st.form_submit_button(
                        "❌ Confirmar Estorno da Venda", type="primary"
                    )

                if submitted:
                    try:
                        cursor = conn.cursor()
                        cursor.execute("BEGIN IMMEDIATE")

                        # O PDV grava os produtos vendidos individualmente em 'vendas'.
                        # O ID digitado identifica uma linha; agrupamos as linhas
                        # da mesma venda por cliente, data e vendedor.
                        cursor.execute("PRAGMA table_info(vendas)")
                        cols_vendas = [c[1] for c in cursor.fetchall()]
                        obrigatorias = {"id", "produto", "quantidade", "cliente", "data"}
                        if not obrigatorias.issubset(set(cols_vendas)):
                            raise Exception("A tabela vendas não possui as colunas necessárias ao estorno.")

                        cursor.execute(
                            "SELECT id, cliente, data, vendedor FROM vendas WHERE id = ? AND tipo = 'VENDA'",
                            (int(id_venda_estorno),)
                        )
                        venda_base = cursor.fetchone()
                        if not venda_base:
                            raise Exception("Venda não encontrada. Confira o ID na tabela de vendas.")

                        _, cliente_base, data_base, vendedor_base = venda_base
                        if "vendedor" in cols_vendas:
                            cursor.execute(
                                """SELECT id, produto, quantidade FROM vendas
                                   WHERE cliente IS ? AND data IS ? AND vendedor IS ? AND tipo = 'VENDA'
                                   ORDER BY id""",
                                (cliente_base, data_base, vendedor_base)
                            )
                        else:
                            cursor.execute(
                                """SELECT id, produto, quantidade FROM vendas
                                   WHERE cliente IS ? AND data IS ? AND tipo = 'VENDA'
                                   ORDER BY id""",
                                (cliente_base, data_base)
                            )
                        itens_venda = cursor.fetchall()
                        if not itens_venda:
                            raise Exception("Não foram encontrados os itens desta venda.")

                        ids_linhas = [int(item[0]) for item in itens_venda]
                        id_principal_venda = min(ids_linhas)
                        total_venda = 0.0
                        if "valor_total" in cols_vendas:
                            cursor.execute(
                                f"SELECT COALESCE(SUM(CAST(valor_total AS REAL)), 0) FROM vendas WHERE id IN ({','.join('?' for _ in ids_linhas)})",
                                ids_linhas
                            )
                            total_venda = float(cursor.fetchone()[0] or 0)
                        else:
                            raise Exception("Não encontrei a coluna valor_total para conferir o valor da venda.")

                        # Devolve cada item ao estoque uma única vez.
                        for _, produto, quantidade in itens_venda:
                            if not produto:
                                continue
                            cursor.execute(
                                """UPDATE produtos
                                   SET quantidade = COALESCE(CAST(quantidade AS REAL), 0) + ?
                                   WHERE UPPER(TRIM(produto)) = UPPER(TRIM(?))""",
                                (float(quantidade or 0), str(produto))
                            )
                            if cursor.rowcount == 0:
                                raise Exception(f"Produto não encontrado no estoque: {produto}")

                        # Remove o lançamento financeiro exato, nunca os outros movimentos.
                        cursor.execute("PRAGMA table_info(caixa_movimentacoes)")
                        cols_mov = [c[1] for c in cursor.fetchall()]
                        movimento_removido = 0
                        if "venda_id" in cols_mov:
                            cursor.execute(
                                "DELETE FROM caixa_movimentacoes WHERE venda_id = ? AND UPPER(TRIM(tipo)) = 'VENDA'",
                                (id_principal_venda,)
                            )
                            movimento_removido = cursor.rowcount

                        # Compatibilidade com vendas antigas, feitas antes do vínculo venda_id.
                        # Só remove se houver exatamente um movimento com mesma data e valor.
                        if movimento_removido == 0 and "venda_id" in cols_mov:
                            cursor.execute(
                                """SELECT id FROM caixa_movimentacoes
                                   WHERE venda_id IS NULL
                                     AND UPPER(TRIM(tipo)) = 'VENDA'
                                     AND data = ? AND ABS(COALESCE(valor, 0) - ?) < 0.01
                                     AND descricao LIKE 'Venda PDV%'""",
                                (data_base, total_venda)
                            )
                            candidatos_mov = cursor.fetchall()
                            if len(candidatos_mov) == 1:
                                cursor.execute("DELETE FROM caixa_movimentacoes WHERE id = ?", (candidatos_mov[0][0],))
                                movimento_removido = cursor.rowcount
                            elif len(candidatos_mov) > 1:
                                raise Exception("Há mais de um movimento antigo compatível com esta venda. Nenhum movimento do caixa foi apagado; é necessário identificar o lançamento correto.")

                        # Cancela eventual conta a receber vinculada à venda fiada.
                        if "contas_receber" in [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]:
                            cursor.execute("DELETE FROM contas_receber WHERE descricao LIKE ?", (f"%#{id_principal_venda}%",))

                        # Exclui todas as linhas de produtos que compõem esta venda.
                        cursor.execute(
                            f"DELETE FROM vendas WHERE id IN ({','.join('?' for _ in ids_linhas)})",
                            ids_linhas
                        )

                        # Remove também o detalhe do histórico, se existir.
                        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                        tabelas_db = {r[0] for r in cursor.fetchall()}
                        if "vendas_itens" in tabelas_db:
                            cursor.execute("DELETE FROM vendas_itens WHERE venda_id = ?", (id_principal_venda,))
                        if "vendas_cabecalho" in tabelas_db:
                            # Cabeçalho do PDV não guarda atualmente o ID da linha de vendas;
                            # não removemos por aproximação para não apagar outra venda.
                            pass

                        conn.commit()
                        try:
                            st.cache_data.clear()
                        except Exception:
                            pass

                        if movimento_removido:
                            st.success(f"✅ Venda #{id_principal_venda} estornada! Estoque devolvido e R$ {total_venda:,.2f} retirados do caixa.")
                        else:
                            st.warning(f"Venda #{id_principal_venda} e estoque estornados. Não foi encontrado um movimento antigo inequívoco para retirar do caixa; confira o histórico financeiro.")
                        st.rerun()

                    except Exception as e:
                        conn.rollback()
                        st.error(f"❌ Erro ao executar estorno: {e}")

            else:
                st.info(
                    "ℹ️ Nenhum registro de vendas encontrado."
                )

    # -------------------------------------------------------------
    # 11. CONFIGURAÇÕES
    # -------------------------------------------------------------
    elif menu_admin == "🏢 Configurações da Empresa":
        st.subheader("🏢 Configurações e Dados da Empresa")

        st.markdown("### 🔑 Ativação e Limite de Dispositivos")

        df_devs_count = carregar_dados("""
            SELECT COUNT(*) AS total
            FROM empresas_dispositivos
            WHERE ativado = 1
        """)
        total_ativados = (
            int(df_devs_count.iloc[0]["total"])
            if not df_devs_count.empty else 0
        )

        limite_permitido = max(
            1, int(reg_emp.get("limite_dispositivos", 2) or 2)
        )

        st.info(
            f"📊 **Status de Licença de Dispositivos:** "
            f"{total_ativados} de {limite_permitido} dispositivo(s) autorizados."
        )

        if dispositivo_esta_ativado:
            dias_val = st.session_state.get(
                "dias_licenca",
                reg_emp.get("dias_licenca", 30)
            )
            st.success(
                f"✅ Este dispositivo está **ATIVADO**! "
                f"Licença válida por {dias_val} dias."
            )
            st.markdown("#### 🔄 Renovação da licença")

        else:
            if total_ativados >= limite_permitido:
                st.error(
                    f"❌ Limite atingido! O limite máximo de "
                    f"{limite_permitido} dispositivo(s) já foi alcançado."
                )
                # --- BOTÃO DIRETO DE RESET DE DISPOSITIVOS ---
                st.markdown("---")
                if st.button("🗑️ Limpar / Resetar Dispositivos Autorizados", type="primary"):
                    try:
                        cursor = conn.cursor()
                        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                        tabelas_existentes = [row[0] for row in cursor.fetchall()]
                        
                        tabelas_alvo = [t for t in tabelas_existentes if any(termo in t.lower() for termo in ["dispositivo", "device", "licenca", "ativacao"])]
                        
                        if tabelas_alvo:
                            for tab in tabelas_alvo:
                                cursor.execute(f"DELETE FROM {tab}")
                            conn.commit()
                            
                            try:
                                st.cache_data.clear()
                            except Exception:
                                pass
                                
                            st.session_state['dispositivo_ativado'] = False
                            st.success("✅ Dispositivos limpos com sucesso! O sistema está livre para novas ativações.")
                            st.rerun()
                        else:
                            st.session_state['dispositivo_ativado'] = False
                            st.success("✅ Estado limpo com sucesso!")
                            st.rerun()
                    except Exception as e:
                        st.error(f"❌ Erro ao limpar: {e}")
            else:
                st.warning(
                    "⚠️ Insira a chave de ativação para liberar este dispositivo."
                )

        # O campo de chave permanece disponível para renovar
        # sem desativar o aparelho antes da validação.
        pode_inserir_chave = (
            dispositivo_esta_ativado
            or total_ativados < limite_permitido
        )

        if pode_inserir_chave:
            doc_atual = str(reg_emp.get("cnpj", "19417439000142"))
            st.info(f"Empresa Atual (CNPJ/CPF): `{doc_atual}`")

            chave_digitada = st.text_input(
                "Chave de Ativação:",
                key="input_chave_ativacao_config"
            )

            texto_botao = (
                "🔄 Inserir Nova Chave / Renovar"
                if dispositivo_esta_ativado
                else "🔓 Ativar Este Dispositivo"
            )

            if st.button(
                texto_botao,
                type="primary",
                key="btn_ativar_dispositivo_config"
            ):
                apenas_digitos = "".join(
                    filter(str.isdigit, str(doc_atual))
                )
                chave_limpa = str(chave_digitada).strip().upper()

                sucesso = False
                dias_validade = 0
                limite_extraido = 1

                for sufixo, dias in [
                    ("TESTE", 7),
                    ("MENSAL", 30),
                    ("ANUAL", 365)
                ]:
                    for lim_test in range(1, 20):
                        base_hash_str = (
                            apenas_digitos
                            + "REY_CEBOLA_2026"
                            + sufixo
                            + str(lim_test)
                        )

                        hash_hex = hashlib.md5(
                            base_hash_str.encode()
                        ).hexdigest().upper()

                        chave_esperada = (
                            f"CRM-{sufixo}-{lim_test}D-"
                            f"{hash_hex[:4]}-{hash_hex[4:8]}"
                        )

                        if chave_limpa == chave_esperada:
                            sucesso = True
                            dias_validade = dias
                            limite_extraido = lim_test
                            break

                    if sucesso:
                        break

                if sucesso:
                    cursor = conn.cursor()

                    # Na renovação, mantém o limite que já estava salvo.
                    # Só uma alteração feita nas configurações da empresa
                    # poderá aumentar a quantidade de dispositivos.
                    if dispositivo_esta_ativado:
                        limite_final = limite_permitido
                    else:
                        limite_final = limite_extraido

                    cursor.execute("""
                        UPDATE empresas_dispositivos
                        SET ativado = 1,
                            dias_licenca = ?,
                            limite_dispositivos = ?
                        WHERE device_id = ?
                    """, (
                        dias_validade,
                        limite_final,
                        device_id
                    ))

                    conn.commit()

                    st.session_state["dispositivo_ativado"] = True
                    st.session_state["dias_licenca"] = dias_validade
                    st.session_state["limite_dispositivos"] = limite_final

                    st.success(
                        f"🎉 Licença renovada/ativada com sucesso! "
                        f"Validade: {dias_validade} dias. "
                        f"Limite mantido: {limite_final} dispositivo(s)."
                    )
                    st.rerun()

                else:
                    st.error(
                        "❌ Chave inválida para este CNPJ/CPF "
                        "ou limite de dispositivos incorreto."
                    )

        st.markdown("---")

        with st.form("form_cfg_emp"):
            st.markdown("### 📝 Dados Gerais e Limites da Empresa")

            nome_emp = st.text_input(
                "Razão Social / Nome Fantasia",
                value=str(reg_emp.get("nome_empresa", "REY DA CEBOLA"))
            )
            cnpj_emp = st.text_input(
                "CNPJ ou CPF",
                value=str(reg_emp.get("cnpj", "19417439000142"))
            )
            inscr_est_emp = st.text_input(
                "INSCR. EST",
                value=str(reg_emp.get("inscr_est", "12.426.725-4"))
            )
            tel_emp = st.text_input(
                "Telefone de Contato",
                value=str(reg_emp.get("fone", "(99) 98501-6050"))
            )
            end_emp = st.text_input(
                "Endereço Completo",
                value=str(reg_emp.get("endereco", "RUA CAIPIRA, Nº 174"))
            )

            df_ativos_cfg = carregar_dados("""
                SELECT COUNT(*) AS total
                FROM empresas_dispositivos
                WHERE ativado = 1
            """)

            qtd_ativos_cfg = (
                int(df_ativos_cfg.iloc[0]["total"])
                if not df_ativos_cfg.empty else 0
            )

            limite_atual_cfg = max(
                1,
                qtd_ativos_cfg,
                int(reg_emp.get("limite_dispositivos", 2) or 2)
            )

            dias_atual_cfg = max(
                1, int(reg_emp.get("dias_licenca", 30) or 30)
            )

            lim_disp = st.number_input(
                "💻 Limite Máximo de Dispositivos Permitidos",
                min_value=max(1, qtd_ativos_cfg),
                max_value=50,
                value=min(50, limite_atual_cfg),
                help=(
                    "O limite só será aumentado quando você alterar "
                    "este número e salvar as configurações."
                )
            )

            dias_cfg = st.number_input(
                "📅 Duração da licença (dias)",
                min_value=1,
                max_value=3650,
                value=min(3650, dias_atual_cfg),
                step=1
            )

            if st.form_submit_button(
                "💾 Salvar Configurações",
                type="primary"
            ):
                cursor = conn.cursor()

                # Atualiza os dados gerais de todos os aparelhos,
                # sem alterar o campo ativado.
                cursor.execute("""
                    UPDATE empresas_dispositivos
                    SET nome_empresa = ?,
                        cnpj = ?,
                        ie = ?,
                        fone = ?,
                        endereco = ?,
                        dias_licenca = ?,
                        limite_dispositivos = ?
                """, (
                    nome_emp,
                    cnpj_emp,
                    inscr_est_emp,
                    tel_emp,
                    end_emp,
                    int(dias_cfg),
                    int(lim_disp)
                ))

                # Garante que o aparelho atual tenha um registro.
                cursor.execute("""
                    SELECT COUNT(*)
                    FROM empresas_dispositivos
                    WHERE device_id = ?
                """, (device_id,))

                registro_existe = cursor.fetchone()[0] > 0

                if not registro_existe:
                    cursor.execute("""
                        INSERT INTO empresas_dispositivos
                            (device_id, nome_empresa, cnpj, ie,
                             fone, endereco, ativado,
                             dias_licenca, limite_dispositivos)
                        VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
                    """, (
                        device_id,
                        nome_emp,
                        cnpj_emp,
                        inscr_est_emp,
                        tel_emp,
                        end_emp,
                        int(dias_cfg),
                        int(lim_disp)
                    ))

                conn.commit()

                st.session_state["limite_dispositivos"] = int(lim_disp)
                st.session_state["dias_licenca"] = int(dias_cfg)

                st.success(
                    "✅ Configurações atualizadas! "
                    "As ativações existentes foram preservadas."
                )
                st.rerun()
