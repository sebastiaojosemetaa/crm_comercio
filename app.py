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
            fornecedor TEXT,
            grupo TEXT,
            valor_compra REAL,
            valor_venda REAL,
            estoque_atual REAL
        )
    """)
    cursor.execute("PRAGMA table_info(produtos)")
    colunas_produtos = [col[1] for col in cursor.fetchall()]

    if 'fornecedor' not in colunas_produtos:
        try:
            cursor.execute("ALTER TABLE produtos ADD COLUMN fornecedor TEXT")
        except:
            pass

    if 'grupo' not in colunas_produtos:
        try:
            cursor.execute("ALTER TABLE produtos ADD COLUMN grupo TEXT")
        except:
            pass

    if 'valor_compra' not in colunas_produtos:
        try:
            cursor.execute("ALTER TABLE produtos ADD COLUMN valor_compra REAL")
        except:
            pass

    if 'valor_venda' not in colunas_produtos:
        try:
            cursor.execute("ALTER TABLE produtos ADD COLUMN valor_venda REAL")
        except:
            pass

    if 'estoque_atual' not in colunas_produtos:
        try:
            cursor.execute("ALTER TABLE produtos ADD COLUMN estoque_atual REAL")
        except:
            pass 
    cursor.execute("PRAGMA table_info(produtos)")
    colunas_produtos = [col[1] for col in cursor.fetchall()]
    if 'nome' not in colunas_produtos and 'descricao' in colunas_produtos:
        try:
            cursor.execute("ALTER TABLE produtos RENAME COLUMN descricao TO nome")
        except:
            pass
    elif 'nome' not in colunas_produtos:
        try:
            cursor.execute("ALTER TABLE produtos ADD COLUMN nome TEXT")
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

def sincronizar_valores_com_estoque(tabela_alvo, tipo_preco="venda"):
    cursor = conn.cursor()
    df_produtos = carregar_dados("SELECT * FROM produtos")
    if df_produtos.empty:
        return
    
    cols_prod = df_produtos.columns.tolist()
    col_p_nome = 'nome' if 'nome' in cols_prod else cols_prod[1]
    
    if tipo_preco == "venda":
        col_p_preco = 'valor_venda' if 'valor_venda' in cols_prod else ('preco_venda' if 'preco_venda' in cols_prod else [c for c in cols_prod if 'venda' in c or 'preco' in c][-1])
    else:
        col_p_preco = 'valor_compra' if 'valor_compra' in cols_prod else ('preco_custo' if 'preco_custo' in cols_prod else [c for c in cols_prod if 'custo' in c or 'compra' in c][-1])

    df_registros = carregar_dados(f"SELECT id, produto, quantidade as qtd FROM {tabela_alvo}")
    
    for _, row in df_registros.iterrows():
        prod_nome = row['produto']
        mask = df_produtos[col_p_nome].astype(str).str.strip() == str(prod_nome).strip()
        preco_atual = df_produtos.loc[mask, col_p_preco]
        
        if not preco_atual.empty:
            p = float(preco_atual.iloc[0])
            total = p * row['qtd']
            cursor.execute(f"UPDATE {tabela_alvo} SET valor_venda = ?, valor_total = ? WHERE id = ?", (p, total, row['id']))
    
    conn.commit()

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
        cursor.execute(f"PRAGMA table_info({tabela})")
        colunas_existentes = [col[1] for col in cursor.fetchall()]
        
        if not colunas_existentes:
            cursor.execute(f"CREATE TABLE IF NOT EXISTS {tabela} (id INTEGER PRIMARY KEY AUTOINCREMENT, {coluna} TEXT UNIQUE)")
            conn.commit()
            coluna_alvo = coluna
        else:
            coluna_alvo = coluna if coluna in colunas_existentes else colunas_existentes[-1]

        cursor.execute(f"INSERT INTO {tabela} ({coluna_alvo}) VALUES (?)", (valor.strip(),))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    except Exception as e:
        st.error(f"Erro ao salvar em {tabela}: {e}")
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

def converter_pedido_completo_para_venda(cliente_nome):
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE vendas 
        SET tipo = 'VENDA', codigo = 'VEN' 
        WHERE TRIM(cliente) = TRIM(?)
    """, (cliente_nome,))
    conn.commit()
    return cursor.rowcount

