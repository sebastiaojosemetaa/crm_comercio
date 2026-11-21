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
                if empresa == CPF_ALENCARSOFT and consultar_migracao_alencarsoft(remoto):
                    return "validacao", "ALENCARSOFT migrada para o CNPJ 12727169000127. Atualize o CRM."
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


def publicar_catalogo(conectar, empresas, planos, *, somente_novas=False, conflitos=None):
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
        # Serializa a comparação e publicação: duas instalações não podem
        # reivindicar o mesmo documento com identidades diferentes.
        tem_identidades = remoto.execute("SELECT to_regclass('crm_producao.documentos_empresas')").fetchone()[0]
        if tem_identidades:
            remoto.execute("LOCK TABLE crm_producao.identidades_empresas, crm_producao.documentos_empresas, "
                           "crm_producao.catalogo_empresas IN SHARE ROW EXCLUSIVE MODE")
        else:
            remoto.execute("LOCK TABLE crm_producao.catalogo_empresas IN SHARE ROW EXCLUSIVE MODE")
        existentes = {r[0]: r for r in remoto.execute("""SELECT documento,nome,sal,senha_hash,segredo_licenca,plano
            FROM crm_producao.catalogo_empresas ORDER BY documento""").fetchall()}
        publicados = 0
        migracao = consultar_migracao_alencarsoft(remoto)
        for registro in registros:
            if migracao and registro[0] == CPF_ALENCARSOFT:
                continue
            if tem_identidades:
                titular = remoto.execute("SELECT chave_interna FROM crm_producao.documentos_empresas WHERE documento=%s", (registro[0],)).fetchone()
                if titular and titular[0] != registro[0]:
                    if conflitos is not None:
                        conflitos.append(registro[0])
                    continue
            anterior = existentes.get(registro[0])
            if anterior and anterior[4] != registro[4]:
                if conflitos is not None:
                    conflitos.append(registro[0])
                continue
            if anterior and somente_novas:
                continue
            publicados += 1
            remoto.execute("""INSERT INTO crm_producao.catalogo_empresas AS c
                (documento,nome,sal,senha_hash,segredo_licenca,plano)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT(documento) DO UPDATE SET nome=excluded.nome, sal=excluded.sal,
                senha_hash=excluded.senha_hash, segredo_licenca=excluded.segredo_licenca,
                plano=excluded.plano, atualizado_em=now()
                WHERE (c.nome,c.sal,c.senha_hash,c.segredo_licenca,c.plano)
                IS DISTINCT FROM (excluded.nome,excluded.sal,excluded.senha_hash,
                                  excluded.segredo_licenca,excluded.plano)""", registro)
    return publicados


def receber_catalogo(conectar, caminho_cadastro, documentos_configurados, *, conflitos=None):
    with conectar() as remoto:
        registros = remoto.execute("""SELECT documento,nome,sal,senha_hash,segredo_licenca,plano
            FROM crm_producao.catalogo_empresas ORDER BY documento""").fetchall()
        if consultar_migracao_alencarsoft(remoto):
            registros = [r for r in registros if r[0] != CPF_ALENCARSOFT]
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
    with closing(sqlite3.connect(caminho_cadastro, timeout=10)) as cadastro, cadastro:
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
            local = cadastro.execute("SELECT segredo_licenca FROM empresas WHERE documento=?", (documento,)).fetchone()
            if local and local[0] != segredo:
                if conflitos is not None:
                    conflitos.append(documento)
                continue
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
    with closing(sqlite3.connect(Path(caminho_cadastro).resolve().as_uri() + "?mode=ro", uri=True)) as cadastro:
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


def reunir_cadastros_empresas(configuradas, cadastradas):
    """Secrets escolhem a base ativa; cadastro duplicado fica preservado em disco."""
    from pathlib import Path
    resultado = {doc: dict(config) for doc, config in configuradas.items()}
    repetidas = sorted(set(configuradas) & set(cadastradas))
    for documento, configuracao in cadastradas.items():
        if documento not in resultado:
            resultado[documento] = dict(configuracao)
    caminhos = {}
    for documento, configuracao in resultado.items():
        caminho = str(Path(configuracao['banco']).resolve())
        if caminho in caminhos and caminhos[caminho] != documento:
            raise ValueError('Empresas diferentes apontam para o mesmo banco. Confira os caminhos nos Secrets.')
        caminhos[caminho] = documento
    return resultado, repetidas

