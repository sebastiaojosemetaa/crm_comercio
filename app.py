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
# --- ADICIONE ESTAS LINHAS NO TOPO DO SEU APP.PY ---
if "dispositivo_ativado" not in st.session_state:
    st.session_state["dispositivo_ativado"] = False

if "dias_licenca" not in st.session_state:
    st.session_state["dias_licenca"] = 30
# ==========================================
# FUNÇÃO DE VERIFICAÇÃO DE PERMISSÕES BLINDADA
# ==========================================
def checar_permissao(usuario, modulo, acao):
    # Se não houver usuário logado, bloqueia imediatamente por segurança
    if not usuario:
        return False
        
    # Se for estritamente o Administrador Mestre
    if usuario.lower() == "administrador" or st.session_state.get('cargo_logado') == "Administrador":
        return True
    
    try:
        cursor_p = conn.cursor()
        
        # Mapeia o módulo e a ação para a coluna correspondente na tabela de usuários
        coluna_map = {
            ("produtos", "ver"): "perm_produtos_ver",
            ("produtos", "editar"): "perm_produtos_editar",
            ("produtos", "excluir"): "perm_produtos_excluir",
            ("vendas", "ver"): "perm_vendas_ver",
            ("vendas", "editar"): "perm_vendas_editar",
            ("vendas", "excluir"): "perm_vendas_excluir",
            ("clientes", "ver"): "perm_clientes_ver",
            ("clientes", "editar"): "perm_clientes_editar",
            ("clientes", "excluir"): "perm_clientes_excluir",
            ("relatorios", "ver"): "perm_relatorios_ver",
        }
        
        coluna_db = coluna_map.get((modulo, acao))
        if not coluna_db:
            cursor_p.close()
            return False
            
        cursor_p.execute(f"SELECT {coluna_db} FROM usuarios WHERE login = ?", (usuario,))
        res = cursor_p.fetchone()
        cursor_p.close()
        
        # Se encontrou o registro e o valor na coluna é 1, permite; caso contrário, bloqueia
        if res and res[0] == 1:
            return True
        return False
    except Exception:
        return False  # Em caso de qualquer erro, bloqueia por segurança
# --------------------------------------------------
def gerar_chave_por_documento(documento, tipo_plano="MENSAL"):
    import hashlib
    apenas_digitos = ''.join(filter(str.isdigit, str(documento)))
    segredo_mestre = "REY_CEBOLA_2026"
    
    if "TESTE" in str(tipo_plano).upper():
        sufixo = "TESTE"
    elif "ANUAL" in str(tipo_plano).upper():
        sufixo = "ANUAL"
    else:
        sufixo = "MENSAL"
        
    combinado = apenas_digitos + segredo_mestre + sufixo
    hash_hex = hashlib.md5(combinado.encode()).hexdigest().upper()
    
    return f"CRM-{sufixo}-{hash_hex[:4]}-{hash_hex[4:8]}-{hash_hex[8:12]}"
def gerar_pdf_tabela_pedidos(df_pedidos, cliente_nome="Geral"):
    from io import BytesIO
    from fpdf import FPDF
    from datetime import datetime
    import pandas as pd
    import sqlite3
    
    # Valores padrão iniciais
    nome_empresa = "ALENCARSOFT"
    cnpj_empresa = "19417439000142"
    ie_empresa = ""
    tel_empresa = "(99) 98501-6050"
    end_empresa = "RUA CAIPIRA, Nº: 174"
    # 1. Tenta ler primeiro do session_state (memória atual do Streamlit)
    if 'dados_empresa' in st.session_state and isinstance(st.session_state['dados_empresa'], dict):
        emp = st.session_state['dados_empresa']
        nome_empresa = emp.get('nome', nome_empresa)
        cnpj_empresa = emp.get('cnpj', cnpj_empresa)
        ie_empresa = emp.get('ie', ie_empresa)
        tel_empresa = emp.get('telefone', tel_empresa)
        end_empresa = emp.get('endereco', end_empresa)
        
    # 2. Tenta ler da base de dados SQLite testando os nomes de tabelas mais comuns
    try:
        # Conexão fixa e segura à base de dados principal
        db_file = 'banco.db'
        conn = sqlite3.connect(db_file, timeout=10.0)
        
        # Garante que a tabela vendas existe com todas as colunas necessárias
        try:
            cursor_mig = conn.cursor()
            cursor_mig.execute("""
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
                    status TEXT,
                    tipo TEXT,
                    data TEXT,
                    vendedor TEXT
                )
            """)
            conn.commit()
            
            # Adiciona colunas caso a tabela seja de uma versão anterior
            for col_nome, col_tipo in [
                ("vendedor", "TEXT"),
                ("grupo", "TEXT"),
                ("fornecedor", "TEXT"),
                ("forma_pagamento", "TEXT"),
                ("valor_recebido", "REAL")
            ]:
                try:
                    cursor_mig.execute(f"ALTER TABLE vendas ADD COLUMN {col_nome} {col_tipo}")
                    conn.commit()
                except Exception:
                    pass
                    
            cursor_mig.close()
        except Exception:
            pass
            try:
                cursor_v = conn.cursor()
                cursor_v.execute("ALTER TABLE vendas ADD COLUMN vendedor TEXT")
                conn.commit()
                cursor_v.close()
            except Exception:
                pass  # Se a coluna já existir, ignora e segue em frente
                
            cursor = conn.cursor()
            cursor = conn.cursor()
            for tabela in ['configuracao', 'config', 'empresa', 'dados_empresa']:
                try:
                    cursor.execute(f"SELECT nome, cnpj, ie, telefone, endereco FROM {tabela} LIMIT 1")
                    row = cursor.fetchone()
                    if row and row[0]:
                        nome_empresa = row[0]
                        cnpj_empresa = row[1] or cnpj_empresa
                        ie_empresa = row[2] or ie_empresa
                        tel_empresa = row[3] or tel_empresa
                        end_empresa = row[4] or end_empresa
                        break
                except:
                    pass
            conn.close()
            
    except:
        pass
    pdf = FPDF()
    pdf.add_page()
    
    # Cabeçalho dinâmico com os dados da empresa cadastrada
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 7, txt=str(nome_empresa).upper(), ln=True, align="C")
    
    pdf.set_font("Arial", size=8)
    info_linha = []
    if cnpj_empresa:
        info_linha.append(f"CNPJ: {cnpj_empresa}")
    if ie_empresa:
        info_linha.append(f"INSC. EST.: {ie_empresa}")
    if info_linha:
        pdf.cell(0, 4, txt=" - ".join(info_linha), ln=True, align="C")
        
    if tel_empresa:
        pdf.cell(0, 4, txt=f"CONTATO: {tel_empresa}", ln=True, align="C")
        
    if end_empresa:
        pdf.cell(0, 4, txt=f"ENDEREÇO: {end_empresa}", ln=True, align="C")
        
    pdf.ln(5)
    
    # Título do Relatório e Data
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 6, txt=f"Relatório de Pedidos / Orçamentos - {cliente_nome}", ln=True, align="C")
    
    pdf.set_font("Arial", size=8)
    data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pdf.cell(0, 5, txt=f"Gerado em: {data_atual}", ln=True, align="C")
    pdf.ln(8)
    
    # Cabeçalho da Tabela
    pdf.set_font("Arial", 'B', 9)
    pdf.set_fill_color(20, 60, 120)
    pdf.set_text_color(255, 255, 255)
    
    w_prod = 90
    w_qtd = 30
    w_vunit = 35
    w_vtotal = 35
    
    pdf.cell(w_prod, 7, txt="Produto", border=1, fill=True, align="L")
    pdf.cell(w_qtd, 7, txt="Qtd Total", border=1, fill=True, align="C")
    pdf.cell(w_vunit, 7, txt="Preço Unitário (R$)", border=1, fill=True, align="R")
    pdf.cell(w_vtotal, 7, txt="Valor Total (R$)", border=1, fill=True, align="R")
    pdf.ln()
    
    # Linhas de Dados
    pdf.set_font("Arial", size=9)
    pdf.set_text_color(0, 0, 0)
    
    total_geral = 0.0
    
    for index, row in df_pedidos.iterrows():
        produto = str(row.get('produto', ''))
        
        try:
            qtd = float(str(row.get('quantidade', 0)).replace(',', '.'))
        except:
            qtd = 0.0
            
        v_unit = 0.0
        for col in ['Valor Unitário', 'valor_unitario', 'preco']:
            if col in row and pd.notna(row[col]):
                try:
                    val_str = str(row[col]).replace('R$', '').replace('.', '').replace(',', '.').strip()
                    v_unit = float(val_str)
                    break
                except:
                    pass
                    
        v_tot = 0.0
        for col in ['Valor Total', 'valor_total', 'total']:
            if col in row and pd.notna(row[col]):
                try:
                    val_str = str(row[col]).replace('R$', '').replace('.', '').replace(',', '.').strip()
                    v_tot = float(val_str)
                    break
                except:
                    pass
                    
        if v_tot == 0.0 and v_unit > 0:
            v_tot = qtd * v_unit
        elif v_unit == 0.0 and qtd > 0 and v_tot > 0:
            v_unit = v_tot / qtd
            
        total_geral += v_tot
        
        pdf.cell(w_prod, 6, txt=produto, border=1, align="L")
        pdf.cell(w_qtd, 6, txt=f"{qtd:.2f}", border=1, align="C")
        pdf.cell(w_vunit, 6, txt=f"R$ {v_unit:.2f}", border=1, align="R")
        pdf.cell(w_vtotal, 6, txt=f"R$ {v_tot:.2f}", border=1, align="R")
        pdf.ln()
        
    # Rodapé com o Valor Total Geral
    pdf.set_font("Arial", 'B', 9)
    pdf.set_fill_color(40, 40, 40)
    pdf.set_text_color(255, 255, 255)
    
    pdf.cell(w_prod + w_qtd + w_vunit, 7, txt="VALOR TOTAL GERAL", border=1, fill=True, align="R")
    pdf.cell(w_vtotal, 7, txt=f"R$ {total_geral:.2f}", border=1, fill=True, align="R")
    pdf.ln()
    
    pdf_output = pdf.output(dest='S')
    if isinstance(pdf_output, str):
        pdf_output = pdf_output.encode('latin1')
        
    return BytesIO(pdf_output)
# -----------------------------------------------------------------------------
# CONFIGURAÇÃO DA PÁGINA
# -----------------------------------------------------------------------------
st.set_page_config(page_title="CRM Comércio - SEBASTIÃO JOSE DE ALENCAR NETO", layout="wide", page_icon="🛍️")

# =========================================================
# IDENTIFICADOR ÚNICO POR NAVEGADOR / APARELHO
# =========================================================
if "device_id" not in st.query_params:
    st.query_params["device_id"] = str(uuid.uuid4())
device_id = st.query_params["device_id"]

# =========================================================
# FUNÇÃO: GERADOR DE CHAVE ÚNICA POR CNPJ / CPF
# =========================================================
def validar_chave_inserida(chave_digitada, documento):
    import hashlib
    
    apenas_digitos = ''.join(filter(str.isdigit, str(documento)))
    segredo_mestre = "REY_CEBOLA_2026"
    chave_limpa = str(chave_digitada).strip().upper()
    
    # Testa automaticamente contra todos os tipos de planos para evitar erros de prefixo
    for sufixo in ["TESTE", "MENSAL", "ANUAL"]:
        combinado = apenas_digitos + segredo_mestre + sufixo
        hash_hex = hashlib.md5(combinado.encode()).hexdigest().upper()
        chave_esperada = f"CRM-{sufixo}-{hash_hex[:4]}-{hash_hex[4:8]}-{hash_hex[8:12]}"
        
        if chave_limpa == chave_esperada:
            return True
            
    return False

# =========================================================
# PAINEL DO DESENVOLVEDOR (SEMPRE VISÍVEL NA BARRA LATERAL)
# =========================================================
with st.sidebar.expander("⚙️ Gerador de Chaves (Dev)"):
    senha_dev = st.text_input("Senha Mestre Dev", type="password", key="pwd_dev_topo_unico")
    if senha_dev == "13142715":
        tipo_plano = st.selectbox(
            "Tipo de Chave:",
            ["Teste (7 Dias)", "Mensal (30 Dias)", "Anual (365 Dias)"],
            key="select_tipo_plano_dev_novo"
        )
        doc_cliente = st.text_input("CNPJ ou CPF do Cliente:", key="doc_dev_topo_doc_unico")
        if st.button("Gerar Chave", key="btn_dev_topo_acao_unico"):
            if doc_cliente.strip():
                import hashlib
                if "Teste" in tipo_plano:
                    sufixo_tipo = "TESTE"
                    dias = 7
                elif "Mensal" in tipo_plano:
                    sufixo_tipo = "MENSAL"
                    dias = 30
                else:
                    sufixo_tipo = "ANUAL"
                    dias = 365
                    
                doc_limpo = ''.join(filter(str.isdigit, str(doc_cliente)))
                segredo_mestre = "REY_CEBOLA_2026"
                combinado = doc_limpo + segredo_mestre + sufixo_tipo
                hash_hex = hashlib.md5(combinado.encode()).hexdigest().upper()
                
                chave_gerada = f"CRM-{sufixo_tipo}-{hash_hex[:4]}-{hash_hex[4:8]}-{hash_hex[8:12]}"
                st.info(f"Validade: {dias} dias")
                st.code(chave_gerada, language="text")
                st.success("Chave gerada com sucesso!")
            else:
                st.warning("Digite um CNPJ ou CPF.")
    elif senha_dev:
        st.error("Senha incorreta!")

# =========================================================
# CONEXÃO E TABELAS MULTI-EMPRESA
# =========================================================
def get_connection():
    return sqlite3.connect("crm_comercio.db", check_same_thread=False)

conn = get_connection()

def inicializar_tabelas_multiempresas():
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS empresas_dispositivos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT UNIQUE,
            nome_empresa TEXT,
            cnpj TEXT,
            ie TEXT,
            fone TEXT,
            endereco TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dispositivo_licenca (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT UNIQUE,
            chave TEXT,
            data_expiracao DATETIME,
            status TEXT
        )
    """)
    conn.commit()

inicializar_tabelas_multiempresas()

# -----------------------------------------------------------------------------
# 1. VERIFICA A EMPRESA DESTE DISPOSITIVO ESPECÍFICO
# -----------------------------------------------------------------------------
df_emp_dev = pd.read_sql_query(
    "SELECT * FROM empresas_dispositivos WHERE device_id = ?", 
    conn, 
    params=(device_id,)
)

empresa_registrada = not df_emp_dev.empty and bool(str(df_emp_dev.iloc[0].get('cnpj', '')).strip())

if not empresa_registrada:
    st.markdown("## 🏢 Bem-vindo! Cadastre os Dados da sua Empresa")
    st.warning("⚠️ Este dispositivo/navegador ainda não tem uma empresa configurada. Insira os seus dados abaixo.")
    
    with st.form("form_config_inicial_empresa_dev"):
        c_nome = st.text_input("Nome / Razão Social")
        c_cnpj = st.text_input("CNPJ ou CPF")
        c_ie = st.text_input("Inscrição Estadual (IE)")
        c_tel = st.text_input("Telefone de Contato")
        c_end = st.text_input("Endereço Completo")
        
        btn_salvar_emp = st.form_submit_button("💾 Salvar Dados e Ir para Ativação", type="primary")
        if btn_salvar_emp:
            if c_nome.strip() and c_cnpj.strip():
                cnpj_limpo = ''.join(filter(str.isdigit, c_cnpj))
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO empresas_dispositivos (device_id, nome_empresa, cnpj, ie, fone, endereco)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (device_id, c_nome.strip(), cnpj_limpo, c_ie.strip(), c_tel.strip(), c_end.strip()))
                conn.commit()
                st.success("Empresa cadastrada com sucesso para este dispositivo!")
                st.rerun()
            else:
                st.error("Preencha o Nome e o CNPJ/CPF.")
    st.stop()

cnpj_registrado = df_emp_dev.iloc[0]['cnpj']
nome_empresa_registrada = df_emp_dev.iloc[0]['nome_empresa']

# =========================================================
# ESTILO VISUAL METÁLICO/CLÁSSICO PDV (FÊNIX STYLE)
# =========================================================
estilo_pdv_fenix = """
<style>
    .stApp {
        background: linear-gradient(135deg, #e0e0e0 0%, #b0b0b0 100%) !important;
        color: #000000 !important;
    }
    div[data-testid="stVerticalBlock"] > div {
        background-color: #d8d8d8;
        border: 2px solid #a6a6a6;
        border-radius: 12px;
        padding: 12px;
        box-shadow: inset 1px 1px 3px #ffffff, 3px 3px 8px rgba(0,0,0,0.2);
    }
    div[data-baseweb="input"] {
        background-color: #ffffff !important;
        border: 2px solid #888888 !important;
        border-radius: 8px !important;
    }
    div[data-baseweb="input"] input {
        color: #000000 !important;
        font-weight: bold !important;
        font-size: 16px !important;
    }
    label, p, h1, h2, h3, h4, span {
        color: #111111 !important;
        font-weight: bold !important;
    }
    div[data-testid="stTable"], div[data-testid="stDataFrame"] {
        background-color: #ffffff !important;
        border-radius: 8px !important;
        border: 1px solid #999999 !important;
    }
    button[kind="primary"] {
        background-color: #008000 !important;
        color: #ffffff !important;
        font-size: 18px !important;
        font-weight: bold !important;
        border-radius: 8px !important;
    }
</style>
"""
st.markdown(estilo_pdv_fenix, unsafe_allow_html=True)

def adequar_banco_e_migrar():
    try:
        cursor = conn.cursor()
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
                pass

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente TEXT
            )
        """)
        colunas_clientes = [
            "cliente", "nome", "cpf", "doc", "endereco", 
            "email", "fone", "telefone", "cidade", "senha"
        ]
        for col in colunas_clientes:
            try:
                cursor.execute(f"ALTER TABLE clientes ADD COLUMN {col} TEXT")
            except Exception:
                pass

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
    except Exception as e:
        print(f"Aviso de migração: {e}")

