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

# --- INICIALIZAÇÃO DE ESTADOS ---
if "dispositivo_ativado" not in st.session_state:
    st.session_state["dispositivo_ativado"] = False

if "dias_licenca" not in st.session_state:
    st.session_state["dias_licenca"] = 30

if 'autenticado' not in st.session_state:
    st.session_state['autenticado'] = False

if 'admin_logged' not in st.session_state:
    st.session_state.admin_logged = False

if 'cliente_autenticado' not in st.session_state:
    st.session_state.cliente_autenticado = None

if 'carrinho_pdv' not in st.session_state:
    st.session_state.carrinho_pdv = []

if "carrinho_cliente" not in st.session_state:
    st.session_state.carrinho_cliente = []

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="CRM Comércio - REY DA CEBOLA", layout="wide", page_icon="🛍️")

# --- CONEXÃO E TABELAS MULTI-EMPRESA ---
def get_connection():
    return sqlite3.connect("crm_comercio.db", check_same_thread=False)

conn = get_connection()

# --- VERIFICAÇÃO DE PERMISSÕES ---
def checar_permissao(usuario, modulo, acao):
    if not usuario:
        return False
    if usuario.lower() == "administrador" or st.session_state.get('cargo_logado') == "Administrador":
        return True
    
    try:
        cursor_p = conn.cursor()
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
        return bool(res and res[0] == 1)
    except Exception:
        return False

# --- FUNÇÕES DE SUPORTE E BANCO ---
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
        
        # Tabela de Produtos
        cursor.execute("CREATE TABLE IF NOT EXISTS produtos (id INTEGER PRIMARY KEY AUTOINCREMENT, produto TEXT)")
        for col in ["fornecedor", "grupo", "preco_compra", "preco_venda", "venda", "quantidade", "estoque", "codigo"]:
            try: cursor.execute(f"ALTER TABLE produtos ADD COLUMN {col} TEXT")
            except Exception: pass

        # Tabela de Clientes
        cursor.execute("CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente TEXT)")
        for col in ["cliente", "nome", "cpf", "doc", "endereco", "email", "fone", "telefone", "cidade", "senha"]:
            try: cursor.execute(f"ALTER TABLE clientes ADD COLUMN {col} TEXT")
            except Exception: pass

        # Tabela de Vendas
        cursor.execute("CREATE TABLE IF NOT EXISTS vendas (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente TEXT, produto TEXT, data TEXT)")
        for col in ["fornecedor", "grupo", "quantidade", "valor_venda", "valor_total", "forma_pagamento", "valor_recebido", "troco", "restante", "status", "tipo", "codigo", "codigo_venda", "vendedor"]:
            try: cursor.execute(f"ALTER TABLE vendas ADD COLUMN {col} TEXT")
            except Exception: pass

        # Tabela de Pedidos
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pedidos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente TEXT, produto TEXT, fornecedor TEXT, grupo TEXT,
                quantidade REAL, valor_unitario REAL, valor_total REAL, status TEXT, data TEXT
            )
        """)

        # Tabela de Funcionários (Garante todas as colunas)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS funcionarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT,
                cargo TEXT,
                salario REAL,
                cbo TEXT,
                telefone TEXT,
                admissao TEXT,
                usuario TEXT
            )
        """)
        for col_f in ["cbo", "telefone", "admissao", "usuario", "cargo", "salario"]:
            try: cursor.execute(f"ALTER TABLE funcionarios ADD COLUMN {col_f} TEXT")
            except Exception: pass

        # Tabela de Pagamentos de Funcionários
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pagamentos_funcionarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                colaborador TEXT,
                tipo TEXT,
                valor REAL,
                data_pagamento TEXT,
                inss REAL,
                faltas REAL,
                desconto_faltas REAL,
                competencia TEXT
            )
        """)

        # Tabela de Usuários / Logins (Garante todas as colunas de permissão)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT,
                login TEXT UNIQUE,
                senha TEXT,
                cargo TEXT,
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
        
        colunas_usuarios = [
            "usuario TEXT", "login TEXT", "senha TEXT", "cargo TEXT",
            "perm_produtos_ver INTEGER DEFAULT 1", "perm_produtos_editar INTEGER DEFAULT 0", "perm_produtos_excluir INTEGER DEFAULT 0",
            "perm_vendas_ver INTEGER DEFAULT 1", "perm_vendas_editar INTEGER DEFAULT 0", "perm_vendas_excluir INTEGER DEFAULT 0",
            "perm_clientes_ver INTEGER DEFAULT 1", "perm_clientes_editar INTEGER DEFAULT 0", "perm_clientes_excluir INTEGER DEFAULT 0",
            "perm_relatorios_ver INTEGER DEFAULT 0"
        ]
        for col_u in colunas_usuarios:
            try: cursor.execute(f"ALTER TABLE usuarios ADD COLUMN {col_u}")
            except Exception: pass

        conn.commit()
    except Exception as e:
        pass

adequar_banco_e_migrar()

# --- DISPOSITIVO E IDENTIFICADOR ÚNICO ---
if "device_id" not in st.query_params:
    st.query_params["device_id"] = str(uuid.uuid4())
device_id = st.query_params["device_id"]

df_emp_dev = carregar_dados(f"SELECT * FROM empresas_dispositivos WHERE device_id = '{device_id}'")
if df_emp_dev.empty:
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO empresas_dispositivos (device_id, nome_empresa, cnpj, ie, fone, endereco)
        VALUES (?, 'REY DA CEBOLA', '19417439000142', '', '(99) 98501-6050', 'RUA CAIPIRA, Nº 174')
    """, (device_id,))
    conn.commit()
    df_emp_dev = carregar_dados(f"SELECT * FROM empresas_dispositivos WHERE device_id = '{device_id}'")

