import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# Configuração da página
st.set_page_config(page_title="CRM Comércio", page_icon="📦", layout="wide")

# Conexão com o Banco de Dados
def get_connection():
    return sqlite3.connect('crm_comercio.db', check_same_thread=False)

conn = get_connection()

# Leitura Segura de Tabelas
def safe_read_sql(query, params=None):
    try:
        return pd.read_sql_query(query, conn, params=params)
    except Exception:
        return pd.DataFrame()

# Menu Lateral
st.sidebar.title("CRM Comércio 📦")
menu = st.sidebar.radio(
    "Navegação",
    [
        "📊 Fechamento & Financeiro",
        "📑 Pedidos / Orçamentos",
        "🛒 Registrar Venda",
        "📥 Entrada de Estoque (Compras)",
        "📦 Estoque de Produtos",
        "👥 Cadastros (Clientes / Fornecedores / Grupos)"
    ]
)

# ------------------------------------------------------------------------------
# 1. FECHAMENTO & FINANCEIRO
# ------------------------------------------------------------------------------
if menu == "📊 Fechamento & Financeiro":
    st.title("📊 Painel Financeiro & Fechamento")
    
    df_vendas = safe_read_sql("SELECT * FROM vendas")
    
    if not df_vendas.empty:
        qtd = pd.to_numeric(df_vendas.get('quantidade', 0), errors='coerce').fillna(0)
        v_venda = pd.to_numeric(df_vendas.get('valor_venda', 0), errors='coerce').fillna(0)
        
        if 'valor_total' not in df_vendas.columns:
            df_vendas['valor_total'] = qtd * v_venda
        else:
            df_vendas['valor_total'] = pd.to_numeric(df_vendas['valor_total'], errors='coerce').fillna(qtd * v_venda)

        if 'valor_recebido' not in df_vendas.columns:
            if 'forma_pagamento' in df_vendas.columns:
                df_vendas['valor_recebido'] = df_vendas.apply(
                    lambda r: 0.0 if 'fiado' in str(r.get('forma_pagamento', '')).lower() else r['valor_total'], axis=1
                )
            else:
                df_vendas['valor_recebido'] = df_vendas['valor_total']
        else:
            df_vendas['valor_recebido'] = pd.to_numeric(df_vendas['valor_recebido'], errors='coerce').fillna(0.0)

        tot_faturamento = float(df_vendas['valor_total'].sum())
        tot_caixa = float(df_vendas['valor_recebido'].sum())
        tot_pendente = float(tot_faturamento - tot_caixa)
    else:
        tot_faturamento = 0.0
        tot_caixa = 0.0
        tot_pendente = 0.0

    col1, col2, col3 = st.columns(3)
    col1.metric("Faturamento Total", f"R$ {tot_faturamento:.2f}")
    col2.metric("Total Recebido em Caixa", f"R$ {tot_caixa:.2f}")
    col3.metric("Total a Receber (Fiado/Pendente)", f"R$ {tot_pendente:.2f}")

    st.markdown("---")
    st.subheader("📜 Resumo do Histórico de Vendas")
    st.dataframe(df_vendas, use_container_width=True)

# ------------------------------------------------------------------------------
# 2. PEDIDOS / ORÇAMENTOS
# ------------------------------------------------------------------------------
elif menu == "📑 Pedidos / Orçamentos":
    st.title("📑 Pedidos e Orçamentos")
    
    df_vendas = safe_read_sql("SELECT * FROM vendas")
    if 'tipo' in df_vendas.columns:
        df_pedidos = df_vendas[df_vendas['tipo'] == 'PEDIDO']
    else:
        df_pedidos = pd.DataFrame()

    if df_pedidos.empty:
        st.info("Nenhum pedido/orçamento registrado no momento.")
    else:
        st.dataframe(df_pedidos, use_container_width=True)

