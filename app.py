import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# -----------------------------------------------------------------------------
# CONFIGURAÇÃO E CONEXÃO
# -----------------------------------------------------------------------------
st.set_page_config(page_title="CRM Comércio - Rey da Cebola", layout="wide")
conn = sqlite3.connect("crm_comercio.db", check_same_thread=False)

# Inicializa estado da sessão
if 'admin_logged' not in st.session_state: st.session_state.admin_logged = False
if 'cliente_autenticado' not in st.session_state: st.session_state.cliente_autenticado = None
if 'carrinho_pdv' not in st.session_state: st.session_state.carrinho_pdv = []

def carregar_dados(query): return pd.read_sql_query(query, conn)
def carregar_coluna(tabela, coluna):
    df = carregar_dados(f"SELECT DISTINCT {coluna} FROM {tabela} WHERE {coluna} IS NOT NULL")
    return df[coluna].tolist() if not df.empty else []

def salvar_pedido_ou_venda(cliente, produto, quantidade, valor_venda, forma_pagamento, tipo):
    cursor = conn.cursor()
    cursor.execute("INSERT INTO vendas (cliente, produto, quantidade, valor_venda, valor_total, forma_pagamento, tipo, data) VALUES (?,?,?,?,?,?,?,?)",
                   (cliente, produto, quantidade, valor_venda, quantidade*valor_venda, forma_pagamento, tipo, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()

# -----------------------------------------------------------------------------
# INTERFACE
# -----------------------------------------------------------------------------
st.sidebar.title("🔑 Acesso ao Sistema")
perfil = st.sidebar.radio("Perfil:", ["👤 Portal do Cliente", "🔒 Administração / Vendedor"])

if perfil == "👤 Portal do Cliente":
    st.title("🛍️ Portal do Cliente")
    # Aqui entra a lógica de autenticação que você já tinha:
    lista_clientes = carregar_coluna("clientes", "nome")
    cliente_sel = st.sidebar.selectbox("Seu Nome:", lista_clientes)
    if st.sidebar.button("Acessar Pedidos"):
        st.session_state.cliente_autenticado = cliente_sel
    
    if st.session_state.cliente_autenticado:
        st.subheader(f"Bem-vindo, {st.session_state.cliente_autenticado}")
        st.dataframe(carregar_dados(f"SELECT * FROM vendas WHERE cliente = '{st.session_state.cliente_autenticado}'"))
    else:
        st.info("Selecione seu nome na barra lateral para ver seus pedidos.")

else: # ADMINISTRAÇÃO
    if not st.session_state.admin_logged:
        senha = st.sidebar.text_input("Senha Admin:", type="password")
        if st.sidebar.button("Entrar"):
            if senha == "1234": st.session_state.admin_logged = True; st.rerun()
    else:
        menu = st.sidebar.radio("Navegação", ["💸 Frente de Caixa (PDV)", "📊 Financeiro", "📦 Estoque"])
        
        if menu == "💸 Frente de Caixa (PDV)":
            st.title("💸 Frente de Caixa (PDV)")
            produtos_lista = carregar_coluna("produtos", "nome")
            
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                prod_sel = st.selectbox("Produto", produtos_lista)
                df_p = carregar_dados(f"SELECT valor_venda FROM produtos WHERE nome = '{prod_sel}'")
                preco = float(df_p.iloc[0,0]) if not df_p.empty else 0.0
                st.write(f"💰 Preço unitário: **R$ {preco:,.2f}**")
            with col2:
                qtd_sel = st.number_input("Qtd", min_value=0.1, value=1.0)
            with col3:
                st.write("###")
                if st.button("➕ Adicionar"):
                    st.session_state.carrinho_pdv.append({'produto': prod_sel, 'quantidade': qtd_sel, 'valor_unitario': preco, 'valor_total': qtd_sel * preco})
                    st.rerun()
            
            if st.session_state.carrinho_pdv:
                st.table(pd.DataFrame(st.session_state.carrinho_pdv))
                if st.button("✅ FINALIZAR VENDA"):
                    for item in st.session_state.carrinho_pdv:
                        salvar_pedido_ou_venda("Balcão", item['produto'], item['quantidade'], item['valor_unitario'], "Dinheiro", "VENDA")
                        conn.cursor().execute("UPDATE produtos SET estoque_atual = estoque_atual - ? WHERE nome = ?", (item['quantidade'], item['produto']))
                    conn.commit()
                    st.session_state.carrinho_pdv = []
                    st.success("Venda realizada!"); st.rerun()

        elif menu == "📊 Financeiro":
            st.title("Relatório de Vendas")
            st.dataframe(carregar_dados("SELECT * FROM vendas"))
            
        elif menu == "📦 Estoque":
            st.title("Estoque")
            st.dataframe(carregar_dados("SELECT * FROM produtos"))