# Migração específica autorizada da ALENCARSOFT. Outros documentos não são convertidos.
CPF_ALENCARSOFT = '95451161100'
CNPJ_ALENCARSOFT = '12727169000127'


def consultar_migracao_alencarsoft(remoto):
    if not remoto.execute("SELECT to_regclass('crm_producao.migracoes_documentos')").fetchone()[0]:
        return None
    linha = remoto.execute("SELECT dados FROM crm_producao.migracoes_documentos WHERE origem=%s AND destino=%s",
                           (CPF_ALENCARSOFT, CNPJ_ALENCARSOFT)).fetchone()
    if not linha:
        return None
    dados = linha[0]
    return json.loads(dados) if isinstance(dados, str) else dados


def converter_vinculo_alencarsoft(banco, registro):
    """Chamador mantém a transação SQLite; não altera operações ou validade de licença."""
    origem, destino = CPF_ALENCARSOFT, CNPJ_ALENCARSOFT
    tabelas = {r[0] for r in banco.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'crm_empresa' not in tabelas:
        raise ValueError('Base sem vínculo de empresa. Migração interrompida.')
    vinculo = banco.execute('SELECT documento FROM crm_empresa WHERE id=1').fetchone()
    if vinculo == (destino,):
        return False
    if vinculo != (origem,):
        raise ValueError('O arquivo não pertence ao CPF original da ALENCARSOFT.')
    atual_antigo = capturar(banco, origem)
    hash_antigo_local = impressao(atual_antigo)
    banco.execute('UPDATE crm_empresa SET documento=? WHERE id=1', (destino,))
    if 'empresas_dispositivos' in tabelas:
        colunas = {r[1] for r in banco.execute('PRAGMA table_info(empresas_dispositivos)')}
        if 'cnpj' in colunas:
            for dispositivo, documento in banco.execute('SELECT device_id,cnpj FROM empresas_dispositivos').fetchall():
                if re.sub(r'\D', '', str(documento or '')) in ('', origem):
                    banco.execute('UPDATE empresas_dispositivos SET cnpj=? WHERE device_id=?', (destino, dispositivo))
    if 'crm_sync_estado' in tabelas:
        estado = banco.execute('SELECT base_hash,copia_anterior FROM crm_sync_estado WHERE empresa=?', (origem,)).fetchone()
        if estado:
            base, anterior = estado
            if base == registro.get('hash_origem'):
                nova_base = registro['hash_destino']
            elif base == hash_antigo_local:
                nova_base = impressao(capturar(banco, destino))
            else:
                nova_base = 'migracao:conciliacao-necessaria'
            if anterior:
                copia = desempacotar(anterior, origem)
                copia['empresa'] = destino
                anterior = empacotar(copia)
            if banco.execute('SELECT 1 FROM crm_sync_estado WHERE empresa=?', (destino,)).fetchone():
                raise ValueError('Já existe um checkpoint independente para o CNPJ. Dados preservados.')
            banco.execute('DELETE FROM crm_sync_estado WHERE empresa=?', (origem,))
            banco.execute('INSERT INTO crm_sync_estado VALUES(?,?,?)', (destino,nova_base,anterior))
    return True


def converter_backup_alencarsoft(conteudo, registro):
    from pathlib import Path
    import tempfile
    with tempfile.TemporaryDirectory(prefix='crm_migrar_backup_') as pasta:
        caminho = Path(pasta)/'copia.db'
        caminho.write_bytes(bytes(conteudo))
        with closing(sqlite3.connect(caminho)) as banco:
            if banco.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                raise ValueError('Backup original inválido. Migração interrompida.')
            with banco:
                converter_vinculo_alencarsoft(banco, registro)
            banco.execute('PRAGMA journal_mode=DELETE')
        return caminho.read_bytes()


def migrar_servidor_alencarsoft(conectar, hash_local_esperado=None, aparelhos_ativos_locais=None):
    """Copia bases/licenças/backups para o CNPJ numa transação; mantém o histórico CPF."""
    origem, destino = CPF_ALENCARSOFT, CNPJ_ALENCARSOFT
    with conectar() as remoto:
        remoto.execute('CREATE SCHEMA IF NOT EXISTS crm_producao')
        remoto.execute('''CREATE TABLE IF NOT EXISTS crm_producao.migracoes_documentos (
            origem TEXT PRIMARY KEY, destino TEXT UNIQUE NOT NULL,
            dados JSONB NOT NULL, criado_em TIMESTAMPTZ NOT NULL DEFAULT now())''')
        # Os locks impedem alteração da base durante a conferência e cópia.
        remoto.execute('LOCK TABLE crm_producao.migracoes_documentos, crm_producao.catalogo_empresas, '
                       'crm_producao.sincronizacao_empresas, crm_producao.estado_licencas, '
                       'crm_producao.backups_sqlite IN SHARE ROW EXCLUSIVE MODE')
        existente = consultar_migracao_alencarsoft(remoto)
        if existente:
            return existente
        snapshot = remoto.execute('SELECT versao,hash_dados,conteudo FROM crm_producao.sincronizacao_empresas '
                                  'WHERE empresa=%s', (origem,)).fetchone()
        if not snapshot:
            raise ValueError('A base sincronizada do CPF não foi encontrada. Nada foi migrado.')
        if remoto.execute('SELECT 1 FROM crm_producao.sincronizacao_empresas WHERE empresa=%s', (destino,)).fetchone():
            raise ValueError('O CNPJ já possui dados sincronizados. Migração bloqueada para não sobrescrever.')
        if remoto.execute('SELECT 1 FROM crm_producao.estado_licencas WHERE empresa=%s', (destino,)).fetchone():
            raise ValueError('O CNPJ já possui licenças próprias. Migração bloqueada.')
        if remoto.execute('SELECT 1 FROM crm_producao.backups_sqlite WHERE empresa=%s', (destino,)).fetchone():
            raise ValueError('O CNPJ já possui backups próprios. Migração bloqueada.')
        if aparelhos_ativos_locais:
            licenca = remoto.execute('SELECT estado FROM crm_producao.estado_licencas WHERE empresa=%s', (origem,)).fetchone()
            estado = licenca[0] if licenca else {}
            if isinstance(estado, str):
                estado = json.loads(estado)
            ativos = {r[0] for r in estado.get('aparelhos', []) if r[1] == 1}
            if not set(aparelhos_ativos_locais).issubset(ativos):
                raise ValueError('Há ativações locais ainda não reconhecidas no servidor. Migração interrompida para preservar as licenças.')
        catalogo = remoto.execute('SELECT documento,nome,sal,senha_hash,segredo_licenca,plano '
                                 'FROM crm_producao.catalogo_empresas WHERE documento=%s', (origem,)).fetchone()
        if not catalogo:
            raise ValueError('Cadastro remoto do CPF ausente. Migração interrompida.')
        catalogo_destino = remoto.execute('SELECT documento,nome,sal,senha_hash,segredo_licenca,plano '
                                         'FROM crm_producao.catalogo_empresas WHERE documento=%s', (destino,)).fetchone()
        if hash_local_esperado is not None and snapshot[1] != hash_local_esperado:
            raise ValueError('Windows e servidor possuem dados diferentes. Faça backup dos dois e concilie antes de migrar.')
        documento = desempacotar(snapshot[2], origem)
        if impressao(documento) != snapshot[1]:
            raise ValueError('A base remota não passou na conferência de integridade.')
        documento['empresa'] = destino
        registro = {'versao':1,'origem':origem,'destino':destino,
                    'hash_origem':snapshot[1], 'hash_destino':impressao(documento),
                    'catalogo':list(catalogo),
                    'catalogo_cnpj_anterior':list(catalogo_destino) if catalogo_destino else None}
        backups = remoto.execute('SELECT id,nome_arquivo,conteudo FROM crm_producao.backups_sqlite '
                                 'WHERE empresa=%s ORDER BY id', (origem,)).fetchall()
        copias = [(f'migrado-{i}-{nome}',converter_backup_alencarsoft(dados,registro))
                  for i,nome,dados in backups]
        remoto.execute('INSERT INTO crm_producao.sincronizacao_empresas '
                       '(empresa,versao,hash_dados,conteudo) VALUES(%s,%s,%s,%s)',
                       (destino,snapshot[0],registro['hash_destino'],empacotar(documento)))
        remoto.execute('INSERT INTO crm_producao.estado_licencas(empresa,estado) '
                       'SELECT %s,estado FROM crm_producao.estado_licencas WHERE empresa=%s', (destino,origem))
        novo_catalogo = (destino,'ALENCARSOFT',*catalogo[2:])
        remoto.execute('''INSERT INTO crm_producao.catalogo_empresas
            (documento,nome,sal,senha_hash,segredo_licenca,plano) VALUES(%s,%s,%s,%s,%s,%s)
            ON CONFLICT(documento) DO UPDATE SET nome=excluded.nome,sal=excluded.sal,
            senha_hash=excluded.senha_hash,segredo_licenca=excluded.segredo_licenca,
            plano=excluded.plano,atualizado_em=now()''', novo_catalogo)
        for nome,dados in copias:
            remoto.execute('INSERT INTO crm_producao.backups_sqlite(empresa,nome_arquivo,conteudo) VALUES(%s,%s,%s)',
                           (destino,nome,dados))
        remoto.execute('INSERT INTO crm_producao.migracoes_documentos(origem,destino,dados) VALUES(%s,%s,%s::jsonb)',
                       (origem,destino,json.dumps(registro)))
        # Protege contra executáveis antigos que ainda tentem escrever no CPF.
        remoto.execute('''CREATE OR REPLACE FUNCTION crm_producao.proteger_documento_migrado()
            RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
              IF EXISTS(SELECT 1 FROM crm_producao.migracoes_documentos
                        WHERE origem=(to_jsonb(NEW)->>TG_ARGV[0])) THEN
                RAISE EXCEPTION 'Documento migrado. Atualize o CRM para usar o CNPJ.';
              END IF;
              RETURN NEW;
            END $$''')
        for tabela,coluna in (('catalogo_empresas','documento'),('sincronizacao_empresas','empresa'),
                              ('estado_licencas','empresa'),('backups_sqlite','empresa')):
            remoto.execute(f'DROP TRIGGER IF EXISTS proteger_documento_migrado ON crm_producao.{tabela}')
            remoto.execute(f'''CREATE TRIGGER proteger_documento_migrado BEFORE INSERT OR UPDATE
                ON crm_producao.{tabela} FOR EACH ROW EXECUTE FUNCTION
                crm_producao.proteger_documento_migrado('{coluna}')''')
    return registro


def backup_migracao_local(caminho):
    from pathlib import Path
    from datetime import datetime, timezone
    import uuid
    caminho = Path(caminho)
    pasta = caminho.parent / 'backup_migracao_cnpj'
    pasta.mkdir(exist_ok=True)
    nome = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]+'-'+caminho.name+'.db'
    destino = pasta/nome
    with closing(sqlite3.connect(caminho.resolve().as_uri()+'?mode=ro',uri=True)) as origem:
        with closing(sqlite3.connect(destino)) as copia:
            origem.backup(copia)
            if copia.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                raise ValueError('A cópia de segurança local falhou. Migração interrompida.')
    return str(destino)


