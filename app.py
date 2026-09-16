import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

import io

from datetime import datetime, timedelta

def gerar_pdf_tabela_pedidos(df_dados, cliente_nome="Geral"):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=15, bottomMargin=30)
    story = []

    styles = getSampleStyleSheet()

    # Estilos com leading ajustado para evitar sobreposição de linhas
    style_empresa = ParagraphStyle(
        'Empresa', 
        parent=styles['Normal'], 
        fontName='Helvetica-Bold', 
        fontSize=16, 
        leading=20, 
        alignment=1, 
        textColor=colors.HexColor("#0f2a4a"),
        spaceAfter=4
    )
    style_sub = ParagraphStyle(
        'Sub', 
        parent=styles['Normal'], 
        fontName='Helvetica', 
        fontSize=9, 
        leading=12, 
        alignment=1,
        spaceAfter=10
    )
    style_titulo = ParagraphStyle(
        'Titulo', 
        parent=styles['Normal'], 
        fontName='Helvetica-Bold', 
        fontSize=12, 
        leading=15, 
        alignment=1, 
        textColor=colors.HexColor("#0f2a4a"), 
        spaceAfter=4
    )
    style_info = ParagraphStyle(
        'Info', 
        parent=styles['Normal'], 
        fontName='Helvetica', 
        fontSize=9, 
        leading=12, 
        alignment=1, 
        spaceAfter=15
    )

    # Cabeçalho da Empresa
    story.append(Paragraph("REY DA CEBOLA", style_empresa))
    story.append(Paragraph("CNPJ: 194.174.39/000-42 INSC.EST.: 12.426725-4<br/>CONTATO: (99) 98814-9722 OU (99) 98414-3943", style_sub))

    # Ajuste do Horário Oficial do Brasil (UTC -3)
    data_atual = (datetime.utcnow() - timedelta(hours=3)).strftime('%Y-%m-%d %H:%M:%S')

    # Validação do título
    if cliente_nome != "Todos" and cliente_nome != "Geral" and cliente_nome != "":
        story.append(Paragraph("Relatório de Pedidos / Orçamentos", style_titulo))
        story.append(Paragraph(f"<b>Cliente:</b> {cliente_nome} | <b>Gerado em:</b> {data_atual}", style_info))
    else:
        story.append(Paragraph("Relatório de Pedidos / Orçamentos - Geral", style_titulo))
        story.append(Paragraph(f"<b>Gerado em:</b> {data_atual}", style_info))

    # Tratamento dos dados
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

    # Montagem da tabela
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
# 1. CONFIGURAÇÃO E CONEXÃO COM O BANCO DE DADOS
# -----------------------------------------------------------------------------
st.set_page_config(page_title="CRM Comércio - Rey da Cebola", layout="wide")

def get_connection():
    return sqlite3.connect("crm_comercio.db", check_same_thread=False)

conn = get_connection()

# Adicione este bloco aqui:
try:
    cursor = conn.cursor()
    cursor.execute("ALTER TABLE vendas ADD COLUMN status TEXT DEFAULT 'Pendente'")
    conn.commit()
except Exception:
    pass

