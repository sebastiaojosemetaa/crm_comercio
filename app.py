import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, date
import io

# Importação para geração de PDF
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

st.set_page_config(page_title="CRM Comércio - Gestão Completa", layout="wide", page_icon="📦")

# -----------------------------------------------------------------------------
# DEFINIÇÃO DE SENHAS (ADMIN E CLIENTES)
# -----------------------------------------------------------------------------
SENHA_ADMIN = "1234"  # Senha da Administração/Vendedor

# Senhas individuais dos clientes:
SENHAS_CLIENTES = {
    "Carlos Alberto": "1234",
    "Sebastião": "4321",
    "Valeilde Loja 01": "1111"
}
SENHA_CLIENTE_PADRAO = "0000"  # Senha para clientes não cadastrados na lista acima

# -----------------------------------------------------------------------------
# CONEXÃO E CRIAÇÃO DO BANCO DE DADOS
# -----------------------------------------------------------------------------
conn = sqlite3.connect('crm_comercio.db', check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''
    CREATE TABLE IF NOT EXISTS produtos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        produto TEXT UNIQUE,
        grupo TEXT DEFAULT 'Geral',
        quantidade REAL DEFAULT 0.0,
        valor_compra REAL DEFAULT 0.0,
        valor_venda REAL DEFAULT 0.0
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS clientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente TEXT UNIQUE,
        cpf TEXT,
        endereco TEXT,
        email TEXT,
        fone TEXT
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS fornecedores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fornecedor TEXT UNIQUE
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS grupos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        grupo TEXT UNIQUE
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS compras (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        produto TEXT,
        fornecedor TEXT,
        grupo TEXT,
        quantidade REAL,
        valor_compra REAL,
        valor_venda REAL,
        valor_total REAL,
        data TEXT
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS vendas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo_venda TEXT,
        cliente TEXT,
        produto TEXT,
        fornecedor TEXT DEFAULT 'Geral',
        grupo TEXT DEFAULT 'Geral',
        quantidade REAL,
        valor_venda REAL,
        valor_total REAL,
        forma_pagamento TEXT,
        valor_recebido REAL,
        troco REAL,
        restante REAL,
        data TEXT
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS pedidos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo_pedido TEXT,
        cliente TEXT,
        produto TEXT,
        fornecedor TEXT DEFAULT 'Geral',
        grupo TEXT DEFAULT 'Geral',
        quantidade REAL,
        valor_unitario REAL,
        valor_total REAL,
        status TEXT,
        observacoes TEXT,
        data TEXT
    )
''')
conn.commit()

# Compatibilidade de colunas
for query in [
    "ALTER TABLE pedidos ADD COLUMN codigo_pedido TEXT",
    "ALTER TABLE produtos ADD COLUMN grupo TEXT DEFAULT 'Geral'",
    "ALTER TABLE pedidos ADD COLUMN fornecedor TEXT DEFAULT 'Geral'",
    "ALTER TABLE pedidos ADD COLUMN grupo TEXT DEFAULT 'Geral'",
    "ALTER TABLE vendas ADD COLUMN grupo TEXT DEFAULT 'Geral'",
    "ALTER TABLE vendas ADD COLUMN fornecedor TEXT DEFAULT 'Geral'",
    "ALTER TABLE vendas ADD COLUMN codigo_venda TEXT"
]:
    try:
        cursor.execute(query)
    except:
        pass

conn.commit()

# CARGA INICIAL
cursor.execute("SELECT COUNT(*) FROM produtos")
if cursor.fetchone()[0] == 0:
    PRODUTOS_INICIAIS = [
        ("ABACATE", "FRUTAS", 10.0, 80.0, 117.0),
        ("ABACAXI PEQUENO", "FRUTAS", 10.0, 5.0, 6.0),
        ("CEBOLA CAIXA 1", "VERDURAS", 10.0, 55.0, 70.0),
        ("TOMATE 1ª", "VERDURAS", 10.0, 40.0, 70.0)
    ]
    for p, g, q, vc, vv in PRODUTOS_INICIAIS:
        cursor.execute("INSERT INTO produtos (produto, grupo, quantidade, valor_compra, valor_venda) VALUES (?, ?, ?, ?, ?)", (p, g, q, vc, vv))

cursor.execute("SELECT COUNT(*) FROM clientes")
if cursor.fetchone()[0] == 0:
    CLIENTES_INICIAIS = [
        ("Sebastião", "95451160000", "Rua Caipira, 174 Centro", "sebastiaoappsheet@gmail.com", "99985020000"),
        ("Carlos Alberto", "", "", "midiapura07@gmail.com", ""),
        ("Valeilde Loja 01", "", "", "", "")
    ]
    for cli, cpf, end, em, fn in CLIENTES_INICIAIS:
        cursor.execute("INSERT INTO clientes (cliente, cpf, endereco, email, fone) VALUES (?, ?, ?, ?, ?)", (cli, cpf, end, em, fn))

cursor.execute("SELECT COUNT(*) FROM fornecedores")
if cursor.fetchone()[0] == 0:
    FORNECEDORES_INICIAIS = [("BAHIA",), ("TIANGUA",)]
    for f in FORNECEDORES_INICIAIS:
        cursor.execute("INSERT INTO fornecedores (fornecedor) VALUES (?)", f)

cursor.execute("SELECT COUNT(*) FROM grupos")
if cursor.fetchone()[0] == 0:
    GRUPOS_INICIAIS = [("FRUTAS",), ("VERDURAS",), ("LEGUMES",), ("GERAL",)]
    for g in GRUPOS_INICIAIS:
        cursor.execute("INSERT INTO grupos (grupo) VALUES (?)", g)

conn.commit()

# Inicializar Carrinho
if 'carrinho_pedido' not in st.session_state:
    st.session_state.carrinho_pedido = []

# LISTAS GERAIS
clientes_df = pd.read_sql_query("SELECT cliente FROM clientes", conn)
fornecedores_df = pd.read_sql_query("SELECT fornecedor FROM fornecedores", conn)
grupos_df = pd.read_sql_query("SELECT grupo FROM grupos", conn)

list_clientes = clientes_df['cliente'].tolist() if not clientes_df.empty else ["Cliente Geral"]
list_fornecedores = fornecedores_df['fornecedor'].tolist() if not fornecedores_df.empty else ["Geral"]
list_grupos = grupos_df['grupo'].tolist() if not grupos_df.empty else ["GERAL"]

# -----------------------------------------------------------------------------
# --- ESTRUTURA PRINCIPAL ---

# 1. PERFIL: PORTAL DO CLIENTE
if perfil_selecionado == "🥷 Portal do Cliente":
    
    if not st.session_state.get('cliente_autenticado'):
        # --- FORMULÁRIO DE LOGIN DO CLIENTE (SIDEBAR OU CORPO) ---
        st.title("🔒 Portal do Cliente")
        
        # Seleção do cliente no sidebar
        cliente_nome = st.sidebar.selectbox("Identifique seu Nome/Empresa:", lista_clientes)
        senha_cliente = st.sidebar.text_input("Digite sua Senha de Cliente:", type="password")
        
        if st.sidebar.button("Acessar Meus Pedidos"):
            if validar_senha_cliente(cliente_nome, senha_cliente):
                st.session_state.cliente_autenticado = cliente_nome
                st.rerun()
            else:
                st.sidebar.error("Senha incorreta!")
        else:
            st.warning("Por favor, selecione seu nome no menu à esquerda e insira sua senha para acessar seus pedidos.")
            
    else:
        # --- TELA INTERNA DO CLIENTE (LOGADO) ---
        st.title(f"📦 Meus Pedidos — {st.session_state.cliente_autenticado}")
        if st.sidebar.button("Sair / Trocar Cliente"):
            st.session_state.cliente_autenticado = None
            st.rerun()
            
        # [COLOQUE AQUI APENAS O CÓDIGO DA CONSULTA DE PEDIDOS DO CLIENTE]


# 2. PERFIL: ADMIN / VENDEDOR
elif perfil_selecionado == "🔒 Administração / Vendedor":
    
    if not st.session_state.get('admin_logged', False):
        # --- TELA DE LOGIN DO ADMIN ---
        st.title("🔑 Autenticação Administrativa")
        senha_admin = st.text_input("Senha de Acesso", type="password")
        if st.button("Entrar"):
            if senha_admin == "1234":  # Sua senha de admin
                st.session_state.admin_logged = True
                st.rerun()
            else:
                st.error("Senha incorreta.")
    else:
        # --- MENU E TELAS DO ADMIN (SÓ RENDERIZA SE ADMIN LOGADO) ---
        menu = st.sidebar.radio(
            "Navegação",
            [
                "📊 Fechamento & Financeiro",
                "📋 Pedidos / Orçamentos",
                "🛒 Registrar Venda",
                "📥 Entrada de Estoque (Compras)",
                "📦 Estoque de Produtos",
                "👥 Cadastros (Clientes / Fornecedores / Grupos)"
            ]
        )
        
        if menu == "📊 Fechamento & Financeiro":
            st.title("📊 Painel Financeiro & Fechamento")
            # [COLOQUE AQUI O CÓDIGO DO PAINEL FINANCEIRO]
            
        elif menu == "📋 Pedidos / Orçamentos":
            # [CÓDIGO DE PEDIDOS/ORÇAMENTOS]
            pass
            
        elif menu == "🛒 Registrar Venda":
            # [CÓDIGO DE VENDAS]
            pass
        st.warning("Página de vendas restrita ao ambiente administrativo.")

elif menu == "📥 Entrada de Estoque (Compras)":
    st.title("📥 Registro de Compras & Entrada de Estoque")
    st.info("Página de compras restrita ao ambiente administrativo.")

elif menu == "📦 Estoque de Produtos":
    st.title("📦 Consulta & Atualização de Estoque")
    df_estoque = pd.read_sql_query("SELECT * FROM produtos", conn)
    st.dataframe(df_estoque, use_container_width=True)

elif menu == "👥 Cadastros (Clientes / Fornecedores / Grupos)":
    st.title("👥 Cadastros Gerais")
    st.info("Página de cadastros restrita ao ambiente administrativo.")

# -----------------------------------------------------------------------------
# 2. PEDIDOS / ORÇAMENTOS
# -----------------------------------------------------------------------------
elif menu == "📋 Pedidos / Orçamentos":
    if tipo_acesso == "👤 Portal do Cliente":
        st.title(f"🛍️ Portal do Cliente — Meus Pedidos ({cliente_autenticado})")
    else:
        st.title("📋 Gerenciamento de Pedidos e Orçamentos")
    
    tab_novo, tab_lista = st.tabs(["➕ Criar Novo Pedido", "📑 Pedidos Registrados & Relatórios"])
    produtos_df = pd.read_sql_query("SELECT * FROM produtos", conn)

    with tab_novo:
        if produtos_df.empty:
            st.warning("Nenhum produto disponível no momento.")
        else:
            col_head1, col_head2 = st.columns(2)
            with col_head1:
                if tipo_acesso == "👤 Portal do Cliente":
                    st.text_input("Cliente do Pedido", value=cliente_autenticado, disabled=True)
                    ped_cliente = cliente_autenticado
                else:
                    ped_cliente = st.selectbox("Cliente do Pedido", list_clientes, key="ped_cli_multi")
            
            with col_head2:
                if tipo_acesso == "👤 Portal do Cliente":
                    st.text_input("Status Inicial", value="Pendente", disabled=True)
                    ped_status = "Pendente"
                else:
                    ped_status = st.selectbox("Status Inicial", ["Pendente", "Em Andamento", "Cancelado"], key="ped_stat_multi")

            st.markdown("---")
            st.write("#### 🛒 Adicionar Produtos ao Pedido")
            
            if tipo_acesso == "👤 Portal do Cliente":
                c_prod1, c_prod2, c_prod3 = st.columns([4, 2, 2])
                with c_prod1:
                    item_produto = st.selectbox("Selecione o Produto", produtos_df['produto'].tolist(), key="item_prod")
                    prod_info = produtos_df[produtos_df['produto'] == item_produto].iloc[0]
                    grupo_padrao = prod_info.get('grupo', 'GERAL')
                    item_fornecedor = "Geral"
                    item_grupo = grupo_padrao
                
                with c_prod2:
                    item_preco = float(prod_info['valor_venda'])
                    st.number_input("Preço Unit. Venda (R$)", value=item_preco, disabled=True, key="item_prec")

                with c_prod3:
                    item_qtd = st.number_input("Quantidade", min_value=0.01, value=1.0, step=0.1, key="item_qtd")
            else:
                c_prod1, c_prod2, c_prod3, c_prod4 = st.columns([3, 2, 2, 2])
                with c_prod1:
                    item_produto = st.selectbox("Selecione o Produto", produtos_df['produto'].tolist(), key="item_prod")
                    prod_info = produtos_df[produtos_df['produto'] == item_produto].iloc[0]
                    grupo_padrao = prod_info.get('grupo', 'GERAL')
                
                with c_prod2:
                    item_fornecedor = st.selectbox("Fornecedor", list_fornecedores, key="item_forn")
                
                with c_prod3:
                    item_grupo = st.selectbox("Grupo", list_grupos, index=list_grupos.index(grupo_padrao) if grupo_padrao in list_grupos else 0, key="item_grup")

                with c_prod4:
                    item_preco = st.number_input("Preço Unit. Venda (R$)", value=float(prod_info['valor_venda']), min_value=0.0, key="item_prec")

                c_qtd1, c_qtd2 = st.columns([2, 2])
                with c_qtd1:
                    item_qtd = st.number_input("Quantidade", min_value=0.01, value=1.0, step=0.1, key="item_qtd")

            st.write("")
            if st.button("➕ Adicionar Produto à Lista"):
                total_item = item_qtd * item_preco
                st.session_state.carrinho_pedido.append({
                    'produto': item_produto,
                    'fornecedor': item_fornecedor,
                    'grupo': item_grupo,
                    'quantidade': item_qtd,
                    'valor_unitario': item_preco,
                    'valor_total': total_item
                })
                st.success(f"'{item_produto}' adicionado!")

            st.markdown("---")
            st.write("### 📜 Lista de Itens no Pedido Atual")
            
            if len(st.session_state.carrinho_pedido) == 0:
                st.info("Sua lista está vazia. Adicione produtos acima.")
            else:
                df_cart = pd.DataFrame(st.session_state.carrinho_pedido)
                st.dataframe(df_cart[['produto', 'quantidade', 'valor_unitario', 'valor_total']], use_container_width=True)
                
                total_geral_pedido = df_cart['valor_total'].sum()
                st.markdown(f"### 💰 **Valor Total do Pedido: R$ {total_geral_pedido:,.2f}**")
                
                ped_obs = st.text_area("Observações Gerais do Pedido")

                col_b1, col_b2 = st.columns(2)
                with col_b1:
                    if st.button("✅ Finalizar e Enviar Pedido"):
                        data_hoje = datetime.now().strftime('%Y-%m-%d %H:%M')
                        codigo_ped = f"PED-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                        
                        for item in st.session_state.carrinho_pedido:
                            cursor.execute('''
                                INSERT INTO pedidos (codigo_pedido, cliente, produto, fornecedor, grupo, quantidade, valor_unitario, valor_total, status, observacoes, data)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (codigo_ped, ped_cliente, item['produto'], item['fornecedor'], item['grupo'], item['quantidade'], item['valor_unitario'], item['valor_total'], ped_status, ped_obs, data_hoje))
                        
                        conn.commit()
                        st.session_state.carrinho_pedido = []
                        st.success(f"Pedido enviado com sucesso! (Código: {codigo_ped})")
                        st.rerun()

                with col_b2:
                    if st.button("🗑️ Limpar Lista"):
                        st.session_state.carrinho_pedido = []
                        st.rerun()

    with tab_lista:
        query_ped = "SELECT * FROM pedidos WHERE 1=1"
        params = []

        if tipo_acesso == "👤 Portal do Cliente":
            query_ped += " AND cliente = ?"
            params.append(cliente_autenticado)
        else:
            st.subheader("🔍 Filtros de Relatório de Pedidos")
            col_f1, col_f2, col_f3 = st.columns(3)
            with col_f1:
                filtro_cliente = st.selectbox("Filtrar por Cliente", ["Todas as vendas"] + list_clientes, key="f_cli_p")
                filtro_fornecedor = st.selectbox("Filtrar por Fornecedor", ["Todos os fornecedores"] + list_fornecedores, key="f_forn_p")
            with col_f2:
                filtro_grupo = st.selectbox("Filtrar por Grupo", ["Todos os grupos"] + list_grupos, key="f_grp_p")
                filtro_status = st.selectbox("Filtrar por Status", ["Todos", "Pendente", "Em Andamento", "Concluído (Convertido)", "Cancelado"], key="f_stat_p")
            with col_f3:
                data_ini = st.date_input("Data Inicial", value=date(2024, 1, 1), key="d_ini_p")
                data_fim = st.date_input("Data Final", value=date.today(), key="d_fim_p")

            if filtro_cliente != "Todas as vendas":
                query_ped += " AND cliente = ?"
                params.append(filtro_cliente)
                
            if filtro_fornecedor != "Todos os fornecedores":
                query_ped += " AND fornecedor = ?"
                params.append(filtro_fornecedor)
                
            if filtro_grupo != "Todos os grupos":
                query_ped += " AND grupo = ?"
                params.append(filtro_grupo)

            if filtro_status != "Todos":
                query_ped += " AND status = ?"
                params.append(filtro_status)
            
        query_ped += " ORDER BY id DESC"
        
        pedidos_df = pd.read_sql_query(query_ped, conn, params=params)
        
        if tipo_acesso != "👤 Portal do Cliente" and not pedidos_df.empty and 'data' in pedidos_df.columns:
            pedidos_df['data_dt'] = pd.to_datetime(pedidos_df['data'], errors='coerce').dt.date
            pedidos_df = pedidos_df[(pedidos_df['data_dt'] >= data_ini) & (pedidos_df['data_dt'] <= data_fim)]
            pedidos_df = pedidos_df.drop(columns=['data_dt'])

        st.markdown("---")
        
        if pedidos_df.empty:
            st.warning("Nenhum pedido encontrado.")
        else:
            total_filtrado = pedidos_df['valor_total'].sum()
            st.write(f"**Itens Registrados:** {len(pedidos_df)} | **Soma dos Valores:** R$ {total_filtrado:,.2f}")
            
            if 'valor_unitario' not in pedidos_df.columns or pedidos_df['valor_unitario'].isnull().all():
                pedidos_df['valor_unitario'] = pedidos_df['valor_total'] / pedidos_df['quantidade']

            cols_exibicao = ['id', 'codigo_pedido', 'data', 'cliente', 'produto', 'quantidade', 'valor_unitario', 'valor_total', 'status']
            
            if tipo_acesso == "👤 Portal do Cliente":
                st.dataframe(pedidos_df[cols_exibicao], use_container_width=True)
            else:
                st.info("💡 **Dica:** Clique duas vezes em qualquer valor da coluna **`quantidade`** OU **`valor_unitario`** para editar diretamente.", icon="✏️")
                df_editavel = st.data_editor(
                    pedidos_df[cols_exibicao],
                    key="editor_pedidos_direto",
                    use_container_width=True,
                    disabled=['id', 'codigo_pedido', 'data', 'cliente', 'produto', 'valor_total', 'status'],
                    column_config={
                        "quantidade": st.column_config.NumberColumn("Quantidade", min_value=0.01, step=0.1, format="%.2f"),
                        "valor_unitario": st.column_config.NumberColumn("Valor Unitário (R$)", min_value=0.0, step=0.5, format="R$ %.2f"),
                        "valor_total": st.column_config.NumberColumn("Valor Total (R$)", format="R$ %.2f")
                    }
                )

                if st.button("💾 Salvar Alterações da Tabela", type="primary", key="btn_save_pedidos"):
                    for idx, row in df_editavel.iterrows():
                        id_row = int(row['id'])
                        q_nova = float(row['quantidade'])
                        v_unit_novo = float(row['valor_unitario'])
                        v_tot_novo = q_nova * v_unit_novo
                        
                        cursor.execute('''
                            UPDATE pedidos 
                            SET quantidade = ?, valor_unitario = ?, valor_total = ? 
                            WHERE id = ?
                        ''', (q_nova, v_unit_novo, v_tot_novo, id_row))
                    
                    conn.commit()
                    st.success("✅ Alterações salvas com sucesso!")
                    st.rerun()

            st.markdown("---")
            st.subheader("📊 Agrupamento do Período / Seleção")
            
            df_agrupado = pedidos_df.groupby('produto', as_index=False).agg({
                'quantidade': 'sum',
                'valor_total': 'sum'
            })
            
            df_agrupado['valor_unitario_medio'] = df_agrupado['valor_total'] / df_agrupado['quantidade']
            df_agrupado_exibicao = df_agrupado[['produto', 'quantidade', 'valor_unitario_medio', 'valor_total']].copy()
            
            st.dataframe(
                df_agrupado_exibicao,
                column_config={
                    "produto": "Produto",
                    "quantidade": st.column_config.NumberColumn("Quantidade Total", format="%.2f"),
                    "valor_unitario_medio": st.column_config.NumberColumn("Valor Unitário Médio (R$)", format="R$ %.2f"),
                    "valor_total": st.column_config.NumberColumn("Valor Total (R$)", format="R$ %.2f"),
                },
                hide_index=True,
                use_container_width=True
            )

            pdf_bytes = gerar_pdf_relatorio(df_agrupado, titulo=f"Relatório de Pedidos - {cliente_autenticado if tipo_acesso == '👤 Portal do Cliente' else 'Geral'}")
            
            st.download_button(
                label="📄 Baixar Relatório Consolidado em PDF",
                data=pdf_bytes,
                file_name=f"Relatorio_Pedidos_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                mime="application/pdf",
                use_container_width=True
            )

# -----------------------------------------------------------------------------
# RESTANTE DAS TELAS DE ADMINISTRAÇÃO
# -----------------------------------------------------------------------------
elif menu == "🛒 Registrar Venda":
    st.title("🛒 Gerenciamento & Lançamento de Vendas")
    st.info("Página de vendas restrita ao ambiente administrativo.")

elif menu == "📥 Entrada de Estoque (Compras)":
    st.title("📥 Registro de Compras & Entrada de Estoque")
    st.info("Página de compras restrita ao ambiente administrativo.")

elif menu == "📦 Estoque de Produtos":
    st.title("📦 Consulta & Atualização de Estoque")
    df_estoque = pd.read_sql_query("SELECT * FROM produtos", conn)
    st.dataframe(df_estoque, use_container_width=True)

elif menu == "👥 Cadastros (Clientes / Fornecedores / Grupos)":
    st.title("👥 Cadastros Gerais")
    st.info("Página de cadastros restrita ao ambiente administrativo.")
