with tab_novo:
  st.subheader("Criar Novo Pedido")

  # Verifica se existem clientes antes de abrir o formulário
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

        # Busca dados do produto selecionado
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