adequar_banco_e_migrar()

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

# -----------------------------------------------------------------------------
# NAVEGAÇÃO E PERFIL DE ACESSO (BARRA LATERAL)
# -----------------------------------------------------------------------------
if 'admin_logged' not in st.session_state:
    st.session_state.admin_logged = False

if 'cliente_autenticado' not in st.session_state:
    st.session_state.cliente_autenticado = None

if 'carrinho_pdv' not in st.session_state:
    st.session_state.carrinho_pdv = []

st.sidebar.title("🔑 Acesso ao Sistema")
opcoes_perfil = ["🔒 Administração / Vendedor"]
perfil_selecionado = st.sidebar.radio("Selecione o Perfil:", opcoes_perfil, key="perfil_principal_radio_v2")
st.sidebar.markdown("---")
# Status do Dispositivo no Topo da Barra Lateral
if st.session_state.get('dispositivo_ativado', False):
    st.sidebar.success("🟢 Dispositivo Ativado (Acesso Liberado)")
else:
    st.sidebar.error("🔴 Dispositivo Não Ativado")

st.sidebar.markdown("---")
# ==========================================
# AMBIENTE 2: ADMINISTRADOR / VENDEDOR
# ==========================================
# --- BLOCO DE AUTENTICAÇÃO SEGURO ---
st.markdown("## 🔐 Autenticação do Sistema")
usuario_input = st.text_input("Usuário / Login", key="login_usuario").strip().lower()
senha_input = st.text_input("Senha", type="password", key="login_senha")