def adequar_banco_e_migrar():
    cursor = conn.cursor()
    
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
            valor_recebido TEXT,
            tipo TEXT DEFAULT 'PEDIDO',
            codigo TEXT DEFAULT 'PED',
            data TEXT
        )
    """)
    cursor.execute("PRAGMA table_info(vendas)")
    colunas_vendas = [col[1] for col in cursor.fetchall()]

    if 'forma_pagamento' not in colunas_vendas:
        try:
            cursor.execute("ALTER TABLE vendas ADD COLUMN forma_pagamento TEXT")
        except:
            pass

    if 'valor_recebido' not in colunas_vendas:
        try:
            cursor.execute("ALTER TABLE vendas ADD COLUMN valor_recebido TEXT")
        except:
            pass

    if 'tipo' not in colunas_vendas:
        try:
            cursor.execute("ALTER TABLE vendas ADD COLUMN tipo TEXT DEFAULT 'PEDIDO'")
        except:
            pass

    if 'codigo' not in colunas_vendas:
        try:
            cursor.execute("ALTER TABLE vendas ADD COLUMN codigo TEXT DEFAULT 'PED'")
        except:
            pass

    if 'data' not in colunas_vendas:
        try:
            cursor.execute("ALTER TABLE vendas ADD COLUMN data TEXT")
        except:
            pass
            
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE,
            produto TEXT,
            quantidade REAL DEFAULT 0,
            fornecedor TEXT,
            grupo TEXT,
            valor_compra REAL,
            valor_venda REAL,
            estoque_atual REAL
        )
    """)
    cursor.execute("PRAGMA table_info(produtos)")
    colunas_produtos = [col[1] for col in cursor.fetchall()]

    for col_n, col_t in [('fornecedor', 'TEXT'), ('grupo', 'TEXT'), ('valor_compra', 'REAL'), ('valor_venda', 'REAL'), ('estoque_atual', 'REAL'), ('quantidade', 'REAL'), ('produto', 'TEXT')]:
        if col_n not in colunas_produtos:
            try:
                cursor.execute(f"ALTER TABLE produtos ADD COLUMN {col_n} {col_t}")
            except:
                pass

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE,
            telefone TEXT,
            doc TEXT,
            endereco TEXT,
            cidade TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fornecedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fornecedor TEXT UNIQUE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS grupos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grupo TEXT UNIQUE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS compras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            produto TEXT,
            fornecedor TEXT,
            grupo TEXT,
            quantidade REAL,
            valor_custo REAL,
            valor_total REAL,
            data TEXT
        )
    """)
    
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

adequar_banco_e_migrar()

def carregar_dados(query):
    try:
        return pd.read_sql_query(query, conn)
    except Exception:
        return pd.DataFrame()

def carregar_coluna(tabela, coluna):
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({tabela})")
    cols = [col[1] for col in cursor.fetchall()]
    col_alvo = coluna if coluna in cols else (cols[1] if len(cols) > 1 else coluna)
    
    df = carregar_dados(f"SELECT DISTINCT TRIM({col_alvo}) as {col_alvo} FROM {tabela} WHERE {col_alvo} IS NOT NULL AND {col_alvo} != ''")
    if not df.empty:
        return df[col_alvo].tolist()
    return []

def salvar_cliente_completo(nome, telefone, doc, endereco, cidade):
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO clientes (nome, telefone, doc, endereco, cidade) VALUES (?, ?, ?, ?, ?)",
                       (nome.strip(), telefone, doc, endereco, cidade))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def salvar_produto_completo(nome, fornecedor, grupo, preco_custo, preco_venda, estoque_inicial):
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO produtos (nome, produto, fornecedor, grupo, valor_compra, valor_venda, quantidade, estoque_atual) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (nome.strip(), nome.strip(), fornecedor, grupo, preco_custo, preco_venda, estoque_inicial, estoque_inicial))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        cursor.execute("""
            UPDATE produtos 
            SET fornecedor = ?, grupo = ?, valor_compra = ?, valor_venda = ?, quantidade = ?, estoque_atual = ?
            WHERE TRIM(nome) = TRIM(?) OR TRIM(produto) = TRIM(?)
        """, (fornecedor, grupo, preco_custo, preco_venda, estoque_inicial, estoque_inicial, nome.strip(), nome.strip()))
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
    except:
        return False

# -----------------------------------------------------------------------------
# 2. INICIALIZAÇÃO DE SESSÃO E PERFIL
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
        
        lista_clientes = carregar_coluna("clientes", "nome") or carregar_coluna("vendas", "cliente") or ["Carlos Alberto"]
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
    
            col1, col2 = st.columns(2)
            with col1:
                prod = st.selectbox("Selecione o Produto", produtos_opt, key="cli_prod_unique_v3")
                forn_cli = st.selectbox("Selecione o Fornecedor", fornecedores_opt, key="cli_forn_unique_v3")
                
                preco_sugerido = 0.0
                if prod:
                    try:
                        cursor = conn.cursor()
                        cursor.execute("SELECT valor_compra FROM produtos WHERE produto = ? OR nome = ?", (prod, prod))
                        res = cursor.fetchone()
                        if res and res[0] is not None:
                            preco_sugerido = float(res[0])
                    except Exception:
                        pass
    
            with col2:
                grupo_cli = st.selectbox("Selecione o Grupo", grupos_opt, key="cli_grupo_unique_v3")
                qtd_cli = st.number_input("Quantidade", min_value=0.01, value=1.0, format="%.2f", key="cli_qtd_unique_v3")
                preco_cli = st.number_input("Preço Unitário (R$)", min_value=0.0, value=preco_sugerido, format="%.2f", key="cli_preco_unique_v3")
    
            valor_total_item = qtd_cli * preco_cli
            st.info(f"Valor Total do Item: R$ {valor_total_item:.2f}")
    
            if st.button("➕ Incluir Produto no Pedido", type="primary", key="cli_btn_add_unique_v3"):
                if "carrinho_cliente" not in st.session_state:
                    st.session_state.carrinho_cliente = []
                st.session_state.carrinho_cliente.append({
                    "produto": prod,
                    "fornecedor": forn_cli,
                    "grupo": grupo_cli,
                    "quantidade": qtd_cli,
                    "preco_unitario": preco_cli,
                    "valor_total": valor_total_item
                })
                st.success(f"Item '{prod}' adicionado ao pedido!")
                st.rerun()
    
            st.markdown("---")
            st.subheader("📋 Itens Atuais no Pedido")
    
            if len(st.session_state.get("carrinho_cliente", [])) > 0:
                df_carrinho_cli = pd.DataFrame(st.session_state.carrinho_cliente)
                st.dataframe(df_carrinho_cli, use_container_width=True, hide_index=True)
    
                col_b1, col_b2 = st.columns(2)
                with col_b1:
                    if st.button("🗑️ Limpar Carrinho", key="cli_limpar_unique_v3"):
                        st.session_state.carrinho_cliente = []
                        st.rerun()
    
                with col_b2:
                    if st.button("💾 Finalizar e Enviar Pedido", type="primary", key="cli_finalizar_unique_v3"):
                        try:
                            cursor = conn.cursor()
                            data_hora_atual = datetime.now()
                            codigo_pedido_gerado = f"PED-{data_hora_atual.strftime('%Y%m%d%H%M%S')}"
                            data_str = data_hora_atual.strftime("%Y-%m-%d %H:%M:%S")
                            
                            for item in st.session_state.carrinho_cliente:
                                cursor.execute("""
                                    INSERT INTO vendas (
                                        cliente, produto, quantidade, valor_venda, valor_total,
                                        fornecedor, grupo, data, status, codigo_venda, tipo
                                    )
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ORÇAMENTO')
                                """, (
                                    st.session_state.cliente_autenticado,
                                    item["produto"],
                                    item["quantidade"],
                                    item["preco_unitario"],
                                    item["valor_total"],
                                    item.get("fornecedor", "BAHIA"),
                                    item.get("grupo", "GERAL"),
                                    data_str,
                                    "Pendente",
                                    codigo_pedido_gerado
                                ))
                    
                            conn.commit()
                            st.cache_data.clear()
                            st.session_state.carrinho_cliente = []
                            st.success("Pedido finalizado e enviado com sucesso!")
                            st.rerun()
                        except Exception as ex:
                            st.error(f"Erro ao finalizar pedido: {ex}")
            else:
                st.info("Nenhum item adicionado ao pedido ainda.")
    
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
                                ids_para_excluir = df_editado[df_editado['Excluir'] == True]['id'].tolist()
                                
                                if ids_para_excluir:
                                    for id_pedido in ids_para_excluir:
                                        # 1. Pega o codigo_pedido do item antes de excluir (para limpar duplicados/histórico se houver)
                                        cursor.execute("SELECT codigo_pedido FROM pedidos WHERE id = ?", (id_pedido,))
                                        row = cursor.fetchone()
                                        
                                        # 2. Exclui pelo ID exato
                                        cursor.execute("DELETE FROM pedidos WHERE id = ?", (id_pedido,))
                                        
                                        # 3. Se tiver codigo_pedido associado, exclui outros registros atrelados a esse mesmo item
                                        if row and row[0]:
                                            cursor.execute("DELETE FROM pedidos WHERE codigo_pedido = ? AND status = 'Concluído (Convertido)'", (row[0],))
                                    
                                    conn.commit()
                                    st.warning("Itens selecionados excluídos com sucesso!")
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
                    WHERE DATE(data) != DATE('now') AND cliente = ?
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
        
        # --- LÓGICA: PDV — FRENTE DE CAIXA ---
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
                        sessao_id = df_caixa_aberto.iloc[0]['id']
                        data_venda = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                        for item in st.session_state.carrinho_pdv:
                            cursor.execute("""
                                INSERT INTO pedidos (cliente, produto, quantidade, valor_total, status, data)
                                VALUES (?, ?, ?, ?, 'Concluído (Convertido)', ?)
                            """, (
                                cliente_pdv,
                                item['produto'],
                                item['quantidade'],
                                item['valor_total'],
                                data_venda
                            ))

                        cursor.execute("INSERT INTO caixa_movimentacoes (sessao_id, tipo, valor, descricao, data) VALUES (?, ?, ?, ?, ?)",
                            (sessao_id, "VENDA", total_geral_carrinho, f"Venda PDV - Cliente: {cliente_pdv}", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                        )
                        conn.commit()

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
            st.title("📊 Painel Financeiro & Fechamento por Data")
            
            col_d1, col_d2, col_d3 = st.columns(3)
            with col_d1:
                data_inicio = st.date_input("Data Inicial", value=date(2025, 1, 1))
            with col_d2:
                data_fim = st.date_input("Data Final", value=date.today())
            with col_d3:
                status_filtro = st.selectbox("Status dos Registros", ["Somente Vendas Concluídas", "Incluir Pedidos Pendentes", "Todos"])
    
            str_d1 = data_inicio.strftime("%Y-%m-%d")
            str_d2 = data_fim.strftime("%Y-%m-%d")
            
            query_fin = f"SELECT * FROM vendas WHERE date(data) BETWEEN '{str_d1}' AND '{str_d2}'"
            df_todas = carregar_dados(query_fin)
    
            if not df_todas.empty:
                df_todas['status_str'] = df_todas['tipo'].fillna('').astype(str).str.strip().str.upper() if 'tipo' in df_todas.columns else ''
                
                if status_filtro == "Somente Vendas Concluídas":
                    df_filtrado = df_todas[df_todas['status_str'].str.contains('VENDA', na=False)]
                elif status_filtro == "Incluir Pedidos Pendentes":
                    df_filtrado = df_todas[df_todas['status_str'].str.contains('PEDIDO|ORÇAMENTO', na=False)]
                else:
                    df_filtrado = df_todas
    
                if not df_filtrado.empty:
                    col1, col2, col3 = st.columns(3)
                    faturamento = pd.to_numeric(df_filtrado['valor_total'], errors='coerce').sum() if 'valor_total' in df_filtrado.columns else 0.0
                    valor_rec = pd.to_numeric(df_filtrado['valor_recebido'], errors='coerce').sum() if 'valor_recebido' in df_filtrado.columns else 0.0
    
                    col1.metric("Faturamento do Período", f"R$ {faturamento:,.2f}")
                    col2.metric("Total Recebido em Caixa", f"R$ {valor_rec:,.2f}")
                    col3.metric("Total Pendente / Fiado", f"R$ {faturamento - valor_rec:,.2f}")
                    st.markdown("---")
                    st.dataframe(df_filtrado, use_container_width=True)
                else:
                    st.info("Nenhum registro encontrado para os filtros selecionados.")
            else:
                st.info("Nenhum dado cadastrado no período.")

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
        
                cliente_ped = st.selectbox("Cliente", clientes_opt, key="ped_cli_ind")
        
                col_a1, col_a2 = st.columns(2)
                with col_a1:
                    prod_item = st.selectbox("Selecione o Produto", produtos_opt, key="ped_select_produto")
        
                    if prod_item == "➕ Cadastrar Novo Produto...":
                        st.warning("⚠️ Preencha os dados abaixo para cadastrar o novo produto:")
                        novo_nome_prod = st.text_input("Nome do Novo Produto").strip().upper()
                        c_f_r = st.selectbox("Fornecedor", fornecedores_opt, key="cad_f_rapido")
                        c_g_r = st.selectbox("Grupo", grupos_opt, key="cad_g_rapido")
                        c_qtd_r = st.number_input("Qtd Inicial em Estoque", min_value=0.0, value=0.0, key="cad_q_rapido")
                        c_custo_r = st.number_input("Preço de Custo (R$)", min_value=0.0, value=0.0, key="cad_c_rapido")
                        c_venda_r = st.number_input("Preço de Venda (R$)", min_value=0.0, value=0.0, key="cad_v_rapido")
                        
                        if st.button("Salvar e Selecionar Produto"):
                            if novo_nome_prod:
                                salvar_produto_completo(novo_nome_prod, c_f_r, c_g_r, c_custo_r, c_venda_r, c_qtd_r)
                                st.success(f"Produto '{novo_nome_prod}' cadastrado com sucesso!")
                                st.rerun()
                            else:
                                st.error("Digite o nome do produto.")
                        st.stop()
        
                    fornec_ped = st.selectbox("Fornecedor", fornecedores_opt, key="ped_forn_ind")
        
                with col_a2:
                    grupo_ped = st.selectbox("Grupo", grupos_opt, key="ped_grupo_ind")
                    
                    preco_sugerido_admin = 0.0
                    if not df_p_admin.empty:
                        df_p_admin['_nome_limpo'] = df_p_admin[col_nome_p].astype(str).str.strip().str.upper()
                        target_nome = str(prod_item).strip().upper()
                        df_filtrado_admin = df_p_admin[df_p_admin['_nome_limpo'] == target_nome]
                        
                        if not df_filtrado_admin.empty:
                            row_adm = df_filtrado_admin.iloc[0]
                            col_alvo_preco = 'valor_compra' if is_modo_pedido else 'valor_venda'
                            for col_v in [col_alvo_preco, 'valor_venda', 'preco_venda', 'valor_compra', 'preco_compra', 'custo', 'venda']:
                                if col_v in df_p_admin.columns:
                                    try:
                                        val_aux = float(row_adm[col_v])
                                        if val_aux > 0:
                                            preco_sugerido_admin = val_aux
                                            break
                                    except:
                                        pass
        
                    qtd_ped = st.number_input("Quantidade", min_value=0.01, step=1.0, value=1.0, key="ped_qtd_ind")
                    v_venda_ped = st.number_input("Preço Unitário (R$)", min_value=0.0, value=float(preco_sugerido_admin), key="ped_v_ind")
        
                valor_total_item = qtd_ped * v_venda_ped
                st.info(f"Valor Total do Item: R$ {valor_total_item:.2f}")
        
                if st.button("➕ Incluir Produto no Pedido", type="primary", key="btn_add_carrinho_admin"):
                    st.session_state.carrinho_admin.append({
                        "produto": prod_item,
                        "fornecedor": fornec_ped,
                        "grupo": grupo_ped,
                        "quantidade": qtd_ped,
                        "valor_unitario": v_venda_ped,
                        "valor_total": valor_total_item
                    })
                    st.success(f"Item '{prod_item}' adicionado ao pedido!")
                    st.rerun()
        
                st.markdown("---")
                st.subheader("📋 Itens Atuais no Pedido")
        
                if len(st.session_state.carrinho_admin) > 0:
                    df_carrinho_adm = pd.DataFrame(st.session_state.carrinho_admin)
                    st.dataframe(df_carrinho_adm, use_container_width=True, hide_index=True)
        
                    col_c1, col_c2 = st.columns(2)
                    with col_c1:
                        if st.button("🗑️ Limpar Carrinho", key="btn_limpar_carrinho_admin"):
                            st.session_state.carrinho_admin = []
                            st.rerun()
        
                    with col_c2:
                        if st.button("💾 Finalizar e Salvar Pedido", type="primary", key="btn_salvar_bd_admin"):
                            try:
                                cursor = conn.cursor()
                                tipo_banco = 'ORÇAMENTO' if is_modo_pedido else 'VENDA'
                                
                                for item in st.session_state.carrinho_admin:
                                    cursor.execute("""
                                        INSERT INTO vendas (cliente, produto, fornecedor, grupo, quantidade, valor_venda, valor_total, tipo, status, data)
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pendente', datetime('now', 'localtime'))
                                    """, (
                                        cliente_ped,
                                        item["produto"],
                                        item["fornecedor"],
                                        item["grupo"],
                                        item["quantidade"],
                                        item["valor_unitario"],
                                        item["valor_total"],
                                        tipo_banco
                                    ))
                                
                                conn.commit()
                                st.session_state.carrinho_admin = []
                                st.success("Pedido salvo com sucesso!")
                                st.rerun()
                            except Exception as err:
                                st.error(f"Erro ao salvar pedido: {err}")
                else:
                    st.info("Nenhum item adicionado ao carrinho ainda.")
        
            # AQUI COMEÇA A SEGUNDA ABA (Tabela Editável)
            with aba_list:
                st.subheader("🟢 Pedidos do Dia (Editáveis)")

            # --- BARRA DE FILTROS ---
            df_todos_pedidos = pd.read_sql_query("SELECT * FROM vendas", conn)
    
            if not df_todos_pedidos.empty:
                col_f1, col_f2, col_f3, col_f4 = st.columns(4)
    
                lista_clientes = ["Todos"] + sorted(list(df_todos_pedidos['cliente'].dropna().unique()))
                lista_fornecedores = ["Todos"] + sorted(list(df_todos_pedidos['fornecedor'].dropna().unique()))
                lista_grupos = ["Todos"] + sorted(list(df_todos_pedidos['grupo'].dropna().unique()))
    
                with col_f1:
                    filtro_cliente = st.selectbox("Filtrar por Cliente:", lista_clientes, key="f_cli_pedidos")
                with col_f2:
                    filtro_fornecedor = st.selectbox("Filtrar por Fornecedor:", lista_fornecedores, key="f_forn_pedidos")
                with col_f3:
                    filtro_grupo = st.selectbox("Filtrar por Grupo:", lista_grupos, key="f_grp_pedidos")
                with col_f4:
                    filtro_data = st.date_input("Filtrar por Data:", value=None, key="f_dt_pedidos")
    
                query_base = "SELECT id, cliente, produto, quantidade, valor_venda, valor_total, fornecedor, grupo, data, status FROM vendas WHERE 1=1"
                params_filtro = []
    
                if filtro_cliente != "Todos":
                    query_base += " AND cliente = ?"
                    params_filtro.append(filtro_cliente)
                if filtro_fornecedor != "Todos":
                    query_base += " AND fornecedor = ?"
                    params_filtro.append(filtro_fornecedor)
                if filtro_grupo != "Todos":
                    query_base += " AND grupo = ?"
                    params_filtro.append(filtro_grupo)
                if filtro_data is not None:
                    query_base += " AND DATE(data) = ?"
                    params_filtro.append(str(filtro_data))
    
                query_base += " ORDER BY id DESC"
                df_dia = pd.read_sql_query(query_base, conn, params=params_filtro)
            else:
                df_dia = pd.DataFrame()
    
            if not df_dia.empty:
                df_exibir = df_dia.copy()
                if 'Excluir' not in df_exibir.columns:
                    df_exibir.insert(0, 'Excluir', False)
        
                    df_exibir['Valor Unitário (R$)'] = df_exibir['valor_venda'].apply(lambda x: f"R$ {float(x):.2f}" if pd.notnull(x) else "R$ 0.00")
                    df_exibir['Total (R$)'] = df_exibir['valor_total'].apply(lambda x: f"R$ {float(x):.2f}" if pd.notnull(x) else "R$ 0.00")
        
                    cols_vis = ['Excluir', 'id', 'cliente', 'produto', 'quantidade', 'Valor Unitário (R$)', 'Total (R$)', 'fornecedor', 'grupo', 'data', 'status']
                    cols_finais = [c for c in cols_vis if c in df_exibir.columns]
        
                    df_editado = st.data_editor(
                        df_exibir[cols_finais], 
                        key="editor_global_admin_dia", 
                        use_container_width=True, 
                        hide_index=True,
                        disabled=['id', 'Valor Unitário (R$)', 'Total (R$)', 'data']
                    )
        
                    col_b1, col_b2, col_b3, col_b4 = st.columns([1, 1, 1, 2])
                    
                    with col_b1:
                        if st.button("💾 Salvar Alterações", type="primary", key="btn_salvar_edit_admin_global"):
                            try:
                                cursor = conn.cursor()
                                for index, row in df_editado.iterrows():
                                    row_id = int(row['id'])
                                    nova_qtd = float(row.get('quantidade', 1))
                                    novo_prod = str(row.get('produto', '')).strip()
                                    novo_cli = str(row.get('cliente', '')).strip()
                                    novo_fornec = str(row.get('fornecedor', '')).strip()
                                    novo_grupo = str(row.get('grupo', '')).strip()
                                    novo_status = str(row.get('status', 'Pendente')).strip()
        
                                    v_unit_orig = float(df_dia.loc[df_dia['id'] == row_id, 'valor_venda'].values[0])
                                    novo_total = nova_qtd * v_unit_orig
        
                                    cursor.execute("""
                                        UPDATE vendas 
                                        SET cliente = ?, produto = ?, quantidade = ?, valor_total = ?, fornecedor = ?, grupo = ?, status = ?
                                        WHERE id = ?
                                    """, (novo_cli, novo_prod, nova_qtd, novo_total, novo_fornec, novo_grupo, novo_status, row_id))
                                    
                                conn.commit()
                                st.cache_data.clear()
                                st.toast("✅ Alterações salvas com sucesso!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao salvar alterações: {e}")
        
                    with col_b2:
                        if st.button("🗑️ Excluir Marcados", key="btn_excluir_edit_admin_global"):
                            try:
                                cursor = conn.cursor()
                                deletados = 0
                                for index, row in df_editado.iterrows():
                                    if row.get('Excluir', False):
                                        cursor.execute("DELETE FROM vendas WHERE id = ?", (row['id'],))
                                        deletados += 1
                                conn.commit()
                                if deletados > 0:
                                    st.toast(f"🗑️ {deletados} item(ns) excluído(s)!")
                                    st.rerun()
                                else:
                                    st.warning("Marque a caixa 'Excluir'.")
                            except Exception as e:
                                st.error(f"Erro ao excluir: {e}")
        
                    with col_b4:
                        try:
                            # Gera o buffer do PDF
                            pdf_buf = gerar_pdf_tabela_pedidos(df_dia, cliente_nome=filtro_cliente)
                            
                            nome_arq = f"relatorio_pedidos_{filtro_cliente.lower().replace(' ', '_')}.pdf" if filtro_cliente != "Todos" else "relatorio_pedidos_geral.pdf"
            
                            st.download_button(
                                label="📄 Baixar PDF do Dia",
                                data=pdf_buf.getvalue(),  # <--- O .getvalue() resolve o erro de arquivo danificado!
                                file_name=nome_arq,
                                mime="application/pdf",
                                key="btn_pdf_dia_completo"
                            )
                        except Exception as e:
                            st.error(f"Erro ao gerar PDF: {e}")
                else:
                    st.info("Nenhum pedido cadastrado hoje.")
                st.divider()
                st.subheader("💳 Confirmar Recebimento / Dar Baixa no Pedido")
        
                cursor.execute("""
                    SELECT DISTINCT cliente 
                    FROM vendas 
                    WHERE status = 'Pendente' 
                      AND (restante IS NULL OR restante > 0)
                """)
                clientes_pendentes = [row[0] for row in cursor.fetchall() if row[0]]
        
                if clientes_pendentes:
                    cliente_sel = st.selectbox("Selecione o Cliente:", clientes_pendentes, key="sel_cli_baixa")
                    
                    # Busca pedidos pendentes exibindo exatamente o valor devedor atualizado
                    df_pedidos_cli = pd.read_sql_query("""
                        SELECT id, produto, quantidade, valor_venda AS valor_unitario, valor_total,
                               COALESCE(valor_recebido, 0) AS valor_pago,
                               COALESCE(restante, valor_total) AS valor_devedor,
                               data 
                        FROM vendas 
                        WHERE status = 'Pendente' AND cliente = ?
                    """, conn, params=(cliente_sel,))
                    
                    # Formatação visual para garantir que as colunas fiquem organizadas
                    st.dataframe(
                        df_pedidos_cli, 
                        use_container_width=True, 
                        hide_index=True,
                        column_config={
                            "valor_unitario": st.column_config.NumberColumn("Valor Unitário (R$)", format="R$ %.2f"),
                            "valor_total": st.column_config.NumberColumn("Valor Total (R$)", format="R$ %.2f"),
                            "valor_pago": st.column_config.NumberColumn("Valor Já Pago (R$)", format="R$ %.2f"),
                            "valor_devedor": st.column_config.NumberColumn("Valor Devedor (R$)", format="R$ %.2f"),
                        }
                    )
                    
                    total_pendente = float(df_pedidos_cli['valor_devedor'].sum())
                    st.warning(f"💳 **Débito Total Atual de {cliente_sel}: R$ {total_pendente:.2f}**")
                    
                    col_p1, col_p2, col_p3 = st.columns(3)
                    with col_p1:
                        forma_pgto = st.selectbox("Forma de Pagamento:", ["Dinheiro", "Pix", "Cartão de Crédito", "Cartão de Débito", "Crediário / Fiado"], key="fp_baixa")
                    with col_p2:
                        # Inicia sempre zerado conforme solicitado
                        valor_recebido = st.number_input("Valor Recebido / Haver (R$):", min_value=0.0, value=0.0, step=0.50, key="vr_baixa")
                    with col_p3:
                        restante_calculado = max(0.0, total_pendente - valor_recebido)
                        troco = max(0.0, valor_recebido - total_pendente)
                        if forma_pgto == "Crediário / Fiado":
                            st.metric("Saldo Restante (Fiado)", f"R$ {restante_calculado:.2f}")
                        else:
                            st.metric("Troco", f"R$ {troco:.2f}")
        
                    # Campos para Crediário / Fiado
                    datas_vencimento = []
                    num_parcelas = 1
                
                    if forma_pgto == "Crediário / Fiado":
                        col_parc1, col_parc2 = st.columns([1, 3])
                        
                        with col_parc1:
                            num_parcelas = st.number_input("Nº de Parcelas:", min_value=1, max_value=24, value=1, step=1, key="num_parc_baixa")
                        
                        with col_parc2:
                            if num_parcelas == 1:
                                dt_venc = st.date_input("Data do Vencimento:", value=datetime.today(), key="venc_unica_baixa")
                                datas_vencimento.append(dt_venc)
                            else:
                                st.caption("📅 Você pode alterar a data de cada parcela abaixo:")
                                cols_venc = st.columns(min(int(num_parcelas), 3))
                                
                                for i in range(int(num_parcelas)):
                                    col_target = cols_venc[i % 3]
                                    with col_target:
                                        data_sugerida = datetime.today() + timedelta(days=30 * i)
                                        dt = st.date_input(
                                            label=f"Venc. {i+1}ª Parcela:",
                                            value=data_sugerida,
                                            key=f"venc_parc_{i}"
                                        )
                                        datas_vencimento.append(dt)
        
                    if st.button("✅ Confirmar Recebimento / Abatimento", type="primary", key="btn_quitar_pedidos"):
                        try:
                            if valor_recebido <= 0:
                                st.error("Informe um valor recebido/haver maior que zero.")
                            else:
                                valor_restante_a_abater = valor_recebido
                                
                                # Abate o valor recebido item por item nos pedidos pendentes
                                for _, row in df_pedidos_cli.iterrows():
                                    item_id = row['id']
                                    item_pago_atual = float(row['valor_pago'])
                                    item_devedor_atual = float(row['saldo_devedor'])
                                    
                                    if valor_restante_a_abater <= 0:
                                        break
                                        
                                    if valor_restante_a_abater >= item_devedor_atual:
                                        # Abate este item por completo
                                        novo_pago = item_pago_atual + item_devedor_atual
                                        novo_restante = 0.0
                                        item_status = 'Concluído (Convertido)'
                                        valor_restante_a_abater -= item_devedor_atual
                                    else:
                                        # Abate parcial neste item
                                        novo_pago = item_pago_atual + valor_restante_a_abater
                                        novo_restante = item_devedor_atual - valor_restante_a_abater
                                        item_status = 'Pendente'
                                        valor_restante_a_abater = 0.0
                                    
                                    cursor.execute("""
                                        UPDATE vendas 
                                        SET status = ?, 
                                            forma_pagamento = ?, 
                                            valor_recebido = ?, 
                                            troco = ?, 
                                            restante = ?
                                        WHERE id = ?
                                    """, (item_status, forma_pgto, novo_pago, troco if item_status == 'Concluído (Convertido)' else 0.0, novo_restante, item_id))
                                
                                conn.commit()
                                st.cache_data.clear()
                                
                                if restante_calculado == 0:
                                    st.success(f"Pagamento total de {cliente_sel} registrado com sucesso!")
                                else:
                                    st.warning(f"Abatimento (Haver) de R$ {valor_recebido:.2f} registrado! Restante pendente: R$ {restante_calculado:.2f}")
                                    
                                st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao registrar pagamento: {e}")
                else:
                    st.success("🎉 Nenhum pedido pendente para recebimento no momento!")        
                st.divider()
                st.subheader("📚 Pedidos Anteriores / Histórico Geral")
                df_todas_vendas = carregar_dados("SELECT * FROM vendas ORDER BY id DESC")
                if not df_todas_vendas.empty:
                    st.dataframe(df_todas_vendas, use_container_width=True, hide_index=True)
                else:
                    st.info("Nenhum registro encontrado.")
            
        elif menu_admin == "📦 Estoque de Produtos":
            st.title("📦 Estoque de Produtos e Preços")
            
            query_produtos = "SELECT * FROM produtos"
            df_produtos = carregar_dados(query_produtos)
        
            if not df_produtos.empty:
                df_produtos = df_produtos.drop(columns=['estoque_atual', 'nome'], errors='ignore')
                
                df_editado = st.data_editor(
                    df_produtos,
                    use_container_width=True,
                    key="editor_estoque_produtos",
                    hide_index=True
                )
    
                col_salvar, col_atualizar = st.columns(2)
    
                with col_salvar:
                    if st.button("Salvar Alterações no Estoque"):
                        try:
                            cursor = conn.cursor()
                            for index, row in df_editado.iterrows():
                                p_id = row.get('id')
                                p_prod = row.get('produto')
                                p_qtd = row.get('quantidade', 0)
                                p_custo = row.get('valor_compra', 0)
                                p_venda = row.get('valor_venda', 0)
                                p_grupo = row.get('grupo')
                                p_forn = row.get('fornecedor')
    
                                cursor.execute("""
                                    UPDATE produtos 
                                    SET produto = ?, 
                                        nome = ?,
                                        quantidade = ?, 
                                        estoque_atual = ?, 
                                        valor_compra = ?, 
                                        valor_venda = ?, 
                                        grupo = ?, 
                                        fornecedor = ?
                                    WHERE id = ?
                                """, (p_prod, p_prod, p_qtd, p_qtd, p_custo, p_venda, p_grupo, p_forn, p_id))
    
                            conn.commit()
                            st.success("Estoque e preços salvos permanentemente!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao salvar: {e}")
    
                with col_atualizar:
                    if st.button("🔄 Atualizar Preços de Custos"):
                        try:
                            cursor = conn.cursor()
                            cursor.execute("""
                                UPDATE produtos 
                                SET valor_compra = (
                                    SELECT valor_custo FROM compras 
                                    WHERE compras.produto = produtos.produto 
                                    ORDER BY id DESC LIMIT 1
                                )
                                WHERE EXISTS (
                                    SELECT 1 FROM compras 
                                    WHERE compras.produto = produtos.produto
                                )
                            """)
                            conn.commit()
                            st.success("Preços de custo atualizados com sucesso!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao atualizar custos: {e}")
            else:
                st.info("Nenhum produto cadastrado no estoque.")
        
        elif menu_admin == "👥 Cadastros (Clientes / Fornecedores / Grupos)":
            st.title("👥 Cadastros Gerais")
            tab_cli, tab_prod, tab_forn, tab_grup = st.tabs(["👤 Clientes", "📦 Produtos", "🏢 Fornecedores", "🏷️ Grupos"])
            
            with tab_cli:
                st.subheader("Gerenciamento de Clientes")
                with st.form("form_cad_cliente_completo"):
                    novo_cli = st.text_input("Nome do Cliente / Razão Social")
                    telefone = st.text_input("Telefone / WhatsApp")
                    doc = st.text_input("CPF / CNPJ")
                    endereco = st.text_input("Endereço")
                    cidade = st.text_input("Cidade / Email")

                    if st.form_submit_button("💾 Salvar Cliente"):
                        if novo_cli.strip():
                            salvar_cliente_completo(novo_cli, telefone, doc, endereco, cidade)
                            st.success("Cliente cadastrado com sucesso!")
                            st.rerun()
                        else:
                            st.warning("Preencha o nome do cliente.")
                st.dataframe(carregar_dados("SELECT * FROM clientes"), use_container_width=True)

            with tab_prod:
                st.subheader("📝 Gerenciar Produtos (Cadastrar, Editar e Excluir)")
                
                with st.form("form_cad_produto_completo", clear_on_submit=True):
                    col1, col2 = st.columns(2)
                    with col1:
                        txt_nome_produto = st.text_input("Nome do Produto")
                        val_custo = st.number_input("Preço de Custo (R$)", min_value=0.0, format="%.2f")
                    with col2:
                        grupo_produto = st.text_input("Grupo / Categoria", value="Geral")
                        val_venda = st.number_input("Preço de Venda (R$)", min_value=0.0, format="%.2f")
                        
                    col3, col4 = st.columns(2)
                    with col3:
                        estoque_inicial = st.number_input("Estoque Inicial", min_value=0, value=0, step=1)
                    with col4:
                        fornecedor_produto = st.text_input("Fornecedor", value="")
    
                    if st.form_submit_button("Salvar Novo Produto"):
                        if not txt_nome_produto.strip():
                            st.warning("Por favor, informe o nome do produto.")
                        else:
                            try:
                                cursor = conn.cursor()
                                cursor.execute("""
                                    INSERT INTO produtos (produto, nome, quantidade, estoque_atual, valor_compra, valor_venda, fornecedor, grupo)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                """, (
                                    txt_nome_produto.upper(), 
                                    txt_nome_produto.upper(), 
                                    estoque_inicial, 
                                    estoque_inicial, 
                                    val_custo, 
                                    val_venda, 
                                    fornecedor_produto,
                                    grupo_produto
                                ))
                                conn.commit()
                                st.success(f"Produto '{txt_nome_produto}' cadastrado com sucesso!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao cadastrar produto: {e}")
                
                st.markdown("---")
                st.subheader("📋 Lista de Produtos (Edite direto na tabela ou exclua abaixo)")
                
                df_produtos_view = carregar_dados("SELECT * FROM produtos")
                if not df_produtos_view.empty:
                    df_produtos_view = df_produtos_view.drop(columns=['estoque_atual', 'nome'], errors='ignore')
                    
                    df_editado_prod = st.data_editor(
                        df_produtos_view, 
                        use_container_width=True, 
                        hide_index=True,
                        key="editor_produtos_geral"
                    )
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("💾 Salvar Alterações da Tabela"):
                            try:
                                cursor = conn.cursor()
                                for index, row in df_editado_prod.iterrows():
                                    p_id = row.get('id')
                                    p_prod = row.get('produto')
                                    p_qtd = row.get('quantidade', 0)
                                    p_compra = row.get('valor_compra', 0)
                                    p_venda = row.get('valor_venda', 0)
                                    p_grupo = row.get('grupo')
                                    p_forn = row.get('fornecedor')
    
                                    cursor.execute("""
                                        UPDATE produtos 
                                        SET produto = ?, nome = ?, quantidade = ?, estoque_atual = ?, valor_compra = ?, valor_venda = ?, grupo = ?, fornecedor = ?
                                        WHERE id = ?
                                    """, (p_prod, p_prod, p_qtd, p_qtd, p_compra, p_venda, p_grupo, p_forn, p_id))
                                conn.commit()
                                st.success("Alterações salvas com sucesso!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao salvar alterações: {e}")
                    
                    with col_btn2:
                        produtos_para_excluir = df_produtos_view['produto'].tolist()
                        prod_selecionado_excluir = st.selectbox("Selecione um produto para excluir", produtos_para_excluir, key="select_del_prod")
                        if st.button("🗑️ Excluir Produto Selecionado"):
                            try:
                                cursor = conn.cursor()
                                cursor.execute("DELETE FROM produtos WHERE produto = ? OR nome = ?", (prod_selecionado_excluir, prod_selecionado_excluir))
                                conn.commit()
                                st.success(f"Produto '{prod_selecionado_excluir}' excluído com sucesso!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao excluir: {e}")
                else:
                    st.info("Nenhum produto cadastrado.")

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
                    
        elif menu_admin == "📥 Entrada de Estoque (Compras)":
            st.title("📥 Entrada de Estoque (Compras)")
            
            produtos_opt = carregar_coluna("produtos", "produto") or ["AMEIXA IMPORTADA", "ABACATE"]
            fornecedores_opt = carregar_coluna("fornecedores", "fornecedor") or ["BAHIA"]
            grupos_opt = carregar_coluna("grupos", "grupo") or ["GERAL"]
            
            st.subheader("Registrar Entrada de Estoque")
            
            tipo_cadastro = st.radio("Escolha a opção:", ["Produto Existente", "Novo Produto"], horizontal=True, key="radio_tipo_prod")
            
            col1, col2 = st.columns(2)
            with col1:
                if tipo_cadastro == "Produto Existente":
                    produto_escolhido = st.selectbox("Selecione o Produto", produtos_opt, key="prod_entrada_estoque")
                    produto_final = produto_escolhido
                else:
                    produto_final = st.text_input("Digite o Nome do NOVO Produto").strip().upper()
                    
                fornecedor_escolhido = st.selectbox("Fornecedor", fornecedores_opt, key="forn_entrada")
                quantidade_entrada = st.number_input("Quantidade", min_value=0.0, format="%.2f", key="qtd_entrada")

            with col2:
                grupo_escolhido = st.selectbox("Grupo / Categoria", grupos_opt, key="grupo_entrada")
                
                preco_cadastrado = 0.0
                if tipo_cadastro == "Produto Existente" and 'produto_escolhido' in locals() and produto_escolhido:
                    try:
                        cursor = conn.cursor()
                        cursor.execute("SELECT valor_compra FROM produtos WHERE produto = ? OR nome = ?", (produto_escolhido, produto_escolhido))
                        resultado = cursor.fetchone()
                        if resultado and resultado[0] is not None:
                            preco_cadastrado = float(resultado[0])
                    except Exception:
                        pass

                preco_custo = st.number_input("Preço de Custo Unitário (R$)", min_value=0.0, value=preco_cadastrado, format="%.2f", key="custo_entrada")
                preco_venda = st.number_input("Preço de Venda Unitário (R$)", min_value=0.0, format="%.2f", key="venda_entrada")

            if st.button("💾 Confirmar Entrada no Estoque", type="primary", key="btn_conf_entrada"):
                if not produto_final:
                    st.warning("Informe ou selecione o nome do produto.")
                else:
                    try:
                        cursor = conn.cursor()
                        cursor.execute("SELECT id FROM produtos WHERE produto = ? OR nome = ?", (produto_final, produto_final))
                        existe = cursor.fetchone()
                        
                        if existe:
                            cursor.execute("""
                                UPDATE produtos 
                                SET quantidade = quantidade + ?, valor_compra = ?, valor_venda = ?, grupo = ?, fornecedor = ?
                                WHERE produto = ? OR nome = ?
                            """, (quantidade_entrada, preco_custo, preco_venda, grupo_escolhido, fornecedor_escolhido, produto_final, produto_final))
                        else:
                            cursor.execute("""
                                INSERT INTO produtos (produto, nome, quantidade, estoque_atual, valor_compra, valor_venda, grupo, fornecedor)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """, (produto_final, produto_final, quantidade_entrada, quantidade_entrada, preco_custo, preco_venda, grupo_escolhido, fornecedor_escolhido))
                        
                        registrar_compra(produto_final, fornecedor_escolhido, grupo_escolhido, quantidade_entrada, preco_custo, preco_venda)
                        
                        conn.commit()
                        st.success(f"Estoque atualizado/produto '{produto_final}' cadastrado com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao registrar entrada: {e}")