def deletar_pedidos_cliente(cliente_nome, s_d1, s_d2):
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM vendas 
        WHERE TRIM(cliente) = TRIM(?) 
          AND (substr(data, 1, 10) >= ? AND substr(data, 1, 10) <= ? OR data IS NULL OR data = '')
    """, (cliente_nome, s_d1, s_d2))
    conn.commit()
    return cursor.rowcount

def registrar_compra(produto, fornecedor, grupo, quantidade, valor_custo):
    cursor = conn.cursor()
    valor_total = quantidade * valor_custo
    data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO compras (produto, fornecedor, grupo, quantidade, valor_custo, valor_total, data)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (produto, fornecedor, grupo, quantidade, valor_custo, valor_total, data_atual))
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

    table_data = [["Produto", "Qtd Total", "Preço Unitário (R$)", "Valor Total (R$)"]]
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
        aba_novo, aba_historico = st.tabs(["➕ Criar Novo Pedido", "📜 Pedidos Registrados & Relatórios"])
        
        with aba_novo:
            st.subheader("➕ Registrar Novo Pedido")
            produtos_opt = carregar_coluna("produtos", "nome") or ["AMEIXA IMPORTADA", "ABACATE", "CEBOLA CAIXA 1"]
            fornecedores_opt = carregar_coluna("fornecedores", "fornecedor") or ["BAHIA"]
            grupos_opt = carregar_coluna("grupos", "grupo") or ["GERAL"]
            
            with st.form("form_novo_pedido_cliente"):
                prod = st.selectbox("Selecione o Produto", produtos_opt)
                fornec = st.selectbox("Selecione o Fornecedor", fornecedores_opt)
                grupo = st.selectbox("Selecione o Grupo", grupos_opt)
                qtd = st.number_input("Quantidade", min_value=0.1, step=0.5, value=1.0)
                v_unit = st.number_input("Preço de Custo (R$)", min_value=0.0, step=1.0, value=100.0)
                
                if st.form_submit_button("Confirmar Pedido"):
                    salvar_pedido_ou_venda(st.session_state.cliente_autenticado, prod, fornec, grupo, qtd, v_unit, tipo="PEDIDO")
                    st.success("Pedido registrado com sucesso!")
                    st.rerun()

        with aba_historico:
            st.subheader(f"Meus Pedidos e Orçamentos ({st.session_state.cliente_autenticado})")
            
            df_cli_pedidos = carregar_dados("SELECT * FROM vendas")
            
            if not df_cli_pedidos.empty and 'cliente' in df_cli_pedidos.columns:
                nome_pesq = str(st.session_state.cliente_autenticado).strip().lower()
                df_cli_pedidos = df_cli_pedidos[df_cli_pedidos['cliente'].astype(str).str.strip().str.lower().str.contains(nome_pesq, na=False)]
            
            if not df_cli_pedidos.empty:
                codigos = df_cli_pedidos['codigo_venda'].dropna().unique() if 'codigo_venda' in df_cli_pedidos.columns else []
                
                for cod in codigos:
            df_item_venda = df_cli_pedidos[df_cli_pedidos['codigo_venda'] == cod]
            data_venda = df_item_venda['data'].iloc[0] if 'data' in df_item_venda.columns else ""
            
            col_t_item = next((c for c in df_item_venda.columns if "valor" in c.lower() and "total" in c.lower()), "Valor Total")
            val_total = df_item_venda[col_t_item].sum() if col_t_item in df_item_venda.columns else 0.0

        with st.expander(f"🛒 Pedido ID: {cod} | Data: {data_venda} | Total: R$ {val_total:,.2f}"):
            cols_desejadas = ['id', 'produto', 'fornecedor', 'qtd', col_t_item, 'grupo']
            cols_existentes = [c for c in cols_desejadas if c in df_item_venda.columns]
            st.dataframe(df_item_venda[cols_existentes], use_container_width=True)
                
                if len(codigos) == 0:
                    df_edit_cli = df_cli_pedidos.copy()
                    if 'Deletar' not in df_edit_cli.columns:
                        df_edit_cli.insert(0, 'Deletar', False)

                    df_atualizado_cliente = st.data_editor(
                        df_edit_cli,
                        num_rows="dynamic",
                        use_container_width=True,
                        key="editor_pedidos_cliente_direto"
                    )
                    
                    col_salvar_cli, col_del_cli = st.columns(2)
                    
                    with col_salvar_cli:
                        if st.button("💾 Salvar Alterações Feitas na Tabela", use_container_width=True, key="btn_salv_cli_dir"):
                            try:
                                cursor = conn.cursor()
                                for index, row in df_atualizado_cliente.iterrows():
                                    qtd = float(row.get('quantidade', 1))
                                    v_unit = float(row.get('valor_venda', row.get('valor_unitario', 0)))
                                    v_total = qtd * v_unit
                                    
                                    cursor.execute("""
                                        UPDATE vendas 
                                        SET quantidade = ?, valor_total = ? 
                                        WHERE id = ?
                                    """, (qtd, v_total, row.get('id')))
                                conn.commit()
                                st.success("Alterações salvas com sucesso!")
                                st.rerun()
                            except Exception as ex:
                                st.error(f"Erro ao salvar alterações: {ex}")
                                
                    with col_del_cli:
                        itens_para_excluir = df_atualizado_cliente[df_atualizado_cliente['Deletar'] == True]
                        qtd_del = len(itens_para_excluir)
                        if st.button(f"🗑️ Confirmar Exclusão de ({qtd_del}) Item(ns) Marcados", use_container_width=True, key="btn_del_cli_dir"):
                            if qtd_del > 0:
                                cursor = conn.cursor()
                                for _, row in itens_para_excluir.iterrows():
                                    cursor.execute("DELETE FROM vendas WHERE id = ?", (row.get('id'),))
                                conn.commit()
                                st.warning(f"{qtd_del} item(ns) excluído(s) com sucesso!")
                                st.rerun()
                            else:
                                st.info("Marque a caixa 'Deletar' nos itens que deseja remover.")

                st.markdown("---")
                st.markdown(f"### 📄 Relatório do Cliente ({st.session_state.cliente_autenticado})")
                
                try:
                    pdf_bytes = gerar_pdf_tabela_pedidos(df_cli_pedidos, st.session_state.cliente_autenticado)
                    st.download_button(
                        label=f"📥 Baixar Relatório em PDF Corporativo - {st.session_state.cliente_autenticado}",
                        data=pdf_bytes,
                        file_name=f"Relatorio_Pedidos_{st.session_state.cliente_autenticado}.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                        key="btn_baixar_pdf_corporativo_cliente"
                    )
                except Exception as e:
                    st.error(f"Erro ao gerar o PDF corporativo: {e}")
            else:
                st.info(f"Nenhum pedido encontrado para '{st.session_state.cliente_autenticado}'.")

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
        
        # --- LÓGICA: PDV — FRENTE DE CAIXA COM CARRINHO DE MÚLTIPLOS ITENS ---
        if menu_admin == "🛒 PDV — Frente de Caixa":
            st.title("🛒 PDV — Frente de Caixa (Múltiplos Produtos)")
            
            df_caixa_aberto = carregar_dados("SELECT * FROM caixa_sessoes WHERE status = 'ABERTO'")
            if df_caixa_aberto.empty:
                st.warning("⚠️ Atenção: Não há nenhum caixa aberto no momento. Vá em '🔓 Abertura e Fechamento de Caixa' para abrir o caixa antes de registrar vendas.")
            
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

            st.markdown("#### + Adicionar Item ao Carrinho")
            
            prod_item = st.selectbox("Produto", produtos_opt, key="pdv_select_produto")

            preco_sugerido = 0.0
            forn_sugerido = fornecedores_opt[0]
            grupo_sugerido = grupos_opt[0]

            if not df_p.empty:
                df_p['_nome_limpo'] = df_p[col_nome_p].astype(str).str.strip().str.upper()
                target_nome = str(prod_item).strip().upper()
                
                df_filtrado_p = df_p[df_p['_nome_limpo'] == target_nome]
                
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
                idx_f = fornecedores_opt.index(forn_sugerido) if forn_sugerido in fornecedores_opt else 0
                fornec_item = st.selectbox("Fornecedor", fornecedores_opt, index=idx_f, key="pdv_forn_input")
                
                idx_g = grupos_opt.index(grupo_sugerido) if grupo_sugerido in grupos_opt else 0
                grupo_item = st.selectbox("Grupo", grupos_opt, index=idx_g, key="pdv_grupo_input")
            
            with col_s2:
                qtd_item = st.number_input("Quantidade", min_value=0.1, step=1.0, value=1.0, key="pdv_qtd")
                
                v_unit_item = st.number_input(
                    "Preço de Venda (R$)", 
                    min_value=0.0, 
                    step=1.0, 
                    value=float(preco_sugerido),
                    key=f"vunit_{prod_item}"
                )
            
            valor_total_item = qtd_item * v_unit_item
            st.metric("Valor Total do Item", f"R$ {valor_total_item:.2f}")
            
            if st.button("➕ Incluir Produto no Carrinho", type="primary"):
                st.session_state.carrinho_pdv.append({
                    "produto": prod_item,
                    "fornecedor": fornec_item,
                    "grupo": grupo_item,
                    "quantidade": qtd_item,
                    "valor_venda": v_unit_item,
                    "valor_total": valor_total_item
                })
                st.success(f"Item '{prod_item}' adicionado ao carrinho!")
                st.rerun()

            st.markdown("---")
            st.subheader("🛒 Itens Atuais no Carrinho")
            if len(st.session_state.carrinho_pdv) > 0:
                df_carrinho = pd.DataFrame(st.session_state.carrinho_pdv)
                st.dataframe(df_carrinho, use_container_width=True)
                total_geral_carrinho = df_carrinho['valor_total'].sum()
            else:
                total_geral_carrinho = 0.0

            if st.button("🗑️ Limpar Carrinho"):
                st.session_state.carrinho_pdv = []
                st.rerun()

            st.markdown("---")       
            with st.form("form_finalizar_pagamento_pdv"):
                f_pag = st.selectbox("Forma de Pagamento", ["Dinheiro", "Pix", "Cartão de Crédito à Vista", "Cartão de Débito", "Crediário / Fiado"])
                v_rec = st.number_input("Valor Recebido (R$)", min_value=0.0, step=1.0, value=float(total_geral_carrinho))
                
                troco = v_rec - total_geral_carrinho
                
                st.markdown("---")
                c_inf1, c_inf2 = st.columns(2)
                c_inf1.metric("Valor Total da Venda", f"R$ {total_geral_carrinho:,.2f}")
                c_inf2.metric("Troco", f"R$ {max(0.0, troco):,.2f}", delta_color="normal" if troco >= 0 else "inverse")
                
                if st.form_submit_button("Finalizar Venda no PDV"):
                    if not df_caixa_aberto.empty and len(st.session_state.carrinho_pdv) > 0:
                        sessao_id = int(df_caixa_aberto.iloc[0]['id'])
                        
                        for item in st.session_state.carrinho_pdv:
                            salvar_pedido_ou_venda(
                                cliente=cliente_pdv,
                                produto=item['produto'],
                                fornecedor=item['fornecedor'],
                                grupo=item['grupo'],
                                quantidade=item['quantidade'],
                                valor_venda=item['valor_venda'],
                                forma_pagamento=f_pag,
                                valor_recebido=v_rec,
                                tipo="VENDA"
                            )
                        
                        cursor = conn.cursor()
                        cursor.execute("INSERT INTO caixa_movimentacoes (sessao_id, tipo, valor, descricao, data) VALUES (?, ?, ?, ?, ?)",
                            (sessao_id, "VENDA", total_geral_carrinho, f"Venda PDV (Múltiplos Itens) - Cliente: {cliente_pdv}", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                        conn.commit()
                        
                        st.session_state.carrinho_pdv = []
                        st.success(f"Venda realizada com sucesso! Troco: R$ {max(0.0, troco):,.2f}")
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
                else:
                    st.info("Nenhuma movimentação registrada neste caixa ainda.")
                
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
                else:
                    df_vendas = pd.DataFrame()
                
                if not df_vendas.empty:
                    col1, col2, col3 = st.columns(3)
                    faturamento = df_vendas['valor_total'].sum() if 'valor_total' in df_vendas.columns else 0.0
                    
                    if 'valor_recebido' in df_vendas.columns:
                        valor_rec = pd.to_numeric(df_vendas['valor_recebido'], errors='coerce').sum()
                    else:
                        valor_rec = 0.0
                    
                    col1.metric("Faturamento do Período", f"R$ {faturamento:,.2f}")
                    col2.metric("Total Recebido em Caixa", f"R$ {valor_rec:,.2f}")
                    col3.metric("Total Pendente / Fiado", f"R$ {faturamento - valor_rec:,.2f}")
                    st.markdown("---")
                
                    st.subheader("📊 Registros Encontrados")
                    st.dataframe(df_vendas, use_container_width=True)
                
                    st.markdown("---")
                    st.subheader("📄 Gerar Relatório do Fechamento Financeiro em PDF")
                    pdf_fechamento = gerar_pdf_tabela_pedidos(
                        df_vendas, 
                        cliente_nome="Geral", 
                        d_inicio=data_inicio, 
                        d_fim=data_fim,
                        titulo_custom=f"Fechamento Financeiro ({status_filtro})"
                    )
                
                    st.download_button(
                        label="📥 Baixar Relatório de Fechamento Financeiro (PDF)",
                        data=pdf_fechamento,
                        file_name=f"Fechamento_Financeiro_{str_d1}_a_{str_d2}.pdf",
                        mime="application/pdf"
                    )
                else:
                    st.info("Nenhum registro encontrado para os filtros selecionados.")
            else:
                st.info("Nenhum dado cadastrado.")

        elif menu_admin in ["📋 Pedidos / Orçamentos", "🛒 Registrar Venda"]:
            is_modo_pedido = (menu_admin == "📋 Pedidos / Orçamentos")
            st.title(f"🛒 {menu_admin}")

            if not is_modo_pedido:
                aba_cad, aba_baixa, aba_list = st.tabs(["+ Novo Registro", "📋 Baixa de Débito / Haver", "🔧 Tabela Editável (Edição Direta & Exclusão)"])
            else:
                aba_cad, aba_list = st.tabs(["+ Novo Registro / Pedido", "🔧 Tabela Editável (Edição Direta & Exclusão)"])
                aba_baixa = None

            with aba_cad:
                clientes_opt = carregar_coluna("clientes", "nome") or ["Carlos Alberto"]
                produtos_base = carregar_coluna("produtos", "nome") or ["AMEIXA IMPORTADA", "ABACATE"]
                produtos_opt = list(produtos_base) + ["➕ Cadastrar Novo Produto..."]
                
                fornecedores_opt = carregar_coluna("fornecedores", "fornecedor") or ["BAHIA"]
                grupos_opt = carregar_coluna("grupos", "grupo") or ["GERAL"]

                prod_item = st.selectbox("Selecione o Produto", produtos_opt, key="ped_select_produto")

                if prod_item == "➕ Cadastrar Novo Produto...":
                    st.warning("⚠️ O produto selecionado não existe. Preencha os dados abaixo para cadastrá-lo rapidamente:")
                    with st.form("form_cadastro_rapido_prod"):
                        novo_nome_prod = st.text_input("Nome do Novo Produto").strip().upper()
                        c_f_r = st.selectbox("Fornecedor", fornecedores_opt)
                        c_g_r = st.selectbox("Grupo", grupos_opt)
                        c_qtd_r = st.number_input("Qtd Inicial em Estoque", min_value=0.0, value=0.0)
                        c_custo_r = st.number_input("Preço de Custo (R$)", min_value=0.0, value=0.0)
                        c_venda_r = st.number_input("Preço de Venda (R$)", min_value=0.0, value=0.0)
                        
                        if st.form_submit_button("Salvar e Selecionar Produto"):
                            if novo_nome_prod:
                                try:
                                    cursor = conn.cursor()
                                    cursor.execute("""
                                        INSERT INTO produtos (nome, fornecedor, grupo, estoque_atual, valor_compra, valor_venda) 
                                        VALUES (?, ?, ?, ?, ?, ?)
                                    """, (novo_nome_prod, c_f_r, c_g_r, c_qtd_r, c_custo_r, c_venda_r))
                                    conn.commit()
                                    st.success(f"Produto '{novo_nome_prod}' cadastrado com sucesso!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Erro: {e}")
                            else:
                                st.error("Digite o nome do produto.")
                    st.stop()
                
                with st.form("form_cad_pedido_individual"):
                    cliente_ped = st.selectbox("Cliente", clientes_opt, key="ped_cli_ind")
                    fornec_ped = st.selectbox("Fornecedor", fornecedores_opt, key="ped_forn_ind")
                    grupo_ped = st.selectbox("Grupo", grupos_opt, key="ped_grupo_ind")
                    qtd_ped = st.number_input("Quantidade", min_value=0.1, step=1.0, value=1.0, key="ped_qtd_ind")
                    v_venda_ped = st.number_input("Preço Unitário (R$)", min_value=0.0, step=1.0, value=10.0, key="ped_v_ind")
                    
                    tipo_reg = "PEDIDO" if is_modo_pedido else "VENDA"
                    if st.form_submit_button(f"Salvar {tipo_reg}"):
                        salvar_pedido_ou_venda(cliente_ped, prod_item, fornec_ped, grupo_ped, qtd_ped, v_venda_ped, tipo=tipo_reg)
                        st.success(f"{tipo_reg} cadastrado com sucesso!")
                        st.rerun()

            if aba_baixa is not None:
                with aba_baixa:
                    st.subheader("💵 Baixa de Débitos & Lançamento de Haver (Pagamento Parcial ou Total)")
                    st.info("Selecione um cliente para ver o total em aberto. Digite o valor do 'haver', selecione a forma de pagamento e clique em aplicar para abater nas compras pendentes mais antigas.")
                        
                    clientes_com_divida = carregar_coluna("vendas", "cliente") or []
                    if clientes_com_divida:
                        cliente_baixa = st.selectbox("Selecione o Cliente para Baixa:", clientes_com_divida, key="sel_cli_baixa")
                        
                        df_cli_vendas = carregar_dados(f"SELECT * FROM vendas WHERE TRIM(cliente) = TRIM('{cliente_baixa}')")
                        if not df_cli_vendas.empty:
                            tot_vendas = df_cli_vendas['valor_total'].sum()
                            df_cli_vendas['v_rec_num'] = pd.to_numeric(df_cli_vendas['valor_recebido'], errors='coerce').fillna(0.0)
                            tot_recebido = df_cli_vendas['v_rec_num'].sum()
                            total_pendente = tot_vendas - tot_recebido
                            
                            col_m1, col_m2, col_m3 = st.columns(3)
                            col_m1.metric("Total de Compras", f"R$ {tot_vendas:,.2f}")
                            col_m2.metric("Total Já Pago", f"R$ {tot_recebido:,.2f}")
                            col_m3.metric("Saldo Devedor Restante", f"R$ {total_pendente:,.2f}", delta_color="inverse")
                            
                            st.markdown("---")
                            with st.form("form_lancar_haver"):
                                col_h1, col_h2 = st.columns(2)
                                with col_h1:
                                    valor_haver = st.number_input("Valor do Haver / Pagamento Recebido (R$)", min_value=0.0, step=1.0, value=0.0)
                                with col_h2:
                                    forma_pgto_baixa = st.selectbox("Forma de Pagamento", ["Dinheiro", "Pix", "Cartão de Crédito à Vista", "Cartão de Débito"])
                                
                                if st.form_submit_button("Aplicar Haver / Dar Baixa no Débito"):
                                    if valor_haver > 0:
                                        baixar_debito_cliente(cliente_baixa, valor_haver, forma_pagamento=forma_pgto_baixa)
                                        st.success(f"Haver de R$ {valor_haver:,.2f} via {forma_pgto_baixa} aplicado com sucesso para {cliente_baixa}!")
                                        st.rerun()
                                    else:
                                        st.warning("Insira um valor de haver maior que zero.")
                                        
                            st.markdown("#### Histórico de Vendas/Tickets do Cliente (Clique em uma linha para ver os itens)")
                            
                            df_tickets_agrupados = carregar_dados(f"""
                                SELECT MIN(id) as id, cliente, data 
                                FROM vendas 
                                WHERE TRIM(cliente) = TRIM('{cliente_baixa}') 
                                GROUP BY data, cliente 
                                ORDER BY data DESC
                            """)
                            
                            cols_ver = [c for c in ['id', 'cliente', 'data'] if c in df_tickets_agrupados.columns]
                            
                            event_tabela = st.dataframe(
                                df_tickets_agrupados[cols_ver],
                                use_container_width=True,
                                selection_mode="single-row",
                                on_select="rerun"
                            )

                            st.markdown("---")
                            st.subheader("📦 Produtos Relacionados a esta Venda / Ticket")

                            selected_rows = event_tabela.selection.rows

                            if selected_rows:
                                idx_selecionado = selected_rows[0]
                                linha_escolhida = df_tickets_agrupados.iloc[idx_selecionado]

                                id_venda_selecionada = linha_escolhida.get('id', None)
                                data_venda_selecionada = str(linha_escolhida.get('data', ''))[:19]

                                st.info(f"Mostrando itens do Ticket ID: **{id_venda_selecionada}** | Data: **{data_venda_selecionada}** | Cliente: **{cliente_baixa}**")

                                df_ticket_relacionado = carregar_dados(f"SELECT id, produto, quantidade, valor_venda, valor_total, forma_pagamento, data FROM vendas WHERE TRIM(cliente) = TRIM('{cliente_baixa}') AND data LIKE '{data_venda_selecionada[:10]}%'")

                                if not df_ticket_relacionado.empty:
                                    st.dataframe(df_ticket_relacionado, use_container_width=True)
                                else:
                                    df_ticket_unico = carregar_dados(f"SELECT id, produto, quantidade, valor_venda, valor_total, forma_pagamento, data FROM vendas WHERE id = {id_venda_selecionada}")
                                    st.dataframe(df_ticket_unico, use_container_width=True)
                            else:
                                st.caption("👈 Clique em uma linha na tabela acima para carregar os produtos relacionados do respectivo ticket/venda.")

            with aba_list:
                st.subheader("🔍 Edição Direta na Tabela & Gestão por Cliente")

                col_f1, col_f2, col_f3 = st.columns(3)
                with col_f1:
                    clientes_filtro = ["TODOS"] + (carregar_coluna("clientes", "nome") or carregar_coluna("vendas", "cliente"))
                    cliente_sel = st.selectbox("Filtrar por Cliente:", clientes_filtro)
                with col_f2:
                    d_inicio = st.date_input("Data Inicial do Filtro", value=date(2025, 1, 1))
                with col_f3:
                    d_fim = st.date_input("Data Final do Filtro", value=date.today())
                    
                s_d1 = d_inicio.strftime("%Y-%m-%d")
                s_d2 = d_fim.strftime("%Y-%m-%d")

                query_filt = f"SELECT * FROM vendas WHERE substr(data, 1, 10) >= '{s_d1}' AND substr(data, 1, 10) <= '{s_d2}'"

                if cliente_sel != "TODOS":
                    query_filt += f" AND TRIM(cliente) = TRIM('{cliente_sel}')"
                    nome_relatorio = cliente_sel
                else:
                    nome_relatorio = "Geral"

                df_registros = carregar_dados(query_filt)
                
                if not df_registros.empty:
                    st.caption("💡 **Dica:** Clique diretamente em qualquer célula para alterar valores. Marque **Deletar** e clique no botão abaixo para remover registros permanentemente.")
                    
                    df_registros.insert(0, "Deletar", False)
                    
                    if 'valor_recebido' in df_registros.columns:
                        df_registros['valor_recebido'] = pd.to_numeric(df_registros['valor_recebido'], errors='coerce').fillna(0.0)
                    
                    config_cols = {
                        "Deletar": st.column_config.CheckboxColumn("Deletar", help="Marque para excluir o item"),
                        "id": st.column_config.NumberColumn("ID", disabled=True),
                        "cliente": st.column_config.TextColumn("Cliente"),
                        "produto": st.column_config.TextColumn("Produto"),
                        "fornecedor": st.column_config.TextColumn("Fornecedor"),
                        "quantidade": st.column_config.NumberColumn("Qtd", min_value=0.0, format="%.2f"),
                        "valor_total": st.column_config.NumberColumn("Valor Total", disabled=True, format="R$ %.2f"),
                        "data": st.column_config.TextColumn("Data", disabled=True),
                    }
                    
                    if is_modo_pedido:
                        config_cols["valor_venda"] = st.column_config.NumberColumn("Preço Custo / Valor Compra", min_value=0.0, format="R$ %.2f")
                        for col_ocultar in ["forma_pagamento", "valor_recebido", "troco", "restante"]:
                            if col_ocultar in df_registros.columns:
                                df_registros = df_registros.drop(columns=[col_ocultar])
                    else:
                        config_cols["valor_venda"] = st.column_config.NumberColumn("Valor Venda", min_value=0.0, format="R$ %.2f")
                        config_cols["forma_pagamento"] = st.column_config.SelectboxColumn("Forma Pagamento", options=["Dinheiro", "Pix", "Cartão de Crédito à Vista", "Cartão de Débito", "Crediário / Fiado"])
                        config_cols["valor_recebido"] = st.column_config.NumberColumn("Valor Recebido / Haver", min_value=0.0, format="R$ %.2f")
                        
                        col_total = next(
                            (c for c in df_registros.columns if "valor" in c.lower() and "total" in c.lower()),
                            None
                        )
                        
                        if col_total:
                            total_geral = df_registros[col_total].sum()
                            st.metric(
                                label="💰 Valor Total Geral da Seleção",
                                value=f"R$ {total_geral:,.2f}",
                            )
                        if "Valor Total" in df_registros.columns:
                            total_geral = df_registros["Valor Total"].sum()
                            st.markdown(f"### 💰 Valor Total Geral: R$ {total_geral:,.2f}")
                    df_editado = st.data_editor(
                        df_registros,
                        key=f"editor_registros_{menu_admin}",
                        use_container_width=True,
                        num_rows="fixed",
                        column_config=config_cols,
                        hide_index=True
                    )
                    
                    label_btn_sync = "🔄 Atualizar Preço de Custo / Valor da Compra" if is_modo_pedido else "🔄 Atualizar Valores com Estoque Atual"
                    tipo_sync = "compra" if is_modo_pedido else "venda"
                    
                    if st.button(label_btn_sync):
                        sincronizar_valores_com_estoque("vendas", tipo_sync)
                        st.success("Tabela atualizada com os valores de estoque com sucesso!")
                        st.rerun()

                    c_btn1, c_btn2 = st.columns([1, 1])

                    with c_btn1:
                        if st.button("💾 Salvar Alterações Feitas na Tabela", type="primary"):
                            cursor = conn.cursor()
                            for _, row in df_editado.iterrows():
                                if not row["Deletar"]:
                                    v_tot = float(row["quantidade"]) * float(row["valor_venda"])
                                    
                                    f_pag = str(row["forma_pagamento"]) if "forma_pagamento" in row else ""
                                    v_rec = float(row["valor_recebido"]) if "valor_recebido" in row else 0.0
                                    g_val = str(row["grupo"]) if "grupo" in row else ""
                                    t_val = str(row["tipo"]) if "tipo" in row else ""
                                    c_val = str(row["codigo"]) if "codigo" in row else ""
    
                                    cursor.execute("""
                                        UPDATE vendas 
                                        SET cliente = ?, produto = ?, fornecedor = ?, quantidade = ?, 
                                            valor_venda = ?, valor_total = ?, forma_pagamento = ?, 
                                            valor_recebido = ?, grupo = ?, tipo = ?, codigo = ?
                                        WHERE id = ?
                                    """, (
                                        str(row["cliente"]).strip(),
                                        str(row["produto"]),
                                        str(row["fornecedor"]),
                                        float(row["quantidade"]),
                                        float(row["valor_venda"]),
                                        v_tot,
                                        f_pag,
                                        str(v_rec),
                                        g_val,
                                        t_val,
                                        c_val,
                                        int(row["id"])
                                    ))
                            conn.commit()
                            st.success("Todas as edições na tabela foram salvas com sucesso!")
                            st.rerun()

                    with c_btn2:
                        itens_para_deletar = df_editado[df_editado["Deletar"] == True]
                        if not itens_para_deletar.empty:
                            if st.button(f"🗑️ Confirmar Exclusão de ({len(itens_para_deletar)}) Item(ns) Marcados"):
                                ids_del = tuple(itens_para_deletar["id"].tolist())
                                cursor = conn.cursor()
                                if len(ids_del) == 1:
                                    cursor.execute("DELETE FROM vendas WHERE id = ?", (ids_del[0],))
                                else:
                                    cursor.execute(f"DELETE FROM vendas WHERE id IN {ids_del}")
                                conn.commit()
                                st.warning(f"{len(ids_del)} registro(s) foram apagados com sucesso!")
                                st.rerun()

                    st.markdown("---")
                    st.subheader(f"📄 Relatório e Exclusão Total ({nome_relatorio})")
                    
                    col_b1, col_b2 = st.columns(2)
                    with col_b1:
                        pdf_gerado = gerar_pdf_tabela_pedidos(df_registros, cliente_nome=nome_relatorio, d_inicio=d_inicio, d_fim=d_fim)
                        st.download_button(
                            label=f"📥 Baixar Relatório - {nome_relatorio} (PDF)",
                            data=pdf_gerado,
                            file_name=f"Relatorio_Pedidos_{nome_relatorio}.pdf",
                            mime="application/pdf"
                        )
                    with col_b2:
                        if cliente_sel != "TODOS":
                            if st.button(f"🗑️ Apagar Pedido / Venda INTEIRA de {cliente_sel}"):
                                qtd_del = deletar_pedidos_cliente(cliente_sel, s_d1, s_d2)
                                st.success(f"Foram deletados {qtd_del} registro(s) de {cliente_sel} com sucesso!")
                                st.rerun()

                    st.markdown("---")
                    tipo_str = df_registros['tipo'].fillna('').astype(str).str.strip().str.upper() if 'tipo' in df_registros.columns else pd.Series([''] * len(df_registros))
                    codigo_str = df_registros['codigo'].fillna('').astype(str).str.strip().str.upper() if 'codigo' in df_registros.columns else pd.Series([''] * len(df_registros))

                    mask_pedidos = (~tipo_str.isin(['VENDA', 'VENDAS', 'VEN'])) & (~codigo_str.isin(['VEN', 'VENDA']))
                    pedidos_pendentes = df_registros[mask_pedidos]                
                    
                    if cliente_sel != "TODOS":
                        if not pedidos_pendentes.empty:
                            st.subheader("⚙️ Converter Pedido Completo em Venda")
                            total_ped = pedidos_pendentes['valor_total'].sum()
                            qtd_itens = len(pedidos_pendentes)
                            st.write(f"O cliente **{cliente_sel}** possui **{qtd_itens} item(ns)** pendente(s) como pedido, somando **R$ {total_ped:,.2f}**.")
                            
                            if st.button(f"🔄 Converter Pedido Completo de {cliente_sel} para VENDA", key="btn_converter_venda"):
                                linhas_afetadas = converter_pedido_completo_para_venda(cliente_sel)
                                st.success(f"Sucesso! {linhas_afetadas} registro(s) do cliente {cliente_sel} foram convertidos para VENDA!")
                                st.rerun()
                else:
                    st.info("Nenhum registro encontrado para o filtro selecionado.")

        elif menu_admin == "📥 Entrada de Estoque (Compras)":
            st.title("📥 Entrada de Estoque (Compras)")
            aba_compra, aba_historico_compras = st.tabs(["📦 Dar Entrada in Estoque", "📋 Histórico de Entradas / Compras"])
                
            produtos_opt = carregar_coluna("produtos", "nome") or ["AMEIXA IMPORTADA", "ABACATE"]
            fornecedores_opt = carregar_coluna("fornecedores", "fornecedor") or ["BAHIA"]
            grupos_opt = carregar_coluna("grupos", "grupo") or ["GERAL"]
            
            with aba_compra:
                with st.form("form_entrada_estoque"):
                    col1, col2 = st.columns(2)
                    with col1:
                        produto_escolhido = st.selectbox("Produto", produtos_opt)
                        fornecedor_escolhido = st.selectbox("Fornecedor", fornecedores_opt)
                        quantidade = st.number_input("Quantidade", min_value=0.0, format="%.2f")
                    with col2:
                        grupo_escolhido = st.selectbox("Grupo", grupos_opt)
                        preco_custo = st.number_input("Preço de Custo Unitário (R$)", min_value=0.0, format="%.2f")
                    
                    enviado = st.form_submit_button("Registrar Entrada no Estoque")
                    if enviado:
                        registrar_compra(produto_escolhido, fornecedor_escolhido, grupo_escolhido, quantidade, preco_custo)
                        cursor = conn.cursor()
                        cursor.execute("UPDATE produtos SET estoque_atual = COALESCE(estoque_atual, 0) + ? WHERE TRIM(nome) = TRIM(?)", (quantidade, produto_escolhido))
                        conn.commit()
                        st.success("Entrada registrada com sucesso e estoque atualizado!")
                        st.rerun()
                        
            with aba_historico_compras:
                st.dataframe(carregar_dados("SELECT * FROM compras"), use_container_width=True)

        elif menu_admin == "📦 Estoque de Produtos":
            st.title("📦 Estoque de Produtos e Preços")
            df_prods = carregar_dados("SELECT * FROM produtos")            
            if not df_prods.empty:
                if 'nome' not in df_prods.columns and 'produto' in df_prods.columns:
                    df_prods['nome'] = df_prods['produto']
                elif 'produto' not in df_prods.columns and 'nome' in df_prods.columns:
                    df_prods['produto'] = df_prods['nome']
                else:
                    df_prods['nome'] = df_prods['nome'].fillna(df_prods.get('produto', ''))
                    df_prods['produto'] = df_prods['produto'].fillna(df_prods['nome'])

                if 'estoque_atual' not in df_prods.columns and 'quantidade' in df_prods.columns:
                    df_prods['estoque_atual'] = df_prods['quantidade']
                elif 'quantidade' not in df_prods.columns and 'estoque_atual' in df_prods.columns:
                    df_prods['quantidade'] = df_prods['estoque_atual']
                else:
                    df_prods['estoque_atual'] = df_prods['estoque_atual'].fillna(df_prods.get('quantidade', 0))
                    df_prods['quantidade'] = df_prods['quantidade'].fillna(df_prods['estoque_atual'])

                cols_atuais = df_prods.columns.tolist()
                
                col_id = 'id' if 'id' in cols_atuais else cols_atuais[0]
                col_nome = 'nome' if 'nome' in cols_atuais else 'produto'
                col_forn = 'fornecedor' if 'fornecedor' in cols_atuais else None
                col_grupo = 'grupo' if 'grupo' in cols_atuais else None
                
                col_pcusto = 'valor_compra' if 'valor_compra' in cols_atuais else ('preco_custo' if 'preco_custo' in cols_atuais else 'preco_compra')
                col_pvenda = 'valor_venda' if 'valor_venda' in cols_atuais else 'preco_venda'
                col_estoque = 'estoque_atual' if 'estoque_atual' in cols_atuais else 'quantidade'

                col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
                total_itens = df_prods[col_estoque].sum() if col_estoque and col_estoque in df_prods.columns else 0.0
                val_custo_total = (df_prods[col_estoque] * df_prods[col_pcusto]).sum() if col_estoque and col_pcusto and col_estoque in df_prods.columns and col_pcusto in df_prods.columns else 0.0
                val_venda_total = (df_prods[col_estoque] * df_prods[col_pvenda]).sum() if col_estoque and col_pvenda and col_estoque in df_prods.columns and col_pvenda in df_prods.columns else 0.0
                
                col_kpi1.metric("📦 Total de Produtos em Estoque", f"{total_itens:,.2f}")
                col_kpi2.metric("💰 Custo Total em Estoque", f"R$ {val_custo_total:,.2f}")
                col_kpi3.metric("🏷️ Potencial de Venda (Bruto)", f"R$ {val_venda_total:,.2f}")
                
                st.markdown("---")
                
                col_f1, col_f2 = st.columns([2, 1])
                with col_f1:
                    busca = st.text_input("🔍 Pesquisar Produto pelo Nome:", "")
                with col_f2:
                    grupos_list = ["TODOS"] + (sorted(list(df_prods[col_grupo].dropna().unique())) if col_grupo and col_grupo in df_prods.columns else [])
                    grupo_filtro = st.selectbox("Filtrar por Grupo:", grupos_list)
                
                df_exibir = df_prods.copy()
                if busca.strip() and col_nome in df_exibir.columns:
                    df_exibir = df_exibir[df_exibir[col_nome].astype(str).str.contains(busca, case=False, na=False)]
                if grupo_filtro != "TODOS" and col_grupo and col_grupo in df_exibir.columns:
                    df_exibir = df_exibir[df_exibir[col_grupo] == grupo_filtro]
                
                colunas_mostrar = ['Deletar', col_id, col_nome, 'fornecedor', 'grupo', 'valor_compra', 'valor_venda', 'estoque_atual']
                colunas_existentes_exibir = [c for c in colunas_mostrar if c in df_exibir.columns or c == 'Deletar']
                
                if 'Deletar' not in df_exibir.columns:
                    df_exibir.insert(0, "Deletar", False)

                config_colunas = {
                    "Deletar": st.column_config.CheckboxColumn("Deletar", help="Marque para excluir o produto"),
                    col_id: st.column_config.NumberColumn("ID", disabled=True),
                    col_nome: st.column_config.TextColumn("Nome do Produto"),
                    "fornecedor": st.column_config.TextColumn("Fornecedor"),
                    "grupo": st.column_config.TextColumn("Grupo"),
                    "valor_compra": st.column_config.NumberColumn("Preço Custo (R$)", min_value=0.0, format="R$ %.2f"),
                    "valor_venda": st.column_config.NumberColumn("Preço Venda (R$)", min_value=0.0, format="R$ %.2f"),
                    "estoque_atual": st.column_config.NumberColumn("Qtd Estoque", min_value=0.0, format="%.2f")
                }

                df_editado_prod = st.data_editor(
                    df_exibir[[c for c in colunas_existentes_exibir if c in df_exibir.columns]],
                    key="editor_produtos_estoque_dinamico",
                    use_container_width=True,
                    num_rows="fixed",
                    column_config=config_colunas,
                    hide_index=True
                )
                
                c_btn1, c_btn2 = st.columns([1, 1])
                
                with c_btn1:
                    if st.button("💾 Salvar Alterações do Estoque", type="primary"):
                        cursor = conn.cursor()
                        for _, row in df_editado_prod.iterrows():
                            if not row["Deletar"]:
                                val_n = str(row[col_nome]).strip() if col_nome in row else ""
                                val_f = str(row['fornecedor']).strip() if 'fornecedor' in row and pd.notna(row['fornecedor']) else ""
                                val_g = str(row['grupo']).strip() if 'grupo' in row and pd.notna(row['grupo']) else ""
                                val_pc = float(row['valor_compra']) if 'valor_compra' in row and pd.notna(row['valor_compra']) else 0.0
                                val_pv = float(row['valor_venda']) if 'valor_venda' in row and pd.notna(row['valor_venda']) else 0.0
                                val_est = float(row['estoque_atual']) if 'estoque_atual' in row and pd.notna(row['estoque_atual']) else 0.0
                                rid = int(row[col_id])

                                cursor.execute("""
                                    UPDATE produtos 
                                    SET nome = ?, produto = ?, fornecedor = ?, grupo = ?, valor_compra = ?, valor_venda = ?, estoque_atual = ?, quantidade = ?
                                    WHERE id = ?
                                """, (val_n, val_n, val_f, val_g, val_pc, val_pv, val_est, val_est, rid))
                        
                        conn.commit()
                        st.success("Dados do estoque atualizados com sucesso!")
                        st.rerun()

                with c_btn2:
                    itens_del = df_editado_prod[df_editado_prod["Deletar"] == True]
                    if not itens_del.empty:
                        if st.button(f"🗑️ Confirmar Exclusão de ({len(itens_del)}) Produto(s)"):
                            ids_del = tuple(itens_del[col_id].tolist())
                            cursor = conn.cursor()
                            if len(ids_del) == 1:
                                cursor.execute(f"DELETE FROM produtos WHERE {col_id} = ?", (ids_del[0],))
                            else:
                                cursor.execute(f"DELETE FROM produtos WHERE {col_id} IN {ids_del}")
                            conn.commit()
                            st.warning(f"{len(ids_del)} produto(s) excluído(s) com sucesso!")
                            st.rerun()
            else:
                st.info("Nenhum produto cadastrado no banco de dados.")

        elif menu_admin == "👥 Cadastros (Clientes / Fornecedores / Grupos)":
            st.title("👥 Cadastros Gerais")
            tab_cli, tab_prod, tab_forn, tab_grup = st.tabs(["👥 Clientes", "📦 Produtos", "🏢 Fornecedores", "🏷️ Grupos"])            
            
            with tab_cli:
                st.subheader("Gerenciamento de Clientes")
                df_cli_atual = carregar_dados("SELECT * FROM clientes")
                modo_cli = st.radio("Ação (Clientes):", ["➕ Cadastrar Novo Cliente", "✏️ Editar / Excluir Cliente Existente"], horizontal=True)
                
                cli_id_sel = None
                val_nome, val_fone, val_doc, val_end, val_cid = "", "", "", "", ""
                
                if modo_cli == "✏️ Editar / Excluir Cliente Existente" and not df_cli_atual.empty:
                    col_nome_cli = 'cliente' if 'cliente' in df_cli_atual.columns else ('nome' if 'nome' in df_cli_atual.columns else df_cli_atual.columns[1])
                    col_id_cli = 'id' if 'id' in df_cli_atual.columns else df_cli_atual.columns[0]
                    
                    opcoes_clientes = {f"{row[col_id_cli]} - {row[col_nome_cli]}": row[col_id_cli] for _, row in df_cli_atual.iterrows() if pd.notna(row[col_nome_cli])}
                    if opcoes_clientes:
                        cli_escolhido = st.selectbox("Selecione o Cliente:", list(opcoes_clientes.keys()))
                        if cli_escolhido:
                            cli_id_sel = opcoes_clientes[cli_escolhido]
                            dados_cli = df_cli_atual[df_cli_atual[col_id_cli] == cli_id_sel].iloc[0]
                            val_nome = str(dados_cli.get(col_nome_cli, ''))
                            val_fone = str(dados_cli.get('fone', dados_cli.get('telefone', '')))
                            val_doc = str(dados_cli.get('cpf', dados_cli.get('cnpj', dados_cli.get('doc', ''))))
                            val_end = str(dados_cli.get('endereco', ''))
                            val_cid = str(dados_cli.get('email', ''))

                with st.form("form_cad_cliente_completo"):
                    novo_cli = st.text_input("Nome do Cliente / Razão Social", value=val_nome)
                    
                    c1, c2 = st.columns(2)
                    with c1:
                        telefone = st.text_input("Telefone / WhatsApp", value=val_fone if val_fone != "nan" else "")
                    with c2:
                        cidade = st.text_input("Cidade / UF / Email", value=val_cid if val_cid != "nan" else "")
                        
                    doc = st.text_input("CPF / CNPJ", value=val_doc if val_doc != "nan" else "")
                    endereco = st.text_input("Endereço / Logradouro", value=val_end if val_end != "nan" else "")
                    
                    st.markdown("---")
                    b_coll, b_col2, b_col3 = st.columns(3)
                    salvar_clicado = b_coll.form_submit_button("💾 Salvar Cliente", use_container_width=True)
                    editar_clicado = b_col2.form_submit_button("✏️ Salvar Alterações", use_container_width=True)
                    excluir_clicado = b_col3.form_submit_button("🗑️ Excluir Cliente", use_container_width=True)
                    
                    if salvar_clicado:
                        if novo_cli.strip():
                            cursor = conn.cursor()
                            cursor.execute("PRAGMA table_info(clientes)")
                            colunas_db = [col[1] for col in cursor.fetchall()]
                            
                            campos = ['cliente']
                            valores = [novo_cli.strip()]
                            
                            if 'cpf' in colunas_db and doc:
                                campos.append('cpf')
                                valores.append(doc)
                            if 'endereco' in colunas_db and endereco:
                                campos.append('endereco')
                                valores.append(endereco)
                            if 'fone' in colunas_db and telefone:
                                campos.append('fone')
                                valores.append(telefone)
                            if 'email' in colunas_db and cidade:
                                campos.append('email')
                                valores.append(cidade)
                                
                            placeholders = ", ".join(["?"] * len(campos))
                            cols_str = ", ".join(campos)
                            
                            try:
                                sql = f"INSERT INTO clientes ({cols_str}) VALUES ({placeholders})"
                                cursor.execute(sql, tuple(valores))
                                conn.commit()
                                st.success("Cliente cadastrado com sucesso!")
                                st.rerun()
                            except Exception as ex:
                                st.error(f"Erro ao salvar no banco: {ex}")
                        else:
                            st.warning("Preencha o nome do cliente.")
                            
                    if editar_clicado:
                        if cli_id_sel and novo_cli.strip():
                            cursor = conn.cursor()
                            try:
                                sql = "UPDATE clientes SET cliente = ?, fone = ?, cpf = ?, endereco = ?, email = ? WHERE id = ?"
                                cursor.execute(sql, (novo_cli.strip(), telefone, doc, endereco, cidade, cli_id_sel))
                                conn.commit()
                                st.success("Cliente atualizado com sucesso!")
                                st.rerun()
                            except Exception as ex:
                                st.error(f"Erro ao atualizar: {ex}")
                        else:
                            st.warning("Selecione um cliente válido para editar.")
                            
                    if excluir_clicado:
                        if cli_id_sel:
                            cursor = conn.cursor()
                            try:
                                cursor.execute("DELETE FROM clientes WHERE id = ?", (cli_id_sel,))
                                conn.commit()
                                st.warning("Cliente excluído com sucesso!")
                                st.rerun()
                            except Exception as ex:
                                st.error(f"Erro ao excluir: {ex}")
                        else:
                            st.warning("Nenhum cliente selecionado.")

                st.markdown("---")
                st.dataframe(carregar_dados("SELECT * FROM clientes"), use_container_width=True)
                
            with tab_prod:
                st.subheader("Gerenciamento de Produtos e Stock")
                grupos_opt = carregar_coluna("grupos", "grupo") or ["GERAL"]
                fornecedores_opt = carregar_coluna("fornecedores", "fornecedor") or ["BAHIA"]
                df_prod_atual = carregar_dados("SELECT * FROM produtos")
                
                modo_prod = st.radio("Ação (Produtos):", ["➕ Cadastrar Novo Produto", "✏️ Editar / Excluir Produto Existente"], horizontal=True)
                
                prod_id_sel = None
                p_nome_v, p_forn_v, p_grupo_v, p_custo_v, p_venda_v, p_est_v = "", fornecedores_opt[0], grupos_opt[0], 10.0, 20.0, 0.0
                
                if modo_prod == "✏️ Editar / Excluir Produto Existente" and not df_prod_atual.empty:
                    col_id_p = 'id' if 'id' in df_prod_atual.columns else df_prod_atual.columns[0]
                    col_nome_p = 'produto' if 'produto' in df_prod_atual.columns else ('nome' if 'nome' in df_prod_atual.columns else df_prod_atual.columns[1])
                    
                    opcoes_prod = {f"{row[col_id_p]} - {row[col_nome_p]}": row[col_id_p] for _, row in df_prod_atual.iterrows() if pd.notna(row[col_nome_p])}
                    if opcoes_prod:
                        prod_escolhido = st.selectbox("Selecione o Produto:", list(opcoes_prod.keys()))
                        if prod_escolhido:
                            prod_id_sel = opcoes_prod[prod_escolhido]
                            d_prod = df_prod_atual[df_prod_atual[col_id_p] == prod_id_sel].iloc[0]
                            p_nome_v = str(d_prod.get(col_nome_p, ''))
                            p_forn_v = str(d_prod.get('fornecedor', fornecedores_opt[0]))
                            p_grupo_v = str(d_prod.get('grupo', grupos_opt[0]))
                            
                            val_c = d_prod.get('valor_compra', d_prod.get('preco_custo', 10.0))
                            p_custo_v = float(val_c) if pd.notna(val_c) else 10.0
                            
                            val_v = d_prod.get('valor_venda', d_prod.get('preco_venda', 20.0))
                            p_venda_v = float(val_v) if pd.notna(val_v) else 20.0
                            
                            val_e = d_prod.get('estoque_atual', d_prod.get('quantidade', 0.0))
                            p_est_v = float(val_e) if pd.notna(val_e) else 0.0

                with st.form("form_cad_produto_completo"):
                    coll, col2 = st.columns(2)
                    with coll:
                        novo_prod = st.text_input("Nome do Produto", value=p_nome_v)
                        fornec_prod = st.selectbox("Fornecedor", fornecedores_opt, index=fornecedores_opt.index(p_forn_v) if p_forn_v in fornecedores_opt else 0)
                        grupo_prod = st.selectbox("Grupo / Categoria", grupos_opt, index=grupos_opt.index(p_grupo_v) if p_grupo_v in grupos_opt else 0)
                    with col2:
                        p_custo = st.number_input("Preço de Custo (R$)", min_value=0.0, step=1.0, value=p_custo_v)
                        p_venda = st.number_input("Preço de Venda (R$)", min_value=0.0, step=1.0, value=p_venda_v)
                        estoque_ini = st.number_input("Estoque Inicial / Atual", min_value=0.0, step=1.0, value=p_est_v)

                    st.markdown("---")
                    bp1, bp2, bp3 = st.columns(3)
                    s_prod = bp1.form_submit_button("💾 Salvar Produto", use_container_width=True)
                    e_prod = bp2.form_submit_button("✏️ Salvar Alterações", use_container_width=True)
                    d_prod_btn = bp3.form_submit_button("🗑️ Excluir Produto", use_container_width=True)

                    if s_prod:
                        if novo_prod.strip():
                            try:
                                salvar_produto_completo(novo_prod.strip(), fornec_prod, grupo_prod, p_custo, p_venda, estoque_ini)
                                st.success("Produto cadastrado com sucesso!")
                                st.rerun()
                            except Exception as ex:
                                st.error(f"Erro ao salvar produto: {ex}")
                        else:
                            st.warning("Preencha o nome do produto.")
                            
                    if e_prod:
                        if prod_id_sel and novo_prod.strip():
                            cursor = conn.cursor()
                            try:
                                sql = "UPDATE produtos SET produto = ?, grupo = ?, fornecedor = ?, valor_compra = ?, valor_venda = ?, estoque_atual = ? WHERE id = ?"
                                cursor.execute(sql, (novo_prod.strip(), grupo_prod, fornec_prod, p_custo, p_venda, estoque_ini, prod_id_sel))
                                conn.commit()
                                st.success("Produto atualizado com sucesso!")
                                st.rerun()
                            except Exception as ex:
                                st.error(f"Erro ao atualizar produto: {ex}")
                        else:
                            st.warning("Selecione um produto válido para editar.")
                            
                    if d_prod_btn:
                        if prod_id_sel:
                            cursor = conn.cursor()
                            try:
                                cursor.execute("DELETE FROM produtos WHERE id = ?", (prod_id_sel,))
                                conn.commit()
                                st.warning("Produto excluído com sucesso!")
                                st.rerun()
                            except Exception as ex:
                                st.error(f"Erro ao excluir produto: {ex}")
                        else:
                            st.warning("Nenhum produto selecionado.")

                st.markdown("---")
                st.dataframe(carregar_dados("SELECT * FROM produtos"), use_container_width=True)

            with tab_forn:
                st.subheader("Gerenciamento de Fornecedores")
                df_forn_atual = carregar_dados("SELECT * FROM fornecedores")
                
                modo_forn = st.radio("Ação (Fornecedores):", ["➕ Cadastrar Novo Fornecedor", "✏️ Editar / Excluir Fornecedor Existente"], horizontal=True)
                forn_id_sel = None
                nome_forn_v = ""
                
                if modo_forn == "✏️ Editar / Excluir Fornecedor Existente" and not df_forn_atual.empty:
                    col_id_f = 'id' if 'id' in df_forn_atual.columns else df_forn_atual.columns[0]
                    col_nome_f = 'fornecedor' if 'fornecedor' in df_forn_atual.columns else df_forn_atual.columns[1]
                    
                    opcoes_forn = {f"{row[col_id_f]} - {row[col_nome_f]}": row[col_id_f] for _, row in df_forn_atual.iterrows() if pd.notna(row[col_nome_f])}
                    if opcoes_forn:
                        forn_escolhido = st.selectbox("Selecione o Fornecedor:", list(opcoes_forn.keys()))
                        if forn_escolhido:
                            forn_id_sel = opcoes_forn[forn_escolhido]
                            d_forn = df_forn_atual[df_forn_atual[col_id_f] == forn_id_sel].iloc[0]
                            nome_forn_v = str(d_forn.get(col_nome_f, ''))

                with st.form("form_cad_fornecedor_completo"):
                    nome_forn = st.text_input("Nome do Fornecedor / Empresa", value=nome_forn_v)
                    
                    st.markdown("---")
                    bf1, bf2, bf3 = st.columns(3)
                    s_forn = bf1.form_submit_button("💾 Salvar Fornecedor", use_container_width=True)
                    e_forn = bf2.form_submit_button("✏️ Salvar Alterações", use_container_width=True)
                    d_forn_btn = bf3.form_submit_button("🗑️ Excluir Fornecedor", use_container_width=True)
                    
                    if s_forn:
                        if nome_forn.strip():
                            cursor = conn.cursor()
                            cursor.execute("SELECT id FROM fornecedores WHERE fornecedor = ?", (nome_forn.strip(),))
                            existe = cursor.fetchone()
                            if existe:
                                st.warning("Este fornecedor já está cadastrado!")
                            else:
                                cursor.execute("INSERT INTO fornecedores (fornecedor) VALUES (?)", (nome_forn.strip(),))
                                conn.commit()
                                st.success("Fornecedor cadastrado com sucesso!")
                                st.rerun()
                        else:
                            st.warning("Preencha o nome do fornecedor.")
                            
                    if e_forn:
                        if forn_id_sel and nome_forn.strip():
                            cursor = conn.cursor()
                            cursor.execute("UPDATE fornecedores SET fornecedor = ? WHERE id = ?", (nome_forn.strip(), forn_id_sel))
                            conn.commit()
                            st.success("Fornecedor atualizado com sucesso!")
                            st.rerun()
                        else:
                            st.warning("Selecione um fornecedor válido para editar.")
                            
                    if d_forn_btn:
                        if forn_id_sel:
                            cursor = conn.cursor()
                            cursor.execute("DELETE FROM fornecedores WHERE id = ?", (forn_id_sel,))
                            conn.commit()
                            st.warning("Fornecedor excluído com sucesso!")
                            st.rerun()
                        else:
                            st.warning("Nenhum fornecedor selecionado.")

                st.markdown("---")
                st.dataframe(carregar_dados("SELECT * FROM fornecedores"), use_container_width=True)

            with tab_grup:
                st.subheader("Gerenciamento de Grupos / Categorias")
                df_grup_atual = carregar_dados("SELECT * FROM grupos")
                
                modo_grup = st.radio("Ação (Grupos):", ["➕ Cadastrar Novo Grupo", "✏️ Editar / Excluir Grupo Existente"], horizontal=True)
                grup_id_sel = None
                nome_grup_v = ""
                
                if modo_grup == "✏️ Editar / Excluir Grupo Existente" and not df_grup_atual.empty:
                    col_id_g = 'id' if 'id' in df_grup_atual.columns else df_grup_atual.columns[0]
                    col_nome_g = 'grupo' if 'grupo' in df_grup_atual.columns else df_grup_atual.columns[1]
                    
                    opcoes_grup = {f"{row[col_id_g]} - {row[col_nome_g]}": row[col_id_g] for _, row in df_grup_atual.iterrows() if pd.notna(row[col_nome_g])}
                    if opcoes_grup:
                        grup_escolhido = st.selectbox("Selecione o Grupo:", list(opcoes_grup.keys()))
                        if grup_escolhido:
                            grup_id_sel = opcoes_grup[grup_escolhido]
                            d_grup = df_grup_atual[df_grup_atual[col_id_g] == grup_id_sel].iloc[0]
                            nome_grup_v = str(d_grup.get(col_nome_g, ''))

                with st.form("form_cad_grupo_completo"):
                    nome_grupo = st.text_input("Nome do Grupo / Categoria", value=nome_grup_v)
                    
                    st.markdown("---")
                    bg1, bg2, bg3 = st.columns(3)
                    s_grup = bg1.form_submit_button("💾 Salvar Grupo", use_container_width=True)
                    e_grup = bg2.form_submit_button("✏️ Salvar Alterações", use_container_width=True)
                    d_grup_btn = bg3.form_submit_button("🗑️ Excluir Grupo", use_container_width=True)
                    
                    if s_grup:
                        if nome_grupo.strip():
                            cursor = conn.cursor()
                            cursor.execute("SELECT id FROM grupos WHERE grupo = ?", (nome_grupo.strip(),))
                            if cursor.fetchone():
                                st.warning("Este grupo já está cadastrado!")
                            else:
                                cursor.execute("INSERT INTO grupos (grupo) VALUES (?)", (nome_grupo.strip(),))
                                conn.commit()
                                st.success("Grupo cadastrado com sucesso!")
                                st.rerun()
                        else:
                            st.warning("Preencha o nome do grupo.")
                            
                    if e_grup:
                        if grup_id_sel and nome_grupo.strip():
                            cursor = conn.cursor()
                            cursor.execute("UPDATE grupos SET grupo = ? WHERE id = ?", (nome_grupo.strip(), grup_id_sel))
                            conn.commit()
                            st.success("Grupo atualizado com sucesso!")
                            st.rerun()
                        else:
                            st.warning("Selecione um grupo válido para editar.")
                            
                    if d_grup_btn:
                        if grup_id_sel:
                            cursor = conn.cursor()
                            cursor.execute("DELETE FROM grupos WHERE id = ?", (grup_id_sel,))
                            conn.commit()
                            st.warning("Grupo excluído com sucesso!")
                            st.rerun()
                        else:
                            st.warning("Nenhum grupo selecionado.")

                st.markdown("---")
                st.dataframe(carregar_dados("SELECT * FROM grupos"), use_container_width=True)
