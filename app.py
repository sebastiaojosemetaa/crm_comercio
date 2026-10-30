import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
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
            CREATE TABLE IF NOT EXISTS produtos_promocao (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                produto TEXT, quantidade REAL, quantidade_minima REAL DEFAULT 1,
                preco_promocional REAL, grupo TEXT, fornecedor TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS empresas_dispositivos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT UNIQUE, nome_empresa TEXT, cnpj TEXT, ie TEXT,
                fone TEXT, endereco TEXT, ativado INTEGER DEFAULT 0,
                dias_licenca INTEGER DEFAULT 30, limite_dispositivos INTEGER DEFAULT 1
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chaves_pix (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo TEXT, chave TEXT, favorecido TEXT, cidade TEXT, padrao INTEGER DEFAULT 0
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
                id INTEGER PRIMARY KEY AUTOINCREMENT, cliente TEXT, produto TEXT, data TEXT
            )
        """)
        for col in ["fornecedor", "grupo", "quantidade", "valor_venda", "valor_total", "forma_pagamento", "valor_recebido", "troco", "restante", "status", "tipo", "codigo", "codigo_venda", "vendedor"]:
            try: cursor.execute(f"ALTER TABLE vendas ADD COLUMN {col} TEXT")
            except Exception: pass

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
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT, login TEXT UNIQUE, senha TEXT, cargo TEXT
            )
        """)
        conn.commit()
    except Exception:
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

st.sidebar.title("🔑 Acesso ao Sistema")
st.sidebar.radio("Selecione o Perfil:", ["🔒 Administração / Vendedor"], key="perfil_principal_radio")
st.sidebar.markdown("---")

if dispositivo_esta_ativado:
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
                st.success("Login efetuado com sucesso!")
                st.rerun()
            else:
                st.error("❌ Usuário ou senha incorretos.")
else:
    usr_exibicao = "administrador"
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
    # CONFIGURAÇÕES DA EMPRESA (COM ATIVAÇÃO DIRETA)
    # -------------------------------------------------------------
    if menu_admin == "🏢 Configurações da Empresa":
        st.subheader("🏢 Configurações e Dados da Empresa")
        st.markdown("### 🔑 Ativação do Sistema")
        
        if dispositivo_esta_ativado:
            st.success("✅ Este dispositivo está **ATIVADO** e licenciado!")
        else:
            st.warning("⚠️ Insira a chave de ativação para liberar o acesso.")
            chave_digitada = st.text_input("Chave de Ativação:", key="input_chave_config")
            
            if st.button("🔓 Ativar Dispositivo", type="primary"):
                doc_atual = str(reg_emp.get('cnpj', '19417439000142'))
                apenas_digitos = ''.join(filter(str.isdigit, str(doc_atual)))
                chave_limpa = str(chave_digitada).strip().upper()

                sucesso = False
                dias_validade = 30
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
                    st.success("🎉 Dispositivo ativado com sucesso! Recarregando...")
                    st.rerun()
                else:
                    st.error("❌ Chave de ativação inválida.")
    else:
        st.info("ℹ️ Vá na aba **Configurações da Empresa** na barra lateral para inserir sua chave de ativação e liberar todas as telas.")
