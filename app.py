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
st.set_page_config(page_title="CRM Comércio - Rey da Cebola", layout="wide")[cite: 3]

def get_connection():
    return sqlite3.connect("crm_comercio.db", check_same_thread=False)[cite: 3]

conn = get_connection()[cite: 3]

def adequar_banco_e_migrar():
    cursor = conn.cursor()[cite: 3]
    
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
    """)[cite: 3]
    cursor.execute("PRAGMA table_info(vendas)")[cite: 3]
    colunas_vendas = [col[1] for col in cursor.fetchall()][cite: 3]

    if 'forma_pagamento' not in colunas_vendas:
        try:
            cursor.execute("ALTER TABLE vendas ADD COLUMN forma_pagamento TEXT")[cite: 3]
        except:
            pass

    if 'valor_recebido' not in colunas_vendas:
        try:
            cursor.execute("ALTER TABLE vendas ADD COLUMN valor_recebido TEXT")[cite: 3]
        except:
            pass

    if 'tipo' not in colunas_vendas:
        try:
            cursor.execute("ALTER TABLE vendas ADD COLUMN tipo TEXT DEFAULT 'PEDIDO'")[cite: 3]
        except:
            pass

    if 'codigo' not in colunas_vendas:
        try:
            cursor.execute("ALTER TABLE vendas ADD COLUMN codigo TEXT DEFAULT 'PED'")[cite: 3]
        except:
            pass

    if 'data' not in colunas_vendas:
        try:
            cursor.execute("ALTER TABLE vendas ADD COLUMN data TEXT")[cite: 3]
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
    """)[cite: 3]

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE,
            telefone TEXT,
            doc TEXT,
            endereco TEXT,
            cidade TEXT
        )
    """)[cite: 3]

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fornecedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fornecedor TEXT UNIQUE
        )
    """)[cite: 3]

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS grupos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grupo TEXT UNIQUE
        )
    """)[cite: 3]

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
    """)[cite: 3]

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS caixa_sessoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_abertura TEXT,
            data_fechamento TEXT,
            saldo_inicial REAL,
            saldo_final REAL,
            status TEXT
        )
    """)[cite: 3]

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS caixa_movimentacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sessao_id INTEGER,
            tipo TEXT,
            valor REAL,
            descricao TEXT,
            data TEXT
        )
    """)[cite: 3]
    conn.commit()[cite: 3]

adequar_banco_e_migrar()[cite: 3]

def carregar_dados(query):
    try:
        return pd.read_sql_query(query, conn)[cite: 3]
    except Exception:
        return pd.DataFrame()[cite: 3]

def carregar_coluna(tabela, coluna):
    cursor = conn.cursor()[cite: 3]
    cursor.execute(f"PRAGMA table_info({tabela})")[cite: 3]
    cols = [col[1] for col in cursor.fetchall()][cite: 3]
    col_alvo = coluna if coluna in cols else (cols[1] if len(cols) > 1 else coluna)[cite: 3]
    
    df = carregar_dados(f"SELECT DISTINCT TRIM({col_alvo}) as {col_alvo} FROM {tabela} WHERE {col_alvo} IS NOT NULL AND {col_alvo} != ''")[cite: 3]
    if not df.empty:
        return df[col_alvo].tolist()[cite: 3]
    return [][cite: 3]

def sincronizar_valores_com_estoque(tabela_alvo, tipo_preco="venda"):
    cursor = conn.cursor()[cite: 3]
    df_produtos = carregar_dados("SELECT * FROM produtos")[cite: 3]
    if df_produtos.empty:
        return
    
    cols_prod = df_produtos.columns.tolist()[cite: 3]
    col_p_nome = 'nome' if 'nome' in cols_prod else cols_prod[1][cite: 3]
    
    if tipo_preco == "venda":
        col_p_preco = 'valor_venda' if 'valor_venda' in cols_prod else ('preco_venda' if 'preco_venda' in cols_prod else [c for c in cols_prod if 'venda' in c or 'preco' in c][-1])[cite: 3]
    else:
        col_p_preco = 'valor_compra' if 'valor_compra' in cols_prod else ('preco_custo' if 'preco_custo' in cols_prod else [c for c in cols_prod if 'custo' in c or 'compra' in c][-1])[cite: 3]

    df_registros = carregar_dados(f"SELECT id, produto, quantidade as qtd FROM {tabela_alvo}")[cite: 3]
    
    for _, row in df_registros.iterrows():
        prod_nome = row['produto'][cite: 3]
        mask = df_produtos[col_p_nome].astype(str).str.strip() == str(prod_nome).strip()[cite: 3]
        preco_atual = df_produtos.loc[mask, col_p_preco][cite: 3]
        
        if not preco_atual.empty:
            p = float(preco_atual.iloc[0])[cite: 3]
            total = p * row['qtd'][cite: 3]
            cursor.execute(f"UPDATE {tabela_alvo} SET valor_venda = ?, valor_total = ? WHERE id = ?", (p, total, row['id']))[cite: 3]
    
    conn.commit()[cite: 3]

def salvar_cliente_completo(nome, telefone, doc, endereco, cidade):
    cursor = conn.cursor()[cite: 3]
    try:
        cursor.execute("INSERT INTO clientes (nome, telefone, doc, endereco, cidade) VALUES (?, ?, ?, ?, ?)",
                       (nome.strip(), telefone, doc, endereco, cidade))[cite: 3]
        conn.commit()[cite: 3]
        return True
    except sqlite3.IntegrityError:
        return False

