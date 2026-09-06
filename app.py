import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date
import io
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# -----------------------------------------------------------------------------
# 1. CONFIGURAÇÃO E CONEXÃO COM O BANCO DE DADOS
# -----------------------------------------------------------------------------
st.set_page_config(page_title="CRM Comércio - Rey da Cebola", layout="wide")

def get_connection():
    return sqlite3.connect("crm_comercio.db", check_same_thread=False)

conn = get_connection()

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

    colunas_verificar_vendas = ['forma_pagamento', 'valor_recebido', 'tipo', 'codigo', 'data']
    for col_nome in colunas_verificar_vendas:
        if col_nome not in colunas_vendas:
            try:
                tipo_sql = "TEXT"
                default_val = "DEFAULT 'PEDIDO'" if col_nome == 'tipo' else ("DEFAULT 'PED'" if col_nome == 'codigo' else "")
                cursor.execute(f"ALTER TABLE vendas ADD COLUMN {col_nome} {tipo_sql} {default_val}")
            except Exception:
                pass
          
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE,
            fornecedor TEXT,
            grupo TEXT,
            valor_compra REAL,
            valor_venda REAL,
            estoque_atual REAL
        )
    """)
    
    cursor.execute("PRAGMA table_info(produtos)")
    colunas_produtos = [col[1] for col in cursor.fetchall()]

    colunas_verificar_produtos = ['fornecedor', 'grupo', 'valor_compra', 'valor_venda', 'estoque_atual', 'nome']
    for col_nome in colunas_verificar_produtos:
        if col_nome not in colunas_produtos:
            try:
                cursor.execute(f"ALTER TABLE produtos ADD COLUMN {col_nome} TEXT")
            except Exception:
                pass

    if 'nome' not in colunas_produtos and 'descricao' in colunas_produtos:
        try:
            cursor.execute("ALTER TABLE produtos RENAME COLUMN descricao TO nome")
        except Exception:
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
    
    colunas_compras = [
        ("produto", "TEXT"),
        ("fornecedor", "TEXT"),
        ("grupo", "TEXT"),
        ("quantidade", "REAL"),
        ("valor_custo", "REAL"),
        ("valor_total", "REAL"),
        ("data", "TEXT")
    ]
    for col_nome, col_tipo in colunas_compras:
        try:
            cursor.execute(f"ALTER TABLE compras ADD COLUMN {col_nome} {col_tipo}")
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
            INSERT INTO produtos (nome, fornecedor, grupo, valor_compra, valor_venda, estoque_atual) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (nome.strip(), fornecedor, grupo, preco_custo, preco_venda, estoque_inicial))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        cursor.execute("""
            UPDATE produtos 
            SET fornecedor = ?, grupo = ?, valor_compra = ?, valor_venda = ?, estoque_atual = ?
            WHERE TRIM(nome) = TRIM(?)
        """, (fornecedor, grupo, preco_custo, preco_venda, estoque_inicial, nome.strip()))
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

def salvar_pedido_ou_venda(cliente, produto, fornecedor, grupo, quantidade, valor_venda, forma_pagamento="", valor_recebido=0.0, tipo="PEDIDO"):
    cursor = conn.cursor()
    valor_total = quantidade * valor_venda
    data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cod_status = "VEN" if tipo.upper() in ["VENDA", "VENDAS", "VEN"] else "PED"
    
    cursor.execute("""
        INSERT INTO vendas (cliente, produto, fornecedor, grupo, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, tipo, codigo, data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (cliente.strip(), produto, fornecedor, grupo, quantidade, valor_venda, valor_total, forma_pagamento, str(valor_recebido), tipo, cod_status, data_atual))
    conn.commit()

def baixar_debito_cliente(cliente_nome, valor_haver, forma_pagamento="Dinheiro"):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, valor_total, valor_recebido 
        FROM vendas 
        WHERE TRIM(cliente) = TRIM(?)
    """, (cliente_nome,))
    registros = cursor.fetchall()
    
    saldo_haver = float(valor_haver)
    
    for reg in registros:
        reg_id, v_total, v_rec_atual = reg
        v_rec_atual = float(v_rec_atual) if v_rec_atual else 0.0
        pendente_linha = v_total - v_rec_atual
        
        if pendente_linha > 0 and saldo_haver > 0:
            if saldo_haver >= pendente_linha:
                novo_recebido = v_total
                saldo_haver -= pendente_linha
            else:
                novo_recebido = v_rec_atual + saldo_haver
                saldo_haver = 0.0
            
            cursor.execute("""
                UPDATE vendas 
                SET valor_recebido = ?, forma_pagamento = ? 
                WHERE id = ?
            """, (str(novo_recebido), forma_pagamento, reg_id))
            
    conn.commit()

def registrar_compra(produto, fornecedor, grupo, quantidade, valor_custo, valor_venda=0.0):
    cursor = conn.cursor()
    valor_total = quantidade * valor_custo
    data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute("""
        INSERT INTO compras (produto, fornecedor, grupo, quantidade, valor_custo, valor_venda, valor_total, data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (produto, fornecedor, grupo, quantidade, valor_custo, valor_venda, valor_total, data_atual))
    conn.commit()

