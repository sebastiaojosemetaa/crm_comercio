from datetime import date, datetime, timedelta
import io
import sqlite3
import pandas as pd
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# Fuso horário do Brasil (UTC-3) para padronizar as datas em todo o app
fuso_brasil = timedelta(hours=3)
data_hoje_brasil = (datetime.now() - fuso_brasil).date()

# 1. CONFIGURAÇÃO E CONEXÃO COM O BANCO DE DADOS
st.set_page_config(page_title="CRM Comércio - Rey da Cebola", layout="wide")


# Funções Auxiliares de Banco de Dados
def carregar_dados(query):
  try:
    conn = sqlite3.connect("vendas.db")
    df = pd.read_sql(query, conn)
    conn.close()
    return df
  except:
    return pd.DataFrame()


def carregar_coluna(tabela, coluna):
  try:
    conn = sqlite3.connect("vendas.db")
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT DISTINCT {coluna} FROM {tabela} WHERE {coluna} IS NOT NULL"
    )
    res = [row[0] for row in cursor.fetchall()]
    conn.close()
    return res
  except:
    return []


def baixar_debito_cliente(cliente, valor, forma_pagamento):
  try:
    conn = sqlite3.connect("vendas.db")
    cursor = conn.cursor()
    # Insira aqui a lógica de baixa de débito se houver tabela específica, ex:
    # cursor.execute("INSERT INTO historico_baixas ...", (...))
    conn.commit()
    conn.close()
  except Exception as e:
    st.error(f"Erro ao baixar débito: {e}")


