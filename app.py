import io
import sqlite3
from datetime import date, datetime
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
import streamlit as st

# -----------------------------------------------------------------------------
# 1. CONFIGURAÇÃO DA PÁGINA
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="CRM Comércio",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------------------------------------------------------
# 2. BANCO DE DADOS E FUNÇÕES DE SUPORTE
# -----------------------------------------------------------------------------
DB_FILE = "crm_comercio.db"


@st.cache_resource
def get_db_connection():
  conn = sqlite3.connect(DB_FILE, check_same_thread=False)
  conn.row_factory = sqlite3.Row
  return conn


def init_db():
  conn = get_db_connection()
  cursor = conn.cursor()

  cursor.execute("""
    CREATE TABLE IF NOT EXISTS clientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT UNIQUE NOT NULL,
        telefone TEXT,
        email TEXT
    )
    """)

  cursor.execute("""
    CREATE TABLE IF NOT EXISTS fornecedores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT UNIQUE NOT NULL,
        contato TEXT
    )
    """)

  cursor.execute("""
    CREATE TABLE IF NOT EXISTS grupos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT UNIQUE NOT NULL
    )
    """)

  cursor.execute("""
    CREATE TABLE IF NOT EXISTS produtos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        produto TEXT UNIQUE NOT NULL,
        fornecedor TEXT,
        grupo TEXT,
        quantidade REAL DEFAULT 0,
        preco_custo REAL DEFAULT 0,
        preco_venda REAL DEFAULT 0
    )
    """)

  cursor.execute("""
    CREATE TABLE IF NOT EXISTS pedidos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo_pedido TEXT,
        cliente TEXT,
        produto TEXT,
        fornecedor TEXT,
        grupo TEXT,
        quantidade REAL,
        valor_unitario REAL,
        valor_total REAL,
        status TEXT DEFAULT 'Pendente',
        data TEXT
    )
    """)

  cursor.execute("""
    CREATE TABLE IF NOT EXISTS vendas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo_venda TEXT,
        cliente TEXT,
        produto TEXT,
        fornecedor TEXT,
        grupo TEXT,
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

  conn.commit()


def carregar_dados_iniciais():
  conn = get_db_connection()
  c = conn.cursor()
  clientes_padrao = [
      ("Carlos Alberto", "1234"),
      ("Sebastião", "123456"),
      ("Valeilde Loja 01", "12345"),
      ("Neurialdo", "456892"),
  ]
  for nome, senha in clientes_padrao:
    try:
      c.execute(
          "INSERT OR IGNORE INTO clientes (nome, telefone) VALUES (?, ?)",
          (nome, senha),
      )
    except Exception:
      pass
  conn.commit()


# Executa com segurança
init_db()
carregar_dados_iniciais()


def safe_query_list(query, params=()):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        # Garante que estamos pegando a primeira coluna de cada linha
        lista = [r[0] for r in rows if r[0] is not None]
        return lista
    except Exception as e:
        # Se der erro, retorna vazio para não quebrar a tela
        return []


def get_produto_info(nome_produto):
  if not nome_produto:
    return 0.0, "", "", 0.0
  try:
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT preco_venda, fornecedor, grupo, quantidade FROM produtos WHERE"
        " produto = ?",
        (nome_produto,),
    ).fetchone()
    if row:
      return (
          row["preco_venda"] or 0.0,
          row["fornecedor"] or "",
          row["grupo"] or "",
          row["quantidade"] or 0.0,
      )
  except Exception:
    pass
  return 0.0, "", "", 0.0


# -----------------------------------------------------------------------------
# 3. FUNÇÃO PARA GERAR PDF
# -----------------------------------------------------------------------------
def gerar_pdf_relatorio(df, titulo="Relatório Geral"):
  buffer = io.BytesIO()
  doc = SimpleDocTemplate(
      buffer, pagesize=A4, rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20
  )
  elements = []

  styles = getSampleStyleSheet()
  title_style = ParagraphStyle(
      "TitleStyle",
      parent=styles["Heading1"],
      fontName="Helvetica-Bold",
      fontSize=18,
      leading=22,
      textColor=colors.HexColor("#1E293B"),
      spaceAfter=10,
  )

  header_style = ParagraphStyle(
      "HeaderStyle",
      fontName="Helvetica-Bold",
      fontSize=8,
      leading=10,
      textColor=colors.white,
      alignment=1,
  )

  cell_style = ParagraphStyle(
      "CellStyle",
      fontName="Helvetica",
      fontSize=8,
      leading=10,
      textColor=colors.HexColor("#334155"),
  )

  elements.append(Paragraph(f"<b>CRM Comércio</b> - {titulo}", title_style))
  elements.append(
      Paragraph(
          f"<font size=9 color='#64748B'>Gerado em:"
          f" {datetime.now().strftime('%d/%m/%Y %H:%M')}</font>",
          styles["Normal"],
      )
  )
  elements.append(Spacer(1, 15))

  if not df.empty:
    cols_ignore = ["id"]
    cols_to_use = [c for c in df.columns if c.lower() not in cols_ignore]

    data_table = []
    header_row = [
        Paragraph(f"<b>{col.upper()}</b>", header_style) for col in cols_to_use
    ]
    data_table.append(header_row)

    for _, row in df.iterrows():
      formatted_row = []
      for col in cols_to_use:
        val = row[col]
        if isinstance(val, (int, float)):
          val_str = f"{val:,.2f}"
        else:
          val_str = str(val) if pd.notnull(val) else ""
        formatted_row.append(Paragraph(val_str, cell_style))
      data_table.append(formatted_row)

    col_widths = [550 / len(cols_to_use)] * len(cols_to_use)
    t = Table(data_table, colWidths=col_widths, repeatRows=1)
    t.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            (
                "ROWBACKGROUNDS",
                (0, 1),
                (-1, -1),
                [colors.white, colors.HexColor("#F8FAFC")],
            ),
        ])
    )
    elements.append(t)
  else:
    elements.append(Paragraph("Nenhum dado encontrado.", styles["Normal"]))

  doc.build(elements)
  buffer.seek(0)
  return buffer.getvalue()


# -----------------------------------------------------------------------------
# 4. BARRA LATERAL (NAVEGAÇÃO E FILTROS DE PERFIL)
# -----------------------------------------------------------------------------
st.sidebar.title("🔑 Acesso ao Sistema")
tipo_acesso = st.sidebar.radio(
    "Selecione o Perfil:",
    ["👤 Portal do Cliente", "🔒 Administração / Vendedor"],
)

list_clientes = safe_query_list("SELECT nome FROM clientes ORDER BY nome")
list_fornecedores = safe_query_list(
    "SELECT nome FROM fornecedores ORDER BY nome"
)
list_grupos = safe_query_list("SELECT nome FROM grupos ORDER BY nome")
list_produtos = safe_query_list("SELECT produto FROM produtos ORDER BY produto")

cliente_autenticado = None
if tipo_acesso == "👤 Portal do Cliente":
  if list_clientes:
    cliente_autenticado = st.sidebar.selectbox(
        "Selecione seu Nome/Empresa:", list_clientes
    )
  else:
    st.sidebar.warning("Nenhum cliente cadastrado no sistema.")

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


# -----------------------------------------------------------------------------
# 5. FECHAMENTO & FINANCEIRO
# -----------------------------------------------------------------------------
if menu == "📊 Fechamento & Financeiro":
  st.header("📊 Fechamento Financeiro & Relatórios")

  conn = get_db_connection()
  df_vendas_all = pd.read_sql_query("SELECT * FROM vendas", conn)

  col_m1, col_m2, col_m3, col_m4 = st.columns(4)
  val_tot = (
      df_vendas_all["valor_total"].sum() if not df_vendas_all.empty else 0.0
  )
  val_rec = (
      df_vendas_all["valor_recebido"].sum() if not df_vendas_all.empty else 0.0
  )
  val_pend = df_vendas_all["restante"].sum() if not df_vendas_all.empty else 0.0

  col_m1.metric("Faturamento Total", f"R$ {val_tot:,.2f}")
  col_m2.metric("Total Recebido", f"R$ {val_rec:,.2f}")
  col_m3.metric("A Receber (Fiado)", f"R$ {val_pend:,.2f}")
  col_m4.metric(
      "Total Vendas",
      len(df_vendas_all["codigo_venda"].unique())
      if not df_vendas_all.empty
      else 0,
  )

  st.markdown("---")
  if not df_vendas_all.empty:
    st.subheader("📋 Histórico Geral de Vendas")
    st.dataframe(df_vendas_all, use_container_width=True)

  st.markdown("---")
  st.subheader("📄 Relatório Financeiro em PDF")
  pdf_fin = gerar_pdf_relatorio(df_vendas_all, titulo="Fechamento Financeiro")
  st.download_button(
      label="📥 Baixar Relatório Financeiro (PDF)",
      data=pdf_fin,
      file_name=f"Relatorio_Financeiro_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
      mime="application/pdf",
      type="primary",
  )


# -----------------------------------------------------------------------------
# 6. PEDIDOS / ORÇAMENTOS
# -----------------------------------------------------------------------------
elif menu == "📋 Pedidos / Orçamentos":
  st.header("📋 Gestão de Pedidos e Orçamentos")

  tab_novo, tab_lista = st.tabs(
      ["➕ Criar Novo Pedido", "📑 Pedidos Registrados & Relatórios"]
  )

  with tab_novo:
    st.subheader("Criar Novo Pedido")

    if not list_clientes and tipo_acesso != "👤 Portal do Cliente":
      st.warning(
          "⚠️ Nenhum cliente cadastrado! Acesse a aba '👥 Cadastros' para"
          " cadastrar o primeiro cliente."
      )
    else:
      with st.form("form_novo_pedido"):
        col_p1, col_p2 = st.columns(2)
        with col_p1:
          if tipo_acesso == "👤 Portal do Cliente":
            if cliente_autenticado:
              cli_pedido = cliente_autenticado
              st.info(f"Cliente: **{cli_pedido}**")
            else:
              cli_pedido = None
              st.error("Nenhum cliente selecionado no portal.")
          else:
            cli_pedido = st.selectbox("Cliente:", list_clientes)

          prod_pedido = st.selectbox("Produto:", list_produtos)

        with col_p2:
          qtd_pedido = st.number_input(
              "Quantidade:", min_value=0.01, value=1.0, step=0.5
          )
          v_unit_padrao, forn_padrao, grp_padrao, _ = get_produto_info(
              prod_pedido
          )

          val_unit = st.number_input(
              "Valor Unitário (R$):",
              min_value=0.0,
              value=float(v_unit_padrao),
              step=0.5,
          )

        btn_add_pedido = st.form_submit_button("➕ Gravar Pedido")

        if btn_add_pedido:
          if not cli_pedido:
            st.error("Selecione ou cadastre um cliente primeiro.")
          elif not prod_pedido:
            st.error("Selecione um produto.")
          else:
            cod_p = f"PED-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            data_p = datetime.now().strftime("%Y-%m-%d %H:%M")
            v_tot = qtd_pedido * val_unit

            conn = get_db_connection()
            c = conn.cursor()
            c.execute(
                """
                  INSERT INTO pedidos (codigo_pedido, cliente, produto, fornecedor, grupo, quantidade, valor_unitario, valor_total, status, data)
                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pendente', ?)
              """,
                (
                    cod_p,
                    cli_pedido,
                    prod_pedido,
                    forn_padrao,
                    grp_padrao,
                    qtd_pedido,
                    val_unit,
                    v_tot,
                    data_p,
                ),
            )
            conn.commit()
            st.success(f"Pedido `{cod_p}` registrado com sucesso!")
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

    conn = get_db_connection()
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
      st.warning(
          "Nenhum pedido encontrado para o filtro selecionado no momento."
      )
    else:
      total_filtrado = pedidos_df["valor_total"].sum()
      st.write(
          f"**Itens Registrados:** {len(pedidos_df)} | **Soma dos Valores:** R$"
          f" {total_filtrado:,.2f}"
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
        )

        if st.button(
            "💾 Salvar Alterações da Tabela",
            type="primary",
            key="btn_save_pedidos",
        ):
          conn = get_db_connection()
          c = conn.cursor()
          for idx, row in df_editavel.iterrows():
            id_row = int(row["id"])
            q_nova = float(row["quantidade"])
            v_unit_novo = float(row["valor_unitario"])
            v_tot_novo = q_nova * v_unit_novo
            c.execute(
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


# -----------------------------------------------------------------------------
# 7. REGISTRAR VENDA DIRETA
# -----------------------------------------------------------------------------
elif menu == "🛒 Registrar Venda":
  st.header("🛒 Registrar Venda Direta (Balcão)")
  if not list_clientes:
    st.warning("⚠️ Nenhum cliente cadastrado.")
  elif not list_produtos:
    st.warning("⚠️ Nenhum produto cadastrado.")
  else:
    with st.form("form_venda_direta"):
      col_v1, col_v2 = st.columns(2)
      with col_v1:
        cli_venda = st.selectbox("Cliente:", list_clientes)
        prod_venda = st.selectbox("Produto:", list_produtos)
        qtd_venda = st.number_input(
            "Quantidade:", min_value=0.01, value=1.0, step=0.5
        )
      with col_v2:
        v_unit_p, forn_p, grp_p, estq_p = get_produto_info(prod_venda)
        st.caption(f"Estoque disponível: **{estq_p}**")
        val_venda_unit = st.number_input(
            "Preço de Venda (R$):",
            min_value=0.0,
            value=float(v_unit_p),
            step=0.5,
        )
        forma_pagto = st.selectbox(
            "Forma de Pagamento:",
            [
                "Dinheiro",
                "PIX",
                "Cartão de Débito",
                "Cartão de Crédito",
                "A Prazo / Fiado",
            ],
        )

      val_tot_venda = qtd_venda * val_venda_unit
      val_recebido = st.number_input(
          "Valor Recebido (R$):",
          min_value=0.0,
          value=(
              float(val_tot_venda) if forma_pagto != "A Prazo / Fiado" else 0.0
          ),
      )

      if st.form_submit_button("🛒 Concluir Venda"):
        if qtd_venda > estq_p:
          st.error(
              f"Estoque insuficiente! Disponível: {estq_p}, Tentativa:"
              f" {qtd_venda}."
          )
        else:
          cod_v = f"VEN-{datetime.now().strftime('%Y%m%d%H%M%S')}"
          data_v = datetime.now().strftime("%Y-%m-%d %H:%M")
          troco = max(0.0, val_recebido - val_tot_venda)
          restante = max(0.0, val_tot_venda - val_recebido)

          conn = get_db_connection()
          c = conn.cursor()
          c.execute(
              """
              INSERT INTO vendas (codigo_venda, cliente, produto, fornecedor, grupo, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, troco, restante, data)
              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
          """,
              (
                  cod_v,
                  cli_venda,
                  prod_venda,
                  forn_p,
                  grp_p,
                  qtd_venda,
                  val_venda_unit,
                  val_tot_venda,
                  forma_pagto,
                  val_recebido,
                  troco,
                  restante,
                  data_v,
              ),
          )
          c.execute(
              "UPDATE produtos SET quantidade = quantidade - ? WHERE produto ="
              " ?",
              (qtd_venda, prod_venda),
          )
          conn.commit()
          st.success(f"Venda `{cod_v}` concluída com sucesso!")
          st.rerun()


# -----------------------------------------------------------------------------
# 8. ENTRADA DE ESTOQUE
# -----------------------------------------------------------------------------
elif menu == "📥 Entrada de Estoque (Compras)":
  st.header("📥 Entrada de Estoque")
  if not list_produtos:
    st.warning("⚠️ Cadastre produtos primeiro.")
  else:
    with st.form("form_entrada_estoque"):
      prod_ent = st.selectbox("Produto:", list_produtos)
      qtd_ent = st.number_input(
          "Quantidade Comprada:", min_value=0.01, value=1.0, step=1.0
      )
      preco_custo_ent = st.number_input(
          "Preço de Custo Unitário (R$):", min_value=0.0, value=0.0, step=0.5
      )

      if st.form_submit_button("📥 Registrar Entrada"):
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            """
            UPDATE produtos 
            SET quantidade = quantidade + ?, preco_custo = ? 
            WHERE produto = ?
        """,
            (qtd_ent, preco_custo_ent, prod_ent),
        )
        conn.commit()
        st.success("Entrada registrada com sucesso!")
        st.rerun()


# -----------------------------------------------------------------------------
# 9. ESTOQUE DE PRODUTOS
# -----------------------------------------------------------------------------
elif menu == "📦 Estoque de Produtos":
  st.header("📦 Estoque de Produtos")
  tab_prod_lista, tab_prod_novo = st.tabs(
      ["📦 Produtos em Estoque", "➕ Novo Produto"]
  )
  with tab_prod_novo:
    with st.form("form_novo_prod"):
      p_nome = st.text_input("Nome do Produto:")
      p_forn = st.selectbox("Fornecedor:", [""] + list_fornecedores)
      p_cost = st.number_input(
          "Preço Custo (R$):", min_value=0.0, value=0.0, step=0.5
      )
      p_qtd = st.number_input(
          "Quantidade Inicial:", min_value=0.0, value=0.0, step=1.0
      )
      p_grp = st.selectbox("Grupo:", [""] + list_grupos)
      p_venda = st.number_input(
          "Preço Venda (R$):", min_value=0.0, value=0.0, step=0.5
      )

      if st.form_submit_button("💾 Cadastrar Produto"):
        if p_nome:
          try:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute(
                """
                INSERT INTO produtos (produto, fornecedor, grupo, quantidade, preco_custo, preco_venda)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (p_nome, p_forn, p_grp, p_qtd, p_cost, p_venda),
            )
            conn.commit()
            st.success("Produto cadastrado com sucesso!")
            st.rerun()
          except sqlite3.IntegrityError:
            st.error("Produto já cadastrado.")

  with tab_prod_lista:
    conn = get_db_connection()
    df_prods = pd.read_sql_query("SELECT * FROM produtos", conn)
    st.dataframe(df_prods, use_container_width=True)