reg_emp = df_emp_dev.iloc[0] if not df_emp_dev.empty else {}

# --- ESTILO VISUAL METÁLICO (FÊNIX STYLE) ---
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
                st.session_state['cargo_logado'] = "Administrador"
                st.success("Login efetuado com sucesso!")
                st.rerun()
            else:
                try:
                    cursor = conn.cursor()
                    cursor.execute("SELECT * FROM usuarios WHERE LOWER(TRIM(login)) = ? AND senha = ?", (usuario_input, senha_input))
                    user_row = cursor.fetchone()
                    cursor.close()
                    if user_row:
                        st.session_state['autenticado'] = True
                        st.session_state['usuario_logado'] = user_row[2] # login column index
                        st.session_state['cargo_logado'] = user_row[4] if len(user_row) > 4 else "Funcionário"
                        st.success("Login efetuado com sucesso!")
                        st.rerun()
                    else:
                        st.error("❌ Usuário ou senha incorretos. Verifique os dados.")
                except Exception as e:
                    st.error(f"Erro ao autenticar: {e}")

else:
    # --- INTERFACE PRINCIPAL APÓS O LOGIN ---
    st.sidebar.write(f"👤 **Utilizador:** `{st.session_state.get('usuario_logado')}`")
    if st.sidebar.button("🚪 Sair do Sistema"):
        st.session_state['autenticado'] = False
        st.rerun()

    menu_admin = st.sidebar.radio(
        "Navegação",
        [
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
        ],
        key="radio_menu_admin_opcoes"
    )

    # -------------------------------------------------------------
    # 1. MÓDULO PDV — FRENTE DE CAIXA (ALINHADO LADO A LADO)
    # -------------------------------------------------------------
    if menu_admin == "🛒 PDV — Frente de Caixa":
        st.subheader("🛒 PDV — Frente de Caixa — REY DA CEBOLA")
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
                val_v = float(p_row.get('valor_venda', 0.0) or p_row.get('venda', 0.0) or 0.0)
                return val_v, str(p_row.get('fornecedor', '')), str(p_row.get('grupo', ''))
            return 0.0, "", ""

        if not df_caixa_aberto.empty:
            st.success("🟢 Caixa Aberto e Operacional")
        else:
            st.warning("⚠️ Atenção: Não há nenhum caixa aberto no momento.")

        col_esq, col_dir = st.columns([1, 1], gap="medium")

        # --- LADO ESQUERDO: DADOS DO ITEM ---
        with col_esq:
            st.markdown("### 📦 Dados do Item")
            prod_selecionado = st.selectbox("Selecione o Produto", [""] + lista_produtos_pdv, key="sel_prod_pdv_alin")
            val_venda_sug, forn_sug, grupo_sug = obter_dados_produto(prod_selecionado) if prod_selecionado else (0.0, "", "")

            col_sub1, col_sub2 = st.columns(2)
            with col_sub1:
                qtd_venda = st.number_input("Qtd", min_value=0.01, value=1.0, step=1.0, key="qtd_prod_pdv_alin")
            with col_sub2:
                preco_unit_venda = st.number_input("Preço Unit. (R$)", min_value=0.0, value=val_venda_sug, format="%.2f", key="preco_unit_pdv_alin")

            subtotal_item = qtd_venda * preco_unit_venda
            st.markdown(f"#### SUBTOTAL: **R$ {subtotal_item:,.2f}**")

            if st.button("➕ [ Enter ] Incluir Produto", type="primary", use_container_width=True, key="btn_inc_prod_alin"):
                if not prod_selecionado:
                    st.error("Selecione um produto antes de incluir.")
                else:
                    st.session_state.carrinho_pdv.append({
                        "produto": prod_selecionado,
                        "quantidade": qtd_venda,
                        "valor_unitario": preco_unit_venda,
                        "valor_total": subtotal_item,
                        "fornecedor": forn_sug,
                        "grupo": grupo_sug
                    })
                    st.success(f"✅ '{prod_selecionado}' adicionado!")
                    st.rerun()

        # --- LADO DIREITO: CARRINHO E FINALIZAÇÃO ---
        with col_dir:
            total_geral_carrinho = sum(item['valor_total'] for item in st.session_state.carrinho_pdv) if st.session_state.carrinho_pdv else 0.0
            st.markdown(f"### 🛒 Carrinho — Total: R$ {total_geral_carrinho:,.2f}")

            if st.session_state.carrinho_pdv:
                df_carrinho = pd.DataFrame(st.session_state.carrinho_pdv)
                df_exibicao = df_carrinho[['produto', 'quantidade', 'valor_unitario', 'valor_total']].copy()
                df_exibicao.columns = ['Produto', 'Qtd', 'Preço Unit.', 'Total']
                
                st.dataframe(df_exibicao, use_container_width=True, height=220)

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
                            vendedor_atual = st.session_state.get('usuario_logado', 'administrador')

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
                st.info("O carrinho está vazio.")

    # -------------------------------------------------------------
    # 2. MÓDULO FECHAMENTO & FINANCEIRO
    # -------------------------------------------------------------
    elif menu_admin == "📊 Fechamento & Financeiro":
        st.subheader("📊 Fechamento & Financeiro")
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

    # -------------------------------------------------------------
    # 3. MÓDULO REGISTRAR VENDA
    # -------------------------------------------------------------
    elif menu_admin == "🛒 Registrar Venda":
        st.subheader("🛒 Registrar Venda / Pedido")
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

        col1, col2 = st.columns(2)
        with col1:
            prod_compra = st.selectbox("Selecione o Produto", produtos_opt, key="prod_compra_sel")
            forn_compra = st.selectbox("Fornecedor", fornecedores_opt, key="forn_compra_sel")
            qtd_compra = st.number_input("Quantidade", min_value=0.01, value=1.0, key="qtd_compra_num")
        with col2:
            grp_compra = st.selectbox("Grupo", grupos_opt, key="grp_compra_sel")
            pr_compra = st.number_input("Preço Compra Unitário (R$)", min_value=0.0, key="pr_compra_num")
            pr_venda = st.number_input("Preço Venda Unitário (R$)", min_value=0.0, key="pr_venda_num")

        if st.button("🛒 Adicionar ao Carrinho de Compras", type="primary"):
            st.session_state.carrinho_compras.append({
                "produto": prod_compra, "grupo": grp_compra, "fornecedor": forn_compra,
                "quantidade": qtd_compra, "valor_compra": pr_compra, "valor_venda": pr_venda
            })
            st.success(f"'{prod_compra}' adicionado!")
            st.rerun()

        if st.session_state.carrinho_compras:
            st.dataframe(pd.DataFrame(st.session_state.carrinho_compras), use_container_width=True)
            if st.button("💾 Finalizar Todas as Entradas"):
                cursor = conn.cursor()
                for item in st.session_state.carrinho_compras:
                    cursor.execute("SELECT id FROM produtos WHERE produto = ?", (item['produto'],))
                    if cursor.fetchone():
                        cursor.execute("UPDATE produtos SET quantidade = quantidade + ?, valor_compra = ?, valor_venda = ? WHERE produto = ?",
                                       (item['quantidade'], item['valor_compra'], item['valor_venda'], item['produto']))
                    else:
                        cursor.execute("INSERT INTO produtos (produto, grupo, fornecedor, quantidade, valor_compra, valor_venda) VALUES (?, ?, ?, ?, ?, ?)",
                                       (item['produto'], item['grupo'], item['fornecedor'], item['quantidade'], item['valor_compra'], item['valor_venda']))
                conn.commit()
                st.session_state.carrinho_compras = []
                st.success("✅ Entrada registrada no banco de dados com sucesso!")
                st.rerun()

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
    # 6. MÓDULO RH
    # -------------------------------------------------------------
    elif "RH" in menu_admin or "Recursos Humanos" in menu_admin:
        st.subheader("👥 Gestão de Recursos Humanos (RH)")
        aba_colab, aba_pag = st.tabs(["👥 Colaboradores", "💸 Registar Pagamentos / Vales"])

        with aba_colab:
            with st.form("form_cad_func"):
                n_func = st.text_input("Nome Completo")
                c_func = st.text_input("Cargo")
                s_func = st.number_input("Salário Base (R$)", value=1412.00)
                if st.form_submit_button("Salvar Colaborador"):
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO funcionarios (nome, cargo, salario) VALUES (?, ?, ?)", (n_func, c_func, s_func))
                    conn.commit()
                    st.success("Colaborador cadastrado!")
                    st.rerun()

            st.dataframe(carregar_dados("SELECT * FROM funcionarios"), use_container_width=True)

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
    # 7. GESTÃO DE UTILIZADORES E LOGINS (NOVO)
    # -------------------------------------------------------------
    elif menu_admin == "🔐 Gestão de Utilizadores e Logins":
        st.subheader("🔐 Gestão de Logins e Permissões de Funcionários")
        
        with st.form("form_cad_usuario"):
            st.markdown("### Cadastrar Novo Utilizador / Funcionário")
            col_u1, col_u2 = st.columns(2)
            with col_u1:
                nome_usuario = st.text_input("Nome Completo do Funcionário")
                login_usuario = st.text_input("Login de Acesso (ex: joao.silva)")
            with col_u2:
                senha_usuario = st.text_input("Senha de Acesso", type="password")
                cargo_usuario = st.selectbox("Cargo / Nível", ["Vendedor", "Caixa", "Gerente", "Administrador"])

            st.markdown("#### Permissões do Sistema")
            p_prod_ver = st.checkbox("Ver Produtos", value=True)
            p_prod_ed = st.checkbox("Editar Produtos")
            p_vend_ver = st.checkbox("Ver Vendas", value=True)
            p_vend_ed = st.checkbox("Realizar Vendas", value=True)
            p_cli_ver = st.checkbox("Ver Clientes", value=True)
            p_rel_ver = st.checkbox("Ver Relatórios")

            if st.form_submit_button("💾 Salvar Utilizador / Login", type="primary"):
                if not login_usuario.strip() or not senha_usuario.strip():
                    st.error("Preencha o login e a senha.")
                else:
                    try:
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT INTO usuarios (usuario, login, senha, cargo, perm_produtos_ver, perm_produtos_editar, perm_vendas_ver, perm_vendas_editar, perm_clientes_ver, perm_relatorios_ver)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            nome_usuario, login_usuario.strip().lower(), senha_usuario, cargo_usuario,
                            1 if p_prod_ver else 0, 1 if p_prod_ed else 0,
                            1 if p_vend_ver else 0, 1 if p_vend_ed else 0,
                            1 if p_cli_ver else 0, 1 if p_rel_ver else 0
                        ))
                        conn.commit()
                        st.success(f"✅ Utilizador '{login_usuario}' criado com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar utilizador (talvez o login já exista): {e}")

        st.markdown("---")
        st.markdown("### 📋 Utilizadores Cadastrados")
        df_usuarios = carregar_dados("SELECT id, usuario, login, cargo FROM usuarios")
        if not df_usuarios.empty:
            st.dataframe(df_usuarios, use_container_width=True)
        else:
            st.info("Nenhum funcionário cadastrado além do administrador padrão.")

    # -------------------------------------------------------------
    # 8. BACKUP
    # -------------------------------------------------------------
    elif menu_admin == "💾 Backup e Restauração":
        st.subheader("💾 Central de Backup e Restauração")
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
        except Exception:
            st.warning("Banco de dados ainda não localizado.")

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
    # 10. ESTOQUE
    # -------------------------------------------------------------
    elif menu_admin == "📦 Estoque de Produtos":
        st.subheader("📦 Estoque de Produtos e Preços")
        df_prods = carregar_dados("SELECT * FROM produtos")
        if not df_prods.empty:
            st.data_editor(df_prods, use_container_width=True, key="editor_est_prods")
        else:
            st.info("Nenhum produto cadastrado no estoque.")

    # -------------------------------------------------------------
    # 11. CONFIGURAÇÕES
    # -------------------------------------------------------------
    elif menu_admin == "🏢 Configurações da Empresa":
        st.subheader("🏢 Configurações e Dados da Empresa")

        st.markdown("### 🔑 Ativação de Licença do Dispositivo")
        if st.session_state.get('dispositivo_ativado', False):
            dias_val = st.session_state.get('dias_licenca', 30)
            st.success(f"✅ Dispositivo Ativado! Licença válida por {dias_val} dias.")
            if st.button("🔄 Inserir Nova Chave / Renovar"):
                st.session_state['dispositivo_ativado'] = False
                st.rerun()
        else:
            st.warning("⚠️ Insira a chave de ativação correspondente ao seu CNPJ/CPF para liberar o sistema.")
            doc_atual = str(reg_emp.get('cnpj', '19417439000142'))
            st.info(f"Empresa Atual (CNPJ/CPF): `{doc_atual}`")

            chave_digitada = st.text_input("Chave de Ativação:", key="input_chave_ativacao_config")

            if st.button("🔓 Ativar Este Dispositivo", type="primary", key="btn_ativar_dispositivo_config"):
                apenas_digitos = ''.join(filter(str.isdigit, str(doc_atual)))
                chave_limpa = str(chave_digitada).strip().upper()

                sucesso = False
                dias_validade = 0

                for sufixo, dias in [("TESTE", 7), ("MENSAL", 30), ("ANUAL", 365)]:
                    hash_hex = hashlib.md5((apenas_digitos + "REY_CEBOLA_2026" + sufixo).encode()).hexdigest().upper()
                    chave_esperada = f"CRM-{sufixo}-{hash_hex[:4]}-{hash_hex[4:8]}-{hash_hex[8:12]}"

                    if chave_limpa == chave_esperada:
                        sucesso = True
                        dias_validade = dias
                        break

                if sucesso:
                    st.session_state['dispositivo_ativado'] = True
                    st.session_state['dias_licenca'] = dias_validade
                    st.success(f"🎉 Dispositivo ativado com sucesso! Validade: {dias_validade} dias.")
                    st.rerun()
                else:
                    st.error("❌ Chave inválida para este CNPJ/CPF. Verifique os dados inseridos.")

        st.markdown("---")
        with st.form("form_cfg_emp"):
            st.markdown("### 📝 Dados Gerais da Empresa")
            nome_emp = st.text_input("Razão Social / Nome Fantasia", value=str(reg_emp.get('nome_empresa', 'REY DA CEBOLA')))
            cnpj_emp = st.text_input("CNPJ ou CPF", value=str(reg_emp.get('cnpj', '19417439000142')))
            tel_emp = st.text_input("Telefone de Contato", value=str(reg_emp.get('fone', '(99) 98501-6050')))
            end_emp = st.text_input("Endereço Completo", value=str(reg_emp.get('endereco', 'RUA CAIPIRA, Nº 174')))
            
            if st.form_submit_button("💾 Salvar Configurações", type="primary"):
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO empresas_dispositivos (device_id, nome_empresa, cnpj, fone, endereco)
                    VALUES (?, ?, ?, ?, ?)
                """, (device_id, nome_emp, cnpj_emp, tel_emp, end_emp))
                conn.commit()
                st.success("✅ Dados atualizados com sucesso!")
                st.rerun()
