import io
import sqlite3
from datetime import date, datetime

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
import streamlit as st

st.set_page_config(
    page_title="CRM Comércio - Gestão Completa", layout="wide", page_icon="📦"
)

# -----------------------------------------------------------------------------
# DEFINIÇÃO DE SENHAS
# -----------------------------------------------------------------------------
SENHA_ADMIN = "13142715"
Neurialdo = "456892"

SENHAS_CLIENTES = {
    "Carlos Alberto": "1234",
    "Sebastião": "123456",
    "Valeilde Loja 01": "12345",
}
SENHA_CLIENTE_PADRAO = "0000"

# -----------------------------------------------------------------------------
# CONEXÃO E CRIAÇÃO DO BANCO DE DADOS
# -----------------------------------------------------------------------------
conn = sqlite3.connect("crm_comercio.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS produtos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        produto TEXT UNIQUE,
        grupo TEXT DEFAULT 'Geral',
        quantidade REAL DEFAULT 0.0,
        valor_compra REAL DEFAULT 0.0,
        valor_venda REAL DEFAULT 0.0
    )
""")

cursor.execute("""
    CREATE TABLE IF NOT EXISTS clientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente TEXT UNIQUE,
        cpf TEXT,
        endereco TEXT,
        email TEXT,
        fone TEXT
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
        valor_compra REAL,
        valor_venda REAL,
        valor_total REAL,
        data TEXT
    )
