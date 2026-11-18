"""Sincronização transacional de uma empresa, com detecção de bases divergentes."""
import base64
import hashlib
import json
import re
import sqlite3
import zlib
from contextlib import closing

TABELAS = frozenset({
    "produtos", "clientes", "fornecedores", "grupos", "vendas", "vendas_itens",
    "vendas_cabecalho", "pedidos", "compras", "caixa_sessoes", "caixa_movimentacoes",
    "funcionarios", "pagamentos_funcionarios", "usuarios", "auditoria_estornos",
    "contas_receber", "movimentos_estoque", "promocoes", "chaves_pix", "config_nfce",
    "preferencias_aparencia", "contas_pagar", "pagamentos_contas",
    "estornos_pagamentos_contas", "eventos_gaveta",
})


def identificador(nome):
    return '"' + nome.replace('"', '""') + '"'


def codificar(valor):
    if isinstance(valor, bytes):
        return {"blob": base64.b64encode(valor).decode("ascii")}
    return valor


def decodificar(valor):
    if isinstance(valor, dict):
        return base64.b64decode(valor["blob"], validate=True)
    return valor


def capturar(conexao, empresa):
    tabelas = {}
    for nome, sql in conexao.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name"
    ):
        if nome not in TABELAS:
            continue
        colunas = [linha[1] for linha in conexao.execute(f"PRAGMA table_info({identificador(nome)})")]
        linhas = [
            [codificar(valor) for valor in linha]
            for linha in conexao.execute(f"SELECT * FROM {identificador(nome)}")
        ]
        # A ordem física das linhas e o estilo do CREATE TABLE não alteram os dados.
        linhas.sort(key=lambda linha: json.dumps(linha, sort_keys=True, ensure_ascii=False))
        tabelas[nome] = {"sql": sql, "colunas": colunas, "linhas": linhas}
    return {"empresa": empresa, "tabelas": tabelas}


