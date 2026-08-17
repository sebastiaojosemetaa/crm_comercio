import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="CRM Comércio - Rey da Cebola", layout="wide")

# --- CONEXÃO E ESTRUTURA DO BANCO ---
def get_connection():
    return sqlite3.connect("crm_comercio.db", check_same_thread=False)

conn = get_connection()

def inicializar_banco():
    cursor = conn.cursor()
    # Tabelas essenciais
    cursor.execute("CREATE TABLE IF NOT EXISTS vendas (id INTEGER PRIMARY KEY, cliente TEXT, produto TEXT, quantidade REAL, valor_venda REAL, valor_total REAL, data TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS produtos (id INTEGER PRIMARY KEY, nome TEXT UNIQUE, preco_custo REAL, preco_venda REAL, estoque_atual REAL)")
    cursor.execute("CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY, nome TEXT UNIQUE)")
    cursor.execute("CREATE TABLE IF NOT EXISTS fornecedores (id INTEGER PRIMARY KEY, nome TEXT UNIQUE)")
    
    # Dados de teste se estiver vazio
    cursor.execute("INSERT OR IGNORE INTO produtos (nome, preco_custo, preco_venda, estoque_atual) VALUES ('CEBOLA', 2.0, 5.0, 100.0)")
    cursor.execute("INSERT OR IGNORE INTO clientes (nome) VALUES ('CLIENTE PADRÃO')")
    conn.commit()

inicializar_banco()

# --- FUNÇÕES DE APOIO ---
def buscar_opcoes(tabela, coluna):
    try:
        df = pd.read_sql_query(f"SELECT {coluna} FROM {tabela}", conn)
        return df[coluna].tolist() if not df.empty else ["NENHUM"]
    except: return ["NENHUM"]

# --- BARRA LATERAL ---
st.sidebar.title("🔐 Acesso")
perfil = st.sidebar.radio("Selecione o Perfil:", ["Portal do Cliente", "Administração / Vendedor"])

if perfil == "Administração / Vendedor":
    senha = st.sidebar.text_input("Senha", type="password")
    if senha == "1234":
        menu = st.sidebar.radio("Navegação", [
            "Fechamento & Financeiro", 
            "Registrar Venda", 
            "Entrada de Estoque (Compras)", 
            "Estoque de Produtos", 
            "Cadastros"
        ])

        # --- TELA: REGISTRAR VENDA ---
        if menu == "Registrar Venda":
            st.title("🛒 Registrar Venda")
            clientes = buscar_opcoes("clientes", "nome")
            produtos = buscar_opcoes("produtos", "nome")
            
            with st.form("venda_form"):
                c = st.selectbox("Cliente", clientes)
                p = st.selectbox("Produto", produtos)
                q = st.number_input("Quantidade", min_value=0.1, value=1.0)
                v = st.number_input("Valor Unitário", value=5.0)
                btn = st.form_submit_button("Finalizar Venda")
                
                if btn:
                    total = q * v
                    data = datetime.now().strftime("%d/%m/%Y %H:%M")
                    conn.execute("INSERT INTO vendas (cliente, produto, quantidade, valor_venda, valor_total, data) VALUES (?,?,?,?,?,?)", 
                                 (c, p, q, v, total, data))
                    conn.execute("UPDATE produtos SET estoque_atual = estoque_atual - ? WHERE nome = ?", (q, p))
                    conn.commit()
                    st.success("Venda registrada com sucesso!")

        # --- TELA: ENTRADA DE ESTOQUE ---
        elif menu == "Entrada de Estoque (Compras)":
            st.title("📥 Entrada de Estoque")
            produtos = buscar_opcoes("produtos", "nome")
            with st.form("compra_form"):
                p = st.selectbox("Produto", produtos)
                q = st.number_input("Quantidade de Entrada", min_value=0.1, value=1.0)
                btn = st.form_submit_button("Confirmar Entrada")
                
                if btn:
                    conn.execute("UPDATE produtos SET estoque_atual = estoque_atual + ? WHERE nome = ?", (q, p))
                    conn.commit()
                    st.success(f"Estoque de {p} atualizado!")

        # --- TELA: ESTOQUE DE PRODUTOS ---
        elif menu == "Estoque de Produtos":
            st.title("📦 Estoque Atual")
            df = pd.read_sql_query("SELECT * FROM produtos", conn)
            st.data_editor(df, use_container_width=True)

        # --- TELA: FINANCEIRO ---
        elif menu == "Fechamento & Financeiro":
            st.title("📊 Fechamento")
            df = pd.read_sql_query("SELECT * FROM vendas", conn)
            if not df.empty:
                st.metric("Total Vendido", f"R$ {df['valor_total'].sum():.2f}")
                st.dataframe(df)
            else: st.write("Nenhuma venda registrada.")

        # --- TELA: CADASTROS ---
        elif menu == "Cadastros":
            st.title("👥 Cadastros Gerais")
            tab1, tab2 = st.tabs(["Cliente", "Produto"])
            with tab1:
                nome_c = st.text_input("Nome do Novo Cliente")
                if st.button("Salvar Cliente"):
                    conn.execute("INSERT INTO clientes (nome) VALUES (?)", (nome_c,))
                    conn.commit()
                    st.success("Cliente salvo!")
            with tab2:
                nome_p = st.text_input("Nome do Produto")
                custo = st.number_input("Custo")
                venda = st.number_input("Preço Venda")
                if st.button("Salvar Produto"):
                    conn.execute("INSERT INTO produtos (nome, preco_custo, preco_venda, estoque_atual) VALUES (?,?,?,0)", (nome_p, custo, venda))
                    conn.commit()
                    st.success("Produto salvo!")

    else:
        st.warning("Por favor, digite a senha 1234 para acessar.")