""")

cursor.execute("""
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
""")

cursor.execute("""
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
""")
conn.commit()

# Compatibilidade de colunas
for query in [
    "ALTER TABLE pedidos ADD COLUMN codigo_pedido TEXT",
    "ALTER TABLE produtos ADD COLUMN grupo TEXT DEFAULT 'Geral'",
    "ALTER TABLE pedidos ADD COLUMN fornecedor TEXT DEFAULT 'Geral'",
    "ALTER TABLE pedidos ADD COLUMN grupo TEXT DEFAULT 'Geral'",
    "ALTER TABLE vendas ADD COLUMN grupo TEXT DEFAULT 'Geral'",
    "ALTER TABLE vendas ADD COLUMN fornecedor TEXT DEFAULT 'Geral'",
    "ALTER TABLE vendas ADD COLUMN codigo_venda TEXT",
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
      ("TOMATE 1ª", "VERDURAS", 10.0, 40.0, 70.0),
  ]
  for p, g, q, vc, vv in PRODUTOS_INICIAIS:
    cursor.execute(
        "INSERT INTO produtos (produto, grupo, quantidade, valor_compra,"
        " valor_venda) VALUES (?, ?, ?, ?, ?)",
        (p, g, q, vc, vv),
    )

cursor.execute("SELECT COUNT(*) FROM clientes")
if cursor.fetchone()[0] == 0:
  CLIENTES_INICIAIS = [
      (
          "Sebastião",
          "95451160000",
          "Rua Caipira, 174 Centro",
          "sebastiaoappsheet@gmail.com",
          "99985020000",
      ),
      ("Carlos Alberto", "", "", "midiapura07@gmail.com", ""),
      ("Valeilde Loja 01", "", "", "", ""),
  ]
  for cli, cpf, end, em, fn in CLIENTES_INICIAIS:
    cursor.execute(
        "INSERT INTO clientes (cliente, cpf, endereco, email, fone) VALUES (?,"
        " ?, ?, ?, ?)",
        (cli, cpf, end, em, fn),
    )

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

# Inicializar Carrinhos na sessão
if "carrinho_pedido" not in st.session_state:
  st.session_state.carrinho_pedido = []
if "carrinho_venda" not in st.session_state:
  st.session_state.carrinho_venda = []

# CARREGAR LISTAS ATUALIZADAS
clientes_df = pd.read_sql_query(
    "SELECT cliente FROM clientes ORDER BY cliente ASC", conn
)
fornecedores_df = pd.read_sql_query(
    "SELECT fornecedor FROM fornecedores ORDER BY fornecedor ASC", conn
)
grupos_df = pd.read_sql_query(
    "SELECT grupo FROM grupos ORDER BY grupo ASC", conn
)

list_clientes = (
    clientes_df["cliente"].tolist()
    if not clientes_df.empty
    else ["Cliente Geral"]
)
list_fornecedores = (
    fornecedores_df["fornecedor"].tolist()
    if not fornecedores_df.empty
    else ["Geral"]
)
list_grupos = (
    grupos_df["grupo"].tolist() if not grupos_df.empty else ["GERAL"]
)

# -----------------------------------------------------------------------------
# AUTENTICAÇÃO E PERFIS DE ACESSO
# -----------------------------------------------------------------------------
st.sidebar.title("🔑 Acesso ao Sistema")

if "perfil_ativo" not in st.session_state:
  st.session_state.perfil_ativo = "👤 Portal do Cliente"

opcoes_perfil = ["👤 Portal do Cliente", "🔒 Administração / Vendedor"]
index_atual = opcoes_perfil.index(st.session_state.perfil_ativo)

perfil_selecionado = st.sidebar.radio(
    "Selecione o Perfil:", opcoes_perfil, index=index_atual
)

cliente_autenticado = None
menu = None

if perfil_selecionado == "🔒 Administração / Vendedor":
  if st.session_state.get("admin_autenticado") != True:
    st.sidebar.markdown("---")
    st.sidebar.subheader("🔒 Área Restrita")
    senha_digitada = st.sidebar.text_input(
        "Digite a Senha do Admin:", type="password", key="pwd_admin"
    )

    if st.sidebar.button("Entrar como Admin"):
      if senha_digitada == SENHA_ADMIN:
        st.session_state.admin_autenticado = True
        st.session_state.perfil_ativo = "🔒 Administração / Vendedor"
        st.sidebar.success("Acesso liberado!")
        st.rerun()
      else:
        st.sidebar.error("Senha incorreta!")

    tipo_acesso = "👤 Portal do Cliente"
    menu = "📋 Pedidos / Orçamentos"
  else:
    tipo_acesso = "🔒 Administração / Vendedor"
    st.sidebar.markdown("---")
    st.sidebar.title("CRM Comércio 📦")
    menu = st.sidebar.radio(
        "Navegação",
        [
            "📊 Fechamento & Financeiro",
            "📋 Pedidos / Orçamentos",
            "🛒 Registrar Venda",
            "📥 Entrada de Estoque (Compras)",
            "📦 Estoque de Produtos",
            "👥 Cadastros (Clientes / Fornecedores / Grupos)",
        ],
    )

    if st.sidebar.button("🚪 Sair do Modo Admin"):
      st.session_state.admin_autenticado = False
      st.session_state.perfil_ativo = "👤 Portal do Cliente"
      st.rerun()

else:
  st.session_state.admin_autenticado = False
  st.session_state.perfil_ativo = "👤 Portal do Cliente"
  tipo_acesso = "👤 Portal do Cliente"

  st.sidebar.markdown("---")
  cliente_sel = st.sidebar.selectbox(
      "Identifique seu Nome/Empresa:", list_clientes, key="cli_login"
  )

  if st.session_state.get("cliente_logado") != cliente_sel:
    st.session_state.cliente_autenticado_status = False

  senha_esperada = SENHAS_CLIENTES.get(cliente_sel, SENHA_CLIENTE_PADRAO)

  if not st.session_state.get("cliente_autenticado_status", False):
    st.sidebar.subheader(f"🔒 Login — {cliente_sel}")
    pin_cliente = st.sidebar.text_input(
        "Digite sua Senha de Cliente:",
        type="password",
        key=f"pwd_cli_{cliente_sel}",
    )

    if st.sidebar.button("Acessar Meus Pedidos"):
      if pin_cliente == senha_esperada:
        st.session_state.cliente_autenticado_status = True
        st.session_state.cliente_logado = cliente_sel
        st.sidebar.success("Acesso confirmado!")
        st.rerun()
      else:
        st.sidebar.error("Senha incorreta!")
  else:
    cliente_autenticado = cliente_sel
    st.sidebar.success(f"Logado como: **{cliente_autenticado}**")
    if st.sidebar.button("🚪 Sair / Trocar Cliente"):
      st.session_state.cliente_autenticado_status = False
      st.session_state.cliente_logado = None
      st.rerun()

  menu = "📋 Pedidos / Orçamentos"

# -----------------------------------------------------------------------------
# IMPLEMENTAÇÃO DE TODAS AS TELAS
# -----------------------------------------------------------------------------

if tipo_acesso == "👤 Portal do Cliente" and not cliente_autenticado:
  st.title("🔒 Portal do Cliente")
  st.warning(
      "Por favor, selecione seu nome no menu à esquerda e insira sua senha para"
      " acessar seus pedidos."
  )

# --- 1. FECHAMENTO & FINANCEIRO ---
elif menu == "📊 Fechamento & Financeiro":
  st.title("📊 Painel Financeiro & Fechamento")

  df_vendas = pd.read_sql_query("SELECT * FROM vendas", conn)

  if not df_vendas.empty:
    total_faturado = df_vendas["valor_total"].sum()
    total_recebido = df_vendas["valor_recebido"].sum()
    total_fiado = df_vendas["restante"].sum()

    c1, c2, c3 = st.columns(3)
    c1.metric("Faturamento Total", f"R$ {total_faturado:,.2f}")
    c2.metric("Total Recebido em Caixa", f"R$ {total_recebido:,.2f}")
    c3.metric("Total a Receber (Fiado/Pendente)", f"R$ {total_fiado:,.2f}")

    st.markdown("---")
    st.subheader("📋 Resumo do Histórico de Vendas")
    cols_exib = [
        c
        for c in [
            "id",
            "codigo_venda",
            "data",
            "cliente",
            "produto",
            "fornecedor",
            "grupo",
            "quantidade",
            "valor_venda",
            "valor_total",
            "forma_pagamento",
            "restante",
        ]
        if c in df_vendas.columns
    ]
    st.dataframe(df_vendas[cols_exib], use_container_width=True)
  else:
    st.info("Nenhuma venda registrada até o momento.")

# --- 2. PEDIDOS / ORÇAMENTOS ---
elif menu == "📋 Pedidos / Orçamentos":
  if tipo_acesso == "👤 Portal do Cliente":
    st.title(f"🛍️ Portal do Cliente — Meus Pedidos ({cliente_autenticado})")
  else:
    st.title("📋 Gerenciamento de Pedidos e Orçamentos")

  tab_novo, tab_lista = st.tabs(
      ["➕ Criar Novo Pedido", "📑 Pedidos Registrados & Relatórios"]
  )
  produtos_df = pd.read_sql_query("SELECT * FROM produtos", conn)

  with tab_novo:
    if produtos_df.empty:
      st.warning("Nenhum produto disponível no momento.")
    else:
      col_head1, col_head2 = st.columns(2)
      with col_head1:
        if tipo_acesso == "👤 Portal do Cliente":
          st.text_input(
              "Cliente do Pedido", value=cliente_autenticado, disabled=True
          )
          ped_cliente = cliente_autenticado
        else:
          ped_cliente = st.selectbox(
              "Cliente do Pedido", list_clientes, key="ped_cli_multi"
          )

      with col_head2:
        if tipo_acesso == "👤 Portal do Cliente":
          st.text_input("Status Inicial", value="Pendente", disabled=True)
          ped_status = "Pendente"
        else:
          ped_status = st.selectbox(
              "Status Inicial",
              ["Pendente", "Em Andamento", "Cancelado"],
              key="ped_stat_multi",
          )

      st.markdown("---")
      st.write("#### 🛒 Adicionar Produtos ao Pedido")

      if tipo_acesso == "👤 Portal do Cliente":
        c_prod1, c_prod2, c_prod3 = st.columns([4, 2, 2])
        with c_prod1:
          item_produto = st.selectbox(
              "Selecione o Produto",
              produtos_df["produto"].tolist(),
              key="item_prod",
          )
          prod_info = produtos_df[
              produtos_df["produto"] == item_produto
          ].iloc[0]
          grupo_padrao = prod_info.get("grupo", "GERAL")
          item_fornecedor = "Geral"
          item_grupo = grupo_padrao

        with c_prod2:
          item_preco = float(prod_info["valor_venda"])
          st.number_input(
              "Preço Unit. Venda (R$)",
              value=item_preco,
              disabled=True,
              key="item_prec",
          )

        with c_prod3:
          item_qtd = st.number_input(
              "Quantidade", min_value=0.01, value=1.0, step=0.1, key="item_qtd"
          )
      else:
        c_prod1, c_prod2, c_prod3, c_prod4 = st.columns([3, 2, 2, 2])
        with c_prod1:
          item_produto = st.selectbox(
              "Selecione o Produto",
              produtos_df["produto"].tolist(),
              key="item_prod",
          )
          prod_info = produtos_df[
              produtos_df["produto"] == item_produto
          ].iloc[0]
          grupo_padrao = prod_info.get("grupo", "GERAL")

        with c_prod2:
          item_fornecedor = st.selectbox(
              "Fornecedor", list_fornecedores, key="item_forn"
          )

        with c_prod3:
          item_grupo = st.selectbox(
              "Grupo",
              list_grupos,
              index=(
                  list_grupos.index(grupo_padrao)
                  if grupo_padrao in list_grupos
                  else 0
              ),
              key="item_grup",
          )

        with c_prod4:
          item_preco = st.number_input(
              "Preço Unit. Venda (R$)",
              value=float(prod_info["valor_venda"]),
              min_value=0.0,
              key="item_prec",
          )

        c_qtd1, c_qtd2 = st.columns([2, 2])
        with c_qtd1:
          item_qtd = st.number_input(
              "Quantidade", min_value=0.01, value=1.0, step=0.1, key="item_qtd"
          )

      st.write("")
      if st.button("➕ Adicionar Produto à Lista"):
        total_item = item_qtd * item_preco
        st.session_state.carrinho_pedido.append({
            "produto": item_produto,
            "fornecedor": item_fornecedor,
            "grupo": item_grupo,
            "quantidade": item_qtd,
            "valor_unitario": item_preco,
            "valor_total": total_item,
        })
        st.success(f"'{item_produto}' adicionado!")

      st.markdown("---")
      st.write("### 📜 Lista de Itens no Pedido Atual")

      if len(st.session_state.carrinho_pedido) == 0:
        st.info("Sua lista está vazia. Adicione produtos acima.")
      else:
        df_cart = pd.DataFrame(st.session_state.carrinho_pedido)
        st.dataframe(
            df_cart[
                ["produto", "quantidade", "valor_unitario", "valor_total"]
            ],
            use_container_width=True,
        )

        total_geral_pedido = df_cart["valor_total"].sum()
        st.markdown(
            f"### 💰 **Valor Total do Pedido: R$ {total_geral_pedido:,.2f}**"
        )

        ped_obs = st.text_area("Observações Gerais do Pedido")

        col_b1, col_b2 = st.columns(2)
        with col_b1:
          if st.button("✅ Finalizar e Enviar Pedido"):
            data_hoje = datetime.now().strftime("%Y-%m-%d %H:%M")
            codigo_ped = f"PED-{datetime.now().strftime('%Y%m%d%H%M%S')}"

            for item in st.session_state.carrinho_pedido:
              cursor.execute(
                  """
                                INSERT INTO pedidos (codigo_pedido, cliente, produto, fornecedor, grupo, quantidade, valor_unitario, valor_total, status, observacoes, data)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                  (
                      codigo_ped,
                      ped_cliente,
                      item["produto"],
                      item["fornecedor"],
                      item["grupo"],
                      item["quantidade"],
                      item["valor_unitario"],
                      item["valor_total"],
                      ped_status,
                      ped_obs,
                      data_hoje,
                  ),
              )

            conn.commit()
            st.session_state.carrinho_pedido = []
            st.success(
                f"Pedido enviado com sucesso! (Código: {codigo_ped})"
            )
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
        filtro_cliente = st.selectbox(
            "Filtrar por Cliente",
            ["Todas as vendas"] + list_clientes,
            key="f_cli_p",
        )
        filtro_fornecedor = st.selectbox(
            "Filtrar por Fornecedor",
            ["Todos os fornecedores"] + list_fornecedores,
            key="f_forn_p",
        )
      with col_f2:
        filtro_grupo = st.selectbox(
            "Filtrar por Grupo", ["Todos os grupos"] + list_grupos, key="f_grp_p"
        )
        filtro_status = st.selectbox(
            "Filtrar por Status",
            [
                "Todos",
                "Pendente",
                "Em Andamento",
                "Concluído (Convertido)",
                "Cancelado",
            ],
            key="f_stat_p",
        )
      with col_f3:
        data_ini = st.date_input(
            "Data Inicial", value=date(2024, 1, 1), key="d_ini_p"
        )
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

    if (
        tipo_acesso != "👤 Portal do Cliente"
        and not pedidos_df.empty
        and "data" in pedidos_df.columns
    ):
      pedidos_df["data_dt"] = pd.to_datetime(
          pedidos_df["data"], errors="coerce"
      ).dt.date
      pedidos_df = pedidos_df[
          (pedidos_df["data_dt"] >= data_ini)
          & (pedidos_df["data_dt"] <= data_fim)
      ]
      pedidos_df = pedidos_df.drop(columns=["data_dt"])

    st.markdown("---")

    if pedidos_df.empty:
      st.warning("Nenhum pedido encontrado.")
    else:
      total_filtrado = pedidos_df["valor_total"].sum()
      st.write(
          f"**Itens Registrados:** {len(pedidos_df)} | **Soma dos Valores:** R$"
          f" {total_filtrado:,.2f}"
      )

      if (
          "valor_unitario" not in pedidos_df.columns
          or pedidos_df["valor_unitario"].isnull().all()
      ):
        pedidos_df["valor_unitario"] = (
            pedidos_df["valor_total"] / pedidos_df["quantidade"]
        )

      cols_exibicao = [
          "id",
          "codigo_pedido",
          "data",
          "cliente",
          "produto",
          "quantidade",
          "valor_unitario",
          "valor_total",
          "status",
      ]

      if tipo_acesso == "👤 Portal do Cliente":
        st.dataframe(pedidos_df[cols_exibicao], use_container_width=True)
      else:
        st.info(
            "💡 **Dica:** Clique duas vezes em qualquer valor para editar"
            " quantidade ou preço unitário diretamente na tabela.",
            icon="✏️",
        )
        df_editavel = st.data_editor(
            pedidos_df[cols_exibicao],
            key="editor_pedidos_direto",
            use_container_width=True,
            disabled=[
                "id",
                "codigo_pedido",
                "data",
                "cliente",
                "produto",
                "valor_total",
                "status",
            ],
            column_config={
                "quantidade": st.column_config.NumberColumn(
                    "Quantidade", min_value=0.01, step=0.1, format="%.2f"
                ),
                "valor_unitario": st.column_config.NumberColumn(
                    "Valor Unitário (R$)",
                    min_value=0.0,
                    step=0.5,
                    format="R$ %.2f",
                ),
                "valor_total": st.column_config.NumberColumn(
                    "Valor Total (R$)", format="R$ %.2f"
                ),
            },
        )

        if st.button(
            "💾 Salvar Alterações da Tabela",
            type="primary",
            key="btn_save_pedidos",
        ):
          for idx, row in df_editavel.iterrows():
            id_row = int(row["id"])
            q_nova = float(row["quantidade"])
            v_unit_novo = float(row["valor_unitario"])
            v_tot_novo = q_nova * v_unit_novo

            cursor.execute(
                """
                                UPDATE pedidos 
                                SET quantidade = ?, valor_unitario = ?, valor_total = ? 
                                WHERE id = ?
                            """,
                (q_nova, v_unit_novo, v_tot_novo, id_row),
            )

          conn.commit()
          st.success("✅ Alterações salvas com sucesso!")
          st.rerun()

        st.markdown("---")
        st.subheader("🔄 Transferir / Converter Pedido em Venda")

        codigos_pedidos_pendentes = (
            pedidos_df[pedidos_df["status"] != "Concluído (Convertido)"][
                "codigo_pedido"
            ]
            .dropna()
            .unique()
            .tolist()
        )

        if not codigos_pedidos_pendentes:
          st.success("Todos os pedidos atuais já foram convertidos em vendas!")
        else:
          col_conv1, col_conv2, col_conv3 = st.columns([3, 3, 2])

          with col_conv1:
            ped_sel_conv = st.selectbox(
                "Selecione o Pedido para Transferir:",
                codigos_pedidos_pendentes,
                key="ped_sel_conv",
            )

          itens_pedido_sel = pedidos_df[
              pedidos_df["codigo_pedido"] == ped_sel_conv
          ]
          total_ped_conv = itens_pedido_sel["valor_total"].sum()
          cliente_ped_conv = itens_pedido_sel.iloc[0]["cliente"]

          with col_conv2:
            forma_pagto_conv = st.selectbox(
                "Forma de Pagamento:",
                [
                    "Dinheiro",
                    "PIX",
                    "Cartão de Débito",
                    "Cartão de Crédito",
                    "A Prazo / Fiado",
                ],
                key="forma_pagto_conv",
            )

          with col_conv3:
            val_pago_conv = st.number_input(
                "Valor Recebido (R$):",
                min_value=0.0,
                value=(
                    float(total_ped_conv)
                    if forma_pagto_conv != "A Prazo / Fiado"
                    else 0.0
                ),
                key="val_pago_conv",
            )

          st.write(
              f"**Cliente:** `{cliente_ped_conv}` | **Total do Pedido:** R$"
              f" `{total_ped_conv:,.2f}`"
          )

          if st.button("🚀 Transferir para Vendas e Dar Baixa no Estoque"):
            cod_venda = f"VEN-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            data_venda = datetime.now().strftime("%Y-%m-%d %H:%M")

            troco_c = max(0.0, val_pago_conv - total_ped_conv)
            restante_c = max(0.0, total_ped_conv - val_pago_conv)

            for idx, r in itens_pedido_sel.iterrows():
              p_nome = r["produto"]
              p_qtd = float(r["quantidade"])
              p_v_unit = float(r["valor_unitario"])
              p_v_tot = float(r["valor_total"])
              p_forn = r.get("fornecedor", "Geral")
              p_grp = r.get("grupo", "Geral")

              cursor.execute(
                  """
                                INSERT INTO vendas (codigo_venda, cliente, produto, fornecedor, grupo, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, troco, restante, data)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                  (
                      cod_venda,
                      cliente_ped_conv,
                      p_nome,
                      p_forn,
                      p_grp,
                      p_qtd,
                      p_v_unit,
                      p_v_tot,
                      forma_pagto_conv,
                      val_pago_conv,
                      troco_c,
                      restante_c,
                      data_venda,
                  ),
              )

              cursor.execute(
                  """
                                UPDATE produtos 
                                SET quantidade = quantidade - ? 
                                WHERE produto = ?
                            """,
                  (p_qtd, p_nome),
              )

            cursor.execute(
                """
                            UPDATE pedidos 
                            SET status = 'Concluído (Convertido)' 
                            WHERE codigo_pedido = ?
                        """,
                (ped_sel_conv,),
            )

            conn.commit()
            st.success(
                f"Pedido `{ped_sel_conv}` transferido para Vendas com sucesso!"
                f" (Venda `{cod_venda}` registrada)"
            )
            st.rerun()

      st.markdown("---")
      st.subheader("📊 Agrupamento do Período / Seleção")

      df_agrupado = pedidos_df.groupby("produto", as_index=False).agg(
          {"quantidade": "sum", "valor_total": "sum"}
      )

      df_agrupado["valor_unitario_medio"] = (
          df_agrupado["valor_total"] / df_agrupado["quantidade"]
      )

      st.dataframe(
          df_agrupado[[
              "produto",
              "quantidade",
              "valor_unitario_medio",
              "valor_total",
          ]],
          column_config={
              "produto": "Produto",
              "quantidade": st.column_config.NumberColumn(
                  "Quantidade Total", format="%.2f"
              ),
              "valor_unitario_medio": st.column_config.NumberColumn(
                  "Valor Unitário Médio (R$)", format="R$ %.2f"
              ),
              "valor_total": st.column_config.NumberColumn(
                  "Valor Total (R$)", format="R$ %.2f"
              ),
          },
          hide_index=True,
      )

# --- 3. REGISTRAR VENDA ---
elif menu == "🛒 Registrar Venda":
  st.title("🛒 Registrar Venda Direta (PDV)")

  produtos_df = pd.read_sql_query("SELECT * FROM produtos", conn)

  if produtos_df.empty:
    st.warning("Nenhum produto cadastrado.")
  else:
    c_v1, c_v2 = st.columns(2)
    with c_v1:
      venda_cli = st.selectbox(
          "Selecione o Cliente:", list_clientes, key="venda_cli"
      )
    with c_v2:
      forma_pagto = st.selectbox(
          "Forma de Pagamento:",
          [
              "Dinheiro",
              "PIX",
              "Cartão de Débito",
              "Cartão de Crédito",
              "A Prazo / Fiado",
          ],
          key="forma_pagto",
      )

    st.markdown("---")
    st.write("#### ➕ Adicionar Item à Venda")
    c_p1, c_p2, c_p3 = st.columns([4, 2, 2])

    with c_p1:
      venda_prod = st.selectbox(
          "Produto", produtos_df["produto"].tolist(), key="v_prod"
      )
      prod_sel = produtos_df[produtos_df["produto"] == venda_prod].iloc[0]

    with c_p2:
      venda_preco = st.number_input(
          "Preço Venda (R$)",
          value=float(prod_sel["valor_venda"]),
          min_value=0.0,
          key="v_prec",
      )

    with c_p3:
      venda_qtd = st.number_input(
          "Quantidade", min_value=0.01, value=1.0, step=0.1, key="v_qtd"
      )

    if st.button("➕ Adicionar à Venda"):
      st.session_state.carrinho_venda.append({
          "produto": venda_prod,
          "fornecedor": "Geral",
          "grupo": prod_sel.get("grupo", "Geral"),
          "quantidade": venda_qtd,
          "valor_venda": venda_preco,
          "valor_total": venda_qtd * venda_preco,
      })
      st.success(f"'{venda_prod}' adicionado ao carrinho.")

    st.markdown("---")
    st.write("### 🛒 Carrinho da Venda")

    if not st.session_state.carrinho_venda:
      st.info("O carrinho está vazio.")
    else:
      df_cart_v = pd.DataFrame(st.session_state.carrinho_venda)
      st.dataframe(
          df_cart_v[["produto", "quantidade", "valor_venda", "valor_total"]],
          use_container_width=True,
      )

      total_venda = df_cart_v["valor_total"].sum()
      st.markdown(f"### 💰 Total a Pagar: R$ {total_venda:,.2f}")

      c_pay1, c_pay2 = st.columns(2)
      with c_pay1:
        val_recebido = st.number_input(
            "Valor Recebido (R$)",
            min_value=0.0,
            value=float(total_venda) if forma_pagto != "A Prazo / Fiado" else 0.0,
        )
      with c_pay2:
        troco = max(0.0, val_recebido - total_venda)
        restante = max(0.0, total_venda - val_recebido)
        st.write(
            f"**Troco:** R$ {troco:,.2f} | **Falta Pagar:** R$"
            f" {restante:,.2f}"
        )

      col_fv1, col_fv2 = st.columns(2)
      with col_fv1:
        if st.button("✅ Finalizar Venda"):
          cod_v = f"VEN-{datetime.now().strftime('%Y%m%d%H%M%S')}"
          data_v = datetime.now().strftime("%Y-%m-%d %H:%M")

          for item in st.session_state.carrinho_venda:
            cursor.execute(
                """
                            INSERT INTO vendas (codigo_venda, cliente, produto, fornecedor, grupo, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, troco, restante, data)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                (
                    cod_v,
                    venda_cli,
                    item["produto"],
                    item["fornecedor"],
                    item["grupo"],
                    item["quantidade"],
                    item["valor_venda"],
                    item["valor_total"],
                    forma_pagto,
                    val_recebido,
                    troco,
                    restante,
                    data_v,
                ),
            )

            cursor.execute(
                """
                            UPDATE produtos 
                            SET quantidade = quantidade - ? 
                            WHERE produto = ?
                        """,
                (item["quantidade"], item["produto"]),
            )

          conn.commit()
          st.session_state.carrinho_venda = []
          st.success(f"Venda `{cod_v}` concluída com sucesso!")
          st.rerun()

      with col_fv2:
        if st.button("🗑️ Esvaziar Carrinho"):
          st.session_state.carrinho_venda = []
          st.rerun()

