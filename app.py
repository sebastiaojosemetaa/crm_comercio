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
        cursor.execute("CREATE TABLE IF NOT EXISTS produtos (id INTEGER PRIMARY KEY AUTOINCREMENT, produto TEXT)")
        for col in ["fornecedor", "grupo", "preco_compra", "preco_venda", "venda", "quantidade", "estoque", "codigo"]:
            try: cursor.execute(f"ALTER TABLE produtos ADD COLUMN {col} TEXT")
            except Exception: pass

        cursor.execute("CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente TEXT)")
        for col in ["cliente", "nome", "cpf", "doc", "endereco", "email", "fone", "telefone", "cidade", "senha"]:
            try: cursor.execute(f"ALTER TABLE clientes ADD COLUMN {col} TEXT")
            except Exception: pass

        cursor.execute("CREATE TABLE IF NOT EXISTS vendas (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente TEXT, produto TEXT, data TEXT)")
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
            CREATE TABLE IF NOT EXISTS empresas_dispositivos (
                id INTEGER PRIMARY KEY AUTOINCREMENT, device_id TEXT UNIQUE,
                nome_empresa TEXT, cnpj TEXT, ie TEXT, fone TEXT, endereco TEXT
            )
        """)
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
                    cursor.execute("SELECT * FROM usuarios WHERE LOWER(TRIM(usuario)) = ? AND senha = ?", (usuario_input, senha_input))
                    user_row = cursor.fetchone()
                    cursor.close()
                    if user_row:
                        st.session_state['autenticado'] = True
                        st.session_state['usuario_logado'] = user_row[1]
                        st.session_state['cargo_logado'] = user_row[3] if len(user_row) > 3 else "Funcionário"
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
            "💾 Backup e Restauração",
            "💸 Contas a Receber",
            "📦 Estoque de Produtos",
            "🏢 Configurações da Empresa"
        ],
        key="radio_menu_admin_opcoes"
    )

    # -------------------------------------------------------------
    # 1. MÓDULO PDV — FRENTE DE CAIXA
    # -------------------------------------------------------------
    if menu_admin == "🛒 PDV — Frente de Caixa":
            # CSS para compactar e estilizar os botões de atalho no rodapé
            st.markdown("""
            <style>
                .block-container { padding-top: 1rem !important; padding-bottom: 0rem !important; }
                div[data-testid="stVerticalBlock"] > div { padding: 4px 8px !important; margin-bottom: 0px !important; }
                .stMarkdown { margin-bottom: -10px !important; }
                div[data-baseweb="input"] { min-height: 35px !important; }
                h3, h4 { margin-top: 0px !important; margin-bottom: 5px !important; font-size: 16px !important; }
                
                /* Estilo da barra de atalhos inferior */
                .barra-atalhos {
                    background-color: #2b2b2b;
                    color: #ffffff;
                    padding: 8px 15px;
                    border-radius: 8px;
                    border: 2px solid #555555;
                    margin-top: 15px;
                    font-family: monospace;
                    font-size: 13px;
                    text-align: center;
                }
                .atalho-item {
                    color: #00ffcc;
                    font-weight: bold;
                }
            </style>
            """, unsafe_allow_html=True)
        
            st.markdown("### 🛒 PDV — Frente de Caixa — REY DA CEBOLA")
            
            # --- VERIFICAÇÃO DE CAIXA ABERTO ---
            df_caixa_aberto = carregar_dados("SELECT * FROM caixa_sessoes WHERE status = 'ABERTO'")
            if df_caixa_aberto.empty:
                st.warning("⚠️ Atenção: Não há nenhum caixa aberto no momento.")
        
            # --- CARREGAMENTO DE DADOS ---
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
        
            # --- BARRA DE CÓDIGO DE BARRAS NO TOPO ---
            col_cb1, col_cb2 = st.columns([4.5, 1])
            with col_cb1:
                cod_barras_lido = st.text_input(
                    "Entre com o Código ou Código de barras:", 
                    key="input_cb_pdv", 
                    placeholder="Passe o leitor ou digite o código...",
                    label_visibility="collapsed"
                )
            with col_cb2:
                st.button("VERSÃO COMPLETA", type="primary", use_container_width=True)
        
            # FILTRO AUTOMÁTICO DO LEITOR
            produtos_para_exibir = produtos_opt
            if cod_barras_lido.strip() and not df_p.empty:
                termo_cb = cod_barras_lido.strip().lower()
                if 'codigo_barras' not in df_p.columns:
                    df_p['codigo_barras'] = ''
                    
                df_cb_filtrado = df_p[
                    (df_p['codigo_barras'].astype(str).str.lower().str.contains(termo_cb)) | 
                    (df_p['id'].astype(str).str.lower() == termo_cb) | 
                    (df_p[col_nome_p].astype(str).str.lower().str.contains(termo_cb))
                ]
                if not df_cb_filtrado.empty:
                    produtos_para_exibir = [
                        f"{r[col_nome_p]} — R$ {float(r.get('preco_venda', r.get('venda', r.get('valor_venda', 0))) or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                        for _, r in df_cb_filtrado.iterrows()
                    ]
        
            cliente_pdv = clientes_opt[0]
        
            # --- LAYOUT PRINCIPAL EM 2 COLUNAS ---
            col_pdv_esq, col_pdv_dir = st.columns([1, 1.3], gap="small")
        
            # =========================================================
            # COLUNA ESQUERDA
            # =========================================================
            with col_pdv_esq:
                st.markdown("#### 📦 Dados do Item")
                prod_item = st.selectbox("Produto", produtos_para_exibir, key="pdv_select_produto", label_visibility="collapsed")
                
                preco_sugerido = 0.0
                forn_sugerido = fornecedores_opt[0]
                grupo_sugerido = grupos_opt[0]
        
                if not df_p.empty:
                    df_p['nome_limpo'] = df_p[col_nome_p].astype(str).str.strip().str.upper()
                    target_nome = str(prod_item).split(" — R$")[0].strip().upper()
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
        
                idx_f = fornecedores_opt.index(forn_sugerido) if fornecedores_opt and forn_sugerido in fornecedores_opt else 0
                idx_g = grupos_opt.index(grupo_sugerido) if grupos_opt and grupo_sugerido in grupos_opt else 0
                forn_item = fornecedores_opt[idx_f]
                grupo_item = grupos_opt[idx_g]
        
                col_s1, col_s2 = st.columns(2)
                with col_s1:
                    qtd_item = st.number_input("Qtd", min_value=0.1, step=1.0, value=1.0, key="pdv_qtd")
                with col_s2:
                    v_unit_item = st.number_input("Preço Unit. (R$)", min_value=0.0, step=0.01, value=float(preco_sugerido), key=f"vunit_{prod_item}")
        
                valor_total_item = qtd_item * v_unit_item
                
                st.markdown(f"""
                <div style="background-color: #ffffff; padding: 6px; border-radius: 6px; border: 2px solid #888888; text-align: center; margin-top: 5px;">
                    <span style="color: #444444; font-size: 11px; font-weight: bold;">SUBTOTAL</span><br>
                    <span style="color: #000000; font-size: 20px; font-weight: bold;">R$ {valor_total_item:,.2f}</span>
                </div>
                """.replace(",", "X").replace(".", ",").replace("X", "."), unsafe_allow_html=True)
        
                if st.button("➕ [ Enter ] Incluir Produto", type="primary", use_container_width=True):
                    st.session_state.carrinho_pdv.append({
                        "produto": str(prod_item).split(" — R$")[0],
                        "fornecedor": forn_item,
                        "grupo": grupo_item,
                        "quantidade": qtd_item,
                        "valor_venda": v_unit_item,
                        "valor_total": valor_total_item
                    })
                    st.rerun()
        
            # =========================================================
            # COLUNA DIREITA: CARRINHO E FINALIZAÇÃO
            # =========================================================
            with col_pdv_dir:
                st.markdown("#### 📋 Carrinho")
                if len(st.session_state.carrinho_pdv) > 0:
                    df_carrinho = pd.DataFrame(st.session_state.carrinho_pdv)
                    altura_dinamica = 38 + (len(df_carrinho) * 35)
                    st.dataframe(
                        df_carrinho[['produto', 'quantidade', 'valor_venda', 'valor_total']], 
                        use_container_width=True, 
                        hide_index=True, 
                        height=altura_dinamica
                    )
                    total_geral_carrinho = df_carrinho['valor_total'].sum()
                else:
                    st.info("Carrinho vazio.")
                    total_geral_carrinho = 0.0
        
                col_pag1, col_pag2 = st.columns(2)
                with col_pag1:
                    f_pag = st.selectbox("Forma Pagto", ["Dinheiro", "Pix", "Cartão de Crédito", "Cartão de Débito", "Fiado / Prazo"], key="pdv_forma_pagto")
                with col_pag2:
                    v_rec = st.number_input("Valor Rec. (R$)", min_value=0.0, step=1.0, value=float(total_geral_carrinho), key="pdv_val_rec")
                
                troco = v_rec - total_geral_carrinho if v_rec > total_geral_carrinho else 0.0
        
                col_t1, col_t2 = st.columns(2)
                with col_t1:
                    st.markdown(f"""
                    <div style="background-color: #ffffff; padding: 6px; border-radius: 6px; border: 2px solid #28a745; text-align: center;">
                        <span style="color: #28a745; font-size: 11px; font-weight: bold;">TOTAL</span><br>
                        <span style="color: #000000; font-size: 20px; font-weight: bold;">R$ {total_geral_carrinho:,.2f}</span>
                    </div>
                    """.replace(",", "X").replace(".", ",").replace("X", "."), unsafe_allow_html=True)
                with col_t2:
                    st.markdown(f"""
                    <div style="background-color: #ffffff; padding: 6px; border-radius: 6px; border: 2px solid #17a2b8; text-align: center;">
                        <span style="color: #17a2b8; font-size: 11px; font-weight: bold;">TROCO</span><br>
                        <span style="color: #000000; font-size: 20px; font-weight: bold;">R$ {troco:,.2f}</span>
                    </div>
                    """.replace(",", "X").replace(".", ",").replace("X", "."), unsafe_allow_html=True)
        
                if st.button("🟢 Finalizar Venda [ Alt + V ]", type="primary", use_container_width=True):
                    if not df_caixa_aberto.empty and len(st.session_state.carrinho_pdv) > 0:
                        cursor = conn.cursor()
                        sessao_id = int(df_caixa_aberto.iloc[0]['id'])
                        data_venda = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
                        for item in st.session_state.carrinho_pdv:
                            cursor.execute("""
                                INSERT INTO vendas (cliente, produto, fornecedor, grupo, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, status, tipo, data)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                cliente_pdv, item['produto'], item['fornecedor'], item['grupo'],
                                item['quantidade'], item['valor_venda'], item['valor_total'],
                                f_pag, v_rec, 'Concluído', 'VENDA', data_venda
                            ))
        
                        cursor.execute("""
                            INSERT INTO caixa_movimentacoes (sessao_id, tipo, valor, descricao, data) 
                            VALUES (?, ?, ?, ?, ?)
                        """, (
                            sessao_id, "VENDA", float(total_geral_carrinho), f"Venda PDV - Cliente: {cliente_pdv}", data_venda
                        ))
                        
                        conn.commit()
                        st.session_state.carrinho_pdv = []
                        st.success(f"Venda concluída! Troco: R$ {max(0.0, troco):.2f}")
                        st.rerun()
                    else:
                        st.error("Verifique se o caixa está aberto e se há itens no carrinho.")
        
                # --- BARRA DE ATALHOS NO RODAPÉ (100% BRANCO FORÇADO) ---
                st.markdown("""
                <div style="background-color: #0d1b2a; padding: 8px; border-radius: 6px; text-align: center; font-family: monospace; font-size: 14px; font-weight: bold; margin-top: 4px;">
                    <span style="color: #ffffff !important; -webkit-text-fill-color: #ffffff;">&#91; Enter &#93; Incluir &nbsp;|&nbsp; &#91; Alt + C &#93; Limpar &nbsp;|&nbsp; &#91; Alt + V &#93; Finalizar</span>
                </div>
                """, unsafe_allow_html=True)
        
            # =========================================================
            # ATALHOS REALMENTE FUNCIONAIS (SEM CONFLITO COM O WINDOWS)
            # =========================================================
            st.components.v1.html("""
            <script>
            const doc = window.parent.document;
            doc.addEventListener('keydown', function(e) {
                // Alt + V (Finalizar Venda)
                if (e.altKey && (e.key === 'v' || e.key === 'V')) {
                    e.preventDefault();
                    const btns = doc.querySelectorAll('button');
                    btns.forEach(b => { if (b.innerText.includes('Finalizar Venda')) b.click(); });
                }
                // Alt + C ou Delete (Limpar Carrinho)
                if (e.altKey && (e.key === 'c' || e.key === 'C')) {
                    e.preventDefault();
                    const btns = doc.querySelectorAll('button');
                    btns.forEach(b => { if (b.innerText.includes('Limpar Carrinho')) b.click(); });
                }
            });
            </script>
            """, height=0)

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
    # 5. MÓDULO CADASTROS (CLIENTES / FORNECEDORES / GRUPOS)
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
    # 7. MÓDULO BACKUP E RESTAURAÇÃO
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
    # 8. MÓDULO CONTAS A RECEBER
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
    # 9. MÓDULO ESTOQUE DE PRODUTOS
    # -------------------------------------------------------------
    elif menu_admin == "📦 Estoque de Produtos":
        st.subheader("📦 Estoque de Produtos e Preços")
        df_prods = carregar_dados("SELECT * FROM produtos")
        if not df_prods.empty:
            st.data_editor(df_prods, use_container_width=True, key="editor_est_prods")
        else:
            st.info("Nenhum produto cadastrado no estoque.")

    # -------------------------------------------------------------
    # 10. MÓDULO CONFIGURAÇÕES DA EMPRESA & ATIVAÇÃO DE CHAVE
    # -------------------------------------------------------------
    elif menu_admin == "🏢 Configurações da Empresa":
        st.subheader("🏢 Configurações e Dados da Empresa")

        # === CAMPO DE ATIVAÇÃO DE LICENÇA ===
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
