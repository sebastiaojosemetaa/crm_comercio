def carregar_dados_iniciais():
    conn = get_db_connection()
    c = conn.cursor()
    # Cadastra clientes se a tabela estiver vazia
    clientes_padrao = [
        ("Carlos Alberto", "1234"),
        ("Sebastião", "123456"),
        ("Valeilde Loja 01", "12345"),
        ("Neurialdo", "456892")
    ]
    for nome, senha in clientes_padrao:
        try:
            c.execute("INSERT OR IGNORE INTO clientes (nome, telefone) VALUES (?, ?)", (nome, senha))
        except:
            pass
    conn.commit()

# Chame esta função após init_db()
init_db()
carregar_dados_iniciais()