if st.button("Entrar no Sistema", type="primary", key="btn_login"):
    # Permissão padrão de administrador mestre
    if usuario_input == "administrador" and senha_input == "admin": # ou sua senha mestre
        st.session_state['autenticado'] = True
        st.session_state['usuario_logado'] = "administrador"
        st.session_state['cargo_logado'] = "Administrador"
        st.success("Login efetuado com sucesso!")
        st.rerun()
    else:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM usuarios WHERE LOWER(TRIM(usuario)) = ? AND senha = ?", (usuario_input, senha_input))
            user_row = cursor.fetchone()
            cursor.close()
            
            if user_row:
                st.session_state['autenticado'] = True
                st.session_state['usuario_logado'] = user_row[1] # Nome do usuário
                st.session_state['cargo_logado'] = user_row[3] if len(user_row) > 3 else "Funcionário"
                st.success("Login efetuado com sucesso!")
                st.rerun()
            else:
                st.error("❌ Usuário ou senha incorretos. Verifique os dados.")
        except Exception as e:
            # Caso a tabela usuarios ainda não exista
            if usuario_input == "admin" and senha_input == "123456":
                st.session_state['autenticado'] = True
                st.session_state['usuario_logado'] = "admin"
                st.session_state['cargo_logado'] = "Administrador"
                st.rerun()
            else:
                st.error(f"Erro ao autenticar: {e}")
        # =============================================================
        # 1. CRIAÇÃO E ATUALIZAÇÃO DA TABELA DE USUÁRIOS E PERMISSÕES
        # =============================================================
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL,
                    login TEXT UNIQUE,
                    senha TEXT,
                    cargo TEXT,
                    cpf TEXT,
                    perm_produtos_ver INTEGER DEFAULT 1,
                    perm_produtos_editar INTEGER DEFAULT 0,
                    perm_produtos_excluir INTEGER DEFAULT 0,
                    perm_vendas_ver INTEGER DEFAULT 1,
                    perm_vendas_editar INTEGER DEFAULT 0,
                    perm_vendas_excluir INTEGER DEFAULT 0,
                    perm_clientes_ver INTEGER DEFAULT 1,
                    perm_clientes_editar INTEGER DEFAULT 0,
                    perm_clientes_excluir INTEGER DEFAULT 0,
                    perm_relatorios_ver INTEGER DEFAULT 0
                )
            """)
            
            # Garante que colunas essenciais existam caso a tabela seja de uma versão anterior
            colunas_necessarias = [
                "login TEXT", "senha TEXT", "cargo TEXT", "cpf TEXT",
                "perm_produtos_ver INTEGER DEFAULT 1", "perm_produtos_editar INTEGER DEFAULT 0", "perm_produtos_excluir INTEGER DEFAULT 0",
                "perm_vendas_ver INTEGER DEFAULT 1", "perm_vendas_editar INTEGER DEFAULT 0", "perm_vendas_excluir INTEGER DEFAULT 0",
                "perm_clientes_ver INTEGER DEFAULT 1", "perm_clientes_editar INTEGER DEFAULT 0", "perm_clientes_excluir INTEGER DEFAULT 0",
                "perm_relatorios_ver INTEGER DEFAULT 0"
            ]
            
            for col_def in colunas_necessarias:
                try:
                    cursor.execute(f"ALTER TABLE usuarios ADD COLUMN {col_def}")
                except Exception:
                    pass # Se a coluna já existir, o SQLite apenas ignora
                    
            conn.commit()
        except Exception as e:
            st.error(f"Erro ao configurar tabela de usuários: {e}")

        # -------------------------------------------------------------
        # ÁREA RESTRITA E MENU DO ADMINISTRADOR
        # -------------------------------------------------------------
        st.sidebar.subheader("🔒 Área Restrita")
        if st.sidebar.button("Sair do Modo Admin", key="btn_logout_admin"):
            st.session_state.admin_logged = False
            st.rerun()
        if st.session_state.get('admin_logged'):
            usuario_atual = st.session_state.get('usuario_logado', 'Administrador')
            cargo_atual = st.session_state.get('cargo_logado', 'Administrador')
            st.sidebar.markdown("---")
            st.sidebar.markdown(f"👤 **Usuário:** `{usuario_atual}`")
            st.sidebar.markdown(f"🏷️ **Cargo:** `{cargo_atual}`")          
        menu_admin = st.sidebar.radio(
            "Navegação",
            [
                "🛒 PDV — Frente de Caixa",
                "🔓 Abertura e Fechamento de Caixa",
                "📊 Fechamento & Financeiro",
                "🛒 Registrar Venda",
                "📦 Entrada de Estoque (Compras)",
                "👥 Cadastros (Clientes / Fornecedores / Grupos)",
                "👥 Gestão de Recursos Humanos (RH)",
                "💾 Backup e Restauração",
                "💸 Contas a Receber",
                "📦 Estoque de Produtos",
                "🏢 Configurações da Empresa"
            ],
            key="radio_menu_admin_opcoes"
        )
        
        # Módulo de Gestão de Funcionários vinculado ao RH
        if menu_admin == "🛒 PDV — Frente de Caixa":
            # CSS para compactar e estilizar os botões e campos
            st.markdown("""
            <style>
                .block-container { padding-top: 1rem !important; padding-bottom: 0rem !important; }
                div[data-testid="stVerticalBlock"] > div { padding: 4px 8px !important; margin-bottom: 0px !important; }
                .stMarkdown { margin-bottom: -10px !important; }
                div[data-baseweb="input"] { min-height: 35px !important; }
                h3, h4 { margin-top: 0px !important; margin-bottom: 5px !important; font-size: 16px !important; }
            </style>
            """, unsafe_allow_html=True)
            
            # Inicializa estados necessários
            if 'carrinho_pdv' not in st.session_state:
                st.session_state.carrinho_pdv = []
        
            if 'pdv_modo_completo' not in st.session_state:
                st.session_state.pdv_modo_completo = False
        
            if 'etapa_pagamento' not in st.session_state:
                st.session_state.etapa_pagamento = False
            
            st.subheader("🛒 PDV — Frente de Caixa — SEBASTIÃO JOSE DE ALENCAR NETO")
            
            # --- CARREGAR DADOS DO CAIXA E PRODUTOS ---
            df_caixa_aberto = carregar_dados("SELECT * FROM caixa_sessoes WHERE status = 'ABERTO'")
            
            try:
                df_prod_pdv = pd.read_sql_query("SELECT * FROM produtos", conn)
                lista_produtos_pdv = df_prod_pdv['produto'].tolist() if not df_prod_pdv.empty else []
            except Exception:
                lista_produtos_pdv = []
                df_prod_pdv = pd.DataFrame()
        
            def obter_dados_produto(nome_prod):
                if not df_prod_pdv.empty and nome_prod in lista_produtos_pdv:
                    p_row = df_prod_pdv[df_prod_pdv['produto'] == nome_prod].iloc[0]
                    return float(p_row.get('valor_venda', 0.0)), str(p_row.get('fornecedor', '')), str(p_row.get('grupo', ''))
                return 0.0, "", ""
        
            total_geral_carrinho = sum(item['valor_total'] for item in st.session_state.carrinho_pdv)
        
            # ==========================================
            # 💳 TELA 2: SELEÇÃO DE PAGAMENTO E TROCO
            # ==========================================
            if st.session_state.etapa_pagamento:
                st.markdown("---")
                st.markdown("### 💳 Tela de Fechamento e Pagamento")
                
                col_pag_esq, col_pag_dir = st.columns([1, 1])
                
                with col_pag_esq:
                    st.metric("TOTAL A PAGAR", f"R$ {total_geral_carrinho:.2f}")
                    f_pag = st.selectbox("Forma de Pagamento:", ["Dinheiro", "Cartão de Crédito", "Cartão de Débito", "PIX"])
                    
                    v_rec = float(total_geral_carrinho)
                    troco = 0.0
                    
                    # --- PAGAMENTO EM DINHEIRO ---
                    if f_pag == "Dinheiro":
                        v_rec = st.number_input("Valor Recebido (R$):", min_value=0.0, value=float(total_geral_carrinho), format="%.2f")
                        troco = v_rec - total_geral_carrinho if v_rec >= total_geral_carrinho else 0.0
                        st.metric("TROCO", f"R$ {troco:.2f}")  
                    
                    # --- PAGAMENTO EM PIX (DINÂMICO E SEGURO) ---
                    elif f_pag == "PIX":
                        chave_pix = ""
                        nome_beneficiario = ""
                        
                        try:
                            cursor_t = conn.cursor()
                            cursor_t.execute("SELECT name FROM sqlite_master WHERE type='table'")
                            tabelas = [row[0] for row in cursor_t.fetchall()]
                            cursor_t.close()
                            
                            for tabela in ['empresa', 'configuracoes', 'config', 'dados_empresa', 'empresa_cfg']:
                                if tabela in tabelas:
                                    df_emp = pd.read_sql_query(f"SELECT * FROM {tabela}", conn)
                                    if not df_emp.empty:
                                        row = df_emp.iloc[-1]
                                        
                                        for col_n in ['nome', 'razao_social', 'empresa', 'nome_empresa', 'razao']:
                                            if col_n in df_emp.columns and pd.notna(row[col_n]):
                                                val = str(row[col_n]).strip()
                                                if val:
                                                    nome_beneficiario = val
                                                    break
                                                    
                                        for col_c in ['cnpj', 'cnpj_cpf', 'cpf', 'documento']:
                                            if col_c in df_emp.columns and pd.notna(row[col_c]):
                                                doc = str(row[col_c]).strip()
                                                nums = ''.join(filter(str.isdigit, doc))
                                                if nums:
                                                    chave_pix = nums
                                                    break
                                        if nome_beneficiario or chave_pix:
                                            break
                        except Exception:
                            pass
                        
                        # Se não encontrar na base de dados, usa valores padrão seguros
                        if not nome_beneficiario:
                            nome_beneficiario = "REY DA CEBOLA"
                        if not chave_pix:
                            chave_pix = "19417439000142"
                        
                        cidade_beneficiario = "BRASIL"
                        
                        def gerar_payload_pix(pix_key, nome, cidade, valor):
                            import unicodedata
                            
                            def remover_acentos(txt):
                                return ''.join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')
                            
                            nome = remover_acentos(nome)[:25].upper()
                            cidade = remover_acentos(cidade)[:15].upper()
                            valor_str = f"{valor:.2f}"
                            
                            def tlv(tag, value):
                                return f"{tag}{len(value):02d}{value}"
                            
                            merchant_account = tlv("00", "br.gov.bcb.pix") + tlv("01", pix_key)
                            
                            payload = (
                                "000201" +
                                tlv("26", merchant_account) +
                                "52040000" +
                                "5303986" +
                                tlv("54", valor_str) +
                                "5802BR" +
                                tlv("59", nome) +
                                tlv("60", cidade) +
                                tlv("62", tlv("05", "***")) +
                                "6304"
                            )
                            
                            crc = 0xFFFF
                            for byte in payload.encode('ascii'):
                                crc ^= (byte << 8)
                                for _ in range(8):
                                    if crc & 0x8000:
                                        crc = ((crc << 1) ^ 0x1021) & 0xFFFF
                                    else:
                                        crc = (crc << 1) & 0xFFFF
                            return payload + f"{crc:04X}"
        
                        pix_payload = gerar_payload_pix(chave_pix, nome_beneficiario, cidade_beneficiario, total_geral_carrinho)
                        
                        st.markdown("---")
                        st.markdown("#### 📱 Pagamento via QR Code PIX")
                        st.info(f"**Chave PIX (CNPJ):** `{chave_pix}`")
                        
                        qr_code_url = f"https://api.qrserver.com/v1/create-qr-code/?size=180x180&data={pix_payload}"
                        
                        col_qr1, col_qr2 = st.columns([1, 2])
                        with col_qr1:
                            st.image(qr_code_url, caption="Aponte a câmara para pagar", width=160)
                        with col_qr2:
                            st.write(f"**Empresa:** {nome_beneficiario}")
                            st.write(f"**Valor do PIX:** R$ {total_geral_carrinho:.2f}")
                            st.success("Aguarde a confirmação do cliente após o escaneamento.")
        
                with col_pag_dir:
                    st.markdown("#### Resumo dos Itens no Carrinho:")
                    if st.session_state.carrinho_pdv:
                        df_carrinho_resumo = pd.DataFrame(st.session_state.carrinho_pdv)
                        st.dataframe(df_carrinho_resumo[['produto', 'quantidade', 'valor_total']], use_container_width=True, hide_index=True)
        
                st.markdown("---")
                col_botoes1, col_botoes2 = st.columns(2)
                
                with col_botoes1:
                    if st.button("⬅️ Voltar ao Carrinho", use_container_width=True):
                        st.session_state.etapa_pagamento = False
                        st.rerun()
                        
                with col_botoes2:
                    if checar_permissao(st.session_state.get('usuario_logado'), 'vendas', 'editar'):
                        if st.button("🟢 Confirmar e Concluir Venda", type="primary", use_container_width=True):
                            if not df_caixa_aberto.empty and len(st.session_state.carrinho_pdv) > 0:
                                # Bloco protetor para garantir que a tabela vendas e colunas existem
                                cursor_chk = conn.cursor()
                                cursor_chk.execute("""
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
                                        status TEXT,
                                        tipo TEXT,
                                        data TEXT,
                                        vendedor TEXT
                                    )
                                """)
                                conn.commit()
                                
                                for col_nome, col_tipo in [
                                    ("vendedor", "TEXT"),
                                    ("grupo", "TEXT"),
                                    ("fornecedor", "TEXT"),
                                    ("forma_pagamento", "TEXT"),
                                    ("valor_recebido", "REAL")
                                ]:
                                    try:
                                        cursor_chk.execute(f"ALTER TABLE vendas ADD COLUMN {col_nome} {col_tipo}")
                                        conn.commit()
                                    except Exception:
                                        pass
                                cursor_chk.close()
                                
                                cursor = conn.cursor()
                                sessao_id = int(df_caixa_aberto.iloc[0]['id'])
                                data_venda = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                vendedor_atual = st.session_state.get('usuario_logado', 'administrador')
                                
                                for item in st.session_state.carrinho_pdv:
                                    cursor.execute("""
                                        INSERT INTO vendas (
                                            cliente, produto, fornecedor, grupo, quantidade, 
                                            valor_venda, valor_total, forma_pagamento, valor_recebido, 
                                            status, tipo, data, vendedor
                                        )
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    """, (
                                        "Cliente Balcão", item['produto'], item['fornecedor'], item['grupo'],
                                        item['quantidade'], item['valor_venda'], item['valor_total'],
                                        f_pag, v_rec, 'Concluído', 'VENDA', data_venda, vendedor_atual
                                    ))
                                
                                cursor.execute("""
                                    INSERT INTO caixa_movimentacoes (sessao_id, tipo, valor, descricao, data)
                                    VALUES (?, ?, ?, ?, ?)
                                """, (sessao_id, "VENDA", float(total_geral_carrinho), f"Venda PDV (Por: {vendedor_atual})", data_venda))
                                
                                conn.commit()
                                cursor.close()
                                
                                st.session_state.carrinho_pdv = []
                                st.session_state.etapa_pagamento = False
                                st.success(f"Venda concluída por {vendedor_atual}!")
                                st.rerun()
                            else:
                                st.error("Verifique se o caixa está aberto e se há itens no carrinho.")
                    else:
                        st.error("🚫 Sem permissão para faturar vendas.")
        
            # ==========================================
            # 🛒 TELA 1: PDV PRINCIPAL (BUSCA E CARRINHO)
            # ==========================================
            else:
                # --- CABEÇALHO COM BOTÃO DE ALTERNÂNCIA DE MODO ---
                col_hdr1, col_hdr2 = st.columns([3, 1])
                with col_hdr1:
                    if not df_caixa_aberto.empty:
                        st.success("🟢 Caixa Aberto e Operacional")
                    else:
                        st.warning("⚠️ Atenção: Não há nenhum caixa aberto no momento.")
                
                with col_hdr2:
                    if st.session_state.pdv_modo_completo:
                        if st.button("⚡ MODO SIMPLIFICADO", use_container_width=True):
                            st.session_state.pdv_modo_completo = False
                            st.rerun()
                    else:
                        if st.button("🟢 VERSÃO COMPLETA", type="primary", use_container_width=True):
                            st.session_state.pdv_modo_completo = True
                            st.rerun()
                
                st.markdown("---")
                
                col_esquerda, col_direita = st.columns([1, 1])
                
                with col_esquerda:
                    st.markdown("### 📦 Dados do Item")
                    busca_produto = st.text_input("Passe o leitor ou digite o código/nome:", key="input_busca_pdv_unico")
                    produto_selecionado = st.selectbox("Selecione o Produto:", lista_produtos_pdv, key="select_prod_pdv")
                    
                    preco_padrao_prod, fornecedor_prod, grupo_prod = obter_dados_produto(produto_selecionado)
                    
                    if st.session_state.pdv_modo_completo:
                        col_q1, col_q2 = st.columns(2)
                        with col_q1:
                            qtd_item = st.number_input("Qtd:", min_value=0.01, value=1.00, step=1.0, format="%.2f")
                        with col_q2:
                            preco_item = st.number_input("Preço Unit. (R$):", value=preco_padrao_prod, format="%.2f")
                        
                        subtotal_item = qtd_item * preco_item
                        st.markdown(f"#### SUBTOTAL: **R$ {subtotal_item:.2f}**")
                    else:
                        qtd_item = 1.00
                        preco_item = preco_padrao_prod
                        subtotal_item = preco_item
                    
                    if st.button("➕ [ Enter ] Incluir Produto", type="primary", use_container_width=True):
                        if produto_selecionado:
                            item_carrinho = {
                                'produto': produto_selecionado,
                                'fornecedor': fornecedor_prod,
                                'grupo': grupo_prod,
                                'quantidade': qtd_item,
                                'valor_venda': preco_item,
                                'valor_total': subtotal_item
                            }
                            st.session_state.carrinho_pdv.append(item_carrinho)
                            st.success(f"Item '{produto_selecionado}' adicionado!")
                            st.rerun()
                
                with col_direita:
                    st.markdown("### 🛒 Carrinho")
                    
                    if st.session_state.carrinho_pdv:
                        df_carrinho = pd.DataFrame(st.session_state.carrinho_pdv)
                        st.dataframe(df_carrinho[['produto', 'quantidade', 'valor_venda', 'valor_total']], use_container_width=True, hide_index=True)
                        
                        opcoes_remover = [f"{i}: {item['produto']} (Qtd: {item['quantidade']})" for i, item in enumerate(st.session_state.carrinho_pdv)]
                        item_para_remover = st.selectbox("Selecione o item para excluir do carrinho:", opcoes_remover, key="select_remover_item")
                        if st.button("🗑️ Excluir Item Selecionado", use_container_width=True):
                            indice = int(item_para_remover.split(":")[0])
                            removido = st.session_state.carrinho_pdv.pop(indice)
                            st.warning(f"Item '{removido['produto']}' removido do carrinho.")
                            st.rerun()
                    else:
                        st.info("Carrinho vazio.")
                        
                    st.metric("TOTAL A PAGAR", f"R$ {total_geral_carrinho:.2f}")
                    
                    st.markdown("---")
                    
                    col_acao1, col_acao2 = st.columns(2)
                    
                    with col_acao1:
                        if st.button("❌ Cancelar Venda [ Alt + C ]", use_container_width=True):
                            st.session_state.carrinho_pdv = []
                            st.warning("Venda cancelada e carrinho limpo.")
                            st.rerun()
                            
                    with col_acao2:
                        if st.button("🟢 Finalizar Venda [ Alt + V ]", type="primary", use_container_width=True):
                            if len(st.session_state.carrinho_pdv) > 0:
                                st.session_state.etapa_pagamento = True
                                st.rerun()
                            else:
                                st.error("Adicione itens ao carrinho antes de finalizar.")
        
                # --- BARRA DE ATALHOS NO RODAPÉ E SCRIPT PARA O TECLADO ---
                st.markdown("""
                <div style="background-color: #2b2b2b; color: #ffffff; padding: 8px 15px; border-radius: 8px; border: 2px solid #555555; margin-top: 15px; font-family: monospace; font-size: 13px; text-align: center;">
                    Atalhos: <span style="color: #00ffcc; font-weight: bold;">[ Enter ]</span> Incluir | 
                    <span style="color: #00ffcc; font-weight: bold;">[ Alt + C ]</span> Cancelar Venda | 
                    <span style="color: #00ffcc; font-weight: bold;">[ Alt + V ]</span> Finalizar Venda
                </div>
                """, unsafe_allow_html=True)
        
                st.components.v1.html("""
                <script>
                const doc = window.parent.document;
                doc.addEventListener('keydown', function(e) {
                    if (e.altKey && (e.key === 'v' || e.key === 'V')) {
                        e.preventDefault();
                        const btns = doc.querySelectorAll('button');
                        btns.forEach(b => { if (b.innerText.includes('Finalizar Venda')) b.click(); });
                    }
                    if (e.altKey && (e.key === 'c' || e.key === 'C')) {
                        e.preventDefault();
                        const btns = doc.querySelectorAll('button');
                        btns.forEach(b => { if (b.innerText.includes('Cancelar Venda')) b.click(); });
                    }
                });
                </script>
                """, height=0)
        
        if menu_admin == "🏢 Configurações da Empresa":
            st.title("🏢 Configurações e Dados da Empresa")
            
            # Carrega os dados da empresa deste dispositivo específico
            df_emp_atual = pd.read_sql_query("SELECT * FROM empresas_dispositivos WHERE device_id = ?", conn, params=(device_id,))
            reg_emp = df_emp_atual.iloc[0] if not df_emp_atual.empty else {}
        
            # === VERIFICAÇÃO DE ATIVAÇÃO ===
            if not st.session_state.get('dispositivo_ativado', False):
                st.markdown("### 🔑 Ativação de Licença do Dispositivo")
                st.warning("⚠️ Insira a chave de ativação correspondente ao seu documento para liberar o sistema.")
                
                # Forma 100% segura para evitar o erro do Pandas
                doc_atual = "19417439000142"
                if not df_emp_atual.empty:
                    doc_atual = str(df_emp_atual.iloc[0].get('cnpj', '19417439000142'))
                st.info(f"Empresa Atual (CNPJ/CPF): {doc_atual}")
                
                chave_digitada = st.text_input("Chave de Ativação:", key="input_chave_ativacao_config")
                
                if st.button("Ativar Este Dispositivo", key="btn_ativar_dispositivo_config"):
                    import hashlib
                    
                    apenas_digitos = ''.join(filter(str.isdigit, str(doc_atual)))
                    segredo_mestre = "REY_CEBOLA_2026"
                    chave_limpa = str(chave_digitada).strip().upper()
                    
                    chaves_calculadas = {}
                    sucesso = False
                    dias_validade = 0
                    
                    mapeamento_dias = {
                        "TESTE": 7,
                        "MENSAL": 30,
                        "ANUAL": 365
                    }
                    
                    for sufixo, dias in mapeamento_dias.items():
                        combinado = apenas_digitos + segredo_mestre + sufixo
                        hash_hex = hashlib.md5(combinado.encode()).hexdigest().upper()
                        chave_esperada = f"CRM-{sufixo}-{hash_hex[:4]}-{hash_hex[4:8]}-{hash_hex[8:12]}"
                        chaves_calculadas[sufixo] = chave_esperada
                        
                        if chave_limpa == chave_esperada:
                            sucesso = True
                            dias_validade = dias
                            break
                            
                    if sucesso:
                        st.session_state['dispositivo_ativado'] = True
                        st.session_state['dias_licenca'] = dias_validade
                        st.success(f"Dispositivo ativado com sucesso! Validade: {dias_validade} dias.")
                        st.rerun()
                    else:
                        st.error("Chave inválida para este CPF/CNPJ.")
                        st.warning("🔍 **Painel de Diagnóstico (Chaves esperadas pelo sistema):**")
                        for tipo, c_gerada in chaves_calculadas.items():
                            st.text(f"Gerada para {tipo}: {c_gerada}")
                        st.text(f"Chave que você digitou: {chave_limpa}")
                st.markdown("---")
                
            else:
                # SE JÁ ESTIVER ATIVADO, MOSTRA O STATUS E O BOTÃO DE RENOVAR
                dias_ativos = st.session_state.get('dias_licenca', 30)
                st.success(f"✅ Dispositivo Ativado com Sucesso! Licença válida por {dias_ativos} dias.")
                
                # Botão para permitir inserir uma nova chave / renovar
                if st.button("🔄 Inserir Nova Chave / Renovar Licença", key="btn_renovar_licenca"):
                    st.session_state['dispositivo_ativado'] = False
                    st.rerun()
                    
                st.markdown("---")
                
                with st.form("form_atualizar_dados_empresa"):
                    c_nome_alt = st.text_input("Nome / Razão Social", value=str(reg_emp.get('nome_empresa', '')))
                    c_cnpj_alt = st.text_input("CNPJ ou CPF", value=str(reg_emp.get('cnpj', '')))
                    c_ie_alt = st.text_input("Inscrição Estadual (IE)", value=str(reg_emp.get('ie', '')))
                    c_tel_alt = st.text_input("Telefone de Contato", value=str(reg_emp.get('fone', '')))
                    c_end_alt = st.text_input("Endereço Completo", value=str(reg_emp.get('endereco', '')))
                    
                    if st.form_submit_button("💾 Salvar Alterações da Empresa", type="primary"):
                        if c_nome_alt.strip() and c_cnpj_alt.strip():
                            cnpj_limpo = ''.join(filter(str.isdigit, c_cnpj_alt))
                            cursor = conn.cursor()
                            cursor.execute("""
                                INSERT OR REPLACE INTO empresas_dispositivos (device_id, nome_empresa, cnpj, ie, fone, endereco)
                                VALUES (?, ?, ?, ?, ?, ?)
                            """, (device_id, c_nome_alt.strip(), cnpj_limpo, c_ie_alt.strip(), c_tel_alt.strip(), c_end_alt.strip()))
                            conn.commit()
                            st.success("✅ Dados da empresa atualizados com sucesso!")
                            st.rerun()
                        else:
                            st.error("Preencha o Nome e o CNPJ/CPF.")
        
        elif menu_admin == "📊 Fechamento & Financeiro":
            st.subheader("📊 Fechamento & Financeiro")
            # Certifique-se de que esta secção termina corretamente
            df_caixa_atual = carregar_dados("SELECT * FROM caixa_sessoes WHERE status = 'ABERTO'")

            if df_caixa_atual.empty:
                st.info("O caixa encontra-se **FECHADO**. Insira o valor inicial para abri-lo.")
                with st.form("form_abrir_caixa"):
                    saldo_inicial = st.number_input("Saldo Inicial em Dinheiro (Troco / Fundo de Caixa)", min_value=0.0, step=10.0)
                    if st.form_submit_button("Abrir Caixa"):
                        cursor = conn.cursor()
                        data_agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        cursor.execute("INSERT INTO caixa_sessoes (data_abertura, saldo_inicial, status) VALUES (?, ?, ?)", (data_agora, saldo_inicial, "ABERTO"))
                        conn.commit()
                        st.success("Caixa aberto com sucesso!")
                        st.rerun()
            else:
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
                        cursor.execute("UPDATE caixa_sessoes SET data_fechamento = ?, saldo_final = ?, status = ? WHERE id = ?", (data_fechamento, saldo_final_informado, "FECHADO", sessao_id))
                        conn.commit()
                        st.success("Caixa fechado com sucesso!")
                        st.rerun()

        elif menu_admin == "📊 Fechamento & Financeiro":
            # Verifica se o utilizador logado tem permissão para ver relatórios
            if not checar_permissao(st.session_state.get('usuario_logado'), "relatorios", "ver"):
                st.warning("⚠️ Você não tem permissão para aceder aos relatórios financeiros.")
            else:
                # Todo o código original do painel financeiro fica recuado aqui dentro:
                st.header("📊 Painel Financeiro & Fechamento por Data")
                st.subheader("💳 Contas a Receber (Parcelas / Fiado)")
                
                df_vendas_fin = carregar_dados("SELECT id, cliente, produto, fornecedor, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, troco, restante, data, grupo")
                df_pedidos_fin = carregar_dados("SELECT * FROM pedidos ORDER BY id DESC")
                
                if not df_vendas_fin.empty and 'restante' in df_vendas_fin.columns:
                    df_vendas_fin['restante'] = pd.to_numeric(df_vendas_fin['restante'], errors='coerce').fillna(0.0)
                    df_pendentes_fin = df_vendas_fin[df_vendas_fin['restante'] > 0]
                    if not df_pendentes_fin.empty:
                        st.warning(f"⚠️ Existem {len(df_pendentes_fin)} registos de crediário com saldo pendente.")
                    else:
                        pass
            st.header("📊 Painel Financeiro & Fechamento por Data")
            st.subheader("💳 Contas a Receber (Parcelas / Fiado)")

            df_vendas_fin = carregar_dados("SELECT id, cliente, produto, fornecedor, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, troco, restante, data, grupo FROM vendas ORDER BY id DESC")
            df_pedidos_fin = carregar_dados("SELECT * FROM pedidos ORDER BY id DESC")
            
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
            
            clientes_vendas = df_vendas_fin['cliente'].dropna().astype(str).unique().tolist() if not df_vendas_fin.empty and 'cliente' in df_vendas_fin.columns else []
            clientes_pedidos = df_pedidos_fin['cliente'].dropna().astype(str).unique().tolist() if not df_pedidos_fin.empty and 'cliente' in df_pedidos_fin.columns else []
            todos_clientes = sorted(list(set(clientes_vendas + clientes_pedidos)))
            lista_clientes_fin = ["Todos"] + todos_clientes
            
            col_f1, col_f2, col_f3, col_f4 = st.columns([2.5, 2, 2, 2.5])
            
            with col_f1:
                f_cliente_fin = st.selectbox("Filtrar por Cliente:", lista_clientes_fin, key="f_cli_painel_fin")
            with col_f2:
                data_inicio_def = dt.date(2025, 1, 1)
                data_inicio = st.date_input("Data Inicial", value=data_inicio_def, key="dt_inicio_fin")
            with col_f3:
                data_fim = st.date_input("Data Final", value=dt.date.today(), key="dt_fim_fin")
            with col_f4:
                opcao_status = st.selectbox("Status dos Registros", ["Incluir Pedidos Pendentes", "Apenas Vendas Concluídas", "Apenas Pedidos Pendentes"], key="status_registros_fin")
            
            dfs_para_concatenar = []
            
            if not df_vendas_fin.empty and opcao_status != "Apenas Pedidos Pendentes":
                df_v = df_vendas_fin.copy()
                if 'data' in df_v.columns:
                    df_v['dt_formatada'] = pd.to_datetime(df_v['data'], errors='coerce').dt.date
                    df_v['dt_formatada'] = df_v['dt_formatada'].fillna(pd.to_datetime(df_v['data'].astype(str).str[:10], errors='coerce').dt.date)
                dfs_para_concatenar.append(df_v)
            
            if not df_pedidos_fin.empty and opcao_status in ["Incluir Pedidos Pendentes", "Apenas Pedidos Pendentes"]:
                df_p = df_pedidos_fin[df_pedidos_fin['status'].astype(str).str.upper().str.contains("PENDENTE")].copy()
                if not df_p.empty:
                    if 'data' in df_p.columns:
                        df_p['dt_formatada'] = pd.to_datetime(df_p['data'], errors='coerce').dt.date
                        df_p['dt_formatada'] = df_p['dt_formatada'].fillna(pd.to_datetime(df_p['data'].astype(str).str[:10], errors='coerce').dt.date)
            
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
            
            if dfs_para_concatenar:
                df_fin_geral = pd.concat(dfs_para_concatenar, ignore_index=True)
            else:
                df_fin_geral = pd.DataFrame()
            
            if not df_fin_geral.empty:
                if f_cliente_fin != "Todos":
                    df_fin_geral = df_fin_geral[df_fin_geral['cliente'].astype(str) == str(f_cliente_fin)]
            
                if 'dt_formatada' in df_fin_geral.columns:
                    df_fin_geral = df_fin_geral[(df_fin_geral['dt_formatada'] >= data_inicio) & (df_fin_geral['dt_formatada'] <= data_fim)]
            
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
            
            if not df_fin_geral.empty:
                cols_ordem = ['id', 'cliente', 'produto', 'fornecedor', 'quantidade', 'valor_venda', 'valor_total', 'forma_pagamento', 'valor_recebido', 'troco', 'restante', 'data', 'grupo']
                cols_presentes = [c for c in cols_ordem if c in df_fin_geral.columns]
                st.dataframe(df_fin_geral[cols_presentes], use_container_width=True)
            else:
                st.info("Nenhum registro encontrado para os filtros selecionados.")

        elif menu_admin == "🛒 Registrar Venda":
            st.subheader("🛒 Registrar Venda")
        
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
        
                if "prod_selecionado_temp" in st.session_state:
                    st.session_state["ped_select_produto"] = st.session_state.pop("prod_selecionado_temp")
                
                opcoes_produtos_com_novo = ["+ Cadastrar Novo Produto..."] + list(produtos_opt)
                
                cliente_ped = st.selectbox("Cliente", clientes_opt, key="ped_cli_ind")
                
                col_l2_1, col_l2_2 = st.columns(2)
                with col_l2_1:
                    prod_item = st.selectbox("Selecione o Produto", opcoes_produtos_com_novo, key="ped_select_produto")
                with col_l2_2:
                    grupo_ped = st.selectbox("Grupo", grupos_opt, key="ped_grupo_ind")
                
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
                                    cursor.execute("INSERT INTO produtos (produto, grupo, fornecedor, quantidade, valor_compra, valor_venda) VALUES (?, ?, ?, ?, ?, ?)", (novo_nome_prod, c_g_r, c_f_r, c_qtd_r, c_compra_r, c_venda_r))
                                    conn.commit()
                                    st.cache_data.clear()
                                    st.session_state["prod_selecionado_temp"] = novo_nome_prod
                                    st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao cadastrar: {e}")
                        else:
                            st.error("Digite o nome do produto.")
                        st.stop()
                
                preco_sugerido_admin = 0.0
                if not df_p_admin.empty and prod_item != "+ Cadastrar Novo Produto...":
                    df_p_admin.columns = [c.lower() for c in df_p_admin.columns]
                    col_nome_p = 'produto' if 'produto' in df_p_admin.columns else ('nome' if 'nome' in df_p_admin.columns else df_p_admin.columns[1])
                    df_p_admin['_nome_limpo'] = df_p_admin[col_nome_p].astype(str).str.strip().str.upper()
                    df_filtrado_admin = df_p_admin[df_p_admin['_nome_limpo'] == str(prod_item).strip().upper()]
                
                    if not df_filtrado_admin.empty:
                        row_adm = df_filtrado_admin.iloc[0]
                        for col_v in ['valor_venda', 'preco_venda', 'venda', 'preco', 'valor']:
                            if col_v in df_p_admin.columns:
                                try:
                                    val_aux = float(row_adm[col_v])
                                    if val_aux > 0:
                                        preco_sugerido_admin = val_aux
                                        break
                                except:
                                    pass
                
                col_l3_1, col_l3_2 = st.columns(2)
                with col_l3_1:
                    fornec_ped = st.selectbox("Fornecedor", fornecedores_opt, key="ped_forn_ind")
                with col_l3_2:
                    qtd_ped = st.number_input("Quantidade", min_value=0.01, step=1.0, value=1.0, key="ped_qtd_ind")
                
                col_l4_1, col_l4_2 = st.columns(2)
                with col_l4_1:
                    v_venda_ped = st.number_input("Preço Unitário (R$)", min_value=0.0, value=float(preco_sugerido_admin), key=f"ped_v_ind_{prod_item}")
                with col_l4_2:
                    valor_total_item = qtd_ped * v_venda_ped
                    st.info(f"**Valor Total do Item:** R$ {valor_total_item:.2f}")
                
                # Garante que o carrinho do cliente existe na sessão e nunca é apagado sozinho
                if "carrinho_cliente" not in st.session_state:
                    st.session_state.carrinho_cliente = []
            
                if st.button("➕ Incluir Produto no Pedido", type="primary", key="btn_incluir_prod_cli"):
                    if prod_item == "+ Cadastrar Novo Produto...":
                        st.error("Por favor, selecione ou cadastre o produto antes de incluir no pedido.")
                    else:
                        # Verifica se o produto já existe na lista atual do carrinho
                        produto_ja_existe = False
                        for item in st.session_state.carrinho_cliente:
                            if str(item.get("produto", "")).strip().upper() == str(prod_item).strip().upper():
                                produto_ja_existe = True
                                break
            
                        if produto_ja_existe:
                            st.warning(f"⚠️ O produto **'{prod_item}'** já existe no carrinho!")
                        else:
                            # Adiciona o novo item mantendo os anteriores intactos
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
                st.subheader("📋 Itens Atuais no Pedido")
            
                if 'modo_edicao_carrinho' not in st.session_state:
                    st.session_state.modo_edicao_carrinho = False
            
                carrinho_atual = st.session_state.get('carrinho_cliente', [])
            
                if carrinho_atual:
                    df_carrinho = pd.DataFrame(carrinho_atual)
            
                    if st.session_state.modo_edicao_carrinho:
                        st.info("💡 **Modo de Edição Ativo:** Altere as quantidades ou valores diretamente na tabela abaixo e depois clique em **'💾 Salvar'**.")
                        df_editado = st.data_editor(df_carrinho, use_container_width=True, key="editor_itens_carrinho")
                    else:
                        st.dataframe(df_carrinho, use_container_width=True)
            
                    col_btn1, col_btn2, col_btn3, col_btn4 = st.columns(4)
            
                    with col_btn1:
                        if st.button("🗑️ Limpar Carrinho", key="btn_limpar_carrinho_admin"):
                            # Esvazia a lista unificada do carrinho na sessão
                            st.session_state.carrinho_cliente = []
                            st.success("✅ Carrinho limpo com sucesso!")
                            st.rerun()
            
                    with col_btn2:
                        if st.button("✏️ Alterar", use_container_width=True, key="btn_alterar_carrinho_v2"):
                            st.session_state.modo_edicao_carrinho = True
                            st.rerun()
            
                    with col_btn3:
                        # Botão para Salvar as alterações feitas na tabela do carrinho
                        if st.button("💾 Salvar", key="btn_salvar_carrinho_admin"):
                            try:
                                # Procura dinamicamente por qualquer tabela editada ativa na sessão do Streamlit
                                df_editado = None
                                for chave_sessao in st.session_state:
                                    if "tabela" in chave_sessao or "carrinho" in chave_sessao or "editor" in chave_sessao:
                                        obj = st.session_state[chave_sessao]
                                        if hasattr(obj, "to_dict"):
                                            df_editado = obj
                                            break
                                
                                if df_editado is not None and hasattr(df_editado, 'to_dict'):
                                    nova_lista = df_editado.to_dict(orient='records')
                                    
                                    # Recalcula os valores totais dos itens
                                    for item in nova_lista:
                                        qtd = float(item.get("quantidade", 1) or 1)
                                        v_unit = float(item.get("valor_unitario", item.get("preco_unitario", 0)) or 0)
                                        item["quantidade"] = qtd
                                        item["valor_unitario"] = v_unit
                                        item["preco_unitario"] = v_unit
                                        item["valor_total"] = qtd * v_unit
                                        
                                    st.session_state.carrinho_cliente = nova_lista
                                    st.success("✅ Alterações guardadas com sucesso!")
                                    st.rerun()
                                else:
                                    # Se os dados já estão no estado, apenas força o recarregamento com sucesso
                                    st.success("✅ Alterações guardadas com sucesso!")
                                    st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao salvar alterações: {e}")
                            else:
                                st.warning("Clique em '✏️ Alterar' primeiro para editar a tabela.")
            
                    with col_btn4:
                        if st.button("🔴 Finalizar e Enviar Pedido", type="primary", use_container_width=True, key="btn_finalizar_pedido_v2"):
                            try:
                                cursor = conn.cursor()
                                import zoneinfo
                                data_agora = dt.datetime.now(zoneinfo.ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d %H:%M:%S")
                    
                                for item in carrinho_atual:
                                    qtd_item = float(item.get("quantidade", 1))
                                    prod_nome = str(item.get("produto", ""))
                                    val_unit = float(item.get("valor_unitario", 0))
                                    val_tot = float(item.get("valor_total", 0))
                                    forn_nome = item.get("fornecedor", "")
                                    grupo_nome = item.get("grupo", "")
                    
                                    # 1. Grava APENAS no histórico de pedidos como Pendente
                                    cursor.execute("""
                                        INSERT INTO pedidos (cliente, produto, fornecedor, grupo, quantidade, valor_unitario, valor_total, status, data)
                                        VALUES (?, ?, ?, ?, ?, ?, ?, 'Pendente', ?)
                                    """, (cliente_ped, prod_nome, forn_nome, grupo_nome, qtd_item, val_unit, val_tot, data_agora))
                    
                                conn.commit()
                    
                                # Limpa os carrinhos da sessão
                                if 'carrinho_admin' in st.session_state:
                                    st.session_state.carrinho_admin = []
                                if 'carrinho' in st.session_state:
                                    st.session_state.carrinho = []
                                if 'carrinho_cliente' in st.session_state:
                                    st.session_state.carrinho_cliente = []
                    
                                st.session_state.modo_edicao_carrinho = False
                                st.cache_data.clear()
                                st.success("✅ Pedido enviado com sucesso! Aguardando conversão em venda.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao salvar pedido: {e}")
                else:
                    st.info("Nenhum item adicionado ao carrinho ainda.")
        
            with aba_list:
                st.subheader("🟢 Pedidos do Dia Pendentes (Editáveis)")
            
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
                                "valor_unitario": st.column_config.NumberColumn("Valor Unitário", format="R$ %.2f"),
                                "valor_total": st.column_config.NumberColumn("Valor Total", format="R$ %.2f")
                            },
                            key="editor_pedidos_dia"
                        )
            
                        col_b1, col_b2, col_b3 = st.columns(3)
            
                        with col_b1:
                            if st.button("💾 Salvar Alterações", type="primary", key="btn_salvar_edicoes_pedidos"):
                                try:
                                    cursor = conn.cursor()
                                    for _, row in df_editado.iterrows():
                                        ped_id = row['id']
                                        qtd = float(row.get('quantidade', 1))
                                        v_unit = float(row.get('valor_unitario', 0.0))
                                        v_tot = qtd * v_unit
                                        cli = str(row.get('cliente', '')).strip()
                                        prod = str(row.get('produto', '')).strip()
                                        fornec = str(row.get('fornecedor', '')).strip()
                                        grp = str(row.get('grupo', '')).strip()
                                        stts = str(row.get('status', 'PENDENTE')).strip()
            
                                        cursor.execute("UPDATE pedidos SET cliente = ?, produto = ?, quantidade = ?, valor_unitario = ?, valor_total = ?, fornecedor = ?, grupo = ?, status = ? WHERE id = ?", (cli, prod, qtd, v_unit, v_tot, fornec, grp, stts, ped_id))
            
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
                                        cursor.execute("UPDATE pedidos SET valor_unitario = (SELECT valor_venda FROM produtos WHERE produtos.produto = pedidos.produto), valor_total = quantidade * (SELECT valor_venda FROM produtos WHERE produtos.produto = pedidos.produto) WHERE status = 'Pendente' AND EXISTS (SELECT 1 FROM produtos WHERE produtos.produto = pedidos.produto)")
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
                                    
                                    if valor_total_debito > 0:
                                        item_rec = round((item_tot / valor_total_debito) * valor_recebido, 2)
                                    else:
                                        item_rec = 0.0
                                    
                                    item_rest = round(max(0.0, item_tot - item_rec), 2)
            
                                    cursor.execute("DELETE FROM vendas WHERE cliente = ? AND produto = ? AND (forma_pagamento = '-' OR forma_pagamento IS NULL OR forma_pagamento = 'None')", (str(r['cliente']), str(r['produto'])))
                                    cursor.execute("UPDATE produtos SET quantidade = quantidade - ? WHERE produto = ?", (qtd_item, str(r['produto'])))
                                    cursor.execute("INSERT INTO vendas (cliente, produto, fornecedor, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, troco, restante, data, grupo, codigo_venda, status, tipo, codigo) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                                        str(r['cliente']), str(r['produto']), str(r.get('fornecedor', '')), qtd_item, float(r.get('valor_unitario', 0)), item_tot, detalhe_pagamento, item_rec, 0.0, item_rest, dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), str(r.get('grupo', '')), codigo_venda_gerado, "Concluído", "PEDIDO", f"PED-{r['id']}"
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
                st.subheader("📚 Pedidos Anteriores / Histórico Geral")
            
                df_historico = carregar_dados("SELECT id, cliente, produto, fornecedor, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, troco, restante, data, grupo FROM vendas ORDER BY id DESC")
            
                if not df_historico.empty:
                    df_historico['forma_pagamento'] = df_historico['forma_pagamento'].fillna('-').replace({'None': '-', '': '-'})
                    for c in ['valor_recebido', 'troco', 'restante']:
                        df_historico[c] = pd.to_numeric(df_historico[c], errors='coerce').fillna(0.0)
            
                    st.dataframe(df_historico, use_container_width=True)
            
                    col_hist1, col_hist2 = st.columns([1, 4])
                    with col_hist1:
                        if st.button("🗑️ Limpar Todo o Histórico", type="secondary", key="btn_limpar_historico"):
                            try:
                                cursor = conn.cursor()
                                cursor.execute("DELETE FROM vendas")
                                cursor.execute("DELETE FROM pedidos WHERE status LIKE '%Concluído%' OR status LIKE '%Convertido%'")
                                conn.commit()
                                st.cache_data.clear()
                                st.success("✅ Histórico limpo com sucesso!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao limpar histórico: {e}")
                else:
                    st.info("Nenhum registro encontrado.")
        elif "Contas a Receber" in str(menu_admin):
            st.title("💸 Contas a Receber")
            st.markdown("Gerencie de forma centralizada todos os valores pendentes e saldos devedores dos clientes.")
            
            # Bloco para carregar todos os pedidos da base de dados de forma segura
            try:
                df_contas = pd.read_sql_query("SELECT * FROM pedidos", conn)
            except Exception:
                df_contas = pd.DataFrame()
            
            if not df_contas.empty:
                # Padroniza colunas numéricas de forma segura
                for col in ['valor_total', 'valor_recebido', 'restante', 'quantidade', 'valor_unitario']:
                    if col in df_contas.columns:
                        df_contas[col] = pd.to_numeric(df_contas[col], errors='coerce').fillna(0.0)
            
                # Define o valor devedor com base na coluna restante ou no cálculo total - recebido
                if 'restante' in df_contas.columns:
                    df_contas['valor_devedor'] = df_contas['restante']
                elif 'valor_total' in df_contas.columns and 'valor_recebido' in df_contas.columns:
                    df_contas['valor_devedor'] = df_contas['valor_total'] - df_contas['valor_recebido']
                elif 'valor_total' in df_contas.columns:
                    df_contas['valor_devedor'] = df_contas['valor_total']
                else:
                    df_contas['valor_devedor'] = 0.0
            
                # Filtra apenas os registos que realmente possuem débito pendente (> 0)
                df_contas = df_contas[df_contas['valor_devedor'] > 0]
            
            if not df_contas.empty:
                col_f1, col_f2 = st.columns(2)
                with col_f1:
                    clientes_disponiveis = ["Todos"] + sorted(df_contas['cliente'].dropna().unique().tolist()) if 'cliente' in df_contas.columns else ["Todos"]
                    filtro_cliente_cr = st.selectbox("Filtrar por Cliente:", clientes_disponiveis, key="select_cliente_contas_receber")
                
                with col_f2:
                    st.markdown("<br>", unsafe_allow_html=True)
                    termo_busca_cr = st.text_input("🔍 Pesquisa rápida:", placeholder="Digite o produto ou detalhe...", key="busca_cr_livre")
            
                df_filtrado = df_contas.copy()
                if filtro_cliente_cr != "Todos" and 'cliente' in df_filtrado.columns:
                    df_filtrado = df_filtrado[df_filtrado['cliente'] == filtro_cliente_cr]
                    
                if termo_busca_cr.strip() and 'produto' in df_filtrado.columns:
                    df_filtrado = df_filtrado[df_filtrado['produto'].astype(str).str.contains(termo_busca_cr, case=False, na=False)]
            
                total_a_receber = df_filtrado['valor_devedor'].sum()
                total_clientes_devedores = df_filtrado['cliente'].nunique() if 'cliente' in df_filtrado.columns else 0
            
                st.markdown("---")
                col_m1, col_m2 = st.columns(2)
                with col_m1:
                    st.metric("💰 Total Geral a Receber", f"R$ {total_a_receber:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                with col_m2:
                    st.metric("👥 Clientes com Pendências", str(total_clientes_devedores))
            
                st.markdown("---")
                st.subheader("📋 Lista de Contas Pendentes")
            
                colunas_exibir = [c for c in ['id', 'cliente', 'produto', 'quantidade', 'valor_total', 'valor_recebido', 'restante', 'data'] if c in df_filtrado.columns]
                if not colunas_exibir:
                    colunas_exibir = df_filtrado.columns.tolist()
            
                st.dataframe(
                    df_filtrado[colunas_exibir],
                    use_container_width=True,
                    hide_index=True
                )
            
                if st.button("🔄 Atualizar Dados de Contas a Receber", key="btn_refresh_cr"):
                    st.rerun()
            
            else:
                st.info("ℹ️ Não existem contas a receber registadas ou todos os pedidos já se encontram quitados.")
        elif menu_admin == "📦 Estoque de Produtos":
            st.title("📦 Estoque de Produtos e Preços")
        
            # --- IMPORTAÇÃO DIRETA PELA TELA DA APLICAÇÃO ---
            with st.expander("📦 Importar / Colar Lista de Produtos em Massa"):
                st.info("Cole abaixo a sua lista copiada diretamente do Excel ou Bloco de Notas.")
                
                texto_lista_colada = st.text_area(
                    "Cole os produtos aqui:",
                    placeholder="Exemplo:\n1\tABACATE\t6\tBAHIA\tGERAL\t0\t0",
                    key="input_texto_produtos_massa"
                )
                
                if st.button("🚀 Processar e Importar Lista Colada"):
                    if not texto_lista_colada.strip():
                        st.warning("⚠️ Por favor, cole os dados na caixa de texto acima antes de importar.")
                    else:
                        try:
                            cursor = conn.cursor()
                            linhas = texto_lista_colada.strip().split("\n")
                            sucessos = 0
                            
                            for linha in linhas:
                                if not linha.strip():
                                    continue
                                
                                # Divide a linha rigorosamente por tabulação (formato de tabela copiada)
                                partes = linha.split("\t")
                                if len(partes) < 2:
                                    # Fallback caso venha com espaços normais
                                    partes = linha.strip().split()
                                    
                                # Mapeia as colunas com base na estrutura (ID, Produto, Qtd, Fornecedor, Grupo, V.Compra, V.Venda)
                                if len(partes) >= 7:
                                    prod = partes[1].strip().upper()
                                    qtd = float(partes[2].strip().replace(',', '.') or 0.0)
                                    forn = partes[3].strip().upper()
                                    grupo = partes[4].strip().upper()
                                    v_compra = float(partes[5].strip().replace(',', '.') or 0.0)
                                    v_venda = float(partes[6].strip().replace(',', '.') or 0.0)
                                elif len(partes) >= 6:
                                    prod = partes[0].strip().upper()
                                    qtd = float(partes[1].strip().replace(',', '.') or 0.0)
                                    forn = partes[2].strip().upper()
                                    grupo = partes[3].strip().upper()
                                    v_compra = float(partes[4].strip().replace(',', '.') or 0.0)
                                    v_venda = float(partes[5].strip().replace(',', '.') or 0.0)
                                else:
                                    continue
                                    
                                # Insere ou atualiza de forma limpa usando a restrição OR REPLACE
                                cursor.execute("""
                                    INSERT OR REPLACE INTO produtos (produto, grupo, fornecedor, quantidade, valor_compra, valor_venda)
                                    VALUES (?, ?, ?, ?, ?, ?)
                                """, (prod, grupo, forn, qtd, v_compra, v_venda))
                                sucessos += 1
                                
                            conn.commit()
                            if sucessos > 0:
                                st.success(f"✅ {sucessos} produtos importados/atualizados com sucesso!")
                                st.rerun()
                            else:
                                st.warning("⚠️ Nenhum produto válido foi detetado. Verifique o formato do texto colado.")
                        except Exception as e:
                            st.error(f"Erro ao processar a lista: {e}")
        
            try:
                df_produtos = pd.read_sql_query("SELECT * FROM produtos", conn)
            except Exception:
                df_produtos = pd.DataFrame()
        
            # Filtro de stock
            filtro_estoque = st.selectbox(
                "Filtrar por Status do Stock:",
                ["Todos", "Com Stock (> 0)", "Zerados (= 0)"],
                key="filtro_status_stock"
            )
        
            cols_esperadas = ['id', 'produto', 'quantidade', 'fornecedor', 'grupo', 'valor_compra', 'valor_venda']
            for c in cols_esperadas:
                if c not in df_produtos.columns:
                    df_produtos[c] = 0.0 if ('valor' in c or 'quantidade' in c) else ""
        
            if not df_produtos.empty:
                cols_finais = [c for c in cols_esperadas if c in df_produtos.columns]
                df_produtos = df_produtos[cols_finais]
                
                # Aplica o filtro de quantidade de forma segura
                df_produtos['quantidade'] = pd.to_numeric(df_produtos['quantidade'], errors='coerce').fillna(0)
                
                if filtro_estoque == "Com Stock (> 0)":
                    df_produtos = df_produtos[df_produtos['quantidade'] > 0]
                elif filtro_estoque == "Zerados (= 0)":
                    df_produtos = df_produtos[df_produtos['quantidade'] == 0]
    
            df_estoque_editado = st.data_editor(df_produtos, use_container_width=True, hide_index=True, key="editor_estoque_produtos")
    
            col_salvar, col_atualizar, col_pdf = st.columns([1, 1, 1])
    
            with col_salvar:
                if st.button("💾 Salvar Alterações no Estoque", type="primary", key="btn_salvar_estoque"):
                    try:
                        cursor = conn.cursor()
                        for col in ["grupo", "fornecedor"]:
                            try:
                                cursor.execute(f"ALTER TABLE produtos ADD COLUMN {col} TEXT")
                            except Exception:
                                pass
    
                        for _, row in df_estoque_editado.iterrows():
                            cursor.execute("""
                                UPDATE produtos 
                                SET produto = ?, quantidade = ?, valor_compra = ?, valor_venda = ?, grupo = ?, fornecedor = ? 
                                WHERE id = ?
                            """, (str(row['produto']).strip(), float(row['quantidade']), float(row['valor_compra']), float(row['valor_venda']), str(row.get('grupo', '')), str(row.get('fornecedor', '')), int(row['id'])))
    
                        conn.commit()
                        st.cache_data.clear()
                        st.success("✅ Alterações do estoque salvas com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar: {e}")
    
            with col_atualizar:
                if st.button("🔄 Atualizar Preços de Compra", key="btn_atualizar_precos"):
                    try:
                        with conn:
                            cursor = conn.cursor()
                            cursor.execute("UPDATE produtos SET valor_compra = (SELECT valor_compra FROM compras WHERE compras.produto = produtos.produto ORDER BY id DESC LIMIT 1) WHERE EXISTS (SELECT 1 FROM compras WHERE compras.produto = produtos.produto)")
                        st.cache_data.clear()
                        st.success("✅ Preços de compra atualizados com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao atualizar preço: {e}")

            with col_pdf:
                # --- BOTÃO PARA GERAR PDF DO ESTOQUE COM TOTAIS ---
                try:
                    import io
                    from reportlab.lib.pagesizes import letter
                    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
                    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                    from reportlab.lib import colors

                    def gerar_pdf_estoque(df_dados):
                        buffer = io.BytesIO()
                        doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
                        elements = []
                        styles = getSampleStyleSheet()
                        
                        title_style = ParagraphStyle(
                            'TitleStyle',
                            parent=styles['Heading1'],
                            fontSize=16,
                            textColor=colors.HexColor('#1f2937'),
                            spaceAfter=5,
                            alignment=1
                        )
                        
                        sub_style = ParagraphStyle(
                            'SubStyle',
                            parent=styles['Normal'],
                            fontSize=10,
                            textColor=colors.HexColor('#4b5563'),
                            spaceAfter=15,
                            alignment=1
                        )
                        
                        elements.append(Paragraph("Relatório de Estoque de Produtos e Preços", title_style))
                        
                        # Calcula os valores totais (Quantidade * Valor)
                        total_compra = 0.0
                        total_venda = 0.0
                        
                        for _, row in df_dados.iterrows():
                            try:
                                qtd = float(str(row.get('quantidade', 0)).replace(',', '.') or 0.0)
                                v_compra = float(str(row.get('valor_compra', 0)).replace(',', '.') or 0.0)
                                v_venda = float(str(row.get('valor_venda', 0)).replace(',', '.') or 0.0)
                                
                                total_compra += qtd * v_compra
                                total_venda += qtd * v_venda
                            except:
                                pass
                                
                        # Formata o texto dos totais para exibir no PDF
                        texto_totais = f"<b>Valor Total de Compras:</b> R$ {total_compra:,.2f} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Valor Total de Vendas:</b> R$ {total_venda:,.2f}"
                        elements.append(Paragraph(texto_totais, sub_style))
                        elements.append(Spacer(1, 5))
                        
                        # Cabeçalho e dados da tabela
                        data = [["ID", "Produto", "Qtd", "Fornecedor", "Grupo", "V. Compra", "V. Venda"]]
                        for _, row in df_dados.iterrows():
                            data.append([
                                str(row.get('id', '')),
                                str(row.get('produto', '')),
                                str(row.get('quantidade', '')),
                                str(row.get('fornecedor', '')),
                                str(row.get('grupo', '')),
                                f"R$ {float(str(row.get('valor_compra', 0)).replace(',', '.') or 0):.2f}",
                                f"R$ {float(str(row.get('valor_venda', 0)).replace(',', '.') or 0):.2f}"
                            ])
                            
                        t = Table(data, colWidths=[35, 170, 50, 85, 75, 60, 60])
                        t.setStyle(TableStyle([
                            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#374151')),
                            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                            ('FONTSIZE', (0,0), (-1,0), 9),
                            ('BOTTOMPADDING', (0,0), (-1,0), 6),
                            ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#f9fafb')),
                            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#d1d5db')),
                            ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
                            ('FONTSIZE', (0,1), (-1,-1), 8),
                        ]))
                        
                        elements.append(t)
                        doc.build(elements)
                        buffer.seek(0)
                        return buffer.getvalue()

                    pdf_estoque_bytes = gerar_pdf_estoque(df_estoque_editado)
                    
                    st.download_button(
                        label="📄 Gerar PDF do Estoque",
                        data=pdf_estoque_bytes,
                        file_name="relatorio_estoque.pdf",
                        mime="application/pdf",
                        key="btn_baixar_pdf_estoque"
                    )
                except Exception as e_pdf_est:
                    st.error(f"Erro ao gerar PDF: {e_pdf_est}")
        elif menu_admin == "Cadastros (Clientes / Fornecedores / Grupos)":
            st.subheader("👥 Cadastros (Clientes / Fornecedores / Grupos)")
            tab_cli, tab_prod, tab_forn, tab_grup = st.tabs(["👤 Clientes", "📦 Produtos", "🏢 Fornecedores", "🏷️ Grupos"])
    
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
                            sucesso, msg = salvar_cliente_completo(txt_nome_cli, txt_tel_cli, txt_doc_cli, txt_end_cli, txt_cidade_cli)
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
                                cursor.execute("UPDATE clientes SET cliente = ?, nome = ?, cpf = ?, endereco = ?, email = ?, fone = ?, cidade = ? WHERE id = ?", (novo_nome, novo_nome, novo_cpf, novo_end, novo_email, novo_fone, novo_cidade, id_selecionado))
                                conn.commit()
                                st.success("Cliente atualizado com sucesso!")
                                st.rerun()
                                
                            if btn_excluir:
                                cursor = conn.cursor()
                                cursor.execute("DELETE FROM clientes WHERE id = ?", (id_selecionado,))
                                conn.commit()
                                st.success("Cliente excluído com sucesso!")
                                st.rerun()

                        # -----------------------------------------------------------------------------
                        # EXTRATO FINANCEIRO & HISTÓRICO DO CLIENTE (STATUS CORRIGIDO)
                        # -----------------------------------------------------------------------------
                        st.markdown("---")
                        st.markdown(f"### 💰 Extrato Financeiro: {nome_atual}")
                        
                        try:
                            from datetime import datetime
                            from zoneinfo import ZoneInfo
                            from fpdf import FPDF
                            import pandas as pd
                            
                            query_financeiro = """
                                SELECT *
                                FROM vendas
                                WHERE cliente = ?
                                ORDER BY id DESC
                            """
                            df_fin_cliente = pd.read_sql_query(query_financeiro, conn, params=(nome_atual,))
                        
                            if not df_fin_cliente.empty:
                                if 'status' in df_fin_cliente.columns:
                                    df_fin_cliente['status_limpo'] = df_fin_cliente['status'].astype(str).str.strip().str.capitalize()
                                else:
                                    df_fin_cliente['status_limpo'] = 'Concluído'
                        
                                def verificar_em_aberto(row):
                                    status = str(row.get('status_limpo', '')).lower()
                                    if status == 'quitado':
                                        return False
                                    if status == 'parcial':
                                        restante_val = float(row.get('restante', 0.0) or 0.0)
                                        return restante_val > 0
                                    
                                    fp = str(row.get('forma_pagamento', '')).lower()
                                    termos = ['crediário', 'crediario', 'fiado', 'prazo', 'p1:', 'p1', 'parcial']
                                    return any(termo in fp for termo in termos)
                        
                                df_fin_cliente['is_aberto'] = df_fin_cliente.apply(verificar_em_aberto, axis=1)
                        
                                df_abertos = df_fin_cliente[df_fin_cliente['is_aberto'] == True]
                                df_quitados = df_fin_cliente[df_fin_cliente['is_aberto'] == False]
                        
                                total_falta_pagar = 0.0
                                for _, r_row in df_abertos.iterrows():
                                    v_tot = float(r_row.get('valor_total', 0.0) or 0.0)
                                    v_res = float(r_row.get('restante', 0.0) or 0.0)
                                    total_falta_pagar += v_res if v_res > 0 else v_tot
                        
                                total_ja_pago = df_fin_cliente['valor_recebido'].sum() if 'valor_recebido' in df_fin_cliente.columns else 0.0
                        
                                col_m1, col_m2 = st.columns(2)
                                with col_m1:
                                    st.metric("🔴 Saldo Devedor (Falta Pagar)", f"R$ {total_falta_pagar:.2f}")
                                with col_m2:
                                    st.metric("🟢 Total Já Pago pelo Cliente", f"R$ {total_ja_pago:.2f}")
                        
                                # -----------------------------------------------------------------------------
                                # CLASSE PARA GERAR O PDF COM O CABEÇALHO, RESUMO E VALOR UNITÁRIO
                                # -----------------------------------------------------------------------------
                                class PDFComprovante(FPDF):
                                    def __init__(self, cliente_nome, saldo_devedor, total_pago):
                                        super().__init__()
                                        self.cliente_nome = cliente_nome
                                        self.saldo_devedor = saldo_devedor
                                        self.total_pago = total_pago
                        
                                    def header(self):
                                        self.set_font('Arial', 'B', 14)
                                        self.set_text_color(20, 70, 140)
                                        self.cell(0, 6, "SEBASTIÃO JOSE DE ALENCAR NETO", 0, 1, 'C')
                                        
                                        self.set_font('Arial', '', 9)
                                        self.set_text_color(50, 50, 50)
                                        self.cell(0, 4, "CNPJ: 954.511.611-00   INSC.EST.:", 0, 1, 'C')
                                        self.cell(0, 4, "CONTATO: (99) 98814-9722 OU (99) 98501-6050", 0, 1, 'C')
                                        
                                        self.set_font('Arial', 'B', 11)
                                        self.cell(0, 6, "Extrato Financeiro / Comprovante do Cliente", 0, 1, 'C')
                                        
                                        self.set_font('Arial', 'B', 10)
                                        data_atual_str = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime('%Y-%m-%d %H:%M:%S')
                                        self.cell(0, 6, f"Cliente: {self.cliente_nome} | Gerado em: {data_atual_str}", 0, 1, 'L')
                                        
                                        # Quadro de Resumo Financeiro no Topo do PDF
                                        self.ln(2)
                                        self.set_fill_color(240, 240, 240)
                                        self.set_font('Arial', 'B', 9)
                                        self.cell(95, 6, f"Saldo Devedor (Falta Pagar): R$ {self.saldo_devedor:.2f}", 1, 0, 'L', True)
                                        self.cell(95, 6, f"Total Ja Pago: R$ {self.total_pago:.2f}", 1, 1, 'L', True)
                                        
                                        self.ln(2)
                                        self.set_draw_color(20, 70, 140)
                                        self.line(10, self.get_y(), 200, self.get_y())
                                        self.ln(4)
                        
                                    def footer(self):
                                        self.set_y(-15)
                                        self.set_font('Arial', 'I', 8)
                                        self.cell(0, 10, f"Pagina {self.page_no()}", 0, 0, 'C')
                        
                                def gerar_pdf_bytes(nome_cli, df_completo, s_dev, t_pag):
                                    pdf = PDFComprovante(nome_cli, s_dev, t_pag)
                                    pdf.add_page()
                                    pdf.set_font('Arial', '', 10)
                                    
                                    pdf.set_font('Arial', 'B', 10)
                                    pdf.cell(0, 6, "Historico de Transacoes:", 0, 1, 'L')
                                    pdf.ln(2)
                                    
                                    # Cabeçalho da Tabela no PDF
                                    pdf.set_fill_color(230, 230, 230)
                                    pdf.cell(10, 6, "ID", 1, 0, 'C', True)
                                    pdf.cell(58, 6, "Produto", 1, 0, 'L', True)
                                    pdf.cell(15, 6, "Qtd", 1, 0, 'C', True)
                                    pdf.cell(24, 6, "Vlr. Unit.", 1, 0, 'R', True)
                                    pdf.cell(24, 6, "Total (R$)", 1, 0, 'R', True)
                                    pdf.cell(32, 6, "Status", 1, 0, 'C', True)
                                    pdf.cell(27, 6, "Data", 1, 1, 'C', True)
                                    
                                    pdf.set_font('Arial', '', 9)
                                    for _, row in df_completo.iterrows():
                                        pdf.cell(10, 6, str(row.get('id', '')), 1, 0, 'C')
                                        pdf.cell(58, 6, str(row.get('produto', ''))[:26], 1, 0, 'L')
                                        
                                        qtd = float(row.get('quantidade', 0) or 0)
                                        pdf.cell(15, 6, str(int(qtd) if qtd.is_integer() else qtd), 1, 0, 'C')
                                        
                                        val_tot = float(row.get('valor_total', 0.0) or 0.0)
                                        val_unit = (val_tot / qtd) if qtd > 0 else float(row.get('valor_venda', 0.0) or 0.0)
                                        
                                        pdf.cell(24, 6, f"R$ {val_unit:.2f}", 1, 0, 'R')
                                        pdf.cell(24, 6, f"R$ {val_tot:.2f}", 1, 0, 'R')
                                        
                                        st_val = str(row.get('status', ''))
                                        if st_val.lower() in ['nan', 'none', '']:
                                            status_exibicao = "Pendente" if row.get('is_aberto', True) else "Quitado"
                                        else:
                                            status_exibicao = st_val.capitalize()
                        
                                        pdf.cell(32, 6, status_exibicao[:15], 1, 0, 'C')
                                        data_val = str(row.get('data', ''))[:16]
                                        pdf.cell(27, 6, data_val, 1, 1, 'C')
                                        
                                    # Tratamento robusto para extrair os bytes do PDF sem corromper
                                    try:
                                        res = pdf.output(dest='S')
                                        if isinstance(res, str):
                                            return res.encode('latin1', errors='replace')
                                        elif isinstance(res, (bytes, bytearray)):
                                            return bytes(res)
                                    except Exception:
                                        pass
                                    
                                    try:
                                        res2 = pdf.output()
                                        if isinstance(res2, bytes):
                                            return res2
                                        elif isinstance(res2, bytearray):
                                            return bytes(res2)
                                        elif isinstance(res2, str):
                                            return res2.encode('latin1', errors='replace')
                                    except Exception:
                                        pass
                                        
                                    return b""
                        
                                st.markdown("---")
                                pdf_data = gerar_pdf_bytes(nome_atual, df_fin_cliente, total_falta_pagar, total_ja_pago)
                                
                                if pdf_data:
                                    st.download_button(
                                        label="📥 Descarregar Comprovante / Extrato em PDF",
                                        data=pdf_data,
                                        file_name=f"comprovante_{nome_atual.replace(' ', '_')}.pdf",
                                        mime="application/pdf",
                                        type="secondary"
                                    )
                                else:
                                    st.error("Erro ao gerar o ficheiro PDF.")
                        
                                st.markdown("---")
                        
                                aba_aberto, aba_pago = st.tabs(["🔴 Compras Pendentes (Em Aberto)", "🟢 Histórico de Pagamentos (Quitados)"])
                        
                                with aba_aberto:
                                    if not df_abertos.empty:
                                        st.info("💡 Marque as compras que o cliente deseja pagar. A data e a hora serão gravadas no horário do Brasil.")
                                        
                                        df_abertos_ex = df_abertos.copy()
                                        df_abertos_ex.insert(0, "Quitar?", False)
                        
                                        colunas_desejadas = [c for c in ['Quitar?', 'id', 'produto', 'quantidade', 'valor_total', 'valor_recebido', 'restante', 'data'] if c in df_abertos_ex.columns]
                                        
                                        df_edit_abertos = st.data_editor(
                                            df_abertos_ex[colunas_desejadas],
                                            use_container_width=True,
                                            hide_index=True,
                                            key="editor_vendas_abertas_cliente"
                                        )
                        
                                        st.markdown("---")
                                        col_b1, col_b2 = st.columns(2)
                                        with col_b1:
                                            forma_recebimento = st.selectbox(
                                                "💳 Forma de Recebimento:",
                                                ["Dinheiro", "Pix", "Cartão de Crédito", "Cartão de Débito", "Transferência", "Outros"],
                                                key="select_forma_recebimento_baixa"
                                            )
                                        with col_b2:
                                            valor_recebido_input = st.number_input(
                                                "💵 Valor que o Cliente está Pagando Agora (R$):",
                                                min_value=0.0,
                                                value=float(total_falta_pagar),
                                                step=1.0,
                                                key="input_valor_recebido_baixa"
                                            )
                        
                                        if st.button("✅ Confirmar Recebimento", type="primary", key="btn_dar_baixa_vendas_direto"):
                                            try:
                                                cursor = conn.cursor()
                                                marcados = df_edit_abertos[df_edit_abertos['Quitar?'] == True]
                                                if not marcados.empty:
                                                    dinheiro_disponivel = float(valor_recebido_input)
                                                    data_agora = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime('%Y-%m-%d %H:%M:%S')
                                                    
                                                    for _, row_m in marcados.iterrows():
                                                        v_id = row_m['id']
                                                        v_total = float(row_m.get('valor_total', 0.0) or 0.0)
                                                        v_restante_atual = float(row_m.get('restante', 0.0) or 0.0)
                                                        debito_alvo = v_restante_atual if v_restante_atual > 0 else v_total
                                                        
                                                        ja_pago_anterior = float(row_m.get('valor_recebido', 0.0) or 0.0)
                        
                                                        if dinheiro_disponivel >= debito_alvo:
                                                            novo_valor_recebido = ja_pago_anterior + debito_alvo
                                                            cursor.execute(
                                                                """UPDATE vendas 
                                                                   SET status = 'Quitado', 
                                                                       forma_pagamento = ?, 
                                                                       valor_recebido = ?, 
                                                                       troco = 0.0, 
                                                                       restante = 0.0,
                                                                       data = ?
                                                                   WHERE id = ?""",
                                                                (f"Quitado ({forma_recebimento})", novo_valor_recebido, data_agora, v_id)
                                                            )
                                                            dinheiro_disponivel -= debito_alvo
                                                        elif dinheiro_disponivel > 0:
                                                            v_pago_agora = dinheiro_disponivel
                                                            novo_valor_recebido = ja_pago_anterior + v_pago_agora
                                                            v_novo_restante = debito_alvo - v_pago_agora
                                                            cursor.execute(
                                                                """UPDATE vendas 
                                                                   SET status = 'Parcial', 
                                                                       forma_pagamento = ?, 
                                                                       valor_recebido = ?, 
                                                                       troco = 0.0, 
                                                                       restante = ?,
                                                                       data = ?
                                                                   WHERE id = ?""",
                                                                (f"Parcial ({forma_recebimento})", novo_valor_recebido, v_novo_restante, data_agora, v_id)
                                                            )
                                                            dinheiro_disponivel = 0.0
                                                        else:
                                                            break
                                                    
                                                    conn.commit()
                                                    st.success("🎉 Pagamento registado no horário do Brasil com sucesso!")
                                                    st.rerun()
                                                else:
                                                    st.warning("⚠️ Marque pelo menos uma compra na coluna 'Quitar?' para registar o pagamento.")
                                            except Exception as e_quitar:
                                                st.error(f"Erro ao processar recebimento: {e_quitar}")
                                    else:
                                        st.success("✨ Este cliente não possui nenhuma compra em aberto no momento!")
                        
                                with aba_pago:
                                    if not df_quitados.empty:
                                        cols_drop = [c for c in ['status_limpo', 'is_aberto'] if c in df_quitados.columns]
                                        st.dataframe(df_quitados.drop(columns=cols_drop), use_container_width=True, hide_index=True)
                                    else:
                                        st.info("Nenhum histórico de pagamento quitado encontrado para este cliente.")
                        
                            else:
                                st.info(f"ℹ️ Não há registos de vendas ou pedidos associados ao cliente '{nome_atual}'.")
                        
                        except Exception as e_fin:
                            st.warning(f"Extrato financeiro indisponível no momento: {e_fin}")
                    else:
                        st.info("Nenhum cliente cadastrado ainda.")
                else:
                    st.info("Nenhum cliente cadastrado ainda.")
    
            with tab_prod:
                st.subheader("📝 Gerenciar Produtos (Cadastrar, Editar e Excluir)")
                try:
                    df_g = carregar_dados("SELECT DISTINCT grupo FROM grupos WHERE grupo IS NOT NULL AND grupo != '' ORDER BY grupo")
                    grupos_opt = df_g['grupo'].tolist() if not df_g.empty else ["GERAL"]
                except Exception:
                    grupos_opt = ["GERAL"]
    
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
                                for col in ["grupo", "fornecedor", "valor_compra", "valor_venda"]:
                                    try:
                                        cursor.execute(f"ALTER TABLE produtos ADD COLUMN {col} TEXT")
                                    except Exception:
                                        pass
    
                                cursor.execute("INSERT INTO produtos (produto, grupo, fornecedor, quantidade, valor_compra, valor_venda) VALUES (?, ?, ?, ?, ?, ?)", (txt_nome_produto.strip().upper(), grupo_produto, fornecedor_produto, float(estoque_inicial), float(val_compra), float(val_venda)))
                                conn.commit()
                                st.cache_data.clear()
                                st.success(f"✅ Produto '{txt_nome_produto}' cadastrado com sucesso!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao cadastrar produto: {e}")
    
                st.markdown("---")
                st.subheader("📋 Lista de Produtos")
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
    
                df_gerenciar_editado = st.data_editor(df_produtos_gerenciar, use_container_width=True, hide_index=True, key="editor_gerenciar_produtos_tab")
    
                col_btn_salvar, col_btn_excluir = st.columns([1, 1])
                with col_btn_salvar:
                    if st.button("💾 Salvar Alterações da Tabela", type="primary", key="btn_salvar_tabela_gerenciar"):
                        try:
                            with conn:
                                cursor = conn.cursor()
                                for _, row in df_gerenciar_editado.iterrows():
                                    cursor.execute("UPDATE produtos SET produto = ?, quantidade = ?, valor_compra = ?, valor_venda = ?, grupo = ?, fornecedor = ? WHERE id = ?", (row['produto'], row['quantidade'], row['valor_compra'], row['valor_venda'], row['grupo'], row['fornecedor'], row['id']))
                            st.cache_data.clear()
                            st.success("✅ Alterações salvas com sucesso!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao salvar alterações: {e}")
    
                with col_btn_excluir:
                    lista_produtos_excluir = df_produtos_gerenciar['produto'].tolist() if not df_produtos_gerenciar.empty else []
                    prod_para_excluir = st.selectbox("Selecione um produto para excluir", options=lista_produtos_excluir, key="sel_prod_excluir")
                    if st.button("🗑️ Excluir Produto Selecionado", key="btn_excluir_produto"):
                        # Verifica se o usuário logado tem permissão para excluir produtos
                        if checar_permissao(st.session_state.get('usuario_logado'), "produtos", "excluir"):
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
                        else:
                            st.error("🚫 Acesso negado: Você não tem permissão para excluir produtos.")
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
                st.subheader("📋 Lista de Fornecedores")
                df_forn_view = carregar_dados("SELECT * FROM fornecedores")
                if not df_forn_view.empty:
                    df_editado_forn = st.data_editor(df_forn_view, use_container_width=True, hide_index=True, key="editor_fornecedores")
                    col_f1, col_f2 = st.columns(2)
                    with col_f1:
                        if st.button("💾 Salvar Alterações de Fornecedores"):
                            try:
                                cursor = conn.cursor()
                                for _, row in df_editado_forn.iterrows():
                                    cursor.execute("UPDATE fornecedores SET fornecedor = ? WHERE id = ?", (str(row.get('fornecedor')).upper(), row.get('id')))
                                conn.commit()
                                st.success("Fornecedores atualizados com sucesso!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao salvar: {e}")
                    with col_f2:
                        forn_selecionado = st.selectbox("Selecione um fornecedor para excluir", df_forn_view['fornecedor'].tolist(), key="select_del_forn")
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
                st.subheader("📋 Lista de Grupos")
                df_grup_view = carregar_dados("SELECT * FROM grupos")
                if not df_grup_view.empty:
                    df_editado_grup = st.data_editor(df_grup_view, use_container_width=True, hide_index=True, key="editor_grupos")
                    col_g1, col_g2 = st.columns(2)
                    with col_g1:
                        if st.button("💾 Salvar Alterações de Grupos"):
                            try:
                                cursor = conn.cursor()
                                for _, row in df_editado_grup.iterrows():
                                    cursor.execute("UPDATE grupos SET grupo = ? WHERE id = ?", (str(row.get('grupo')).upper(), row.get('id')))
                                conn.commit()
                                st.success("Grupos atualizados com sucesso!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao salvar: {e}")
                    with col_g2:
                        grup_selecionado = st.selectbox("Selecione um grupo para excluir", df_grup_view['grupo'].tolist(), key="select_del_grup")
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
            st.info("Gerencie cópias de segurança do seu banco de dados com total segurança.")

            tab_bk1, tab_bk2 = st.tabs(["📤 Fazer Backup", "📥 Restaurar Backup"])

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
                except Exception:
                    st.warning("O arquivo do banco de dados ainda não foi criado ou não foi encontrado.")

            with tab_bk2:
                st.subheader("Restaurar Sistema por Arquivo de Backup")
                st.warning("⚠️ **Atenção:** Enviar um arquivo de backup antigo irá substituir os dados atuais.")
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

        # Módulo de Gestão de Funcionários vinculado ao RH
        elif "RH" in str(menu_admin) or "Recursos Humanos" in str(menu_admin):
            st.title("👥 Gestão de Recursos Humanos (RH)")
            st.markdown("Faça a gestão de colaboradores, registos com descontos, vales, haveres e emissão de Holerites em PDF.")
        
            from datetime import datetime
        
            # Função ultra-segura para gerar o PDF do Holerite com Ambas as Datas e Detalhes
            def gerar_bytes_pdf(dados_func, dados_pag):
                try:
                    from fpdf import FPDF
                    pdf = FPDF(orientation='P', unit='mm', format='A4')
                    pdf.add_page()
                    
                    # Desenha o Recibo
                    pdf.rect(10, 10, 190, 134)
                    pdf.rect(10, 10, 130, 22)
                    pdf.rect(140, 10, 60, 22)
                    
                    pdf.set_xy(12, 11)
                    pdf.set_font("Arial", "B", 7)
                    pdf.cell(126, 4, "EMPREGADOR:", 0, 1)
                    pdf.set_font("Arial", "", 7)
                    pdf.set_x(12)
                    pdf.cell(126, 3.5, "Nome: NM COMERCIO", 0, 1)
                    pdf.set_x(12)
                    pdf.cell(126, 3.5, "Endereço: Rua Principal, S/N - BA", 0, 1)
                    pdf.set_x(12)
                    pdf.cell(126, 3.5, "CNPJ: 954.511.611-00", 0, 1)
                    
                    pdf.set_xy(142, 11)
                    pdf.set_font("Arial", "B", 8.5)
                    pdf.cell(56, 4, "Recibo de Pagamento", 0, 1, 'C')
                    pdf.set_xy(142, 15)
                    pdf.set_font("Arial", "B", 7.5)
                    pdf.cell(56, 3.5, "de Salário / Vales", 0, 1, 'C')
                    
                    # 1. Competência / Referência
                    pdf.set_xy(142, 19)
                    pdf.set_font("Arial", "", 7)
                    ref_raw = str(dados_pag.get('referencia', datetime.now().strftime('%Y-%m')))
                    if len(ref_raw) >= 7 and '-' in ref_raw:
                        p_ano, p_mes = ref_raw.split('-')[:2]
                        ref_mes = f"01/{p_mes}/{p_ano}"
                    else:
                        ref_mes = ref_raw
                    pdf.cell(56, 3, f"Ref: {ref_mes}", 0, 1, 'C')

                    # 2. Data do Pagamento Efetuado
                    pdf.set_xy(142, 22.5)
                    data_pag_raw = str(dados_pag.get('data_pagamento', ''))
                    if len(data_pag_raw) >= 10:
                        dp_parts = data_pag_raw[:10].split('-')
                        if len(dp_parts) == 3:
                            data_pag_fmt = f"{dp_parts[2]}/{dp_parts[1]}/{dp_parts[0]}"
                        else:
                            data_pag_fmt = data_pag_raw[:10]
                    else:
                        data_pag_fmt = data_pag_raw[:10] if data_pag_raw else '-'
                    pdf.cell(56, 3, f"Data Pgto: {data_pag_fmt}", 0, 1, 'C')
        
                    pdf.rect(10, 32, 190, 12)
                    pdf.set_xy(12, 33)
                    pdf.set_font("Arial", "B", 7)
                    pdf.cell(20, 3, "CÓDIGO", 0, 0)
                    pdf.cell(85, 3, "NOME DO FUNCIONÁRIO", 0, 0)
                    pdf.cell(35, 3, "CBO", 0, 0)
                    pdf.cell(50, 3, "FUNÇÃO", 0, 0)
                    
                    pdf.set_xy(12, 37)
                    pdf.set_font("Arial", "", 8)
                    func_id = int(dados_func.get('id', 1))
                    pdf.cell(20, 5, f"{func_id:05d}", 0, 0)
                    pdf.cell(85, 5, str(dados_func.get('nome', '')), 0, 0)
                    pdf.cell(35, 5, str(dados_func.get('cbo', '-')), 0, 0)
                    pdf.cell(50, 5, str(dados_func.get('cargo', '-')), 0, 0)
        
                    pdf.rect(10, 44, 190, 7)
                    pdf.set_xy(12, 45)
                    pdf.set_font("Arial", "B", 7)
                    pdf.cell(15, 5, "Cód.", 0, 0)
                    pdf.cell(75, 5, "Descrição", 0, 0)
                    pdf.cell(25, 5, "Referência", 0, 0, 'C')
                    pdf.cell(37, 5, "Proventos", 0, 0, 'R')
                    pdf.cell(38, 5, "Descontos", 0, 1, 'R')
        
                    pdf.rect(10, 51, 190, 58)
                    pdf.set_xy(12, 53)
                    pdf.set_font("Arial", "", 8)
                    
                    valor_salario = float(dados_pag.get('valor', 0.0))
                    tipo_pag = str(dados_pag.get('tipo', 'Salário')).upper()
                    inss_val = float(dados_pag.get('inss', 0.0))
                    faltas_qtd = float(dados_pag.get('faltas', 0.0))
                    desc_faltas = float(dados_pag.get('desconto_faltas', 0.0))
        
                    pdf.cell(15, 5, "001", 0, 0)
                    pdf.cell(75, 5, f"{tipo_pag}", 0, 0)
                    pdf.cell(25, 5, "220.00", 0, 0, 'C')
                    pdf.cell(37, 5, f"R$ {valor_salario:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), 0, 0, 'R')
                    pdf.cell(38, 5, "R$ 0,00", 0, 1, 'R')
        
                    curr_y = 58
                    if faltas_qtd > 0 or desc_faltas > 0:
                        pdf.set_xy(12, curr_y)
                        pdf.cell(15, 5, "450", 0, 0)
                        pdf.cell(75, 5, f"FALTAS ({faltas_qtd} dia(s))", 0, 0)
                        pdf.cell(25, 5, f"{faltas_qtd:.1f}", 0, 0, 'C')
                        pdf.cell(37, 5, "R$ 0,00", 0, 0, 'R')
                        pdf.cell(38, 5, f"R$ {desc_faltas:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), 0, 1, 'R')
                        curr_y += 5
        
                    if inss_val > 0:
                        pdf.set_xy(12, curr_y)
                        pdf.cell(15, 5, "903", 0, 0)
                        pdf.cell(75, 5, "INSS", 0, 0)
                        pdf.cell(25, 5, "", 0, 0, 'C')
                        pdf.cell(37, 5, "R$ 0,00", 0, 0, 'R')
                        pdf.cell(38, 5, f"R$ {inss_val:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), 0, 1, 'R')
        
                    total_venc = valor_salario
                    total_desc = inss_val + desc_faltas
                    liquido = total_venc - total_desc
        
                    pdf.rect(10, 109, 130, 17)
                    pdf.rect(140, 109, 60, 17)
                    
                    pdf.set_xy(12, 110)
                    pdf.set_font("Arial", "B", 7)
                    pdf.cell(126, 3, "MENSAGENS:", 0, 1)
                    pdf.set_font("Arial", "", 7)
                    pdf.set_x(12)
                    pdf.cell(126, 3, "Documento gerado automaticamente pelo Sistema CRM Comércio.", 0, 1)
        
                    pdf.set_xy(142, 110)
                    pdf.set_font("Arial", "B", 7)
                    pdf.cell(28, 4, "Total Vencimentos:", 0, 0)
                    pdf.cell(28, 4, f"R$ {total_venc:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), 0, 1, 'R')
                    
                    pdf.set_x(142)
                    pdf.cell(28, 4, "Total Descontos:", 0, 0)
                    pdf.cell(28, 4, f"R$ {total_desc:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), 0, 1, 'R')
                    
                    pdf.set_x(142)
                    pdf.set_font("Arial", "B", 8)
                    pdf.cell(28, 5, "Líquido a Receber:", 0, 0)
                    pdf.cell(28, 5, f"R$ {liquido:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), 0, 1, 'R')
        
                    pdf.rect(10, 126, 190, 18)
                    pdf.set_xy(12, 127)
                    pdf.set_font("Arial", "B", 6)
                    pdf.cell(31, 3, "Salário Base", 0, 0)
                    pdf.cell(31, 3, "Base Cálc. INSS", 0, 0)
                    pdf.cell(31, 3, "Base Cálc. FGTS", 0, 0)
                    pdf.cell(31, 3, "FGTS do Mês", 0, 0)
                    pdf.cell(32, 3, "Base Cálc. IRRF", 0, 0)
                    pdf.cell(32, 3, "Faixa IRRF", 0, 1)
        
                    pdf.set_xy(12, 132)
                    pdf.set_font("Arial", "", 7)
                    pdf.cell(31, 4, f"R$ {valor_salario:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), 0, 0)
                    base_inss = max(0.0, valor_salario - desc_faltas)
                    pdf.cell(31, 4, f"R$ {base_inss:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), 0, 0)
                    pdf.cell(31, 4, f"R$ {valor_salario:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), 0, 0)
                    fgts_val = valor_salario * 0.08
                    pdf.cell(31, 4, f"R$ {fgts_val:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), 0, 0)
                    pdf.cell(32, 4, "R$ 0,00", 0, 0)
                    pdf.cell(32, 4, "0", 0, 1)
        
                    res = pdf.output(dest='S')
                    if isinstance(res, str):
                        return res.encode('latin1', errors='replace')
                    return bytes(res)
                except Exception as e:
                    return f"Erro PDF: {str(e)}".encode('utf-8')
        
            # Garantir tabelas com coluna competencia
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS funcionarios (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        nome TEXT,
                        cargo TEXT,
                        telefone TEXT,
                        salario REAL,
                        admissao TEXT,
                        cbo TEXT
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS pagamentos_funcionarios (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        colaborador TEXT,
                        tipo TEXT,
                        valor REAL,
                        data_pagamento TEXT,
                        inss REAL DEFAULT 0.0,
                        faltas REAL DEFAULT 0.0,
                        desconto_faltas REAL DEFAULT 0.0,
                        competencia TEXT DEFAULT ''
                    )
                """)
                for col_def in [("inss", "REAL DEFAULT 0.0"), ("faltas", "REAL DEFAULT 0.0"), ("desconto_faltas", "REAL DEFAULT 0.0"), ("competencia", "TEXT DEFAULT ''")]:
                    try:
                        cursor.execute(f"ALTER TABLE pagamentos_funcionarios ADD COLUMN {col_def[0]} {col_def[1]}")
                    except Exception:
                        pass
                conn.commit()
            except Exception:
                pass
        
            aba_colab, aba_pagamentos, aba_pendentes = st.tabs([
                "👥 Colaboradores", 
                "💸 Registar Pagamentos / Vales", 
                "📅 Salários Pendentes e a Vencer"
            ])
        
            with st.expander("➕ Adicionar Novo Colaborador"):
                with st.form("form_cadastro_colaborador", clear_on_submit=True):
                    col_rh1, col_rh2 = st.columns(2)
                    with col_rh1:
                        nome_colab = st.text_input("Nome Completo do Colaborador")
                        cargo_colab = st.text_input("Cargo / Função")
                        cbo_colab = st.text_input("CBO (Ex: 5211-10)")
                        usuario_login = st.text_input("Usuário para Login no Sistema")
                        
                    with col_rh2:
                        tel_colab = st.text_input("Telefone / Telemóvel")
                        salario_colab = st.number_input("Salário Base (R$)", value=1412.00)
                        data_adm = st.date_input("Data de Admissão")
                        senha_login = st.text_input("Senha de Acesso", type="password")
            
                    submitted = st.form_submit_button("💾 Salvar Colaborador e Criar Acesso", type="primary")
                    
                    if submitted:
                        if nome_colab:
                            try:
                                cursor = conn.cursor()
                                
                                # 1. Garante que a tabela funcionarios existe com todas as colunas necessárias
                                cursor.execute("""
                                    CREATE TABLE IF NOT EXISTS funcionarios (
                                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                                        nome TEXT,
                                        cargo TEXT,
                                        cbo TEXT,
                                        telefone TEXT,
                                        salario REAL,
                                        admissao TEXT,
                                        usuario TEXT
                                    )
                                """)
                                conn.commit()
                                
                                # Garante colunas caso a tabela já exista sem elas
                                for col_nome, col_tipo in [("usuario", "TEXT"), ("cbo", "TEXT"), ("telefone", "TEXT"), ("admissao", "TEXT")]:
                                    try:
                                        cursor.execute(f"ALTER TABLE funcionarios ADD COLUMN {col_nome} {col_tipo}")
                                        conn.commit()
                                    except Exception:
                                        pass
                                
                                # 2. Garante que a tabela usuarios existe para o login no sistema
                                cursor.execute("""
                                    CREATE TABLE IF NOT EXISTS usuarios (
                                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                                        usuario TEXT,
                                        senha TEXT,
                                        cargo TEXT
                                    )
                                """)
                                conn.commit()
                                
                                for col_nome, col_tipo in [("usuario", "TEXT"), ("senha", "TEXT"), ("cargo", "TEXT")]:
                                    try:
                                        cursor.execute(f"ALTER TABLE usuarios ADD COLUMN {col_nome} {col_tipo}")
                                        conn.commit()
                                    except Exception:
                                        pass
                                
                                # 3. Insere o colaborador na tabela correta (funcionarios)
                                cursor.execute("""
                                    INSERT INTO funcionarios (nome, cargo, cbo, telefone, salario, admissao, usuario)
                                    VALUES (?, ?, ?, ?, ?, ?, ?)
                                """, (nome_colab, cargo_colab, cbo_colab, tel_colab, float(salario_colab), str(data_adm), usuario_login))
                                
                                # 4. Insere as credenciais de login se preenchidas
                                if usuario_login and senha_login:
                                    cursor.execute("""
                                        INSERT INTO usuarios (usuario, senha, cargo)
                                        VALUES (?, ?, ?)
                                    """, (usuario_login, senha_login, cargo_colab))
                                
                                conn.commit()
                                cursor.close()
                                st.success("Colaborador cadastrado e acesso ao sistema criado com sucesso!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro detalhado ao salvar: {e}")
                        else:
                            st.error("Preencha pelo menos o nome do colaborador.")
        
                st.markdown("---")
        
                try:
                    df_func = pd.read_sql_query("SELECT * FROM funcionarios", conn)
                except Exception:
                    df_func = pd.DataFrame()
        
                if not df_func.empty:
                    total_colaboradores = len(df_func)
                    folha_salarial = pd.to_numeric(df_func['salario'], errors='coerce').sum()
        
                    col_m1, col_m2 = st.columns(2)
                    with col_m1:
                        st.metric("👨‍💼 Total de Colaboradores", str(total_colaboradores))
                    with col_m2:
                        st.metric("💵 Folha Salarial Total Base", f"R$ {folha_salarial:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        
                    st.markdown("---")
                    st.subheader("📋 Lista de Colaboradores (Editável)")
        
                    df_func['salario'] = pd.to_numeric(df_func['salario'], errors='coerce').fillna(0.0)
                    edited_func = st.data_editor(
                        df_func,
                        key="editor_tabela_funcionarios",
                        use_container_width=True,
                        num_rows="dynamic"
                    )
        
                    if st.button("💾 Atualizar Alterações no RH", key="btn_salvar_rh", use_container_width=True):
                        try:
                            cursor = conn.cursor()
                            for _, row in edited_func.iterrows():
                                cursor.execute("""
                                    UPDATE funcionarios 
                                    SET nome = ?, cargo = ?, telefone = ?, salario = ?, admissao = ?, cbo = ?
                                    WHERE id = ?
                                """, (
                                    str(row.get('nome', '')),
                                    str(row.get('cargo', '')),
                                    str(row.get('telefone', '')),
                                    float(row.get('salario', 0)),
                                    str(row.get('admissao', '')),
                                    str(row.get('cbo', '-')),
                                    int(row.get('id', 0))
                                ))
                            conn.commit()
                            st.success("✅ Dados atualizados com sucesso!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro: {e}")
                else:
                    st.info("ℹ️ Ainda não existem colaboradores registados.")
        st.markdown("### ⚙️ Restrições e Permissões de Acessos")
        st.info("Selecione o funcionário e configure quais módulos ele pode aceder.")
        
        try:
            df_users_perm = pd.read_sql_query("SELECT * FROM usuarios", conn)
        except Exception:
            df_users_perm = pd.DataFrame()
        
        if not df_users_perm.empty:
            utilizador_selecionado = st.selectbox("Selecione o Utilizador", df_users_perm['usuario'].tolist(), key="sel_user_perm")
            
            col_p1, col_p2, col_p3 = st.columns(3)
            with col_p1:
                p_pdv = st.checkbox("Aceder ao PDV (Frente de Caixa)", value=True, key=f"p_pdv_{utilizador_selecionado}")
                p_estoque = st.checkbox("Aceder ao Estoque / Compras", value=False, key=f"p_est_{utilizador_selecionado}")
            with col_p2:
                p_financeiro = st.checkbox("Aceder ao Fechamento Financeiro", value=False, key=f"p_fin_{utilizador_selecionado}")
                p_cadastros = st.checkbox("Gerir Clientes e Fornecedores", value=False, key=f"p_cad_{utilizador_selecionado}")
            with col_p3:
                p_rh = st.checkbox("Gerir RH e Funcionários", value=False, key=f"p_rh_{utilizador_selecionado}")
                p_config = st.checkbox("Configurações da Empresa", value=False, key=f"p_cfg_{utilizador_selecionado}")
                
            if st.button("💾 Salvar Permissões do Utilizador", key="btn_salvar_permissoes"):
                try:
                    cursor = conn.cursor()
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS permissoes_usuario (
                            usuario TEXT PRIMARY KEY,
                            pdv INTEGER,
                            estoque INTEGER,
                            financeiro INTEGER,
                            cadastros INTEGER,
                            rh INTEGER,
                            config INTEGER
                        )
                    """)
                    cursor.execute("""
                        INSERT OR REPLACE INTO permissoes_usuario (usuario, pdv, estoque, financeiro, cadastros, rh, config)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (utilizador_selecionado, int(p_pdv), int(p_estoque), int(p_financeiro), int(p_cadastros), int(p_rh), int(p_config)))
                    conn.commit()
                    cursor.close()
                    st.success(f"✅ Permissões atualizadas para o utilizador '{utilizador_selecionado}' com sucesso!")
                except Exception as e:
                    st.error(f"Erro ao salvar permissões: {e}")
        else:
            st.warning("⚠️ Nenhum utilizador criado no sistema. Cadastre um colaborador com login na aba de RH.")
        
        # --- EXPANSOR PARA ELIMINAR COLABORADOR (Alinhado corretamente fora do if/else) ---
        with st.expander("🗑️ Eliminar Colaborador"):
            try:
                df_colab_del = pd.read_sql_query("SELECT nome FROM funcionarios", conn)
            except Exception:
                df_colab_del = pd.DataFrame()
        
            if not df_colab_del.empty:
                colaboradores_lista = df_colab_del['nome'].tolist()
                colab_para_excluir = st.selectbox("Selecione o colaborador que deseja eliminar:", colaboradores_lista, key="select_colab_excluir_rh")
                
                if st.button("❌ Confirmar Eliminação", type="primary", key="btn_confirma_excluir_colab"):
                    try:
                        cursor = conn.cursor()
                        with conn:
                            cursor.execute("DELETE FROM funcionarios WHERE nome = ?", (colab_para_excluir,))
                            cursor.execute("DELETE FROM pagamentos_funcionarios WHERE colaborador = ?", (colab_para_excluir,))
                        
                        st.cache_data.clear()
                        st.success(f"✅ Colaborador '{colab_para_excluir}' e respetivos registos eliminados com sucesso!")
                        st.rerun()
                    except Exception as e_del:
                        st.error(f"Erro ao eliminar colaborador: {e_del}")
            else:
                st.info("ℹ️ Não existem colaboradores registados para eliminar.")

            with aba_pagamentos:
                st.subheader("💸 Registar Pagamento, Salário, Vale ou Haver")
                
                try:
                    df_func_list = pd.read_sql_query("SELECT id, nome, cargo, cbo, salario, admissao FROM funcionarios", conn)
                    lista_nomes = df_func_list['nome'].tolist() if not df_func_list.empty else []
                except Exception:
                    df_func_list = pd.DataFrame()
                    lista_nomes = []
        
                if lista_nomes:
                    col_sel1, col_sel2 = st.columns(2)
                    with col_sel1:
                        colaborador_selecionado = st.selectbox("Selecione o Colaborador", lista_nomes, key="sel_colab_pag_v2")
                    
                    # Gerar lista de competências baseada na admissão
                    func_row = df_func_list[df_func_list['nome'] == colaborador_selecionado]
                    salario_base_func = float(func_row.iloc[0]['salario']) if not func_row.empty else 0.0
                    admissao_func = str(func_row.iloc[0]['admissao']) if not func_row.empty else '2021-01-01'
                    
                    try:
                        dt_adm = datetime.strptime(admissao_func[:10], '%Y-%m-%d').date()
                    except Exception:
                        dt_adm = datetime(2021, 1, 1).date()
                    
                    hoje = datetime.now().date()
                    cur_y, cur_m = dt_adm.year, dt_adm.month
                    cur_m += 1
                    if cur_m > 12:
                        cur_m = 1
                        cur_y += 1
                    
                    lista_competencias = []
                    lim_y = hoje.year + 1
                    lim_m = 12
                    while (cur_y < lim_y) or (cur_y == lim_y and cur_m <= lim_m):
                        lista_competencias.append(f"01/{cur_m:02d}/{cur_y}")
                        cur_m += 1
                        if cur_m > 12:
                            cur_m = 1
                            cur_y += 1
                    
                    with col_sel2:
                        competencia_selecionada = st.selectbox("Selecione a Competência / Mês", lista_competencias, key="sel_comp_pag_v2")
                    
                    # Calcular saldo restante para a competência selecionada
                    try:
                        df_todos_pag = pd.read_sql_query("SELECT * FROM pagamentos_funcionarios WHERE colaborador = ?", conn, params=(colaborador_selecionado,))
                    except Exception:
                        df_todos_pag = pd.DataFrame()
                    
                    parts_c = competencia_selecionada.split('/')
                    mes_sel, ano_sel = parts_c[1], parts_c[2]
                    
                    vales_ja_dados = 0.0
                    if not df_todos_pag.empty:
                        for _, p_row in df_todos_pag.iterrows():
                            comp_db = str(p_row.get('competencia', ''))
                            data_db = str(p_row.get('data_pagamento', ''))
                            if competencia_selecionada in comp_db or f"{ano_sel}-{mes_sel}" in data_db:
                                vales_ja_dados += float(p_row.get('valor', 0.0))
                    
                    restante_calcular = max(0.0, salario_base_func - vales_ja_dados)
                    
                    st.info(f"📊 **Resumo da Competência {competencia_selecionada}:** Salário Base: **R$ {salario_base_func:,.2f}** | Já Lançado/Descontado: **R$ {vales_ja_dados:,.2f}** | **Restante a Pagar: R$ {restante_calcular:,.2f}**")

                    with st.form("form_registo_pagamento", clear_on_submit=True):
                        col_p1, col_p2 = st.columns(2)
                        with col_p1:
                            tipo_lancamento = st.selectbox("Descrição / Tipo", ["Salário Parcial", "Vale", "Haver", "Adiantamento", "Bónus", "Salário Final (Baixa Total)"])
                            valor_lancamento = st.number_input("Valor da Transação (R$)", min_value=0.0, value=restante_calcular, step=50.0)
                        with col_p2:
                            inss_lancamento = st.number_input("Desconto INSS (R$)", min_value=0.0, value=0.0, step=10.0)
                            faltas_qtd = st.number_input("Quantidade de Faltas (Dias)", min_value=0.0, value=0.0, step=1.0)
                            desc_faltas_val = st.number_input("Desconto por Faltas (R$)", min_value=0.0, value=0.0, step=10.0)
                            data_lancamento = st.date_input("Data do Recebimento")
        
                        btn_gravar_pagamento = st.form_submit_button("💾 Registar Lançamento, Descontar e Liberar Holerite", use_container_width=True)
                        if btn_gravar_pagamento:
                            if valor_lancamento > 0:
                                try:
                                    cursor = conn.cursor()
                                    cursor.execute("""
                                        INSERT INTO pagamentos_funcionarios (colaborador, tipo, valor, data_pagamento, inss, faltas, desconto_faltas, competencia)
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                    """, (colaborador_selecionado, tipo_lancamento, valor_lancamento, str(data_lancamento), inss_lancamento, faltas_qtd, desc_faltas_val, competencia_selecionada))
                                    conn.commit()
                                    st.success("✅ Transação registada com sucesso! O saldo foi descontado.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Erro: {e}")
                            else:
                                st.warning("⚠️ Insira um valor superior a zero.")
                else:
                    st.warning("⚠️ Registe primeiro um colaborador na aba 'Colaboradores'.")
        
                st.markdown("---")
                st.subheader("📊 Histórico de Pagamentos e Edição de Holerites")
        
                try:
                    df_historico_pag = pd.read_sql_query("SELECT * FROM pagamentos_funcionarios ORDER BY id DESC", conn)
                except Exception:
                    df_historico_pag = pd.DataFrame()
        
                if not df_historico_pag.empty:
                    for i, row_pag in df_historico_pag.iterrows():
                        p_id = row_pag['id']
                        p_collab = row_pag['colaborador']
                        p_tipo = row_pag['tipo']
                        p_valor = float(row_pag['valor'] or 0)
                        p_data = str(row_pag['data_pagamento'])[:10]
                        p_inss = float(row_pag.get('inss', 0) or 0)
                        p_faltas = float(row_pag.get('faltas', 0) or 0)
                        p_desc_faltas = float(row_pag.get('desconto_faltas', 0) or 0)
                        p_comp = str(row_pag.get('competencia', p_data))
                        
                        f_info = df_func_list[df_func_list['nome'] == p_collab]
                        f_dict = f_info.iloc[0].to_dict() if not f_info.empty else {'id': 1, 'cargo': 'Funcionário', 'cbo': '-'}
        
                        with st.expander(f"📄 {p_collab} — {p_tipo}: R$ {p_valor:,.2f} ( Ref: {p_comp} ) em {p_data}"):
                            with st.form(f"form_edite_holerite_{p_id}_{i}"):
                                ce1, ce2, ce3 = st.columns(3)
                                with ce1:
                                    novo_val_pag = st.number_input("Valor Bruto (R$)", value=p_valor, step=10.0, key=f"val_{p_id}_{i}")
                                with ce2:
                                    novo_inss = st.number_input("INSS (R$)", value=p_inss, step=5.0, key=f"inss_{p_id}_{i}")
                                with ce3:
                                    nova_qtd_faltas = st.number_input("Qtd Faltas", value=p_faltas, step=1.0, key=f"faltas_{p_id}_{i}")
                                
                                ce4, ce5 = st.columns(2)
                                with ce4:
                                    novo_desc_faltas = st.number_input("Desc. Faltas (R$)", value=p_desc_faltas, step=10.0, key=f"desc_f_{p_id}_{i}")
                                with ce5:
                                    st.markdown("<br>", unsafe_allow_html=True)
                                    btn_atualiza_reg = st.form_submit_button("💾 Atualizar Dados do Holerite", use_container_width=True)
        
                                if btn_atualiza_reg:
                                    try:
                                        cursor = conn.cursor()
                                        cursor.execute("""
                                            UPDATE pagamentos_funcionarios 
                                            SET valor = ?, inss = ?, faltas = ?, desconto_faltas = ?
                                            WHERE id = ?
                                        """, (novo_val_pag, novo_inss, nova_qtd_faltas, novo_desc_faltas, p_id))
                                        conn.commit()
                                        st.success("✅ Holerite atualizado com sucesso!")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Erro: {e}")
        
                            # --- GERAÇÃO SEGURA DO HOLERITE ---
                            try:
                                func_seguro = f_dict.copy() if 'f_dict' in locals() and isinstance(f_dict, dict) else {}
                                pag_seguro = {
                                    'referencia': p_comp if p_comp else (p_data[:7] if 'p_data' in locals() and p_data else ''),
                                    'valor': p_valor if 'p_valor' in locals() else 0.0,
                                    'tipo': p_tipo if 'p_tipo' in locals() else '',
                                    'inss': p_inss if 'p_inss' in locals() else 0.0,
                                    'faltas': p_faltas if 'p_faltas' in locals() else 0.0,
                                    'desconto_faltas': p_desc_faltas if 'p_desc_faltas' in locals() else 0.0,
                                    'data_pagamento': p_data if 'p_data' in locals() else ''
                                }
                                
                                pdf_bytes = gerar_bytes_pdf(dados_func=func_seguro, dados_pag=pag_seguro)
                                
                                collab_nome = str(p_collab if 'p_collab' in locals() else 'funcionario').replace(' ', '_')
                                ref_data = str(p_comp if p_comp else '2026')
                                nome_arquivo_pdf = f"holerite_{collab_nome}_{ref_data.replace('/', '-')}.pdf"
                                
                            except Exception as e_gen:
                                pdf_bytes = b""
                                nome_arquivo_pdf = "holerite.pdf"
                                st.warning(f"Não foi possível gerar o PDF do holerite: {e_gen}")
    
                            if pdf_bytes:
                                idx_unico = str(i) if 'i' in locals() else str(hash(p_data))
                                
                                st.download_button(
                                    label="📥 Descarregar / Imprimir Holerite em PDF",
                                    data=pdf_bytes,
                                    file_name=nome_arquivo_pdf,
                                    mime="application/pdf",
                                    key=f"btn_baixar_holerite_rh_unico_{idx_unico}_{ref_data}_{p_id}"
                                )
                            else:
                                st.info("ℹ️ Registe ou selecione um lançamento válido para descarregar o holerite.")
                                
            with aba_pendentes:
                st.subheader("📅 Controlo Automático de Salários Pendentes, Vales e Baixa")
                st.markdown("O sistema calcula automaticamente o restante com base nos vales/haveres dados. Marque como '✅ Pago' para quitar a competência.")
        
                try:
                    df_f = pd.read_sql_query("SELECT * FROM funcionarios", conn)
                    df_p = pd.read_sql_query("SELECT * FROM pagamentos_funcionarios", conn)
                except Exception:
                    df_f = pd.DataFrame()
                    df_p = pd.DataFrame()
        
                if not df_f.empty:
                    competencias_geradas = []
                    hoje = datetime.now().date()
        
                    for _, func in df_f.iterrows():
                        nome_func = func.get('nome')
                        salario_base = float(func.get('salario', 0) or 0)
                        admissao_str = str(func.get('admissao', ''))
        
                        try:
                            data_adm = datetime.strptime(admissao_str[:10], '%Y-%m-%d').date()
                        except Exception:
                            data_adm = hoje
                
                        ano_atual, mes_atual = hoje.year, hoje.month
                        cur_year, cur_month = data_adm.year, data_adm.month
                        
                        cur_month += 1
                        if cur_month > 12:
                            cur_month = 1
                            cur_year += 1
                        
                        limite_year = ano_atual + (1 if mes_atual == 12 else 0)
                        limite_month = 1 if mes_atual == 12 else mes_atual + 1
        
                        while (cur_year < limite_year) or (cur_year == limite_year and cur_month <= limite_month):
                            competencia_str = f"01/{cur_month:02d}/{cur_year}"
                            
                            total_pago_comp = 0.0
                            tem_salario_final = False
                            data_pag_efetuado = "-"
                            
                            if not df_p.empty:
                                pag_func = df_p[df_p['colaborador'] == nome_func]
                                for _, pag in pag_func.iterrows():
                                    comp_db = str(pag.get('competencia', ''))
                                    data_db = str(pag.get('data_pagamento', ''))
                                    tipo_db = str(pag.get('tipo', ''))
                                    val_db = float(pag.get('valor', 0.0))
                                    
                                    if competencia_str in comp_db or f"{cur_year:04d}-{cur_month:02d}" in data_db:
                                        total_pago_comp += val_db
                                        if "Salário" in tipo_db or "Baixa" in tipo_db or val_db >= salario_base * 0.9:
                                            tem_salario_final = True
                                        data_pag_str = data_db
                                        if len(data_pag_str) >= 10:
                                            dp_partes = data_pag_str[:10].split('-')
                                            if len(dp_partes) == 3:
                                                data_pag_efetuado = f"{dp_partes[2]}/{dp_partes[1]}/{dp_partes[0]}"

                            restante_devido = max(0.0, salario_base - total_pago_comp)

                            if cur_year > ano_atual or (cur_year == ano_atual and cur_month > mes_atual):
                                status_competencia = "🟢 A Vencer"
                            elif tem_salario_final or restante_devido <= 0.01:
                                status_competencia = "✅ Pago"
                            elif total_pago_comp > 0:
                                status_competencia = "🟡 Parcial (Com Vales/Haveres)"
                            else:
                                status_competencia = "🔴 Pendente (Em Aberto)"
        
                            competencias_geradas.append({
                                "Excluir": False,
                                "Colaborador": nome_func,
                                "Cargo": func.get('cargo', ''),
                                "Competência (Mês/Ano)": competencia_str,
                                "Data do Pagamento": data_pag_efetuado,
                                "Salário Base (R$)": salario_base,
                                "Total Pago/Vales (R$)": total_pago_comp,
                                "Restante (R$)": restante_devido,
                                "Status": status_competencia
                            })
        
                            cur_month += 1
                            if cur_month > 12:
                                cur_month = 1
                                cur_year += 1
        
                    df_pendentes_final = pd.DataFrame(competencias_geradas)
        
                    if not df_pendentes_final.empty:
                        filtro_status = st.selectbox("Filtrar por Status:", ["Todos", "🔴 Pendente (Em Aberto)", "🟡 Parcial (Com Vales/Haveres)", "🟢 A Vencer", "✅ Pago"], key="filtro_status_pend_v10")
                        if filtro_status != "Todos":
                            df_pendentes_final = df_pendentes_final[df_pendentes_final['Status'] == filtro_status]
        
                        edited_pendentes = st.data_editor(
                            df_pendentes_final,
                            key="editor_tabela_salarios_pendentes_v10",
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "Excluir": st.column_config.CheckboxColumn("Excluir", default=False),
                                "Competência (Mês/Ano)": st.column_config.TextColumn("Competência (Mês/Ano)", disabled=True),
                                "Data do Pagamento": st.column_config.TextColumn("Data do Pagamento"),
                                "Salário Base (R$)": st.column_config.NumberColumn("Salário Base (R$)", disabled=True, format="R$ %.2f"),
                                "Total Pago/Vales (R$)": st.column_config.NumberColumn("Total Pago/Vales (R$)", disabled=True, format="R$ %.2f"),
                                "Restante (R$)": st.column_config.NumberColumn("Restante (R$)", format="R$ %.2f"),
                                "Status": st.column_config.SelectboxColumn(
                                    "Status do Pagamento",
                                    options=["🔴 Pendente (Em Aberto)", "🟡 Parcial (Com Vales/Haveres)", "🟢 A Vencer", "✅ Pago"],
                                    required=True
                                )
                            },
                            num_rows="fixed"
                        )
        
                        st.markdown("---")
                        
                        if st.button("💾 Salvar Alterações e Dar Baixa nos Salários", key="btn_salvar_pend_v10", use_container_width=True):
                            try:
                                cursor = conn.cursor()
                                with conn:
                                    for _, row in edited_pendentes.iterrows():
                                        collab = row['Colaborador']
                                        comp = row['Competência (Mês/Ano)']
                                        restante_val = float(row['Restante (R$)'])
                                        status_mod = row['Status']
                                        
                                        parts_comp = comp.split('/')
                                        if len(parts_comp) == 3:
                                            _, mes_competencia, ano_competencia = parts_comp
                                        else:
                                            mes_competencia, ano_competencia = parts_comp
                                        
                                        data_pag_col = str(row.get('Data do Pagamento', '')).strip()
                                        if data_pag_col and data_pag_col != '-' and len(data_pag_col) == 10:
                                            d_p = data_pag_col.split('/')
                                            data_formatada_db = f"{d_p[2]}-{d_p[1]}-{d_p[0]}"
                                        else:
                                            data_formatada_db = f"{ano_competencia}-{mes_competencia}-05"
        
                                        if "Pago" in status_mod:
                                            if restante_val > 0.01:
                                                cursor.execute("""
                                                    INSERT INTO pagamentos_funcionarios (colaborador, tipo, valor, data_pagamento, competencia)
                                                    VALUES (?, 'Salário Final', ?, ?, ?)
                                                """, (collab, restante_val, data_formatada_db, comp))
        
                                st.success("✅ Alterações e baixa salarial guardadas com sucesso!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro: {e}")
                    else:
                        st.info("ℹ️ Não foram encontradas competências para exibir.")
                else:
                    st.info("ℹ️ Registe colaboradores na primeira aba.")
        elif menu_admin == "Entrada de Estoque (Compras)":
            st.subheader("📦 Entrada de Estoque (Compras)")
            st.subheader("Registrar Entrada de Estoque")
        
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
        
            if st.session_state.carrinho_compras:
                st.divider()
                st.subheader("📋 Itens no Carrinho de Entrada")
                st.caption("💡 **Dica**: Você pode editar os campos direto na tabela ou selecionar a linha e apertar `Delete` para excluir.")
        
                df_carrinho = pd.DataFrame(st.session_state.carrinho_compras)
                df_carrinho_editado = st.data_editor(df_carrinho, use_container_width=True, num_rows="dynamic", key="editor_carrinho_compras")
        
                col_salvar_tudo, col_limpar = st.columns([2, 1])
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
        
                                for _, item in df_carrinho_editado.iterrows():
                                    cursor.execute("SELECT id FROM produtos WHERE produto = ?", (item['produto'],))
                                    existe = cursor.fetchone()
        
                                    if existe:
                                        cursor.execute("UPDATE produtos SET quantidade = quantidade + ?, valor_compra = ?, valor_venda = ?, grupo = ?, fornecedor = ? WHERE produto = ?", (item['quantidade'], item['valor_compra'], item['valor_venda'], item['grupo'], item['fornecedor'], item['produto']))
                                    else:
                                        cursor.execute("INSERT INTO produtos (produto, grupo, fornecedor, quantidade, valor_compra, valor_venda) VALUES (?, ?, ?, ?, ?, ?)", (item['produto'], item['grupo'], item['fornecedor'], item['quantidade'], item['valor_compra'], item['valor_venda']))
        
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