# Função Principal do Módulo de Vendas / Pedidos
def renderizar_modulo_vendas(menu_admin="principal", is_modo_pedido=False):
  conn = sqlite3.connect("vendas.db")

  st.divider()
  st.subheader("🛒 Itens já lançados neste Pedido (Hoje)")

  try:
    conn_direto = sqlite3.connect("vendas.db")
    df_parcial = pd.read_sql(
        "SELECT id, cliente, produto, quantidade, valor_venda as valor_compra,"
        " valor_total, tipo, status FROM vendas WHERE status IS NULL OR status"
        " != 'Finalizado' ORDER BY id DESC LIMIT 20",
        conn_direto,
    )
    conn_direto.close()
  except Exception as e:
    df_parcial = pd.DataFrame()

  if not df_parcial.empty:
    df_parcial.dropna(axis=1, how="all", inplace=True)
    if "excluir" in df_parcial.columns:
      df_parcial = df_parcial.rename(columns={"excluir": "Excluir"})
    if "Excluir" not in df_parcial.columns:
      df_parcial.insert(0, "Excluir", False)
    else:
      df_parcial["Excluir"] = False

    cols_config_parcial = {
        "Excluir": st.column_config.CheckboxColumn("Excluir", default=False),
        "quantidade": st.column_config.NumberColumn(
            "Qtd", min_value=0.0, format="%.2f"
        ),
        "valor_compra": st.column_config.NumberColumn(
            "Vlr Unit", format="R$ %.2f"
        ),
        "valor_total": st.column_config.NumberColumn(
            "Vlr Total", format="R$ %.2f"
        ),
    }

    edit_parcial = st.data_editor(
        df_parcial,
        column_config=cols_config_parcial,
        disabled=[
            c
            for c in df_parcial.columns
            if c != "Excluir" and c != "quantidade" and c != "valor_compra"
        ],
        key=f"editor_parcial_{menu_admin}",
        use_container_width=True,
    )

    total_parcial = (
        edit_parcial["valor_total"].sum()
        if "valor_total" in edit_parcial.columns
        else 0.0
    )
    st.markdown(f"### **Valor Total Acumulado: R$ {total_parcial:.2f}**")

    col_fin, col_del = st.columns([2, 1])

    with col_fin:
      if st.button(
          "Finalizar Pedido / Venda",
          type="primary",
          key="btn_finalizar_pedido_unico",
      ):
        try:
          con_local = sqlite3.connect("vendas.db")
          cur = con_local.cursor()
          for id_item in edit_parcial["id"].tolist():
            cur.execute(
                "UPDATE vendas SET status = 'Finalizado', tipo = 'VENDA' WHERE"
                " id = ?",
                (int(id_item),),
            )
          con_local.commit()
          con_local.close()
          st.success("Pedido finalizado com sucesso!")
          st.balloons()
          st.rerun()
        except Exception as e:
          st.error(f"Erro ao finalizar: {e}")

    with col_del:
      if st.button("Excluir Selecionados", key="btn_excluir_parcial_sel"):
        try:
          ids_a_excluir = []
          if "Excluir" in edit_parcial.columns:
            ids_a_excluir = (
                edit_parcial[edit_parcial["Excluir"] == True]["id"]
                .dropna()
                .tolist()
            )
          if ids_a_excluir:
            con_local = sqlite3.connect("vendas.db")
            cur = con_local.cursor()
            for item_id in ids_a_excluir:
              cur.execute("DELETE FROM vendas WHERE id = ?", (int(item_id),))
            con_local.commit()
            con_local.close()
            st.success(f"{len(ids_a_excluir)} item(ns) excluído(s) com sucesso!")
            st.rerun()
          else:
            st.warning("Nenhum item marcado para exclusão.")
        except Exception as e:
          st.error(f"Erro detalhado ao salvar: {e}")
  else:
    st.info(
        "Nenhum registro encontrado na tabela 'vendas'. Faça um lançamento"
        " acima para testar."
    )

  st.markdown("---")
  st.subheader("🔍 Edição Direta na Tabela & Gestão por Cliente")

  clientes_filtro = ["TODOS"] + (
      carregar_coluna("clientes", "nome")
      or carregar_coluna("vendas", "cliente")
      or []
  )

  col_f1, col_f2, col_f3 = st.columns(3)
  with col_f1:
    cliente_sel = st.selectbox(
        "Filtrar por Cliente:", clientes_filtro, key=f"filtro_cli_tabela_{menu_admin}"
    )
  with col_f2:
    d_inicio = st.date_input(
        "Data Inicial do Filtro",
        value=date(2025, 1, 1),
        key=f"filtro_d_ini_{menu_admin}",
    )
  with col_f3:
    d_fin = st.date_input(
        "Data Final do Filtro",
        value=data_hoje_brasil,
        key=f"filtro_d_fin_{menu_admin}",
    )

  texto_botao_atualizar = (
      "🔄 Atualizar Preços de Venda"
      if not is_modo_pedido
      else "🔄 Atualizar Preços de Custo"
  )
  if st.button(texto_botao_atualizar, key=f"btn_atualizar_precos_{menu_admin}"):
    cursor = conn.cursor()
    coluna_alvo_estoque = (
        "valor_venda" if not is_modo_pedido else "valor_compra"
    )

    cursor.execute(f"""
            UPDATE vendas 
            SET valor_venda = (
                SELECT {coluna_alvo_estoque} 
                FROM produtos 
                WHERE TRIM(UPPER(produtos.nome)) = TRIM(UPPER(vendas.produto))
            ),
            valor_total = quantidade * (
                SELECT {coluna_alvo_estoque} 
                FROM produtos 
                WHERE TRIM(UPPER(produtos.nome)) = TRIM(UPPER(vendas.produto))
            )
            WHERE TRIM(UPPER(produto)) IN (SELECT TRIM(UPPER(nome)) FROM produtos)
        """)
    linhas_afetadas = cursor.rowcount
    conn.commit()

    if linhas_afetadas > 0:
      st.success(
          f"Preços atualizados com sucesso! ({linhas_afetadas} itens modificados)"
      )
    else:
      st.warning(
          "Nenhum produto correspondente foi encontrado na tabela de estoque para"
          " atualizar."
      )
    st.rerun()

  s_d1, s_d2 = d_inicio.strftime("%Y-%m-%d"), d_fin.strftime("%Y-%m-%d")
  df_registros = carregar_dados("SELECT * FROM vendas")

  if not df_registros.empty:
    df_registros.columns = [c.lower() for c in df_registros.columns]
    if "status" not in df_registros.columns:
      df_registros["status"] = "Pendente"
    if "valor_venda" in df_registros.columns and "valor_unitario" not in df_registros.columns:
      df_registros["valor_unitario"] = df_registros["valor_venda"]

    if "data" in df_registros.columns:
      df_registros["data_str"] = (
          df_registros["data"].astype(str).str.slice(0, 10)
      )
      df_historico_periodo = df_registros[
          (df_registros["data_str"] >= s_d1)
          & (df_registros["data_str"] <= s_d2)
      ]
    else:
      df_historico_periodo = pd.DataFrame()

    if cliente_sel != "TODOS" and "cliente" in df_historico_periodo.columns:
      df_historico_periodo = df_historico_periodo[
          df_historico_periodo["cliente"]
          .astype(str)
          .str.strip()
          .str.upper()
          == str(cliente_sel).strip().upper()
      ]
  else:
    df_historico_periodo = pd.DataFrame()

  st.markdown("---")
  st.markdown("### 🔍 Consultar e Editar por Data Específica")

  data_sugerida = datetime.now().date()
  if not df_registros.empty and "data_str" in df_registros.columns:
    max_data_str = df_registros["data_str"].max()
    if max_data_str and len(str(max_data_str)) >= 10:
      try:
        data_sugerida = datetime.strptime(
            str(max_data_str)[:10], "%Y-%m-%d"
        ).date()
      except:
        pass

  data_consulta_input = st.date_input(
      "Escolha a data para gerenciar/editar os pedidos:",
      value=data_sugerida,
      key=f"input_data_especifica_{menu_admin}",
  )
  data_consulta_str = data_consulta_input.strftime("%Y-%m-%d")

  df_dia = pd.DataFrame()
  if not df_registros.empty and "data_str" in df_registros.columns:
    df_dia = df_registros[df_registros["data_str"] == data_consulta_str]

  if not df_dia.empty:
    st.markdown(f"### 🟢 Pedidos da Data: {data_consulta_str} (Editáveis)")

    if "Excluir" not in df_dia.columns:
      df_dia.insert(0, "Excluir", False)

    df_editado = st.data_editor(
        df_dia,
        column_config={
            "Excluir": st.column_config.CheckboxColumn(
                "❌ Excluir?", default=False
            ),
            "id": st.column_config.NumberColumn("ID", disabled=True),
            "cliente": st.column_config.TextColumn("Cliente", disabled=True),
            "produto": st.column_config.TextColumn("Produto", disabled=True),
            "quantidade": st.column_config.NumberColumn(
                "Quantidade", min_value=0.01, step=0.01, format="%.2f"
            ),
            "valor_unitario": st.column_config.NumberColumn(
                "Preço Unitário (R$)", format="R$ %.2f"
            ),
            "valor_total": st.column_config.NumberColumn(
                "Total (R$)", disabled=True, format="R$ %.2f"
            ),
            "status": st.column_config.TextColumn("Status", disabled=True),
        },
        hide_index=True,
        key=f"tabela_pedidos_data_esp_{menu_admin}",
    )

    col_btn1, col_btn2 = st.columns(2)

    with col_btn1:
      if st.button(
          "💾 Salvar Alterações",
          type="primary",
          key=f"btn_salvar_data_esp_{menu_admin}",
      ):
        try:
          cursor = conn.cursor()
          for index, row in df_editado.iterrows():
            novo_total = float(row["quantidade"]) * float(
                row["valor_unitario"]
            )
            cursor.execute(
                """
                            UPDATE vendas 
                            SET quantidade = ?, valor_venda = ?, valor_total = ?, status = ?
                            WHERE id = ?
                        """,
                (
                    row["quantidade"],
                    row["valor_unitario"],
                    novo_total,
                    row.get("status", "Pendente"),
                    row["id"],
                ),
            )
          conn.commit()
          st.success("Registros atualizados com sucesso!")
          st.rerun()
        except Exception as ex:
          conn.rollback()
          st.error(f"Erro ao atualizar: {ex}")

    with col_btn2:
      if st.button(
          "🗑️ Excluir Marcados",
          type="secondary",
          key=f"btn_excluir_data_esp_{menu_admin}",
      ):
        try:
          cursor = conn.cursor()
          ids_para_excluir = df_editado[df_editado["Excluir"] == True][
              "id"
          ].tolist()

          if ids_para_excluir:
            for id_pedido in ids_para_excluir:
              cursor.execute("DELETE FROM vendas WHERE id = ?", (id_pedido,))
            conn.commit()
            st.warning("Itens selecionados excluídos com sucesso!")
            st.rerun()
          else:
            st.info("Nenhum item foi marcado para exclusão.")
        except Exception as ex:
          conn.rollback()
          st.error(f"Erro ao excluir: {ex}")

    # Geração do PDF
    try:
      buffer = io.BytesIO()
      doc = SimpleDocTemplate(
          buffer,
          pagesize=letter,
          rightMargin=30,
          leftMargin=30,
          topMargin=15,
          bottomMargin=30,
      )
      elements = []
      styles = getSampleStyleSheet()

      hora_local = datetime.now() - fuso_brasil
      data_hora_str = hora_local.strftime("%Y-%m-%d %H:%M:%S")

      estilo_empresa = ParagraphStyle(
          "Empresa",
          parent=styles["Heading1"],
          fontSize=14,
          textColor=colors.HexColor("#002060"),
          alignment=1,
          fontName="Helvetica-Bold",
          spaceAfter=0,
      )
      estilo_sub_empresa = ParagraphStyle(
          "SubEmpresa",
          parent=styles["Normal"],
          fontSize=8,
          textColor=colors.black,
          alignment=1,
          leading=9,
          spaceAfter=0,
      )
      estilo_titulo_rel = ParagraphStyle(
          "TituloRel",
          parent=styles["Heading2"],
          fontSize=10,
          textColor=colors.black,
          alignment=1,
          fontName="Helvetica-Bold",
          spaceBefore=4,
          spaceAfter=0,
      )
      estilo_info_cli = ParagraphStyle(
          "InfoCli",
          parent=styles["Normal"],
          fontSize=8,
          textColor=colors.black,
          alignment=1,
          leading=10,
          spaceAfter=0,
      )

      estilo_th = ParagraphStyle(
          "TH",
          parent=styles["Normal"],
          fontSize=9,
          textColor=colors.white,
          alignment=1,
          fontName="Helvetica-Bold",
      )
      estilo_td_left = ParagraphStyle(
          "TDLeft", parent=styles["Normal"], fontSize=9, textColor=colors.black, alignment=0
      )
      estilo_td_center = ParagraphStyle(
          "TDCenter", parent=styles["Normal"], fontSize=9, textColor=colors.black, alignment=1
      )
      estilo_td_right = ParagraphStyle(
          "TDRight", parent=styles["Normal"], fontSize=9, textColor=colors.black, alignment=2
      )

      estilo_total_label = ParagraphStyle(
          "TotLabel",
          parent=styles["Normal"],
          fontSize=9,
          textColor=colors.white,
          alignment=0,
          fontName="Helvetica-Bold",
      )
      estilo_total_val = ParagraphStyle(
          "TotVal",
          parent=styles["Normal"],
          fontSize=9,
          textColor=colors.white,
          alignment=2,
          fontName="Helvetica-Bold",
      )

      elements.append(Paragraph("REY DA CEBOLA", estilo_empresa))
      elements.append(
          Paragraph(
              "CNPJ: 194.174.39/000-42 INSC.EST.: 12.426725-4<br/>CONTATO:"
              " (99) 98814-9722 OU (99) 98414-3943",
              estilo_sub_empresa,
          )
      )
      elements.append(Spacer(1, 4))

      cliente_atual_pdf = cliente_sel if cliente_sel != "TODOS" else "Geral"
      elements.append(
          Paragraph(
              f"Relatório de Pedidos - Data: {data_consulta_str}",
              estilo_titulo_rel,
          )
      )
      elements.append(
          Paragraph(
              f"<b>Cliente:</b> {cliente_atual_pdf} | <b>Gerado em:</b>"
              f" {data_hora_str}",
              estilo_info_cli,
          )
      )
      elements.append(Spacer(1, 8))

      data_tabela = [[
          Paragraph("Produto", estilo_th),
          Paragraph("Qtd Total", estilo_th),
          Paragraph("Preço Unitário (R$)", estilo_th),
          Paragraph("Valor Total (R$)", estilo_th),
      ]]

      for _, row in df_dia.iterrows():
        data_tabela.append([
            Paragraph(str(row["produto"]), estilo_td_left),
            Paragraph(f"{row['quantidade']:.2f}", estilo_td_center),
            Paragraph(f"R$ {row['valor_unitario']:.2f}", estilo_td_right),
            Paragraph(f"R$ {row['valor_total']:.2f}", estilo_td_right),
        ])

      total_geral_dia = df_dia["valor_total"].sum()

      data_tabela.append([
          Paragraph("VALOR TOTAL GERAL", estilo_total_label),
          Paragraph("", estilo_total_val),
          Paragraph("", estilo_total_val),
          Paragraph(f"R$ {total_geral_dia:.2f}", estilo_total_val),
      ])

      t = Table(data_tabela, colWidths=[220, 80, 110, 130])
      t.setStyle(
          TableStyle([
              (
                  "BACKGROUND",
                  (0, 0),
                  (-1, 0),
                  colors.HexColor("#1F4E79"),
              ),
              ("ALIGN", (0, 0), (-1, -1), "LEFT"),
              ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
              ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
              ("TOPPADDING", (0, 0), (-1, -1), 4),
              (
                  "GRID",
                  (0, 0),
                  (-1, -2),
                  0.5,
                  colors.HexColor("#CCCCCC"),
              ),
              ("SPAN", (0, -1), (2, -1)),
              ("BACKGROUND", (0, -1), (-1, -1), colors.black),
          ])
      )

      elements.append(t)
      doc.build(elements)
      pdf_bytes = buffer.getvalue()

      st.download_button(
          label="📥 Baixar PDF da Data Escolhida",
          data=pdf_bytes,
          file_name=(
              f"relatorio_pedidos_{data_consulta_str}_{cliente_atual_pdf}.pdf"
          ),
          mime="application/pdf",
          key=f"btn_pdf_data_esp_{menu_admin}",
      )
    except Exception as ex:
      st.error(f"Erro ao gerar PDF: {ex}")
  else:
    st.info(
        f"ℹ️ Nenhum pedido encontrado para a data {data_consulta_str}."
        " Selecione outra data no campo acima para editar."
    )

  if not df_historico_periodo.empty:
    st.markdown("---")
    st.markdown("### 📚 Histórico de Registros do Período")
    st.dataframe(
        df_historico_periodo, hide_index=True, use_container_width=True
    )
  else:
    st.warning("Nenhum registro encontrado no histórico para o período selecionado.")

  conn.close()


# EXECUÇÃO DO MÓDULO NO APP PRINCIPAL
st.title("Rey da Cebola - Painel de Vendas e Gestão")
renderizar_modulo_vendas(menu_admin="principal", is_modo_pedido=False)
