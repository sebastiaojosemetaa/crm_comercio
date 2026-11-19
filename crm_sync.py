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
    "estornos_pagamentos_contas", "eventos_gaveta", "vinculos_pagamentos_caixa",
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
    # Índices preservam restrições como a unicidade de parcelas após criar uma tabela.
    indices = [sql for nome, sql in conexao.execute(
        "SELECT tbl_name, sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL ORDER BY name"
    ) if nome in TABELAS]
    sequencias = {}
    if conexao.execute("SELECT 1 FROM sqlite_master WHERE name='sqlite_sequence'").fetchone():
        sequencias = {nome: valor for nome, valor in conexao.execute("SELECT name, seq FROM sqlite_sequence")
                      if nome in TABELAS}
    return {"empresa": empresa, "tabelas": tabelas, "indices": indices, "sequencias": sequencias}


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
    for sql in documento.get("indices", []):
        if not re.match(r"^CREATE\s+(?:UNIQUE\s+)?INDEX\s", sql, re.I):
            raise ValueError("Índice incompatível na sincronização.")
        sql = re.sub(r"^(CREATE\s+(?:UNIQUE\s+)?INDEX\s+)(?!IF\s+NOT\s+EXISTS)",
                     r"\1IF NOT EXISTS ", sql, count=1, flags=re.I)
        conexao.execute(sql)
    for nome, sequencia in documento.get("sequencias", {}).items():
        if nome not in TABELAS:
            raise ValueError("Contador de tabela inválido.")
        linha = conexao.execute("SELECT seq FROM sqlite_sequence WHERE name=?", (nome,)).fetchone()
        if linha:
            conexao.execute("UPDATE sqlite_sequence SET seq=MAX(seq, ?) WHERE name=?", (int(sequencia), nome))
        else:
            conexao.execute("INSERT INTO sqlite_sequence(name, seq) VALUES (?, ?)", (nome, int(sequencia)))
    violacoes = conexao.execute("PRAGMA foreign_key_check").fetchall()
    if violacoes:
        raise ValueError("A cópia recebida contém vínculos inconsistentes. Confira o backup.")


def sincronizar(caminho, empresa, conectar, pode_iniciar=False, receber_inicial=False):
    with closing(sqlite3.connect(caminho, timeout=5)) as local:
        local.execute("PRAGMA foreign_keys=ON")
        local.execute("""CREATE TABLE IF NOT EXISTS crm_sync_estado (
            empresa TEXT PRIMARY KEY, base_hash TEXT, copia_anterior BLOB
        )""")
        local.commit()
        try:
            with conectar() as remoto:
                remoto.execute("CREATE SCHEMA IF NOT EXISTS crm_producao")
                remoto.execute("""CREATE TABLE IF NOT EXISTS crm_producao.sincronizacao_empresas (
                    empresa TEXT PRIMARY KEY, versao BIGINT NOT NULL,
                    hash_dados TEXT NOT NULL, conteudo BYTEA NOT NULL,
                    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now()
                )""")
                # A conexão remota é aberta antes de bloquear as gravações locais.
                local.execute("BEGIN IMMEDIATE")
                vinculo = local.execute("SELECT documento FROM crm_empresa WHERE id=1").fetchone()
                if vinculo != (empresa,):
                    raise ValueError("O banco local pertence a outra empresa.")
                atual = capturar(local, empresa)
                hash_local = impressao(atual)
                estado = local.execute(
                    "SELECT base_hash FROM crm_sync_estado WHERE empresa=?", (empresa,)
                ).fetchone()
                base = estado[0] if estado else None
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
                elif base is None and (not receber_inicial or pode_iniciar):
                    local.rollback()
                    return "inicial_diferente", "As bases iniciais diferem. Receba a base inicial publicada pelo Windows."
                elif hash_remoto == base:
                    remoto.execute("""UPDATE crm_producao.sincronizacao_empresas
                        SET versao=versao+1, hash_dados=%s, conteudo=%s, atualizado_em=now()
                        WHERE empresa=%s""", (hash_local, empacotar(atual), empresa))
                    hash_remoto = hash_local
                    resultado = ("enviado", f"Alterações enviadas. Versão {versao + 1}.")
                elif hash_local == base or (base is None and receber_inicial and not pode_iniciar):
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


