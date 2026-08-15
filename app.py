# ---------------------------------------------------------------------
        # BOTÃO DE DOWNLOAD DO RELATÓRIO PDF (PEDIDOS)
        # ---------------------------------------------------------------------
        st.markdown("---")
        st.subheader("📥 Exportar Relatório em PDF")
        
        if not pedidos_df.empty:
            pdf_buffer = gerar_pdf_relatorio(df_agrupado, titulo="Relatório Consolidado de Pedidos")
            st.download_button(
                label="📄 Baixar Relatório de Pedidos em PDF",
                data=pdf_buffer,
                file_name=f"relatorio_pedidos_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                mime="application/pdf"
            )

# --- REGISTRAR VENDA ---
elif menu == "🛒 Registrar Venda":
    st.title("🛒 Registrar Nova Venda Direta")
    produtos_df = pd.read_sql_query("SELECT * FROM produtos", conn)
    
    if produtos_df.empty:
        st.warning("Cadastre produtos antes de registrar vendas.")
    else:
        col_v1, col_v2 = st.columns(2)
        with col_v1:
            v_cliente = st.selectbox("Cliente", list_clientes, key="v_cliente")
        with col_v2:
            v_forma = st.selectbox("Forma de Pagamento", ["Dinheiro", "PIX", "Cartão de Débito", "Cartão de Crédito", "A Prazo / Fiado"], key="v_forma")
            
        st.markdown("---")
        c_i1, c_i2, c_i3 = st.columns([3, 2, 2])
        with c_i1:
            v_prod = st.selectbox("Produto", produtos_df["produto"].tolist(), key="v_prod")
            p_info = produtos_df[produtos_df["produto"] == v_prod].iloc[0]
        with c_i2:
            v_qtd = st.number_input("Quantidade", min_value=0.01, value=1.0, step=0.1, key="v_qtd")
        with c_i3:
            v_preco_unit = st.number_input("Valor Unitário (R$)", value=float(p_info["valor_venda"]), min_value=0.0, key="v_preco_unit")
            
        if st.button("➕ Adicionar ao Carrinho de Venda"):
            tot_item = v_qtd * v_preco_unit
            st.session_state.carrinho_venda.append({
                "produto": v_prod,
                "quantidade": v_qtd,
                "valor_venda": v_preco_unit,
                "valor_total": tot_item,
                "fornecedor": p_info.get("fornecedor", "Geral"),
                "grupo": p_info.get("grupo", "Geral")
            })
            st.success("Item adicionado ao carrinho!")
            
        if len(st.session_state.carrinho_venda) > 0:
            st.markdown("### 🛍️ Carrinho de Venda Atual")
            df_v_cart = pd.DataFrame(st.session_state.carrinho_venda)
            st.dataframe(df_v_cart[["produto", "quantidade", "valor_venda", "valor_total"]], use_container_width=True)
            
            tot_geral_venda = df_v_cart["valor_total"].sum()
            st.write(f"**Total da Venda: R$ {tot_geral_venda:,.2f}**")
            
            val_recebido = st.number_input("Valor Recebido em Dinheiro/PIX (R$)", min_value=0.0, value=float(tot_geral_venda) if v_forma != "A Prazo / Fiado" else 0.0)
            troco = max(0.0, val_recebido - tot_geral_venda)
            restante = max(0.0, tot_geral_venda - val_recebido)
            
            if v_forma == "A Prazo / Fiado":
                restante = tot_geral_venda
                troco = 0.0
                
            st.write(f"Troco: R$ {troco:,.2f} | Restante/Fiado: R$ {restante:,.2f}")
            
            if st.button("💾 Concluir Venda e Dar Baixa no Estoque"):
                codigo_venda = f"VEN-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                data_venda = datetime.now().strftime("%Y-%m-%d %H:%M")
                
                for item in st.session_state.carrinho_venda:
                    cursor.execute("""
                        INSERT INTO vendas (codigo_venda, cliente, produto, fornecedor, grupo, quantidade, valor_venda, valor_total, forma_pagamento, valor_recebido, troco, restante, data)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        codigo_venda, v_cliente, item["produto"], item["fornecedor"], item["grupo"],
                        item["quantidade"], item["valor_venda"], item["valor_total"],
                        v_forma, val_recebido, troco, restante, data_venda
                    ))
                    cursor.execute("""
                        UPDATE produtos SET quantidade = quantidade - ? WHERE produto = ?
                    """, (item["quantidade"], item["produto"]))
                    
                conn.commit()
                st.session_state.carrinho_venda = []
                st.success(f"Venda {codigo_venda} concluída com sucesso!")
                st.rerun()

# --- ENTRADA DE ESTOQUE ---
elif menu == "📥 Entrada de Estoque (Compras)":
    st.title("📥 Entrada de Estoque (Registro de Compras)")
    produtos_df = pd.read_sql_query("SELECT * FROM produtos", conn)
    
    with st.form("form_compra"):
        c1, c2 = st.columns(2)
        with c1:
            prod_compra = st.selectbox("Produto", produtos_df["produto"].tolist() if not produtos_df.empty else ["Novo Produto"])
            forn_compra = st.selectbox("Fornecedor", list_fornecedores)
            grupo_compra = st.selectbox("Grupo", list_grupos)
        with c2:
            qtd_compra = st.number_input("Quantidade Comprada", min_value=0.01, value=1.0, step=1.0)
            v_compra = st.number_input("Valor de Compra Unitário (R$)", min_value=0.0, value=0.0)
            v_venda = st.number_input("Valor de Venda Unitário (R$)", min_value=0.0, value=0.0)
            
        submitted = st.form_submit_button("Registrar Entrada")
        if submitted:
            total_compra = qtd_compra * v_compra
            data_atual = datetime.now().strftime("%Y-%m-%d %H:%M")
            
            cursor.execute("""
                INSERT INTO compras (produto, fornecedor, grupo, quantidade, valor_compra, valor_venda, valor_total, data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (prod_compra, forn_compra, grupo_compra, qtd_compra, v_compra, v_venda, total_compra, data_atual))
            
            # Atualiza ou insere o produto na tabela de produtos
            cursor.execute("SELECT id, quantidade FROM produtos WHERE produto = ?", (prod_compra,))
            res = cursor.fetchone()
            if res:
                cursor.execute("""
                    UPDATE produtos SET quantidade = quantidade + ?, valor_compra = ?, valor_venda = ?, grupo = ? WHERE produto = ?
                """, (qtd_compra, v_compra, v_venda, grupo_compra, prod_compra))
            else:
                cursor.execute("""
                    INSERT INTO produtos (produto, grupo, quantidade, valor_compra, valor_venda)
                    VALUES (?, ?, ?, ?, ?)
                """, (prod_compra, grupo_compra, qtd_compra, v_compra, v_venda))
                
            conn.commit()
            st.success("Entrada de estoque registrada com sucesso!")

# --- ESTOQUE DE PRODUTOS ---
elif menu == "📦 Estoque de Produtos":
    st.title("📦 Consulta e Gestão de Estoque")
    df_prod = pd.read_sql_query("SELECT * FROM produtos", conn)
    
    if df_prod.empty:
        st.info("Nenhum produto cadastrado.")
    else:
        st.dataframe(df_prod, use_container_width=True)

# --- CADASTROS ---
elif menu == "👥 Cadastros (Clientes / Fornecedores / Grupos)":
    st.title("👥 Gestão de Cadastros")
    tab_c, tab_f, tab_g = st.tabs(["Clientes", "Fornecedores", "Grupos"])
    
    with tab_c:
        st.subheader("Gerenciar Clientes")
        novo_cli = st.text_input("Nome do Novo Cliente")
        if st.button("Adicionar Cliente"):
            if novo_cli:
                try:
                    cursor.execute("INSERT INTO clientes (cliente) VALUES (?)", (novo_cli,))
                    conn.commit()
                    st.success("Cliente adicionado!")
                    st.rerun()
                except:
                    st.error("Cliente já existe.")
                    
    with tab_f:
        st.subheader("Gerenciar Fornecedores")
        novo_forn = st.text_input("Nome do Novo Fornecedor")
        if st.button("Adicionar Fornecedor"):
            if novo_forn:
                try:
                    cursor.execute("INSERT INTO fornecedores (fornecedor) VALUES (?)", (novo_forn,))
                    conn.commit()
                    st.success("Fornecedor adicionado!")
                    st.rerun()
                except:
                    st.error("Fornecedor já existe.")
                    
    with tab_g:
        st.subheader("Gerenciar Grupos")
        novo_grp = st.text_input("Nome do Novo Grupo")
        if st.button("Adicionar Grupo"):
            if novo_grp:
                try:
                    cursor.execute("INSERT INTO grupos (grupo) VALUES (?)", (novo_grp,))
                    conn.commit()
                    st.success("Grupo adicionado!")
                    st.rerun()
                except:
                    st.error("Grupo já existe.")