# -----------------------------------------------------------------------------
# 10. CADASTROS
# -----------------------------------------------------------------------------
elif menu == "👥 Cadastros (Clientes / Fornecedores / Grupos)":
  st.header("👥 Gestão de Cadastros Base")
  tab_c, tab_f, tab_g = st.tabs(
      ["👤 Clientes", "🏭 Fornecedores", "🏷️ Grupos"]
  )

  with tab_c:
    st.subheader("Novo Cliente")
    with st.form("form_cli"):
      c_nome = st.text_input("Nome / Razão Social:")
      c_tel = st.text_input("Telefone / WhatsApp:")
      c_mail = st.text_input("E-mail:")
      if st.form_submit_button("Salvar Cliente"):
        if c_nome:
          try:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute(
                "INSERT INTO clientes (nome, telefone, email) VALUES (?, ?, ?)",
                (c_nome, c_tel, c_mail),
            )
            conn.commit()
            st.success("Cliente salvo!")
            st.rerun()
          except sqlite3.IntegrityError:
            st.error("Cliente já existe.")
    conn = get_db_connection()
    st.dataframe(
        pd.read_sql_query("SELECT * FROM clientes", conn),
        use_container_width=True,
    )

  with tab_f:
    st.subheader("Novo Fornecedor")
    with st.form("form_forn"):
      f_nome = st.text_input("Nome do Fornecedor:")
      f_cont = st.text_input("Contato / Obs:")
      if st.form_submit_button("Salvar Fornecedor"):
        if f_nome:
          try:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute(
                "INSERT INTO fornecedores (nome, contato) VALUES (?, ?)",
                (f_nome, f_cont),
            )
            conn.commit()
            st.success("Fornecedor salvo!")
            st.rerun()
          except sqlite3.IntegrityError:
            st.error("Fornecedor já existe.")
    conn = get_db_connection()
    st.dataframe(
        pd.read_sql_query("SELECT * FROM fornecedores", conn),
        use_container_width=True,
    )

  with tab_g:
    st.subheader("Novo Grupo")
    with st.form("form_grp"):
      g_nome = st.text_input("Nome do Grupo de Produtos:")
      if st.form_submit_button("Salvar Grupo"):
        if g_nome:
          try:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("INSERT INTO grupos (nome) VALUES (?)", (g_nome,))
            conn.commit()
            st.success("Grupo salvo!")
            st.rerun()
          except sqlite3.IntegrityError:
            st.error("Grupo já existe.")
    conn = get_db_connection()
    st.dataframe(
        pd.read_sql_query("SELECT * FROM grupos", conn), use_container_width=True
    )
