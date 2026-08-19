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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            produto TEXT UNIQUE,
            fornecedor TEXT,
            grupo TEXT,
            valor_compra REAL,
            valor_venda REAL,
            quantidade REAL
        )
    """)

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
    if not cols:
        return []
    col_alvo = coluna if coluna in cols else cols[1]
    
    df = carregar_dados(f"SELECT DISTINCT TRIM({col_alvo}) as {col_alvo} FROM {tabela} WHERE {col_alvo} IS NOT NULL AND {col_alvo} != ''")
    if not df.empty:
        return df[col_alvo].tolist()
    return []

def salvar_pedido_ou_venda(cliente, produto, fornecedor, grupo, quantidade, valor_venda, forma_pagamento="", valor_recebido=0.0, tipo="PEDIDO"):
    cursor = conn.cursor()
    valor_total = quantidade * valor_venda
    data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cod_status = "VEN" if tipo.upper() in ["VENDA", "VENDAS", "VEN"] else "PED"
    
    cursor.execute("""
        INSERT INTO vendas (cliente, produto, fornecedor, grupo, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, tipo, codigo, data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (str(cliente).strip(), str(produto), str(fornecedor), str(grupo), float(quantidade), float(valor_venda), float(valor_total), str(forma_pagamento), str(valor_recebido), str(tipo), str(cod_status), str(data_atual)))
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

    table_data = [["Produto", "Qtd Total", "Preço Médio (R$)", "Valor Total (R$)"]]
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
        ('ALIGN', (0, 1), (0, -2), 'LEFT'),
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
# 2. SESSÃO E PERFIL
# -----------------------------------------------------------------------------
if 'admin_logged' not in st.session_state:
    st.session_state.admin_logged = False

if 'cliente_autenticado' not in st.session_state:
    st.session_state.cliente_autenticado = None

st.sidebar.title("🔑 Acesso ao Sistema")
perfil_selecionado = st.sidebar.radio("Selecione o Perfil:", ["👤 Portal do Cliente", "🔒 Administração / Vendedor"])
st.sidebar.markdown("---")

if perfil_selecionado == "👤 Portal do Cliente":
    if not st.session_state.cliente_autenticado:
        st.title("🔒 Portal do Cliente")
        lista_clientes = carregar_coluna("clientes", "nome") or ["Carlos Alberto"]
        cliente_nome = st.sidebar.selectbox("Identifique seu Nome/Empresa:", lista_clientes)
        senha_cliente = st.sidebar.text_input("Senha:", type="password")
        if st.sidebar.button("Acessar"):
            if senha_cliente == "123":
                st.session_state.cliente_autenticado = cliente_nome
                st.rerun()
            else:
                st.sidebar.error("Senha incorreta!")
    else:
        st.sidebar.success(f"Logado como: **{st.session_state.cliente_autenticado}**")
        if st.sidebar.button("Sair"):
            st.session_state.cliente_autenticado = None
            st.rerun()
        st.title(f"🛍️ Meus Pedidos ({st.session_state.cliente_autenticado})")
        df_pedidos = carregar_dados(f"SELECT * FROM vendas WHERE TRIM(cliente) = TRIM('{st.session_state.cliente_autenticado}')")
        if not df_pedidos.empty:
            st.dataframe(df_pedidos, use_container_width=True)
        else:
            st.warning("Nenhum pedido encontrado.")

