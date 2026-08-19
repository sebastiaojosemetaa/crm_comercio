import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# -----------------------------------------------------------------------------
# CONFIGURAÇÃO E CONEXÃO SEGURA
# -----------------------------------------------------------------------------
st.set_page_config(page_title="CRM Comércio - Rey da Cebola", layout="wide")
conn = sqlite3.connect("crm_comercio.db", check_same_thread=False)

def inicializar_banco():
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS vendas (id INTEGER PRIMARY KEY, cliente TEXT, produto TEXT, quantidade REAL, valor_venda REAL, valor_total REAL, forma_pagamento TEXT, tipo TEXT, data TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS produtos (id INTEGER PRIMARY KEY, nome TEXT UNIQUE, valor_venda REAL, estoque_atual REAL)")
    cursor.execute("CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY, nome TEXT UNIQUE)")
    conn.commit()

inicializar_banco()

# Inicializa estados
if 'admin_logged' not in st.session_state: st.session_state.admin_logged = False
if 'cliente_autenticado' not in st.session_state: st.session_state.cliente_autenticado = None
if 'carrinho_pdv' not in st.session_state: st.session_state.carrinho_pdv = []

def carregar_dados(query): 
    try: return pd.read_sql_query(query, conn)
    except: return pd.DataFrame()

def carregar_coluna(tabela, coluna):
    df = carregar_dados(f"SELECT {coluna} FROM {tabela}")
    return df[coluna].tolist() if not df.empty else []

# -----------------------------------------------------------------------------
# INTERFACE
# -----------------------------------------------------------------------------
st.sidebar.title("🔑 Acesso ao Sistema")
perfil = st.sidebar.radio("Perfil:", ["👤 Portal do Cliente", "🔒 Administração / Vendedor"])

if perfil == "👤 Portal do Cliente":
    st.title("🛍️ Portal do Cliente")
    lista_clientes = carregar_coluna("clientes", "nome")
    cliente_sel = st.sidebar.selectbox("Seu Nome:", lista_clientes if lista_clientes else ["Nenhum cliente"])
    
    if st.sidebar.button("Acessar Pedidos"):
        st.session_state.cliente_autenticado = cliente_sel
    
    if st.session_state.cliente_autenticado:
        st.subheader(f"Bem-vindo, {st.session_state.cliente_autenticado}")
        st.dataframe(carregar_dados(f"SELECT * FROM vendas WHERE cliente = '{st.session_state.cliente_autenticado}'"))

else:
    if not st.session_state.admin_logged:
        if st.sidebar.text_input("Senha Admin:", type="password") == "1234":
            if st.sidebar.button("Entrar"): st.session_state.admin_logged = True; st.rerun()
    else:
        menu = st.sidebar.radio("Navegação", ["💸 Frente de Caixa (PDV)", "📊 Financeiro", "📦 Estoque"])
        
        if menu == "💸 Frente de Caixa (PDV)":
            st.title("💸 Frente de Caixa")
            produtos_lista = carregar_coluna("produtos", "nome")
            prod_sel = st.selectbox("Produto", produtos_lista if produtos_lista else ["Sem produtos"])
            
            df_p = carregar_dados(f"SELECT valor_venda FROM produtos WHERE nome = '{prod_sel}'")
            preco = float(df_p.iloc[0,0]) if not df_p.empty else 0.0
            st.write(f"💰 Preço unitário: **R$ {preco:,.2f}**")
            
            qtd_sel = st.number_input("Qtd", min_value=0.1, value=1.0)
            if st.button("➕ Adicionar"):
                st.session_state.carrinho_pdv.append({'produto': prod_sel, 'quantidade': qtd_sel, 'valor_unitario': preco, 'valor_total': qtd_sel * preco})
                st.rerun()
            
            if st.session_state.carrinho_pdv:
                st.table(pd.DataFrame(st.session_state.carrinho_pdv))
                if st.button("✅ FINALIZAR VENDA"):
                    for item in st.session_state.carrinho_pdv:
                        cursor = conn.cursor()
                        cursor.execute("INSERT INTO vendas (cliente, produto, quantidade, valor_venda, valor_total, forma_pagamento, tipo, data) VALUES (?,?,?,?,?,?,?,?)",
                                       ("Balcão", item['produto'], item['quantidade'], item['valor_unitario'], item['valor_total'], "Dinheiro", "VENDA", datetime.now().strftime("%Y-%m-%d")))
                        cursor.execute("UPDATE produtos SET estoque_atual = estoque_atual - ? WHERE nome = ?", (item['quantidade'], item['produto']))
                    conn.commit()
                    st.session_state.carrinho_pdv = []
                    st.success("Venda realizada!"); st.rerun()

        elif menu == "📊 Financeiro":
            st.dataframe(carregar_dados("SELECT * FROM vendas"))
        elif menu == "📦 Estoque":
            st.dataframe(carregar_dados("SELECT * FROM produtos"))