# ------------------------------------------------------------------------------
# 3. REGISTRAR VENDA
# ------------------------------------------------------------------------------
elif menu == "🛒 Registrar Venda":
    st.title("🛒 Nova Venda")

    df_clientes = safe_read_sql("SELECT * FROM clientes")
    df_produtos = safe_read_sql("SELECT * FROM produtos")

    col_prod = 'produto' if 'produto' in df_produtos.columns else 'nome' if 'nome' in df_produtos.columns else None

    if df_produtos.empty or col_prod is None:
        st.warning("Nenhum produto cadastrado no estoque.")
    else:
        lista_clientes = df_clientes['nome'].dropna().tolist() if not df_clientes.empty and 'nome' in df_clientes.columns else ["Consumidor Final"]
        cliente = st.selectbox("Cliente:", lista_clientes)
        
        lista_produtos = df_produtos[col_prod].dropna().tolist()
        produto_nome = st.selectbox("Selecione o Produto:", lista_produtos)

        prod_row = df_produtos[df_produtos[col_prod] == produto_nome].iloc[0]
        
        col_pv = 'valor_venda' if 'valor_venda' in prod_row else 'preco_venda' if 'preco_venda' in prod_row else None
        preco_padrao = float(prod_row[col_pv]) if col_pv and pd.notnull(prod_row[col_pv]) else 0.0

        quantidade = st.number_input("Quantidade:", min_value=0.1, value=1.0, step=0.5)
        preco_venda = st.number_input("Preço de Venda (R$):", min_value=0.0, value=preco_padrao)
        valor_total = quantidade * preco_venda

        st.markdown(f"### Total: **R$ {valor_total:.2f}**")

        forma_pag = st.selectbox("Forma de Pagamento:", ["Dinheiro", "PIX", "Cartão de Crédito", "Cartão de Débito", "Crediário / Fiado"])
        
        val_recebido_default = 0.0 if forma_pag == "Crediário / Fiado" else valor_total
        valor_recebido = st.number_input("Valor Recebido (R$):", min_value=0.0, value=float(val_recebido_default))

        if st.button("✅ Finalizar Venda", type="primary"):
            c = conn.cursor()
            
            fornecedor = prod_row.get('fornecedor', 'BAHIA')
            data_hoje = datetime.now().strftime('%Y-%m-%d %H:%M')
            
            c.execute("PRAGMA table_info(vendas)")
            vendas_cols = [col[1] for col in c.fetchall()]

            fields = ['cliente', 'produto', 'fornecedor', 'quantidade', 'valor_venda', 'valor_total', 'forma_pagamento', 'valor_recebido', 'data']
            values = [cliente, produto_nome, fornecedor, quantidade, preco_venda, valor_total, forma_pag, valor_recebido, data_hoje]

            valid_fields = [f for f in fields if f in vendas_cols]
            valid_values = [values[i] for i, f in enumerate(fields) if f in vendas_cols]

            placeholders = ", ".join(["?"] * len(valid_fields))
            cols_str = ", ".join(valid_fields)

            c.execute(f"INSERT INTO vendas ({cols_str}) VALUES ({placeholders})", valid_values)

            # Atualizar Estoque
            col_est = 'quantidade' if 'quantidade' in df_produtos.columns else 'estoque'
            est_atual = float(prod_row.get(col_est, 0))
            novo_est = est_atual - quantidade

            c.execute(f"UPDATE produtos SET {col_est} = ? WHERE id = ?", (novo_est, prod_row['id']))

            conn.commit()
            st.success("Venda registrada com sucesso!")
            st.rerun()

# ------------------------------------------------------------------------------
# 4. ENTRADA DE ESTOQUE
# ------------------------------------------------------------------------------
elif menu == "📥 Entrada de Estoque (Compras)":
    st.title("📥 Entrada de Estoque")
    
    df_produtos = safe_read_sql("SELECT * FROM produtos")
    col_prod = 'produto' if 'produto' in df_produtos.columns else 'nome' if 'nome' in df_produtos.columns else None

    if not df_produtos.empty and col_prod:
        produto_nome = st.selectbox("Selecione o Produto:", df_produtos[col_prod].dropna().tolist())
        qtd_entrada = st.number_input("Quantidade Adicionada:", min_value=0.1, value=10.0)

        if st.button("📥 Dar Entrada no Estoque"):
            prod_row = df_produtos[df_produtos[col_prod] == produto_nome].iloc[0]
            col_est = 'quantidade' if 'quantidade' in df_produtos.columns else 'estoque'
            novo_est = float(prod_row.get(col_est, 0)) + qtd_entrada
            
            c = conn.cursor()
            c.execute(f"UPDATE produtos SET {col_est} = ? WHERE id = ?", (novo_est, prod_row['id']))
            conn.commit()
            st.success(f"Estoque do produto '{produto_nome}' atualizado para {novo_est}!")
            st.rerun()
    else:
        st.info("Nenhum produto cadastrado.")