# -----------------------------------------------------------------------------
# GERADOR DE PDF
# -----------------------------------------------------------------------------
def gerar_pdf_tabela_pedidos(df_dados, cliente_nome="Geral", d_inicio=None, d_fim=None, titulo_custom=None):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=20, leftMargin=20, topMargin=15, bottomMargin=15)
    elements = []
    styles = getSampleStyleSheet()
    
    style_empresa = ParagraphStyle('EmpresaStyle', parent=styles['Heading1'], fontName='Helvetica-BoldOblique', fontSize=18, leading=20, alignment=1, textColor=colors.black)
    style_sub = ParagraphStyle('SubStyle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, leading=10, alignment=1)
    style_titulo_relatorio = ParagraphStyle('RelatorioStyle', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=13, leading=16, alignment=1, textColor=colors.HexColor('#1E50A2'))
    style_data = ParagraphStyle('DataStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=10, alignment=1, textColor=colors.HexColor('#333333'))

    elements.append(Paragraph("REY DA CEBOLA", style_empresa))
    elements.append(Paragraph("CNPJ: 194.174.39/000-42 INSC.EST.: 12.426725-4", style_sub))
    elements.append(Paragraph("CONTATO: (99) 98814-9722 OU (99) 98414-3943", style_sub))
    elements.append(Spacer(1, 4))
    
    titulo_doc = titulo_custom if titulo_custom else f"Relatório de Pedidos / Orçamentos - {cliente_nome}"
    elements.append(Paragraph(titulo_doc, style_titulo_relatorio))
    periodo_str = f"Período: {d_inicio.strftime('%d/%m/%Y')} até {d_fim.strftime('%d/%m/%Y')}" if d_inicio and d_fim else f"Data de Emissão: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    elements.append(Paragraph(periodo_str, style_data))
    elements.append(Spacer(1, 6))
    
    if not df_dados.empty:
        df_resumo = df_dados.groupby('produto').agg({
            'quantidade': 'sum',
            'valor_venda': 'mean',
            'valor_total': 'sum'
        }).reset_index()
    else:
        df_resumo = pd.DataFrame(columns=['produto', 'quantidade', 'valor_venda', 'valor_total'])

    table_data = [["Produto", "Qtd Total", "Preço Custo Unitário (R$)", "Valor Total (R$)"]]
    valor_total_geral = 0.0
    for _, row in df_resumo.iterrows():
        prod = str(row['produto'])
        qtd = f"{row['quantidade']:.2f}"
        v_unit = f"R$ {row['valor_venda']:,.2f}"
        v_tot = row['valor_total']
        valor_total_geral += v_tot
        table_data.append([prod, qtd, v_unit, f"R$ {v_tot:,.2f}"])
        
    table_data.append(["VALOR TOTAL GERAL", "", "", f"R$ {valor_total_geral:,.2f}"])
    
    t = Table(table_data, colWidths=[240, 90, 130, 130])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2A65F0')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#CCCCCC')),
        ('SPAN', (0, -1), (2, -1)),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#1B2A4A')),
        ('TEXTCOLOR', (0, -1), (-1, -1), colors.white),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, -1), (-1, -1), 10),
        ('ALIGN', (0, -1), (2, -1), 'RIGHT'),
        ('ALIGN', (-1, -1), (-1, -1), 'CENTER'),
    ]))
    
    elements.append(t)
    doc.build(elements)
    buffer.seek(0)
    return buffer

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
    if not st.session_state.get("cliente_autenticado"):
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

        # Garante que a tabela de pedidos existe
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
                        cursor.execute("SELECT valor_compra FROM produtos WHERE produto = ?", (prod,))
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
                                    INSERT INTO pedidos (
                                        cliente, produto, quantidade, valor_unitario, valor_total, 
                                        fornecedor, grupo, data, status, codigo_pedido
                                    )
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                            st.session_state.carrinho_cliente = []
                            st.success("Pedido finalizado e enviado com sucesso!")
                            st.rerun()
                        except Exception as ex:
                            conn.rollback()
                            st.error(f"Erro ao finalizar pedido: {ex}")
            else:
                st.info("Nenhum item adicionado ao pedido ainda.")
    
        with aba_historico:
            st.subheader("Histórico e Gestão de Meus Pedidos")
            
            try:
                query_dia = """
                    SELECT id, cliente, produto, quantidade, valor_unitario, valor_total, fornecedor, grupo, data, status 
                    FROM pedidos 
                    WHERE DATE(data) = DATE('now') AND cliente = ?
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
                                        UPDATE pedidos 
                                        SET quantidade = ?, valor_total = ? 
                                        WHERE id = ?
                                    """, (row['quantidade'], novo_total, row['id']))
                                conn.commit()
                                st.success("Pedidos atualizados com sucesso!")
                                st.rerun()
                            except Exception as ex:
                                conn.rollback()
                                st.error(f"Erro ao atualizar os pedidos: {ex}")
        
                    with col_btn2:
                        if st.button("🗑️ Excluir Marcados", type="secondary", key="btn_excluir_selecionados"):
                            try:
                                cursor = conn.cursor()
                                ids_para_excluir = df_editado[df_editado['Excluir'] == True]['id'].tolist()
                                
                                if ids_para_excluir:
                                    for id_pedido in ids_para_excluir:
                                        cursor.execute("DELETE FROM pedidos WHERE id = ?", (id_pedido,))
                                    conn.commit()
                                    st.warning("Itens selecionados excluídos com sucesso!")
                                    st.rerun()
                                else:
                                    st.info("Nenhum item foi marcado para exclusão.")
                            except Exception as ex:
                                conn.rollback()
                                st.error(f"Erro ao excluir os itens: {ex}")

                    try:
                        from reportlab.lib.pagesizes import letter
                        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
                        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                        from reportlab.lib import colors
                        from datetime import timedelta
                        import io

                        buffer = io.BytesIO()
                        doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=15, bottomMargin=30)
                        elements = []
                        styles = getSampleStyleSheet()

                        fuso_brasil = timedelta(hours=3)
                        hora_local = datetime.now() - fuso_brasil
                        data_hora_str = hora_local.strftime('%Y-%m-%d %H:%M:%S')

                        estilo_empresa = ParagraphStyle('Empresa', parent=styles['Heading1'], fontSize=14, textColor=colors.HexColor('#002060'), alignment=1, fontName='Helvetica-Bold', spaceAfter=0)
                        estilo_sub_empresa = ParagraphStyle('SubEmpresa', parent=styles['Normal'], fontSize=8, textColor=colors.black, alignment=1, leading=9, spaceAfter=0)
                        estilo_titulo_rel = ParagraphStyle('TituloRel', parent=styles['Heading2'], fontSize=10, textColor=colors.black, alignment=1, fontName='Helvetica-Bold', spaceBefore=4, spaceAfter=0)
                        estilo_info_cli = ParagraphStyle('InfoCli', parent=styles['Normal'], fontSize=8, textColor=colors.black, alignment=1, leading=10, spaceAfter=0)
                        
                        estilo_th = ParagraphStyle('TH', parent=styles['Normal'], fontSize=9, textColor=colors.white, alignment=1, fontName='Helvetica-Bold')
                        estilo_td_left = ParagraphStyle('TDLeft', parent=styles['Normal'], fontSize=9, textColor=colors.black, alignment=0)
                        estilo_td_center = ParagraphStyle('TDCenter', parent=styles['Normal'], fontSize=9, textColor=colors.black, alignment=1)
                        estilo_td_right = ParagraphStyle('TDRight', parent=styles['Normal'], fontSize=9, textColor=colors.black, alignment=2)
                        
                        estilo_total_label = ParagraphStyle('TotLabel', parent=styles['Normal'], fontSize=9, textColor=colors.white, alignment=0, fontName='Helvetica-Bold')
                        estilo_total_val = ParagraphStyle('TotVal', parent=styles['Normal'], fontSize=9, textColor=colors.white, alignment=2, fontName='Helvetica-Bold')

                        elements.append(Paragraph("REY DA CEBOLA", estilo_empresa))
                        elements.append(Paragraph("CNPJ: 194.174.39/000-42 INSC.EST.: 12.426725-4<br/>CONTATO: (99) 98814-9722 OU (99) 98414-3943", estilo_sub_empresa))
                        elements.append(Spacer(1, 4))

                        elements.append(Paragraph("Relatório de Pedidos / Orçamentos", estilo_titulo_rel))
                        elements.append(Paragraph(f"<b>Cliente:</b> {st.session_state.cliente_autenticado} | <b>Gerado em:</b> {data_hora_str}", estilo_info_cli))
                        elements.append(Spacer(1, 8))

                        data_tabela = [[
                            Paragraph("Produto", estilo_th),
                            Paragraph("Qtd Total", estilo_th),
                            Paragraph("Preço Unitário (R$)", estilo_th),
                            Paragraph("Valor Total (R$)", estilo_th)
                        ]]

                        for _, row in df_dia.iterrows():
                            data_tabela.append([
                                Paragraph(str(row['produto']), estilo_td_left),
                                Paragraph(f"{row['quantidade']:.2f}", estilo_td_center),
                                Paragraph(f"R$ {row['valor_unitario']:.2f}", estilo_td_right),
                                Paragraph(f"R$ {row['valor_total']:.2f}", estilo_td_right)
                            ])

                        total_geral_dia = df_dia['valor_total'].sum()

                        data_tabela.append([
                            Paragraph("VALOR TOTAL GERAL", estilo_total_label),
                            Paragraph("", estilo_total_val),
                            Paragraph("", estilo_total_val),
                            Paragraph(f"R$ {total_geral_dia:.2f}", estilo_total_val)
                        ])

                        t = Table(data_tabela, colWidths=[220, 80, 110, 130])
                        t.setStyle(TableStyle([
                            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F4E79')),
                            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                            ('TOPPADDING', (0, 0), (-1, -1), 4),
                            ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#CCCCCC')),
                            ('SPAN', (0, -1), (2, -1)),
                            ('BACKGROUND', (0, -1), (-1, -1), colors.black),
                        ]))
                        
                        elements.append(t)
                        doc.build(elements)
                        pdf_bytes = buffer.getvalue()

                        st.download_button(
                            label="📥 Baixar PDF do Dia",
                            data=pdf_bytes,
                            file_name=f"relatorio_pedidos_dia_{st.session_state.cliente_autenticado}.pdf",
                            mime="application/pdf",
                            key="btn_pdf_portal_dia"
                        )
                    except Exception as ex:
                        st.error(f"Erro ao gerar PDF dos pedidos do dia: {ex}")
                else:
                    st.info("Nenhum pedido registrado hoje para edição.")
                    
            except Exception as e:
                st.error(f"Erro ao carregar pedidos do dia: {e}")
                        
            # ==========================================
            # Seção de Histórico de Pedidos do Cliente
            # ==========================================
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
                st.warning("⚠️ Atenção: Não há nenhum caixa aberto no momento. Vá em '🔒 Abertura e Fechamento de Caixa' para abrir o caixa.")
    
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
                    df_todas = carregar_dados("SELECT * FROM vendas")
                    
                    if not df_todas.empty:
                        df_todas['tipo_str'] = df_todas['tipo'].fillna('').astype(str).str.strip().str.upper() if 'tipo' in df_todas.columns else ''
                        df_todas['codigo_str'] = df_todas['codigo'].fillna('').astype(str).str.strip().str.upper() if 'codigo' in df_todas.columns else ''
                        is_venda = df_todas['tipo_str'].isin(['VENDA', 'VENDAS', 'VEN']) | df_todas['codigo_str'].isin(['VEN', 'VENDA'])
                        
                        if status_filtro == "Somente Vendas Concluídas":
                            df_vendas = df_todas[is_venda]
                        elif status_filtro == "Incluir Pedidos Pendentes":
                            df_vendas = df_todas[~is_venda]
                        else:
                            df_vendas = df_todas.copy()
                            
                        if 'data' in df_vendas.columns:
                            df_vendas['data_curta'] = df_vendas['data'].fillna('').astype(str).str.slice(0, 10)
                            mask_data = (df_vendas['data_curta'] >= str_d1) & (df_vendas['data_curta'] <= str_d2)
                            df_vendas = df_vendas[mask_data | (df_vendas['data_curta'] == '')]
                            df_vendas = df_vendas.drop(columns=['data_curta', 'tipo_str', 'codigo_str'], errors='ignore')
                        
                        if not df_vendas.empty:
                            col1, col2, col3 = st.columns(3)
                            faturamento = df_vendas['valor_total'].sum() if 'valor_total' in df_vendas.columns else 0.0
                            valor_rec = pd.to_numeric(df_vendas['valor_recebido'], errors='coerce').sum() if 'valor_recebido' in df_vendas.columns else 0.0
                            
                            col1.metric("Faturamento do Período", f"R$ {faturamento:,.2f}")
                            col2.metric("Total Recebido em Caixa", f"R$ {valor_rec:,.2f}")
                            col3.metric("Total Pendente / Fiado", f"R$ {faturamento - valor_rec:,.2f}")
                            st.markdown("---")
                            st.dataframe(df_vendas, use_container_width=True)
                        else:
                            st.info("Nenhum registro encontrado para os filtros selecionados.")
                    else:
                        st.info("Nenhum dado cadastrado.")
        #INICIO PEDIDOS/ORÇAMENTO#
        elif menu_admin in ["📋 Pedidos / Orçamentos", "🛒 Registrar Venda"]:
            is_modo_pedido = (menu_admin == "📋 Pedidos / Orçamentos")
            st.title(f"🛒 {menu_admin}")

            if not is_modo_pedido:
                aba_cad, aba_baixa, aba_list = st.tabs(["+ Novo Registro", "📋 Baixa de Débito / Haver", "🔧 Tabela Editável"])
            else:
                aba_cad, aba_list = st.tabs(["+ Novo Registro / Pedido", "🔧 Tabela Editável"])
                aba_baixa = None

            with aba_cad:
                clientes_opt = carregar_coluna("clientes", "nome") or ["Carlos Alberto"]
                
                df_p_admin = carregar_dados("SELECT * FROM produtos")
                if not df_p_admin.empty:
                    df_p_admin.columns = [c.lower() for c in df_p_admin.columns]
                    col_nome_p = 'produto' if 'produto' in df_p_admin.columns else ('nome' if 'nome' in df_p_admin.columns else df_p_admin.columns[1])
                    produtos_base = df_p_admin[col_nome_p].dropna().astype(str).str.strip().unique().tolist()
                else:
                    produtos_base = ["ABACATE", "BANANA", "LARANJA", "MAÇÃ"]
                df_p_admin = pd.DataFrame()

                produtos_opt = list(produtos_base) + ["➕ Cadastrar Novo Produto..."]
                fornecedores_opt = carregar_coluna("fornecedores", "fornecedor") or ["BAHIA"]
                grupos_opt = carregar_coluna("grupos", "grupo") or ["GERAL"]

                produto = st.selectbox("Selecione o Produto", options=produtos_opt, key="sel_prod_unico_correto")

                if produto == "➕ Cadastrar Novo Produto...":
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

                cliente = st.selectbox("Cliente", options=clientes_opt, key="sel_cli_unico_correto")
                fornecedor = st.selectbox("Fornecedor", options=fornecedores_opt, key="sel_forn_unico_correto")
                grupo = st.selectbox("Grupo", options=grupos_opt, key="sel_grp_unico_correto")
                
                quantidade = st.number_input("Quantidade", min_value=0.01, value=1.0, step=1.0, key="num_qtd_unico_correto")
                preco_unitario = st.number_input("Preço Unitário (R$)", min_value=0.0, value=80.0, step=1.0, key="num_preco_unico_correto")
            
                if st.button("Salvar PEDIDO", type="primary", key="btn_salvar_pedido_unico_definitivo"):
                    try:
                        import sqlite3
                        con_ins = sqlite3.connect("vendas.db")
                        cur_ins = con_ins.cursor()
                        
                        cur_ins.execute("""
                            CREATE TABLE IF NOT EXISTS vendas (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                cliente TEXT,
                                produto TEXT,
                                quantidade REAL,
                                valor_venda REAL,
                                valor_total REAL,
                                tipo TEXT,
                                status TEXT
                            )
                        """)
                        
                        c_total = float(quantidade) * float(preco_unitario)
                        c_tipo = 'ORÇAMENTO'
                        
                        cur_ins.execute("""
                            INSERT INTO vendas (cliente, produto, quantidade, valor_venda, valor_total, tipo)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (str(cliente), str(produto), float(quantidade), float(preco_unitario), c_total, c_tipo))
                        
                        con_ins.commit()
                        con_ins.close()
                        
                        st.success("Item salvo com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar: {e}")
            
                st.divider()
                st.subheader("🛒 Itens já lançados neste Pedido (Hoje)")
                
                import sqlite3
                try:
                    conn_direto = sqlite3.connect("vendas.db")
                    df_parcial = pd.read_sql("SELECT id, cliente, produto, quantidade, valor_venda as valor_compra, valor_total, tipo, status FROM vendas WHERE status IS NULL OR status != 'Finalizado' ORDER BY id DESC LIMIT 20", conn_direto)
                    conn_direto.close()
                except Exception as e:
                    df_parcial = pd.DataFrame()
            
                if not df_parcial.empty:
                    df_parcial.dropna(axis=1, how='all', inplace=True)
                    if 'excluir' in df_parcial.columns:
                        df_parcial = df_parcial.rename(columns={'excluir': 'Excluir'})
                    if 'Excluir' not in df_parcial.columns:
                        df_parcial.insert(0, 'Excluir', False)
                    else:
                        df_parcial['Excluir'] = False

                    cols_config_parcial = {
                        "Excluir": st.column_config.CheckboxColumn("Excluir", default=False),
                        "quantidade": st.column_config.NumberColumn("Qtd", min_value=0.0, format="%.2f"),
                        "valor_compra": st.column_config.NumberColumn("Vlr Unit", format="R$ %.2f"),
                        "valor_total": st.column_config.NumberColumn("Vlr Total", format="R$ %.2f")
                    }

                    edit_parcial = st.data_editor(
                        df_parcial,
                        column_config=cols_config_parcial,
                        disabled=[c for c in df_parcial.columns if c != 'Excluir' and c != 'quantidade' and c != 'valor_compra'],
                        key=f"editor_parcial_{menu_admin}",
                        use_container_width=True
                    )

                    total_parcial = edit_parcial['valor_total'].sum() if 'valor_total' in edit_parcial.columns else 0.0
                    st.markdown(f"### **Valor Total Acumulado: R$ {total_parcial:.2f}**")
            
                    col_fin, col_del = st.columns([2, 1])
                    
                    with col_fin:
                        if st.button("Finalizar e Enviar Pedido", type="primary", key="btn_finalizar_pedido_unico"):
                            try:
                                con_local = sqlite3.connect("vendas.db")
                                cur = con_local.cursor()
                                for id_item in edit_parcial['id'].tolist():
                                    cur.execute("UPDATE vendas SET status = 'Finalizado', tipo = 'VENDA' WHERE id = ?", (int(id_item),))
                                con_local.commit()
                                con_local.close()
                                st.success("Pedido finalizado com sucesso!")
                                st.balloons()
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao finalizar: {e}")
            
                    with col_del:
                        if st.button("Excluir Selecionados", key="btn_excluir_parcial_sel"):
                            try:
                                ids_a_excluir = []
                                if 'Excluir' in edit_parcial.columns:
                                    ids_a_excluir = edit_parcial[edit_parcial['Excluir'] == True]['id'].dropna().tolist()
                                if ids_a_excluir:
                                    con_local = sqlite3.connect("vendas.db")
                                    cur = con_local.cursor()
                                    for item_id in ids_a_excluir:
                                        cur.execute("DELETE FROM vendas WHERE id = ?", (int(item_id),))
                                    con_local.commit()
                                    con_local.close()
                                    st.success(f"{len(ids_a_excluir)} item(ns) excluído(s) com sucesso!")
                                    st.rerun()
                                else:
                                    st.warning("Nenhum item marcado para exclusão.")
                            except Exception as e:
                                st.error(f"Erro ao excluir: {e}")
                else:
                    st.info("Nenhum registro encontrado na tabela 'vendas'. Faça um lançamento acima para testar.")

            if aba_baixa is not None:
                with aba_baixa:
                    st.subheader("💵 Baixa de Débitos & Lançamento de Haver")
                    clientes_com_divida = carregar_coluna("vendas", "cliente") or []
                    if clientes_com_divida:
                        cliente_baixa = st.selectbox("Selecione o Cliente para Baixa:", clientes_com_divida, key="sel_cli_baixa")
                        df_cli_vendas = carregar_dados(f"SELECT * FROM vendas WHERE TRIM(cliente) = TRIM('{cliente_baixa}')")
                        
                        if not df_cli_vendas.empty:
                            tot_vendas = df_cli_vendas['valor_total'].sum()
                            tot_recebido = pd.to_numeric(df_cli_vendas['valor_recebido'], errors='coerce').fillna(0.0).sum() if 'valor_recebido' in df_cli_vendas.columns else 0.0
                            total_pendente = tot_vendas - tot_recebido
                            
                            col_m1, col_m2, col_m3 = st.columns(3)
                            col_m1.metric("Total de Compras", f"R$ {tot_vendas:,.2f}")
                            col_m2.metric("Total Já Pago", f"R$ {tot_recebido:,.2f}")
                            col_m3.metric("Saldo Devedor Restante", f"R$ {total_pendente:,.2f}", delta_color="inverse")
                            
                            st.markdown("---")
                            st.markdown(f"### 📋 Detalhamento das Vendas / Débitos de **{cliente_baixa}**")
                            
                            df_exibicao_cli = df_cli_vendas.copy()
                            if 'valor_recebido' not in df_exibicao_cli.columns:
                                df_exibicao_cli['valor_recebido'] = 0.0
                            df_exibicao_cli['saldo_devedor'] = df_exibicao_cli['valor_total'] - pd.to_numeric(df_exibicao_cli['valor_recebido'], errors='coerce').fillna(0.0)
                            
                            cols_mostrar = [c for c in ['id', 'data', 'produto', 'quantidade', 'valor_total', 'valor_recebido', 'saldo_devedor', 'status'] if c in df_exibicao_cli.columns]
                            st.dataframe(df_exibicao_cli[cols_mostrar], use_container_width=True)
                            
                            st.markdown("---")
                            valor_haver = st.number_input("Valor do Haver / Pagamento Recebido (R$)", min_value=0.0, step=1.0, value=0.0, key="val_haver_input")
                            forma_pgto_baixa = st.selectbox("Forma de Pagamento", ["Dinheiro", "Pix", "Cartão de Crédito à Vista", "Cartão de Débito"], key="fp_haver_input")
                            
                            if st.button("Aplicar Haver"):
                                if valor_haver > 0:
                                    baixar_debito_cliente(cliente_baixa, valor_haver, forma_pagamento=forma_pgto_baixa)
                                    st.success(f"Haver de R$ {valor_haver:,.2f} aplicado com sucesso!")
                                    st.rerun()

            with aba_list:
                st.subheader("🔍 Edição Direta na Tabela & Gestão por Cliente")
                
                clientes_filtro = ["TODOS"] + (carregar_coluna("clientes", "nome") or carregar_coluna("vendas", "cliente") or [])
                
                col_f1, col_f2, col_f3 = st.columns(3)
                with col_f1:
                    cliente_sel = st.selectbox("Filtrar por Cliente:", clientes_filtro, key=f"filtro_cli_tabela_{menu_admin}")
                with col_f2:
                    d_inicio = st.date_input("Data Inicial do Filtro", value=date(2025, 1, 1), key=f"filtro_d_ini_{menu_admin}")
                with col_f3:
                    d_fin = st.date_input("Data Final do Filtro", value=date.today(), key=f"filtro_d_fim_{menu_admin}")

                texto_botao_atualizar = "🔄 Atualizar Preços de Venda" if not is_modo_pedido else "🔄 Atualizar Preços de Custo"
                if st.button(texto_botao_atualizar, key=f"btn_atualizar_precos_{menu_admin}"):
                    cursor = conn.cursor()
                    coluna_alvo_estoque = 'valor_venda' if not is_modo_pedido else 'valor_compra'
                    
                    cursor.execute(f"""
                        UPDATE vendas 
                        SET valor_venda = (
                            SELECT {coluna_alvo_estoque} 
                            FROM produtos 
                            WHERE TRIM(UPPER(produtos.nome)) = TRIM(UPPER(vendas.produto))
                        ),
                        valor_total = quantidade * (
                            SELECT {coluna_alvo_estoque} 
                            FROM produtos 
                            WHERE TRIM(UPPER(produtos.nome)) = TRIM(UPPER(vendas.produto))
                        )
                        WHERE TRIM(UPPER(produto)) IN (SELECT TRIM(UPPER(nome)) FROM produtos)
                    """)
                    linhas_afetadas = cursor.rowcount
                    conn.commit()
                    
                    if linhas_afetadas > 0:
                        st.success(f"Preços atualizados com sucesso! ({linhas_afetadas} itens modificados)")
                    else:
                        st.warning("Nenhum produto correspondente foi encontrado na tabela de estoque para atualizar.")
                    
                    st.rerun()
                
                st.markdown("---")
                s_d1, s_d2 = d_inicio.strftime("%Y-%m-%d"), d_fin.strftime("%Y-%m-%d")
                
                tabela_alvo_historico = 'pedidos' if 'pedidos' in [t[0] for t in conn.cursor().execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()] else 'vendas'
                
                query_filt = f"SELECT * FROM {tabela_alvo_historico}"
                df_registros = carregar_dados(query_filt)
                
                if not df_registros.empty:
                    df_registros.columns = [c.lower() for c in df_registros.columns]
                    
                    if 'data' in df_registros.columns:
                        df_registros['data_str'] = df_registros['data'].astype(str).str.slice(0, 10)
                        df_registros = df_registros[(df_registros['data_str'] >= s_d1) & (df_registros['data_str'] <= s_d2)]
                    
                    if cliente_sel != "TODOS" and 'cliente' in df_registros.columns:
                        df_registros = df_registros[df_registros['cliente'].astype(str).str.strip().str.upper() == str(cliente_sel).strip().upper()]

                    data_hoje_str = datetime.now().strftime("%Y-%m-%d")
                    
                    if 'data_str' in df_registros.columns:
                        df_dia = df_registros[df_registros['data_str'] == data_hoje_str]
                        df_historico = df_registros[df_registros['data_str'] != data_hoje_str]
                    else:
                        df_dia = pd.DataFrame()
                        df_historico = df_registros

                    st.subheader("🟢 Pedidos do Dia (Editáveis — Admin)")

                    # Inicializa o dataframe vazio por segurança para evitar NameError
                    df_admin_dia = pd.DataFrame()
                    
                    try:
                        conn_admin = sqlite3.connect("vendas.db")
                        query_admin = """
                            SELECT id, cliente, produto, quantidade, valor_venda as valor_unitario, valor_total, fornecedor, grupo, data, status 
                            FROM vendas 
                            WHERE (status = 'ORÇAMENTO' OR status IS NULL OR status = '' OR status LIKE '%Pendente%')
                               OR (data LIKE '2026-09-06%' AND status NOT LIKE '%Concluído%')
                            ORDER BY id DESC
                        """
                        df_admin_dia = pd.read_sql(query_admin, conn_admin)
                        conn_admin.close()
                    except Exception as e:
                        df_admin_dia = pd.DataFrame()
                    
                    if df_admin_dia.empty:
                        st.info("Nenhum pedido pendente no momento.")
                    else:
                        # Resto da tabela editável e botões...
                        if 'Excluir' not in df_admin_dia.columns:
                            df_admin_dia.insert(0, 'Excluir', False)
                        else:
                            df_admin_dia['Excluir'] = False
                    
                        cols_config_admin = {
                            "Excluir": st.column_config.CheckboxColumn("Excluir?", default=False),
                            "id": "ID",
                            "cliente": "Cliente",
                            "produto": "Produto",
                            "quantidade": st.column_config.NumberColumn("Quantidade", min_value=0.0, format="%.2f"),
                            "valor_unitario": st.column_config.NumberColumn("Valor Unitário (R$)", format="R$ %.2f"),
                            "valor_total": st.column_config.NumberColumn("Total (R$)", format="R$ %.2f"),
                            "fornecedor": "Fornecedor",
                            "grupo": "Grupo",
                            "data": "Data",
                            "status": "Status"
                        }
                    
                        edit_admin_dia = st.data_editor(
                            df_admin_dia,
                            column_config=cols_config_admin,
                            disabled=[c for c in df_admin_dia.columns if c != 'Excluir' and c != 'quantidade' and c != 'valor_unitario'],
                            key="editor_admin_pedidos_dia",
                            use_container_width=True
                        )
                    
                        col_btn1, col_btn2, col_btn3 = st.columns(3)
                        
                        with col_btn1:
                            if st.button("Salvar Alterações", key="btn_salvar_alt_admin_dia"):
                                try:
                                    con_up = sqlite3.connect("vendas.db")
                                    cur_up = con_up.cursor()
                                    for index, row in edit_admin_dia.iterrows():
                                        item_id = row['id']
                                        nova_qtd = row['quantidade']
                                        novo_vlr = row['valor_unitario']
                                        novo_total = nova_qtd * novo_vlr
                                        cur_up.execute("""
                                            UPDATE vendas 
                                            SET quantidade = ?, valor_venda = ?, valor_total = ? 
                                            WHERE id = ?
                                        """, (nova_qtd, novo_vlr, novo_total, int(item_id)))
                                    con_up.commit()
                                    con_up.close()
                                    st.success("Alterações salvas com sucesso!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Erro ao salvar: {e}")
                    
                        with col_btn2:
                            if st.button("Finalizar Pedido / Venda", type="primary", key="btn_finalizar_admin_dia"):
                                try:
                                    con_fin = sqlite3.connect("vendas.db")
                                    cur_fin = con_fin.cursor()
                                    cur_fin.execute("""
                                        UPDATE vendas 
                                        SET status = 'Concluído (Convertido)', tipo = 'VENDA' 
                                        WHERE status = 'ORÇAMENTO' OR status IS NULL OR status = '' OR status LIKE '%Pendente%'
                                    """)
                                    afetados = cur_fin.rowcount
                                    con_fin.commit()
                                    con_fin.close()
                                    if afetados > 0:
                                        st.success(f"{afetados} pedido(s) finalizado(s) e movido(s) para o histórico com sucesso!")
                                        st.rerun()
                                    else:
                                        st.warning("Nenhum pedido pendente para finalizar.")
                                except Exception as e:
                                    st.error(f"Erro ao finalizar: {e}")
                    
                        with col_btn3:
                            if st.button("Excluir Marcados", key="btn_excluir_marcados_admin_dia"):
                                try:
                                    ids_excluir = edit_admin_dia[edit_admin_dia['Excluir'] == True]['id'].tolist()
                                    if ids_excluir:
                                        con_del = sqlite3.connect("vendas.db")
                                        cur_del = con_del.cursor()
                                        for i_id in ids_excluir:
                                            cur_del.execute("DELETE FROM vendas WHERE id = ?", (int(i_id),))
                                        con_del.commit()
                                        con_del.close()
                                        st.success(f"{len(ids_excluir)} item(ns) excluído(s)!")
                                        st.rerun()
                                    else:
                                        st.warning("Nenhum item selecionado para exclusão.")
                                except Exception as e:
                                    st.error(f"Erro ao excluir: {e}")
                            
                            try:
                                conn_hist = sqlite3.connect("vendas.db")
                                query_hist_admin = """
                                    SELECT id, cliente, produto, quantidade, valor_venda as valor_unitario, valor_total, status, observacoes, data, fornecedor, grupo, codigo_pedido, data_str 
                                    FROM vendas 
                                    WHERE status LIKE '%Concluído%' OR status LIKE '%Convertido%' 
                                    ORDER BY id DESC
                                """
                                df_historico = pd.read_sql(query_hist_admin, conn_hist)
                                conn_hist.close()
                            except Exception as e:
                                df_historico = pd.DataFrame()
                            
                            st.markdown("---")
                            st.subheader("Histórico de Pedidos anteriores")

                    st.markdown("---")
                    st.subheader("📚 Histórico de Pedidos anteriores")
                    if not df_historico.empty:
                        df_historico.dropna(axis=1, how='all', inplace=True)
                        if 'excluir' in df_historico.columns:
                            df_historico = df_historico.rename(columns={'excluir': 'Excluir'})
                        if 'Excluir' not in df_historico.columns:
                            df_historico.insert(0, 'Excluir', False)
                        else:
                            df_historico['Excluir'] = False

                        cols_config_hist = {
                            "Excluir": st.column_config.CheckboxColumn("Excluir", default=False),
                            "quantidade": st.column_config.NumberColumn("Qtd", min_value=0.0, format="%.2f"),
                            "valor_total": st.column_config.NumberColumn("Vlr Total", format="R$ %.2f")
                        }

                        edit_hist = st.data_editor(
                            df_historico,
                            column_config=cols_config_hist,
                            disabled=[c for c in df_historico.columns if c != 'Excluir' and c != 'quantidade'],
                            key=f"editor_pedidos_hist_{menu_admin}",
                            use_container_width=True
                        )

                        col_salvar_hist, col_excluir_hist = st.columns(2)
                        with col_salvar_hist:
                            if st.button("💾 Salvar Alterações (Histórico)", key=f"btn_salvar_hist_{menu_admin}"):
                                try:
                                    cursor_upd = conn.cursor()
                                    for idx, row in edit_hist.iterrows():
                                        if 'id' in row and pd.notna(row['id']):
                                            item_id = int(row['id'])
                                            qtd_nova = float(row.get('quantidade', 0))
                                            vlr_unit = float(row.get('valor_venda', row.get('valor_unitario', 0)))
                                            vlr_tot_novo = qtd_nova * vlr_unit
                                            cursor_upd.execute(
                                                f"UPDATE {tabela_alvo_historico} SET quantidade = ?, valor_total = ? WHERE id = ?",
                                                (qtd_nova, vlr_tot_novo, item_id)
                                            )
                                    conn.commit()
                                    st.success("Alterações do histórico salvas com sucesso!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Erro ao salvar alterações do histórico: {e}")

                        with col_excluir_hist:
                            if st.button("🗑️ Excluir Selecionados (Histórico)", key=f"btn_excluir_hist_{menu_admin}"):
                                try:
                                    ids_a_excluir_hist = []
                                    if 'Excluir' in edit_hist.columns:
                                        ids_a_excluir_hist = edit_hist[edit_hist['Excluir'] == True]['id'].dropna().tolist()
                                    if ids_a_excluir_hist:
                                        cursor_del = conn.cursor()
                                        for item_id in ids_a_excluir_hist:
                                            cursor_del.execute(f"DELETE FROM {tabela_alvo_historico} WHERE id = ?", (int(item_id),))
                                        conn.commit()
                                        st.success(f"{len(ids_a_excluir_hist)} item(ns) do histórico excluído(s) com sucesso!")
                                        st.rerun()
                                    else:
                                        st.warning("Nenhum item marcado para exclusão no histórico.")
                                except Exception as e:
                                    st.error(f"Erro ao excluir itens do histórico: {e}")
                    else:
                        st.info("Nenhum registro no histórico para o período selecionado.")
                else:
                    st.info("Nenhum registro encontrado para os filtros aplicados.")
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
                                    INSERT INTO produtos (produto, nome, quantidade, estoque_atual, valor_compra, valor_venda, grupo, fornecedor)
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
                                        SET produto = ?, quantidade = ?, estoque_atual = ?, valor_compra = ?, valor_venda = ?, grupo = ?, fornecedor = ?
                                        WHERE id = ?
                                    """, (p_prod, p_qtd, p_qtd, p_compra, p_venda, p_grupo, p_forn, p_id))
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
                                cursor.execute("DELETE FROM produtos WHERE produto = ?", (prod_selecionado_excluir,))
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
                            
                            st.dataframe(carregar_dados("SELECT * FROM grupos"), use_container_width=True, hide_index=True)            
        elif menu_admin == "📥 Entrada de Estoque (Compras)":
            st.title("📥 Entrada de Estoque (Compras)")
            aba_compra, aba_historico_compras = st.tabs(["📦 Dar Entrada em Estoque", "📋 Histórico de Entradas"])
            
            # Padronizado para usar 'nome' na tabela produtos
            produtos_opt = carregar_coluna("produtos", "nome") or carregar_coluna("produtos", "produto") or ["AMEIXA IMPORTADA", "ABACATE"]
            fornecedores_opt = carregar_coluna("fornecedores", "fornecedor") or ["BAHIA"]
            grupos_opt = carregar_coluna("grupos", "grupo") or ["GERAL"]
            
            with aba_compra:
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
                            cursor.execute("SELECT valor_venda FROM produtos WHERE nome = ? OR produto = ?", (produto_escolhido, produto_escolhido))
                            resultado = cursor.fetchone()
                            if resultado and resultado[0] is not None:
                                preco_cadastrado = float(resultado[0])
                        except Exception:
                            pass
    
                    preco_custo = st.number_input("Preço de Custo Unitário (R$)", min_value=0.0, format="%.2f", key="custo_entrada")
                    preco_venda = st.number_input("Preço de Venda Unitário (R$)", min_value=0.0, value=preco_cadastrado, format="%.2f", key="venda_entrada")
    
                if st.button("💾 Confirmar Entrada no Estoque", type="primary", key="btn_conf_entrada"):
                    if not produto_final:
                        st.warning("Informe ou selecione o nome do produto.")
                    else:
                        try:
                            cursor = conn.cursor()
                            cursor.execute("SELECT id FROM produtos WHERE nome = ? OR produto = ?", (produto_final, produto_final))
                            existe = cursor.fetchone()
                            
                            data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if 'datetime' in globals() else ""
                            
                            if existe:
                                cursor.execute("""
                                    UPDATE produtos 
                                    SET estoque_atual = COALESCE(estoque_atual, 0) + ?, valor_compra = ?, valor_venda = ?, grupo = ?, fornecedor = ?
                                    WHERE nome = ? OR produto = ?
                                """, (quantidade_entrada, preco_custo, preco_venda, grupo_escolhido, fornecedor_escolhido, produto_final, produto_final))
                            else:
                                cursor.execute("""
                                    INSERT INTO produtos (nome, produto, estoque_atual, quantidade, valor_compra, valor_venda, grupo, fornecedor)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                """, (produto_final, produto_final, quantidade_entrada, quantidade_entrada, preco_custo, preco_venda, grupo_escolhido, fornecedor_escolhido))
                            
                            # Registrar também na tabela compras se existir
                            try:
                                cursor.execute("""
                                    INSERT INTO compras (produto, fornecedor, grupo, quantidade, valor_custo, valor_total, data)
                                    VALUES (?, ?, ?, ?, ?, ?, ?)
                                """, (produto_final, fornecedor_escolhido, grupo_escolhido, quantidade_entrada, preco_custo, quantidade_entrada * preco_custo, data_atual))
                            except Exception:
                                pass

                            conn.commit()
                            st.success(f"Estoque atualizado/produto '{produto_final}' cadastrado com sucesso!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao registrar entrada: {e}")

            with aba_historico_compras:
                st.subheader("📋 Histórico de Entradas de Estoque")
                try:
                    df_compras = carregar_dados("SELECT * FROM compras")
                    if not df_compras.empty:
                        st.dataframe(df_compras, use_container_width=True, hide_index=True)
                    else:
                        st.info("Nenhuma entrada de estoque registrada no histórico.")
                except Exception as e:
                    st.error(f"Erro ao carregar histórico de compras: {e}")
                