# --- 4. ENTRADA DE ESTOQUE (COMPRAS) ---
elif menu == "📥 Entrada de Estoque (Compras)":
  st.title("📥 Lançamento de Compras (Entrada de Estoque)")

  produtos_df = pd.read_sql_query("SELECT * FROM produtos", conn)

  col_c1, col_c2 = st.columns(2)
  with col_c1:
    compra_prod = st.selectbox(
        "Selecione o Produto",
        produtos_df["produto"].tolist() if not produtos_df.empty else ["Nenhum"],
    )
    compra_forn = st.selectbox("Fornecedor", list_fornecedores)
  with col_c2:
    compra_grupo = st.selectbox("Grupo", list_grupos)
    compra_qtd = st.number_input(
        "Quantidade Comprada", min_value=0.01, value=10.0, step=1.0
    )

  col_p1, col_p2 = st.columns(2)
  with col_p1:
    compra_val_compra = st.number_input(
        "Valor Unitário de Custo (R$)", min_value=0.0, value=10.0
    )
  with col_p2:
    compra_val_venda = st.number_input(
        "Novo Valor Unitário de Venda (R$)", min_value=0.0, value=15.0
    )

  compra_total = compra_qtd * compra_val_compra
  st.write(f"### 💵 **Custo Total do Lote: R$ {compra_total:,.2f}**")

  if st.button("📥 Dar Entrada no Estoque"):
    data_compra = datetime.now().strftime("%Y-%m-%d %H:%M")

    cursor.execute(
        """
            INSERT INTO compras (produto, fornecedor, grupo, quantidade, valor_compra, valor_venda, valor_total, data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            compra_prod,
            compra_forn,
            compra_grupo,
            compra_qtd,
            compra_val_compra,
            compra_val_venda,
            compra_total,
            data_compra,
        ),
    )

    cursor.execute(
        """
            UPDATE produtos 
            SET quantidade = quantidade + ?, valor_compra = ?, valor_venda = ?
            WHERE produto = ?
        """,
        (compra_qtd, compra_val_compra, compra_val_venda, compra_prod),
    )

    conn.commit()
    st.success(f"Entrada de {compra_qtd} unidades do produto '{compra_prod}' salva!")
    st.rerun()

  st.markdown("---")
  st.subheader("📑 Histórico de Entradas")
  df_compras = pd.read_sql_query(
      "SELECT * FROM compras ORDER BY id DESC", conn
  )
  st.dataframe(df_compras, use_container_width=True)

# --- 5. ESTOQUE DE PRODUTOS ---
elif menu == "📦 Estoque de Produtos":
  st.title("📦 Gestão de Estoque e Produtos")

  tab_p1, tab_p2 = st.tabs(["📋 Lista de Produtos", "➕ Cadastrar Novo Produto"])

  with tab_p1:
    df_prods = pd.read_sql_query("SELECT * FROM produtos", conn)
    st.info("✏️ Você pode alterar os valores na tabela e salvar.")
    df_p_edit = st.data_editor(df_prods, use_container_width=True, disabled=["id"])

    if st.button("💾 Salvar Alterações nos Produtos"):
      for idx, row in df_p_edit.iterrows():
        cursor.execute(
            """
                    UPDATE produtos 
                    SET produto = ?, grupo = ?, quantidade = ?, valor_compra = ?, valor_venda = ?
                    WHERE id = ?
                """,
            (
                row["produto"],
                row["grupo"],
                float(row["quantidade"]),
                float(row["valor_compra"]),
                float(row["valor_venda"]),
                int(row["id"]),
            ),
        )
      conn.commit()
      st.success("Estoque atualizado!")
      st.rerun()

  with tab_p2:
    st.subheader("➕ Novo Produto")
    np_nome = st.text_input("Nome do Produto")
    np_grupo = st.selectbox("Grupo", list_grupos, key="np_g")
    np_qtd = st.number_input("Quantidade Inicial", min_value=0.0, value=0.0)
    np_vc = st.number_input("Valor de Custo (R$)", min_value=0.0, value=0.0)
    np_vv = st.number_input("Valor de Venda (R$)", min_value=0.0, value=0.0)

    if st.button("Cadastrar Produto"):
      if np_nome:
        try:
          cursor.execute(
              """
                        INSERT INTO produtos (produto, grupo, quantidade, valor_compra, valor_venda)
                        VALUES (?, ?, ?, ?, ?)
                    """,
              (np_nome, np_grupo, np_qtd, np_vc, np_vv),
          )
          conn.commit()
          st.success(f"Produto '{np_nome}' cadastrado!")
          st.rerun()
        except Exception as e:
          st.error(f"Erro ao cadastrar: {e}")

# --- 6. CADASTROS (CLIENTES / FORNECEDORES / GRUPOS) ---
elif menu == "👥 Cadastros (Clientes / Fornecedores / Grupos)":
  st.title("👥 Cadastros de Apoio")

  t_cli, t_forn, t_grp = st.tabs(
      ["👥 Clientes", "🚚 Fornecedores", "🏷️ Grupos de Produtos"]
  )

  with t_cli:
    st.subheader("Cadastro de Clientes")
    df_cli = pd.read_sql_query("SELECT * FROM clientes", conn)
    st.dataframe(df_cli, use_container_width=True)

    with st.form("f_add_cli"):
      nc_nome = st.text_input("Nome do Cliente/Empresa")
      nc_cpf = st.text_input("CPF/CNPJ")
      nc_end = st.text_input("Endereço")
      nc_email = st.text_input("E-mail")
      nc_fone = st.text_input("Telefone")
      if st.form_submit_button("Adicionar Cliente"):
        if nc_nome:
          try:
            cursor.execute(
                """
                            INSERT INTO clientes (cliente, cpf, endereco, email, fone)
                            VALUES (?, ?, ?, ?, ?)
                        """,
                (nc_nome, nc_cpf, nc_end, nc_email, nc_fone),
            )
            conn.commit()
            st.success("Cliente adicionado!")
            st.rerun()
          except Exception as e:
            st.error(f"Erro: {e}")

  with t_forn:
    st.subheader("Cadastro de Fornecedores")
    df_forn = pd.read_sql_query("SELECT * FROM fornecedores", conn)
    st.dataframe(df_forn, use_container_width=True)

    nf_nome = st.text_input("Nome do Fornecedor")
    if st.button("Adicionar Fornecedor"):
      if nf_nome:
        try:
          cursor.execute(
              "INSERT INTO fornecedores (fornecedor) VALUES (?)", (nf_nome,)
          )
          conn.commit()
          st.success("Fornecedor cadastrado!")
          st.rerun()
        except Exception as e:
          st.error(f"Erro: {e}")

  with t_grp:
    st.subheader("Cadastro de Grupos/Categorias")
    df_grp = pd.read_sql_query("SELECT * FROM grupos", conn)
    st.dataframe(df_grp, use_container_width=True)

    ng_nome = st.text_input("Nome do Grupo")
    if st.button("Adicionar Grupo"):
      if ng_nome:
        try:
          cursor.execute("INSERT INTO grupos (grupo) VALUES (?)", (ng_nome,))
          conn.commit()
          st.success("Grupo cadastrado!")
          st.rerun()
        except Exception as e:
          st.error(f"Erro: {e}")