elif perfil_selecionado == "🔒 Administração / Vendedor":
    if not st.session_state.admin_logged:
        st.title("🔑 Autenticação Admin")
        senha_admin = st.sidebar.text_input("Senha:", type="password")
        if st.sidebar.button("Entrar"):
            if senha_admin == "1234":
                st.session_state.admin_logged = True
                st.rerun()
            else:
                st.sidebar.error("Senha incorreta!")
    else:
        if st.sidebar.button("Sair do Modo Admin"):
            st.session_state.admin_logged = False
            st.rerun()
            
        # Menu completo com todas as telas na lateral esquerda
        menu_admin = st.sidebar.radio(
            "Navegação",
            [
                "🛒 PDV — Frente de Caixa",
                "📊 Fechamento & Financeiro",
                "📋 Pedidos / Orçamentos",
                "📥 Entrada de Estoque (Compras)",
                "📦 Estoque de Produtos",
                "👥 Cadastros (Clientes / Fornecedores / Grupos)"
            ]
        )
        
        # ==========================================
        # PDV — FRENTE DE CAIXA
        # ==========================================
        if menu_admin == "🛒 PDV — Frente de Caixa":
            st.title("🛒 PDV — Frente de Caixa (Balcão)")
            df_produtos_pdv = carregar_dados("SELECT * FROM produtos")
            lista_clientes_pdv = carregar_coluna("clientes", "nome") or ["Cliente Balcão / Geral"]
            
            if df_produtos_pdv.empty:
                st.warning("⚠️ Nenhum produto cadastrado no estoque.")
            else:
                col_pdv1, col_pdv2 = st.columns([1.2, 0.8])
                with col_pdv1:
                    cli_pdv = st.selectbox("Cliente:", lista_clientes_pdv)
                    prod_nomes = df_produtos_pdv['produto'].dropna().astype(str).tolist()
                    prod_escolhido = st.selectbox("Produto:", prod_nomes)
                    
                    dados_p = df_produtos_pdv[df_produtos_pdv['produto'].astype(str).str.strip() == str(prod_escolhido).strip()].iloc[0]
                    preco_sugerido = float(dados_p['valor_venda'])
                    estoque_disp = float(dados_p['quantidade'])
                    forn_prod = str(dados_p['fornecedor'])
                    grupo_prod = str(dados_p['grupo'])
                    
                    st.caption(f"📦 **Estoque Disponível:** {estoque_disp:,.2f} | 🏢 **Fornecedor:** {forn_prod}")
                    
                    col_q, col_v = st.columns(2)
                    with col_q:
                        qtd_pdv = st.number_input("Quantidade", min_value=0.01, step=1.0, value=1.0)
                    with col_v:
                        valor_unit_pdv = st.number_input("Preço Unitário (R$)", min_value=0.0, step=1.0, value=preco_sugerido)
                    
                    subtotal_pdv = qtd_pdv * valor_unit_pdv
                    st.markdown(f"### Total: **R$ {subtotal_pdv:,.2f}**")
                    
                    forma_pgto_pdv = st.selectbox("Forma de Pagamento", ["Dinheiro", "Pix", "Cartão de Crédito à Vista", "Cartão de Débito", "Crediário / Fiado"])
                    val_recebido_pdv = subtotal_pdv
                    if forma_pgto_pdv == "Dinheiro":
                        val_recebido_pdv = st.number_input("Dinheiro Recebido (R$)", min_value=0.0, step=5.0, value=subtotal_pdv)
                        troco_pdv = val_recebido_pdv - subtotal_pdv
                        if troco_pdv >= 0:
                            st.success(f"💵 **Troco:** R$ {troco_pdv:,.2f}")
                        else:
                            st.error(f"⚠️ Valor menor que o total!")

                    if st.button("🚀 Finalizar Venda", type="primary", use_container_width=True):
                        if estoque_disp < qtd_pdv:
                            st.error(f"⚠️ Estoque insuficiente! Disponível: {estoque_disp}")
                        else:
                            salvar_pedido_ou_venda(
                                cliente=cli_pdv,
                                produto=prod_escolhido,
                                fornecedor=forn_prod,
                                grupo=grupo_prod,
                                quantidade=qtd_pdv,
                                valor_venda=valor_unit_pdv,
                                forma_pagamento=forma_pgto_pdv,
                                valor_recebido=val_recebido_pdv,
                                tipo="VENDA"
                            )
                            cursor = conn.cursor()
                            cursor.execute("UPDATE produtos SET quantidade = quantidade - ? WHERE TRIM(produto) = TRIM(?)", (qtd_pdv, prod_escolhido))
                            conn.commit()
                            st.success(f"✅ Venda de {prod_escolhido} concluída com sucesso!")
                            st.balloons()

                with col_pdv2:
                    st.subheader("📋 Últimas Vendas")
                    df_ult = carregar_dados("SELECT id, cliente, produto, quantidade, valor_total, data FROM vendas WHERE tipo = 'VENDA' ORDER BY id DESC LIMIT 5")
                    if not df_ult.empty:
                        st.dataframe(df_ult, use_container_width=True)

        # ==========================================
        # FECHAMENTO & FINANCEIRO
        # ==========================================
        elif menu_admin == "📊 Fechamento & Financeiro":
            st.title("📊 Fechamento & Financeiro")
            df_vendas = carregar_dados("SELECT * FROM vendas")
            if not df_vendas.empty:
                st.dataframe(df_vendas, use_container_width=True)
            else:
                st.info("Nenhuma venda registrada.")

        # ==========================================
        # PEDIDOS / ORÇAMENTOS
        # ==========================================
        elif menu_admin == "📋 Pedidos / Orçamentos":
            st.title("📋 Pedidos / Orçamentos")
            df_ped = carregar_dados("SELECT * FROM vendas WHERE tipo = 'PEDIDO'")
            if not df_ped.empty:
                st.dataframe(df_ped, use_container_width=True)
            else:
                st.info("Nenhum pedido registrado.")

        # ==========================================
        # ENTRADA DE ESTOQUE (COMPRAS)
        # ==========================================
        elif menu_admin == "📥 Entrada de Estoque (Compras)":
            st.title("📥 Entrada de Estoque / Compras")
            lista_forn = carregar_coluna("fornecedores", "fornecedor") or ["Geral"]
            lista_grupos = carregar_coluna("grupos", "grupo") or ["Geral"]
            lista_prods = carregar_coluna("produtos", "produto") or ["Produto Exemplo"]

            with st.form("form_compras"):
                f_prod = st.selectbox("Produto", lista_prods, index=0)
                f_forn = st.selectbox("Fornecedor", lista_forn)
                f_grupo = st.selectbox("Grupo", lista_grupos)
                f_qtd = st.number_input("Quantidade Entrante", min_value=0.01, value=1.0)
                f_custo = st.number_input("Valor de Custo Unitário (R$)", min_value=0.0, value=0.0)
                
                btn_salvar_compra = st.form_submit_button("Registrar Entrada")
                if btn_salvar_compra:
                    cursor = conn.cursor()
                    total_custo = f_qtd * f_custo
                    data_hj = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    cursor.execute("INSERT INTO compras (produto, fornecedor, grupo, quantidade, valor_custo, valor_total, data) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                   (f_prod, f_forn, f_grupo, f_qtd, f_custo, total_custo, data_hj))
                    
                    # Atualiza o estoque somando a quantidade nova
                    cursor.execute("UPDATE produtos SET quantidade = quantidade + ? WHERE TRIM(produto) = TRIM(?)", (f_qtd, f_prod))
                    conn.commit()
                    st.success("✅ Entrada registrada e estoque atualizado com sucesso!")

        # ==========================================
        # ESTOQUE DE PRODUTOS (COM EDIÇÃO DIRETA NA TELA)
        # ==========================================
        elif menu_admin == "📦 Estoque de Produtos":
            st.title("📦 Estoque de Produtos e Preços")
            st.info("💡 Você pode editar a quantidade e os preços diretamente na tabela abaixo e clicar no botão para salvar.")
            
            df_prods = carregar_dados("SELECT * FROM produtos")
            if not df_prods.empty:
                df_prods.insert(0, "Deletar", False)
                
                config_cols = {
                    "Deletar": st.column_config.CheckboxColumn("Excluir", help="Marque para excluir o produto"),
                    "id": st.column_config.NumberColumn("ID", disabled=True),
                    "produto": st.column_config.TextColumn("Nome do Produto"),
                    "fornecedor": st.column_config.TextColumn("Fornecedor"),
                    "grupo": st.column_config.TextColumn("Grupo"),
                    "valor_compra": st.column_config.NumberColumn("Preço Compra", min_value=0.0, format="R$ %.2f"),
                    "valor_venda": st.column_config.NumberColumn("Preço Venda", min_value=0.0, format="R$ %.2f"),
                    "quantidade": st.column_config.NumberColumn("Estoque Atual", min_value=0.0, format="%.2f")
                }
                
                df_editado_estoque = st.data_editor(
                    df_prods,
                    key="editor_estoque_geral",
                    use_container_width=True,
                    num_rows="fixed",
                    column_config=config_cols,
                    hide_index=True
                )
                
                if st.button("💾 Salvar Alterações no Estoque", type="primary"):
                    cursor = conn.cursor()
                    for _, row in df_editado_estoque.iterrows():
                        if row["Deletar"]:
                            cursor.execute("DELETE FROM produtos WHERE id = ?", (int(row["id"]),))
                        else:
                            cursor.execute("""
                                UPDATE produtos 
                                SET produto = ?, fornecedor = ?, grupo = ?, valor_compra = ?, valor_venda = ?, quantidade = ?
                                WHERE id = ?
                            """, (
                                str(row["produto"]).strip(),
                                str(row["fornecedor"]),
                                str(row["grupo"]),
                                float(row["valor_compra"]),
                                float(row["valor_venda"]),
                                float(row["quantidade"]),
                                int(row["id"])
                            ))
                    conn.commit()
                    st.success("✅ Estoque e preços atualizados com sucesso!")
                    st.rerun()
            else:
                st.info("Nenhum produto cadastrado no estoque.")

        # ==========================================
        # CADASTROS
        # ==========================================
        elif menu_admin == "👥 Cadastros (Clientes / Fornecedores / Grupos)":
            st.title("👥 Cadastros Gerais")
            tab_c, tab_p, tab_f = st.tabs(["Clientes", "Produtos", "Fornecedores"])
            with tab_c:
                st.dataframe(carregar_dados("SELECT * FROM clientes"), use_container_width=True)
            with tab_p:
                st.dataframe(carregar_dados("SELECT * FROM produtos"), use_container_width=True)
            with tab_f:
                st.dataframe(carregar_dados("SELECT * FROM fornecedores"), use_container_width=True)