def aplicar_migracao_alencarsoft(configuradas, caminho_cadastro, registro):
    from pathlib import Path
    origem, destino = CPF_ALENCARSOFT, CNPJ_ALENCARSOFT
    if registro.get('origem') != origem or registro.get('destino') != destino or registro.get('versao') != 1:
        raise ValueError('Registro de migração inválido.')
    resultado = {d:dict(c) for d,c in configuradas.items()}
    if origem in resultado and destino in resultado:
        raise ValueError('Mantenha um único bloco da ALENCARSOFT nos Secrets durante a migração.')
    config = resultado.get(origem) or resultado.get(destino)
    if not config:
        return resultado
    caminho = Path(config['banco']).resolve()
    if not caminho.is_file():
        raise ValueError('Banco original da ALENCARSOFT não encontrado. Migração local interrompida.')
    # Não torna uma base independente inacessível ao escolher o caminho dos Secrets.
    alternativa = Path(caminho_cadastro).parent / (destino+'.db')
    if alternativa.resolve() != caminho and alternativa.exists():
        raise ValueError('Há outro banco local para o CNPJ. Preserve os dois e confira antes da migração.')
    with closing(sqlite3.connect(caminho,timeout=10)) as banco:
        vinculo = banco.execute('SELECT documento FROM crm_empresa WHERE id=1').fetchone()
        if vinculo not in ((origem,),(destino,)):
            raise ValueError('Banco original vinculado a outra empresa. Migração interrompida.')
        if vinculo == (origem,):
            backup_migracao_local(caminho)
            with banco:
                banco.execute('BEGIN IMMEDIATE')
                converter_vinculo_alencarsoft(banco, registro)
    cadastro_path = Path(caminho_cadastro)
    if cadastro_path.is_file():
        with closing(sqlite3.connect(cadastro_path,timeout=10)) as cadastro:
            tabelas = {r[0] for r in cadastro.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            precisa = any(cadastro.execute('SELECT 1 FROM '+t+' WHERE documento=?',(origem,)).fetchone()
                          for t in ('empresas','catalogo_licencas','planos_comerciais') if t in tabelas)
            if precisa:
                backup_migracao_local(cadastro_path)
                cat = registro['catalogo']
                with cadastro:
                    cadastro.execute('BEGIN IMMEDIATE')
                    if 'empresas' in tabelas:
                        cadastro.execute('DELETE FROM empresas WHERE documento IN (?,?)',(origem,destino))
                        # A linha do CNPJ nos Secrets mantém seu banco original; não criamos outro banco.
                    if 'catalogo_licencas' in tabelas:
                        cadastro.execute('DELETE FROM catalogo_licencas WHERE documento IN (?,?)',(origem,destino))
                        cadastro.execute('INSERT INTO catalogo_licencas VALUES(?,?,?)',(destino,'ALENCARSOFT',cat[4]))
                    if 'planos_comerciais' in tabelas:
                        cadastro.execute('DELETE FROM planos_comerciais WHERE documento IN (?,?)',(origem,destino))
                        cadastro.execute('INSERT INTO planos_comerciais VALUES(?,?)',(destino,cat[5]))
    config = dict(config)
    config['nome'] = 'ALENCARSOFT'
    config['segredo_licenca'] = registro['catalogo'][4]
    resultado.pop(origem,None)
    resultado[destino] = config
    return resultado


def carregar_migracao_instalacao(configuradas, caminho_cadastro, conectar):
    """Somente uma migração já confirmada no servidor pode modificar a instalação."""
    from pathlib import Path
    if not ({CPF_ALENCARSOFT,CNPJ_ALENCARSOFT} & set(configuradas)):
        return configuradas, False
    recibo = Path(caminho_cadastro).parent/'migracao_alencarsoft_confirmada.json'
    registro = None
    if recibo.is_file():
        registro = json.loads(recibo.read_text(encoding='utf-8'))
    else:
        try:
            with conectar() as remoto:
                registro = consultar_migracao_alencarsoft(remoto)
        except Exception:
            return configuradas, False
    if registro is None:
        return configuradas, False
    # Recibo permite retomar após falha local ou sem internet; contém segredo de licença,
    # como o cadastro local. Não é um relatório a compartilhar.
    recibo.parent.mkdir(parents=True,exist_ok=True)
    import uuid
    temporario = recibo.with_name(recibo.name+'.'+uuid.uuid4().hex+'.tmp')
    temporario.write_text(json.dumps(registro),encoding='utf-8')
    temporario.replace(recibo)
    return aplicar_migracao_alencarsoft(configuradas,caminho_cadastro,registro), True