def publicar_catalogo(conectar, empresas, planos):
    """Publica os cadastros, sem os caminhos locais ou senhas em texto."""
    registros = []
    for documento, empresa in empresas.items():
        if not re.fullmatch(r"[0-9]{11}|[0-9]{14}", documento):
            raise ValueError("Documento inválido no cadastro.")
        segredo = empresa.get("segredo_licenca") or empresa.get("senha_admin")
        if empresa.get("senha_admin"):
            sal = hashlib.sha256((documento + segredo).encode()).hexdigest()[:32]
            senha_hash = hashlib.scrypt(empresa["senha_admin"].encode(),
                                       salt=bytes.fromhex(sal), n=16384, r=8, p=1).hex()
        else:
            sal, senha_hash = empresa["sal"], empresa["senha_hash"]
        registros.append((documento, empresa["nome"], sal, senha_hash,
                          segredo, planos.get(documento, "Simples")))
    if not registros:
        raise ValueError("Nenhuma empresa cadastrada para publicar.")
    with conectar() as remoto:
        remoto.execute("CREATE SCHEMA IF NOT EXISTS crm_producao")
        remoto.execute("""CREATE TABLE IF NOT EXISTS crm_producao.catalogo_empresas (
            documento TEXT PRIMARY KEY, nome TEXT NOT NULL, sal TEXT NOT NULL,
            senha_hash TEXT NOT NULL, segredo_licenca TEXT NOT NULL,
            plano TEXT NOT NULL, atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now()
        )""")
        for registro in registros:
            remoto.execute("""INSERT INTO crm_producao.catalogo_empresas AS c
                (documento,nome,sal,senha_hash,segredo_licenca,plano)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT(documento) DO UPDATE SET nome=excluded.nome, sal=excluded.sal,
                senha_hash=excluded.senha_hash, segredo_licenca=excluded.segredo_licenca,
                plano=excluded.plano, atualizado_em=now()
                WHERE (c.nome,c.sal,c.senha_hash,c.segredo_licenca,c.plano)
                IS DISTINCT FROM (excluded.nome,excluded.sal,excluded.senha_hash,
                                  excluded.segredo_licenca,excluded.plano)""", registro)
    return len(registros)


def receber_catalogo(conectar, caminho_cadastro, documentos_configurados):
    with conectar() as remoto:
        registros = remoto.execute("""SELECT documento,nome,sal,senha_hash,segredo_licenca,plano
            FROM crm_producao.catalogo_empresas ORDER BY documento""").fetchall()
    for documento, nome, sal, senha_hash, segredo, plano in registros:
        if (
            not re.fullmatch(r"[0-9]{11}|[0-9]{14}", documento)
            or not nome.strip() or plano not in {"Simples", "Pro"}
            or not re.fullmatch(r"[0-9a-f]{32}", sal)
            or not re.fullmatch(r"[0-9a-f]{128}", senha_hash)
            or not segredo
        ):
            raise ValueError("Cadastro remoto inválido.")
    from pathlib import Path
    Path(caminho_cadastro).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(caminho_cadastro, timeout=10) as cadastro:
        cadastro.execute("BEGIN IMMEDIATE")
        cadastro.execute("""CREATE TABLE IF NOT EXISTS empresas (
            documento TEXT PRIMARY KEY,nome TEXT NOT NULL,sal TEXT NOT NULL,
            senha_hash TEXT NOT NULL,segredo_licenca TEXT NOT NULL)""")
        cadastro.execute("""CREATE TABLE IF NOT EXISTS planos_comerciais (
            documento TEXT PRIMARY KEY,plano TEXT NOT NULL CHECK(plano IN ('Simples','Pro')))""")
        cadastro.execute("""CREATE TABLE IF NOT EXISTS catalogo_licencas (
            documento TEXT PRIMARY KEY, nome TEXT NOT NULL, segredo_licenca TEXT NOT NULL
        )""")
        for documento,nome,sal,senha_hash,segredo,plano in registros:
            cadastro.execute("""INSERT INTO catalogo_licencas VALUES(?,?,?)
                ON CONFLICT(documento) DO UPDATE SET nome=excluded.nome,
                segredo_licenca=excluded.segredo_licenca""", (documento,nome,segredo))
            if documento not in documentos_configurados:
                cadastro.execute("""INSERT INTO empresas VALUES(?,?,?,?,?)
                    ON CONFLICT(documento) DO UPDATE SET nome=excluded.nome,sal=excluded.sal,
                    senha_hash=excluded.senha_hash,segredo_licenca=excluded.segredo_licenca""",
                    (documento,nome,sal,senha_hash,segredo))
            cadastro.execute("""INSERT INTO planos_comerciais VALUES(?,?)
                ON CONFLICT(documento) DO UPDATE SET plano=excluded.plano""", (documento,plano))
    return len(registros)



def aplicar_configuracao_catalogo(caminho_cadastro, configuradas):
    from pathlib import Path

    resultado = {doc: dict(config) for doc, config in configuradas.items()}
    if not Path(caminho_cadastro).exists():
        return resultado
    with sqlite3.connect(Path(caminho_cadastro).resolve().as_uri() + "?mode=ro", uri=True) as cadastro:
        if not cadastro.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='catalogo_licencas'"
        ).fetchone():
            return resultado
        for documento, nome, segredo in cadastro.execute(
            "SELECT documento,nome,segredo_licenca FROM catalogo_licencas"
        ):
            if documento in resultado:
                resultado[documento]["nome"] = nome
                resultado[documento]["segredo_licenca"] = segredo
    return resultado
