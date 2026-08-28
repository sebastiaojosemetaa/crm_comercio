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

def salvar_cliente_completo(nome, telefone, doc, endereco, cidade):
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO clientes (nome, telefone, doc, endereco, cidade) VALUES (?, ?, ?, ?, ?)",
                       (nome.strip(), telefone, doc, endereco, cidade))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def salvar_produto_completo(nome, fornecedor, group, preco_custo, preco_venda, estoque_inicial):
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO produtos (nome, fornecedor, grupo, valor_compra, valor_venda, estoque_atual) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (nome.strip(), fornecedor, group, preco_custo, preco_venda, estoque_inicial))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        cursor.execute("""
            UPDATE produtos 
            SET fornecedor = ?, grupo = ?, valor_compra = ?, valor_venda = ?, estoque_atual = ?
            WHERE TRIM(nome) = TRIM(?)
        """, (fornecedor, group, preco_custo, preco_venda, estoque_inicial, nome.strip()))
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

def salvar_pedido_ou_venda(cliente, produto, fornecedor, group, quantidade, valor_venda, forma_pagamento="", valor_recebido=0.0, tipo="PEDIDO"):
    cursor = conn.cursor()
    valor_total = quantidade * valor_venda
    data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cod_status = "VEN" if tipo.upper() in ["VENDA", "VENDAS", "VEN"] else "PED"
    
    cursor.execute("""
        INSERT INTO vendas (cliente, produto, fornecedor, grupo, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, tipo, codigo, data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (cliente.strip(), produto, fornecedor, group, quantidade, valor_venda, valor_total, forma_pagamento, str(valor_recebido), tipo, cod_status, data_atual))
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

def registrar_compra(produto, fornecedor, group, quantidade, valor_custo):
    cursor = conn.cursor()
    valor_total = quantidade * valor_custo
    data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO compras (produto, fornecedor, grupo, quantidade, valor_custo, valor_total, data)
        VALUES (?, ?, ?, ?, ?, ?, ?)