def salvar_produto_completo(nome, fornecedor, grupo, preco_custo, preco_venda, estoque_inicial):
    cursor = conn.cursor()[cite: 3]
    try:
        cursor.execute("""
            INSERT INTO produtos (nome, fornecedor, grupo, valor_compra, valor_venda, estoque_atual) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (nome.strip(), fornecedor, grupo, preco_custo, preco_venda, estoque_inicial))[cite: 3]
        conn.commit()[cite: 3]
        return True
    except sqlite3.IntegrityError:
        cursor.execute("""
            UPDATE produtos 
            SET fornecedor = ?, grupo = ?, valor_compra = ?, valor_venda = ?, estoque_atual = ?
            WHERE TRIM(nome) = TRIM(?)
        """, (fornecedor, grupo, preco_custo, preco_venda, estoque_inicial, nome.strip()))[cite: 3]
        conn.commit()[cite: 3]
        return True
    except Exception as e:
        st.error(f"Erro ao salvar produto: {e}")[cite: 3]
        return False

def salvar_simples(tabela, coluna, valor):
    cursor = conn.cursor()[cite: 3]
    try:
        cursor.execute(f"PRAGMA table_info({tabela})")[cite: 3]
        colunas_existentes = [col[1] for col in cursor.fetchall()][cite: 3]
        
        if not colunas_existentes:
            cursor.execute(f"CREATE TABLE IF NOT EXISTS {tabela} (id INTEGER PRIMARY KEY AUTOINCREMENT, {coluna} TEXT UNIQUE)")[cite: 3]
            conn.commit()[cite: 3]
            coluna_alvo = coluna[cite: 3]
        else:
            coluna_alvo = coluna if coluna in colunas_existentes else colunas_existentes[-1][cite: 3]

        cursor.execute(f"INSERT INTO {tabela} ({coluna_alvo}) VALUES (?)", (valor.strip(),))[cite: 3]
        conn.commit()[cite: 3]
        return True
    except sqlite3.IntegrityError:
        return False
    except Exception as e:
        st.error(f"Erro ao salvar em {tabela}: {e}")[cite: 3]
        return False

def salvar_pedido_ou_venda(cliente, produto, fornecedor, grupo, quantidade, valor_venda, forma_pagamento="", valor_recebido=0.0, tipo="PEDIDO"):
    cursor = conn.cursor()[cite: 3]
    valor_total = quantidade * valor_venda[cite: 3]
    data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")[cite: 3]
    cod_status = "VEN" if tipo.upper() in ["VENDA", "VENDAS", "VEN"] else "PED"[cite: 3]
    
    cursor.execute("""
        INSERT INTO vendas (cliente, produto, fornecedor, grupo, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, tipo, codigo, data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (cliente.strip(), produto, fornecedor, grupo, quantidade, valor_venda, valor_total, forma_pagamento, str(valor_recebido), tipo, cod_status, data_atual))[cite: 3]
    conn.commit()[cite: 3]

def baixar_debito_cliente(cliente_nome, valor_haver, forma_pagamento="Dinheiro"):
    cursor = conn.cursor()[cite: 3]
    cursor.execute("""
        SELECT id, valor_total, valor_recebido 
        FROM vendas 
        WHERE TRIM(cliente) = TRIM(?)
    """, (cliente_nome,))[cite: 3]
    registros = cursor.fetchall()[cite: 3]
    
    saldo_haver = float(valor_haver)[cite: 3]
    
    for reg in registros:
        reg_id, v_total, v_rec_atual = reg[cite: 3]
        v_rec_atual = float(v_rec_atual) if v_rec_atual else 0.0[cite: 3]
        pendente_linha = v_total - v_rec_atual[cite: 3]
        
        if pendente_linha > 0 and saldo_haver > 0:
            if saldo_haver >= pendente_linha:
                novo_recebido = v_total[cite: 3]
                saldo_haver -= pendente_linha[cite: 3]
            else:
                novo_recebido = v_rec_atual + saldo_haver[cite: 3]
                saldo_haver = 0.0[cite: 3]
            
            cursor.execute("""
                UPDATE vendas 
                SET valor_recebido = ?, forma_pagamento = ? 
                WHERE id = ?
            """, (str(novo_recebido), forma_pagamento, reg_id))[cite: 3]
            
    conn.commit()[cite: 3]

def converter_pedido_completo_para_venda(cliente_nome):
    cursor = conn.cursor()[cite: 3]
    cursor.execute("""
        UPDATE vendas 
        SET tipo = 'VENDA', codigo = 'VEN' 
        WHERE TRIM(cliente) = TRIM(?)
    """, (cliente_nome,))[cite: 3]
    conn.commit()[cite: 3]
    return cursor.rowcount[cite: 3]

def deletar_pedidos_cliente(cliente_nome, s_d1, s_d2):
    cursor = conn.cursor()[cite: 3]
    cursor.execute("""
        DELETE FROM vendas 
        WHERE TRIM(cliente) = TRIM(?) 
          AND (substr(data, 1, 10) >= ? AND substr(data, 1, 10) <= ? OR data IS NULL OR data = '')
    """, (cliente_nome, s_d1, s_d2))[cite: 3]
    conn.commit()[cite: 3]
    return cursor.rowcount[cite: 3]

def registrar_compra(produto, fornecedor, grupo, quantidade, valor_custo):
    cursor = conn.cursor()[cite: 3]
    valor_total = quantidade * valor_custo[cite: 3]
    data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")[cite: 3]
    cursor.execute("""
        INSERT INTO compras (produto, fornecedor, grupo, quantidade, valor_custo, valor_total, data)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (produto, fornecedor, grupo, quantidade, valor_custo, valor_total, data_atual))[cite: 3]
    conn.commit()[cite: 3]

# -----------------------------------------------------------------------------
# GERADOR DE PDF
# -----------------------------------------------------------------------------
def gerar_pdf_tabela_pedidos(df_dados, cliente_nome="Geral", d_inicio=None, d_fim=None, titulo_custom=None):
    buffer = io.BytesIO()[cite: 3]
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=20, leftMargin=20, topMargin=15, bottomMargin=15)[cite: 3]
    elements = [][cite: 3]
    styles = getSampleStyleSheet()[cite: 3]
    
    style_empresa = ParagraphStyle('EmpresaStyle', parent=styles['Heading1'], fontName='Helvetica-BoldOblique', fontSize=18, leading=20, alignment=1, textColor=colors.black)[cite: 3]
    style_sub = ParagraphStyle('SubStyle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, leading=10, alignment=1)[cite: 3]
    style_titulo_relatorio = ParagraphStyle('RelatorioStyle', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=13, leading=16, alignment=1, textColor=colors.HexColor('#1E50A2'))[cite: 3]
    style_data = ParagraphStyle('DataStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=10, alignment=1, textColor=colors.HexColor('#333333'))[cite: 3]

    elements.append(Paragraph("REY DA CEBOLA", style_empresa))[cite: 3]
    elements.append(Paragraph("CNPJ: 194.174.39/000-42 INSC.EST.: 12.426725-4", style_sub))[cite: 3]
    elements.append(Paragraph("CONTATO: (99) 98814-9722 OU (99) 98414-3943", style_sub))[cite: 3]
    elements.append(Spacer(1, 4))[cite: 3]
    
    titulo_doc = titulo_custom if titulo_custom else f"Relatório de Pedidos / Orçamentos - {cliente_nome}"[cite: 3]
    elements.append(Paragraph(titulo_doc, style_titulo_relatorio))[cite: 3]
    periodo_str = f"Período: {d_inicio.strftime('%d/%m/%Y')} até {d_fim.strftime('%d/%m/%Y')}" if d_inicio and d_fim else f"Data de Emissão: {datetime.now().strftime('%d/%m/%Y %H:%M')}"[cite: 3]
    elements.append(Paragraph(periodo_str, style_data))[cite: 3]
    elements.append(Spacer(1, 6))[cite: 3]
    
    if not df_dados.empty:
        df_resumo = df_dados.groupby('produto').agg({
            'quantidade': 'sum',
            'valor_venda': 'mean',
            'valor_total': 'sum'
        }).reset_index()[cite: 3]
    else:
        df_resumo = pd.DataFrame(columns=['produto', 'quantidade', 'valor_venda', 'valor_total'])[cite: 3]

    table_data = [["Produto", "Qtd Total", "Preço Unitário (R$)", "Valor Total (R$)"]][cite: 3]
    valor_total_geral = 0.0[cite: 3]
    for _, row in df_resumo.iterrows():
        prod = str(row['produto'])[cite: 3]
        qtd = f"{row['quantidade']:.2f}"[cite: 3]
        v_unit = f"R$ {row['valor_venda']:,.2f}"[cite: 3]
        v_tot = row['valor_total'][cite: 3]
        valor_total_geral += v_tot[cite: 3]
        table_data.append([prod, qtd, v_unit, f"R$ {v_tot:,.2f}"])[cite: 3]
        
    table_data.append(["VALOR TOTAL GERAL", "", "", f"R$ {valor_total_geral:,.2f}"])[cite: 3]
    
    t = Table(table_data, colWidths=[240, 90, 130, 130])[cite: 3]
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
    ]))[cite: 3]
    
    elements.append(t)[cite: 3]
    doc.build(elements)[cite: 3]
    buffer.seek(0)[cite: 3]
    return buffer

# -----------------------------------------------------------------------------
# 2. INICIALIZAÇÃO DE SESSÃO E PERFIL
# -----------------------------------------------------------------------------
if 'admin_logged' not in st.session_state:
    st.session_state.admin_logged = False[cite: 3]

if 'cliente_autenticado' not in st.session_state:
    st.session_state.cliente_autenticado = None[cite: 3]

if 'carrinho_pdv' not in st.session_state:
    st.session_state.carrinho_pdv = [][cite: 3]

st.sidebar.title("🔑 Acesso ao Sistema")[cite: 3]
opcoes_perfil = ["👤 Portal do Cliente", "🔒 Administração / Vendedor"][cite: 3]
perfil_selecionado = st.sidebar.radio("Selecione o Perfil:", opcoes_perfil)[cite: 3]
st.sidebar.markdown("---")[cite: 3]

# ==========================================
# AMBIENTE 1: PORTAL DO CLIENTE
# ==========================================
if perfil_selecionado == "👤 Portal do Cliente":
    if not st.session_state.cliente_autenticado:
        st.title("🔒 Portal do Cliente")[cite: 3]
        st.info("Por favor, selecione seu nome no menu à esquerda e insira sua senha para acessar seus pedidos.")[cite: 3]
        
        lista_clientes = carregar_coluna("clientes", "nome") or carregar_coluna("vendas", "cliente") or ["Carlos Alberto"][cite: 3]
        cliente_nome = st.sidebar.selectbox("Identifique seu Nome/Empresa:", lista_clientes)[cite: 3]
        senha_cliente = st.sidebar.text_input("Digite sua Senha de Cliente:", type="password")[cite: 3]
        
        if st.sidebar.button("Acessar Meus Pedidos"):
            if senha_cliente == "123":
                st.session_state.cliente_autenticado = cliente_nome[cite: 3]
                st.rerun()
            else:
                st.sidebar.error("Senha incorreta!")[cite: 3]
    else:
        st.sidebar.success(f"Logado como:\n**{st.session_state.cliente_autenticado}**")[cite: 3]
        if st.sidebar.button("Sair / Trocar Cliente"):
            st.session_state.cliente_autenticado = None[cite: 3]
            st.rerun()
            
        st.title(f"🛍️ Portal do Cliente — Meus Pedidos ({st.session_state.cliente_autenticado})")[cite: 3]
        aba_novo, aba_historico = st.tabs(["➕ Criar Novo Pedido", "📜 Pedidos Registrados & Relatórios"])[cite: 3]
        
        with aba_novo:
            st.subheader("➕ Registrar Novo Pedido")[cite: 3]
            produtos_opt = carregar_coluna("produtos", "nome") or ["AMEIXA IMPORTADA", "ABACATE", "CEBOLA CAIXA 1"][cite: 3]
            fornecedores_opt = carregar_coluna("fornecedores", "fornecedor") or ["BAHIA"][cite: 3]
            grupos_opt = carregar_coluna("grupos", "grupo") or ["GERAL"][cite: 3]
            
            with st.form("form_novo_pedido_cliente"):
                prod = st.selectbox("Selecione o Produto", produtos_opt)[cite: 3]
                fornec = st.selectbox("Selecione o Fornecedor", fornecedores_opt)[cite: 3]
                grupo = st.selectbox("Selecione o Grupo", grupos_opt)[cite: 3]
                qtd = st.number_input("Quantidade", min_value=0.1, step=0.5, value=1.0)[cite: 3]
                v_unit = st.number_input("Preço de Custo (R$)", min_value=0.0, step=1.0, value=100.0)[cite: 3]
                
                if st.form_submit_button("Confirmar Pedido"):
                    salvar_pedido_ou_venda(st.session_state.cliente_autenticado, prod, fornec, grupo, qtd, v_unit, tipo="PEDIDO")[cite: 3]
                    st.success("Pedido registrado com sucesso!")[cite: 3]
                    st.rerun()

        with aba_historico:
            df_pedidos = carregar_dados(f"SELECT * FROM vendas WHERE TRIM(cliente) = TRIM('{st.session_state.cliente_autenticado}')")[cite: 3]
            if not df_pedidos.empty:
                soma_total = df_pedidos['valor_total'].sum() if 'valor_total' in df_pedidos.columns else 0.0[cite: 3]
                st.markdown(f"**Itens Registrados:** {len(df_pedidos)} | **Soma dos Valores:** R$ {soma_total:,.2f}")[cite: 3]
                
                if st.button("🔄 Atualizar Valores com Estoque (Preço Custo)"):
                    sincronizar_valores_com_estoque("vendas", "compra")[cite: 3]
                    st.success("Tabela atualizada com o Preço de Custo!")[cite: 3]
                    st.rerun()

                st.markdown("---")[cite: 3]
                cols_exibir = [c for c in ['id', 'cliente', 'produto', 'fornecedor', 'quantidade', 'valor_venda', 'valor_total', 'data'] if c in df_pedidos.columns][cite: 3]
                st.dataframe(df_pedidos[cols_exibir], use_container_width=True)[cite: 3]
                pdf_cli = gerar_pdf_tabela_pedidos(df_pedidos, cliente_nome=st.session_state.cliente_autenticado)[cite: 3]
                st.download_button(
                    label=f"Baixar Relatório de Pedidos ({st.session_state.cliente_autenticado}) em PDF",
                    data=pdf_cli,
                    file_name=f"Relatorio_Pedidos_{st.session_state.cliente_autenticado}.pdf",
                    mime="application/pdf"
                )
            else:
                st.warning("Nenhum pedido encontrado para o seu usuário.")[cite: 3]

# ==========================================
# AMBIENTE 2: ADMINISTRADOR / VENDEDOR
# ==========================================
elif perfil_selecionado == "🔒 Administração / Vendedor":
    if not st.session_state.admin_logged:
        st.title("🔑 Autenticação Administrativa")[cite: 3]
        senha_admin = st.sidebar.text_input("Digite a Senha do Admin:", type="password")[cite: 3]
        if st.sidebar.button("Entrar como Admin"):
            if senha_admin == "1234":
                st.session_state.admin_logged = True[cite: 3]
                st.rerun()
            else:
                st.sidebar.error("Senha incorreta!")[cite: 3]
    else:
        st.sidebar.subheader("🔒 Área Restrita")[cite: 3]
        if st.sidebar.button("Sair do Modo Admin"):
            st.session_state.admin_logged = False[cite: 3]
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
        )[cite: 3]
        
        # --- LÓGICA: PDV — FRENTE DE CAIXA COM CARRINHO DE MÚLTIPLOS ITENS ---
        if menu_admin == "🛒 PDV — Frente de Caixa":
            st.title("🛒 PDV — Frente de Caixa (Múltiplos Produtos)")[cite: 3]
            
            df_caixa_aberto = carregar_dados("SELECT * FROM caixa_sessoes WHERE status = 'ABERTO'")[cite: 3]
            if df_caixa_aberto.empty:
                st.warning("⚠️ Atenção: Não há nenhum caixa aberto no momento. Vá em '🔓 Abertura e Fechamento de Caixa' para abrir o caixa antes de registrar vendas.")[cite: 3]
            
            clientes_opt = carregar_coluna("clientes", "nome") or ["Carlos Alberto"][cite: 3]
            produtos_opt = carregar_coluna("produtos", "nome") or ["AMEIXA IMPORTADA", "ABACATE"][cite: 3]
            fornecedores_opt = carregar_coluna("fornecedores", "fornecedor") or ["BAHIA"][cite: 3]
            grupos_opt = carregar_coluna("grupos", "grupo") or ["GERAL"][cite: 3]

            cliente_pdv = st.selectbox("Selecione o Cliente do Atendimento", clientes_opt)[cite: 3]

            st.markdown("#### + Adicionar Item ao Carrinho")[cite: 3]
            
            prod_item = st.selectbox("Produto", produtos_opt, key="pdv_select_produto")[cite: 3]

            df_p = carregar_dados("SELECT * FROM produtos")[cite: 3]
            preco_sugerido = 0.0[cite: 3]
            forn_sugerido = fornecedores_opt[0][cite: 3]
            grupo_sugerido = grupos_opt[0][cite: 3]

            if not df_p.empty:
                cols_prod_lower = {c.lower(): c for c in df_p.columns}[cite: 3]
                col_nome_real = cols_prod_lower.get('nome') or df_p.columns[1][cite: 3]
                
                df_p['_nome_limpo'] = df_p[col_nome_real].astype(str).str.strip().str.upper()[cite: 3]
                target_nome = str(prod_item).strip().upper()[cite: 3]
                
                df_filtrado_p = df_p[df_p['_nome_limpo'] == target_nome][cite: 3]
                
                if not df_filtrado_p.empty:
                    row_p = df_filtrado_p.iloc[0][cite: 3]
                    
                    for col_v in df_p.columns:
                        c_low = col_v.lower()[cite: 3]
                        if 'venda' in c_low or 'preco' in c_low:
                            try:
                                val_aux = float(row_p[col_v])[cite: 3]
                                if val_aux > 0:
                                    preco_sugerido = val_aux[cite: 3]
                                    break
                            except:
                                pass
                    
                    for col_f in df_p.columns:
                        if 'fornecedor' in col_f.lower():
                            forn_sugerido = str(row_p[col_f])[cite: 3]
                            break
                            
                    for col_g in df_p.columns:
                        if 'grupo' in col_g.lower():
                            grupo_sugerido = str(row_p[col_g])[cite: 3]
                            break

            col_s1, col_s2 = st.columns(2)[cite: 3]
            with col_s1:
                idx_f = fornecedores_opt.index(forn_sugerido) if forn_sugerido in fornecedores_opt else 0[cite: 3]
                fornec_item = st.selectbox("Fornecedor", fornecedores_opt, index=idx_f, key="pdv_forn_input")[cite: 3]
                
                idx_g = grupos_opt.index(grupo_sugerido) if grupo_sugerido in grupos_opt else 0[cite: 3]
                grupo_item = st.selectbox("Grupo", grupos_opt, index=idx_g, key="pdv_grupo_input")[cite: 3]
            
            with col_s2:
                qtd_item = st.number_input("Quantidade", min_value=0.1, step=1.0, value=1.0, key="pdv_qtd")[cite: 3]
                v_unit_item = st.number_input("Preço de Venda (R$)", min_value=0.0, step=1.0, value=float(preco_sugerido), key=f"pdv_vunit_{prod_item}")[cite: 3]
            
            valor_total_item = qtd_item * v_unit_item[cite: 3]
            st.metric("Valor Total do Item", f"R$ {valor_total_item:.2f}")[cite: 3]
            
            if st.button("➕ Incluir Produto no Carrinho", type="primary"):
                st.session_state.carrinho_pdv.append({
                    "produto": prod_item,
                    "fornecedor": fornec_item,
                    "grupo": grupo_item,
                    "quantidade": qtd_item,
                    "valor_venda": v_unit_item,
                    "valor_total": valor_total_item
                })[cite: 3]
                st.success(f"Item '{prod_item}' adicionado ao carrinho!")[cite: 3]
                st.rerun()

            st.markdown("---")[cite: 3]
            st.subheader("🛒 Itens Atuais no Carrinho")[cite: 3]
            if len(st.session_state.carrinho_pdv) > 0:
                df_carrinho = pd.DataFrame(st.session_state.carrinho_pdv)[cite: 3]
                st.dataframe(df_carrinho, use_container_width=True)[cite: 3]
                total_geral_carrinho = df_carrinho['valor_total'].sum()[cite: 3]
            else:
                total_geral_carrinho = 0.0[cite: 3]

            if st.button("🗑️ Limpar Carrinho"):
                st.session_state.carrinho_pdv = [][cite: 3]
                st.rerun()

            st.markdown("---")[cite: 3]       
            with st.form("form_finalizar_pagamento_pdv"):
                f_pag = st.selectbox("Forma de Pagamento", ["Dinheiro", "Pix", "Cartão de Crédito à Vista", "Cartão de Débito", "Crediário / Fiado"])[cite: 3]
                v_rec = st.number_input("Valor Recebido (R$)", min_value=0.0, step=1.0, value=float(total_geral_carrinho))[cite: 3]
                
                troco = v_rec - total_geral_carrinho[cite: 3]
                
                st.markdown("---")[cite: 3]
                c_inf1, c_inf2 = st.columns(2)[cite: 3]
                c_inf1.metric("Valor Total da Venda", f"R$ {total_geral_carrinho:,.2f}")[cite: 3]
                c_inf2.metric("Troco", f"R$ {max(0.0, troco):,.2f}", delta_color="normal" if troco >= 0 else "inverse")[cite: 3]
                
                if st.form_submit_button("Finalizar Venda no PDV"):
                    if not df_caixa_aberto.empty and len(st.session_state.carrinho_pdv) > 0:
                        sessao_id = int(df_caixa_aberto.iloc[0]['id'])[cite: 3]
                        
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
                            )[cite: 3]
                        
                        cursor = conn.cursor()[cite: 3]
                        cursor.execute("INSERT INTO caixa_movimentacoes (sessao_id, tipo, valor, descricao, data) VALUES (?, ?, ?, ?, ?)",
                            (sessao_id, "VENDA", total_geral_carrinho, f"Venda PDV (Múltiplos Itens) - Cliente: {cliente_pdv}", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))[cite: 3]
                        conn.commit()[cite: 3]
                        
                        st.session_state.carrinho_pdv = [][cite: 3]
                        st.success(f"Venda realizada com sucesso! Troco: R$ {max(0.0, troco):,.2f}")[cite: 3]
                        st.rerun()
                    else:
                        st.error("Verifique se o caixa está aberto e se há itens no carrinho.")[cite: 3]

        elif menu_admin == "🔓 Abertura e Fechamento de Caixa":
            st.title("🔓 Abertura e Fechamento de Caixa")[cite: 3]
            df_caixa_atual = carregar_dados("SELECT * FROM caixa_sessoes WHERE status = 'ABERTO'")[cite: 3]

            if df_caixa_atual.empty:
                st.info("O caixa encontra-se **FECHADO**. Insira o valor inicial para abri-lo.")[cite: 3]
                with st.form("form_abrir_caixa"):
                    saldo_inicial = st.number_input("Saldo Inicial em Dinheiro (Troco / Fundo de Caixa)", min_value=0.0, step=10.0)[cite: 3]
                    if st.form_submit_button("Abrir Caixa"):
                        cursor = conn.cursor()[cite: 3]
                        data_agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")[cite: 3]
                        cursor.execute("INSERT INTO caixa_sessoes (data_abertura, saldo_inicial, status) VALUES (?, ?, ?)",
                                       (data_agora, saldo_inicial, "ABERTO"))[cite: 3]
                        conn.commit()[cite: 3]
                        st.success("Caixa aberto com sucesso!")[cite: 3]
                        st.rerun()
            else:
                sessao_id = int(df_caixa_atual.iloc[0]['id'])[cite: 3]
                data_abertura = df_caixa_atual.iloc[0]['data_abertura'][cite: 3]
                saldo_inicial = float(df_caixa_atual.iloc[0]['saldo_inicial'])[cite: 3]
                
                st.success(f"🟢 **Caixa ABERTO** desde: {data_abertura} | Saldo Inicial: R$ {saldo_inicial:,.2f}")[cite: 3]
                
                df_movs = carregar_dados(f"SELECT * FROM caixa_movimentacoes WHERE sessao_id = {sessao_id}")[cite: 3]
                total_movimentado = df_movs['valor'].sum() if not df_movs.empty else 0.0[cite: 3]
                
                st.metric("Total Movimentado neste Caixa", f"R$ {total_movimentado:,.2f}")[cite: 3]
                
                if not df_movs.empty:
                    st.dataframe(df_movs, use_container_width=True)[cite: 3]
                else:
                    st.info("Nenhuma movimentação registrada neste caixa ainda.")[cite: 3]
                
                st.markdown("---")[cite: 3]
                with st.form("form_fechar_caixa"):
                    saldo_final_informado = st.number_input("Conferência de Saldo Final (Dinheiro em Caixa)", min_value=0.0, step=10.0, value=saldo_inicial + total_movimentado)[cite: 3]
                    if st.form_submit_button("🔒 Fechar Caixa"):
                        cursor = conn.cursor()[cite: 3]
                        data_fechamento = datetime.now().strftime("%Y-%m-%d %H:%M:%S")[cite: 3]
                        cursor.execute("UPDATE caixa_sessoes SET data_fechamento = ?, saldo_final = ?, status = ? WHERE id = ?",
                                       (data_fechamento, saldo_final_informado, "FECHADO", sessao_id))[cite: 3]
                        conn.commit()[cite: 3]
                        st.success("Caixa fechado com sucesso!")[cite: 3]
                        st.rerun()

        elif menu_admin == "📊 Fechamento & Financeiro":
            st.title("📊 Painel Financeiro & Fechamento por Data")[cite: 3]
            
            col_d1, col_d2, col_d3 = st.columns(3)[cite: 3]
            with col_d1:
                data_inicio = st.date_input("Data Inicial", value=date(2025, 1, 1))[cite: 3]
            with col_d2:
                data_fim = st.date_input("Data Final", value=date.today())[cite: 3]
            with col_d3:
                status_filtro = st.selectbox("Status dos Registros", ["Somente Vendas Concluídas", "Incluir Pedidos Pendentes", "Todos"])[cite: 3]
                
            str_d1 = data_inicio.strftime("%Y-%m-%d")[cite: 3]
            str_d2 = data_fim.strftime("%Y-%m-%d")[cite: 3]
            
            df_todas = carregar_dados("SELECT * FROM vendas")[cite: 3]
            
            if not df_todas.empty:
                df_todas['tipo_str'] = df_todas['tipo'].fillna('').astype(str).str.strip().str.upper() if 'tipo' in df_todas.columns else ''[cite: 3]
                df_todas['codigo_str'] = df_todas['codigo'].fillna('').astype(str).str.strip().str.upper() if 'codigo' in df_todas.columns else ''[cite: 3]
                
                is_venda = df_todas['tipo_str'].isin(['VENDA', 'VENDAS', 'VEN']) | df_todas['codigo_str'].isin(['VEN', 'VENDA'])[cite: 3]
                
                if status_filtro == "Somente Vendas Concluídas":
                    df_vendas = df_todas[is_venda][cite: 3]
                elif status_filtro == "Incluir Pedidos Pendentes":
                    df_vendas = df_todas[~is_venda][cite: 3]
                else:
                    df_vendas = df_todas.copy()[cite: 3]
                    
                if 'data' in df_vendas.columns:
                    df_vendas['data_curta'] = df_vendas['data'].fillna('').astype(str).str.slice(0, 10)[cite: 3]
                    mask_data = (df_vendas['data_curta'] >= str_d1) & (df_vendas['data_curta'] <= str_d2)[cite: 3]
                    df_vendas = df_vendas[mask_data | (df_vendas['data_curta'] == '')][cite: 3]
                    df_vendas = df_vendas.drop(columns=['data_curta', 'tipo_str', 'codigo_str'], errors='ignore')[cite: 3]
                else:
                    df_vendas = pd.DataFrame()[cite: 3]
                
                if not df_vendas.empty:
                    col1, col2, col3 = st.columns(3)[cite: 3]
                    faturamento = df_vendas['valor_total'].sum() if 'valor_total' in df_vendas.columns else 0.0[cite: 3]
                    
                    if 'valor_recebido' in df_vendas.columns:
                        valor_rec = pd.to_numeric(df_vendas['valor_recebido'], errors='coerce').sum()[cite: 3]
                    else:
                        valor_rec = 0.0[cite: 3]
                    
                    col1.metric("Faturamento do Período", f"R$ {faturamento:,.2f}")[cite: 3]
                    col2.metric("Total Recebido em Caixa", f"R$ {valor_rec:,.2f}")[cite: 3]
                    col3.metric("Total Pendente / Fiado", f"R$ {faturamento - valor_rec:,.2f}")[cite: 3]
                    st.markdown("---")[cite: 3]
                
                    st.subheader("📊 Registros Encontrados")[cite: 3]
                    st.dataframe(df_vendas, use_container_width=True)[cite: 3]
                
                    st.markdown("---")[cite: 3]
                    st.subheader("📄 Gerar Relatório do Fechamento Financeiro em PDF")[cite: 3]
                    pdf_fechamento = gerar_pdf_tabela_pedidos(
                        df_vendas, 
                        cliente_nome="Geral", 
                        d_inicio=data_inicio, 
                        d_fim=data_fim,
                        titulo_custom=f"Fechamento Financeiro ({status_filtro})"
                    )[cite: 3]
                
                    st.download_button(
                        label="📥 Baixar Relatório de Fechamento Financeiro (PDF)",
                        data=pdf_fechamento,
                        file_name=f"Fechamento_Financeiro_{str_d1}_a_{str_d2}.pdf",
                        mime="application/pdf"
                    )
                else:
                    st.info("Nenhum registro encontrado para os filtros selecionados.")[cite: 3]
            else:
                st.info("Nenhum dado cadastrado.")[cite: 3]

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
            st.title("📥 Entrada de Estoque (Compras)")[cite: 3]
            aba_compra, aba_historico_compras = st.tabs(["📦 Dar Entrada in Estoque", "📋 Histórico de Entradas / Compras"])[cite: 3]
                
            produtos_opt = carregar_coluna("produtos", "nome") or ["AMEIXA IMPORTADA", "ABACATE"][cite: 3]
            fornecedores_opt = carregar_coluna("fornecedores", "fornecedor") or ["BAHIA"][cite: 3]
            grupos_opt = carregar_coluna("grupos", "grupo") or ["GERAL"][cite: 3]
            
            with aba_compra:
                with st.form("form_entrada_estoque"):
                    col1, col2 = st.columns(2)[cite: 3]
                    with col1:
                        produto_escolhido = st.selectbox("Produto", produtos_opt)[cite: 3]
                        fornecedor_escolhido = st.selectbox("Fornecedor", fornecedores_opt)[cite: 3]
                        quantidade = st.number_input("Quantidade", min_value=0.0, format="%.2f")[cite: 3]
                    with col2:
                        grupo_escolhido = st.selectbox("Grupo", grupos_opt)[cite: 3]
                        preco_custo = st.number_input("Preço de Custo Unitário (R$)", min_value=0.0, format="%.2f")[cite: 3]
                    
                    enviado = st.form_submit_button("Registrar Entrada no Estoque")[cite: 3]
                    if enviado:
                        registrar_compra(produto_escolhido, fornecedor_escolhido, grupo_escolhido, quantidade, preco_custo)[cite: 3]
                        cursor = conn.cursor()[cite: 3]
                        cursor.execute("UPDATE produtos SET estoque_atual = COALESCE(estoque_atual, 0) + ? WHERE TRIM(nome) = TRIM(?)", (quantidade, produto_escolhido))[cite: 3]
                        conn.commit()[cite: 3]
                        st.success("Entrada registrada com sucesso e estoque atualizado!")[cite: 3]
                        st.rerun()
                        
            with aba_historico_compras:
                st.dataframe(carregar_dados("SELECT * FROM compras"), use_container_width=True)[cite: 3]

elif menu_admin == "📦 Estoque de Produtos":
            st.title("📦 Estoque de Produtos e Preços")[cite: 3]
            df_prods = carregar_dados("SELECT * FROM produtos")[cite: 3]            
            if not df_prods.empty:
                cols_atuais = df_prods.columns.tolist()[cite: 3]
                
                col_id = 'id' if 'id' in cols_atuais else cols_atuais[0][cite: 3]
                col_nome = 'nome' if 'nome' in cols_atuais else (cols_atuais[1] if len(cols_atuais) > 1 else col_id)[cite: 3]
                col_forn = 'fornecedor' if 'fornecedor' in cols_atuais else None[cite: 3]
                col_grupo = 'grupo' if 'grupo' in cols_atuais else None[cite: 3]
                
                col_pcusto = 'valor_compra' if 'valor_compra' in cols_atuais else ('preco_custo' if 'preco_custo' in cols_atuais else ('preco_compra' if 'preco_compra' in cols_atuais else None))[cite: 3]
                col_pvenda = 'valor_venda' if 'valor_venda' in cols_atuais else ('preco_venda' if 'preco_venda' in cols_atuais else None)[cite: 3]
                col_estoque = 'estoque_atual' if 'estoque_atual' in cols_atuais else ('quantidade' if 'quantidade' in cols_atuais else None)[cite: 3]

                col_kpi1, col_kpi2, col_kpi3 = st.columns(3)[cite: 3]
                total_itens = df_prods[col_estoque].sum() if col_estoque and col_estoque in df_prods.columns else 0.0[cite: 3]
                val_custo_total = (df_prods[col_estoque] * df_prods[col_pcusto]).sum() if col_estoque and col_pcusto and col_estoque in df_prods.columns and col_pcusto in df_prods.columns else 0.0[cite: 3]
                val_venda_total = (df_prods[col_estoque] * df_prods[col_pvenda]).sum() if col_estoque and col_pvenda and col_estoque in df_prods.columns and col_pvenda in df_prods.columns else 0.0[cite: 3]
                
                col_kpi1.metric("📦 Total de Produtos em Estoque", f"{total_itens:,.2f}")[cite: 3]
                col_kpi2.metric("💰 Custo Total em Estoque", f"R$ {val_custo_total:,.2f}")[cite: 3]
                col_kpi3.metric("🏷️ Potencial de Venda (Bruto)", f"R$ {val_venda_total:,.2f}")[cite: 3]
                
                st.markdown("---")[cite: 3]
                
                col_f1, col_f2 = st.columns([2, 1])[cite: 3]
                with col_f1:
                    busca = st.text_input("🔍 Pesquisar Produto pelo Nome:", "")[cite: 3]
                with col_f2:
                    grupos_list = ["TODOS"] + (sorted(list(df_prods[col_grupo].dropna().unique())) if col_grupo and col_grupo in df_prods.columns else [])[cite: 3]
                    grupo_filtro = st.selectbox("Filtrar por Grupo:", grupos_list)[cite: 3]
                
                df_exibir = df_prods.copy()[cite: 3]
                if busca.strip() and col_nome in df_exibir.columns:
                    df_exibir = df_exibir[df_exibir[col_nome].astype(str).str.contains(busca, case=False, na=False)][cite: 3]
                if grupo_filtro != "TODOS" and col_grupo and col_grupo in df_exibir.columns:
                    df_exibir = df_exibir[df_exibir[col_grupo] == grupo_filtro][cite: 3]
                
                st.caption("💡 **Dica:** Altere preços, estoques, fornecedores ou nomes diretamente na tabela e clique em **Salvar Alterações do Estoque**.")[cite: 3]
                
                df_exibir.insert(0, "Deletar", False)[cite: 3]
                
                config_colunas = {
                    "Deletar": st.column_config.CheckboxColumn("Deletar", help="Marque para excluir o produto"),
                    col_id: st.column_config.NumberColumn("ID", disabled=True),
                }[cite: 3]
                if col_nome: config_colunas[col_nome] = st.column_config.TextColumn("Nome do Produto")[cite: 3]
                if col_forn: config_colunas[col_forn] = st.column_config.TextColumn("Fornecedor")[cite: 3]
                if col_grupo: config_colunas[col_grupo] = st.column_config.TextColumn("Grupo")[cite: 3]
                if col_pcusto: config_colunas[col_pcusto] = st.column_config.NumberColumn("Preço Custo (R$)", min_value=0.0, format="R$ %.2f")[cite: 3]
                if col_pvenda: config_colunas[col_pvenda] = st.column_config.NumberColumn("Preço Venda (R$)", min_value=0.0, format="R$ %.2f")[cite: 3]
                if col_estoque: config_colunas[col_estoque] = st.column_config.NumberColumn("Qtd Estoque", min_value=0.0, format="%.2f")[cite: 3]

                df_editado_prod = st.data_editor(
                    df_exibir,
                    key="editor_produtos_estoque_dinamico",
                    use_container_width=True,
                    num_rows="fixed",
                    column_config=config_colunas,
                    hide_index=True
                )[cite: 3]
                
                c_btn1, c_btn2 = st.columns([1, 1])[cite: 3]
                
                with c_btn1:
                    if st.button("💾 Salvar Alterações do Estoque", type="primary"):
                        cursor = conn.cursor()[cite: 3]
                        for _, row in df_editado_prod.iterrows():
                            if not row["Deletar"]:
                                val_n = str(row[col_nome]).strip() if col_nome else ""[cite: 3]
                                val_f = str(row[col_forn]).strip() if col_forn and col_forn in row else ("" if not col_forn else str(row[col_forn]))[cite: 3]
                                val_g = str(row[col_grupo]).strip() if col_grupo and col_grupo in row else ("" if not col_grupo else str(row[col_grupo]))[cite: 3]
                                val_pc = float(row[col_pcusto]) if col_pcusto and col_pcusto in row else 0.0[cite: 3]
                                val_pv = float(row[col_pvenda]) if col_pvenda and col_pvenda in row else 0.0[cite: 3]
                                val_est = float(row[col_estoque]) if col_estoque and col_estoque in row else 0.0[cite: 3]
                                rid = int(row[col_id])[cite: 3]

                                sql_update = "UPDATE produtos SET "[cite: 3]
                                partes_update = [][cite: 3]
                                valores = [][cite: 3]
                                
                                if col_nome:
                                    partes_update.append(f"{col_nome} = ?")[cite: 3]
                                    valores.append(val_n)[cite: 3]
                                if col_forn:
                                    partes_update.append(f"{col_forn} = ?")[cite: 3]
                                    valores.append(val_f)[cite: 3]
                                if col_grupo:
                                    partes_update.append(f"{col_grupo} = ?")[cite: 3]
                                    valores.append(val_g)[cite: 3]
                                if col_pcusto:
                                    partes_update.append(f"{col_pcusto} = ?")[cite: 3]
                                    valores.append(val_pc)[cite: 3]
                                if col_pvenda:
                                    partes_update.append(f"{col_pvenda} = ?")[cite: 3]
                                    valores.append(val_pv)[cite: 3]
                                if col_estoque:
                                    partes_update.append(f"{col_estoque} = ?")[cite: 3]
                                    valores.append(val_est)[cite: 3]
                                    
                                sql_update += ", ".join(partes_update) + f" WHERE {col_id} = ?"[cite: 3]
                                valores.append(rid)[cite: 3]
                                
                                cursor.execute(sql_update, tuple(valores))[cite: 3]
                        
                        conn.commit()[cite: 3]
                        st.success("Dados do estoque atualizados com sucesso!")[cite: 3]
                        st.rerun()

                with c_btn2:
                    itens_del = df_editado_prod[df_editado_prod["Deletar"] == True][cite: 3]
                    if not itens_del.empty:
                        if st.button(f"🗑️ Confirmar Exclusão de ({len(itens_del)}) Produto(s)"):
                            ids_del = tuple(itens_del[col_id].tolist())[cite: 3]
                            cursor = conn.cursor()[cite: 3]
                            if len(ids_del) == 1:
                                cursor.execute(f"DELETE FROM produtos WHERE {col_id} = ?", (ids_del[0],))[cite: 3]
                            else:
                                cursor.execute(f"DELETE FROM produtos WHERE {col_id} IN {ids_del}")[cite: 3]
                            conn.commit()[cite: 3]
                            st.warning(f"{len(ids_del)} produto(s) excluído(s) com sucesso!")[cite: 3]
                            st.rerun()
            else:
                st.info("Nenhum produto cadastrado no banco de dados.")[cite: 3]

elif menu_admin == "👥 Cadastros (Clientes / Fornecedores / Grupos)":
            st.title("👥 Cadastros Gerais")[cite: 3]
            tab_cli, tab_prod, tab_forn, tab_grup = st.tabs(["👥 Clientes", "📦 Produtos", "🏢 Fornecedores", "🏷️ Grupos"])[cite: 3]            
            
            with tab_cli:
                st.subheader("Cadastrar Novo Cliente")[cite: 3]
                with st.form("form_cad_cliente_completo"):
                    col1, col2 = st.columns(2)[cite: 3]
                    with col1:
                        novo_cli = st.text_input("Nome do Cliente / Razão Social")[cite: 3]
                        telefone = st.text_input("Telefone / WhatsApp")[cite: 3]
                        doc = st.text_input("CPF / CNPJ")[cite: 3]
                    with col2:
                        endereco = st.text_input("Endereço / Logradouro")[cite: 3]
                        cidade = st.text_input("Cidade / UF")[cite: 3]
                    
                    if st.form_submit_button("Salvar Cliente"):
                        if novo_cli.strip() and salvar_cliente_completo(novo_cli.strip(), telefone, doc, endereco, cidade):
                            st.success("Cliente cadastrado com sucesso!")[cite: 3]
                            st.rerun()
                st.markdown("---")[cite: 3]
                st.dataframe(carregar_dados("SELECT * FROM clientes"), use_container_width=True)[cite: 3]

            with tab_prod:
                st.subheader("Cadastrar Novo Produto e Estoque")[cite: 3]
                grupos_opt = carregar_coluna("grupos", "grupo") or ["GERAL"][cite: 3]
                fornecedores_opt = carregar_coluna("fornecedores", "fornecedor") or ["BAHIA"][cite: 3]
                    
                with st.form("form_cad_produto_completo"):
                    col1, col2 = st.columns(2)[cite: 3]
                    with col1:
                        novo_prod = st.text_input("Nome do Produto")[cite: 3]
                        fornec_prod = st.selectbox("Fornecedor", fornecedores_opt)[cite: 3]
                        grupo_prod = st.selectbox("Grupo / Categoria", grupos_opt)[cite: 3]
                    with col2:
                        p_custo = st.number_input("Preço de Custo (R$)", min_value=0.0, step=1.0, value=10.0)[cite: 3]
                        p_venda = st.number_input("Preço de Venda (R$)", min_value=0.0, step=20.0, value=20.0)[cite: 3]
                        estoque_ini = st.number_input("Estoque Inicial", min_value=0.0, step=1.0, value=0.0)[cite: 3]
                    
                    if st.form_submit_button("Salvar Produto no Estoque"):
                        if novo_prod.strip() and salvar_produto_completo(novo_prod.strip(), fornec_prod, grupo_prod, p_custo, p_venda, estoque_ini):
                            st.success("Produto cadastrado com sucesso!")[cite: 3]
                            st.rerun()
                st.markdown("---")[cite: 3]
                st.dataframe(carregar_dados("SELECT * FROM produtos"), use_container_width=True)[cite: 3]

            with tab_forn:
                st.subheader("Cadastrar Novo Fornecedor")[cite: 3]
                with st.form("form_cad_fornecedor"):
                    novo_forn = st.text_input("Nome do Fornecedor")[cite: 3]
                    if st.form_submit_button("Salvar Fornecedor"):
                        if novo_forn.strip() and salvar_simples("fornecedores", "fornecedor", novo_forn.strip()):
                            st.success("Fornecedor cadastrado com sucesso!")[cite: 3]
                            st.rerun()
                st.markdown("---")[cite: 3]
                st.dataframe(carregar_dados("SELECT * FROM fornecedores"), use_container_width=True)[cite: 3]

            with tab_grup:
                st.subheader("Cadastrar Novo Grupo")[cite: 3]
                with st.form("form_cad_grupo"):
                    novo_grup = st.text_input("Nome do Grupo")[cite: 3]
                    if st.form_submit_button("Salvar Grupo"):
                        if novo_grup.strip() and salvar_simples("grupos", "grupo", novo_grup.strip()):
                            st.success("Grupo cadastrado com sucesso!")[cite: 3]
                            st.rerun()
                st.markdown("---")[cite: 3]
                st.dataframe(carregar_dados("SELECT * FROM grupos"), use_container_width=True)[cite: 3]