def impressao(documento):
    dados = {
        nome: {"colunas": tabela["colunas"], "linhas": tabela["linhas"]}
        for nome, tabela in documento["tabelas"].items()
        if tabela["linhas"]
    }
    payload = json.dumps([documento["empresa"], dados], sort_keys=True,
                         ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def empacotar(documento):
    return zlib.compress(json.dumps(documento, ensure_ascii=False, allow_nan=False).encode())


def desempacotar(conteudo, empresa):
    documento = json.loads(zlib.decompress(bytes(conteudo)))
    if documento["empresa"] != empresa or not set(documento["tabelas"]).issubset(TABELAS):
        raise ValueError("A cópia de sincronização pertence a outra empresa ou versão.")
    return documento


def aplicar(conexao, documento):
    """Chamador mantém BEGIN IMMEDIATE. Falhas revertem dados e migrações."""
    existentes = {r[0] for r in conexao.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for nome, tabela in documento["tabelas"].items():
        if nome not in existentes:
            sql = tabela["sql"]
            if not re.match(r'^CREATE\s+TABLE\s', sql, re.I):
                raise ValueError("Estrutura incompatível na sincronização.")
            # Apenas uma instrução CREATE TABLE pode ser executada.
            conexao.execute(sql)
            existentes.add(nome)
        colunas = [r[1] for r in conexao.execute(f"PRAGMA table_info({identificador(nome)})")]
        if colunas != tabela["colunas"]:
            raise ValueError(f"Atualize as duas instalações. A estrutura de {nome} é diferente.")
    conexao.execute("PRAGMA defer_foreign_keys=ON")
    for nome in sorted(TABELAS & existentes):
        conexao.execute(f"DELETE FROM {identificador(nome)}")
    for nome, tabela in documento["tabelas"].items():
        colunas = ", ".join(identificador(c) for c in tabela["colunas"])
        marcadores = ", ".join("?" for _ in tabela["colunas"])
        conexao.executemany(
            f"INSERT INTO {identificador(nome)} ({colunas}) VALUES ({marcadores})",
            ([decodificar(v) for v in linha] for linha in tabela["linhas"]),
        )
    # Os contadores precisam acompanhar a origem mesmo quando a última linha foi excluída.
    # O AUTOINCREMENT local permanece monotônico para evitar reutilização de IDs.
    violacoes = conexao.execute("PRAGMA foreign_key_check").fetchall()
    if violacoes:
        raise ValueError("A cópia recebida contém vínculos inconsistentes. Confira o backup.")


def sincronizar(caminho, empresa, conectar, pode_iniciar=False):
    with closing(sqlite3.connect(caminho, timeout=5)) as local:
        local.execute("PRAGMA foreign_keys=ON")
        local.execute("""CREATE TABLE IF NOT EXISTS crm_sync_estado (
            empresa TEXT PRIMARY KEY, base_hash TEXT, copia_anterior BLOB
        )""")
        local.commit()
        # Serializa sincronização e gravações do PDV na mesma instalação.
        local.execute("BEGIN IMMEDIATE")
        try:
            vinculo = local.execute("SELECT documento FROM crm_empresa WHERE id=1").fetchone()
            if vinculo != (empresa,):
                raise ValueError("O banco local pertence a outra empresa.")
            atual = capturar(local, empresa)
            hash_local = impressao(atual)
            estado = local.execute(
                "SELECT base_hash FROM crm_sync_estado WHERE empresa=?", (empresa,)
            ).fetchone()
            base = estado[0] if estado else None
            with conectar() as remoto:
                remoto.execute("CREATE SCHEMA IF NOT EXISTS crm_producao")
                remoto.execute("""CREATE TABLE IF NOT EXISTS crm_producao.sincronizacao_empresas (
                    empresa TEXT PRIMARY KEY, versao BIGINT NOT NULL,
                    hash_dados TEXT NOT NULL, conteudo BYTEA NOT NULL,
                    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now()
                )""")
                if pode_iniciar:
                    remoto.execute("""INSERT INTO crm_producao.sincronizacao_empresas
                        (empresa, versao, hash_dados, conteudo) VALUES (%s, 1, %s, %s)
                        ON CONFLICT (empresa) DO NOTHING""", (empresa, hash_local, empacotar(atual)))
                registro = remoto.execute("""SELECT versao, hash_dados, conteudo
                    FROM crm_producao.sincronizacao_empresas WHERE empresa=%s FOR UPDATE""",
                    (empresa,)).fetchone()
                if not registro:
                    local.rollback()
                    return "aguardando", "Inicie a sincronização primeiro no Windows."
                versao, hash_remoto, conteudo = registro
                if hash_local == hash_remoto:
                    resultado = ("ok", f"Dados sincronizados. Versão {versao}.")
                elif base is None:
                    local.rollback()
                    return "conflito", "As bases iniciais diferem. Restaure a mesma base nas duas instalações."
                elif hash_remoto == base:
                    remoto.execute("""UPDATE crm_producao.sincronizacao_empresas
                        SET versao=versao+1, hash_dados=%s, conteudo=%s, atualizado_em=now()
                        WHERE empresa=%s""", (hash_local, empacotar(atual), empresa))
                    hash_remoto = hash_local
                    resultado = ("enviado", f"Alterações enviadas. Versão {versao + 1}.")
                elif hash_local == base:
                    documento = desempacotar(conteudo, empresa)
                    if impressao(documento) != hash_remoto:
                        raise ValueError("Falha na conferência da cópia recebida.")
                    aplicar(local, documento)
                    local.execute("""INSERT INTO crm_sync_estado (empresa, copia_anterior)
                        VALUES (?, ?) ON CONFLICT(empresa) DO UPDATE SET copia_anterior=excluded.copia_anterior""",
                        (empresa, empacotar(atual)))
                    resultado = ("recebido", f"Alterações recebidas. Versão {versao}.")
                else:
                    local.rollback()
                    return "conflito", (
                        "Há alterações pendentes nos dois sistemas. Faça backup de ambos "
                        "para conciliar as operações antes de continuar a sincronização."
                    )
            # O commit remoto precede o checkpoint local. Após interrupção, hashes iguais
            # reconhecem o envio já confirmado sem repetir operações.
            local.execute("""INSERT INTO crm_sync_estado (empresa, base_hash) VALUES (?, ?)
                ON CONFLICT(empresa) DO UPDATE SET base_hash=excluded.base_hash""",
                (empresa, hash_remoto))
            local.commit()
            return resultado
        except Exception:
            local.rollback()
            raise