# ------------------------------------------------------------------------------
# 5. ESTOQUE DE PRODUTOS
# ------------------------------------------------------------------------------
elif menu == "📦 Estoque de Produtos":
    st.title("📦 Cadastro & Consulta de Produtos")

    with st.expander("➕ Cadastrar Novo Produto"):
        c_nome = st.text_input("Nome do Produto")
        c_forn = st.text_input("Fornecedor", value="BAHIA")
        c_grup = st.text_input("Grupo", value="Geral")
        c_custo = st.number_input("Preço de Custo (R$)", min_value=0.0)
        c_venda = st.number_input("Preço de Venda (R$)", min_value=0.0)
        c_est = st.number_input("Estoque Inicial", min_value=0.0)

        if st.button("Salvar Produto"):
            c = conn.cursor()
            c.execute("PRAGMA table_info(produtos)")
            cols_db = [col[1] for col in c.fetchall()]

            col_p = 'produto' if 'produto' in cols_db else 'nome'
            col_q = 'quantidade' if 'quantidade' in cols_db else 'estoque'
            col_vc = 'valor_compra' if 'valor_compra' in cols_db else 'preco_custo'
            col_vv = 'valor_venda' if 'valor_venda' in cols_db else 'preco_venda'

            c.execute(f'''
                INSERT INTO produtos ({col_p}, {col_q}, {col_vc}, {col_vv}, grupo, fornecedor)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (c_nome, c_est, c_custo, c_venda, c_grup, c_forn))

            conn.commit()
            st.success("Produto cadastrado com sucesso!")
            st.rerun()

    df_produtos = safe_read_sql("SELECT * FROM produtos")
    st.dataframe(df_produtos, use_container_width=True)

# ------------------------------------------------------------------------------
# 6. CADASTROS
# ------------------------------------------------------------------------------
elif menu == "👥 Cadastros (Clientes / Fornecedores / Grupos)":
    st.title("👥 Cadastros do Sistema")

    tab1, tab2, tab3 = st.tabs(["Clientes", "Fornecedores", "Grupos"])

    with tab1:
        st.subheader("Cadastrar Cliente")
        nome_cli = st.text_input("Nome do Cliente")
        tel_cli = st.text_input("Telefone / WhatsApp")
        if st.button("Salvar Cliente"):
            if nome_cli:
                c = conn.cursor()
                c.execute("INSERT INTO clientes (nome, telefone) VALUES (?, ?)", (nome_cli, tel_cli))
                conn.commit()
                st.success("Cliente cadastrado!")
                st.rerun()

        st.dataframe(safe_read_sql("SELECT * FROM clientes"), use_container_width=True)

    with tab2:
        st.subheader("Cadastrar Fornecedor")
        nome_forn = st.text_input("Nome do Fornecedor")
        if st.button("Salvar Fornecedor"):
            if nome_forn:
                c = conn.cursor()
                c.execute("INSERT INTO fornecedores (nome) VALUES (?)", (nome_forn,))
                conn.commit()
                st.success("Fornecedor cadastrado!")
                st.rerun()

        st.dataframe(safe_read_sql("SELECT * FROM fornecedores"), use_container_width=True)

    with tab3:
        st.subheader("Cadastrar Grupo")
        nome_grup = st.text_input("Nome do Grupo")
        if st.button("Salvar Grupo"):
            if nome_grup:
                c = conn.cursor()
                c.execute("INSERT INTO grupos (nome) VALUES (?)", (nome_grup,))
                conn.commit()
                st.success("Grupo cadastrado!")
                st.rerun()

        st.dataframe(safe_read_sql("SELECT * FROM grupos"), use_container_width=True)
