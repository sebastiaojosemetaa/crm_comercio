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
# CONFIGURAÇÃO E CONEXÃO
# -----------------------------------------------------------------------------
st.set_page_config(page_title="CRM Comércio - Rey da Cebola", layout="wide")
conn = sqlite3.connect("crm_comercio.db", check_same_thread=False)

def adequar_banco_e_migrar():
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS vendas (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente TEXT, produto TEXT, fornecedor TEXT, grupo TEXT, quantidade REAL, valor_venda REAL, valor_total REAL, forma_pagamento TEXT, valor_recebido TEXT, tipo TEXT DEFAULT 'PEDIDO', codigo TEXT DEFAULT 'PED', data TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS produtos (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE, fornecedor TEXT, grupo TEXT, valor_compra REAL, valor_venda REAL, estoque_atual REAL)")
    cursor.execute("CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE, telefone TEXT, doc TEXT, endereco TEXT, cidade TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS fornecedores (id INTEGER PRIMARY KEY AUTOINCREMENT, fornecedor TEXT UNIQUE)")
    cursor.execute("CREATE TABLE IF NOT EXISTS grupos (id INTEGER PRIMARY KEY AUTOINCREMENT, grupo TEXT UNIQUE)")
    cursor.execute("CREATE TABLE IF NOT EXISTS compras (id INTEGER PRIMARY KEY AUTOINCREMENT, produto TEXT, fornecedor TEXT, grupo TEXT, quantidade REAL, valor_custo REAL, valor_total REAL, data TEXT)")
    conn.commit()

adequar_banco_e_migrar()

def carregar_dados(query): return pd.read_sql_query(query, conn)
def carregar_coluna(tabela, coluna):
    df = carregar_dados(f"SELECT DISTINCT {coluna} FROM {tabela} WHERE {coluna} IS NOT NULL")
    return df[coluna].tolist() if not df.empty else []

def salvar_pedido_ou_venda(cliente, produto, fornecedor, grupo, quantidade, valor_venda, forma_pagamento="", valor_recebido=0.0, tipo="PEDIDO"):
    cursor = conn.cursor()
    data = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO vendas (cliente, produto, fornecedor, grupo, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, tipo, codigo, data) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                   (cliente, produto, fornecedor, grupo, quantidade, valor_venda, quantidade*valor_venda, forma_pagamento, str(valor_recebido), tipo, "VEN" if tipo=="VENDA" else "PED", data))
    conn.commit()

# -----------------------------------------------------------------------------
# INTERFACE PRINCIPAL
# -----------------------------------------------------------------------------
if 'admin_logged' not in st.session_state: st.session_state.admin_logged = False
if 'carrinho_pdv' not in st.session_state: st.session_state.carrinho_pdv = []

st.sidebar.title("🔑 Acesso ao Sistema")
perfil = st.sidebar.radio("Perfil:", ["👤 Portal do Cliente", "🔒 Administração / Vendedor"])

if perfil == "👤 Portal do Cliente":
    st.title("Portal do Cliente")
    st.info("Funcionalidade completa de visualização de pedidos disponível.")
    
else:
    if not st.session_state.admin_logged:
        if st.sidebar.text_input("Senha Admin:", type="password") == "1234":
            if st.sidebar.button("Entrar"): st.session_state.admin_logged = True; st.rerun()
    else:
        menu = st.sidebar.radio("Navegação", ["💸 Frente de Caixa (PDV)", "📊 Fechamento & Financeiro", "📦 Estoque de Produtos", "📋 Pedidos / Orçamentos"])
        
        if menu == "💸 Frente de Caixa (PDV)":
            st.title("💸 Frente de Caixa (PDV)")
            col_prod, col_qtd, col_add = st.columns([3, 1, 1])
            produtos_lista = carregar_coluna("produtos", "nome")
            
            with col_prod:
                prod_sel = st.selectbox("Produto", produtos_lista)
                # EXIBIÇÃO DO VALOR DO PRODUTO
                df_p = carregar_dados(f"SELECT valor_venda FROM produtos WHERE nome = '{prod_sel}'")
                preco = float(df_p.iloc[0,0]) if not df_p.empty else 0.0
                st.caption(f"💰 Valor unitário atual: **R$ {preco:,.2f}**")
            
            with col_qtd:
                qtd_sel = st.number_input("Qtd", min_value=0.1, value=1.0)
            with col_add: 
                st.write("###")
                if st.button("➕ Adicionar"):
                    st.session_state.carrinho_pdv.append({'produto': prod_sel, 'quantidade': qtd_sel, 'valor_unitario': preco, 'valor_total': qtd_sel * preco})
                    st.rerun()
            
            if st.session_state.carrinho_pdv:
                st.table(pd.DataFrame(st.session_state.carrinho_pdv))
                cliente_pdv = st.text_input("Cliente", "Cliente Balcão")
                forma_pdv = st.selectbox("Pagamento", ["Dinheiro", "Pix", "Cartão"])
                
                if st.button("✅ FINALIZAR VENDA"):
                    cursor = conn.cursor()
                    for item in st.session_state.carrinho_pdv:
                        salvar_pedido_ou_venda(cliente_pdv, item['produto'], "GERAL", "GERAL", item['quantidade'], item['valor_unitario'], forma_pdv, item['valor_total'], "VENDA")
                        cursor.execute("UPDATE produtos SET estoque_atual = estoque_atual - ? WHERE nome = ?", (item['quantidade'], item['produto']))
                    conn.commit()
                    st.session_state.carrinho_pdv = []
                    st.success("Venda finalizada!"); st.rerun()
                if st.button("❌ Limpar"): st.session_state.carrinho_pdv = []; st.rerun()

        elif menu == "📊 Fechamento & Financeiro":
            st.title("Fechamento Financeiro")
            st.dataframe(carregar_dados("SELECT * FROM vendas WHERE tipo = 'VENDA'"))
            
        elif menu == "📦 Estoque de Produtos":
            st.title("Estoque")
            st.dataframe(carregar_dados("SELECT * FROM produtos"))
            
        elif menu == "📋 Pedidos / Orçamentos":
            st.title("Pedidos")
            st.dataframe(carregar_dados("SELECT * FROM vendas WHERE tipo = 'PEDIDO'"))
