from contextlib import closing
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
import sqlite3
import pandas as pd
import base64
from datetime import datetime, date, timedelta
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
import io
import datetime as dt
import hashlib
import hmac
import secrets
import uuid
import string
import unicodedata
import json
import re
import html
from urllib.request import Request, urlopen
from urllib.parse import urlencode, urlparse
from PIL import Image, ImageOps

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="CRM Comércio", layout="wide", page_icon="🛍️")

# --- CONEXÃO E FUNÇÕES DE SUPORTE ---
import threading
import tempfile
import os
import time

# Cada empresa cadastrada na configuração do servidor usa um banco próprio.
try:
    empresas_config = st.secrets.get("empresas", {})
except FileNotFoundError:
    empresas_config = {}

PASTA_EMPRESAS = os.path.realpath("crm_empresas")
BANCO_CADASTRO_EMPRESAS = os.path.join(PASTA_EMPRESAS, "cadastro.sqlite3")


def hash_senha_empresa(senha, sal):
    return hashlib.scrypt(senha.encode(), salt=bytes.fromhex(sal), n=16384, r=8, p=1).hex()


def ler_empresas_cadastradas():
    if not os.path.isfile(BANCO_CADASTRO_EMPRESAS):
        return {}
    with sqlite3.connect(BANCO_CADASTRO_EMPRESAS) as cadastro:
        registros = cadastro.execute(
            "SELECT documento, nome, sal, senha_hash, segredo_licenca FROM empresas"
        ).fetchall()
    return {
        doc: dict(nome=nome, banco=os.path.join(PASTA_EMPRESAS, f"{doc}.db"),
                  sal=sal, senha_hash=senha_hash, segredo_licenca=segredo)
        for doc, nome, sal, senha_hash, segredo in registros
    }


def cadastrar_empresa(documento, nome, senha, empresas_existentes):
    if not re.fullmatch(r"[0-9]{11}|[0-9]{14}", documento) or not nome.strip():
        raise ValueError("Informe o nome e um CPF de 11 dígitos ou CNPJ de 14 dígitos.")
    if len(senha) < 16:
        raise ValueError("A senha do administrador precisa ter pelo menos 16 caracteres.")
    if documento in empresas_existentes:
        raise ValueError("Já existe uma empresa com esse documento.")
    banco = os.path.join(PASTA_EMPRESAS, f"{documento}.db")
    if os.path.lexists(banco) or any(
        os.path.realpath(e["banco"]) == banco for e in empresas_existentes.values()
    ):
        raise ValueError("Já existe um banco associado a esse documento.")
    sal = secrets.token_hex(16)
    os.makedirs(PASTA_EMPRESAS, exist_ok=True)
    with sqlite3.connect(BANCO_CADASTRO_EMPRESAS, timeout=30) as cadastro:
        cadastro.execute("BEGIN IMMEDIATE")
        cadastro.execute("""
            CREATE TABLE IF NOT EXISTS empresas (
                documento TEXT PRIMARY KEY, nome TEXT NOT NULL, sal TEXT NOT NULL,
                senha_hash TEXT NOT NULL, segredo_licenca TEXT NOT NULL
            )
        """)
        try:
            cadastro.execute(
                "INSERT INTO empresas VALUES (?, ?, ?, ?, ?)",
                (documento, nome.strip(), sal, hash_senha_empresa(senha, sal), secrets.token_hex(32)),
            )
        except sqlite3.IntegrityError as erro:
            raise ValueError("Já existe uma empresa com esse documento.") from erro


DOCUMENTO_ALENCARSOFT = "95451161100"
empresa_doc = ""
empresa_config = {}
banco_empresa = "crm_comercio.db"
if not empresas_config:
    st.error("Configure as empresas nos Secrets do CRM principal.")
    st.stop()
if empresas_config:
    caminhos = []
    senhas = []
    for documento, configuracao in empresas_config.items():
        if (
            not re.fullmatch(r"[0-9]{11}|[0-9]{14}", documento)
            or not configuracao.get("nome")
            or not configuracao.get("banco")
            or len(configuracao.get("senha_admin", "")) < 16
        ):
            st.error("Configuração de empresas inválida. Contate o responsável pelo CRM.")
            st.stop()
        caminhos.append(os.path.realpath(configuracao["banco"]))
        senhas.append(configuracao["senha_admin"])
    if len(set(caminhos)) != len(caminhos) or len(set(senhas)) != len(senhas):
        st.error("Cada empresa precisa de um banco e uma senha administrativa exclusivos.")
        st.stop()

    empresas_config = dict(empresas_config)
    cadastradas = ler_empresas_cadastradas()
    bancos_cadastrados = {os.path.realpath(e["banco"]) for e in cadastradas.values()}
    if empresas_config.keys() & cadastradas.keys() or bancos_cadastrados.intersection(caminhos):
        st.error("Há empresas ou bancos duplicados entre os Secrets e o painel.")
        st.stop()
    empresas_config.update(cadastradas)

    empresa_doc = st.session_state.get("_empresa_doc", "")
    if empresa_doc not in empresas_config:
        st.title("CRM Comércio")
        with st.form("selecionar_empresa"):
            documento_padrao = (
                DOCUMENTO_ALENCARSOFT
                if DOCUMENTO_ALENCARSOFT in empresas_config
                and not st.session_state.get("_trocando_empresa")
                else ""
            )
            documento = st.text_input("CNPJ ou CPF da empresa", value=documento_padrao)
            if st.form_submit_button("Continuar"):
                documento = re.sub(r"[^0-9]", "", documento)
                if documento in empresas_config:
                    st.session_state["_empresa_doc"] = documento
                    st.rerun()
                st.error("Empresa não cadastrada neste CRM.")
        st.stop()

    empresa_config = empresas_config[empresa_doc]
    banco_empresa = os.path.realpath(empresa_config["banco"])
    st.sidebar.caption(empresa_config["nome"])
    if st.sidebar.button("Trocar empresa"):
        st.session_state.clear()
        st.session_state["_trocando_empresa"] = True
        st.query_params.clear()
        st.rerun()

# A lista em Secrets usa os mesmos documentos do cadastro de empresas.
configuracao_backup_producao = st.secrets.get("crm_producao", {})
documentos_backup_automatico = configuracao_backup_producao.get("empresas_backup_automatico", [])
if not isinstance(documentos_backup_automatico, list):
    documentos_backup_automatico = []
empresas_backup_automatico = {
    doc for doc in documentos_backup_automatico
    if isinstance(doc, str) and doc in empresas_config
}


nome_empresa_padrao = empresa_config.get("nome", "REY DA CEBOLA")
doc_empresa_padrao = empresa_doc or "19417439000142"
fone_empresa_padrao = "" if empresa_doc else "(99) 98501-6050"
endereco_empresa_padrao = "" if empresa_doc else "RUA CAIPIRA, Nº 174"
inscricao_empresa_padrao = "" if empresa_doc else "12.426.725-4"


def credencial_admin_principal(login, senha):
    if empresa_doc:
        if login != "administrador":
            return False
        if "senha_hash" in empresa_config:
            return hmac.compare_digest(
                hash_senha_empresa(str(senha), empresa_config["sal"]), empresa_config["senha_hash"]
            )
        return hmac.compare_digest(str(senha).encode(), empresa_config["senha_admin"].encode())
    return (login, senha) in {("administrador", "admin"), ("admin", "123456")}


def hash_chave_licenca(documento, plano, limite, configuracao_destino=None):
    dados = f"{documento}REY_CEBOLA_2026{plano}{limite}".encode()
    if empresa_doc:
        configuracao = empresa_config if configuracao_destino is None else configuracao_destino
        segredo = configuracao.get("segredo_licenca") or configuracao["senha_admin"]
        return hmac.new(segredo.encode(), dados, hashlib.sha256).hexdigest().upper()
    return hashlib.md5(dados).hexdigest().upper()


PLANOS_LICENCA = {"TESTE": 7, "MENSAL": 30, "ANUAL": 365}


def assinatura_chave_unica(documento, corpo, configuracao):
    segredo = configuracao.get("segredo_licenca") or configuracao["senha_admin"]
    return hmac.new(segredo.encode(), f"{documento}:{corpo}".encode(), hashlib.sha256).hexdigest()[:32].upper()


def emitir_chave_unica(documento, plano, limite, configuracao):
    corpo = f"CRM2-{plano}-{limite}D-{uuid.uuid4().hex.upper()}"
    return f"{corpo}-{assinatura_chave_unica(documento, corpo, configuracao)}"


def aplicar_chave_unica(conexao, documento, dispositivo, chave, alterar_limite, configuracao):
    partes = re.fullmatch(r"CRM2-(TESTE|MENSAL|ANUAL)-([1-9][0-9]?)D-([0-9A-F]{32})-([0-9A-F]{32})", chave)
    if not partes:
        raise ValueError("Chave inválida. Solicite uma nova chave de uso único.")
    plano, limite, identificador, assinatura = partes.groups()
    limite = int(limite)
    corpo = chave.rsplit("-", 1)[0]
    if limite > 50 or not hmac.compare_digest(assinatura, assinatura_chave_unica(documento, corpo, configuracao)):
        raise ValueError("Chave inválida para esta empresa.")

    with conexao:
        conexao.execute("BEGIN IMMEDIATE")
        conexao.execute("CREATE TABLE IF NOT EXISTS chaves_licenca_usadas (identificador TEXT PRIMARY KEY)")
        if conexao.execute("SELECT 1 FROM chaves_licenca_usadas WHERE identificador = ?", (identificador,)).fetchone():
            raise ValueError("Chave já utilizada.")
        registro = conexao.execute(
            "SELECT ativado, limite_dispositivos FROM empresas_dispositivos WHERE device_id = ?",
            (dispositivo,),
        ).fetchone()
        if registro is None:
            raise ValueError("Dispositivo não encontrado.")
        registrado, limite_atual = registro
        if registrado and not alterar_limite:
            limite = limite_atual
        ativos = conexao.execute("SELECT COUNT(*) FROM empresas_dispositivos WHERE ativado = 1").fetchone()[0]
        if ativos + (not registrado) > limite:
            raise ValueError("O limite da licença é menor que a quantidade de dispositivos necessária.")

        dias = PLANOS_LICENCA[plano]
        vencimento = (datetime.now(dt.timezone.utc) + timedelta(days=dias)).isoformat(timespec="seconds")
        conexao.execute("UPDATE empresas_dispositivos SET limite_dispositivos = ?", (limite,))
        conexao.execute(
            """UPDATE empresas_dispositivos
               SET ativado = 1, dias_licenca = ?, licenca_expira_em = ?
               WHERE device_id = ?""",
            (dias, vencimento, dispositivo),
        )
        conexao.execute("INSERT INTO chaves_licenca_usadas VALUES (?)", (identificador,))


def vincular_banco_empresa(conexao, documento):
    with conexao:
        conexao.execute("BEGIN IMMEDIATE")
        conexao.execute("""
            CREATE TABLE IF NOT EXISTS crm_empresa (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                documento TEXT NOT NULL
            )
        """)
        conexao.execute("INSERT OR IGNORE INTO crm_empresa VALUES (1, ?)", (documento,))
        if conexao.execute("SELECT documento FROM crm_empresa WHERE id = 1").fetchone() != (documento,):
            raise ValueError("O banco configurado pertence a outra empresa.")


@st.cache_resource(show_spinner=False)
def _sqlite_init_lock():
    # Evita que sessões simultâneas tentem inicializar o modo WAL ao mesmo tempo.
    return threading.RLock()


def get_connection():
    """Abre uma conexão por execução, inclusive nos reruns da mesma sessão."""
    conexao = sqlite3.connect(
        banco_empresa,
        timeout=60.0,
        check_same_thread=False,
        isolation_level="DEFERRED"
    )
    conexao.execute("PRAGMA busy_timeout = 60000")
    conexao.execute("PRAGMA foreign_keys = ON")
    with _sqlite_init_lock():
        # WAL é habilitado uma vez no arquivo; não repetir a alteração a cada rerun.
        modo = conexao.execute("PRAGMA journal_mode").fetchone()[0]
        if str(modo).lower() != "wal":
            conexao.execute("PRAGMA journal_mode = WAL")
    conexao.execute("PRAGMA synchronous = NORMAL")
    return conexao

def conectar_supabase_producao():
    try:
        import psycopg
    except ImportError as erro:
        raise ValueError("Adicione psycopg[binary]>=3.2,<4 ao requirements.txt e publique novamente.") from erro
    configuracao = st.secrets.get("crm_producao", {})
    url = str(configuracao.get("database_url", "")).strip()
    senha_separada = configuracao.get("password")
    if senha_separada is not None:
        # A URI original do painel pode ser usada sem inserir a senha nela.
        url = url.replace("[YOUR-PASSWORD]", "")

    if not url.startswith(("postgresql://", "postgres://")):
        raise ValueError("Configure database_url no bloco crm_producao dos Secrets.")
    if "[YOUR-PASSWORD]" in url or "COLE_A_" in url:
        raise ValueError("A conexão ainda contém um texto de exemplo. Substitua [YOUR-PASSWORD] pela senha do banco nos Secrets.")
    try:
        parametros = psycopg.conninfo.conninfo_to_dict(url)
        if senha_separada is not None:
            parametros["password"] = str(senha_separada)
        parametros.update(sslmode="require", connect_timeout=10)
        # Configura o prazo após conectar para compatibilidade com o pooler.
        parametros.pop("options", None)
        conexao = psycopg.connect(**parametros)
        try:
            with conexao.transaction():
                conexao.execute("SET statement_timeout = '30s'")
        except Exception:
            conexao.close()
            raise
        return conexao
    except psycopg.Error as erro:
        texto = str(erro).lower()
        if "unsupported" in texto and ("parameter" in texto or "option" in texto):
            mensagem = "O servidor recusou um parâmetro da conexão. Copie a URI original de Session pooler e use password separado nos Secrets."
        elif "circuit breaker" in texto or "too many authentication" in texto:
            mensagem = "O Supabase suspendeu temporariamente as tentativas após falhas de autenticação. Confira a senha e aguarde alguns minutos antes de testar."
        elif "tenant or user not found" in texto:
            mensagem = "O Supabase não reconheceu o usuário ou projeto. Copie novamente a URI de Session pooler do projeto de produção."
        elif erro.sqlstate == "28P01" or "password authentication failed" in texto:
            mensagem = "O Supabase recusou a senha do banco. Confira a senha e substitua @ por %40 apenas dentro da senha na URI."
        elif any(trecho in texto for trecho in ["resolve", "translate host", "name or service not known"]):
            mensagem = "O endereço do servidor não foi encontrado. Confira se a URI foi copiada inteira e se o @ que separa senha e servidor foi mantido."
        elif any(trecho in texto for trecho in ["timeout", "timed out", "network is unreachable", "connection refused"]):
            mensagem = "O servidor não respondeu. Confira se o projeto está ativo e se a conexão selecionada é Session pooler."
        elif "ssl" in texto or "certificate" in texto:
            mensagem = "Falha na conexão SSL com o banco. Confira a configuração do projeto."
        else:
            codigo = erro.sqlstate or ""
            mensagem = "Não foi possível abrir a conexão com o banco."
            if re.fullmatch(r"[0-9A-Z]{5}", codigo):
                mensagem += f" Código PostgreSQL: {codigo}."
        raise ValueError(mensagem) from None


def validar_backup_piloto(dados, documento):
    if not dados.startswith(b"SQLite format 3\x00"):
        raise ValueError("Selecione um backup SQLite do CRM.")
    with tempfile.TemporaryDirectory(prefix="crm_validar_piloto_") as pasta:
        caminho = os.path.join(pasta, "backup.db")
        with open(caminho, "wb") as arquivo:
            arquivo.write(dados)
        banco = sqlite3.connect(caminho)
        try:
            banco.execute("PRAGMA query_only = ON")
            if banco.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise ValueError("O backup não passou na verificação de integridade.")
            tabela = banco.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='crm_empresa'").fetchone()
            if not tabela or banco.execute("SELECT documento FROM crm_empresa WHERE id=1").fetchone() != (documento,):
                raise ValueError("O backup pertence a outra empresa.")
        finally:
            banco.close()


def gravar_backup_piloto(dados, documento, nome_arquivo):
    validar_backup_piloto(dados, documento)
    with conectar_supabase_producao() as remoto:
        registro = remoto.execute(
            """INSERT INTO crm_producao.backups_sqlite (empresa, nome_arquivo, conteudo)
               VALUES (%s, %s, %s) RETURNING id""",
            (documento, os.path.basename(nome_arquivo), dados),
        ).fetchone()[0]
        recuperado = bytes(remoto.execute(
            "SELECT conteudo FROM crm_producao.backups_sqlite WHERE id=%s AND empresa=%s",
            (registro, documento),
        ).fetchone()[0])
        if recuperado != dados:
            raise ValueError("A cópia recuperada difere do arquivo enviado.")


def copiar_banco_sqlite(origem, destino):
    limite = time.monotonic() + 30
    def progresso(status, restantes, total):
        if time.monotonic() > limite:
            raise TimeoutError("O banco está ocupado. Feche as outras sessões e tente novamente.")
    origem.backup(destino, pages=256, progress=progresso, sleep=0.1)


def gerar_backup_sqlite(conexao):
    if conexao.in_transaction:
        raise ValueError("Há alterações pendentes no banco. Conclua a operação antes de gerar o backup.")
    with tempfile.TemporaryDirectory(prefix="crm_backup_") as pasta:
        caminho = os.path.join(pasta, "backup.db")
        copia = sqlite3.connect(caminho)
        try:
            copiar_banco_sqlite(conexao, copia)
            if copia.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise ValueError("A cópia do banco não passou na verificação de integridade.")
        finally:
            copia.close()
        with open(caminho, "rb") as arquivo:
            return arquivo.read()


def restaurar_backup_sqlite(conexao, dados, preservar_copia):
    if not dados.startswith(b"SQLite format 3\x00"):
        raise ValueError("O arquivo não é um banco SQLite válido.")
    if conexao.in_transaction:
        raise ValueError("Há alterações pendentes. Conclua a operação antes de restaurar.")
    with tempfile.TemporaryDirectory(prefix="crm_restauracao_") as pasta:
        caminho = os.path.join(pasta, "restaurar.db")
        with open(caminho, "wb") as arquivo:
            arquivo.write(dados)
        origem = sqlite3.connect(caminho)
        try:
            origem.execute("PRAGMA query_only = ON")
            if origem.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise ValueError("Backup incompleto ou corrompido. Os dados atuais foram mantidos.")
            tabelas = {r[0] for r in origem.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"produtos", "empresas_dispositivos"}.issubset(tabelas):
                raise ValueError("O arquivo não contém as tabelas do CRM. Pode ser um backup incompleto, como o arquivo de 4 KB. Os dados atuais foram mantidos.")
            backup_legado = empresa_doc and "crm_empresa" not in tabelas
            if backup_legado:
                documentos = {
                    re.sub(r"[^0-9]", "", str(cnpj or ""))
                    for (cnpj,) in origem.execute("SELECT DISTINCT cnpj FROM empresas_dispositivos")
                }
                documentos.discard("")
                if empresa_doc != "19417439000142" or documentos != {empresa_doc}:
                    raise ValueError("O backup antigo precisa conter apenas o CNPJ da REY DA CEBOLA.")
            elif empresa_doc and origem.execute(
                "SELECT documento FROM crm_empresa WHERE id = 1"
            ).fetchone() != (empresa_doc,):
                raise ValueError("Selecione um backup gerado para esta empresa.")
            colunas = {r[1] for r in origem.execute("PRAGMA table_info(produtos)")}
            if not {"id", "produto"}.issubset(colunas):
                raise ValueError("A tabela de produtos do backup é incompatível com este sistema.")
            if backup_legado:
                # Identifica a cópia temporária antes de restaurá-la no modo multiempresa.
                origem.execute("PRAGMA query_only = OFF")
                vincular_banco_empresa(origem, empresa_doc)
                origem.execute("PRAGMA query_only = ON")
                tabelas.add("crm_empresa")
            if empresa_doc and conexao.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'chaves_licenca_usadas'"
            ).fetchone():
                usadas = conexao.execute("SELECT identificador FROM chaves_licenca_usadas").fetchall()
                origem.execute("PRAGMA query_only = OFF")
                with origem:
                    origem.execute("CREATE TABLE IF NOT EXISTS chaves_licenca_usadas (identificador TEXT PRIMARY KEY)")
                    origem.executemany("INSERT OR IGNORE INTO chaves_licenca_usadas VALUES (?)", usadas)
                origem.execute("PRAGMA query_only = ON")
            # Os vínculos e limites de licença pertencem à instalação atual.
            colunas_dispositivos = (
                "device_id, nome_empresa, cnpj, ie, fone, endereco, "
                "ativado, dias_licenca, limite_dispositivos, licenca_expira_em"
            )
            dispositivos = conexao.execute(
                f"SELECT {colunas_dispositivos} FROM empresas_dispositivos"
            ).fetchall()
            origem.execute("PRAGMA query_only = OFF")
            with origem:
                colunas_origem = {r[1] for r in origem.execute("PRAGMA table_info(empresas_dispositivos)")}
                for coluna, tipo in (
                    ("dias_licenca", "INTEGER DEFAULT 30"),
                    ("limite_dispositivos", "INTEGER DEFAULT 1"),
                    ("licenca_expira_em", "TEXT"),
                ):
                    if coluna not in colunas_origem:
                        origem.execute(f"ALTER TABLE empresas_dispositivos ADD COLUMN {coluna} {tipo}")
                origem.execute("DELETE FROM empresas_dispositivos")
                origem.executemany(
                    f"INSERT INTO empresas_dispositivos ({colunas_dispositivos}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    dispositivos,
                )
            # Guarda a cópia de segurança ANTES de alterar o banco atual.
            seguranca = gerar_backup_sqlite(conexao)
            preservar_copia(seguranca)
            # A API do SQLite substitui o conteúdo mantendo as conexões/WAL coerentes.
            copiar_banco_sqlite(origem, conexao)
            return tabelas
        finally:
            origem.close()


conn = get_connection()
if not empresa_doc and conn.execute(
    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'crm_empresa'"
).fetchone():
    conn.close()
    st.error("Este banco exige a configuração de empresas no servidor.")
    st.stop()
if empresa_doc:
    try:
        vincular_banco_empresa(conn, empresa_doc)
    except ValueError as erro:
        conn.close()
        st.error(str(erro))
        st.stop()

def carregar_dados(query):
    # pandas.read_sql_query pode executar rollback na conexão quando a consulta
    # falha. Uma leitura opcional não deve desfazer a transação de uma venda.
    cursor_leitura = conn.cursor()
    try:
        cursor_leitura.execute(query)
        colunas = [coluna[0] for coluna in (cursor_leitura.description or [])]
        return pd.DataFrame.from_records(cursor_leitura.fetchall(), columns=colunas)
    except sqlite3.Error:
        return pd.DataFrame()
    finally:
        cursor_leitura.close()

def carregar_coluna(tabela, coluna):
    cursor = conn.cursor()
    try:
        cursor.execute(f"PRAGMA table_info({tabela})")
        cols = [col[1] for col in cursor.fetchall()]
        col_alvo = coluna if coluna in cols else (cols[1] if len(cols) > 1 else coluna)
        df = carregar_dados(f"SELECT DISTINCT TRIM({col_alvo}) as {col_alvo} FROM {tabela} WHERE {col_alvo} IS NOT NULL AND {col_alvo} != ''")
        if not df.empty:
            return df[col_alvo].tolist()
    except Exception:
        pass
    return []

def salvar_simples(tabela, coluna, valor):
    cursor = conn.cursor()
    cursor.execute(f"CREATE TABLE IF NOT EXISTS {tabela} (id INTEGER PRIMARY KEY AUTOINCREMENT, {coluna} TEXT)")
    cursor.execute(f"INSERT INTO {tabela} ({coluna}) VALUES (?)", (valor,))
    conn.commit()

def salvar_cliente_completo(nome, tel, doc, endereco, cidade):
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente TEXT, nome TEXT, cpf TEXT, endereco TEXT, email TEXT, fone TEXT, cidade TEXT
            )
        """)
        cursor.execute("""
            INSERT INTO clientes (cliente, nome, cpf, endereco, fone, cidade)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (nome, nome, doc, endereco, tel, cidade))
        conn.commit()
        return True, f"Cliente '{nome}' cadastrado com sucesso!"
    except Exception as e:
        return False, f"Erro ao cadastrar cliente: {e}"

def adequar_banco_e_migrar():
    try:
        cursor = conn.cursor()
        # Reserve a escrita antes de inspecionar o esquema. Outra sessão
        # só inicia a migração depois que esta concluir ou fizer rollback.
        cursor.execute("BEGIN IMMEDIATE")
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS empresas_dispositivos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT UNIQUE,
                nome_empresa TEXT,
                cnpj TEXT,
                ie TEXT,
                fone TEXT,
                endereco TEXT,
                ativado INTEGER DEFAULT 0,
                dias_licenca INTEGER DEFAULT 30,
                limite_dispositivos INTEGER DEFAULT 1
            )
        """)
        
        # TABELA DE CHAVES PIX MULTIPLAS
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chaves_pix (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo TEXT,
                chave TEXT,
                favorecido TEXT,
                cidade TEXT,
                padrao INTEGER DEFAULT 0
            )
        """)

        # Configuração básica da NFC-e; segredos (A1/CSC) não ficam no banco.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS config_nfce (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                uf TEXT DEFAULT 'MA',
                ambiente TEXT DEFAULT 'Homologacao',
                serie TEXT DEFAULT '1',
                proximo_numero INTEGER DEFAULT 1,
                modelo TEXT DEFAULT '65',
                atualizado_em TEXT
            )
        """)
        cursor.execute("""
            INSERT OR IGNORE INTO config_nfce
                (id, uf, ambiente, serie, proximo_numero, modelo)
            VALUES (1, 'MA', 'Homologacao', '1', 1, '65')
        """)

        cursor.execute("PRAGMA table_info(empresas_dispositivos)")
        cols_emp = [col[1] for col in cursor.fetchall()]
        if "ativado" not in cols_emp:
            cursor.execute("ALTER TABLE empresas_dispositivos ADD COLUMN ativado INTEGER DEFAULT 0")
        if "dias_licenca" not in cols_emp:
            cursor.execute("ALTER TABLE empresas_dispositivos ADD COLUMN dias_licenca INTEGER DEFAULT 30")
        if "licenca_expira_em" not in cols_emp:
            cursor.execute("ALTER TABLE empresas_dispositivos ADD COLUMN licenca_expira_em TEXT")
        if "limite_dispositivos" not in cols_emp:
            cursor.execute("ALTER TABLE empresas_dispositivos ADD COLUMN limite_dispositivos INTEGER DEFAULT 1")

        # Adequa produtos sem apagar nem recriar a tabela existente.
        cursor.execute("CREATE TABLE IF NOT EXISTS produtos (id INTEGER PRIMARY KEY AUTOINCREMENT, produto TEXT)")
        cursor.execute("PRAGMA table_info(produtos)")
        cols_produtos = {col[1] for col in cursor.fetchall()}
        colunas_produtos = {
            "fornecedor": "TEXT", "grupo": "TEXT", "preco_compra": "REAL",
            "preco_venda": "REAL", "venda": "REAL", "quantidade": "REAL",
            "estoque": "REAL", "codigo": "TEXT", "valor_compra": "REAL",
            "valor_venda": "REAL", "unidade": "TEXT"
        }
        for coluna, tipo in colunas_produtos.items():
            if coluna not in cols_produtos:
                cursor.execute(f"ALTER TABLE produtos ADD COLUMN {coluna} {tipo}")

        cursor.execute("CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente TEXT)")
        for col in ["cliente", "nome", "cpf", "doc", "endereco", "email", "fone", "telefone", "cidade", "senha"]:
            try: cursor.execute(f"ALTER TABLE clientes ADD COLUMN {col} TEXT")
            except Exception: pass

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vendas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente TEXT, produto TEXT, data TEXT
            )
        """)
        for col in ["fornecedor", "grupo", "quantidade", "valor_venda", "valor_total", "forma_pagamento", "valor_recebido", "troco", "restante", "status", "tipo", "codigo", "codigo_venda", "vendedor"]:
            try: cursor.execute(f"ALTER TABLE vendas ADD COLUMN {col} TEXT")
            except Exception: pass

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pedidos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente TEXT, produto TEXT, fornecedor TEXT, grupo TEXT,
                quantidade REAL, valor_unitario REAL, valor_total REAL, status TEXT, data TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS caixa_sessoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT, data_abertura TEXT, data_fechamento TEXT,
                saldo_inicial REAL, saldo_final REAL, status TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS caixa_movimentacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT, sessao_id INTEGER, tipo TEXT,
                valor REAL, descricao TEXT, data TEXT
            )
        """)
        # Vincula cada movimento do caixa à venda que o originou.
        # A migração é compatível com bancos já existentes.
        cursor.execute("PRAGMA table_info(caixa_movimentacoes)")
        cols_mov_caixa = {col[1].casefold() for col in cursor.fetchall()}
        if "venda_id" not in cols_mov_caixa:
            cursor.execute("ALTER TABLE caixa_movimentacoes ADD COLUMN venda_id INTEGER")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS funcionarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT,
                cargo TEXT,
                salario REAL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pagamentos_funcionarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                colaborador TEXT,
                valor REAL,
                data_pagamento TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT,
                login TEXT UNIQUE,
                senha TEXT,
                cargo TEXT,
                perm_pdv INTEGER DEFAULT 1,
                perm_financeiro INTEGER DEFAULT 1,
                perm_registrar_venda INTEGER DEFAULT 1,
                perm_compras INTEGER DEFAULT 0,
                perm_cadastros INTEGER DEFAULT 1,
                perm_rh INTEGER DEFAULT 0,
                perm_usuarios INTEGER DEFAULT 0,
                perm_backup INTEGER DEFAULT 0,
                perm_contas_receber INTEGER DEFAULT 1,
                perm_estoque INTEGER DEFAULT 1,
                perm_configuracoes INTEGER DEFAULT 0
            )
        """)
        
        cursor.execute("PRAGMA table_info(usuarios)")
        cols_usr = [col[1] for col in cursor.fetchall()]
        colunas_necessarias_usr = {
            "usuario": "TEXT", "login": "TEXT", "senha": "TEXT", "cargo": "TEXT",
            "perm_pdv": "INTEGER DEFAULT 1", "perm_financeiro": "INTEGER DEFAULT 1",
            "perm_registrar_venda": "INTEGER DEFAULT 1", "perm_compras": "INTEGER DEFAULT 0",
            "perm_cadastros": "INTEGER DEFAULT 1", "perm_rh": "INTEGER DEFAULT 0",
            "perm_usuarios": "INTEGER DEFAULT 0", "perm_backup": "INTEGER DEFAULT 0",
            "perm_contas_receber": "INTEGER DEFAULT 1", "perm_estoque": "INTEGER DEFAULT 1",
            "perm_configuracoes": "INTEGER DEFAULT 0"
        }
        for coluna, tipo in colunas_necessarias_usr.items():
            if coluna not in cols_usr:
                try: cursor.execute(f"ALTER TABLE usuarios ADD COLUMN {coluna} {tipo}")
                except Exception: pass

        # Histórico de compras: criar/adequar sem apagar registros existentes.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS compras (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                produto TEXT, fornecedor TEXT, grupo TEXT,
                quantidade REAL, preco_compra REAL, preco_venda REAL,
                unidade TEXT, data TEXT
            )
        """)
        cursor.execute("PRAGMA table_info(compras)")
        cols_compras = [col[1] for col in cursor.fetchall()]
        colunas_compras = {
            "produto": "TEXT", "fornecedor": "TEXT", "grupo": "TEXT",
            "quantidade": "REAL", "preco_compra": "REAL", "preco_venda": "REAL",
            "unidade": "TEXT", "data": "TEXT"
        }
        for coluna, tipo in colunas_compras.items():
            if coluna not in cols_compras:
                cursor.execute(f"ALTER TABLE compras ADD COLUMN {coluna} {tipo}")

        conn.commit()
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        raise RuntimeError(f"Falha ao preparar o banco de dados do CRM: {e}") from e

adequar_banco_e_migrar()

def garantir_colunas_produtos(conexao=None):
    """Garante as colunas usadas pelo cadastro/estoque sem apagar dados."""
    conexao = conexao or conn
    colunas = {
        "codigo": "TEXT", "produto": "TEXT", "quantidade": "REAL DEFAULT 0",
        "valor_compra": "REAL DEFAULT 0", "valor_venda": "REAL DEFAULT 0",
        "grupo": "TEXT", "fornecedor": "TEXT", "unidade": "TEXT",
        "preco_compra": "REAL DEFAULT 0", "preco_venda": "REAL DEFAULT 0",
        "venda": "REAL DEFAULT 0", "estoque": "REAL DEFAULT 0",
        "imagem_produto": "BLOB", "imagem_creditos": "TEXT",
        "estoque_minimo": "REAL NOT NULL DEFAULT 0"
    }
    cur = conexao.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS produtos (id INTEGER PRIMARY KEY AUTOINCREMENT, produto TEXT)")
    existentes = {r[1] for r in cur.execute("PRAGMA table_info(produtos)").fetchall()}
    for nome, tipo in colunas.items():
        if nome not in existentes:
            cur.execute(f"ALTER TABLE produtos ADD COLUMN {nome} {tipo}")
    conexao.commit()


garantir_colunas_produtos(conn)




def garantir_forma_movimentacoes(conexao):
    colunas = {r[1] for r in conexao.execute("PRAGMA table_info(caixa_movimentacoes)")}
    if colunas and "forma_pagamento" not in colunas:
        conexao.execute("ALTER TABLE caixa_movimentacoes ADD COLUMN forma_pagamento TEXT")
        conexao.commit()


garantir_forma_movimentacoes(conn)


def resumo_recebimentos_caixa(conexao, sessao_id):
    cursor_resumo = conexao.execute("""
        SELECT m.*, v.forma_pagamento AS forma_venda
        FROM caixa_movimentacoes m LEFT JOIN vendas v ON v.id = m.venda_id
        WHERE m.sessao_id = ? AND COALESCE(m.estornado,0) = 0 ORDER BY m.id
    """, (int(sessao_id),))
    nomes = [c[0] for c in cursor_resumo.description]
    linhas = []
    totais = {"Dinheiro": 0.0, "Pix": 0.0, "Cartão Débito": 0.0,
              "Cartão Crédito": 0.0, "Não informado": 0.0}
    for registro in cursor_resumo.fetchall():
        mov = dict(zip(nomes, registro))
        tipo = str(mov.get('tipo') or '').strip().upper()
        forma = str(mov.get('forma_pagamento') or mov.get('forma_venda') or '').strip()
        if not forma:
            antiga = re.search(r"Venda PDV \((.*)\) por ", str(mov.get('descricao') or ''), re.I)
            forma = antiga.group(1) if antiga else ''
        normal = unicodedata.normalize('NFKD', forma).encode('ascii', 'ignore').decode().lower()
        # Uma promessa de pagamento não é um recebimento.
        if tipo == 'VENDA' and ('fiado' in normal or 'parcelado' in normal):
            continue
        if normal == 'dinheiro': categoria = 'Dinheiro'
        elif normal == 'pix': categoria = 'Pix'
        elif 'debito' in normal: categoria = 'Cartão Débito'
        elif 'credito' in normal: categoria = 'Cartão Crédito'
        else: categoria = 'Não informado'
        valor = float(mov.get('valor') or 0)
        if tipo in {'SAIDA', 'SAÍDA', 'SANGRIA', 'ESTORNO'}:
            valor = -abs(valor)
        totais[categoria] = round(totais[categoria] + valor, 2)
        linhas.append({"Forma de Pagamento": categoria, "Valor líquido (R$)": valor,
                       "Tipo": tipo, "Descrição": mov.get('descricao', '')})
    return totais, linhas


def moeda_historico_venda(valor):
    return "R$ " + f"{float(valor):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def gerar_pdf_vendas_periodo(empresa, filtros, resumo, total_valido, total_estornado, linhas):
    arquivo = io.BytesIO()
    estilos = getSampleStyleSheet()
    doc = SimpleDocTemplate(arquivo, pagesize=letter, leftMargin=48, rightMargin=48,
                            topMargin=48, bottomMargin=48, title="Relatório de vendas por período")
    conteudo = [
        Paragraph(html.escape(str(empresa)), estilos['Heading2']),
        Paragraph("Relatório de vendas por período", estilos['Title']),
        Spacer(1, 12),
    ]
    for rotulo, valor in filtros.items():
        conteudo.append(Paragraph(f"<b>{rotulo}:</b> {html.escape(str(valor))}", estilos['BodyText']))
    conteudo.extend([
        Spacer(1, 12),
        Paragraph(f"<b>Vendas válidas:</b> {moeda_historico_venda(total_valido)}", estilos['BodyText']),
        Paragraph(f"<b>Estornos:</b> {moeda_historico_venda(total_estornado)}", estilos['BodyText']),
        Paragraph(f"<b>Linhas de produtos:</b> {linhas}", estilos['BodyText']),
        Spacer(1, 12),
    ])
    dados = [["Forma de pagamento", "Vendas válidas", "Estornos"]]
    for forma, valido, estornado in resumo.itertuples(index=False, name=None):
        dados.append([Paragraph(html.escape(str(forma)), estilos['BodyText']),
                      moeda_historico_venda(valido), moeda_historico_venda(estornado)])
    tabela = Table(dados, colWidths=[264, 120, 120], repeatRows=1)
    tabela.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#10325a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#eef3f8'), colors.white]),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    conteudo.extend([tabela, Spacer(1, 12), Paragraph(
        "O relatório soma as linhas de produtos dos filtros selecionados. "
        "Vendas a prazo entram pelo valor vendido. O recebimento das parcelas é conferido no caixa.",
        estilos['BodyText'])])
    doc.build(conteudo)
    return arquivo.getvalue()


def gerar_pdf_estoque(empresa, produtos, filtros, reposicao=False):
    titulo = "Lista de reposição" if reposicao else "Relatório de estoque"
    arquivo = io.BytesIO()
    estilos = getSampleStyleSheet()
    doc = SimpleDocTemplate(arquivo, pagesize=letter, leftMargin=48, rightMargin=48,
                            topMargin=48, bottomMargin=48, title=titulo)
    conteudo = [
        Paragraph(html.escape(str(empresa)), estilos['Heading2']),
        Paragraph(titulo, estilos['Title']),
        Spacer(1, 10),
    ]
    for rotulo, valor in filtros.items():
        conteudo.append(Paragraph(f"<b>{rotulo}:</b> {html.escape(str(valor))}", estilos['BodyText']))
    conteudo.extend([
        Spacer(1, 10),
        Paragraph(f"Produtos listados: {len(produtos)}", estilos['BodyText']),
        Paragraph(f"Sem estoque: {int(produtos['Qtd. Estoque'].eq(0).sum())}", estilos['BodyText']),
        Paragraph(f"Saldo negativo: {int(produtos['Qtd. Estoque'].lt(0).sum())}", estilos['BodyText']),
        Spacer(1, 10),
    ])
    def quadro_estoque(linhas, larguras):
        tabela = Table(linhas, colWidths=larguras, repeatRows=1)
        tabela.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#10325a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#eef3f8'), colors.white]),
            ('TOPPADDING', (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ]))
        return tabela

    if reposicao:
        produtos = produtos.copy()
        custo = produtos['Preço Compra (R$)'].where(produtos['Preço Compra (R$)'] > 0)
        produtos['Estimativa'] = (produtos['Sugestão de compra'] * custo).round(2)

        def estimativa(valor):
            return moeda_historico_venda(valor) if pd.notna(valor) else "Sem custo"

        total = produtos['Estimativa'].sum(min_count=1)
        conteudo.append(Paragraph(f"<b>Total estimado:</b> {estimativa(total)}", estilos['BodyText']))
        conteudo.append(Paragraph("Estimativa pelo custo unitário de compra cadastrado. "
                                  "Itens sem custo positivo ficam fora dos totais.", estilos['BodyText']))
        colunas = ['Produto', 'Unidade', 'Qtd. Estoque', 'Estoque mínimo',
                   'Sugestão de compra', 'Preço Compra (R$)', 'Estimativa']
        for fornecedor, grupo in produtos.groupby('Fornecedor', sort=True):
            conteudo.append(Paragraph(html.escape(str(fornecedor)), estilos['Heading2']))
            subtotal = grupo['Estimativa'].sum(min_count=1)
            conteudo.append(Paragraph(f"Subtotal estimado: {estimativa(subtotal)}", estilos['BodyText']))
            linhas = [["Produto", "Un.", "Saldo", "Mínimo", "Comprar", "Custo un.", "Estimado"]]
            for produto, unidade, saldo, minimo, comprar, custo_unitario, valor in grupo[colunas].itertuples(index=False, name=None):
                linhas.append([
                    Paragraph(html.escape(str(produto)), estilos['BodyText']),
                    Paragraph(html.escape(str(unidade)), estilos['BodyText']),
                    *[f"{qtd:.3f}".replace(".", ",") for qtd in (saldo, minimo, comprar)],
                    estimativa(custo_unitario if custo_unitario > 0 else None), estimativa(valor),
                ])
            conteudo.append(quadro_estoque(linhas, [147, 45, 52, 52, 56, 76, 76]))
    else:
        linhas = [["Produto", "Unidade", "Saldo", "Situação", "Preço de venda"]]
        colunas = ['Produto', 'Unidade', 'Qtd. Estoque', 'Preço Venda (R$)']
        for produto, unidade, saldo, preco in produtos[colunas].itertuples(index=False, name=None):
            situacao = "Sem estoque" if saldo == 0 else "Saldo negativo" if saldo < 0 else "Com saldo"
            linhas.append([
                Paragraph(html.escape(str(produto)), estilos['BodyText']),
                Paragraph(html.escape(str(unidade)), estilos['BodyText']),
                f"{saldo:,.3f}".replace(",", "_").replace(".", ",").replace("_", "."),
                situacao, moeda_historico_venda(preco),
            ])
        conteudo.append(quadro_estoque(linhas, [184, 86, 62, 82, 90]))
    doc.build(conteudo)
    return arquivo.getvalue()


def gerar_pdf_compras_periodo(empresa, periodo, fornecedor, produto, itens, resumo):
    arquivo = io.BytesIO()
    estilos = getSampleStyleSheet()
    doc = SimpleDocTemplate(arquivo, pagesize=letter, leftMargin=48, rightMargin=48,
                            topMargin=48, bottomMargin=48, title="Relatório de compras por período")

    def texto(valor):
        return Paragraph(html.escape(str(valor)), estilos['BodyText'])

    def valor_pdf(valor):
        return moeda_historico_venda(valor) if pd.notna(valor) else "Não informado"

    def tabela_pdf(linhas, larguras):
        tabela = Table(linhas, colWidths=larguras, repeatRows=1)
        tabela.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#10325a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (-2, 1), (-1, -1), 'RIGHT'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#eef3f8'), colors.white]),
            ('TOPPADDING', (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ]))
        return tabela

    totais = itens['Total compra (R$)']
    faltantes = int(totais.isna().sum())
    conteudo = [
        Paragraph(html.escape(str(empresa)), estilos['Heading2']),
        Paragraph("Relatório de compras por período", estilos['Title']),
        Spacer(1, 12),
        texto(f"Período: {periodo}"),
        texto(f"Fornecedor: {fornecedor}"),
        texto(f"Produto: {produto}"),
        Spacer(1, 10),
        texto(f"Total das compras: {valor_pdf(totais.sum(min_count=1))}"),
        texto(f"Linhas de produtos: {len(itens)}"),
    ]
    if faltantes:
        conteudo.append(texto(f"Total parcial. {faltantes} registro(s) sem quantidade ou custo válido ficaram fora da soma."))
    conteudo.extend([
        Paragraph("Totais por fornecedor", estilos['Heading2']),
        tabela_pdf([["Fornecedor", "Total"]] + [
            [texto(nome), valor_pdf(total)] for nome, total in resumo.itertuples(index=False, name=None)
        ], [364, 140]),
        Paragraph("Itens comprados", estilos['Heading2']),
    ])
    linhas = [["Data e fornecedor", "Produto", "Quantidade", "Custo unitário", "Total"]]
    colunas = ['Data', 'Fornecedor', 'Produto', 'Quantidade', 'Unidade', 'Custo unitário (R$)', 'Total compra (R$)']
    for data, nome, item, qtd, unidade, custo, total in itens[colunas].itertuples(index=False, name=None):
        quantidade = f"{qtd:.3f}".replace(".", ",") if pd.notna(qtd) else "Não informada"
        linhas.append([texto(f"{data} / {nome}"), texto(item), texto(f"{quantidade} {unidade}"),
                       valor_pdf(custo), valor_pdf(total)])
    conteudo.extend([tabela_pdf(linhas, [130, 120, 88, 83, 83]), Spacer(1, 10),
        texto("Os totais representam os custos registrados nas compras do período. Pagamentos são conferidos no caixa.")])
    doc.build(conteudo)
    return arquivo.getvalue()


def gerar_pdf_contas_receber(empresa, contas, cliente, situacao, vencimento):
    arquivo = io.BytesIO()
    estilos = getSampleStyleSheet()
    doc = SimpleDocTemplate(arquivo, pagesize=letter, leftMargin=48, rightMargin=48,
                            topMargin=48, bottomMargin=48, title="Relatório de contas a receber")

    def texto(valor):
        return Paragraph(html.escape(str(valor)), estilos['BodyText'])

    def quadro(linhas, larguras, primeira_coluna_valores):
        tabela = Table(linhas, colWidths=larguras, repeatRows=1)
        tabela.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#10325a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (primeira_coluna_valores, 0), (-1, -1), 'RIGHT'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#eef3f8'), colors.white]),
            ('TOPPADDING', (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ]))
        return tabela

    saldo = contas['restante'].clip(lower=0)
    dados = pd.DataFrame({
        'Cliente': contas['cliente'].fillna('').astype(str).str.strip().replace('', 'Não informado'),
        'Recebido': contas['valor_pago'],
        'Em aberto': saldo,
        'Vencido': saldo.where(contas['situacao_tela'].eq('Vencida'), 0),
        'A vencer': saldo.where(contas['situacao_tela'].eq('A vencer'), 0),
    })
    resumo = dados.groupby('Cliente', as_index=False).sum()
    moeda = moeda_historico_venda
    linhas_resumo = [['Cliente', 'Recebido', 'Em aberto', 'Vencido', 'A vencer']]
    linhas_resumo.extend([texto(nome), moeda(recebido), moeda(aberto), moeda(vencido), moeda(a_vencer)]
                         for nome, recebido, aberto, vencido, a_vencer in resumo.itertuples(index=False, name=None))
    linhas_itens = [['Conta, cliente e descrição', 'Vencimento e situação', 'Valor', 'Recebido', 'Saldo']]
    datas = pd.to_datetime(contas['vencimento'], errors='coerce').dt.strftime('%d/%m/%Y').fillna('Sem data')
    for indice, conta in contas.iterrows():
        linhas_itens.append([
            texto(f"#{conta['id']} - {dados.at[indice, 'Cliente']} | {conta['descricao'] or ''}"),
            texto(f"{datas.at[indice]} | {conta['situacao_tela']}"),
            moeda(conta['valor']), moeda(conta['valor_pago']), moeda(saldo.at[indice]),
        ])
    conteudo = [
        Paragraph(html.escape(str(empresa)), estilos['Heading2']),
        Paragraph("Relatório de contas a receber", estilos['Title']),
        Spacer(1, 10),
        texto(f"Cliente: {cliente}"),
        texto(f"Situação: {situacao}"),
        texto(f"Vencimento: {vencimento}"),
        Spacer(1, 10),
        texto(f"Recebido: {moeda(dados['Recebido'].sum())}"),
        texto(f"Em aberto: {moeda(dados['Em aberto'].sum())}"),
        texto(f"Vencido: {moeda(dados['Vencido'].sum())}"),
        Paragraph("Resumo por cliente", estilos['Heading2']),
        quadro(linhas_resumo, [160, 86, 86, 86, 86], 1),
        Paragraph("Contas e parcelas", estilos['Heading2']),
        quadro(linhas_itens, [178, 104, 74, 74, 74], 2),
        Spacer(1, 10),
        texto("O saldo em aberto inclui as parcelas vencidas, a vencer e sem vencimento. "
              "O recebido é o valor pago nas contas selecionadas, conforme os filtros de vencimento."),
    ]
    doc.build(conteudo)
    return arquivo.getvalue()


def gerar_pdf_fechamento_caixa(conexao, registro, nome_empresa):
    sessao_id = int(registro['id'])
    totais, _ = resumo_recebimentos_caixa(conexao, sessao_id)
    saldo_inicial = float(registro['saldo_inicial'] or 0)
    esperado = round(saldo_inicial + totais['Dinheiro'], 2)
    saldo_final = registro['saldo_final']

    def moeda(valor):
        if pd.isna(valor):
            return "Não informado"
        return "R$ " + f"{float(valor):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")

    def data_formatada(valor):
        data = pd.to_datetime(valor, errors='coerce')
        return data.strftime('%d/%m/%Y às %H:%M:%S') if pd.notna(data) else "Não informada"

    def texto(valor):
        return html.escape(str(valor)) if pd.notna(valor) and str(valor).strip() else "Não informado"

    estilos = getSampleStyleSheet()
    estilo_nota = ParagraphStyle('NotaCaixa', parent=estilos['BodyText'],
                                textColor=colors.HexColor('#485a70'), fontSize=9, leading=13)
    arquivo = io.BytesIO()
    doc = SimpleDocTemplate(arquivo, pagesize=letter, leftMargin=48, rightMargin=48,
                            topMargin=48, bottomMargin=48, title=f"Fechamento do caixa {sessao_id}")

    def tabela(linhas, titulo):
        quadro = Table([[titulo, "Valor"]] + linhas, colWidths=[350, 166], repeatRows=1)
        quadro.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#10325a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#eef3f8'), colors.white]),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        return quadro

    diferenca = "Não informada"
    if pd.notna(saldo_final):
        valor_diferenca = round(float(saldo_final) - esperado, 2)
        situacao = "Sobra" if valor_diferenca > 0 else "Falta" if valor_diferenca < 0 else "Confere"
        diferenca = f"{situacao} | {moeda(abs(valor_diferenca))}"

    conteudo = [
        Paragraph(texto(nome_empresa), estilos['Heading2']),
        Paragraph(f"Comprovante de fechamento do caixa nº {sessao_id}", estilos['Title']),
        Spacer(1, 12),
        Paragraph(f"<b>Abertura:</b> {data_formatada(registro['data_abertura'])}", estilos['BodyText']),
        Paragraph(f"<b>Fechamento:</b> {data_formatada(registro['data_fechamento'])}", estilos['BodyText']),
        Paragraph(f"<b>Fechado por:</b> {texto(registro['fechado_por'])}", estilos['BodyText']),
        Paragraph(f"<b>Autorizado por:</b> {texto(registro['fechamento_autorizado_por'])}", estilos['BodyText']),
        Spacer(1, 16),
        tabela([[forma, moeda(valor)] for forma, valor in totais.items()], "Movimentação líquida por forma de pagamento"),
        Spacer(1, 16),
        tabela([
            ["Saldo inicial", moeda(saldo_inicial)],
            ["Dinheiro esperado na gaveta", moeda(esperado)],
            ["Saldo final registrado", moeda(saldo_final)],
            ["Diferença", diferenca],
        ], "Conferência do fechamento"),
        Spacer(1, 12),
        Paragraph("O dinheiro esperado é calculado pelas movimentações identificadas em dinheiro. "
                  "O saldo final é o valor salvo no fechamento, conforme a regra usada na época.",
                  estilo_nota),
    ]
    doc.build(conteudo)
    return arquivo.getvalue()


def exibir_resumo_caixa(conexao, sessao_id, saldo_inicial, recolher_detalhes=False, conferencia_historico=None):
    totais, linhas = resumo_recebimentos_caixa(conexao, sessao_id)
    dinheiro = round(float(saldo_inicial) + totais['Dinheiro'], 2)
    st.markdown("### 💰 Conferência por forma de pagamento deste caixa")
    if conferencia_historico is None:
        c_din, c_pix, c_cartao = st.columns(3)
        c_din.metric("Dinheiro esperado na gaveta", f"R$ {dinheiro:,.2f}")
    else:
        def moeda_historico_caixa(valor):
            return "R$ " + f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
        registrado = conferencia_historico['saldo_final']
        esperado_col, contado_col, diferenca_col = st.columns(3)
        esperado_col.metric("Dinheiro esperado", moeda_historico_caixa(dinheiro))
        contado_col.metric("Saldo final registrado", moeda_historico_caixa(float(registrado)) if pd.notna(registrado) else "Não informado")
        if pd.notna(registrado):
            diferenca = round(float(registrado) - dinheiro, 2)
            situacao = "Sobra" if diferenca > 0 else "Falta" if diferenca < 0 else "Confere"
            diferenca_col.metric(f"Diferença · {situacao}", moeda_historico_caixa(abs(diferenca)))
        else:
            diferenca_col.metric("Diferença", "Não informada")
        st.caption("O esperado é calculado pelas movimentações. O saldo final é o valor salvo no fechamento, conforme a regra usada na época.")
        c_pix, c_cartao = st.columns(2)
    c_pix.metric("Pix líquido", f"R$ {totais['Pix']:,.2f}")
    c_cartao.metric("Cartões líquidos", f"R$ {totais['Cartão Débito'] + totais['Cartão Crédito']:,.2f}")
    st.caption(f"Dinheiro: saldo inicial de R$ {float(saldo_inicial):,.2f} mais movimentação líquida em dinheiro de R$ {totais['Dinheiro']:,.2f}. Pix e cartões ficam separados.")
    if linhas:
        quadro = pd.DataFrame(linhas).groupby('Forma de Pagamento', as_index=False).agg(
            **{'Qtd. Movimentações': ('Tipo', 'count'), 'Valor líquido (R$)': ('Valor líquido (R$)', 'sum')})
        if recolher_detalhes:
            with st.expander("Detalhes por forma de pagamento"):
                st.dataframe(quadro, use_container_width=True, hide_index=True)
        else:
            st.dataframe(quadro, use_container_width=True, hide_index=True)
    indefinidas = [l for l in linhas if l['Forma de Pagamento'] == 'Não informado']
    if indefinidas:
        st.warning("Há movimentos antigos sem forma de pagamento identificável. Eles aparecem como Não informado e não entram automaticamente no dinheiro esperado. Confira esses lançamentos antes de fechar.")
    return dinheiro, round(float(saldo_inicial) + sum(totais.values()), 2)


def validar_administrador(conexao, login, senha):
    login = str(login or '').strip().lower()
    if not login or not senha:
        raise ValueError('Informe o login e a senha do administrador para esta operação.')
    if empresa_doc and login == "administrador":
        if credencial_admin_principal(login, senha):
            return login
        raise ValueError('Login ou senha de administrador inválidos.')
    registro = conexao.execute("SELECT login, senha, cargo FROM usuarios WHERE LOWER(TRIM(login)) = ?", (login,)).fetchone()
    if registro:
        cargo = unicodedata.normalize('NFKD', str(registro[2] or '')).encode('ascii', 'ignore').decode().lower()
        if cargo != 'administrador' or not __import__('hmac').compare_digest(str(registro[1] or '').encode(), str(senha).encode()):
            raise ValueError('Login ou senha de administrador inválidos.')
        return str(registro[0])
    # Compatibilidade com os acessos administrativos já existentes no sistema.
    if credencial_admin_principal(login, senha):
        return login
    raise ValueError('Login ou senha de administrador inválidos.')


def campos_autorizacao(prefixo):
    st.markdown('**🔐 Autorização do administrador — obrigatória a cada operação**')
    st.text_input('Login do administrador', value='administrador', key=prefixo + '_login')
    st.text_input('Senha do administrador', type='password', key=prefixo + '_senha')


def capturar_autorizacao(prefixo):
    # Callback do envio do formulário: apaga o campo antes de renderizar novamente.
    st.session_state[prefixo + '_credenciais'] = (
        st.session_state.get(prefixo + '_login', ''), st.session_state.get(prefixo + '_senha', ''))
    st.session_state[prefixo + '_senha'] = ''


def consumir_autorizacao(prefixo):
    return st.session_state.pop(prefixo + '_credenciais', ('', ''))


def garantir_auditoria_operacoes(conexao):
    migracoes = {
        'vendas': {'estornado_em': 'TEXT', 'estornado_por': 'TEXT', 'autorizado_por': 'TEXT', 'motivo_estorno': 'TEXT'},
        'vendas_cabecalho': {'status': "TEXT DEFAULT 'Concluído'", 'estornado_em': 'TEXT', 'estornado_por': 'TEXT', 'autorizado_por': 'TEXT', 'motivo_estorno': 'TEXT'},
        'caixa_movimentacoes': {'estornado': 'INTEGER DEFAULT 0'},
        'caixa_sessoes': {'fechado_por': 'TEXT', 'fechamento_autorizado_por': 'TEXT'},
    }
    for tabela, novas in migracoes.items():
        existentes = {r[1] for r in conexao.execute(f'PRAGMA table_info({tabela})')}
        if existentes:
            for coluna, tipo in novas.items():
                if coluna not in existentes:
                    conexao.execute(f'ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}')
    conexao.execute('''CREATE TABLE IF NOT EXISTS auditoria_estornos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, origem TEXT NOT NULL, venda_id INTEGER NOT NULL,
        data TEXT NOT NULL, operador TEXT NOT NULL, administrador TEXT NOT NULL,
        motivo TEXT NOT NULL, valor REAL NOT NULL, itens TEXT NOT NULL, movimentos TEXT NOT NULL,
        UNIQUE(origem, venda_id))''')
    conexao.commit()


garantir_auditoria_operacoes(conn)


def estornar_venda_auditada(conexao, venda_id, origem, motivo, login, senha, operador):
    administrador = validar_administrador(conexao, login, senha)
    if not str(motivo or '').strip():
        raise ValueError('Informe o motivo do estorno.')
    if origem not in {'PDV', 'Pedido'}:
        raise ValueError('Origem da venda inválida.')
    agora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    def consultar(sql, parametros=()):
        cur = conexao.execute(sql, parametros)
        nomes = [c[0] for c in cur.description]
        return [dict(zip(nomes, r)) for r in cur.fetchall()]
    try:
        conexao.execute('BEGIN IMMEDIATE')
        if origem == 'PDV':
            base = consultar("SELECT * FROM vendas WHERE id = ? AND tipo = 'VENDA'", (int(venda_id),))
            if not base:
                raise ValueError('Venda não encontrada. Confira o ID no histórico.')
            base = base[0]
            itens = consultar("SELECT * FROM vendas WHERE cliente IS ? AND data IS ? AND vendedor IS ? AND tipo = 'VENDA' ORDER BY id",
                               (base.get('cliente'), base.get('data'), base.get('vendedor')))
            if any(str(i.get('status') or '').lower() == 'estornada' for i in itens):
                raise ValueError('Esta venda já foi estornada. O estoque e o caixa não foram alterados novamente.')
            principal = min(int(i['id']) for i in itens)
            total = round(sum(float(i.get('valor_total') or 0) for i in itens), 2)
            movimentos = consultar("SELECT * FROM caixa_movimentacoes WHERE venda_id = ? AND UPPER(TRIM(tipo)) = 'VENDA' AND COALESCE(estornado,0) = 0", (principal,))
            if not movimentos:
                movimentos = consultar("SELECT * FROM caixa_movimentacoes WHERE venda_id IS NULL AND UPPER(TRIM(tipo)) = 'VENDA' AND data = ? AND ABS(COALESCE(valor,0) - ?) < 0.01 AND descricao LIKE 'Venda PDV%' AND COALESCE(estornado,0) = 0", (base.get('data'), total))
                if len(movimentos) > 1:
                    raise ValueError('Há mais de um lançamento financeiro compatível. Identifique o movimento antes de estornar.')
            formas = [str(i.get('forma_pagamento') or '').lower() for i in itens]
            if not movimentos and not any('fiado' in f or 'parcelado' in f for f in formas):
                raise ValueError('Não foi possível identificar o movimento desta venda no caixa. Nenhum dado foi alterado.')
            descricao_conta = f'Venda PDV #{principal}'
        else:
            cab = consultar('SELECT * FROM vendas_cabecalho WHERE id = ?', (int(venda_id),))
            if not cab:
                raise ValueError('Pedido não encontrado.')
            base = cab[0]
            if str(base.get('status') or '').lower() == 'estornada':
                raise ValueError('Este pedido já foi estornado.')
            principal = int(venda_id)
            itens = consultar('SELECT * FROM vendas_itens WHERE venda_id = ?', (principal,))
            if not itens:
                raise ValueError('Não há itens registrados para devolver ao estoque.')
            total = float(base.get('total') or 0)
            movimentos = []
            descricao_conta = f'Venda #{principal}'
        if conexao.execute('SELECT 1 FROM auditoria_estornos WHERE origem=? AND venda_id=?', (origem, principal)).fetchone():
            raise ValueError('Esta venda já possui um estorno registrado.')
        # Não apaga recebimentos já realizados de uma venda a prazo.
        tabelas = {r[0] for r in conexao.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        contas = []
        if 'contas_receber' in tabelas:
            candidatas = consultar('SELECT * FROM contas_receber')
            padrao = re.compile(r'^' + re.escape(descricao_conta) + r'(?:\s|$|\s*-)', re.I)
            contas = [c for c in candidatas if padrao.search(str(c.get('descricao') or ''))]
            if any(float(c.get('valor_pago') or 0) > 0 for c in contas):
                raise ValueError('Esta venda possui recebimentos. É necessário tratar a devolução desses valores antes de estornar.')
        for item in itens:
            produto = str(item.get('produto') or '').strip()
            encontrados = conexao.execute('SELECT id FROM produtos WHERE UPPER(TRIM(produto)) = UPPER(TRIM(?))', (produto,)).fetchall()
            if len(encontrados) != 1:
                raise ValueError(f'Produto inexistente ou duplicado no estoque: {produto}. Nenhum estorno foi aplicado.')
            unidade_vendida = normalizar_unidade_medida(item.get('unidade'))
            unidade_estoque = normalizar_unidade_medida(conexao.execute('SELECT unidade FROM produtos WHERE id=?', (encontrados[0][0],)).fetchone()[0])
            if unidade_vendida and unidade_estoque and unidade_vendida != unidade_estoque:
                raise ValueError(f'A unidade de {produto} mudou desde a venda. Confira a unidade antes de devolver ao estoque.')
            saldo_estorno_antes = float(conexao.execute('SELECT quantidade FROM produtos WHERE id=?', (encontrados[0][0],)).fetchone()[0] or 0)
            conexao.execute('UPDATE produtos SET quantidade = COALESCE(quantidade,0) + ? WHERE id = ?',
                            (float(item.get('quantidade') or 0), encontrados[0][0]))
            saldo_estorno_depois = float(conexao.execute('SELECT quantidade FROM produtos WHERE id=?', (encontrados[0][0],)).fetchone()[0])
            registrar_movimento_estoque(conexao, encontrados[0][0], 'ESTORNO', saldo_estorno_antes, saldo_estorno_depois,
                                         operador, f'{origem} #{principal} — autorizado por {administrador}')
        for mov in movimentos:
            conexao.execute('UPDATE caixa_movimentacoes SET estornado=1 WHERE id=?', (mov['id'],))
        for conta in contas:
            conexao.execute("UPDATE contas_receber SET status='Cancelado' WHERE id=?", (conta['id'],))
        if origem == 'PDV':
            for item in itens:
                conexao.execute("UPDATE vendas SET status='Estornada', estornado_em=?, estornado_por=?, autorizado_por=?, motivo_estorno=? WHERE id=?",
                                 (agora, operador, administrador, motivo.strip(), item['id']))
        else:
            conexao.execute("UPDATE vendas_cabecalho SET status='Estornada', estornado_em=?, estornado_por=?, autorizado_por=?, motivo_estorno=? WHERE id=?",
                             (agora, operador, administrador, motivo.strip(), principal))
        conexao.execute('INSERT INTO auditoria_estornos (origem,venda_id,data,operador,administrador,motivo,valor,itens,movimentos) VALUES (?,?,?,?,?,?,?,?,?)',
                         (origem, principal, agora, operador, administrador, motivo.strip(), total,
                          json.dumps(itens, ensure_ascii=False, default=str), json.dumps(movimentos, ensure_ascii=False, default=str)))
        conexao.commit()
        return principal
    except Exception:
        conexao.rollback()
        raise



def garantir_rastreio_recebimentos(conexao):
    existentes = {r[1] for r in conexao.execute('PRAGMA table_info(caixa_movimentacoes)')}
    novas = {'conta_id': 'INTEGER', 'recebido_por': 'TEXT', 'regularizacao_autorizada_por': 'TEXT',
             'data_recebimento_original': 'TEXT', 'operacao_recebimento': 'TEXT'}
    for coluna, tipo in novas.items():
        if coluna not in existentes:
            conexao.execute(f'ALTER TABLE caixa_movimentacoes ADD COLUMN {coluna} {tipo}')
    conexao.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_operacao_recebimento ON caixa_movimentacoes(operacao_recebimento) WHERE operacao_recebimento IS NOT NULL')
    conexao.commit()


garantir_rastreio_recebimentos(conn)


def valor_recebido_sem_caixa(conexao, conta_id):
    conta = conexao.execute('SELECT valor_pago FROM contas_receber WHERE id=?', (int(conta_id),)).fetchone()
    if not conta:
        raise ValueError('Conta não encontrada.')
    contabilizado = 0.0
    # Compatibilidade: movimentos antigos identificavam a conta apenas na descrição.
    padrao = re.compile(r'^(?:Recebimento de conta #|Regularização de recebimento antigo - Conta #)' + str(int(conta_id)) + r'(?:\s|$)', re.I)
    movimentos = conexao.execute("SELECT conta_id, descricao, valor FROM caixa_movimentacoes WHERE UPPER(tipo)='ENTRADA' AND COALESCE(estornado,0)=0").fetchall()
    for vinculo, descricao, valor in movimentos:
        if (vinculo is not None and int(vinculo) == int(conta_id)) or (vinculo is None and padrao.search(str(descricao or ''))):
            contabilizado += float(valor or 0)
    return round(max(0.0, float(conta[0] or 0) - contabilizado), 2)


def registrar_recebimento_seguro(conexao, conta_id, valor, quitar, forma, data_original, operador,
                                operacao_id, regularizar=False, login_admin='', senha_admin=''):
    if forma not in {'Dinheiro', 'Pix', 'Cartão Débito', 'Cartão Crédito'}:
        raise ValueError('Selecione a forma de pagamento recebida.')
    if not operacao_id:
        raise ValueError('Identificador de operação ausente. Recarregue a tela.')
    administrador = validar_administrador(conexao, login_admin, senha_admin) if regularizar else None
    try:
        conexao.execute('BEGIN IMMEDIATE')
        repetida = conexao.execute('SELECT valor FROM caixa_movimentacoes WHERE operacao_recebimento=?', (operacao_id,)).fetchone()
        if repetida:
            raise ValueError('Esta operação já foi registrada. Nenhum recebimento foi duplicado.')
        # Obrigatório ANTES da baixa, e dentro da mesma transação de escrita.
        abertas = conexao.execute("SELECT id FROM caixa_sessoes WHERE status='ABERTO' ORDER BY id DESC").fetchall()
        if len(abertas) != 1:
            raise ValueError('Abra um caixa antes de receber ou regularizar esta conta. Nenhuma baixa foi realizada.' if not abertas else 'Há mais de um caixa aberto. Confira as sessões antes de receber.')
        sessao_id = int(abertas[0][0])
        conta = conexao.execute('SELECT cliente, valor, valor_pago, status FROM contas_receber WHERE id=?', (int(conta_id),)).fetchone()
        if not conta or str(conta[3] or '').lower() == 'cancelado':
            raise ValueError('Conta inexistente ou cancelada.')
        cliente, total, pago, status = conta
        total, pago = round(float(total or 0), 2), round(float(pago or 0), 2)
        if regularizar:
            recebido = valor_recebido_sem_caixa(conexao, conta_id)
            if recebido <= 0:
                raise ValueError('Não há valor sem lançamento no caixa para regularizar nesta conta.')
            descricao = f'Regularização de recebimento antigo - Conta #{int(conta_id)} - {cliente}. Baixa anterior sem movimento; não é nova cobrança.'
            restante = round(max(0, total - pago), 2)
        else:
            restante = round(total - pago, 2)
            if restante <= 0:
                raise ValueError('Esta conta já está quitada. Nenhum novo recebimento foi registrado.')
            recebido = restante if quitar else round(float(valor), 2)
            if recebido <= 0 or recebido > restante:
                raise ValueError(f'Informe um recebimento entre R$ 0,01 e R$ {restante:,.2f}.')
            novo_pago = round(pago + recebido, 2)
            restante = round(total - novo_pago, 2)
            conexao.execute('UPDATE contas_receber SET valor_pago=?, status=?, data_quitacao=? WHERE id=?',
                            (novo_pago, 'Quitado' if restante == 0 else 'Parcial', str(data_original) if restante == 0 else '-', int(conta_id)))
            descricao = f'Recebimento de conta #{int(conta_id)} - {cliente}'
        conexao.execute('''INSERT INTO caixa_movimentacoes
            (sessao_id,tipo,valor,descricao,data,forma_pagamento,conta_id,recebido_por,regularizacao_autorizada_por,data_recebimento_original,operacao_recebimento)
            VALUES (?,'ENTRADA',?,?,?,?,?,?,?,?,?)''',
            (sessao_id, recebido, descricao, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), forma,
             int(conta_id), operador, administrador, str(data_original), operacao_id))
        conexao.commit()
        return recebido, restante, sessao_id
    except Exception:
        conexao.rollback()
        raise



def garantir_colunas_parcelas(conexao):
    conexao.execute('''CREATE TABLE IF NOT EXISTS contas_receber (
        id INTEGER PRIMARY KEY AUTOINCREMENT, cliente TEXT, valor REAL,
        valor_pago REAL DEFAULT 0, vencimento TEXT, data_lancamento TEXT,
        data_quitacao TEXT, status TEXT, descricao TEXT)''')
    atuais = {r[1] for r in conexao.execute('PRAGMA table_info(contas_receber)')}
    novas = {'valor_pago': 'REAL DEFAULT 0', 'data_lancamento': 'TEXT', 'data_quitacao': 'TEXT',
             'origem_venda': 'TEXT', 'venda_id': 'INTEGER', 'parcela_numero': 'INTEGER',
             'parcelas_total': 'INTEGER', 'criado_por': 'TEXT', 'reparacao_autorizada_por': 'TEXT'}
    for coluna, tipo in novas.items():
        if coluna not in atuais:
            conexao.execute(f'ALTER TABLE contas_receber ADD COLUMN {coluna} {tipo}')
    conexao.execute('''CREATE UNIQUE INDEX IF NOT EXISTS idx_parcela_pdv
        ON contas_receber(origem_venda, venda_id, parcela_numero)
        WHERE origem_venda IS NOT NULL AND venda_id IS NOT NULL AND parcela_numero IS NOT NULL''')
    conexao.commit()


garantir_colunas_parcelas(conn)


def montar_parcelas_pdv(total, quantidade, primeiro_vencimento):
    from decimal import Decimal, ROUND_HALF_UP
    import calendar
    quantidade = int(quantidade)
    centavos = int((Decimal(str(total)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    if not 2 <= quantidade <= 24 or centavos < quantidade:
        raise ValueError('Informe de 2 a 24 parcelas, com valor mínimo de R$ 0,01 por parcela.')
    if isinstance(primeiro_vencimento, datetime):
        primeiro_vencimento = primeiro_vencimento.date()
    if not isinstance(primeiro_vencimento, date):
        primeiro_vencimento = date.fromisoformat(str(primeiro_vencimento)[:10])
    base, sobra = divmod(centavos, quantidade)
    parcelas = []
    for indice in range(quantidade):
        mes_absoluto = primeiro_vencimento.year * 12 + primeiro_vencimento.month - 1 + indice
        ano, mes = divmod(mes_absoluto, 12)
        mes += 1
        dia = min(primeiro_vencimento.day, calendar.monthrange(ano, mes)[1])
        parcelas.append({'numero': indice + 1, 'valor': (base + (sobra if indice == quantidade - 1 else 0)) / 100,
                         'vencimento': date(ano, mes, dia).isoformat()})
    return parcelas


def criar_parcelas_pdv(conexao, venda_id, cliente, parcelas, data_venda, operador, autorizador=None):
    # Chamada dentro da transação da venda ou da recuperação, sem commit próprio.
    padrao = re.compile(r'^Venda PDV #' + str(int(venda_id)) + r'(?:\s|$)', re.I)
    contas = conexao.execute('SELECT descricao, origem_venda, venda_id FROM contas_receber').fetchall()
    if any((origem == 'PDV' and vinculo == int(venda_id)) or padrao.search(str(descricao or ''))
           for descricao, origem, vinculo in contas):
        raise ValueError('Esta venda já possui contas a receber. Nenhuma parcela foi duplicada.')
    for parcela in parcelas:
        conexao.execute('''INSERT INTO contas_receber
            (cliente,valor,valor_pago,vencimento,data_lancamento,status,descricao,
             origem_venda,venda_id,parcela_numero,parcelas_total,criado_por,reparacao_autorizada_por)
            VALUES (?,?,0,?,?,'Pendente',?,'PDV',?,?,?,?,?)''',
            (cliente, parcela['valor'], parcela['vencimento'], str(data_venda)[:10],
             f"Venda PDV #{int(venda_id)} - Parcela {parcela['numero']}/{len(parcelas)}",
             int(venda_id), parcela['numero'], len(parcelas), operador, autorizador))


def recuperar_parcelas_pdv(conexao, venda_id, primeiro_vencimento, operador, login, senha):
    autorizador = validar_administrador(conexao, login, senha)
    try:
        conexao.execute('BEGIN IMMEDIATE')
        base = conexao.execute("SELECT cliente,data,vendedor,forma_pagamento,status FROM vendas WHERE id=? AND tipo='VENDA'", (int(venda_id),)).fetchone()
        if not base or str(base[4] or '').lower() == 'estornada':
            raise ValueError('Venda inexistente ou estornada.')
        cliente, data_venda, vendedor, forma, status = base
        numero = re.match(r'^Parcelado \((\d+)x', str(forma or ''), re.I)
        if not numero:
            raise ValueError('Selecione uma venda parcelada própria do PDV.')
        linhas = conexao.execute("SELECT id,valor_total,status FROM vendas WHERE cliente IS ? AND data IS ? AND vendedor IS ? AND tipo='VENDA'", (cliente, data_venda, vendedor)).fetchall()
        if any(str(linha[2] or '').lower() == 'estornada' for linha in linhas):
            raise ValueError('A venda possui itens estornados e não pode ser recuperada desta forma.')
        principal = min(int(linha[0]) for linha in linhas)
        total = round(sum(float(linha[1] or 0) for linha in linhas), 2)
        parcelas = montar_parcelas_pdv(total, int(numero.group(1)), primeiro_vencimento)
        criar_parcelas_pdv(conexao, principal, cliente, parcelas, data_venda, operador, autorizador)
        conexao.commit()
        return principal, len(parcelas)
    except Exception:
        conexao.rollback()
        raise



UNIDADES_MEDIDA = ['CAIXA', 'KG', 'UNIDADE', 'LITRO', 'METRO', 'PACOTE', 'SACO', 'GRAMA']
ROTULOS_UNIDADE = {'CAIXA': 'caixa', 'KG': 'kg', 'UNIDADE': 'un.', 'LITRO': 'litro',
                   'METRO': 'metro', 'PACOTE': 'pacote', 'SACO': 'saco', 'GRAMA': 'g'}


def normalizar_unidade_medida(valor):
    texto = str(valor or '').strip().upper()
    apelidos = {'CX': 'CAIXA', 'CAIXAS': 'CAIXA', 'QUILO': 'KG', 'QUILOGRAMA': 'KG',
                'UN': 'UNIDADE', 'UND': 'UNIDADE', 'UNIDADES': 'UNIDADE',
                'L': 'LITRO', 'LT': 'LITRO', 'LITROS': 'LITRO', 'M': 'METRO', 'METROS': 'METRO',
                'PCT': 'PACOTE', 'PACOTES': 'PACOTE', 'SC': 'SACO', 'SACOS': 'SACO',
                'G': 'GRAMA', 'GRAMAS': 'GRAMA'}
    texto = apelidos.get(texto, texto)
    return texto if texto in UNIDADES_MEDIDA else ''


def rotulo_unidade_medida(valor):
    return ROTULOS_UNIDADE.get(normalizar_unidade_medida(valor), 'unidade não informada')


def quantidade_com_unidade(quantidade, unidade):
    numero = f'{float(quantidade):.3f}'.rstrip('0').rstrip('.').replace('.', ',')
    return f'{numero} {rotulo_unidade_medida(unidade)}'


def unidade_do_item(conexao, item):
    if normalizar_unidade_medida(item.get('unidade')):
        return normalizar_unidade_medida(item['unidade'])
    if item.get('produto_id'):
        linha = conexao.execute('SELECT unidade FROM produtos WHERE id=?', (int(item['produto_id']),)).fetchone()
    else:
        linhas = conexao.execute('SELECT unidade FROM produtos WHERE UPPER(TRIM(produto))=UPPER(TRIM(?))', (str(item.get('produto') or ''),)).fetchall()
        linha = linhas[0] if len(linhas) == 1 else None
    return normalizar_unidade_medida(linha[0]) if linha else ''


def garantir_unidade_historicos(conexao):
    conexao.execute('''CREATE TABLE IF NOT EXISTS vendas_itens (
        id INTEGER PRIMARY KEY AUTOINCREMENT, venda_id INTEGER, produto TEXT,
        quantidade REAL, valor_unitario REAL, valor_total REAL, unidade TEXT)''')
    for tabela in ['vendas', 'vendas_itens']:
        colunas = {r[1] for r in conexao.execute(f'PRAGMA table_info({tabela})')}
        if colunas and 'unidade' not in colunas:
            conexao.execute(f'ALTER TABLE {tabela} ADD COLUMN unidade TEXT')
    conexao.commit()


garantir_unidade_historicos(conn)


def validar_unidade_entrada(conexao, produto, unidade):
    nova = normalizar_unidade_medida(unidade)
    if not nova:
        raise ValueError('Selecione a unidade de medida antes de registrar a entrada.')
    linhas = conexao.execute('SELECT unidade FROM produtos WHERE UPPER(TRIM(produto))=UPPER(TRIM(?))', (str(produto),)).fetchall()
    if len(linhas) > 1:
        raise ValueError(f'Existem produtos duplicados com o nome {produto}. Confira o cadastro.')
    atual = normalizar_unidade_medida(linhas[0][0]) if linhas else ''
    if atual and atual != nova:
        raise ValueError(f'{produto} está cadastrado em {rotulo_unidade_medida(atual)}. Registre a compra nessa mesma unidade. Conversão entre unidades não está configurada.')
    return nova



def garantir_historico_estoque(conexao):
    conexao.execute('''CREATE TABLE IF NOT EXISTS movimentos_estoque (
        id INTEGER PRIMARY KEY AUTOINCREMENT, produto_id INTEGER NOT NULL,
        produto TEXT NOT NULL, unidade TEXT, tipo TEXT NOT NULL,
        quantidade REAL NOT NULL, saldo_antes REAL NOT NULL, saldo_depois REAL NOT NULL,
        data TEXT NOT NULL, usuario TEXT, referencia TEXT, grupo_operacao TEXT)''')
    conexao.execute('CREATE INDEX IF NOT EXISTS idx_movimentos_estoque_produto ON movimentos_estoque(produto_id,id)')
    conexao.commit()


garantir_historico_estoque(conn)


def registrar_movimento_estoque(conexao, produto_id, tipo, antes, depois, usuario='', referencia='', grupo=''):
    if not conexao.in_transaction:
        raise ValueError('O movimento de estoque deve fazer parte da mesma transação da operação.')
    registro = conexao.execute('SELECT produto,unidade FROM produtos WHERE id=?', (int(produto_id),)).fetchone()
    if not registro:
        raise ValueError('Produto não encontrado para registrar o movimento de estoque.')
    from decimal import Decimal
    variacao = Decimal(str(depois)) - Decimal(str(antes))
    conexao.execute('''INSERT INTO movimentos_estoque
        (produto_id,produto,unidade,tipo,quantidade,saldo_antes,saldo_depois,data,usuario,referencia,grupo_operacao)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
        (int(produto_id),registro[0],normalizar_unidade_medida(registro[1]),tipo,float(variacao),
         float(antes),float(depois),datetime.now().strftime('%Y-%m-%d %H:%M:%S'),usuario,referencia,grupo))



def conferir_estoque_carrinho(conexao, itens):
    from decimal import Decimal, InvalidOperation
    if not itens:
        raise ValueError('Inclua pelo menos um produto antes de concluir a venda.')
    agrupados = {}
    for item in itens:
        try:
            quantidade = Decimal(str(item.get('quantidade', 0)))
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError('Quantidade inválida no carrinho.')
        if not quantidade.is_finite() or quantidade <= 0:
            raise ValueError('A quantidade de cada produto deve ser maior que zero.')
        identificador = item.get('produto_id')
        if identificador is not None and str(identificador) not in {'', '0', 'None'}:
            encontrados = conexao.execute('SELECT id, produto, quantidade, unidade FROM produtos WHERE id=?', (int(identificador),)).fetchall()
        else:
            encontrados = conexao.execute('SELECT id, produto, quantidade, unidade FROM produtos WHERE UPPER(TRIM(produto))=UPPER(TRIM(?))', (str(item.get('produto') or ''),)).fetchall()
        if len(encontrados) != 1:
            raise ValueError(f"Não foi possível identificar um produto único no estoque: {item.get('produto', '')}.")
        produto_id, nome, saldo, unidade_atual = encontrados[0]
        unidade_atual = normalizar_unidade_medida(unidade_atual)
        unidade_carrinho = normalizar_unidade_medida(item.get('unidade'))
        if unidade_carrinho and unidade_atual and unidade_carrinho != unidade_atual:
            raise ValueError(f'A unidade de {nome} mudou. Retire o produto do carrinho e inclua novamente.')
        try:
            disponivel = Decimal(str(saldo if saldo is not None else 0))
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError(f'Estoque inválido para {nome}. Confira o cadastro.')
        if not disponivel.is_finite():
            raise ValueError(f'Estoque inválido para {nome}. Confira o cadastro.')
        if produto_id not in agrupados:
            agrupados[produto_id] = {'id': produto_id, 'produto': nome, 'disponivel': disponivel, 'quantidade': Decimal('0'), 'unidade': unidade_atual}
        agrupados[produto_id]['quantidade'] += quantidade
    for produto in agrupados.values():
        if produto['quantidade'] > produto['disponivel']:
            raise ValueError(f"Estoque insuficiente para {produto['produto']}. Disponível: {quantidade_com_unidade(max(0, produto['disponivel']), produto['unidade'])}; total solicitado no carrinho: {quantidade_com_unidade(produto['quantidade'], produto['unidade'])}.")
    return list(agrupados.values())


def incluir_com_estoque(conexao, carrinho, item):
    # A soma inclui todas as linhas repetidas do produto que já estão no carrinho.
    conferir_estoque_carrinho(conexao, list(carrinho) + [item])
    item = dict(item)
    item['unidade'] = unidade_do_item(conexao, item)
    carrinho.append(item)


def baixar_estoque_carrinho(conexao, itens, operador='', referencia=''):
    grupo_operacao = uuid.uuid4().hex
    if not conexao.in_transaction:
        raise ValueError('A baixa de estoque exige uma transação ativa.')
    # O chamador abre BEGIN IMMEDIATE antes da consulta para serializar vendas concorrentes.
    plano = conferir_estoque_carrinho(conexao, itens)
    for produto in plano:
        novo_saldo = float(produto['disponivel'] - produto['quantidade'])
        cursor_baixa = conexao.execute('''UPDATE produtos SET quantidade=?
            WHERE id=? AND CAST(COALESCE(quantidade,0) AS REAL)>=?''',
            (novo_saldo, produto['id'], float(produto['quantidade'])))
        if cursor_baixa.rowcount != 1:
            raise ValueError(f"O estoque de {produto['produto']} mudou. Confira o carrinho antes de concluir.")
        registrar_movimento_estoque(conexao, produto['id'], 'VENDA', produto['disponivel'], novo_saldo,
                                    operador, referencia, grupo_operacao)
    return grupo_operacao



def icone_automatico_produto(nome):
    """Ilustração local por palavra inteira; produtos desconhecidos usam embalagem."""
    texto = unicodedata.normalize("NFKD", str(nome)).encode("ascii", "ignore").decode().lower()
    palavras = set(__import__("re").findall(r"[a-z]+", texto))
    catalogo = {
        "abacate": "🥑", "abacaxi": "🍍", "banana": "🍌", "maca": "🍎",
        "pera": "🍐", "laranja": "🍊", "limao": "🍋", "uva": "🍇",
        "melancia": "🍉", "melao": "🍈", "morango": "🍓", "manga": "🥭",
        "pessego": "🍑", "cereja": "🍒", "coco": "🥥", "kiwi": "🥝",
        "tomate": "🍅", "cebola": "🧅", "alho": "🧄", "batata": "🥔",
        "cenoura": "🥕", "milho": "🌽", "pepino": "🥒", "berinjela": "🍆",
        "brocolis": "🥦", "alface": "🥬", "pimentao": "🫑", "pimenta": "🌶️",
        "arroz": "🍚", "feijao": "🫘", "leite": "🥛", "ovo": "🥚",
        "ovos": "🥚", "pao": "🍞", "queijo": "🧀", "cafe": "☕",
        "carne": "🥩", "frango": "🍗", "peixe": "🐟", "agua": "💧",
    }
    return next((icone for palavra, icone in catalogo.items() if palavra in palavras), "📦")


def mostrar_imagem_produto(produto):
    foto = produto.get("imagem_produto")
    if isinstance(foto, (bytes, bytearray, memoryview)) and len(foto):
        try:
            st.image(bytes(foto), width=120)
            creditos = produto.get("imagem_creditos")
            if isinstance(creditos, str) and creditos:
                st.caption(creditos)
            return
        except Exception:
            st.caption("Foto indisponível. Exibindo ilustração automática.")
    st.markdown(
        f"<div style='font-size:72px;line-height:1.2;text-align:center;"
        f"background:#e7eee9;border-radius:12px;padding:8px;'>"
        f"{icone_automatico_produto(produto.get('produto', ''))}</div>",
        unsafe_allow_html=True,
    )
    st.caption("Ilustração automática")


def preparar_foto_produto(arquivo):
    if arquivo.size > 5 * 1024 * 1024:
        raise ValueError("Escolha uma imagem de até 5 MB.")
    with Image.open(arquivo) as original:
        if original.format not in {"JPEG", "PNG", "WEBP"}:
            raise ValueError("Use uma foto JPG, PNG ou WebP.")
        if original.width * original.height > 20000000:
            raise ValueError("A imagem é muito grande. Reduza para até 20 megapixels.")
        foto = ImageOps.exif_transpose(original).convert("RGBA")
        foto.thumbnail((640, 640))
        fundo = Image.new("RGB", foto.size, "#e7eee9")
        fundo.paste(foto, mask=foto.getchannel("A"))
        saida = io.BytesIO()
        fundo.save(saida, format="JPEG", quality=85)
        return saida.getvalue()



@st.cache_data(ttl=3600, show_spinner=False)
def buscar_fotos_produto(termo):
    # A busca só ocorre por solicitação, nunca ao abrir ou finalizar uma venda.
    traducao = {"abacaxi": "pineapple fruit", "abacate": "avocado fruit", "cebola": "onion vegetable",
                "banana": "banana fruit", "maca": "apple fruit", "laranja": "orange fruit",
                "tomate": "tomato", "batata": "potato", "alho": "garlic", "manga": "mango fruit"}
    normal = unicodedata.normalize("NFKD", termo).encode("ascii", "ignore").decode().lower()
    consulta = next((v for k, v in traducao.items() if k in re.findall(r"[a-z]+", normal)), termo)
    parametros = {"action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
                  "gsrsearch": consulta + " filetype:bitmap -drawing -illustration -logo",
                  "gsrlimit": 12, "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 960}
    req = Request("https://commons.wikimedia.org/w/api.php?" + urlencode(parametros),
                  headers={"User-Agent": "CRMComercioProductPhotos/1.0 (product photo selection)"})
    with urlopen(req, timeout=15) as resposta:
        conteudo = json.loads(resposta.read(2 * 1024 * 1024))
    if "error" in conteudo:
        raise ValueError("O serviço de imagens não conseguiu concluir a busca.")
    resultados = []
    paginas = sorted(conteudo.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 999))
    for pagina in paginas:
        infos = pagina.get("imageinfo", [])
        if not infos:
            continue
        info = infos[0]
        if info.get("mime") not in {"image/jpeg", "image/png", "image/webp"} or min(info.get("width", 0), info.get("height", 0)) < 600:
            continue
        meta = info.get("extmetadata", {})
        def limpar(campo):
            return html.unescape(re.sub(r"<[^>]+>", "", meta.get(campo, {}).get("value", ""))).strip()[:500]
        licenca = limpar("LicenseShortName")
        autor = limpar("Artist")
        fonte = info.get("descriptionurl", "")
        if not licenca or not autor or not fonte:
            continue
        resultados.append({"url": info.get("thumburl", info["url"]), "fonte": fonte,
                           "titulo": pagina.get("title", "Foto").removeprefix("File:"),
                           "creditos": f"Foto: {autor} | {licenca} | {fonte}"})
        if len(resultados) == 6:
            break
    return resultados


def baixar_foto_produto(url):
    # Somente arquivos da fonte consultada; não aceita endereços digitados pelo usuário.
    def permitido(endereco):
        partes = urlparse(endereco)
        return partes.scheme == "https" and partes.hostname == "upload.wikimedia.org"
    if not permitido(url):
        raise ValueError("Endereço de imagem não permitido.")
    req = Request(url, headers={"User-Agent": "CRMComercioProductPhotos/1.0 (product photo selection)"})
    with urlopen(req, timeout=20) as resposta:
        if not permitido(resposta.geturl()):
            raise ValueError("Redirecionamento de imagem não permitido.")
        dados = resposta.read(5 * 1024 * 1024 + 1)
    arquivo = io.BytesIO(dados)
    arquivo.size = len(dados)
    return preparar_foto_produto(arquivo)


def selecionar_foto_online(produto, contexto):
    chave = f"busca_foto_{contexto}_{int(produto['id'])}"
    st.markdown("**🔎 Buscar fotografias reais na internet**")
    termo = st.text_input("Nome para buscar a foto", value=str(produto['produto']), key=chave + "_termo")
    if st.button("🔎 Buscar fotos reais", key=chave + "_buscar"):
        st.session_state.pop(chave, None)
        if not termo.strip():
            st.warning("Digite o nome do produto.")
        else:
            try:
                with st.spinner("Procurando fotos em boa resolução..."):
                    st.session_state[chave] = buscar_fotos_produto(termo.strip())
            except Exception:
                st.warning("Não foi possível acessar a busca agora. Tente novamente ou envie uma foto manualmente.")
    resultados = st.session_state.get(chave)
    if resultados == []:
        st.info("Nenhuma foto adequada encontrada. Tente um nome mais simples ou envie sua própria foto.")
    if resultados:
        st.caption("Confira se a foto corresponde ao produto antes de salvar. Fonte: Wikimedia Commons.")
        colunas = st.columns(2)
        for indice, foto in enumerate(resultados):
            with colunas[indice % 2]:
                st.image(foto['url'], width=220)
                st.caption(foto['titulo'])
                st.caption(foto['creditos'])
                if st.button("Usar esta foto", key=chave + f"_usar_{indice}"):
                    try:
                        with st.spinner("Salvando foto..."):
                            dados = baixar_foto_produto(foto['url'])
                    except Exception:
                        st.warning("Não foi possível baixar esta foto. Escolha outra ou tente novamente.")
                    else:
                        conn.execute("UPDATE produtos SET imagem_produto = ?, imagem_creditos = ? WHERE id = ?",
                                     (dados, foto['creditos'], int(produto['id'])))
                        conn.commit()
                        st.session_state.pop(chave, None)
                        st.rerun()


def gerenciar_imagem_produto(produto, contexto):
    produto_id = int(produto['id'])
    with st.expander("📷 Foto do produto — manual ou automática"):
        mostrar_imagem_produto(produto)
        selecionar_foto_online(produto, contexto)
        st.markdown("**📤 Ou envie sua própria foto**")
        st.caption("A foto escolhida fica salva no banco de dados e aparece no PDV.")
        with st.form(f"foto_{contexto}_{produto_id}"):
            arquivo = st.file_uploader("Enviar foto (até 5 MB)", type=["jpg", "jpeg", "png", "webp"])
            salvar = st.form_submit_button("Salvar foto")
            remover = st.form_submit_button("Usar ilustração automática")
        if remover:
            conn.execute("UPDATE produtos SET imagem_produto = NULL, imagem_creditos = NULL WHERE id = ?", (produto_id,))
            conn.commit()
            st.rerun()
        if salvar:
            if arquivo is None:
                st.warning("Selecione uma foto antes de salvar.")
            else:
                try:
                    dados = preparar_foto_produto(arquivo)
                except Exception as erro:
                    st.error(f"Não foi possível usar esta imagem. {erro}")
                else:
                    conn.execute("UPDATE produtos SET imagem_produto = ?, imagem_creditos = NULL WHERE id = ?", (dados, produto_id))
                    conn.commit()
                    st.rerun()


def normalizar_documento(valor):
    return ''.join(ch for ch in str(valor or '') if ch.isdigit())


def contar_dispositivos_ativos(cnpj, conexao=None):
    conexao = conexao or conn
    doc = normalizar_documento(cnpj)
    if not doc:
        return 0
    cur = conexao.cursor()
    cur.execute("""
        SELECT COUNT(DISTINCT device_id)
        FROM empresas_dispositivos
        WHERE ativado = 1
          AND REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(cnpj,''),'.',''),'/',''),'-',''),' ','') = ?
    """, (doc,))
    return int(cur.fetchone()[0] or 0)


# --- DISPOSITIVO: ID persistente no navegador ---
@st.cache_resource
def preparar_componente_dispositivo():
    pasta = tempfile.TemporaryDirectory(prefix="crm_dispositivo_")
    with open(os.path.join(pasta.name, "index.html"), "w", encoding="utf-8") as arquivo:
        arquivo.write("""
<script>

function enviar(tipo, dados) {
    window.parent.postMessage({isStreamlitMessage: true, type: tipo, ...dados}, "*");
}
window.addEventListener("message", (evento) => {
    if (evento.source !== window.parent || evento.data?.type !== "streamlit:render") return;
    try {
        const {id, chave} = evento.data.args;
        if (id) {
            localStorage.setItem(chave, id);
        } else {
            enviar("streamlit:setComponentValue", {
                value: localStorage.getItem(chave) || "",
                dataType: "json"
            });
        }
    } catch (erro) {
        if (!evento.data.args.id) {
            enviar("streamlit:setComponentValue", {value: "", dataType: "json"});
        }
    }
});
enviar("streamlit:componentReady", {apiVersion: 1});
enviar("streamlit:setFrameHeight", {height: 0});
</script>
""")
    return pasta

componente_dispositivo = components.declare_component(
    "crm_identificacao_navegador", path=preparar_componente_dispositivo().name
)

def normalizar_device_id(valor):
    try:
        return str(uuid.UUID(str(valor)))
    except ValueError:
        return ""

chave_dispositivo = (
    f"crm_comercio_device_id_{empresa_doc}"
    if empresa_doc and empresa_doc != "19417439000142"
    else "crm_comercio_device_id"
)
device_id = normalizar_device_id(st.query_params.get("device_id", ""))
if not device_id:
    id_salvo = componente_dispositivo(id="", chave=chave_dispositivo, key="ler_dispositivo", default=None)
    device_id = normalizar_device_id(id_salvo)
    if device_id:
        st.query_params["device_id"] = device_id
        st.rerun()

    if id_salvo is None:
        st.info("Recuperando a identificação deste navegador...")
    else:
        st.info("Este perfil do navegador ainda não tem uma ativação salva.")

    if st.button("Continuar com um novo dispositivo"):
        st.query_params["device_id"] = str(uuid.uuid4())
        st.rerun()
    st.caption("Se você já tem um link ativado, abra esse link neste perfil do navegador.")
    st.stop()

if 'carrinho_compras' not in st.session_state:
    st.session_state.carrinho_compras = []

df_emp_dev = carregar_dados(
    f"SELECT * FROM empresas_dispositivos WHERE device_id = '{device_id}'"
)

if df_emp_dev.empty:
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO empresas_dispositivos
        (device_id, nome_empresa, cnpj, ie, fone, endereco,
         ativado, dias_licenca, limite_dispositivos)
        VALUES (?, ?, ?, '', ?, ?, 0, 30, 1)
    """, (device_id, nome_empresa_padrao, doc_empresa_padrao, fone_empresa_padrao, endereco_empresa_padrao))
    conn.commit()

    df_emp_dev = carregar_dados(
    f"SELECT * FROM empresas_dispositivos WHERE device_id = '{device_id}'"
)

reg_emp = df_emp_dev.iloc[0] if not df_emp_dev.empty else {}

nome_empresa_header = str(
    reg_emp.get('nome_empresa', nome_empresa_padrao)
)

dispositivo_registrado = reg_emp.get("ativado", 0) == 1
licenca_expira_em = reg_emp.get("licenca_expira_em")
agora_licenca = datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
licenca_vencida = bool(dispositivo_registrado and licenca_expira_em and licenca_expira_em <= agora_licenca)
dispositivo_esta_ativado = dispositivo_registrado and not licenca_vencida

if dispositivo_registrado:
    componente_dispositivo(id=device_id, chave=chave_dispositivo, key="salvar_dispositivo")

dias_licenca_atual = int(
    reg_emp.get('dias_licenca', 30)
)

limite_dispositivos_atual = int(
    reg_emp.get('limite_dispositivos', 1)
)

st.session_state["dispositivo_ativado"] = dispositivo_esta_ativado
st.session_state["dias_licenca"] = dias_licenca_atual
st.session_state["limite_dispositivos"] = limite_dispositivos_atual

# --- OUTROS ESTADOS DE SESSÃO ---
if 'autenticado' not in st.session_state:
    st.session_state['autenticado'] = False

if 'usuario_logado' not in st.session_state:
    st.session_state['usuario_logado'] = ""

if 'login_efetuado' not in st.session_state:
    st.session_state['login_efetuado'] = ""

if 'cargo_logado' not in st.session_state:
    st.session_state['cargo_logado'] = ""

if 'permissoes_usuario' not in st.session_state:
    st.session_state['permissoes_usuario'] = {}

if 'carrinho_pdv' not in st.session_state:
    st.session_state.carrinho_pdv = []

if "carrinho_cliente" not in st.session_state:
    st.session_state.carrinho_cliente = []

if 'tela_checkout_ativa' not in st.session_state:
    st.session_state.tela_checkout_ativa = False

# Preferências visuais independentes para cada usuário, salvas no SQLite.
CORES_PADRAO = {
    "fundo": "#8B98A5", "paineis": "#BAC5D0", "campos": "#D0D8E0",
    "texto": "#203346", "titulos": "#172B4D", "botoes": "#086747",
    "texto_botoes": "#FFFFFF", "lateral": "#172B4D", "texto_lateral": "#EEEAE2",
}


def validar_cores_aparencia(valores):
    if not isinstance(valores, dict):
        valores = {}
    return {chave: valores.get(chave, padrao) if isinstance(valores.get(chave), str)
            and re.fullmatch(r"#[0-9a-fA-F]{6}", valores[chave]) else padrao
            for chave, padrao in CORES_PADRAO.items()}


def carregar_aparencia(usuario):
    conn.execute("CREATE TABLE IF NOT EXISTS preferencias_aparencia (usuario TEXT PRIMARY KEY, cores TEXT NOT NULL)")
    conn.commit()
    registro = conn.execute("SELECT cores FROM preferencias_aparencia WHERE usuario = ?", (usuario,)).fetchone()
    try:
        return validar_cores_aparencia(json.loads(registro[0])) if registro else CORES_PADRAO.copy()
    except (ValueError, TypeError):
        return CORES_PADRAO.copy()


def painel_aparencia():
    usuario = str(st.session_state.get('usuario_logado') or 'visitante')
    with st.sidebar.expander("🎨 Aparência — cores do sistema"):
        st.caption("Personalize as cores de todas as telas para seu usuário.")
        if st.session_state.pop('aparencia_salva', False):
            st.success("Cores atualizadas!")
        revisao = st.session_state.get('aparencia_revisao', 0)
        rotulos = {"fundo": "Fundo das telas", "paineis": "Quadros e janela de pagamento",
                   "campos": "Campos de preenchimento", "texto": "Letras das telas",
                   "titulos": "Títulos", "botoes": "Botões verdes (ações principais)",
                   "texto_botoes": "Letras dos botões principais", "lateral": "Fundo do menu lateral",
                   "texto_lateral": "Letras do menu lateral"}
        with st.form("form_aparencia"):
            escolhas = {chave: st.color_picker(rotulos[chave], value=cores_atuais[chave],
                        key=f"cor_{usuario}_{revisao}_{chave}") for chave in CORES_PADRAO}
            salvar = st.form_submit_button("💾 Salvar minhas cores", type="primary")
            restaurar = st.form_submit_button("↩️ Restaurar cinza metálico")
        if salvar or restaurar:
            novas = CORES_PADRAO.copy() if restaurar else validar_cores_aparencia(escolhas)
            conn.execute("INSERT INTO preferencias_aparencia (usuario, cores) VALUES (?, ?) "
                         "ON CONFLICT(usuario) DO UPDATE SET cores = excluded.cores", (usuario, json.dumps(novas)))
            conn.commit()
            st.session_state.aparencia_revisao = revisao + 1
            st.session_state.aparencia_salva = True
            st.rerun()


cores_atuais = carregar_aparencia(str(st.session_state.get('usuario_logado') or 'visitante'))

# --- ESTILO VISUAL MODERNO DO CRM ---
st.markdown("""
<style>
    /* Fundo geral e área principal */
    .stApp {
        background: #8b98a5 !important;
        color: #152536 !important;
    }
    [data-testid="stAppViewContainer"] > .main {
        background: #8b98a5 !important;
    }
    .block-container {
        max-width: 1500px;
        padding-top: 1.6rem;
        padding-bottom: 2.5rem;
    }

    /* Barra lateral */
    [data-testid="stSidebar"] {
        background: #172b4d !important;
        border-right: 1px solid #263f65;
    }
    /* Texto do menu lateral maior e com bom contraste */
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] [data-testid="stRadio"] p,
    [data-testid="stSidebar"] [data-testid="stRadio"] label {
        color: #d0d8e0 !important;
        font-size: 14px !important;
        font-weight: 650 !important;
        line-height: 1.45 !important;
    }
    [data-testid="stSidebar"] [data-testid="stRadio"] label {
        padding: 8px 7px;
        border-radius: 8px;
        margin-bottom: 3px;
    }
    /* Campos e botões da barra lateral precisam manter contraste próprio */
    [data-testid="stSidebar"] input,
    [data-testid="stSidebar"] textarea,
    [data-testid="stSidebar"] [data-baseweb="select"] *,
    [data-testid="stSidebar"] [data-baseweb="input"] * {
        color: #152536 !important;
        font-size: 14px !important;
    }
    [data-testid="stSidebar"] button {
        color: #172b4d !important;
        font-size: 14px !important;
        font-weight: 700 !important;
        background: #d0d8e0 !important;
    }

    /* Tipografia e títulos */
    h1, h2, h3, h4 {
        color: #172b4d !important;
        font-weight: 750 !important;
        letter-spacing: -0.02em;
    }
    p, label, [data-testid="stMarkdownContainer"] {
        color: #203346;
    }

    /* Cartões e áreas de conteúdo: sem aplicar fundo a cada bloco interno */
    [data-testid="stVerticalBlockBorderWrapper"] {
        background: #d0d8e0 !important;
        border: 1px solid #8b9aa9 !important;
        border-radius: 14px !important;
        box-shadow: 0 3px 12px rgba(25, 45, 75, 0.06) !important;
    }

    /* Campos de entrada */
    div[data-baseweb="input"],
    div[data-baseweb="select"],
    div[data-baseweb="textarea"] {
        background: #d0d8e0 !important;
        border: 1px solid #8b9aa9 !important;
        border-radius: 9px !important;
    }
    div[data-baseweb="input"] input,
    div[data-baseweb="textarea"] textarea {
        color: #152536 !important;
        font-size: 15px !important;
    }

    /* Botões */
    .stButton > button,
    .stDownloadButton > button,
    [data-testid="stFormSubmitButton"] > button {
        border-radius: 9px !important;
        min-height: 42px;
        font-weight: 650 !important;
        border: 1px solid #8b9aa9 !important;
        transition: all 0.15s ease-in-out;
    }
    .stButton > button[kind="primary"],
    [data-testid="stFormSubmitButton"] > button[kind="primary"] {
        background: #087f5b !important;
        color: #d0d8e0 !important;
        border: 1px solid #087f5b !important;
    }
    .stButton > button:hover,
    .stDownloadButton > button:hover {
        border-color: #087f5b !important;
        transform: translateY(-1px);
    }

    /* Tabelas */
    div[data-testid="stTable"],
    div[data-testid="stDataFrame"] {
        background: #d0d8e0 !important;
        border: 1px solid #8b9aa9 !important;
        border-radius: 10px !important;
        overflow: hidden;
    }

    /* Abas */
    button[data-baseweb="tab"] {
        font-weight: 650 !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #087f5b !important;
        border-bottom-color: #087f5b !important;
    }

    /* Avisos e métricas */
    [data-testid="stAlert"] {
        border-radius: 10px !important;
    }
    [data-testid="stMetric"] {
        background: #d0d8e0;
        border: 1px solid #8b9aa9;
        border-radius: 12px;
        padding: 12px 14px;
    }

    /* Legibilidade geral dos textos e controles */
    .stApp, .stApp p, .stApp label,
    .stApp [data-testid="stMarkdownContainer"],
    .stApp [data-testid="stWidgetLabel"] {
        font-size: 15px !important;
        line-height: 1.45 !important;
    }
    .stApp input, .stApp textarea,
    .stApp [data-baseweb="select"] {
        font-size: 15px !important;
    }
    .stApp button {
        font-size: 14px !important;
    }
    [data-testid="stDataFrame"] {
        font-size: 14px !important;
    }

    /* Ajuste para telas menores */
    @media (max-width: 768px) {
        .block-container {
            padding-left: 0.8rem;
            padding-right: 0.8rem;
            padding-top: 1rem;
        }
    }

    /* Acabamento aço acetinado, com pouco brilho. */
    .stApp, [data-testid="stAppViewContainer"],
    [data-testid="stMain"] {
        background: linear-gradient(135deg, #a1adb9 0%, #8b98a5 48%, #8795a3 100%) !important;
    }
    [data-testid="stHeader"] {
        background: #8b98a5 !important;
    }
    [data-testid="stVerticalBlockBorderWrapper"],
    [data-testid="stVerticalBlock"][style*="border"] {
        background: linear-gradient(145deg, #c2ccd6, #adb9c5) !important;
        border-color: #798b9c !important;
    }
    /* A janela de pagamento acompanha o tom metálico do PDV. */
    [data-testid="stDialog"] [role="dialog"],
    div[role="dialog"][aria-modal="true"] {
        background: linear-gradient(145deg, #c2ccd6, #a8b5c2) !important;
        color: #152536 !important;
        border: 1px solid #76899c !important;
        box-shadow: 0 18px 55px rgba(15, 30, 45, 0.36) !important;
    }
    div[data-baseweb="select"] > div,
    div[data-baseweb="input"], div[data-baseweb="base-input"],
    div[data-baseweb="textarea"],
    input, textarea {
        background-color: #d0d8e0 !important;
        color: #152536 !important;
    }
    [data-testid="stCaptionContainer"] p {
        color: #34485a !important;
    }
    /* Texto interno também recebe a cor: o parágrafo sobrescrevia o botão. */
    .stApp button[kind="primary"],
    .stApp button[data-testid="stBaseButton-primary"],
    [data-testid="stDialog"] button[kind="primary"] {
        background: linear-gradient(180deg, #08724f, #055a3e) !important;
        border: 1px solid #064b35 !important;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.16), 0 2px 4px rgba(16,35,48,0.18) !important;
    }
    .stApp button[kind="primary"],
    .stApp button[kind="primary"] *,
    .stApp button[data-testid="stBaseButton-primary"] *,
    [data-testid="stDialog"] button[kind="primary"],
    [data-testid="stDialog"] button[kind="primary"] * {
        color: #ffffff !important;
        -webkit-text-fill-color: #ffffff !important;
        font-weight: 800 !important;
        opacity: 1;
        text-shadow: 0 1px 2px rgba(0,0,0,0.35);
    }
    .stApp button[kind="primary"]:hover:not(:disabled) {
        background: #064d37 !important;
        border-color: #033c2b !important;
    }
    .stApp button[kind="primary"]:disabled {
        opacity: 0.5 !important;
        cursor: not-allowed;
    }
    .stApp button:focus-visible {
        outline: 3px solid #e8bf5b !important;
        outline-offset: 2px;
    }
    [data-testid="stAlert"] {
        background-color: #c3d2d7 !important;
        color: #152536 !important;
    }
    [data-testid="stSidebar"] [data-testid="stAlert"] p {
        color: #152536 !important;
    }
    @media print {
        .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
            background: white !important;
        }
    }
</style>
""", unsafe_allow_html=True)


# Tema personalizado; títulos afastados da barra fixa em todas as telas.
css_aparencia = """
<style>
.stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"], [data-testid="stHeader"] {
    background: @fundo@ !important; color: @texto@ !important;
}
[data-testid="stMainBlockContainer"], .main .block-container, section.main .block-container {
    padding-top: 4.8rem !important;
}
.stApp .block-container { padding-top: 4.8rem !important; }
.stApp p, .stApp label, .stApp [data-testid="stMarkdownContainer"],
.stApp [data-testid="stCaptionContainer"] p { color: @texto@ !important; }
.stApp h1, .stApp h2, .stApp h3, .stApp h4 { color: @titulos@ !important; }
[data-testid="stVerticalBlockBorderWrapper"], [data-testid="stVerticalBlock"][style*="border"],
[data-testid="stMetric"], [data-testid="stDialog"] [role="dialog"], div[role="dialog"][aria-modal="true"] {
    background: @paineis@ !important; color: @texto@ !important;
}
div[data-baseweb="input"], div[data-baseweb="base-input"], div[data-baseweb="textarea"],
div[data-baseweb="select"], div[data-baseweb="select"] > div,
.stApp input, .stApp textarea { background: @campos@ !important; color: @texto@ !important; }
div[data-baseweb="select"] span, div[data-baseweb="select"] input { color: @texto@ !important; }
.stApp button[kind="secondary"], .stApp button[data-testid="stBaseButton-secondary"],
.stApp [data-testid="stDownloadButton"] button {
    background: @campos@ !important; color: @texto@ !important;
}
.stApp button[kind="secondary"] *, .stApp [data-testid="stDownloadButton"] button * { color: @texto@ !important; }
.stApp button[kind="primary"], .stApp button[data-testid="stBaseButton-primary"],
[data-testid="stDialog"] button[kind="primary"],
.stApp button[kind="primary"]:hover:not(:disabled) { background: @botoes@ !important; border-color: @botoes@ !important; }
.stApp button[kind="primary"], .stApp button[kind="primary"] *,
.stApp button[data-testid="stBaseButton-primary"] *,
[data-testid="stDialog"] button[kind="primary"], [data-testid="stDialog"] button[kind="primary"] * {
    color: @texto_botoes@ !important; -webkit-text-fill-color: @texto_botoes@ !important; font-weight: 800 !important;
}
[data-testid="stSidebar"] { background: @lateral@ !important; }
.stApp [data-testid="stSidebar"] p, .stApp [data-testid="stSidebar"] label,
.stApp [data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
.stApp [data-testid="stSidebar"] h1, .stApp [data-testid="stSidebar"] h2,
.stApp [data-testid="stSidebar"] h3 { color: @texto_lateral@ !important; }
.stApp [data-testid="stSidebar"] input, .stApp [data-testid="stSidebar"] textarea,
.stApp [data-testid="stSidebar"] [data-baseweb="select"] * { color: @texto@ !important; }
.stApp [data-testid="stSidebar"] button[kind="secondary"] p,
.stApp [data-testid="stSidebar"] [data-testid="stAlert"] p { color: @texto@ !important; }
/* Os botões da lateral mantêm a cor de texto escolhida para botões. */
.stApp [data-testid="stSidebar"] button[kind="primary"] *,
.stApp [data-testid="stSidebar"] button[data-testid="stBaseButton-primary"] * {
    color: @texto_botoes@ !important; -webkit-text-fill-color: @texto_botoes@ !important;
}
@media (max-width: 768px) { .stApp .block-container { padding-top: 4.4rem !important; } }
@media print {
    .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] { background: white !important; }
}
</style>
"""
for chave_cor, valor_cor in cores_atuais.items():
    css_aparencia = css_aparencia.replace("@" + chave_cor + "@", valor_cor)
st.markdown(css_aparencia, unsafe_allow_html=True)


# --- PAINEL LATERAL (DEV) — GERADOR DE CHAVES E RESET ---
if (
    empresa_doc == DOCUMENTO_ALENCARSOFT
    and st.session_state.get("autenticado")
    and st.session_state.get("login_efetuado") == "administrador"
):
    with st.sidebar.expander("⚙️ Gerador de Chaves (Dev)"):
        senha_configurada = st.secrets.get("administracao_central", {}).get(
            "senha_dev", empresas_config.get("19417439000142", {}).get("senha_dev", "")
        )
        if not senha_configurada:
            st.info("Configure senha_dev no bloco [administracao_central] dos Secrets.")
        else:
            senha_informada = st.text_input("Senha Mestre Dev", type="password", key="senha_emissor_dev")
            if senha_informada and hmac.compare_digest(senha_informada.encode(), senha_configurada.encode()):
                with st.form("cadastro_empresa_painel", clear_on_submit=True):
                    st.markdown("**Cadastrar nova empresa**")
                    nome_novo = st.text_input("Nome da empresa")
                    documento_novo = st.text_input("CNPJ ou CPF")
                    senha_nova = st.text_input("Senha inicial do administrador", type="password")
                    if st.form_submit_button("Cadastrar empresa"):
                        try:
                            cadastrar_empresa(re.sub(r"[^0-9]", "", documento_novo), nome_novo, senha_nova, empresas_config)
                        except (ValueError, sqlite3.Error, OSError) as erro:
                            st.error(f"Não foi possível cadastrar a empresa: {erro}")
                        else:
                            st.session_state["empresa_cadastrada_ok"] = nome_novo.strip()
                            st.rerun()
                nome_cadastrado = st.session_state.pop("empresa_cadastrada_ok", None)
                if nome_cadastrado:
                    st.success(f"{nome_cadastrado} cadastrada. Já pode gerar a chave.")
                with st.expander("Backups de produção no Supabase"):
                    st.caption("Selecione a empresa para enviar ou baixar uma cópia do banco.")
                    if st.button("Testar conexão com Supabase", key="testar_supabase_piloto"):
                        try:
                            with conectar_supabase_producao() as remoto:
                                tabela = remoto.execute("SELECT to_regclass('crm_producao.backups_sqlite')").fetchone()[0]
                            if tabela:
                                st.success("Conexão confirmada. A tabela de produção está disponível.")
                            else:
                                st.error("Conexão confirmada, mas a tabela de produção precisa ser criada.")
                        except ValueError as erro:
                            st.error(str(erro))
                        except Exception:
                            st.error("Não foi possível conectar. Confira a URI, a senha e o projeto nos Secrets.")
                    empresas_piloto = {
                        doc: e for doc, e in empresas_config.items()
                        if "senha_hash" in e or doc in empresas_backup_automatico
                    }
                    if not empresas_piloto:
                        st.info("Habilite uma empresa para usar os backups no Supabase.")
                    else:
                        doc_piloto = st.selectbox(
                            "Empresa do backup", list(empresas_piloto),
                            format_func=lambda doc: f"{empresas_piloto[doc]['nome']} · {doc}",
                            key="empresa_backup_piloto",
                        )
                        arquivo_piloto = st.file_uploader("Backup da empresa (.db)", type=["db"], key="backup_supabase_piloto")
                        if st.button("Enviar backup e conferir recuperação", key="enviar_supabase_piloto", disabled=arquivo_piloto is None):
                            try:
                                dados = arquivo_piloto.getvalue()
                                gravar_backup_piloto(dados, doc_piloto, arquivo_piloto.name)
                                st.success("Backup gravado no Supabase e recuperado com conteúdo idêntico.")
                            except ValueError as erro:
                                st.error(str(erro))
                            except Exception:
                                st.error("Falha ao enviar ou conferir o backup. Confira a conexão e a tabela de produção.")
                        if st.button("Recuperar último backup do Supabase", key="recuperar_supabase_piloto"):
                            try:
                                with conectar_supabase_producao() as remoto:
                                    registro = remoto.execute(
                                        """SELECT nome_arquivo, conteudo FROM crm_producao.backups_sqlite
                                           WHERE empresa=%s ORDER BY id DESC LIMIT 1""", (doc_piloto,),
                                    ).fetchone()
                                if registro:
                                    dados = bytes(registro[1])
                                    validar_backup_piloto(dados, doc_piloto)
                                    st.download_button(
                                        "Baixar backup recuperado", data=dados,
                                        file_name=f"recuperado_{doc_piloto}.db",
                                        mime="application/octet-stream",
                                        key="download_supabase_piloto",
                                    )
                                else:
                                    st.info("Ainda não há backup dessa empresa no Supabase.")
                            except ValueError as erro:
                                st.error(str(erro))
                            except Exception:
                                st.error("Não foi possível recuperar o backup de produção.")
                documento_destino = st.selectbox(
                    "Empresa que receberá a chave",
                    list(empresas_config),
                    format_func=lambda doc: f"{empresas_config[doc]['nome']} · {doc}",
                    key="empresa_destino_licenca",
                )
                with st.expander("Liberar vaga de um dispositivo"):
                    st.caption("Selecione acima a empresa e escolha apenas o aparelho que deixou de usar.")
                    caminho_destino = Path(empresas_config[documento_destino]["banco"]).resolve()
                    try:
                        with closing(sqlite3.connect(caminho_destino.as_uri() + "?mode=rw", uri=True)) as destino:
                            vinculo = destino.execute("SELECT documento FROM crm_empresa WHERE id = 1").fetchone()
                            if vinculo != (documento_destino,):
                                raise ValueError("Banco não vinculado à empresa selecionada.")
                            ativos = destino.execute(
                                "SELECT device_id FROM empresas_dispositivos WHERE ativado = 1 ORDER BY device_id"
                            ).fetchall()
                            aparelho = st.selectbox(
                                "Identificador do aparelho a desativar", [linha[0] for linha in ativos],
                                index=None, key=f"liberar_aparelho_{documento_destino}",
                            )
                            if st.button("Desativar aparelho selecionado", disabled=aparelho is None,
                                         key=f"desativar_aparelho_{documento_destino}"):
                                with destino:
                                    alterado = destino.execute(
                                        "UPDATE empresas_dispositivos SET ativado = 0 WHERE device_id = ? AND ativado = 1",
                                        (aparelho,),
                                    ).rowcount
                                if alterado:
                                    st.success("Vaga liberada. Gere uma chave para ativar o aparelho atual.")
                                else:
                                    st.info("Este aparelho já está desativado.")
                    except (sqlite3.Error, ValueError):
                        st.info("Abra a empresa no CRM para inicializar seu banco antes de gerenciar aparelhos.")
                planos = {"TESTE": "Teste (7 dias)", "MENSAL": "Mensal (30 dias)", "ANUAL": "Anual (365 dias)"}
                plano = st.selectbox("Plano", list(planos), format_func=planos.get, key="plano_destino_licenca")
                limite = st.number_input("Limite de dispositivos", min_value=1, max_value=50, value=1, key="limite_destino_licenca")
                if st.button("Gerar Chave", key="gerar_licenca_empresa"):
                    chave = emitir_chave_unica(documento_destino, plano, limite, empresas_config[documento_destino])
                    st.code(chave, language="text")
                    st.caption(f"Cole a chave em Ativar / Renovar Licença na empresa {empresas_config[documento_destino]['nome']}.")
            elif senha_informada:
                st.error("Senha de desenvolvedor incorreta.")
elif not empresa_doc:
    with st.sidebar.expander("⚙️ Gerador de Chaves (Dev)"):

        senha_dev = st.text_input(
            "Senha Mestre Dev",
            type="password",
            key="pwd_dev_topo"
        )

        if senha_dev and senha_dev == (
            empresa_config.get("senha_dev") if empresa_doc else "13142715"
        ):

            st.success("Acesso de desenvolvedor liberado!")

            st.markdown("### 🔑 Gerar Chave de Ativação")

            tipo_plano = st.selectbox(
                "Tipo de Chave:",
                ["Teste (1 Dias)", "Teste (7 Dias)", "Mensal (30 Dias)", "Anual (365 Dias)"],
                key="select_tipo_plano_dev"
            )

            doc_cliente = st.text_input(
                "CNPJ ou CPF do Cliente:",
                key="doc_dev_topo_doc"
            )

            limite_dev_topo = st.number_input(
                "Limite de Dispositivos:",
                min_value=1,
                max_value=50,
                value=1,
                key="limite_dev_topo_num"
            )

            if st.button("Gerar Chave", key="btn_dev_topo_acao"):

                if doc_cliente.strip() and (not empresa_doc or re.sub(r"[^0-9]", "", doc_cliente) == empresa_doc):

                    sufixo_tipo = (
                        "TESTE" if "Teste" in tipo_plano
                        else ("MENSAL" if "Mensal" in tipo_plano else "ANUAL")
                    )

                    doc_limpo = ''.join(
                        filter(str.isdigit, str(doc_cliente))
                    )

                    try:
                        cursor = conn.cursor()

                        cursor.execute("""
                            UPDATE empresas_dispositivos
                            SET limite_dispositivos = ?
                            WHERE REPLACE(
                                REPLACE(
                                    REPLACE(cnpj, '.', ''),
                                '/', ''),
                            '-', '') = ?
                        """, (limite_dev_topo, doc_limpo))

                        conn.commit()
                        cursor.close()

                        hash_hex = hash_chave_licenca(doc_limpo, sufixo_tipo, limite_dev_topo)

                        chave_gerada = (
                            f"CRM-{sufixo_tipo}-{limite_dev_topo}D-"
                            f"{hash_hex[:4]}-{hash_hex[4:8]}"
                        )

                        st.code(chave_gerada, language="text")

                        st.success(
                            f"Chave gerada! Limite definido: "
                            f"{limite_dev_topo} dispositivo(s)."
                        )

                    except Exception as e:
                        conn.rollback()
                        st.error(f"Erro ao gerar chave: {e}")

                else:
                    st.warning("Informe o CNPJ ou CPF do cliente.")

            # ------------------------------------------
            # RESETAR DISPOSITIVOS
            # ------------------------------------------

            st.markdown("---")
            st.markdown("### 🗑️ Resetar Dispositivos")

            st.warning(
                "ATENÇÃO: Esta operação desativará TODOS os dispositivos "
                "registrados na tabela empresas_dispositivos, de todas as empresas."
            )

            if st.button(
                "🗑️ RESETAR DISPOSITIVOS",
                key="btn_reset_dispositivos"
            ):
                st.session_state["confirmar_reset_dispositivos"] = True

            if st.session_state.get("confirmar_reset_dispositivos", False):

                confirmar_reset = st.checkbox(
                    "Confirmo que desejo desativar todos os dispositivos.",
                    key="check_confirmar_reset"
                )

                col_reset1, col_reset2 = st.columns(2)

                with col_reset1:
                    if st.button(
                        "CONFIRMAR RESET",
                        key="btn_confirmar_reset"
                    ):

                        if confirmar_reset:
                            try:
                                cursor = conn.cursor()

                                cursor.execute("""
                                    UPDATE empresas_dispositivos
                                    SET ativado = 0
                                """)

                                conn.commit()
                                cursor.close()

                                st.session_state["dispositivo_ativado"] = False
                                st.session_state["confirmar_reset_dispositivos"] = False

                                st.success(
                                    "Todos os dispositivos foram desativados."
                                )

                                st.rerun()

                            except Exception as e:
                                conn.rollback()
                                st.error(f"Erro ao resetar dispositivos: {e}")

                        else:
                            st.warning(
                                "Marque a confirmação antes de continuar."
                            )

                with col_reset2:
                    if st.button(
                        "CANCELAR",
                        key="btn_cancelar_reset"
                    ):
                        st.session_state["confirmar_reset_dispositivos"] = False
                        st.rerun()

        elif senha_dev:
            st.error("Senha de desenvolvedor incorreta.")


# ==========================================
# ACESSO AO SISTEMA
# ==========================================

st.sidebar.title("🔑 Acesso ao Sistema")

st.sidebar.radio(
    "Selecione o Perfil:",
    ["🔒 Administração / Vendedor"],
    key="perfil_principal_radio"
)

st.sidebar.markdown("---")

if st.session_state.get('dispositivo_ativado', False):
    st.sidebar.success("🟢 Dispositivo Ativado")
else:
    st.sidebar.error("🔴 Dispositivo Não Ativado")

st.sidebar.markdown("---")


# ==========================================
# ECRÃ DE LOGIN OU INTERFACE PRINCIPAL
# ==========================================

if not st.session_state['autenticado']:

    st.markdown("## 🔐 Autenticação do Sistema")

    with st.form("form_login_sistema"):

        usuario_input = st.text_input(
            "Usuário / Login",
            key="login_usuario"
        ).strip().lower()

        senha_input = st.text_input(
            "Senha",
            type="password",
            key="login_senha"
        )

        btn_entrar = st.form_submit_button(
            "🟢 Entrar no Sistema",
            type="primary",
            use_container_width=True
        )

        if btn_entrar:

            if credencial_admin_principal(usuario_input, senha_input):

                st.session_state['autenticado'] = True
                st.session_state['usuario_logado'] = "administrador"
                st.session_state['login_efetuado'] = "administrador"
                st.session_state['cargo_logado'] = "Administrador"

                st.session_state['permissoes_usuario'] = {
                    "pdv": 1,
                    "financeiro": 1,
                    "registrar_venda": 1,
                    "compras": 1,
                    "cadastros": 1,
                    "rh": 1,
                    "usuarios": 1,
                    "backup": 1,
                    "contas_receber": 1,
                    "estoque": 1,
                    "configuracoes": 1
                }

                st.success("Login efetuado com sucesso!")
                st.rerun()

            elif empresa_doc and str(usuario_input).strip().lower() == "administrador":
                st.error("Usuário ou senha incorretos.")
            else:

                try:
                    cursor = conn.cursor()

                    cursor.execute("""
                        SELECT
                            id, usuario, login, senha, cargo,
                            perm_pdv, perm_financeiro,
                            perm_registrar_venda, perm_compras,
                            perm_cadastros, perm_rh,
                            perm_usuarios, perm_backup,
                            perm_contas_receber, perm_estoque,
                            perm_configuracoes
                        FROM usuarios
                        WHERE LOWER(TRIM(login)) = ?
                        AND senha = ?
                    """, (usuario_input, senha_input))

                    user_row = cursor.fetchone()
                    cursor.close()

                    if user_row:

                        st.session_state['autenticado'] = True

                        st.session_state['login_efetuado'] = str(
                            user_row[2] if user_row[2] else usuario_input
                        )

                        st.session_state['usuario_logado'] = str(
                            user_row[1] if user_row[1] else usuario_input
                        )

                        st.session_state['cargo_logado'] = str(
                            user_row[4] if user_row[4] else "Funcionário"
                        )

                        def safe_int(val):
                            try:
                                return int(val) if val is not None else 0
                            except:
                                return 0

                        st.session_state['permissoes_usuario'] = {
                            "pdv": safe_int(user_row[5]),
                            "financeiro": safe_int(user_row[6]),
                            "registrar_venda": safe_int(user_row[7]),
                            "compras": safe_int(user_row[8]),
                            "cadastros": safe_int(user_row[9]),
                            "rh": safe_int(user_row[10]),
                            "usuarios": safe_int(user_row[11]),
                            "backup": safe_int(user_row[12]),
                            "contas_receber": safe_int(user_row[13]),
                            "estoque": safe_int(user_row[14]),
                            "configuracoes": safe_int(user_row[15])
                        }

                        st.success("Login efetuado com sucesso!")
                        st.rerun()

                    else:
                        st.error(
                            "❌ Usuário ou senha incorretos. "
                            "Verifique os dados."
                        )

                except Exception as e:
                    st.error(f"Erro ao autenticar: {e}")


else:

    # --- INTERFACE PRINCIPAL APÓS O LOGIN ---

    usr_exibicao = str(
        st.session_state.get('usuario_logado') or "Utilizador"
    )

    login_atual = str(
        st.session_state.get('login_efetuado') or ''
    ).lower()

    st.sidebar.write(f"👤 **Utilizador:** `{usr_exibicao}`")

    if st.sidebar.button("🚪 Sair do Sistema"):

        st.session_state.pop('senha_emissor_dev', None)
        st.session_state['autenticado'] = False
        st.session_state['usuario_logado'] = ""
        st.session_state['login_efetuado'] = ""
        st.session_state['cargo_logado'] = ""
        st.session_state['permissoes_usuario'] = {}

        st.rerun()

    # ==========================================
    # VERIFICAÇÃO DE MESTRE OU PERMISSÕES
    # ==========================================

    is_admin_master = (
        login_atual == "administrador"
        or st.session_state.get('cargo_logado') == "Administrador"
    )

    if is_admin_master:
        if st.session_state.pop("_backup_restaurado_ok", False):
            st.success("Backup restaurado. Os dados restaurados foram carregados.")
        if st.session_state.get("_backup_antes_restauracao"):
            st.download_button(
                "📥 Baixar cópia de segurança anterior à restauração",
                data=st.session_state["_backup_antes_restauracao"],
                file_name="crm_antes_da_restauracao.db",
                mime="application/octet-stream",
                key="download_backup_seguranca",
            )

    perms = st.session_state.get('permissoes_usuario', {})

    opcoes_menu_disponiveis = []

    if is_admin_master or perms.get("pdv", 1) == 1:
        opcoes_menu_disponiveis.append("🛒 PDV — Frente de Caixa")

    if is_admin_master or perms.get("financeiro", 0) == 1:
        opcoes_menu_disponiveis.append("📊 Fechamento & Financeiro")

    if is_admin_master or perms.get("registrar_venda", 1) == 1:
        opcoes_menu_disponiveis.append("🛒 Registrar Venda")

    if is_admin_master or perms.get("compras", 0) == 1:
        opcoes_menu_disponiveis.append("📦 Entrada de Estoque (Compras)")

    if is_admin_master or perms.get("cadastros", 1) == 1:
        opcoes_menu_disponiveis.append(
            "👥 Cadastros (Clientes / Fornecedores / Grupos)"
        )

    if is_admin_master or perms.get("rh", 0) == 1:
        opcoes_menu_disponiveis.append(
            "👥 Gestão de Recursos Humanos (RH)"
        )

    if is_admin_master or perms.get("usuarios", 0) == 1:
        opcoes_menu_disponiveis.append(
            "🔐 Gestão de Utilizadores e Logins"
        )

    if is_admin_master or (not empresa_doc and perms.get("backup", 0) == 1):
        opcoes_menu_disponiveis.append("💾 Backup e Restauração")

    if is_admin_master or perms.get("contas_receber", 1) == 1:
        opcoes_menu_disponiveis.append("💸 Contas a Receber")

    if is_admin_master or perms.get("estoque", 1) == 1:
        opcoes_menu_disponiveis.append("📦 Estoque de Produtos")

    if is_admin_master or perms.get("configuracoes", 0) == 1:
        opcoes_menu_disponiveis.append("🏢 Configurações da Empresa")

    if not opcoes_menu_disponiveis:
        opcoes_menu_disponiveis = ["🛒 PDV — Frente de Caixa"]

    menu_admin = st.sidebar.radio(
        "Navegação",
        opcoes_menu_disponiveis,
        key="radio_menu_admin_opcoes"
    )

    painel_aparencia()

    # ==========================================
    # TRAVA DE SEGURANÇA DE LICENÇA POR DISPOSITIVO
    # ==========================================

    if not dispositivo_esta_ativado and menu_admin != "🏢 Configurações da Empresa":
        if licenca_vencida:
            st.error("🚫 Licença vencida. Solicite ao administrador a renovação em Configurações da Empresa.")
        else:
            st.error("🚫 Dispositivo não ativado. Vá em Configurações da Empresa para inserir a chave.")

        st.stop()
    # -------------------------------------------------------------
    # 1. MÓDULO PDV — FRENTE DE CAIXA
    # -------------------------------------------------------------
    elif menu_admin == "🛒 PDV — Frente de Caixa":
        
        # Inicializa o estado de exibição do cupom
        if 'exibir_cupom_tela' not in st.session_state:
            st.session_state.exibir_cupom_tela = False
        if 'html_cupom_atual' not in st.session_state:
            st.session_state.html_cupom_atual = ""

        # Confirma a venda sem imprimir comprovante, quando essa opção foi escolhida.
        if st.session_state.get("venda_concluida_sem_cupom", False):
            st.success("✅ Venda concluída e registrada com sucesso. Nenhum cupom foi impresso.")
            if st.button("➕ Iniciar Nova Venda", type="primary", use_container_width=True, key="btn_nova_venda_sem_cupom"):
                st.session_state.venda_concluida_sem_cupom = False
                st.session_state.exibir_cupom_tela = False
                st.session_state.html_cupom_atual = ""
                st.session_state.carrinho_temp_para_imprimir = []
                st.rerun()

        # SE O CUPOM NÃO FISCAL ESTIVER ATIVO NA TELA
        elif st.session_state.exibir_cupom_tela:
            st.success("🎉 Venda concluída com sucesso!")
            
            from datetime import datetime
            data_venda = st.session_state.get('data_venda_final', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            vendedor_atual = st.session_state.get('usuario_logado', st.session_state.get('vendedor', 'administrador'))
            
            # Resgata o cliente selecionado no PDV
            cliente_pdv_selecionado = st.session_state.get('cliente_pdv_selecionado', 'Cliente Balcão')
            
            # Busca o documento do cliente na base de dados
            cli_doc_final = "Não informado"
            try:
                if cliente_pdv_selecionado and cliente_pdv_selecionado != "Cliente Balcão":
                    df_cli_busca = carregar_dados(f"SELECT * FROM clientes WHERE nome = '{cliente_pdv_selecionado}' OR cliente = '{cliente_pdv_selecionado}' LIMIT 1")
                    if not df_cli_busca.empty:
                        cli_doc_final = str(df_cli_busca.iloc[0].get('cpf', df_cli_busca.iloc[0].get('cnpj', df_cli_busca.iloc[0].get('documento', 'Não informado'))))
            except Exception:
                pass

            detalhes_pagto = st.session_state.get('detalhes_pagto', 'Não informado')
            texto_troco = ''
            if st.session_state.get('forma_pagto_venda') == 'Dinheiro':
                recebido = float(st.session_state.get('valor_recebido_venda', 0))
                devolvido = float(st.session_state.get('troco_venda', 0))
                texto_troco = f'VALOR RECEBIDO: R$ {recebido:,.2f}\nTROCO: R$ {devolvido:,.2f}\n'

            emp_nome = nome_empresa_header
            emp_cnpj = str(reg_emp.get("cnpj", doc_empresa_padrao))
            emp_end = inscricao_empresa_padrao

            try:
                df_empresa_cupom = carregar_dados("SELECT * FROM empresa LIMIT 1")
                if not df_empresa_cupom.empty:
                    emp_nome = str(df_empresa_cupom.iloc[0].get('nome', emp_nome))
                    emp_end = str(df_empresa_cupom.iloc[0].get('endereco', ''))
            except Exception:
                pass

            carrinho_impresso = st.session_state.get('carrinho_temp_para_imprimir', [])
            
            texto_itens_cupom = ""
            total_geral_calculado = 0.0  
            
            for item in carrinho_impresso:
                prod_nome = str(item.get('produto', 'Item'))
                qtd_val = float(item.get('quantidade', 1.0))
                total_val = float(item.get('valor_total', 0.0))
                total_geral_calculado += total_val  
                total_fmt = f"R$ {total_val:,.2f}"
                texto_itens_cupom += f"- {prod_nome} | Qtd: {quantidade_com_unidade(qtd_val, item.get('unidade'))} | {total_fmt}\n"

            # 3. Monta o texto final do cupom
            conteudo_cupom_texto = f"""
========================================
              CUPOM NÃO FISCAL
           {emp_nome}
       CNPJ: {emp_cnpj}
       INCR. EST: {emp_end}
========================================
Data: {data_venda}
Vendedor: {vendedor_atual}
Cliente: {cliente_pdv_selecionado}
CPF/CNPJ: {cli_doc_final}
----------------------------------------
ITENS DA VENDA:
{texto_itens_cupom}
----------------------------------------
FORMA DE PAGAMENTO: {detalhes_pagto}
TOTAL GERAL: R$ {total_geral_calculado:,.2f}
{texto_troco}========================================
Obrigado pela preferência volte sempre!
O Senhor é meu pastor nada mim faltarar.
========================================
"""

            # 4. Exibe o cupom e os botões
            st.code(conteudo_cupom_texto, language=None)
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            col_b_imp1, col_b_imp2, col_b_imp3 = st.columns([1, 1, 1])
            with col_b_imp1:
                if st.button("🖨️ Imprimir Cupom", use_container_width=True, key="btn_acao_imprimir_nativo"):
                    js_print = "<script>window.parent.print();</script>"
                    st.components.v1.html(js_print, height=0)
            with col_b_imp2:
                st.download_button(
                    label="📥 Baixar Comprovante (TXT)",
                    data=conteudo_cupom_texto,
                    file_name=f"cupom_venda_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain",
                    use_container_width=True,
                    key="btn_download_txt_direto"
                )
            with col_b_imp3:
                if st.button("➕ Iniciar Nova Venda", type="primary", use_container_width=True, key="btn_nova_venda_reset"):
                    st.session_state.exibir_cupom_tela = False
                    st.session_state.html_cupom_atual = ""
                    st.session_state.carrinho_temp_para_imprimir = []
                    st.rerun()
        
        else:
            # Visual do PDV inspirado no modelo aprovado.
            st.markdown("""<style>
            .stApp:has(.pdv-identidade){background:#eaf2fc!important;color:#102f55!important}
            .stApp:has(.pdv-identidade) .block-container{padding:1rem 1rem 1rem;max-width:100%}
            /* Mantém o controle nativo de reabertura do menu acessível. */
            .stApp:has(.pdv-identidade) [data-testid="stHeader"]{display:block!important;background:transparent!important;height:2.8rem}
            .stApp:has(.pdv-identidade) [data-testid="stSidebarCollapsedControl"],
            .stApp:has(.pdv-identidade) [data-testid="collapsedControl"]{display:flex!important;visibility:visible!important;z-index:1000001;background:#e0eafa;border-radius:7px}
            .stApp:has(.pdv-identidade) [data-testid="stMainBlockContainer"],
            .stApp:has(.pdv-identidade) .block-container{max-width:100%!important;width:100%!important;padding:3rem 1rem .75rem!important;box-sizing:border-box}
            .stApp:has(.pdv-identidade) [data-testid="stSidebar"]{min-width:0!important}
            .pdv-identidade{flex-wrap:wrap;row-gap:5px}
            .pdv-identidade span{font-size:clamp(13px,1.35vw,20px)}
            .stApp:has(.pdv-identidade) .st-key-pdv_grade{height:clamp(260px,49vh,540px)!important}
            .stApp:has(.pdv-identidade) .st-key-pdv_carrinho{height:clamp(210px,37vh,410px)!important}
            .stApp:has(.pdv-identidade) [class*="st-key-pdv_card_"] button p{white-space:normal!important;overflow:visible!important;text-overflow:clip!important;line-height:1.2!important;font-size:13px!important}
            @media(max-width:1000px){
              .pdv-identidade{gap:8px;padding:12px;font-size:18px}
              .pdv-identidade small{font-size:12px}
              .stApp:has(.pdv-identidade) [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .pdv-faixa){flex-wrap:wrap!important}
              .stApp:has(.pdv-identidade) [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .pdv-faixa)>[data-testid="stColumn"]{width:100%!important;flex:1 1 100%!important;min-width:0!important}
            }
            @media(max-width:640px){
              .stApp:has(.pdv-identidade) .block-container{padding:3rem .5rem .5rem!important}
              .pdv-identidade{font-size:16px;gap:6px}.pdv-identidade small{width:100%;margin:0}
              .stApp:has(.pdv-identidade) .st-key-pdv_grade [data-testid="stHorizontalBlock"]{flex-wrap:wrap!important}
              .stApp:has(.pdv-identidade) .st-key-pdv_grade [data-testid="stColumn"]{flex:1 1 45%!important;width:45%!important;min-width:0!important}
              .pdv-foto{height:85px}.pdv-foto img{height:80px}.pdv-total{font-size:22px}
            }
            .stApp:has(.pdv-identidade) [data-testid="stSidebar"]{background:linear-gradient(#103b6c,#092949)!important;min-width:195px;max-width:215px}
            .stApp:has(.pdv-identidade) [data-testid="stVerticalBlock"]{gap:.45rem}
            .pdv-identidade{display:flex;align-items:center;gap:18px;background:linear-gradient(105deg,#07366a,#061e40);color:white;padding:17px 20px;border-radius:8px;margin-bottom:8px;font-size:clamp(15px,1.7vw,23px);font-weight:800}
            .pdv-identidade strong{color:#ffe42c}.pdv-identidade small{margin-left:auto;font-size:13px;color:white}
            .pdv-faixa{background:linear-gradient(90deg,#07417d,#092c52);padding:12px;color:white;border-radius:8px 8px 0 0;font-size:23px;font-weight:800}
            .pdv-foto{height:100px;display:flex;align-items:center;justify-content:center;background:white;border:1px solid #d3dfed;border-radius:9px 9px 0 0;overflow:hidden}
            .pdv-foto img{width:100%;height:96px;object-fit:contain}.pdv-foto span{font-size:66px}
            .pdv-total{background:#082f5b;color:white;border-radius:9px;padding:14px;font-size:27px;font-weight:800;display:flex;justify-content:space-between}.pdv-total strong{color:#ffe72c}
            .pdv-subtotal{background:#dfebfa;padding:10px 14px;color:#092b51;font-weight:700;display:flex;justify-content:space-between}
            /* Tabela do carrinho: regras locais prevalecem sobre o tema metálico. */
            .stApp:has(.pdv-identidade) .st-key-pdv_carrinho,
            .stApp:has(.pdv-identidade) .st-key-pdv_carrinho [data-testid="stVerticalBlockBorderWrapper"],
            .stApp:has(.pdv-identidade) .st-key-pdv_carrinho [data-testid="stVerticalBlock"]{
                background:#fff!important;border-color:#d5deeb!important;border-radius:0!important;gap:0!important}
            .stApp:has(.pdv-identidade) .st-key-pdv_carrinho{padding:0!important;border:1px solid #c3d4e9!important;border-top:0!important;border-radius:0 0 8px 8px!important}
            .stApp:has(.pdv-identidade) .st-key-pdv_cabecalho_carrinho,
            .stApp:has(.pdv-identidade) .st-key-pdv_cabecalho_carrinho [data-testid="stVerticalBlock"]{background:#e6ebf2!important}
            /* Linhas inteiras recebem as divisórias, inclusive entre widgets. */
            .stApp:has(.pdv-identidade) .st-key-pdv_cabecalho_carrinho,
            .stApp:has(.pdv-identidade) [class*="st-key-pdv_linha_carrinho_"]{
                border-bottom:1px solid #c9d5e5!important;border-radius:0!important;padding:0!important;
                background-image:linear-gradient(to right,transparent calc(30.137% - 1px),#c9d5e5 calc(30.137% - 1px),#c9d5e5 30.137%,transparent 30.137%,transparent calc(57.534% - 1px),#c9d5e5 calc(57.534% - 1px),#c9d5e5 57.534%,transparent 57.534%,transparent calc(75.342% - 1px),#c9d5e5 calc(75.342% - 1px),#c9d5e5 75.342%,transparent 75.342%,transparent calc(93.151% - 1px),#c9d5e5 calc(93.151% - 1px),#c9d5e5 93.151%,transparent 93.151%)!important}
            .stApp:has(.pdv-identidade) .st-key-pdv_cabecalho_carrinho{background-color:#e6ebf2!important}
            .stApp:has(.pdv-identidade) [class*="st-key-pdv_linha_carrinho_"]{background-color:white!important}
            .stApp:has(.pdv-identidade) .st-key-pdv_cabecalho_carrinho [data-testid="stVerticalBlock"],
            .stApp:has(.pdv-identidade) [class*="st-key-pdv_linha_carrinho_"] [data-testid="stVerticalBlock"]{background:transparent!important}
            .stApp:has(.pdv-identidade) .st-key-pdv_cabecalho_carrinho [data-testid="stHorizontalBlock"],
            .stApp:has(.pdv-identidade) [class*="st-key-pdv_linha_carrinho_"] [data-testid="stHorizontalBlock"]{gap:0!important;align-items:center!important;flex-wrap:nowrap!important}
            .stApp:has(.pdv-identidade) .st-key-pdv_cabecalho_carrinho [data-testid="stColumn"],
            .stApp:has(.pdv-identidade) [class*="st-key-pdv_linha_carrinho_"] [data-testid="stColumn"]{border:0!important;min-width:0!important;padding:6px!important;display:flex;align-items:center;align-self:stretch}
            .stApp:has(.pdv-identidade) [class*="st-key-pdv_linha_carrinho_"] [data-testid="stHorizontalBlock"] [data-testid="stHorizontalBlock"] [data-testid="stColumn"]{padding:0!important}
            .stApp:has(.pdv-identidade) .st-key-pdv_cabecalho_carrinho{min-height:45px}
            .stApp:has(.pdv-identidade) [class*="st-key-pdv_linha_carrinho_"]{min-height:62px}
            .stApp:has(.pdv-identidade) .st-key-pdv_carrinho p,
            .stApp:has(.pdv-identidade) .st-key-pdv_carrinho b,
            .stApp:has(.pdv-identidade) .st-key-pdv_carrinho [data-testid="stCaptionContainer"] p{color:#122844!important;font-size:17px!important;line-height:1.35!important;margin:0!important}
            .stApp:has(.pdv-identidade) .st-key-pdv_cabecalho_carrinho p{font-size:16px!important;font-weight:800!important}
            .pdv-produto-carrinho{display:flex;align-items:center;gap:8px;min-height:48px;color:#122844}
            .pdv-produto-carrinho img{width:42px;height:42px;object-fit:contain;flex-shrink:0}
            .pdv-produto-carrinho span{font-size:36px;line-height:1}
            .pdv-produto-carrinho b{font-size:17px!important;overflow-wrap:anywhere}
            .stApp:has(.pdv-identidade) .st-key-pdv_carrinho [class*="st-key-pdv_menos_"] button,
            .stApp:has(.pdv-identidade) .st-key-pdv_carrinho [class*="st-key-pdv_mais_"] button{background:#1468e8!important;color:white!important;border:0!important;border-radius:5px!important;min-width:26px!important;min-height:29px!important;padding:0!important;height:29px!important}
            .stApp:has(.pdv-identidade) .st-key-pdv_carrinho [class*="st-key-pdv_remover_"] button{background:#ed293b!important;border:0!important;border-radius:50%!important;width:26px!important;min-width:26px!important;height:26px!important;min-height:26px!important;padding:0!important}
            .stApp:has(.pdv-identidade) .st-key-pdv_carrinho button p{color:white!important;font-size:19px!important}
            .stApp:has(.pdv-identidade) .st-key-pdv_carrinho [data-testid="stCaptionContainer"]{text-align:center;white-space:normal}
            .pdv-subtotal{font-size:21px!important;padding:12px 14px!important;border:1px solid #c5d7ed}
            .pdv-total{font-size:32px!important;padding:14px!important;border:1px solid #12579e}
            @media(max-width:640px){
                .stApp:has(.pdv-identidade) .st-key-pdv_carrinho p,
                .stApp:has(.pdv-identidade) .st-key-pdv_carrinho b,
                .stApp:has(.pdv-identidade) .st-key-pdv_carrinho [data-testid="stCaptionContainer"] p{font-size:13px!important}
                .pdv-produto-carrinho img{width:28px;height:28px}.pdv-produto-carrinho{gap:3px}
                .stApp:has(.pdv-identidade) .st-key-pdv_carrinho{overflow-x:auto!important;min-width:0}
            }
            .pdv-rodape{background:#dce9fa;padding:10px;border-radius:6px;color:#183d64;font-size:13px}
            .stApp:has(.pdv-identidade) .stButton button{border-radius:7px;border:1px solid #b5cdef;font-weight:700;background:#1267dd;color:white!important;min-height:38px}
            .stApp:has(.pdv-identidade) .stButton button p{color:white!important}
            .stApp:has(.pdv-identidade) [class*="st-key-pdv_card_"] button{background:linear-gradient(#25a623,#108613);width:100%;min-height:48px;font-size:14px;white-space:pre-line}
            .stApp:has(.pdv-identidade) .st-key-btn_fin_venda_alin button{background:linear-gradient(#08a50d,#008000)!important;border:2px solid #90df3b;min-height:72px;font-size:23px}
            .stApp:has(.pdv-identidade) [data-testid="stTextInput"] input{background:#fff;color:#14375e}
            </style>""", unsafe_allow_html=True)
            st.markdown(f"<div class='pdv-identidade'>🛒 CRM Comércio <strong>{html.escape(str(nome_empresa_header))}</strong> <span>│ PDV – Frente de Caixa</span><small>👤 {html.escape(str(usr_exibicao))}</small></div>", unsafe_allow_html=True)
            is_simples = False
            df_caixa_aberto = carregar_dados("SELECT * FROM caixa_sessoes WHERE status = 'ABERTO'")
            if df_caixa_aberto.empty:
                st.warning("Abra o caixa para finalizar vendas.")

            # --- SELEÇÃO DE CLIENTE CADASTRADO NO TOPO DO PDV ---
            try:
                lista_cli_cadastrados = carregar_coluna("clientes", "nome")
                if not lista_cli_cadastrados:
                    lista_cli_cadastrados = carregar_coluna("clientes", "cliente") or carregar_coluna("clientes", "razao_social")
            except Exception:
                lista_cli_cadastrados = []

            opcoes_clientes = ["Cliente Balcão"]
            if lista_cli_cadastrados:
                for c in lista_cli_cadastrados:
                    if c and str(c) not in opcoes_clientes:
                        opcoes_clientes.append(str(c))

            col_c1, col_c2 = st.columns([2, 1])
            with col_c1:
                cliente_pdv_selecionado = st.selectbox(
                    "👤 Selecione o Cliente da Venda:", 
                    options=opcoes_clientes, 
                    key="select_cliente_pdv_topo_final"
                )
                # Salva na sessão para o cupom resgatar
                st.session_state['cliente_pdv_selecionado'] = cliente_pdv_selecionado

            try:
                df_prod_pdv = pd.read_sql_query("SELECT * FROM produtos", conn)
                lista_produtos_pdv = df_prod_pdv['produto'].tolist() if not df_prod_pdv.empty else []
            except Exception:
                lista_produtos_pdv = []
                df_prod_pdv = pd.DataFrame()

            def obter_dados_produto(nome_prod):
                if not df_prod_pdv.empty and nome_prod in lista_produtos_pdv:
                    p_row = df_prod_pdv[df_prod_pdv['produto'] == nome_prod].iloc[0]
                    val_v = float(p_row.get('valor_venda', 0.0) or p_row.get('venda', 0.0) or 0.0)
                    cod_prod = str(p_row.get('codigo', ''))
                    prod_id = int(p_row.get('id', 0))
                    return val_v, str(p_row.get('fornecedor', '')), str(p_row.get('grupo', '')), cod_prod, prod_id
                return 0.0, "", "", "", 0

            def obter_produto_por_codigo(cod):
                if not df_prod_pdv.empty and 'codigo' in df_prod_pdv.columns:
                    match = df_prod_pdv[df_prod_pdv['codigo'].astype(str).str.strip() == str(cod).strip()]
                    if not match.empty:
                        return str(match.iloc[0]['produto'])
                return ""

            def moeda_pdv(valor):
                return "R$ " + f"{float(valor):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")

            @st.dialog("Incluir produto", width="small", dismissible=False)
            def selecionar_cartao_pdv(produto_id):
                produto = df_prod_pdv[df_prod_pdv['id'] == produto_id].iloc[0]
                unidade = normalizar_unidade_medida(produto.get('unidade'))
                rotulo = rotulo_unidade_medida(unidade)
                st.markdown(f"### {produto['produto']}")
                st.caption(f"{moeda_pdv(produto.get('valor_venda', 0))} por {rotulo} • Estoque: {quantidade_com_unidade(produto.get('quantidade', 0), unidade)}")
                quantidade = st.number_input(f"Quantidade ({rotulo})", min_value=0.001, value=1.0,
                    step=0.001 if unidade in {'KG','LITRO','METRO','GRAMA'} else 1.0,
                    format="%.3f", key=f"pdv_qtd_card_{produto_id}")
                preco = float(produto.get('valor_venda', 0) or 0)
                grupo = str(produto.get('grupo') or '')
                promos = carregar_dados(f"SELECT * FROM promocoes WHERE produto_id={int(produto_id)} AND ativo=1")
                ja_incluido = sum(float(i['quantidade']) for i in st.session_state.carrinho_pdv if i.get('produto_id') == produto_id)
                if not promos.empty:
                    promo = promos.iloc[0]
                    if quantidade >= float(promo['qtd_minima']) and quantidade + ja_incluido <= float(promo['qtd_estoque_promo']):
                        preco = float(promo['preco_promo'])
                        grupo = 'PROMOÇÃO'
                        st.info("Preço promocional aplicado.")
                st.markdown(f"**Subtotal: {moeda_pdv(quantidade * preco)}**")
                if st.button("➕ Incluir no carrinho", type="primary", use_container_width=True, key="pdv_incluir_card"):
                    try:
                        incluir_com_estoque(conn, st.session_state.carrinho_pdv, {
                            'produto_id':int(produto_id), 'produto':str(produto['produto']),
                            'codigo':str(produto.get('codigo') or ''), 'unidade':unidade,
                            'fornecedor':str(produto.get('fornecedor') or ''), 'grupo':grupo,
                            'quantidade':quantidade, 'valor_unitario':preco, 'valor_total':quantidade*preco})
                    except ValueError as erro:
                        st.error(str(erro))
                    else:
                        st.session_state.pop('pdv_produto_em_edicao', None)
                        st.rerun()
                if st.button("Voltar aos produtos", key="pdv_cancelar_card"):
                    st.session_state.pop('pdv_produto_em_edicao', None)
                    st.rerun()

            col_pdv_produtos, col_pdv_carrinho = st.columns([1.04, 1], gap="medium")
            with col_pdv_produtos:
                busca_col, codigo_col = st.columns([3, 1.25])
                with busca_col:
                    busca_pdv = st.text_input("Buscar produto", placeholder="🔎 Buscar produto...", label_visibility="collapsed", key="pdv_busca_grade")
                with codigo_col:
                    codigo_pdv = st.text_input("Ler código", placeholder="▥ Ler código", label_visibility="collapsed", key="pdv_codigo_grade")
                grupos_pdv = ['Todos'] + sorted({str(g) for g in df_prod_pdv.get('grupo', []) if pd.notna(g) and str(g).strip()})
                grupo_filtro = st.radio("Categorias", grupos_pdv, horizontal=True, label_visibility="collapsed", key="pdv_grupo_grade")
                filtrados = df_prod_pdv.copy()
                if not filtrados.empty:
                    if busca_pdv.strip():
                        filtrados = filtrados[filtrados['produto'].astype(str).str.contains(busca_pdv.strip(), case=False, regex=False)]
                    if codigo_pdv.strip():
                        filtrados = filtrados[filtrados['codigo'].fillna('').astype(str).str.strip() == codigo_pdv.strip()]
                    if grupo_filtro != 'Todos':
                        filtrados = filtrados[filtrados['grupo'].astype(str) == grupo_filtro]
                pagina_max = max(1, (len(filtrados)+11)//12)
                pagina = min(int(st.session_state.get('pdv_pagina_grade', 1)), pagina_max)
                if pagina_max > 1:
                    pagina = int(st.number_input("Página de produtos", min_value=1, max_value=pagina_max, value=pagina, step=1))
                    st.session_state.pdv_pagina_grade = pagina
                with st.container(height=390, border=False, key="pdv_grade"):
                    if filtrados.empty:
                        st.info("Nenhum produto encontrado.")
                    registros = list(filtrados.iloc[(pagina-1)*12:pagina*12].iterrows())
                    for inicio in range(0, len(registros), 4):
                        colunas = st.columns(4, gap="small")
                        for coluna, (_, produto) in zip(colunas, registros[inicio:inicio+4]):
                            with coluna:
                                foto = produto.get('imagem_produto')
                                if isinstance(foto, (bytes,bytearray,memoryview)) and len(foto):
                                    imagem = "<img src='data:image/jpeg;base64," + base64.b64encode(bytes(foto)).decode() + "'>"
                                else:
                                    imagem = f"<span>{icone_automatico_produto(produto['produto'])}</span>"
                                st.markdown(f"<div class='pdv-foto'>{imagem}</div>", unsafe_allow_html=True)
                                if st.button(f"{produto['produto']}\n{moeda_pdv(produto.get('valor_venda',0))} / {rotulo_unidade_medida(produto.get('unidade'))}",
                                             key=f"pdv_card_{int(produto['id'])}", use_container_width=True):
                                    st.session_state.pdv_produto_em_edicao = int(produto['id'])
                                    st.rerun()
                if st.button("🗑 Limpar Carrinho", use_container_width=True, key="btn_limpar_cart_alin"):
                    st.session_state.carrinho_pdv = []
                    st.session_state.tela_checkout_ativa = False
                    st.rerun()

            with col_pdv_carrinho:
                total_geral_carrinho = sum(item['valor_total'] for item in st.session_state.carrinho_pdv) if st.session_state.carrinho_pdv else 0.0
                st.markdown("<div class='pdv-faixa'>🛒 Carrinho de Compras</div>", unsafe_allow_html=True)
                with st.container(height=290, border=True, key="pdv_carrinho"):
                    if not st.session_state.carrinho_pdv:
                        st.caption("Selecione um produto para começar a venda.")
                    else:
                        with st.container(key="pdv_cabecalho_carrinho"):
                            cabecalho = st.columns([2.2,2,1.3,1.3,.5])
                            for coluna, titulo in zip(cabecalho,['Produto','Qtd.','Valor Unit.','Valor Total','']):
                                coluna.markdown(f"**{titulo}**")
                        for indice, item in enumerate(st.session_state.carrinho_pdv):
                            with st.container(key=f"pdv_linha_carrinho_{indice}"):
                                linha = st.columns([2.2,2,1.3,1.3,.5], gap="small")
                                foto_carrinho = None
                                encontrados_foto = df_prod_pdv[df_prod_pdv['id'] == item.get('produto_id')]
                                if not encontrados_foto.empty:
                                    foto_carrinho = encontrados_foto.iloc[0].get('imagem_produto')
                                if isinstance(foto_carrinho, (bytes, bytearray, memoryview)) and len(foto_carrinho):
                                    miniatura = "<img src='data:image/jpeg;base64," + base64.b64encode(bytes(foto_carrinho)).decode() + "'>"
                                else:
                                    miniatura = f"<span>{icone_automatico_produto(item['produto'])}</span>"
                                linha[0].markdown(f"<div class='pdv-produto-carrinho'>{miniatura}<b>{html.escape(str(item['produto']))}</b></div>", unsafe_allow_html=True)
                                with linha[1]:
                                    menos, quantidade_col, mais = st.columns([1,1.5,1], gap="small")
                                    quantidade_col.caption(quantidade_com_unidade(item['quantidade'],item.get('unidade')))
                                    passo = 0.001 if normalizar_unidade_medida(item.get('unidade')) in {'KG','LITRO','METRO','GRAMA'} else 1.0
                                    reduzir = menos.button("−",key=f"pdv_menos_{indice}")
                                    aumentar = mais.button("+",key=f"pdv_mais_{indice}")
                                    if reduzir or aumentar:
                                        from decimal import Decimal
                                        nova = float(Decimal(str(item['quantidade'])) + Decimal(str(passo)) * (1 if aumentar else -1))
                                        if nova <= 0:
                                            st.session_state.carrinho_pdv.pop(indice)
                                            st.rerun()
                                        alterado = dict(item, quantidade=nova, valor_total=round(nova * float(item['valor_unitario']), 6))
                                        proposta = [alterado if j == indice else i for j,i in enumerate(st.session_state.carrinho_pdv)]
                                        try:
                                            conferir_estoque_carrinho(conn, proposta)
                                        except ValueError as erro:
                                            st.error(str(erro))
                                        else:
                                            st.session_state.carrinho_pdv = proposta
                                            st.rerun()
                                linha[2].write(moeda_pdv(item['valor_unitario']))
                                linha[3].markdown(f"**{moeda_pdv(item['valor_total'])}**")
                                if linha[4].button("✕",key=f"pdv_remover_{indice}",help="Retirar produto"):
                                    st.session_state.carrinho_pdv.pop(indice)
                                    st.rerun()
                st.markdown(f"<div class='pdv-subtotal'><span>Subtotal:</span><span>{moeda_pdv(total_geral_carrinho)}</span></div><div class='pdv-total'><span>Total:</span><strong>{moeda_pdv(total_geral_carrinho)}</strong></div>", unsafe_allow_html=True)
                if st.button("▣ Finalizar Venda ❯", type="primary", use_container_width=True, key="btn_fin_venda_alin", disabled=not st.session_state.carrinho_pdv):
                    if not df_caixa_aberto.empty:
                        try:
                            conferir_estoque_carrinho(conn, st.session_state.carrinho_pdv)
                        except ValueError as erro:
                            st.error(str(erro))
                        else:
                            st.session_state.tela_checkout_ativa = True
                            st.rerun()
                    else:
                        st.error("Abra o caixa antes de finalizar.")

                if st.session_state.carrinho_pdv:
                    # --- TELA DE CHECKOUT / FORMA DE PAGAMENTO DINÂMICA ---
                    @st.dialog("💳 Pagamento da venda", width="large", dismissible=False)
                    def abrir_pagamento_pdv():
                        st.markdown("""<style>
                        [data-testid="stDialog"] [role="dialog"]:has(.pagamento-resumo){max-height:92vh;overflow-y:auto}
                        .pagamento-resumo{display:flex;justify-content:space-between;align-items:center;gap:16px;background:linear-gradient(110deg,#103e70,#082544);border-radius:10px;padding:18px;color:white;margin:0 0 15px}
                        .pagamento-resumo small{display:block;color:#d9e8fa;font-size:14px}.pagamento-resumo strong{color:#ffe82b;font-size:32px;white-space:nowrap}.pagamento-resumo b{font-size:17px;color:white}
                        [data-testid="stDialog"] .st-key-radio_forma_pagto_checkout [role="radiogroup"]{display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px!important}
                        [data-testid="stDialog"] .st-key-radio_forma_pagto_checkout [role="radiogroup"] label{display:flex!important;align-items:center;justify-content:center;background:#eaf0f7!important;border:2px solid #9caec4!important;border-radius:10px;padding:16px 10px!important;min-height:74px;margin:0!important;cursor:pointer;transition:background .15s,border-color .15s}
                        [data-testid="stDialog"] .st-key-radio_forma_pagto_checkout label:has(input:checked){background:#d3e8ff!important;border-color:#1467cc!important;box-shadow:0 0 0 1px #1467cc}
                        [data-testid="stDialog"] .st-key-radio_forma_pagto_checkout label:hover{border-color:#1467cc!important;background:#dceafa!important}
                        [data-testid="stDialog"] .st-key-radio_forma_pagto_checkout label p{font-size:19px!important;font-weight:700!important;color:#12385f!important;line-height:1.4!important}
                        [data-testid="stDialog"] .st-key-radio_forma_pagto_checkout label input{accent-color:#1467cc}
                        [data-testid="stDialog"] .st-key-input_val_recebido_dinheiro input{font-size:23px!important;font-weight:700!important}
                        [data-testid="stDialog"] .st-key-btn_confirmar_pagto_final button{min-height:52px!important;background:#08734e!important}
                        [data-testid="stDialog"] .st-key-btn_voltar_pdv_check button{min-height:52px!important}
                        @media(max-width:600px){
                          [data-testid="stDialog"] .st-key-radio_forma_pagto_checkout [role="radiogroup"]{grid-template-columns:repeat(2,minmax(0,1fr))}
                          [data-testid="stDialog"] .st-key-radio_forma_pagto_checkout label{min-height:64px;padding:10px 6px!important}
                          [data-testid="stDialog"] .st-key-radio_forma_pagto_checkout label p{font-size:16px!important}
                          .pagamento-resumo{padding:12px;flex-wrap:wrap}.pagamento-resumo strong{font-size:27px}
                        }
                        </style>""", unsafe_allow_html=True)
                        st.markdown(f"<div class='pagamento-resumo'><div><small>Cliente</small><b>{html.escape(str(cliente_pdv_selecionado))}</b></div><div><small>Total a pagar</small><strong>{moeda_pdv(total_geral_carrinho)}</strong></div></div>", unsafe_allow_html=True)
                        icones_pagamento = {'Dinheiro':'💵 Dinheiro', 'Cartão Débito':'💳 Cartão de débito',
                                            'Cartão Crédito':'💳 Cartão de crédito', 'Fiado':'📒 Fiado',
                                            'Parcelado':'📅 Parcelado', 'Pix':'📱 Pix'}
                    
                        forma_pagto = st.radio(
                            "Selecione a Forma de Pagamento:", 
                            ["Dinheiro", "Cartão Débito", "Cartão Crédito", "Fiado", "Parcelado", "Pix"], 
                            horizontal=True, 
                            key="radio_forma_pagto_checkout",
                            format_func=lambda forma: icones_pagamento[forma]
                        )

                        with st.expander("🧾 Comprovante da venda", expanded=False):
                            tipo_documento_pdv = st.radio(
                                "Escolha uma opção:",
                                ["Cupom não fiscal", "Não imprimir cupom", "NFC-e fiscal"],
                                index=0,
                                key="radio_tipo_documento_pdv",
                                help="O cupom não fiscal é apenas comprovante comercial. A NFC-e só poderá ser liberada depois da integração e autorização da SEFAZ."
                            )
                        if tipo_documento_pdv == "NFC-e fiscal":
                            st.warning(
                                "A emissão de NFC-e ainda não está habilitada neste sistema. "
                                "Faltam integração de transmissão, certificado A1, CSC, credenciamento "
                                "na SEFAZ-MA e configuração tributária dos produtos. "
                                "Escolha uma das outras opções para concluir esta venda."
                            )

                        valor_recebido = 0.0
                        troco = 0.0
                        detalhes_pagto = forma_pagto

                        if forma_pagto == "Dinheiro":
                            valor_recebido = st.number_input("Valor Recebido em Dinheiro (R$)", min_value=0.0, value=float(total_geral_carrinho), format="%.2f", key="input_val_recebido_dinheiro")
                            troco = valor_recebido - total_geral_carrinho
                            if troco >= 0:
                                st.success(f"💵 **Troco a Devolver:** R$ {troco:,.2f}")
                            else:
                                st.warning(f"⚠️ Falta R$ {abs(troco):,.2f} para completar o pagamento.")

                        elif forma_pagto == "Cartão Crédito":
                            parcelas = st.selectbox("Número de Parcelas:", ["1x (À vista)", "2x", "3x", "4x", "5x", "6x", "10x", "12x"], key="select_parcelas_cartao")
                            detalhes_pagto = f"Cartão Crédito ({parcelas})"
                            st.info(f"💳 Pagamento selecionado: **Cartão Crédito em {parcelas}**")

                        elif forma_pagto == "Cartão Débito":
                            st.info("💳 Pagamento via **Cartão de Débito** à vista.")

                        elif forma_pagto == "Fiado":
                            from datetime import timedelta
                            data_venc_padrao = datetime.now().date() + timedelta(days=30)
                            data_vencimento_fiado = st.date_input(
                                "📅 Data de Vencimento do Fiado:",
                                value=data_venc_padrao,
                                format="DD/MM/YYYY",
                                key="input_data_venc_fiado"
                            )
                            data_venc_str = data_vencimento_fiado.strftime('%d/%m/%Y')
                            detalhes_pagto = f"Fiado (Venc: {data_venc_str})"
                            st.warning(f"⚠️ Esta venda será registada como **Fiado** para o cliente **{cliente_pdv_selecionado}** com vencimento em **{data_venc_str}**.")

                        elif forma_pagto == "Parcelado":
                            num_parc = st.number_input("Quantidade de Parcelas Próprias:", min_value=2, max_value=24, value=2, step=1, key="num_parc_proprias")
                            valor_parc = total_geral_carrinho / num_parc
                            detalhes_pagto = f"Parcelado ({num_parc}x de R$ {valor_parc:,.2f})"
                            primeiro_vencimento_parcelado = st.date_input("Vencimento da primeira parcela", value=date.today() + dt.timedelta(days=30), format="DD/MM/YYYY", key="vencimento_primeira_parcela_pdv")
                            parcelas_pdv = montar_parcelas_pdv(total_geral_carrinho, num_parc, primeiro_vencimento_parcelado)
                            st.caption("Parcelas mensais; diferenças de centavos ficam na última parcela.")
                            st.dataframe(pd.DataFrame(parcelas_pdv).rename(columns={'numero': 'Parcela', 'valor': 'Valor (R$)', 'vencimento': 'Vencimento'}), hide_index=True, use_container_width=True)

                        elif forma_pagto == "Pix":
                            st.markdown("### 📱 Pague com Pix (QR Code Oficial)")
                            df_chaves_db = carregar_dados("SELECT * FROM chaves_pix")
                        
                            if df_chaves_db.empty and empresa_doc:
                                st.warning("Cadastre a chave Pix da empresa antes de usar esta opção.")
                                st.stop()
                            if df_chaves_db.empty:
                                lista_opcoes_pix = ["CNPJ Padrão: 19417439000142"]
                                dict_chaves = {"CNPJ Padrão: 19417439000142": {"tipo": "CNPJ", "chave": "19417439000142", "favorecido": nome_empresa_header, "cidade": "SAO LUIS"}}
                            else:
                                dict_chaves = {}
                                lista_opcoes_pix = []
                                for idx, row in df_chaves_db.iterrows():
                                    rotulo = f"[{row['tipo']}] {row['chave']} - {row['favorecido']}"
                                    lista_opcoes_pix.append(rotulo)
                                    dict_chaves[rotulo] = row

                            chave_escolhida_label = st.selectbox("Escolha a Chave Pix para esta venda:", lista_opcoes_pix, key="select_chave_pix_venda")
                            dados_chave_atual = dict_chaves[chave_escolhida_label]

                            pix_key_val = str(dados_chave_atual['chave'])
                            fav_val = str(dados_chave_atual['favorecido'])
                            cidade_val = str(dados_chave_atual['cidade'])
                            tipo_val = str(dados_chave_atual['tipo'])

                            def gerar_payload_pix(pix_key, nome_recebedor, cidade, valor_str, tipo_chave_pix):
                                if tipo_chave_pix in ["CNPJ", "CPF"]:
                                    chave_tratada = ''.join(filter(str.isdigit, pix_key))
                                else:
                                    chave_tratada = pix_key.strip()
                                import unicodedata
                                nfkd = unicodedata.normalize('NFKD', nome_recebedor)
                                nome_tratado = "".join([c for c in nfkd if not unicodedata.combining(c)]).upper()[:25]
                                cidade_tratada = "".join([c for c in unicodedata.normalize('NFKD', cidade) if not unicodedata.combining(c)]).upper()[:15]
                                def mc(id_c, val_c):
                                    return f"{id_c}{len(val_c):02d}{val_c}"
                                gui = mc("00", "br.gov.bcb.pix")
                                chave_f = mc("01", chave_tratada)
                                merchant_account = mc("26", gui + chave_f)
                                payload = (
                                    mc("00", "01") + mc("01", "12") + merchant_account +
                                    mc("52", "0000") + mc("53", "986") + mc("54", valor_str) +
                                    mc("58", "BR") + mc("60", nome_tratado) + mc("61", cidade_tratada) +
                                    mc("62", mc("05", "***")) + "6304"
                                )
                                crc = 0xFFFF
                                for char in payload:
                                    crc ^= (ord(char) << 8)
                                    for _ in range(8):
                                        if crc & 0x8000:
                                            crc = (crc << 1) ^ 0x1021
                                        else:
                                            crc = crc << 1
                                        crc &= 0xFFFF
                                return payload + f"{crc:04X}"

                            valor_formatado = f"{total_geral_carrinho:.2f}"
                            pix_payload = gerar_payload_pix(pix_key_val, fav_val, cidade_val, valor_formatado, tipo_val)
                            qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={pix_payload}"
                        
                            col_qr_img, col_qr_info = st.columns([1, 2], gap="medium")
                            with col_qr_img:
                                st.image(qr_url, width=190, caption="Escaneie o QR Code")
                            with col_qr_info:
                                st.markdown(f"**Valor a Pagar:** R$ {total_geral_carrinho:,.2f}")
                                st.markdown(f"**Favorecido:** `{fav_val}`")
                                st.text_input("Chave Pix Copia e Cola:", value=pix_payload, key="input_pix_copia_cola_detalhe")

                        col_chk1, col_chk2 = st.columns(2)
                        with col_chk1:
                            if st.button("⬅️ Voltar ao PDV", use_container_width=True, key="btn_voltar_pdv_check"):
                                st.session_state.tela_checkout_ativa = False
                                st.rerun()
                        with col_chk2:
                            if st.button(
                                "✅ Confirmar e Concluir Venda",
                                type="primary",
                                use_container_width=True,
                                key="btn_confirmar_pagto_final",
                                disabled=(tipo_documento_pdv == "NFC-e fiscal" or
                                          (forma_pagto == "Dinheiro" and round(troco, 2) < 0))
                            ):
                                try:
                                    if conn.in_transaction:
                                        raise ValueError("Há uma operação pendente no banco. Recarregue a página antes de concluir.")
                                    cursor = conn.cursor()
                                    cursor.execute("BEGIN IMMEDIATE")
                                    caixa_valido = cursor.execute("SELECT status FROM caixa_sessoes WHERE id=?", (int(df_caixa_aberto.iloc[0]['id']),)).fetchone()
                                    if not caixa_valido or caixa_valido[0] != 'ABERTO':
                                        raise ValueError("O caixa foi fechado. Abra um caixa antes de concluir a venda.")
                                    grupo_estoque_pdv = baixar_estoque_carrinho(conn, st.session_state.carrinho_pdv, usr_exibicao)
                                    sessao_id = int(df_caixa_aberto.iloc[0]['id'])
                                    data_venda = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                    vendedor_atual = usr_exibicao
                                    # Garante que a tabela existe com as colunas corretas
                                    cursor.execute("""
                                        CREATE TABLE IF NOT EXISTS vendas_cabecalho (
                                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                                            cliente TEXT,
                                            data TEXT,
                                            forma_pagamento TEXT,
                                            total REAL,
                                            tipo_documento TEXT DEFAULT 'Cupom não fiscal'
                                        )
                                    """)
                                    cursor.execute("PRAGMA table_info(vendas_cabecalho)")
                                    colunas_cabecalho = [col[1] for col in cursor.fetchall()]
                                    if "tipo_documento" not in colunas_cabecalho:
                                        cursor.execute(
                                            "ALTER TABLE vendas_cabecalho ADD COLUMN tipo_documento TEXT DEFAULT 'Cupom não fiscal'"
                                        )
    
                                
                                    # Define com segurança os valores
                                    desc_pagamento = detalhes_pagto
                                
                                    cursor.execute("""
                                        INSERT INTO vendas_cabecalho
                                            (cliente, data, forma_pagamento, total, tipo_documento)
                                        VALUES (?, ?, ?, ?, ?)
                                    """, (
                                        str(cliente_pdv_selecionado),
                                        str(data_venda),
                                        desc_pagamento,
                                        float(total_geral_carrinho),
                                        tipo_documento_pdv
                                    ))
                                
                                    venda_id_gerado = cursor.lastrowid
                                    v_rec = valor_recebido if forma_pagto == "Dinheiro" else (0.0 if forma_pagto in {"Fiado", "Parcelado"} else total_geral_carrinho)
                                    t_val = troco if (forma_pagto == "Dinheiro" and troco >= 0) else 0.0
    
                                    data_vencimento_fiado_val = None
                                    if forma_pagto == "Fiado" and 'input_data_venc_fiado' in st.session_state:
                                        data_vencimento_fiado_val = str(st.session_state.input_data_venc_fiado)
    
                                    # BUSCA OS DADOS DA EMPRESA COM SEGURANÇA
                                    try:
                                        df_empresa_cupom = carregar_dados("SELECT * FROM empresa LIMIT 1")
                                        if not df_empresa_cupom.empty:
                                            emp_nome = df_empresa_cupom.iloc[0].get('nome', nome_empresa_header)
                                            emp_cnpj = df_empresa_cupom.iloc[0].get('cnpj', doc_empresa_padrao)
                                            emp_end = df_empresa_cupom.iloc[0].get('endereco', '')
                                        else:
                                            emp_nome = nome_empresa_header
                                            emp_cnpj = doc_empresa_padrao
                                            emp_end = ''
                                    except Exception:
                                        emp_nome = nome_empresa_header
                                        emp_cnpj = doc_empresa_padrao
                                        emp_end = ''
    
                                    cli_doc_final = "Não informado"
                                    if cliente_pdv_selecionado != "Cliente Balcão":
                                        try:
                                            df_cli_busca = carregar_dados(f"SELECT * FROM clientes WHERE nome = '{cliente_pdv_selecionado}' OR cliente = '{cliente_pdv_selecionado}'")
                                            if not df_cli_busca.empty:
                                                cli_doc_final = str(df_cli_busca.iloc[0].get('cpf_cnpj') or df_cli_busca.iloc[0].get('cpf') or df_cli_busca.iloc[0].get('cnpj') or 'Não informado')
                                        except Exception:
                                            cli_doc_final = "Não informado"
                                
                                    if not conn.in_transaction:
                                        raise ValueError("A transação da venda foi interrompida. A venda não foi concluída.")
                                    venda_id_gerado = None
                                    for item in st.session_state.carrinho_pdv:
                                        cursor.execute("""
                                            INSERT INTO vendas (
                                                cliente, produto, fornecedor, grupo, quantidade, 
                                                valor_venda, valor_total, forma_pagamento, 
                                                valor_recebido, troco, status, tipo, data, vendedor, unidade
                                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Concluído', 'VENDA', ?, ?, ?)
                                        """, (
                                            cliente_pdv_selecionado, 
                                            item['produto'], 
                                            item['fornecedor'], 
                                            item['grupo'], 
                                            item['quantidade'], 
                                            item['valor_unitario'], 
                                            item['valor_total'], 
                                            detalhes_pagto, 
                                            v_rec, 
                                            t_val, 
                                            data_venda, 
                                            vendedor_atual,
                                            unidade_do_item(conn, item)
                                        ))
                                        if not venda_id_gerado:
                                            venda_id_gerado = cursor.lastrowid
                        
                                        # O estoque já foi validado e baixado uma única vez por produto.

                        
                                        if item.get('grupo') == "PROMOÇÃO":
                                            cursor.execute("""
                                                UPDATE promocoes 
                                                SET qtd_estoque_promo = qtd_estoque_promo - ? 
                                                WHERE produto_id = ? AND qtd_estoque_promo >= ?
                                            """, (item['quantidade'], item.get('produto_id'), item['quantidade']))
                        
                                    cursor.execute('UPDATE movimentos_estoque SET referencia=? WHERE grupo_operacao=?',
                                                   (f'Venda PDV #{venda_id_gerado}', grupo_estoque_pdv))
                                    # Registra o movimento com o ID da primeira linha
                                    # da venda na tabela vendas, permitindo estorno exato.
                                    cursor.execute(
                                        """
                                        INSERT INTO caixa_movimentacoes
                                            (sessao_id, tipo, valor, descricao, data, venda_id, forma_pagamento)
                                        VALUES (?, 'VENDA', ?, ?, ?, ?, ?)
                                        """,
                                        (
                                            sessao_id,
                                            float(total_geral_carrinho),
                                            f"Venda PDV ({detalhes_pagto}) por {vendedor_atual}",
                                            data_venda,
                                            int(venda_id_gerado),
                                            detalhes_pagto
                                        )
                                    )
    
                                    if forma_pagto == "Fiado" and data_vencimento_fiado_val:
                                        cursor.execute("""
                                            CREATE TABLE IF NOT EXISTS contas_receber (
                                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                cliente TEXT,
                                                valor REAL,
                                                vencimento TEXT,
                                                status TEXT,
                                                descricao TEXT
                                            )
                                        """)
                                        cursor.execute("""
                                            INSERT INTO contas_receber (cliente, valor, vencimento, status, descricao)
                                            VALUES (?, ?, ?, 'Pendente', ?)
                                        """, (cliente_pdv_selecionado, total_geral_carrinho, data_vencimento_fiado_val, f"Venda PDV #{venda_id_gerado} - Fiado"))
    
                                    if forma_pagto == "Parcelado":
                                        criar_parcelas_pdv(conn, venda_id_gerado, cliente_pdv_selecionado,
                                                           parcelas_pdv, data_venda, usr_exibicao)
    
                                    # Insere os itens da venda no histórico para permitir o estorno
                                    for item in st.session_state.carrinho_pdv:
                                        cursor.execute("""
                                            INSERT INTO vendas_itens (venda_id, produto, quantidade, valor_unitario, valor_total, unidade)
                                            VALUES (?, ?, ?, ?, ?, ?)
                                        """, (
                                            venda_id_gerado, 
                                            item.get('produto'), 
                                            float(item.get('quantidade', 1.0)), 
                                            float(item.get('valor_unitario', 0.0)), 
                                            float(item.get('valor_total', 0.0)),
                                            unidade_do_item(conn, item)
                                        ))
                                    conn.commit()
                                except Exception as erro:
                                    conn.rollback()
                                    st.error(f"Não foi possível concluir a venda: {erro}")
                                    st.stop()
                            
                                # MONTA A LISTA DE ITENS CORRETAMENTE FECHADA
                                carrinho_impresso = [dict(item, unidade=unidade_do_item(conn, item)) for item in st.session_state.carrinho_pdv]
                                itens_html_cupom = ""
                                for item in carrinho_impresso:
                                    prod_nome = str(item.get('produto', 'Item'))
                                    qtd_val = float(item.get('quantidade', 1.0))
                                    total_val = float(item.get('valor_total', 0.0))
                                    total_fmt = f"R$ {total_val:,.2f}"
                                
                                    itens_html_cupom += f"""
                                    <tr>
                                        <td style="text-align: left; padding: 2px 0;">{prod_nome}</td>
                                        <td style="text-align: center; padding: 2px 0;">{quantidade_com_unidade(qtd_val, item.get('unidade'))}</td>
                                        <td style="text-align: right; padding: 2px 0;">{total_fmt}</td>
                                    </tr>
                                    """

                                troco_html = (
                                    f"<p><b>VALOR RECEBIDO:</b> R$ {v_rec:,.2f}</p>"
                                    f"<p><b>TROCO:</b> R$ {t_val:,.2f}</p>"
                                ) if forma_pagto == "Dinheiro" else ""
                                # MONTA O HTML DO CUPOM COM A TABELA FECHADA CORRETAMENTE
                                html_cupom_gerado = f"""
                                <style>
                                    @media print {{
                                        header, footer, nav, aside, .stSidebar, [data-testid="stSidebar"] {{
                                            display: none !important;
                                        }}
                                        body, html {{
                                            background-color: white !important;
                                        }}
                                    }}
                                </style>

                                <div id="cupom_imprimir_exclusivo" style="background-color: #ffffff; padding: 20px; border-radius: 5px; border: 1px dashed #ccc; font-family: monospace; color: #000; max-width: 400px; margin: auto;">
                                    <h3 style="text-align: center; margin: 0;">CUPOM NÃO FISCAL</h3>
                                    <h3 style="text-align: center; margin: 0;">{emp_nome}</h3>
                                    <p style="text-align: center; margin: 2px 0;">CNPJ: {emp_cnpj}</p>
                                    <p style="text-align: center; margin: 2px 0;">{emp_end}</p>
                                    <hr style="border-top: 1px dashed #bbb;">
                                    <p><b>Data:</b> {data_venda} | <b>Vendedor:</b> {vendedor_atual}</p>
                                    <p><b>Cliente:</b> {cliente_pdv_selecionado}</p>
                                    <p><b>CPF/CNPJ:</b> {cli_doc_final}</p>
                                    <hr style="border-top: 1px dashed #bbb;">
                                    <table style="width: 100%; font-family: monospace; font-size: 13px; color: #000; border-collapse: collapse;">
                                        <tr style="border-bottom: 1px solid #ddd;">
                                            <th style="text-align: left; padding-bottom: 4px;">Item</th>
                                            <th style="text-align: center; padding-bottom: 4px;">Qtd</th>
                                            <th style="text-align: right; padding-bottom: 4px;">Total</th>
                                        </tr>
                                        {itens_html_cupom}
                                    </table>
                                    <hr style="border-top: 1px dashed #bbb;">
                                    <p><b>FORMA DE PAGAMENTO:</b> {detalhes_pagto}</p>
                                    <p style="font-size: 15px;"><b>TOTAL GERAL: R$ {total_geral_carrinho:,.2f}</b></p>
                                    {troco_html}
                                    <hr style="border-top: 1px dashed #bbb;">
                                    <p style="text-align: center; margin-bottom: 0;">Obrigado pela preferência!</p>
                                </div>
                                """

                                # Guarda a opção escolhida para esta venda.
                                st.session_state.detalhes_pagto = detalhes_pagto
                                st.session_state.forma_pagto_venda = forma_pagto
                                st.session_state.valor_recebido_venda = v_rec
                                st.session_state.troco_venda = t_val
                                st.session_state.data_venda_final = data_venda
                                st.session_state.html_cupom_atual = html_cupom_gerado
                                st.session_state.tipo_documento_venda = tipo_documento_pdv
                                st.session_state.exibir_cupom_tela = (tipo_documento_pdv == "Cupom não fiscal")
                                st.session_state.venda_concluida_sem_cupom = (tipo_documento_pdv == "Não imprimir cupom")
                                st.session_state.carrinho_temp_para_imprimir = [dict(item, unidade=unidade_do_item(conn, item)) for item in st.session_state.carrinho_pdv]
                                st.session_state.carrinho_pdv = []
                                st.session_state.tela_checkout_ativa = False
                                st.rerun()

            st.markdown(f"<div class='pdv-rodape'>📅 {datetime.now().strftime('%d/%m/%Y')}　│　{'🟢 Caixa aberto' if not df_caixa_aberto.empty else '🔴 Caixa fechado'}　│　Cliente: {html.escape(str(cliente_pdv_selecionado))}</div>", unsafe_allow_html=True)

            produto_em_edicao = st.session_state.get('pdv_produto_em_edicao')
            if produto_em_edicao in set(df_prod_pdv.get('id', [])):
                selecionar_cartao_pdv(produto_em_edicao)

            # Executa fora das colunas para centralizar o pagamento sobre o PDV.
            if st.session_state.get('tela_checkout_ativa', False) and st.session_state.carrinho_pdv:
                abrir_pagamento_pdv()


    # -------------------------------------------------------------
    # 2. MÓDULO FECHAMENTO & FINANCEIRO
    # -------------------------------------------------------------
    elif menu_admin == "📊 Fechamento & Financeiro":
        st.subheader(f"📊 Fechamento & Financeiro — {nome_empresa_header} | 👤 Utilizador: {usr_exibicao}")
        
        aviso_backup = st.session_state.pop("aviso_backup_fechamento", None)
        if aviso_backup is True:
            st.success("Caixa fechado. Backup automático gravado e conferido no Supabase.")
        elif aviso_backup is False:
            st.warning("Caixa fechado. O backup automático falhou. Você pode enviar uma cópia pelo painel de backups.")

        aba_caixa_atual, aba_historico_caixas = st.tabs(["🟢 Caixa Atual & Operação", "📚 Histórico de Caixas Fechados"])

        with aba_caixa_atual:
            df_caixa_atual = carregar_dados("SELECT * FROM caixa_sessoes WHERE status = 'ABERTO'")

            if df_caixa_atual.empty:
                st.info("O caixa encontra-se **FECHADO**. Insira o valor inicial para abri-lo.")
                with st.form("form_abrir_caixa"):
                    saldo_inicial = st.number_input("Saldo Inicial em Dinheiro (Troco)", min_value=0.0, step=10.0)
                    if st.form_submit_button("Abrir Caixa"):
                        cursor = conn.cursor()
                        cursor.execute("INSERT INTO caixa_sessoes (data_abertura, saldo_inicial, status) VALUES (?, ?, 'ABERTO')",
                                       (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), saldo_inicial))
                        conn.commit()
                        st.success("Caixa aberto com sucesso!")
                        st.rerun()
            else:
                sessao_id = int(df_caixa_atual.iloc[0]['id'])
                saldo_inicial = float(df_caixa_atual.iloc[0]['saldo_inicial'])
                st.success(f"🟢 **Caixa ABERTO** | Saldo Inicial: R$ {saldo_inicial:,.2f}")
                
                dinheiro_esperado, _ = exibir_resumo_caixa(conn, sessao_id, saldo_inicial, recolher_detalhes=True)
                st.markdown("### 🔒 Conferência e fechamento")
                saldo_final = st.number_input(
                    "Dinheiro contado na gaveta (R$)", min_value=0.0, value=None,
                    placeholder="Informe o valor contado", format="%.2f",
                    key=f"dinheiro_contado_caixa_{sessao_id}"
                )
                st.caption("Conte apenas o dinheiro físico da gaveta.")
                if saldo_final is not None:
                    diferenca_caixa = round(saldo_final - dinheiro_esperado, 2)
                    if diferenca_caixa == 0:
                        st.success("O dinheiro contado confere com o esperado.")
                    else:
                        tipo_diferenca = "Sobra" if diferenca_caixa > 0 else "Falta"
                        valor_diferenca = f"{abs(diferenca_caixa):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
                        st.warning(f"{tipo_diferenca} de R$ {valor_diferenca} em relação ao esperado.")

                with st.form("form_fechar_caixa"):
                    campos_autorizacao('autorizar_fechamento')
                    if st.form_submit_button("🔒 Fechar Caixa", disabled=saldo_final is None, on_click=capturar_autorizacao, args=('autorizar_fechamento',)):
                        login_admin, senha_admin = consumir_autorizacao('autorizar_fechamento')
                        try:
                            admin_fechamento = validar_administrador(conn, login_admin, senha_admin)
                        except ValueError as erro:
                            st.error(str(erro))
                            st.stop()
                        finally:
                            senha_admin = ''
                        cursor = conn.cursor()

                        cursor.execute("""
                            UPDATE caixa_sessoes
                            SET data_fechamento = ?,
                                saldo_final = ?,
                                status = 'FECHADO', fechado_por = ?, fechamento_autorizado_por = ?
                            WHERE id = ? AND status = 'ABERTO' 
                        """, (
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            saldo_final,
                            usr_exibicao,
                            admin_fechamento,
                            sessao_id
                        ))

                        conn.commit()
                        if cursor.rowcount != 1:
                            st.error("Esta sessão de caixa já foi fechada.")
                            st.stop()
                        if empresa_doc in empresas_backup_automatico:
                            try:
                                dados_backup = gerar_backup_sqlite(conn)
                                agora = datetime.now().strftime("%Y%m%d_%H%M%S")
                                gravar_backup_piloto(dados_backup, empresa_doc, f"backup_caixa_{sessao_id}_{agora}.db")
                                st.session_state["aviso_backup_fechamento"] = True
                            except Exception:
                                st.session_state["aviso_backup_fechamento"] = False
                        else:
                            st.success("Caixa fechado com sucesso!")
                        st.rerun()

                df_movs = carregar_dados(f"""
                    SELECT *
                    FROM caixa_movimentacoes
                    WHERE sessao_id = {sessao_id}
                      AND COALESCE(estornado,0) = 0
                      AND NOT (
                          UPPER(COALESCE(tipo, '')) = 'VENDA'
                          AND (LOWER(COALESCE(descricao, '')) LIKE '%fiado%'
                               OR LOWER(COALESCE(descricao, '')) LIKE '%parcelado%')
                      )
                """)

                st.markdown("### 🔎 Conferência das Movimentações do Caixa")

                if not df_movs.empty:
                    st.dataframe(df_movs, use_container_width=True)

                    if 'tipo' in df_movs.columns:
                        st.markdown("### Resumo por tipo de movimentação")
                        resumo_movs = df_movs.groupby('tipo')['valor'].sum().reset_index()
                        st.dataframe(resumo_movs, use_container_width=True)

                totais_sessao, _ = resumo_recebimentos_caixa(conn, sessao_id)
                total_movimentado = round(sum(totais_sessao.values()), 2)

                st.metric(
                    "Total Movimentado neste Caixa",
                    f"R$ {total_movimentado:,.2f}"
                )

                st.markdown("### 👥 Desempenho de Vendas por Utilizador")
                # Cada movimento vinculado identifica um cupom; as linhas de
                # produtos entram somente na soma do valor daquele cupom.
                df_vendas_usuario = pd.read_sql_query("""
                    WITH cupons AS (
                        SELECT DISTINCT m.venda_id, base.cliente, base.data, base.vendedor
                        FROM caixa_movimentacoes m
                        JOIN vendas base ON base.id = m.venda_id
                        WHERE m.sessao_id = ? AND UPPER(TRIM(m.tipo)) = 'VENDA'
                          AND COALESCE(m.estornado, 0) = 0
                          AND base.tipo = 'VENDA'
                          AND UPPER(TRIM(COALESCE(base.status, ''))) != 'ESTORNADA'
                    ), totais_cupons AS (
                        SELECT c.venda_id, c.vendedor,
                               SUM(COALESCE(v.valor_total, 0)) AS total_cupom
                        FROM cupons c
                        JOIN vendas v ON v.cliente IS c.cliente
                                     AND v.data IS c.data
                                     AND v.vendedor IS c.vendedor
                        WHERE v.tipo = 'VENDA'
                          AND UPPER(TRIM(COALESCE(v.status, ''))) != 'ESTORNADA'
                        GROUP BY c.venda_id, c.vendedor
                    )
                    SELECT COALESCE(vendedor, 'Desconhecido') AS Utilizador,
                           COUNT(*) AS Total_Vendas,
                           SUM(total_cupom) AS Valor_Total
                    FROM totais_cupons
                    GROUP BY vendedor
                """, conn, params=(sessao_id,))
                
                if not df_vendas_usuario.empty:
                    df_vendas_usuario.columns = ['Utilizador', 'Qtd. Vendas', 'Total Vendido (R$)']
                    st.dataframe(df_vendas_usuario, use_container_width=True)
                else:
                    st.info("ℹ️ Nenhuma venda registada por utilizador até o momento.")

                
        # -------------------------------------------------------------
        # HISTÓRICO DE CAIXAS FECHADOS
        # -------------------------------------------------------------
        with aba_historico_caixas:
            st.markdown("### 📚 Histórico de Caixas Fechados")

            df_historico = carregar_dados("""
                SELECT *
                FROM caixa_sessoes
                WHERE status = 'FECHADO'
                ORDER BY id DESC
            """)

            if not df_historico.empty:
                operadores_hist = df_historico['fechado_por'].fillna('').astype(str).str.strip().replace('', 'Não informado')
                datas_fechamento = pd.to_datetime(df_historico['data_fechamento'], errors='coerce')
                with st.container(border=True):
                    operador_hist = st.selectbox("Fechado por", [None] + sorted(operadores_hist.unique().tolist()),
                        format_func=lambda operador: "Todos os operadores" if operador is None else operador,
                        key="hist_caixa_operador")
                    filtrar_periodo_hist = st.checkbox("Filtrar por data do fechamento", key="hist_caixa_filtrar_periodo")
                    if filtrar_periodo_hist:
                        datas_validas = datas_fechamento.dropna()
                        inicio_padrao = datas_validas.min().date() if not datas_validas.empty else date.today()
                        fim_padrao = datas_validas.max().date() if not datas_validas.empty else date.today()
                        col_inicio_hist, col_fim_hist = st.columns(2)
                        inicio_hist = col_inicio_hist.date_input("De", value=inicio_padrao, format="DD/MM/YYYY", key="hist_caixa_inicio")
                        fim_hist = col_fim_hist.date_input("Até", value=fim_padrao, format="DD/MM/YYYY", key="hist_caixa_fim")
                mascara_caixas = pd.Series(True, index=df_historico.index)
                if operador_hist is not None:
                    mascara_caixas &= operadores_hist.eq(operador_hist)
                if filtrar_periodo_hist:
                    if inicio_hist > fim_hist:
                        st.warning("A data inicial deve ser anterior ou igual à data final.")
                    mascara_caixas &= datas_fechamento.dt.date.between(inicio_hist, fim_hist)
                caixas_filtrados = df_historico.loc[mascara_caixas]
                st.caption(f"{len(caixas_filtrados)} fechamento(s) encontrado(s).")
                id_sessao_consulta = None
                if caixas_filtrados.empty:
                    st.info("Nenhum fechamento encontrado com esses filtros.")
                else:
                    tabela_caixas = caixas_filtrados[['id','data_abertura','data_fechamento','saldo_inicial','saldo_final','fechado_por','fechamento_autorizado_por']].copy()
                    for coluna_data in ['data_abertura','data_fechamento']:
                        tabela_caixas[coluna_data] = pd.to_datetime(tabela_caixas[coluna_data], errors='coerce').dt.strftime('%d/%m/%Y %H:%M:%S').fillna('Não informado')
                    tabela_caixas['fechado_por'] = operadores_hist.loc[tabela_caixas.index]
                    tabela_caixas.columns = ['Caixa','Abertura','Fechamento','Saldo inicial (R$)','Saldo final (R$)','Fechado por','Autorizado por']
                    st.dataframe(tabela_caixas, hide_index=True, use_container_width=True,
                        column_config={c: st.column_config.NumberColumn(format='%.2f') for c in ['Saldo inicial (R$)','Saldo final (R$)']})
                    id_sessao_consulta = st.selectbox("Selecione o caixa para ver detalhes", caixas_filtrados['id'].tolist(),
                        key="sel_id_sessao_hist")

                if id_sessao_consulta:
                    df_movs_detalhe = carregar_dados(
                        f"SELECT * FROM caixa_movimentacoes WHERE sessao_id = {int(id_sessao_consulta)}"
                    )

                    registro_caixa = df_historico[df_historico['id'] == id_sessao_consulta].iloc[0]
                    exibir_resumo_caixa(conn, id_sessao_consulta, float(registro_caixa.get('saldo_inicial', 0) or 0),
                        conferencia_historico={'saldo_final': registro_caixa['saldo_final']})
                    st.download_button("📄 Baixar comprovante de fechamento (PDF)",
                        data=gerar_pdf_fechamento_caixa(conn, registro_caixa, nome_empresa_header),
                        file_name=f"fechamento_caixa_{int(id_sessao_consulta)}.pdf",
                        mime="application/pdf", key="baixar_pdf_caixa_fechado")
                    if not df_movs_detalhe.empty:
                        st.dataframe(df_movs_detalhe, use_container_width=True)
                    else:
                        st.info("Nenhuma movimentação registada para este caixa.")
            else:
                st.info("ℹ️ Nenhum caixa fechado registado no histórico até o momento.")
                
    # -------------------------------------------------------------
    # 3. MÓDULO REGISTRAR VENDA / PEDIDOS (COMPLETO E TELA ÚNICA)
    # -------------------------------------------------------------
    elif menu_admin == "🛒 Registrar Venda":
        st.subheader(f"🛒 Registrar Venda / Pedido — {nome_empresa_header} | 👤 Utilizador: {usr_exibicao}")
        
        try:
            df_cli_db = carregar_dados("SELECT * FROM clientes")
            if df_cli_db is not None and not df_cli_db.empty:
                col_nome_c = 'cliente' if 'cliente' in df_cli_db.columns else ('nome' if 'nome' in df_cli_db.columns else df_cli_db.columns[1])
                clientes_opt = df_cli_db[col_nome_c].dropna().astype(str).tolist()
            else:
                clientes_opt = ["Cliente Balcão"]
        except Exception:
            clientes_opt = ["Cliente Balcão"]

        if not clientes_opt:
            clientes_opt = ["Cliente Balcão"]

        df_p_admin = carregar_dados("SELECT * FROM produtos")
        produtos_base = df_p_admin['produto'].tolist() if not df_p_admin.empty else ["ABACATE", "AMEIXA IMPORTADA"]
        
        col_v1, col_v2 = st.columns(2)
        with col_v1:
            cliente_ped = st.selectbox("Selecione o Cliente", clientes_opt, key="sel_cliente_reg_venda")
        with col_v2:
            data_venda_input = st.date_input("Data da Venda", value=datetime.now(), key="input_data_reg_venda")

        st.markdown("---")
        
        # 1. ADICIONAR ITENS AO CARRINHO (NOVA VENDA)
        st.markdown("### ➕ Adicionar Produtos ao Pedido Atual")
        col_prod_r1, col_prod_r2, col_prod_r3 = st.columns([2, 1, 1])
        with col_prod_r1:
            prod_item = st.selectbox("Selecione o Produto", produtos_base, key="sel_prod_reg_venda")
        
        val_sugestao = 0.0
        if not df_p_admin.empty and prod_item in produtos_base:
            p_match = df_p_admin[df_p_admin['produto'] == prod_item]
            if not p_match.empty:
                val_sugestao = float(p_match.iloc[0].get('valor_venda', 0.0) or p_match.iloc[0].get('venda', 0.0) or 0.0)

        unidade_pedido = unidade_do_item(conn, {'produto': prod_item})
        st.caption(f"Unidade do produto: {rotulo_unidade_medida(unidade_pedido)}. Preço informado por essa unidade.")
        with col_prod_r2:
            qtd_ped = st.number_input(f"Quantidade ({rotulo_unidade_medida(unidade_pedido)})", min_value=0.001, value=1.0, format="%.3f", key="qtd_reg_venda")
        with col_prod_r3:
            v_venda_ped = st.number_input("Preço Unitário (R$)", min_value=0.0, value=float(val_sugestao), format="%.2f", key=f"preco_unit_{prod_item}")

        if st.button("➕ Incluir no Carrinho", type="primary", use_container_width=True, key="btn_incluir_reg_venda"):
            try:
                incluir_com_estoque(conn, st.session_state.carrinho_cliente, {
                    "produto": prod_item, "quantidade": qtd_ped, "valor_unitario": v_venda_ped, "valor_total": qtd_ped * v_venda_ped
                })
            except ValueError as erro:
                st.error(str(erro))
            else:
                st.success(f"✅ '{prod_item}' incluído no pedido!")
                st.rerun()

        if st.session_state.carrinho_cliente:
            st.markdown("### 🛒 Itens do Pedido Atual")
            df_carrinho_reg = pd.DataFrame(st.session_state.carrinho_cliente)
            st.dataframe(df_carrinho_reg, use_container_width=True)

            item_para_remover = st.selectbox("Selecionar item para remover do carrinho atual (opcional):", [""] + df_carrinho_reg['produto'].tolist(), key="sel_remover_item_carrinho")
            if item_para_remover and item_para_remover != "":
                if st.button("🗑️ Remover Item Selecionado do Carrinho", key="btn_remover_item_carrinho"):
                    st.session_state.carrinho_cliente = [i for i in st.session_state.carrinho_cliente if i['produto'] != item_para_remover]
                    st.success("Item removido do carrinho!")
                    st.rerun()

            st.markdown("---")
            st.markdown("### 💳 Pagamento e Finalização do Carrinho Atual")
        
            forma_pagto_reg = st.selectbox(
                "Forma de Pagamento / Condição", 
                ["Dinheiro", "Pix", "Cartão Débito", "Cartão Crédito", "Fiado", "Parcelado"],
                key="sel_forma_pagto_reg_venda"
            )
    
            total_carrinho_atual = sum(i['valor_total'] for i in st.session_state.carrinho_cliente)
            detalhes_pagto_reg = forma_pagto_reg
            datas_vencimentos_parcelas_novas = []
            valores_parcelas_novas = []
            
            # Variável exclusiva para controlar o vencimento do fiado
            data_vencimento_fiado_val = None
    
            if forma_pagto_reg == "Parcelado":
                num_parc_reg = st.number_input("Quantidade de Parcelas:", min_value=1, max_value=24, value=2, step=1, key="num_parc_reg_venda")
                from datetime import timedelta
                
                for p_i in range(int(num_parc_reg)):
                    val_sug = total_carrinho_atual / num_parc_reg
                    col_p1, col_p2 = st.columns(2)
                    with col_p1:
                        v_p = st.number_input(f"Valor Parcela {p_i + 1} (R$)", value=float(val_sug), format="%.2f", key=f"val_novo_p_{p_i}")
                    with col_p2:
                        dt_sug = datetime.now().date() + timedelta(days=30 * (p_i + 1))
                        d_p = st.date_input(f"Vencimento Parcela {p_i + 1}", value=dt_sug, key=f"dt_novo_p_{p_i}")
                    valores_parcelas_novas.append(v_p)
                    datas_vencimentos_parcelas_novas.append(str(d_p))
    
                # Auto divisão inteligente para nova venda
                if int(num_parc_reg) > 1:
                    prim_v = valores_parcelas_novas[0]
                    rest = total_carrinho_atual - prim_v
                    if rest < 0: rest = 0.0
                    cada_rest = rest / (int(num_parc_reg) - 1)
                    for p_i in range(1, int(num_parc_reg)):
                        valores_parcelas_novas[p_i] = round(cada_rest, 2)
    
                detalhes_pagto_reg = f"Parcelado ({int(num_parc_reg)}x)"
    
            elif forma_pagto_reg == "Fiado":
                from datetime import timedelta
                data_venc_padrao = datetime.now().date() + timedelta(days=30)
                
                # Seletor de data interativo e editável para o Fiado
                data_vencimento_fiado = st.date_input(
                    "📅 Data de Vencimento do Fiado:",
                    value=data_venc_padrao,
                    format="DD/MM/YYYY",
                    key="input_data_venc_fiado_reg_venda"
                )
                data_vencimento_fiado_val = str(data_vencimento_fiado)
                
                detalhes_pagto_reg = f"Fiado ({cliente_ped}) - Venc: {data_vencimento_fiado.strftime('%d/%m/%Y')}"
    
            if st.button("🔴 Finalizar e Salvar Pedido", type="primary", use_container_width=True, key="btn_finalizar_reg_venda"):
                try:
                    with sqlite3.connect(banco_empresa, timeout=30.0) as conexao_transacao:
                        cursor = conexao_transacao.cursor()
                        
                        # Garante que todas as tabelas necessárias existem
                        cursor.execute("""
                            CREATE TABLE IF NOT EXISTS produtos (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                produto TEXT,
                                quantidade REAL,
                                valor_venda REAL
                            )
                        """)
                        cursor.execute("""
                            CREATE TABLE IF NOT EXISTS vendas_cabecalho (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                cliente TEXT,
                                forma_pagamento TEXT,
                                data TEXT,
                                total REAL
                            )
                        """)
                        cursor.execute("""
                            CREATE TABLE IF NOT EXISTS vendas_itens (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                venda_id INTEGER,
                                produto TEXT,
                                quantidade REAL,
                                valor_unitario REAL,
                                valor_total REAL
                            )
                        """)
                        cursor.execute("""
                            CREATE TABLE IF NOT EXISTS contas_receber (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                cliente TEXT,
                                valor REAL,
                                vencimento TEXT,
                                status TEXT,
                                descricao TEXT
                            )
                        """)
                        conexao_transacao.commit()
                        cursor.execute("BEGIN IMMEDIATE")
                        grupo_estoque_pedido = baixar_estoque_carrinho(conexao_transacao, st.session_state.carrinho_cliente, usr_exibicao)
    
                        data_agora = f"{data_venda_input} " + datetime.now().strftime("%H:%M:%S")
                        
                        cursor.execute("""
                            INSERT INTO vendas_cabecalho (cliente, forma_pagamento, data, total)
                            VALUES (?, ?, ?, ?)
                        """, (cliente_ped, detalhes_pagto_reg, data_agora, total_carrinho_atual))
                        
                        venda_id_gerado = cursor.lastrowid
                        cursor.execute('UPDATE movimentos_estoque SET referencia=? WHERE grupo_operacao=?',
                                       (f'Pedido #{venda_id_gerado}', grupo_estoque_pedido))
    
                        for item in st.session_state.carrinho_cliente:
                            cursor.execute("""
                                INSERT INTO vendas_itens (venda_id, produto, quantidade, valor_unitario, valor_total, unidade)
                                VALUES (?, ?, ?, ?, ?, ?)
                            """, (venda_id_gerado, item['produto'], item['quantidade'], item['valor_unitario'], item['valor_total'], unidade_do_item(conexao_transacao, item)))
                            
                            # Atualiza o estoque com segurança
                            # Baixa agrupada realizada no início desta transação.

    
                        # Se for Parcelado, grava as parcelas no contas a receber
                        if forma_pagto_reg == "Parcelado" and valores_parcelas_novas:
                            for idx_p, (val_p_item, dt_v_item) in enumerate(zip(valores_parcelas_novas, datas_vencimentos_parcelas_novas)):
                                cursor.execute("""
                                    INSERT INTO contas_receber (cliente, valor, vencimento, status, descricao)
                                    VALUES (?, ?, ?, 'Pendente', ?)
                                """, (cliente_ped, val_p_item, dt_v_item, f"Venda #{venda_id_gerado} - Parcela {idx_p+1}/{len(valores_parcelas_novas)}"))
    
                        # Se for Fiado, grava o lançamento único no contas a receber com a data escolhida
                        elif forma_pagto_reg == "Fiado" and data_vencimento_fiado_val:
                            cursor.execute("""
                                INSERT INTO contas_receber (cliente, valor, vencimento, status, descricao)
                                VALUES (?, ?, ?, 'Pendente', ?)
                            """, (cliente_ped, total_carrinho_atual, data_vencimento_fiado_val, f"Venda #{venda_id_gerado} - Fiado"))
    
                        conexao_transacao.commit()
    
                    st.session_state.carrinho_cliente = []
                    st.success(f"✅ Venda #{venda_id_gerado} gravada com sucesso!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Erro ao gravar venda: {e}")

        # -------------------------------------------------------------
        # 2. HISTÓRICO E GESTÃO DE VENDAS (TELA ÚNICA COM EDIÇÃO TOTAL)
        # -------------------------------------------------------------
        st.markdown("---")
        st.markdown("### 📋 Histórico e Gestão de Vendas (Tela Única)")
        
        try:
            df_vendas_cab = carregar_dados("SELECT * FROM vendas_cabecalho ORDER BY id DESC")
        except Exception:
            df_vendas_cab = pd.DataFrame()

        if df_vendas_cab is not None and not df_vendas_cab.empty:
            st.dataframe(df_vendas_cab, use_container_width=True)

            df_vendas_cab['label_venda'] = "Venda #" + df_vendas_cab['id'].astype(str) + " - " + df_vendas_cab['cliente'].astype(str) + " (" + df_vendas_cab['data'].astype(str) + ")"
            lista_vendas_edit = df_vendas_cab['label_venda'].tolist()

            venda_selecionada_label = st.selectbox("🎯 Selecione a Venda para Gerenciar / Editar:", lista_vendas_edit, key="select_venda_gerenciar_master")

            row_venda_sel = df_vendas_cab[df_vendas_cab['label_venda'] == venda_selecionada_label].iloc[0]
            id_venda_atual = int(row_venda_sel['id'])

            st.markdown(f"---")
            st.markdown(f"## 🛠️ Editando Venda #{id_venda_atual}")
            
            col_cab1, col_cab2, col_cab3 = st.columns(3)
            with col_cab1:
                novo_cli_venda = st.text_input("Cliente", value=str(row_venda_sel.get('cliente', '')), key=f"edit_cli_v_{id_venda_atual}")
            with col_cab2:
                try:
                    data_val_dt = datetime.strptime(str(row_venda_sel.get('data', ''))[:10], "%Y-%m-%d")
                except Exception:
                    data_val_dt = datetime.now()
                nova_data_venda = st.date_input("Data da Venda", value=data_val_dt, key=f"edit_data_v_{id_venda_atual}")
            with col_cab3:
                forma_atual_db = str(row_venda_sel.get('forma_pagamento', ''))
                idx_fp = 0
                opcoes_fp = ["Dinheiro", "Pix", "Cartão Débito", "Cartão Crédito", "Fiado", "Parcelado"]
                for i_op, op_val in enumerate(opcoes_fp):
                    if op_val.lower() in forma_atual_db.lower():
                        idx_fp = i_op
                        break

                nova_forma_pagto = st.selectbox("Forma de Pagamento", opcoes_fp, index=idx_fp, key=f"edit_fp_v_{id_venda_atual}")

            st.markdown("#### 📦 Produtos da Venda")
            if str(row_venda_sel.get('status', '')).lower() == 'estornada':
                st.error(f"Venda ESTORNADA em {row_venda_sel.get('estornado_em', '')}. Motivo: {row_venda_sel.get('motivo_estorno', '')}")
                st.dataframe(carregar_dados(f"SELECT * FROM vendas_itens WHERE venda_id = {int(id_venda_atual)}"), use_container_width=True)
                st.stop()

            df_itens_venda = carregar_dados(f"SELECT * FROM vendas_itens WHERE venda_id = {id_venda_atual}")
            
            novos_dados_itens = []
            if df_itens_venda is not None and not df_itens_venda.empty:
                for idx, row_it in df_itens_venda.iterrows():
                    id_it = int(row_it['id'])
                    col_it1, col_it2, col_it3, col_it4 = st.columns([2, 1, 1, 1])
                    
                    with col_it1:
                        st.text(f"Prod: {row_it['produto']}")
                    with col_it2:
                        q_edit = st.number_input("Qtd", value=float(row_it['quantidade']), min_value=0.01, step=1.0, key=f"q_it_{id_it}")
                    with col_it3:
                        v_edit = st.number_input("Val. Unit.", value=float(row_it['valor_unitario']), min_value=0.0, format="%.2f", key=f"v_it_{id_it}")
                    with col_it4:
                        exc_it = st.checkbox("Excluir", key=f"del_it_{id_it}")

                    tot_it = q_edit * v_edit
                    novos_dados_itens.append({
                        "id": id_it, "produto": row_it['produto'], "quantidade": q_edit, "valor_unitario": v_edit, "valor_total": tot_it, "excluir": exc_it
                    })
            
            total_itens_calculado = sum(it['valor_total'] for it in novos_dados_itens if not it['excluir'])
            st.info(f"💡 **Valor Total Atual dos Produtos:** R$ {total_itens_calculado:,.2f}")

            novas_parcelas_editadas = []
            if nova_forma_pagto == "Parcelado":
                st.markdown("#### 📅 Gestão de Parcelas (Divisão Automática)")
                df_parc_exist = carregar_dados(f"SELECT * FROM contas_receber WHERE descricao LIKE '%Venda #{id_venda_atual}%'")
                
                qtd_parc_inicial = len(df_parc_exist) if (df_parc_exist is not None and not df_parc_exist.empty) else 2
                qtd_parc_input = st.number_input("Número de Parcelas:", min_value=1, max_value=24, value=qtd_parc_inicial, key=f"n_parc_edit_{id_venda_atual}")
                
                from datetime import timedelta
                valores_parcelas_temp = []

                for p_i in range(int(qtd_parc_input)):
                    val_sug = total_itens_calculado / qtd_parc_input
                    if df_parc_exist is not None and p_i < len(df_parc_exist):
                        val_sug = float(df_parc_exist.iloc[p_i].get('valor', val_sug))

                    col_p1, col_p2 = st.columns(2)
                    with col_p1:
                        val_parc_p = st.number_input(f"Valor Parcela {p_i + 1} (R$)", value=float(val_sug), format="%.2f", key=f"val_p_{id_venda_atual}_{p_i}")
                    with col_p2:
                        dt_def = datetime.now().date() + timedelta(days=30 * (p_i + 1))
                        if df_parc_exist is not None and p_i < len(df_parc_exist):
                            try:
                                dt_def = datetime.strptime(str(df_parc_exist.iloc[p_i].get('vencimento', ''))[:10], "%Y-%m-%d").date()
                            except Exception:
                                pass
                        dt_parc_p = st.date_input(f"Vencimento Parcela {p_i + 1}", value=dt_def, key=f"dt_p_{id_venda_atual}_{p_i}")

                    valores_parcelas_temp.append({"valor": val_parc_p, "vencimento": str(dt_parc_p)})

                if int(qtd_parc_input) > 1:
                    primeiro_valor = valores_parcelas_temp[0]["valor"]
                    restante_a_dividir = total_itens_calculado - primeiro_valor
                    if restante_a_dividir < 0: restante_a_dividir = 0.0
                    valor_cada_restante = restante_a_dividir / (int(qtd_parc_input) - 1)
                    
                    for p_i in range(1, int(qtd_parc_input)):
                        valores_parcelas_temp[p_i]["valor"] = round(valor_cada_restante, 2)

                for p_i, p_val_data in enumerate(valores_parcelas_temp):
                    novas_parcelas_editadas.append({
                        "numero": p_i + 1, "valor": p_val_data["valor"], "vencimento": p_val_data["vencimento"]
                    })
                    st.caption(f"➡️ Parcela {p_i+1}: **R$ {p_val_data['valor']:,.2f}** para {p_val_data['vencimento']}")

            st.markdown("---")
            col_b_main1, col_b_main2, col_b_estorno = st.columns(3)
            
            with col_b_main1:
                if st.button("💾 Salvar Alterações", type="primary", use_container_width=True, key=f"btn_save_all_{id_venda_atual}"):
                    try:
                        cursor = conn.cursor()
                        
                        total_venda_recalculado = 0.0
                        for it in novos_dados_itens:
                            if it['excluir']:
                                cursor.execute("DELETE FROM vendas_itens WHERE id = ?", (it['id'],))
                            else:
                                cursor.execute("""
                                    UPDATE vendas_itens 
                                    SET quantidade = ?, valor_unitario = ?, valor_total = ?
                                    WHERE id = ?
                                """, (it['quantidade'], it['valor_unitario'], it['valor_total'], it['id']))
                                total_venda_recalculado += it['valor_total']

                        fp_desc = nova_forma_pagto
                        if nova_forma_pagto == "Parcelado":
                            fp_desc = f"Parcelado ({len(novas_parcelas_editadas)}x)"
                        
                        dt_string_final = f"{nova_data_venda} " + datetime.now().strftime("%H:%M:%S")
                        
                        cursor.execute("""
                            UPDATE vendas_cabecalho 
                            SET cliente = ?, data = ?, forma_pagamento = ?, total = ?
                            WHERE id = ?
                        """, (novo_cli_venda.strip().upper(), dt_string_final, fp_desc, total_venda_recalculado, id_venda_atual))

                        cursor.execute("DELETE FROM contas_receber WHERE descricao LIKE ?", (f"%Venda #{id_venda_atual}%",))
                        if nova_forma_pagto == "Parcelado":
                            for p_item in novas_parcelas_editadas:
                                cursor.execute("""
                                    INSERT INTO contas_receber (cliente, valor, vencimento, status, descricao)
                                    VALUES (?, ?, ?, 'Pendente', ?)
                                """, (novo_cli_venda.strip().upper(), p_item['valor'], p_item['vencimento'], f"Venda #{id_venda_atual} - Parcela {p_item['numero']}/{len(novas_parcelas_editadas)}"))

                        conn.commit()
                        st.success(f"✅ Venda #{id_venda_atual} atualizada com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Erro ao salvar: {e}")

            with col_b_main2:
                st.caption("Para cancelar uma venda, use Estornar Venda com autorização do administrador. O histórico será preservado.")

            with col_b_estorno:
                with st.form(f"form_estorno_pedido_{id_venda_atual}"):
                    motivo_pedido = st.text_area("Motivo do estorno do pedido", key=f"motivo_pedido_{id_venda_atual}")
                    campos_autorizacao('autorizar_estorno_pedido')
                    estornar_pedido = st.form_submit_button("🔄 Estornar Venda", type="primary",
                        on_click=capturar_autorizacao, args=('autorizar_estorno_pedido',))
                if estornar_pedido:
                    login_admin, senha_admin = consumir_autorizacao('autorizar_estorno_pedido')
                    try:
                        estornar_venda_auditada(conn, id_venda_atual, 'Pedido', motivo_pedido,
                                                login_admin, senha_admin, usr_exibicao)
                    except Exception as erro:
                        st.error(f"Não foi possível estornar: {erro}")
                    else:
                        st.rerun()
                    finally:
                        senha_admin = ''
        else:
            st.info("ℹ️ Nenhuma venda registrada até o momento.")

    # -------------------------------------------------------------
    # ENTRADA DE ESTOQUE E CADASTRO DE PRODUTOS
    # -------------------------------------------------------------
    elif menu_admin == "Entrada de Estoque (Compras)" or "Entrada de Estoque" in str(menu_admin):
        st.subheader("📦 Gestão de Produtos e Entradas de Estoque")
        
        # Criamos as abas para organizar o cadastro e as compras
        tab_cad_prod, tab_entrada_compra = st.tabs([
            "➕ Cadastrar Novo Produto", 
            "📥 Entrada de Estoque (Compras)"
        ])
        
        # -------------------------------------------------------------
        # ABA 1: CADASTRAR NOVO PRODUTO
        # -------------------------------------------------------------
        with tab_cad_prod:
            st.markdown("### ➕ Cadastro de Novo Produto no Sistema")
            
            with st.form("form_cadastro_produto_direto"):
                col_cp1, col_cp2 = st.columns(2)
                with col_cp1:
                    novo_cod_prod = st.text_input("Código / Código de Barras")
                    novo_nome_prod = st.text_input("Nome do Produto")
                with col_cp2:
                    try:
                        lista_grupos_cad = carregar_coluna("grupos", "grupo") or ["GERAL"]
                    except Exception:
                        lista_grupos_cad = ["GERAL"]
                    novo_grupo_prod = st.selectbox("Grupo / Categoria", lista_grupos_cad)
                    
                    try:
                        lista_forn_cad = carregar_coluna("fornecedores", "nome") or carregar_coluna("fornecedores", "fornecedor") or ["GERAL"]
                    except Exception:
                        lista_forn_cad = ["GERAL"]
                    novo_forn_prod = st.selectbox("Fornecedor Padrão", lista_forn_cad)
    
                col_cp3, col_cp4 = st.columns(2)
                with col_cp3:
                    novo_preco_compra = st.number_input("Preço de Compra Inicial (R$)", value=0.0, format="%.2f")
                with col_cp4:
                    novo_preco_venda = st.number_input("Preço de Venda Inicial (R$)", value=0.0, format="%.2f")
                
                nova_unidade_prod = st.selectbox("Unidade de medida do produto", UNIDADES_MEDIDA, index=None, placeholder="Selecione a unidade", key="nova_unidade_prod")
                st.caption("Preços e quantidade inicial se referem à unidade escolhida. Não há conversão automática entre caixa, kg ou outras unidades.")
                qtd_inicial_prod = st.number_input("Quantidade Inicial em Estoque", value=0.0, step=0.001, min_value=0.0, format="%.3f")
    
                btn_salvar_novo_prod = st.form_submit_button("💾 Salvar Novo Produto", type="primary", use_container_width=True)
                
                if btn_salvar_novo_prod:
                    if novo_nome_prod.strip() and nova_unidade_prod:
                        try:
                            garantir_colunas_produtos(conn)
                            cursor = conn.cursor()
                            cursor.execute("""
                                INSERT INTO produtos (codigo, produto, quantidade, valor_compra, valor_venda, grupo, fornecedor, unidade)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                novo_cod_prod.strip(), 
                                novo_nome_prod.strip().upper(), 
                                qtd_inicial_prod, 
                                novo_preco_compra, 
                                novo_preco_venda, 
                                novo_grupo_prod, 
                                novo_forn_prod,
                                nova_unidade_prod
                            ))
                            registrar_movimento_estoque(conn, cursor.lastrowid, 'SALDO INICIAL', 0, qtd_inicial_prod,
                                                         usr_exibicao, 'Cadastro do produto')
                            conn.commit()
                            st.success(f"✅ Produto '{novo_nome_prod.strip().upper()}' cadastrado com sucesso!")
                            st.rerun()
                        except Exception as e:
                            conn.rollback()
                            st.error(f"❌ Erro ao cadastrar produto: {e}")
                    else:
                        st.warning("⚠️ Informe o nome e selecione a unidade de medida do produto.")
    
        # -------------------------------------------------------------
        # ABA 2: ENTRADA DE ESTOQUE (COMPRAS) COM MARGEM AUTOMÁTICA
        # -------------------------------------------------------------
        produtos_opt = carregar_coluna("produtos", "produto") or []
        fornecedores_opt = carregar_coluna("fornecedores", "fornecedor") or ["BAHIA"]
        grupos_opt = carregar_coluna("grupos", "grupo") or ["GERAL"]
        unidades_opt = UNIDADES_MEDIDA

        st.markdown("### 📥 Registrar compra e repor estoque")
        st.caption("Escolha um produto cadastrado, confira os preços e adicione os itens. O saldo só muda ao finalizar as entradas.")
        if not produtos_opt:
            st.info("Cadastre um produto na primeira aba para registrar a compra.")
            st.stop()
        busca_compra = st.text_input("🔎 Buscar produto por nome ou código", key="busca_produto_compra")
        catalogo_compra = carregar_dados("SELECT id,produto,codigo,quantidade,valor_compra,valor_venda,grupo,fornecedor,unidade FROM produtos")
        if busca_compra.strip():
            filtro_catalogo = catalogo_compra['produto'].fillna('').astype(str).str.contains(busca_compra.strip(),case=False,regex=False) | catalogo_compra['codigo'].fillna('').astype(str).str.contains(busca_compra.strip(),case=False,regex=False)
            produtos_opt = catalogo_compra.loc[filtro_catalogo,'produto'].tolist()
        if not produtos_opt:
            st.info("Nenhum produto encontrado. Altere a busca.")
            st.stop()
        col1, col2, col3 = st.columns(3)
        with col1:
            prod_compra = st.selectbox("Selecione o Produto", produtos_opt, key="prod_compra_sel")
            cadastro_compra = catalogo_compra[catalogo_compra['produto'] == prod_compra].iloc[0]
            if st.session_state.get('_produto_compra_anterior') != prod_compra:
                custo_cadastrado = float(cadastro_compra.get('valor_compra',0) or 0)
                venda_cadastrada = float(cadastro_compra.get('valor_venda',0) or 0)
                st.session_state.pr_compra_form = custo_cadastrado
                st.session_state.qtd_compra_num = 1.0
                st.session_state.preco_venda = venda_cadastrada
                st.session_state.margem_perc = ((venda_cadastrada/custo_cadastrado)-1)*100 if custo_cadastrado else 0.0
                st.session_state.widget_venda = venda_cadastrada
                st.session_state.widget_margem = st.session_state.margem_perc
                st.session_state.ultimo_pr_compra = custo_cadastrado
                st.session_state._produto_compra_anterior = prod_compra
                if cadastro_compra.get('fornecedor') in fornecedores_opt:
                    st.session_state.forn_compra_sel = cadastro_compra['fornecedor']
                if cadastro_compra.get('grupo') in grupos_opt:
                    st.session_state.grp_compra_sel = cadastro_compra['grupo']
            forn_compra = st.selectbox("Fornecedor", fornecedores_opt, key="forn_compra_sel")
        with col2:
            grp_compra = st.selectbox("Grupo", grupos_opt, key="grp_compra_sel")
            linha_unidade_compra = conn.execute('SELECT unidade FROM produtos WHERE produto=?', (prod_compra,)).fetchone()
            unidade_padrao_compra = normalizar_unidade_medida(linha_unidade_compra[0]) if linha_unidade_compra else ''
            unidade_medida = st.selectbox("Unidade de Medida", unidades_opt, index=unidades_opt.index(unidade_padrao_compra) if unidade_padrao_compra in unidades_opt else None,
                                         placeholder="Selecione a unidade", key=f"unidade_medida_sel_{prod_compra}")
        with col3:
            qtd_compra = st.number_input(f"Quantidade ({rotulo_unidade_medida(unidade_medida)})", min_value=0.001, value=1.0, step=0.001, format="%.3f", key="qtd_compra_num")
            pr_compra = st.number_input(f"Preço de compra por {rotulo_unidade_medida(unidade_medida)} (R$)", min_value=0.0, format="%.2f", key="pr_compra_form")

        # Inicializa o estado de cálculo na sessão
        if 'margem_perc' not in st.session_state:
            st.session_state.margem_perc = 30.0
        if 'preco_venda' not in st.session_state:
            st.session_state.preco_venda = pr_compra * (1.0 + (st.session_state.margem_perc / 100.0))
        if 'ultimo_pr_compra' not in st.session_state:
            st.session_state.ultimo_pr_compra = pr_compra

        # Se o preço de compra alterou, recalcula o preço de venda mantendo a margem atual
        if pr_compra != st.session_state.ultimo_pr_compra:
            st.session_state.ultimo_pr_compra = pr_compra
            st.session_state.preco_venda = pr_compra * (1.0 + (st.session_state.margem_perc / 100.0))
            st.session_state.widget_venda = st.session_state.preco_venda

        # Funções de callback seguras ligadas à sessão
        def mudar_margem():
            m = st.session_state.widget_margem
            st.session_state.margem_perc = m
            st.session_state.preco_venda = pr_compra * (1.0 + (m / 100.0))
            st.session_state.widget_venda = st.session_state.preco_venda

        def mudar_venda():
            v = st.session_state.widget_venda
            st.session_state.preco_venda = v
            if pr_compra > 0:
                st.session_state.margem_perc = ((v - pr_compra) / pr_compra) * 100.0
                st.session_state.widget_margem = st.session_state.margem_perc

        col_m1, col_m2 = st.columns(2)
        with col_m1:
            st.number_input(
                "Acréscimo sobre o custo (%)", 
                value=float(st.session_state.margem_perc), 
                format="%.2f", 
                key="widget_margem",
                on_change=mudar_margem
            )
        with col_m2:
            st.number_input(
                f"Preço de venda por {rotulo_unidade_medida(unidade_medida)} (R$)", 
                min_value=0.0, 
                value=float(st.session_state.preco_venda), 
                format="%.2f", 
                key="widget_venda",
                on_change=mudar_venda
            )

        def moeda_compra(valor):
            return "R$ " + f"{float(valor):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
        resumo_compra = st.columns(3)
        resumo_compra[0].metric("📦 Saldo atual", quantidade_com_unidade(cadastro_compra.get('quantidade',0), cadastro_compra.get('unidade')))
        resumo_compra[1].metric("💰 Custo desta entrada", moeda_compra(qtd_compra * pr_compra))
        resumo_compra[2].metric("🏷️ Venda por unidade", moeda_compra(st.session_state.preco_venda))
        st.caption("O acréscimo é calculado sobre o custo de compra. Quantidades e preços seguem a unidade selecionada; não há conversão automática.")

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🛒 Adicionar ao Carrinho de Compras", type="primary", use_container_width=True, key="compras_adicionar"):
            try:
                validar_unidade_entrada(conn, prod_compra, unidade_medida)
            except ValueError as erro:
                st.error(str(erro))
                st.stop()
            if 'carrinho_compras' not in st.session_state:
                st.session_state.carrinho_compras = []
                
            st.session_state.carrinho_compras.append({
                "produto": prod_compra, 
                "grupo": grp_compra, 
                "fornecedor": forn_compra,
                "unidade": unidade_medida,
                "quantidade": qtd_compra, 
                "valor_compra": pr_compra, 
                "valor_venda": st.session_state.preco_venda
            })
            st.success(f"✅ '{prod_compra}' adicionado ao carrinho!")
            st.rerun()

        if 'carrinho_compras' in st.session_state and st.session_state.carrinho_compras:
            st.markdown("### 📋 Itens no Carrinho de Compras")
            
            for item in st.session_state.carrinho_compras:
                if 'unidade' not in item:
                    item['unidade'] = ''

            df_carrinho_compras = pd.DataFrame(st.session_state.carrinho_compras)
            
            df_exib_compras = pd.DataFrame()
            df_exib_compras['Produto'] = df_carrinho_compras['produto']
            df_exib_compras['Grupo'] = df_carrinho_compras['grupo']
            df_exib_compras['Fornecedor'] = df_carrinho_compras['fornecedor']
            df_exib_compras['Unidade'] = df_carrinho_compras['unidade']
            df_exib_compras['Qtd'] = df_carrinho_compras['quantidade']
            df_exib_compras['Preço Compra'] = df_carrinho_compras['valor_compra'].apply(lambda x: f"R$ {float(x):,.2f}")
            df_exib_compras['Preço Venda'] = df_carrinho_compras['valor_venda'].apply(lambda x: f"R$ {float(x):,.2f}")
            
            df_exib_compras['Total Compra (R$)'] = df_carrinho_compras['quantidade'] * df_carrinho_compras['valor_compra']
            totais_carrinho_compra = st.columns(2)
            totais_carrinho_compra[0].metric("Itens na compra", len(df_carrinho_compras))
            totais_carrinho_compra[1].metric("Total da compra", moeda_compra(df_exib_compras['Total Compra (R$)'].sum()))
            st.dataframe(df_exib_compras, hide_index=True, use_container_width=True,
                column_config={'Qtd':st.column_config.NumberColumn(format='%.3f'), 'Total Compra (R$)':st.column_config.NumberColumn(format='%.2f')})

            with st.expander("Revisar quantidade e custo"):
                opcoes_revisao = [f"{i + 1}. {item['produto']}" for i, item in enumerate(st.session_state.carrinho_compras)]
                indice_revisao = st.selectbox("Item da compra", list(range(len(opcoes_revisao))),
                    format_func=lambda i: opcoes_revisao[i], key="compras_item_revisar")
                item_revisao = st.session_state.carrinho_compras[indice_revisao]
                with st.form(f"compras_revisar_{indice_revisao}"):
                    quantidade_revisao = st.number_input("Quantidade", min_value=0.001,
                        value=float(item_revisao['quantidade']), step=0.001, format="%.3f")
                    custo_revisao = st.number_input("Custo unitário (R$)", min_value=0.0,
                        value=float(item_revisao['valor_compra']), step=0.01, format="%.2f")
                    if st.form_submit_button("Atualizar item"):
                        item_revisao['quantidade'] = round(quantidade_revisao, 3)
                        item_revisao['valor_compra'] = round(custo_revisao, 2)
                        st.rerun()

            col_del1, col_del2, col_del3 = st.columns(3)
            with col_del1:
                nomes_remover_compra = [f"{i+1}. {item['produto']}" for i,item in enumerate(st.session_state.carrinho_compras)]
                item_remover_idx = st.selectbox("Item para remover", list(range(len(nomes_remover_compra))),
                    format_func=lambda i:nomes_remover_compra[i], key="item_remover_compra")
                if st.button("❌ Remover Item Selecionado", use_container_width=True):
                    if len(st.session_state.carrinho_compras) > 0:
                        st.session_state.carrinho_compras.pop(int(item_remover_idx))
                        st.success("🗑️ Item removido do carrinho!")
                        st.rerun()
            with col_del2:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("🧹 Limpar Todo o Carrinho", use_container_width=True):
                    st.session_state.carrinho_compras = []
                    st.success("🧹 Carrinho limpo com sucesso!")
                    st.rerun()
            with col_del3:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("💾 Finalizar Todas as Entradas", type="primary", use_container_width=True):
                    try:
                        cursor = conn.cursor()
                        cursor.execute("BEGIN IMMEDIATE")
                        
                        # Recria a tabela de compras com todas as colunas atualizadas para evitar erros de estrutura
                        # A tabela compras já é criada/adequada na inicialização.
                        # Nunca apagar o histórico de compras durante uma entrada.
    
                        # Garante que a tabela produtos tem a coluna unidade
                        cursor.execute("PRAGMA table_info(produtos)")
                        cols_prod = [c[1] for c in cursor.fetchall()]
                        if "unidade" not in cols_prod:
                            try: cursor.execute("ALTER TABLE produtos ADD COLUMN unidade TEXT")
                            except Exception: pass
    
                        data_atual_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
                        for item in st.session_state.carrinho_compras:
                            if 'produto_id_reposicao' in item:
                                produto_atual = cursor.execute('SELECT produto FROM produtos WHERE id=?',
                                    (item['produto_id_reposicao'],)).fetchone()
                                if not produto_atual or produto_atual[0] != item['produto']:
                                    raise ValueError(f"O cadastro de {item['produto']} mudou. Remova e adicione o item novamente.")
                            item['unidade'] = validar_unidade_entrada(conn, item['produto'], item.get('unidade'))
                            saldo_compra_antes = cursor.execute('SELECT quantidade FROM produtos WHERE produto=?', (item['produto'],)).fetchone()
                            saldo_compra_antes = float(saldo_compra_antes[0] or 0) if saldo_compra_antes else 0.0
                            # Insere no histórico de compras
                            cursor.execute("""
                                INSERT INTO compras (produto, fornecedor, grupo, quantidade, preco_compra, preco_venda, unidade, data)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                item.get('produto'), 
                                item.get('fornecedor'), 
                                item.get('grupo'), 
                                item.get('quantidade'), 
                                item.get('valor_compra'), 
                                item.get('valor_venda'), 
                                item.get('unidade', 'UNIDADE'), 
                                data_atual_str
                            ))
    
                            # Atualiza ou insere o produto no estoque geral
                            cursor.execute("SELECT id FROM produtos WHERE produto = ?", (item['produto'],))
                            if cursor.fetchone():
                                cursor.execute("""
                                    UPDATE produtos 
                                    SET quantidade = quantidade + ?, valor_compra = ?, valor_venda = ?, grupo = ?, fornecedor = ?, unidade = ?
                                    WHERE produto = ?
                                """, (item['quantidade'], item['valor_compra'], item['valor_venda'], item['grupo'], item['fornecedor'], item.get('unidade', 'UNIDADE'), item['produto']))
                            else:
                                cursor.execute("""
                                    INSERT INTO produtos (produto, grupo, fornecedor, quantidade, valor_compra, valor_venda, unidade) 
                                    VALUES (?, ?, ?, ?, ?, ?, ?)
                                """, (item['produto'], item['grupo'], item['fornecedor'], item['quantidade'], item['valor_compra'], item['valor_venda'], item.get('unidade', 'UNIDADE')))
                        
                            registro_compra_depois = cursor.execute('SELECT id,quantidade FROM produtos WHERE produto=?', (item['produto'],)).fetchone()
                            registrar_movimento_estoque(conn, registro_compra_depois[0], 'COMPRA', saldo_compra_antes,
                                                         float(registro_compra_depois[1]), usr_exibicao, 'Entrada de estoque')
                        conn.commit()
                    except Exception as erro:
                        conn.rollback()
                        st.error(f"Não foi possível registrar a entrada: {erro}")
                        st.stop()

                    st.session_state.carrinho_compras = []
                    st.success("✅ Entrada registrada no banco de dados e histórico de compras atualizado com sucesso!")
                    st.rerun()

    # -------------------------------------------------------------
    # 5. MÓDULO CADASTROS (CLIENTES / FORNECEDORES / GRUPOS)
    # -------------------------------------------------------------
    elif menu_admin == "👥 Cadastros (Clientes / Fornecedores / Grupos)":
        st.subheader("👥 Cadastros (Clientes / Fornecedores / Grupos)")
        tab_cli, tab_forn, tab_grup = st.tabs(["👤 Clientes", "🏢 Fornecedores", "🏷️ Grupos"])
    
        # Compatibilidade com os cadastros antigos; as listas nunca exibem senhas.
        for tabela_contato in ['clientes','fornecedores']:
            colunas_contato = {r[1] for r in conn.execute(f'PRAGMA table_info({tabela_contato})')}
            for coluna_contato in ['cpf','fone']:
                if coluna_contato not in colunas_contato:
                    conn.execute(f'ALTER TABLE {tabela_contato} ADD COLUMN {coluna_contato} TEXT')
        conn.commit()

        def primeiro_dado_contato(linha, colunas):
            for coluna in colunas:
                valor = linha.get(coluna)
                if pd.notna(valor) and str(valor).strip().lower() not in {'','none','nan','null'}:
                    return str(valor).strip()
            return ''

        def salvar_contato(tabela, nome, documento, telefone, identificador=None):
            if not nome.strip():
                raise ValueError('Informe o nome antes de salvar.')
            colunas = {r[1] for r in conn.execute(f'PRAGMA table_info({tabela})')}
            campos_nome = [c for c in (['nome','cliente'] if tabela == 'clientes' else ['nome','fornecedor']) if c in colunas]
            if not campos_nome:
                raise ValueError('O cadastro não possui uma coluna de nome reconhecida.')
            valores = {c:nome.strip().upper() for c in campos_nome}
            for c in ['cpf','doc','cnpj','cpf_cnpj']:
                if c in colunas:
                    valores[c] = documento.strip()
            for c in ['fone','telefone']:
                if c in colunas:
                    valores[c] = telefone.strip()
            with conn:
                if identificador is None:
                    conn.execute(f"INSERT INTO {tabela} ({','.join(valores)}) VALUES ({','.join('?' for _ in valores)})", tuple(valores.values()))
                else:
                    cursor_contato = conn.execute(f"UPDATE {tabela} SET {','.join(c+'=?' for c in valores)} WHERE id=?", (*valores.values(),int(identificador)))
                    if cursor_contato.rowcount != 1:
                        raise ValueError('Cadastro não encontrado. Atualize a tela.')

        def mostrar_cadastro_contatos(tabela, singular, plural, prefixo):
            st.markdown(f'### {plural}')
            if st.session_state.get(f'{prefixo}_aviso'):
                st.success(st.session_state.pop(f'{prefixo}_aviso'))
            with st.expander(f'➕ Cadastrar {singular.lower()}', expanded=False):
                with st.form(f'{prefixo}_novo_form', clear_on_submit=True):
                    nome_novo = st.text_input('Nome', key=f'{prefixo}_novo_nome')
                    colunas_novo = st.columns(2)
                    doc_novo = colunas_novo[0].text_input('CPF / CNPJ', key=f'{prefixo}_novo_doc')
                    fone_novo = colunas_novo[1].text_input('Telefone', key=f'{prefixo}_novo_fone')
                    salvar_novo = st.form_submit_button(f'💾 Salvar {singular.lower()}',type='primary',use_container_width=True)
                if salvar_novo:
                    try:
                        salvar_contato(tabela,nome_novo,doc_novo,fone_novo)
                    except Exception as erro:
                        st.error(f'Não foi possível cadastrar: {erro}')
                    else:
                        st.session_state[f'{prefixo}_aviso'] = 'Cadastro salvo com sucesso.'
                        st.rerun()
            dados_contato = carregar_dados(f'SELECT * FROM {tabela} ORDER BY id DESC')
            if dados_contato.empty:
                st.info('Nenhum cadastro encontrado. Use a opção acima para cadastrar.')
                return
            visao_contato = pd.DataFrame(index=dados_contato.index)
            visao_contato['ID'] = dados_contato['id']
            visao_contato['Nome'] = dados_contato.apply(lambda r:primeiro_dado_contato(r,['nome','cliente','fornecedor']),axis=1)
            visao_contato['CPF / CNPJ'] = dados_contato.apply(lambda r:primeiro_dado_contato(r,['cpf','doc','cnpj','cpf_cnpj']),axis=1)
            visao_contato['Telefone'] = dados_contato.apply(lambda r:primeiro_dado_contato(r,['fone','telefone']),axis=1)
            busca_contato = st.text_input('🔎 Buscar por nome, CPF/CNPJ ou telefone', key=f'{prefixo}_busca')
            filtrados_contato = visao_contato.copy()
            if busca_contato.strip():
                termo_contato = busca_contato.strip()
                digitos_contato = re.sub(r'\D','',termo_contato)
                mascara_contato = visao_contato['Nome'].str.contains(termo_contato,case=False,regex=False)
                for coluna_contato in ['CPF / CNPJ','Telefone']:
                    mascara_contato |= visao_contato[coluna_contato].str.contains(termo_contato,case=False,regex=False)
                    if digitos_contato:
                        mascara_contato |= visao_contato[coluna_contato].str.replace(r'\D','',regex=True).str.contains(digitos_contato,regex=False)
                filtrados_contato = visao_contato.loc[mascara_contato]
            resumo_contato = st.columns(2)
            resumo_contato[0].metric('Total de cadastros',len(visao_contato))
            resumo_contato[1].metric('Encontrados na busca',len(filtrados_contato))
            if filtrados_contato.empty:
                st.info('Nenhum cadastro corresponde à busca.')
                return
            st.dataframe(filtrados_contato,hide_index=True,use_container_width=True)
            rotulos_contato = {int(r['ID']):f"{int(r['ID'])} — {r['Nome']}" for _,r in filtrados_contato.iterrows()}
            escolhido_contato = st.selectbox(f'Selecione o {singular.lower()} para editar',list(rotulos_contato),format_func=lambda i:rotulos_contato[i],key=f'{prefixo}_selecionado')
            linha_contato = visao_contato[visao_contato['ID'] == escolhido_contato].iloc[0]
            with st.form(f'{prefixo}_editar_{escolhido_contato}'):
                nome_editado = st.text_input('Nome',value=linha_contato['Nome'])
                colunas_editar = st.columns(2)
                doc_editado = colunas_editar[0].text_input('CPF / CNPJ',value=linha_contato['CPF / CNPJ'])
                fone_editado = colunas_editar[1].text_input('Telefone',value=linha_contato['Telefone'])
                salvar_edicao = st.form_submit_button('✏️ Salvar alterações',type='primary',use_container_width=True)
            if salvar_edicao:
                try:
                    salvar_contato(tabela,nome_editado,doc_editado,fone_editado,escolhido_contato)
                except Exception as erro:
                    st.error(f'Não foi possível atualizar: {erro}')
                else:
                    st.session_state[f'{prefixo}_aviso'] = 'Alterações salvas com sucesso. Os registros históricos permanecem com os dados da época.'
                    st.rerun()
            with st.expander('🗑️ Excluir cadastro'):
                confirmar_exclusao = st.checkbox(f'Confirmo a exclusão de {linha_contato["Nome"]}',key=f'{prefixo}_excluir_confirma_{escolhido_contato}')
                if st.button('Excluir cadastro',disabled=not confirmar_exclusao,key=f'{prefixo}_excluir_{escolhido_contato}'):
                    with conn:
                        conn.execute(f'DELETE FROM {tabela} WHERE id=?',(int(escolhido_contato),))
                    st.rerun()

        with tab_cli:
            mostrar_cadastro_contatos('clientes','Cliente','👤 Clientes','cad_cli')
        with tab_forn:
            mostrar_cadastro_contatos('fornecedores','Fornecedor','🏢 Fornecedores','cad_forn')

        # -------------------------------------------------------------
        # ABA 3: GRUPOS
        # -------------------------------------------------------------
        with tab_grup:
            st.markdown("### 🏷️ Grupos de produtos")
            if st.session_state.get('grupo_cad_aviso'):
                st.success(st.session_state.pop('grupo_cad_aviso'))

            def salvar_grupo_cadastro(nome, grupo_id=None):
                nome = nome.strip().upper()
                if not nome:
                    raise ValueError('Informe o nome do grupo.')
                if conn.in_transaction:
                    raise ValueError('Há uma operação pendente. Atualize a tela e tente novamente.')
                with conn:
                    conn.execute('BEGIN IMMEDIATE')
                    if conn.execute('SELECT 1 FROM grupos WHERE TRIM(grupo)=? COLLATE NOCASE AND id<>?', (nome, grupo_id or 0)).fetchone():
                        raise ValueError('Já existe um grupo com esse nome.')
                    if grupo_id is None:
                        conn.execute('INSERT INTO grupos (grupo) VALUES (?)', (nome,))
                        return 0
                    anterior = conn.execute('SELECT grupo FROM grupos WHERE id=?', (grupo_id,)).fetchone()
                    if not anterior:
                        raise ValueError('Grupo não encontrado.')
                    if anterior[0] == nome:
                        return 0
                    conn.execute('UPDATE grupos SET grupo=? WHERE id=?', (nome, grupo_id))
                    return conn.execute('UPDATE produtos SET grupo=? WHERE TRIM(grupo)=TRIM(?) COLLATE NOCASE', (nome, anterior[0])).rowcount

            with st.expander("➕ Cadastrar grupo"):
                with st.form("form_cad_grup", clear_on_submit=True):
                    n_grup = st.text_input("Nome do grupo", key="grupo_cad_novo")
                    salvar_novo_grupo = st.form_submit_button("💾 Salvar grupo", type="primary")
                if salvar_novo_grupo:
                    try:
                        salvar_grupo_cadastro(n_grup)
                    except Exception as erro:
                        st.error(str(erro))
                    else:
                        st.session_state.grupo_cad_aviso = 'Grupo cadastrado com sucesso.'
                        st.rerun()

            df_grupos_cad = carregar_dados("""SELECT g.id AS ID, g.grupo AS Grupo,
                (SELECT COUNT(*) FROM produtos p WHERE TRIM(p.grupo)=TRIM(g.grupo) COLLATE NOCASE) AS Produtos
                FROM grupos g ORDER BY g.grupo COLLATE NOCASE""")
            busca_grupo_cad = st.text_input("🔎 Buscar grupo pelo nome", key="grupo_cad_busca")
            grupos_filtrados_cad = df_grupos_cad
            if not df_grupos_cad.empty and busca_grupo_cad.strip():
                grupos_filtrados_cad = df_grupos_cad[df_grupos_cad['Grupo'].fillna('').str.contains(busca_grupo_cad.strip(), case=False, regex=False)]
            resumo_grupos_cad = st.columns(2)
            resumo_grupos_cad[0].metric("Total de grupos", len(df_grupos_cad))
            resumo_grupos_cad[1].metric("Encontrados na busca", len(grupos_filtrados_cad))
            if grupos_filtrados_cad.empty:
                st.info("Nenhum grupo encontrado.")
            else:
                st.dataframe(grupos_filtrados_cad, hide_index=True, use_container_width=True)
                rotulos_grupos_cad = {int(r['ID']):f"{r['Grupo']} · {r['Produtos']} produto(s)" for _,r in grupos_filtrados_cad.iterrows()}
                grupo_id_cad = st.selectbox("Selecione o grupo para editar", list(rotulos_grupos_cad), format_func=lambda i:rotulos_grupos_cad[i], key="grupo_cad_sel")
                grupo_linha_cad = grupos_filtrados_cad.loc[grupos_filtrados_cad['ID']==grupo_id_cad].iloc[0]
                with st.form(f"grupo_cad_editar_{grupo_id_cad}"):
                    nome_grupo_cad = st.text_input("Nome do grupo", value=str(grupo_linha_cad['Grupo']), key=f"grupo_cad_nome_{grupo_id_cad}")
                    st.caption("O novo nome será aplicado aos produtos vinculados. O histórico de compras e vendas preserva o nome original.")
                    salvar_edicao_grupo = st.form_submit_button("✏️ Salvar alterações do grupo", type="primary")
                if salvar_edicao_grupo:
                    try:
                        atualizados_grupo = salvar_grupo_cadastro(nome_grupo_cad, grupo_id_cad)
                    except Exception as erro:
                        st.error(str(erro))
                    else:
                        st.session_state.grupo_cad_aviso = f'Grupo salvo. Produtos atualizados: {atualizados_grupo}.'
                        st.rerun()
                with st.expander("🗑️ Excluir grupo"):
                    em_uso_grupo = int(grupo_linha_cad['Produtos']) > 0
                    if em_uso_grupo:
                        st.info("Transfira os produtos vinculados para outro grupo antes de excluir.")
                    confirmar_grupo = st.checkbox("Confirmo a exclusão deste grupo", key=f"grupo_cad_confirma_{grupo_id_cad}", disabled=em_uso_grupo)
                    if st.button("Excluir grupo", key=f"grupo_cad_excluir_{grupo_id_cad}", disabled=em_uso_grupo or not confirmar_grupo):
                        with conn:
                            excluido_grupo = conn.execute("""DELETE FROM grupos WHERE id=? AND NOT EXISTS
                                (SELECT 1 FROM produtos WHERE TRIM(produtos.grupo)=TRIM(grupos.grupo) COLLATE NOCASE)""", (grupo_id_cad,)).rowcount
                        if excluido_grupo:
                            st.session_state.grupo_cad_aviso = 'Grupo excluído.'
                            st.rerun()
                        st.error("O grupo está em uso ou já foi excluído.")

    # -------------------------------------------------------------
    # 6. MÓDULO RH (RECURSOS HUMANOS)
    # -------------------------------------------------------------
    elif menu_admin == "👥 Gestão de Recursos Humanos (RH)":
        st.subheader("👥 Gestão de Recursos Humanos (RH)")
        aba_colab, aba_pag = st.tabs(["👥 Colaboradores", "💸 Registar Pagamentos / Vales"])

        with aba_colab:
            sub_tab_cad, sub_tab_ger = st.tabs(["➕ Cadastrar Novo Colaborador", "🛠️ Editar / Excluir Colaboradores"])

            with sub_tab_cad:
                with st.form("form_cad_func"):
                    n_func = st.text_input("Nome Completo")
                    c_func = st.text_input("Cargo")
                    s_func = st.number_input("Salário Base (R$)", value=1412.00)
                    if st.form_submit_button("Salvar Colaborador", type="primary"):
                        if n_func.strip():
                            cursor = conn.cursor()
                            cursor.execute("INSERT INTO funcionarios (nome, cargo, salario) VALUES (?, ?, ?)", (n_func, c_func, s_func))
                            conn.commit()
                            st.success("Colaborador cadastrado com sucesso!")
                            st.rerun()
                        else:
                            st.error("Preencha o nome do colaborador.")

                st.markdown("### 📋 Colaboradores Cadastrados")
                st.dataframe(carregar_dados("SELECT * FROM funcionarios"), use_container_width=True)

            with sub_tab_ger:
                st.markdown("### 📋 Selecione um Colaborador para Editar ou Excluir")
                df_funcs_all = carregar_dados("SELECT * FROM funcionarios")
                if not df_funcs_all.empty:
                    df_funcs_all['label'] = df_funcs_all['id'].astype(str) + " - " + df_funcs_all['nome'] + " (" + df_funcs_all['cargo'] + ")"
                    lista_labels = df_funcs_all['label'].tolist()
                    
                    colab_selecionado_edit = st.selectbox("Selecione o Colaborador", lista_labels, key="sel_colab_edit_key")
                    
                    f_row = df_funcs_all[df_funcs_all['label'] == colab_selecionado_edit].iloc[0]
                    
                    with st.form("form_edit_colaborador"):
                        ed_nome_f = st.text_input("Nome Completo", value=str(f_row.get('nome', '')))
                        ed_cargo_f = st.text_input("Cargo", value=str(f_row.get('cargo', '')))
                        ed_salario_f = st.number_input("Salário Base (R$)", value=float(f_row.get('salario', 1412.00)), format="%.2f")

                        col_btn_f1, col_btn_f2 = st.columns(2)
                        with col_btn_f1:
                            btn_salvar_alt_f = st.form_submit_button("✏️ Salvar / Alterar Colaborador", type="primary")
                        with col_btn_f2:
                            btn_excluir_f = st.form_submit_button("🗑️ Excluir Colaborador")

                        if btn_salvar_alt_f:
                            try:
                                cursor = conn.cursor()
                                cursor.execute("""
                                    UPDATE funcionarios SET nome = ?, cargo = ?, salario = ? WHERE id = ?
                                """, (ed_nome_f, ed_cargo_f, ed_salario_f, int(f_row['id'])))
                                conn.commit()
                                st.success("✅ Colaborador atualizado com sucesso!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao atualizar colaborador: {e}")

                        if btn_excluir_f:
                            try:
                                cursor = conn.cursor()
                                cursor.execute("DELETE FROM funcionarios WHERE id = ?", (int(f_row['id']),))
                                conn.commit()
                                st.success("🗑️ Colaborador excluído com sucesso!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao excluir colaborador: {e}")
                else:
                    st.info("Nenhum colaborador cadastrado.")

        with aba_pag:
            funcs = carregar_coluna("funcionarios", "nome")
            if funcs:
                colab_sel = st.selectbox("Colaborador", funcs)
                val_pag = st.number_input("Valor Pagamento (R$)", min_value=0.0)
                if st.button("Registar Pagamento"):
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO pagamentos_funcionarios (colaborador, valor, data_pagamento) VALUES (?, ?, ?)",
                                   (colab_sel, val_pag, datetime.now().strftime("%Y-%m-%d")))
                    conn.commit()
                    st.success("Pagamento efetuado com sucesso!")
                    st.rerun()

    # -------------------------------------------------------------
    # 7. GESTÃO DE UTILIZADORES E LOGINS
    # -------------------------------------------------------------
    elif menu_admin == "🔐 Gestão de Utilizadores e Logins":
        st.subheader("🔐 Gestão de Logins e Permissões de Acesso aos Menus")
        
        tab_novo_usr, tab_ger_usr = st.tabs(["➕ Cadastrar Novo Utilizador", "🛠️ Editar / Excluir Utilizadores"])

        with tab_novo_usr:
            with st.form("form_cad_usuario_novo"):
                st.markdown("### Preencha os dados do novo funcionário")
                col_u1, col_u2 = st.columns(2)
                with col_u1:
                    nome_usuario = st.text_input("Nome Completo do Funcionário")
                    login_usuario = st.text_input("Login de Acesso (ex: joao.silva)")
                with col_u2:
                    senha_usuario = st.text_input("Senha de Acesso", type="password")
                    cargo_usuario = st.selectbox("Cargo / Nível", ["Vendedor", "Caixa", "Gerente", "Administrador"])

                st.markdown("#### 🎯 Permissões de Acesso (Menus Laterais)")
                col_p1, col_p2, col_p3 = st.columns(3)
                with col_p1:
                    p_pdv = st.checkbox("🛒 PDV — Frente de Caixa", value=True)
                    p_fin = st.checkbox("📊 Fechamento & Financeiro", value=False)
                    p_reg_v = st.checkbox("🛒 Registrar Venda", value=True)
                    p_comp = st.checkbox("📦 Entrada de Estoque", value=False)
                with col_p2:
                    p_cad = st.checkbox("👥 Cadastros (Clientes/Forn)", value=True)
                    p_rh = st.checkbox("👥 Recursos Humanos (RH)", value=False)
                    p_usr = st.checkbox("🔐 Gestão de Utilizadores", value=False)
                    p_bkp = st.checkbox("💾 Backup e Restauração", value=False)
                with col_p3:
                    p_cr = st.checkbox("💸 Contas a Receber", value=True)
                    p_est = st.checkbox("📦 Estoque de Produtos", value=True)
                    p_cfg = st.checkbox("🏢 Configurações Empresa", value=False)

                if st.form_submit_button("💾 Salvar Novo Utilizador", type="primary"):
                    if not login_usuario.strip() or not senha_usuario.strip():
                        st.error("Preencha o login e a senha.")
                    else:
                        try:
                            cursor = conn.cursor()
                            cursor.execute("""
                                INSERT INTO usuarios (
                                    usuario, login, senha, cargo, 
                                    perm_pdv, perm_financeiro, perm_registrar_venda, perm_compras, 
                                    perm_cadastros, perm_rh, perm_usuarios, perm_backup, 
                                    perm_contas_receber, perm_estoque, perm_configuracoes
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                nome_usuario, login_usuario.strip().lower(), senha_usuario, cargo_usuario,
                                1 if p_pdv else 0, 1 if p_fin else 0, 1 if p_reg_v else 0, 1 if p_comp else 0,
                                1 if p_cad else 0, 1 if p_rh else 0, 1 if p_usr else 0, 1 if p_bkp else 0,
                                1 if p_cr else 0, 1 if p_est else 0, 1 if p_cfg else 0
                            ))
                            conn.commit()
                            st.success(f"✅ Utilizador '{login_usuario}' criado com sucesso!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao salvar utilizador (talvez o login já exista): {e}")

        with tab_ger_usr:
            st.markdown("### 📋 Selecione um Utilizador para Editar ou Excluir")
            df_users_all = carregar_dados("SELECT * FROM usuarios")
            if not df_users_all.empty:
                lista_logins = df_users_all['login'].tolist()
                user_selecionado_edit = st.selectbox("Selecione o Login do Utilizador", lista_logins, key="sel_user_edit_key")
                
                u_row = df_users_all[df_users_all['login'] == user_selecionado_edit].iloc[0]
                
                with st.form("form_edit_usuario"):
                    ed_nome = st.text_input("Nome Completo", value=str(u_row.get('usuario', '')))
                    ed_login = st.text_input("Login de Acesso", value=str(u_row.get('login', '')))
                    ed_senha = st.text_input("Nova Senha (ou mantenha a atual)", value=str(u_row.get('senha', '')))
                    ed_cargo = st.selectbox("Cargo", ["Vendedor", "Caixa", "Gerente", "Administrador"], index=["Vendedor", "Caixa", "Gerente", "Administrador"].index(str(u_row.get('cargo', 'Vendedor'))) if str(u_row.get('cargo', 'Vendedor')) in ["Vendedor", "Caixa", "Gerente", "Administrador"] else 0)

                    st.markdown("#### 🎯 Atualizar Permissões de Acesso")
                    ep_pdv = st.checkbox("🛒 PDV — Frente de Caixa", value=bool(u_row.get('perm_pdv', 1)))
                    ep_fin = st.checkbox("📊 Fechamento & Financeiro", value=bool(u_row.get('perm_financeiro', 0)))
                    ep_reg_v = st.checkbox("🛒 Registrar Venda", value=bool(u_row.get('perm_registrar_venda', 1)))
                    ep_comp = st.checkbox("📦 Entrada de Estoque", value=bool(u_row.get('perm_compras', 0)))
                    ep_cad = st.checkbox("👥 Cadastros (Clientes/Forn)", value=bool(u_row.get('perm_cadastros', 1)))
                    ep_rh = st.checkbox("👥 Recursos Humanos (RH)", value=bool(u_row.get('perm_rh', 0)))
                    ep_usr = st.checkbox("🔐 Gestão de Utilizadores", value=bool(u_row.get('perm_usuarios', 0)))
                    ep_bkp = st.checkbox("💾 Backup e Restauração", value=bool(u_row.get('perm_backup', 0)))
                    ep_cr = st.checkbox("💸 Contas a Receber", value=bool(u_row.get('perm_contas_receber', 1)))
                    ep_est = st.checkbox("📦 Estoque de Produtos", value=bool(u_row.get('perm_estoque', 1)))
                    ep_cfg = st.checkbox("🏢 Configurações Empresa", value=bool(u_row.get('perm_configuracoes', 0)))

                    col_btn_ed1, col_btn_ed2 = st.columns(2)
                    with col_btn_ed1:
                        btn_salvar_alt = st.form_submit_button("✏️ Salvar / Alterar Utilizador", type="primary")
                    with col_btn_ed2:
                        btn_excluir_usr = st.form_submit_button("🗑️ Excluir Utilizador")

                    if btn_salvar_alt:
                        try:
                            cursor = conn.cursor()
                            cursor.execute("""
                                UPDATE usuarios SET 
                                    usuario = ?, login = ?, senha = ?, cargo = ?,
                                    perm_pdv = ?, perm_financeiro = ?, perm_registrar_venda = ?, perm_compras = ?,
                                    perm_cadastros = ?, perm_rh = ?, perm_usuarios = ?, perm_backup = ?,
                                    perm_contas_receber = ?, perm_estoque = ?, perm_configuracoes = ?
                                WHERE id = ?
                            """, (
                                ed_nome, ed_login.strip().lower(), ed_senha, ed_cargo,
                                1 if ep_pdv else 0, 1 if ep_fin else 0, 1 if ep_reg_v else 0, 1 if ep_comp else 0,
                                1 if ep_cad else 0, 1 if ep_rh else 0, 1 if ep_usr else 0, 1 if ep_bkp else 0,
                                1 if ep_cr else 0, 1 if ep_est else 0, 1 if ep_cfg else 0, int(u_row['id'])
                            ))
                            conn.commit()
                            st.success("✅ Utilizador atualizado com sucesso!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao atualizar utilizador: {e}")

                    if btn_excluir_usr:
                        if ed_login.strip().lower() == "administrador":
                            st.error("❌ Não é permitido excluir o administrador principal do sistema.")
                        else:
                            try:
                                cursor = conn.cursor()
                                cursor.execute("DELETE FROM usuarios WHERE id = ?", (int(u_row['id']),))
                                conn.commit()
                                st.success("🗑️ Utilizador excluído com sucesso!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao excluir utilizador: {e}")
            else:
                st.info("Nenhum utilizador cadastrado além do administrador padrão.")

    # -------------------------------------------------------------
    # 8. BACKUP E RESTAURAÇÃO
    # -------------------------------------------------------------
    elif menu_admin == "💾 Backup e Restauração" and (not empresa_doc or is_admin_master):
        st.subheader("💾 Central de Backup e Restauração")
        
        tab_bkp_down, tab_bkp_up = st.tabs(["📥 Baixar Backup", "📤 Restaurar Backup"])

        with tab_bkp_down:
            st.markdown("### 📥 Fazer Backup dos Dados Atualizados")
            st.info("Gere uma cópia completa, incluindo vendas, estoque, fotos e configurações.")
            if st.button("🔄 Gerar backup atualizado", type="primary", key="gerar_backup_completo"):
                try:
                    with st.spinner("Gerando e verificando o backup..."):
                        st.session_state['_backup_download'] = gerar_backup_sqlite(conn)
                        st.session_state['_backup_download_nome'] = f"backup_crm_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.db"
                    st.success("Backup completo gerado e verificado. Clique abaixo para baixar.")
                except Exception as erro:
                    st.error(f"Não foi possível gerar o backup: {erro}")
            if st.session_state.get('_backup_download'):
                st.download_button("📥 Baixar arquivo de backup (.db)",
                                   data=st.session_state['_backup_download'],
                                   file_name=st.session_state['_backup_download_nome'],
                                   mime="application/octet-stream", key="baixar_backup_completo")

        with tab_bkp_up:
            st.markdown("### 📤 Restaurar arquivo de backup (.db)")
            st.warning("A restauração substitui os dados atuais pelos dados do backup. Feche o sistema nas outras abas e dispositivos antes de continuar.")
            uploaded_db = st.file_uploader("Selecione o arquivo de backup (.db)", type=["db"], key="arquivo_restaurar_validado")
            if uploaded_db is not None:
                st.caption(f"Arquivo selecionado: {uploaded_db.size / 1024:,.1f} KB. O conteúdo será validado antes da restauração.")
                if st.button("🔴 Confirmar e Restaurar Backup Agora", type="primary", key="restaurar_backup_validado"):
                    try:
                        with st.spinner("Validando o arquivo e restaurando os dados..."):
                            with _sqlite_init_lock():
                                restaurar_backup_sqlite(conn, uploaded_db.getvalue(),
                                    lambda dados: st.session_state.__setitem__('_backup_antes_restauracao', dados))
                    except Exception as erro:
                        st.error(f"Não foi possível restaurar: {erro}")
                    else:
                        st.cache_data.clear()
                        # Limpa dados da venda e credenciais da base anterior.
                        for chave in list(st.session_state):
                            if chave not in {'_backup_antes_restauracao', '_empresa_doc'}:
                                del st.session_state[chave]
                        st.session_state['_backup_restaurado_ok'] = True
                        st.rerun()

    # -------------------------------------------------------------
    # MÓDULO CONTAS A RECEBER (COM COMPROVANTE / EXTRATO PDF)
    # -------------------------------------------------------------
    elif "Contas a Receber" in str(menu_admin):
        import io
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

        def gerar_pdf_comprovante_cliente(nome_cliente, df_contas_cliente):
            import io
            from datetime import datetime, timezone, timedelta
            from reportlab.lib.pagesizes import letter
            from reportlab.lib import colors
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

            buffer = io.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
            story = []

            styles = getSampleStyleSheet()
            
            style_header_title = ParagraphStyle(
                'HeaderTitle',
                parent=styles['Normal'],
                fontName='Helvetica-Bold',
                fontSize=18,
                textColor=colors.HexColor('#004085'),
                alignment=1,
                spaceAfter=8
            )
            style_header_sub = ParagraphStyle(
                'HeaderSub',
                parent=styles['Normal'],
                fontName='Helvetica',
                fontSize=9,
                alignment=1,
                spaceAfter=2
            )
            style_title = ParagraphStyle(
                'TitleDoc',
                parent=styles['Normal'],
                fontName='Helvetica-Bold',
                fontSize=12,
                alignment=1,
                spaceAfter=10
            )

            # Cabeçalho da Empresa
            story.append(Paragraph(f"<b>{nome_empresa_header}</b>", style_header_title))
            story.append(Paragraph(f"CNPJ/CPF: {html.escape(doc_empresa_padrao)}", style_header_sub))
            contato = str(reg_emp.get("fone") or fone_empresa_padrao)
            if contato:
                story.append(Paragraph(f"CONTATO: {html.escape(contato)}", style_header_sub))
            story.append(Spacer(1, 4))
            story.append(Paragraph("Extrato Financeiro / Comprovante do Cliente", style_title))

            # Ajusta para o fuso horário do Brasil (UTC-3)
            fuso_brasil = timezone(timedelta(hours=-3))
            data_hora_atual = datetime.now(fuso_brasil).strftime("%d/%m/%Y %H:%M:%S")
            
            story.append(Paragraph(f"<b>Cliente: {nome_cliente}</b> | <b>Gerado em: {data_hora_atual}</b>", styles['Normal']))
            story.append(Spacer(1, 8))

            # Totais
            total_dev = df_contas_cliente['restante'].sum()
            total_pago = df_contas_cliente['valor_pago'].sum()

            data_totais = [
                [f"Saldo Devedor (Falta Pagar): R$ {total_dev:,.2f}", f"Total Ja Pago: R$ {total_pago:,.2f}"]
            ]
            t_totais = Table(data_totais, colWidths=[270, 270])
            t_totais.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#EAEAEA')),
                ('TEXTCOLOR', (0,0), (-1,-1), colors.black),
                ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
                ('FONTSIZE', (0,0), (-1,-1), 10),
                ('BOX', (0,0), (-1,-1), 1, colors.black),
                ('INNERGRID', (0,0), (-1,-1), 1, colors.black),
                ('PADDING', (0,0), (-1,-1), 6),
            ]))
            story.append(t_totais)
            story.append(Spacer(1, 12))

            # Tabela de Detalhamento com datas no formato DD/MM/YYYY
            data_tabela = [["ID", "Descrição / Parcela", "Total (R$)", "Pago (R$)", "Restante (R$)", "Vencimento", "Status"]]
            for _, r in df_contas_cliente.iterrows():
                venc_str = str(r['vencimento'])[:10]
                try:
                    dt_obj = datetime.strptime(venc_str, "%Y-%m-%d")
                    venc_str = dt_obj.strftime("%d/%m/%Y")
                except Exception:
                    pass

                data_tabela.append([
                    str(r['id']),
                    str(r['descricao']),
                    f"{r['valor']:,.2f}",
                    f"{r['valor_pago']:,.2f}",
                    f"{r['restante']:,.2f}",
                    venc_str,
                    str(r['status'])
                ])

            t_det = Table(data_tabela, colWidths=[30, 150, 70, 70, 70, 80, 70])
            t_det.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#004085')),
                ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE', (0,0), (-1,0), 9),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                ('PADDING', (0,0), (-1,-1), 4),
            ]))
            story.append(t_det)

            doc.build(story)
            buffer.seek(0)
            return buffer.getvalue()

        try:
            st.subheader(f"💰 Contas a Receber / Haveres — {nome_empresa_header} | 👤 Utilizador: {usr_exibicao}")
            
            if st.session_state.get('aviso_parcelas_recuperadas'):
                st.success(st.session_state.pop('aviso_parcelas_recuperadas'))
            with st.expander("🔧 Recuperar parcelas de venda do PDV"):
                st.caption("Use para vendas antigas cujo cupom mostra Parcelado, mas que ficaram sem contas a receber. Esta operação não cria outra venda, não altera estoque e não registra recebimento.")
                with st.form('form_recuperar_parcelas_pdv'):
                    id_recuperar = st.number_input("ID da primeira linha da venda parcelada", min_value=1, value=21, step=1)
                    primeiro_recuperar = st.date_input("Primeiro vencimento das parcelas a recuperar", value=date.today() + dt.timedelta(days=30), format="DD/MM/YYYY", key="primeiro_vencimento_recuperar")
                    campos_autorizacao('autorizar_recuperar_parcelas')
                    btn_recuperar = st.form_submit_button("Recuperar parcelas desta venda", type="primary", on_click=capturar_autorizacao, args=('autorizar_recuperar_parcelas',))
                if btn_recuperar:
                    login_rec, senha_rec = consumir_autorizacao('autorizar_recuperar_parcelas')
                    try:
                        principal_rec, numero_rec = recuperar_parcelas_pdv(conn, id_recuperar, primeiro_recuperar, usr_exibicao, login_rec, senha_rec)
                    except Exception as erro:
                        st.error(f"Não foi possível recuperar: {erro}")
                    else:
                        st.session_state['aviso_parcelas_recuperadas'] = f"Venda #{principal_rec}: {numero_rec} parcelas criadas em Contas a Receber. Estoque e caixa mantidos."
                        st.rerun()
                    finally:
                        senha_rec = ''

            conn_cr = sqlite3.connect(banco_empresa, timeout=30.0)
            cursor_cr = conn_cr.cursor()
            
            cursor_cr.execute("""
                CREATE TABLE IF NOT EXISTS contas_receber (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cliente TEXT,
                    valor REAL,
                    valor_pago REAL DEFAULT 0.0,
                    vencimento TEXT,
                    data_lancamento TEXT,
                    data_quitacao TEXT,
                    status TEXT,
                    descricao TEXT
                )
            """)
            conn_cr.commit()
            
            for sql_alt in [
                "ALTER TABLE contas_receber ADD COLUMN valor_pago REAL DEFAULT 0.0",
                "ALTER TABLE contas_receber ADD COLUMN data_quitacao TEXT",
                "ALTER TABLE contas_receber ADD COLUMN data_lancamento TEXT"
            ]:
                try:
                    cursor_cr.execute(sql_alt)
                    conn_cr.commit()
                except Exception:
                    pass

            df_contas = pd.read_sql_query("SELECT * FROM contas_receber WHERE COALESCE(status,'') != 'Cancelado' ORDER BY id DESC", conn_cr)
            conn_cr.close()
            
            if df_contas is not None and not df_contas.empty:
                if 'valor_pago' not in df_contas.columns:
                    df_contas['valor_pago'] = 0.0
                
                df_contas['valor'] = pd.to_numeric(df_contas['valor'], errors='coerce').fillna(0.0)
                df_contas['valor_pago'] = pd.to_numeric(df_contas['valor_pago'], errors='coerce').fillna(0.0)
                df_contas['restante'] = df_contas['valor'] - df_contas['valor_pago']
                
                def moeda_contas(valor):
                    return "R$ " + f"{float(valor):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")

                vencimentos_contas = pd.to_datetime(df_contas['vencimento'], errors='coerce')
                em_aberto = df_contas['restante'] > 0.005
                atrasadas = em_aberto & (vencimentos_contas.dt.date < date.today())
                df_contas['situacao_tela'] = 'Quitada'
                df_contas.loc[em_aberto, 'situacao_tela'] = 'A vencer'
                df_contas.loc[atrasadas, 'situacao_tela'] = 'Vencida'
                df_contas.loc[em_aberto & vencimentos_contas.isna(), 'situacao_tela'] = 'Sem vencimento'
                clientes_filtro = ['Todos os clientes'] + sorted(df_contas['cliente'].fillna('').astype(str).unique().tolist())
                with st.container(border=True):
                    filtros = st.columns([2, 1.3, 1.3])
                    cliente_filtro = filtros[0].selectbox("Cliente", clientes_filtro, key="cr_cliente_filtro")
                    situacao_filtro = filtros[1].selectbox("Situação", ['Todas', 'Em aberto', 'Vencida', 'A vencer', 'Quitada', 'Sem vencimento'], key="cr_situacao_filtro")
                    periodo_filtro = filtros[2].selectbox("Vencimento", ['Todos', 'Hoje', 'Próximos 7 dias', 'Este mês', 'Escolher período'], key="cr_periodo_filtro")
                    inicio_filtro = fim_filtro = None
                    if periodo_filtro == 'Escolher período':
                        datas_filtro = st.columns(2)
                        inicio_filtro = datas_filtro[0].date_input("De", value=date.today(), key="cr_inicio_filtro")
                        fim_filtro = datas_filtro[1].date_input("Até", value=date.today() + timedelta(days=30), key="cr_fim_filtro")
                mascara_contas = pd.Series(True, index=df_contas.index)
                if cliente_filtro != 'Todos os clientes':
                    mascara_contas &= df_contas['cliente'].fillna('').astype(str) == cliente_filtro
                if situacao_filtro == 'Em aberto':
                    mascara_contas &= em_aberto
                elif situacao_filtro != 'Todas':
                    mascara_contas &= df_contas['situacao_tela'] == situacao_filtro
                if periodo_filtro != 'Todos':
                    if periodo_filtro == 'Hoje':
                        inicio_filtro = fim_filtro = date.today()
                    elif periodo_filtro == 'Próximos 7 dias':
                        inicio_filtro, fim_filtro = date.today(), date.today() + timedelta(days=7)
                    elif periodo_filtro == 'Este mês':
                        inicio_filtro = date.today().replace(day=1)
                        fim_filtro = (inicio_filtro.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
                    if inicio_filtro > fim_filtro:
                        st.warning("A data inicial deve ser anterior ou igual à data final.")
                        mascara_contas &= False
                    else:
                        mascara_contas &= vencimentos_contas.dt.date.between(inicio_filtro, fim_filtro)
                df_lista_contas = df_contas.loc[mascara_contas].copy()
                st.caption("Resumo das contas nos filtros selecionados. Recebido corresponde ao valor já pago dessas contas, independentemente da data do recebimento.")
                totais_contas = st.columns(3)
                totais_contas[0].metric("💰 Em aberto", moeda_contas(df_lista_contas['restante'].clip(lower=0).sum()))
                totais_contas[1].metric("🔴 Vencido · parte do saldo em aberto", moeda_contas(df_lista_contas.loc[df_lista_contas['situacao_tela'] == 'Vencida', 'restante'].clip(lower=0).sum()))
                totais_contas[2].metric("✅ Recebido", moeda_contas(df_lista_contas['valor_pago'].sum()))
                st.markdown("### 📋 Contas e parcelas")
                if df_lista_contas.empty:
                    st.info("Nenhuma conta encontrada com esses filtros.")
                else:
                    tabela_contas = df_lista_contas[['id','cliente','descricao','valor','valor_pago','restante','vencimento','situacao_tela']].copy()
                    tabela_contas['vencimento'] = pd.to_datetime(tabela_contas['vencimento'], errors='coerce').dt.strftime('%d/%m/%Y').fillna('Não informado')
                    tabela_contas['situacao_tela'] = tabela_contas['situacao_tela'].map({'Vencida':'🔴 Vencida','A vencer':'🟠 A vencer','Quitada':'🟢 Quitada','Sem vencimento':'⚪ Sem vencimento'})
                    tabela_contas.columns = ['Conta','Cliente','Descrição','Valor (R$)','Recebido (R$)','Saldo (R$)','Vencimento','Situação']
                    st.dataframe(tabela_contas, hide_index=True, use_container_width=True,
                        column_config={nome:st.column_config.NumberColumn(format="%.2f") for nome in ['Valor (R$)','Recebido (R$)','Saldo (R$)']})
                    periodo_pdf_contas = (
                        f"{inicio_filtro:%d/%m/%Y} a {fim_filtro:%d/%m/%Y}"
                        if inicio_filtro is not None and fim_filtro is not None else "Todos"
                    )
                    st.download_button("📄 Baixar relatório de contas a receber (PDF)",
                        data=gerar_pdf_contas_receber(nome_empresa_header, df_lista_contas,
                            cliente_filtro, situacao_filtro, periodo_pdf_contas),
                        file_name="contas_a_receber.pdf", mime="application/pdf",
                        key="baixar_pdf_contas_receber")

                if not df_lista_contas.empty:
                    st.markdown("### ⚙️ Gerenciar Conta / Registrar Haver ou Pagamento")
    
                    df_contas['label_conta'] = "Conta #" + df_contas['id'].astype(str) + " - " + df_contas['cliente'].astype(str) + " (Restante: R$ " + df_contas['restante'].astype(str) + ")"
                    df_lista_contas['label_conta'] = df_contas.loc[df_lista_contas.index, 'label_conta']
                    lista_contas_sel = df_lista_contas['label_conta'].tolist()
    
                    conta_escolhida = st.selectbox("Selecione a Conta / Parcela para Baixa ou Haver:", lista_contas_sel, key="sel_conta_segura_coringa")
    
                    row_conta_sel = df_contas[df_contas['label_conta'] == conta_escolhida].iloc[0]
                    id_conta_atual = int(row_conta_sel['id'])
                    valor_total_conta = float(row_conta_sel['valor'])
                    valor_ja_pago = float(row_conta_sel.get('valor_pago', 0.0) or 0.0)
                    restante_atual = valor_total_conta - valor_ja_pago
    
                    st.info(f"📌 **Detalhes:** Cliente: **{row_conta_sel['cliente']}** | Total: **R$ {valor_total_conta:,.2f}** | Já Pago: **R$ {valor_ja_pago:,.2f}** | Restante: **R$ {restante_atual:,.2f}**")
    
                    if st.session_state.get('aviso_recebimento'):
                        st.success(st.session_state.pop('aviso_recebimento'))
                    caixa_recebimento_aberto = conn.execute("SELECT COUNT(*) FROM caixa_sessoes WHERE status='ABERTO'").fetchone()[0] == 1
                    if not caixa_recebimento_aberto:
                        st.warning("Caixa fechado ou sessão de caixa indefinida. Abra um caixa antes de receber: a conta não será baixada sem lançamento financeiro.")
                    chave_operacao = f'operacao_receber_{id_conta_atual}'
                    if chave_operacao not in st.session_state:
                        st.session_state[chave_operacao] = uuid.uuid4().hex
                    with st.form(f"form_baixa_conta_segura_{id_conta_atual}"):
                        tipo_operacao = st.radio("Escolha a Ação:", ["Receber Valor Total (Quitar)", "Dar Haver / Pagamento Parcial"], horizontal=True)
                        valor_operacao = st.number_input("Valor da Operação (R$):", min_value=0.01, value=float(max(0.01, restante_atual)), format="%.2f")
                        data_pagto_input = st.date_input("Data do Pagamento / Haver:", value=datetime.now())
                        forma_recebimento_conta = st.selectbox("Forma de pagamento do recebimento", ["Dinheiro", "Pix", "Cartão Débito", "Cartão Crédito"], key="forma_recebimento_conta")
                        col_b1, col_b2 = st.columns(2)
                        with col_b1:
                            btn_executar = st.form_submit_button("✅ Confirmar Operação", type="primary", use_container_width=True,
                                disabled=(not caixa_recebimento_aberto or restante_atual <= 0))
                        with col_b2:
                            btn_excluir_conta = st.form_submit_button("🗑️ Excluir Conta", use_container_width=True, disabled=(valor_ja_pago > 0))
                    if restante_atual <= 0:
                        st.caption("Conta quitada: novos recebimentos estão bloqueados.")
                    if btn_executar:
                        try:
                            recebido, restante, sessao_recebimento = registrar_recebimento_seguro(
                                conn, id_conta_atual, valor_operacao, tipo_operacao == "Receber Valor Total (Quitar)",
                                forma_recebimento_conta, data_pagto_input, usr_exibicao, st.session_state[chave_operacao])
                        except Exception as erro:
                            st.error(f"Não foi possível receber: {erro}")
                        else:
                            st.session_state.pop(chave_operacao, None)
                            st.session_state['aviso_recebimento'] = f"Recebidos R$ {recebido:,.2f} no caixa #{sessao_recebimento}. Restante: R$ {restante:,.2f}."
                            st.rerun()
                    if btn_excluir_conta:
                        try:
                            with conn:
                                cur_excluir = conn.execute('DELETE FROM contas_receber WHERE id=? AND COALESCE(valor_pago,0)=0', (id_conta_atual,))
                                if cur_excluir.rowcount != 1:
                                    raise ValueError('Contas com recebimento não podem ser excluídas.')
                        except Exception as erro:
                            st.error(str(erro))
                        else:
                            st.rerun()
    
                    # Repara somente baixas antigas sem movimento, sem alterar o valor já pago.
                    falta_caixa = valor_recebido_sem_caixa(conn, id_conta_atual)
                    if falta_caixa > 0:
                        st.warning(f"Esta conta possui R$ {falta_caixa:,.2f} já baixados, mas sem lançamento identificado no caixa.")
                        with st.expander("🔧 Regularizar recebimento antigo no caixa"):
                            st.caption("Confirme a forma em que o valor foi recebido. O lançamento será feito no caixa aberto atual, identificado como regularização. O valor pago da conta será mantido.")
                            prefixo_reg = f'autorizar_regularizacao_{id_conta_atual}'
                            chave_reg = f'operacao_regularizar_{id_conta_atual}'
                            if chave_reg not in st.session_state:
                                st.session_state[chave_reg] = uuid.uuid4().hex
                            with st.form(f'form_regularizar_{id_conta_atual}'):
                                forma_reg = st.selectbox("Como esse valor foi recebido?", ["Dinheiro", "Pix", "Cartão Débito", "Cartão Crédito"], index=None, placeholder="Selecione a forma recebida")
                                data_reg = st.date_input("Data do recebimento original", value=datetime.now(), key=f'data_regularizar_{id_conta_atual}')
                                confirmar_reg = st.checkbox(f"Confirmo que R$ {falta_caixa:,.2f} foram recebidos e estão sem lançamento no caixa.")
                                campos_autorizacao(prefixo_reg)
                                btn_reg = st.form_submit_button("Registrar regularização no caixa aberto", type="primary",
                                    disabled=not caixa_recebimento_aberto, on_click=capturar_autorizacao, args=(prefixo_reg,))
                            if btn_reg:
                                login_reg, senha_reg = consumir_autorizacao(prefixo_reg)
                                try:
                                    if not confirmar_reg:
                                        raise ValueError('Confirme o recebimento anterior antes de regularizar.')
                                    recebido, restante, sessao_reg = registrar_recebimento_seguro(
                                        conn, id_conta_atual, 0, False, forma_reg, data_reg, usr_exibicao,
                                        st.session_state[chave_reg], regularizar=True, login_admin=login_reg, senha_admin=senha_reg)
                                except Exception as erro:
                                    st.error(f"Não foi possível regularizar: {erro}")
                                else:
                                    st.session_state.pop(chave_reg, None)
                                    st.session_state['aviso_recebimento'] = f"Regularização de R$ {recebido:,.2f} registrada no caixa #{sessao_reg}. A conta continua com o mesmo valor pago."
                                    st.rerun()
                                finally:
                                    senha_reg = ''
    
                    # Botão para gerar e baixar o Comprovante/Extrato do Cliente em PDF
                    st.markdown("---")
                    cliente_selecionado_nome = str(row_conta_sel['cliente'])
                    df_cliente_filtrado = df_contas[df_contas['cliente'] == cliente_selecionado_nome]
    
                    pdf_bytes = gerar_pdf_comprovante_cliente(cliente_selecionado_nome, df_cliente_filtrado)
    
                    st.download_button(
                        label=f"📄 Baixar Extrato / Comprovante PDF ({cliente_selecionado_nome})",
                        data=pdf_bytes,
                        file_name=f"comprovante_{cliente_selecionado_nome.lower().replace(' ', '_')}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )

            else:
                st.info("ℹ️ Nenhuma conta pendente encontrada.")
        except Exception as err_geral:
            st.error(f"❌ Ocorreu um erro ao carregar o módulo Contas a Receber: {err_geral}")
        
    # -------------------------------------------------------------
    # 10. ESTOQUE E PROMOÇÕES
    # -------------------------------------------------------------
    if "Estoque de Produtos" in str(menu_admin) or menu_admin == "📦 Estoque de Produtos":
        st.subheader("📦 Estoque de Produtos e Promoções")
        
        tab_estoque_geral, tab_deposito_promo, tab_comprados, tab_vendidos = st.tabs([
            "📋 Estoque Geral", 
            "🏷️ Depósito / Produtos para Promoção", 
            "📥 Produtos Comprados", 
            "📤 Produtos Vendidos"
        ])
        
        # -------------------------------------------------------------
        # ABA 1: ESTOQUE GERAL
        # -------------------------------------------------------------
        with tab_estoque_geral:
            st.markdown("### 📋 Produtos no Estoque Geral")
            
            try:
                garantir_colunas_produtos(conn)
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS produtos (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        codigo TEXT,
                        produto TEXT,
                        quantidade REAL,
                        valor_compra REAL,
                        valor_venda REAL,
                        grupo TEXT,
                        fornecedor TEXT
                    )
                """)
                conn.commit()
            except Exception:
                pass
    
            try:
                df_prods = carregar_dados("SELECT * FROM produtos")
            except Exception:
                df_prods = pd.DataFrame()
    
            if df_prods is not None and not df_prods.empty:
                def texto_filtro_estoque(valor):
                    texto = '' if pd.isna(valor) else str(valor).strip()
                    return '' if texto.lower() in {'nan','none','null'} else texto

                df_prods['grupo_filtro'] = df_prods['grupo'].apply(texto_filtro_estoque).replace('', 'Sem grupo')
                df_prods['fornecedor_filtro'] = df_prods['fornecedor'].apply(texto_filtro_estoque).replace('', 'Sem fornecedor')
                df_prods['saldo_tela'] = pd.to_numeric(df_prods['quantidade'], errors='coerce').fillna(0)
                df_prods['minimo_tela'] = pd.to_numeric(df_prods['estoque_minimo'], errors='coerce').fillna(0)
                df_prods['repor_tela'] = (df_prods['minimo_tela'] - df_prods['saldo_tela']).round(3).clip(lower=0).where(df_prods['minimo_tela'] > 0, 0)
                with st.container(border=True):
                    busca_estoque = st.text_input("🔎 Buscar produto por nome ou código", placeholder="Digite o nome ou o código de barras", key="est_busca")
                    filtros_est = st.columns(3)
                    filtro_grupo_est = filtros_est[0].selectbox("Grupo", ['Todos'] + sorted(df_prods['grupo_filtro'].unique().tolist()), key="est_grupo")
                    filtro_fornecedor_est = filtros_est[1].selectbox("Fornecedor", ['Todos'] + sorted(df_prods['fornecedor_filtro'].unique().tolist()), key="est_fornecedor")
                    filtro_saldo_est = filtros_est[2].selectbox("Estoque", ['Todos', 'Com saldo', 'Sem estoque', 'Saldo negativo', 'Precisa repor'], key="est_saldo")
                mascara_est = pd.Series(True, index=df_prods.index)
                if busca_estoque.strip():
                    termo_est = busca_estoque.strip()
                    mascara_est &= (df_prods['produto'].fillna('').astype(str).str.contains(termo_est, case=False, regex=False) |
                                    df_prods['codigo'].apply(texto_filtro_estoque).str.contains(termo_est, case=False, regex=False))
                if filtro_grupo_est != 'Todos':
                    mascara_est &= df_prods['grupo_filtro'] == filtro_grupo_est
                if filtro_fornecedor_est != 'Todos':
                    mascara_est &= df_prods['fornecedor_filtro'] == filtro_fornecedor_est
                if filtro_saldo_est == 'Com saldo':
                    mascara_est &= df_prods['saldo_tela'] > 0
                elif filtro_saldo_est == 'Sem estoque':
                    mascara_est &= df_prods['saldo_tela'] == 0
                elif filtro_saldo_est == 'Saldo negativo':
                    mascara_est &= df_prods['saldo_tela'] < 0
                elif filtro_saldo_est == 'Precisa repor':
                    mascara_est &= df_prods['repor_tela'] > 0
                df_filtrado_est = df_prods.loc[mascara_est].copy()
                resumo_est = st.columns(3)
                resumo_est[0].metric("📦 Produtos encontrados", len(df_filtrado_est))
                resumo_est[1].metric("🔴 Sem estoque", int((df_filtrado_est['saldo_tela'] == 0).sum()))
                resumo_est[2].metric("⚠️ Saldo negativo", int((df_filtrado_est['saldo_tela'] < 0).sum()))
                st.caption("Resumo dos filtros selecionados. Cada quantidade usa a unidade cadastrada no produto.")
                df_exib_est = pd.DataFrame(index=df_filtrado_est.index)
                df_exib_est['ID'] = df_filtrado_est['id']
                df_exib_est['Código'] = df_filtrado_est['codigo'].apply(texto_filtro_estoque)
                df_exib_est['Produto'] = df_filtrado_est['produto']
                df_exib_est['Unidade'] = df_filtrado_est['unidade'].apply(rotulo_unidade_medida)
                df_exib_est['Qtd. Estoque'] = df_filtrado_est['saldo_tela']
                df_exib_est['Situação'] = df_filtrado_est['saldo_tela'].apply(lambda saldo:'🔴 Sem estoque' if saldo == 0 else ('⚠️ Saldo negativo' if saldo < 0 else '🟢 Disponível'))
                df_exib_est['Preço Compra (R$)'] = pd.to_numeric(df_filtrado_est['valor_compra'], errors='coerce').fillna(0)
                df_exib_est['Preço Venda (R$)'] = pd.to_numeric(df_filtrado_est['valor_venda'], errors='coerce').fillna(0)
                df_exib_est['Grupo'] = df_filtrado_est['grupo_filtro']
                df_exib_est['Fornecedor'] = df_filtrado_est['fornecedor_filtro']
                df_exib_est['Estoque mínimo'] = df_filtrado_est['minimo_tela']
                df_exib_est['Sugestão de compra'] = df_filtrado_est['repor_tela']
                if df_exib_est.empty:
                    st.info("Nenhum produto encontrado com esses filtros.")
                else:
                    st.dataframe(df_exib_est, use_container_width=True, hide_index=True,
                        column_config={'Qtd. Estoque': st.column_config.NumberColumn(format='%.3f'),
                                       'Preço Compra (R$)': st.column_config.NumberColumn(format='%.2f'),
                                       'Preço Venda (R$)': st.column_config.NumberColumn(format='%.2f')})
                    filtros_pdf_estoque = {
                        'Busca': busca_estoque.strip() or 'Todos os produtos',
                        'Grupo': filtro_grupo_est,
                        'Fornecedor': filtro_fornecedor_est,
                        'Estoque': filtro_saldo_est,
                    }
                    st.download_button("📄 Baixar relatório de estoque (PDF)",
                        data=gerar_pdf_estoque(nome_empresa_header, df_exib_est, filtros_pdf_estoque),
                        file_name="relatorio_estoque.pdf", mime="application/pdf",
                        key="baixar_pdf_estoque")
                    itens_reposicao = df_exib_est.loc[df_exib_est['Sugestão de compra'] > 0]
                    st.caption("A lista de reposição usa os filtros atuais e os produtos com estoque mínimo definido.")
                    if not itens_reposicao.empty:
                        st.download_button(f"📄 Baixar lista de reposição (PDF) · {len(itens_reposicao)} produto(s)",
                            data=gerar_pdf_estoque(nome_empresa_header, itens_reposicao, filtros_pdf_estoque, reposicao=True),
                            file_name="lista_reposicao.pdf", mime="application/pdf", key="baixar_pdf_reposicao")
                        if "📦 Entrada de Estoque (Compras)" in opcoes_menu_disponiveis:
                            fornecedores_reposicao = sorted(
                                f for f in itens_reposicao['Fornecedor'].unique() if f != 'Sem fornecedor'
                            )
                            if fornecedores_reposicao:
                                fornecedor_reposicao = st.selectbox("Fornecedor para preparar a compra",
                                    fornecedores_reposicao, key="fornecedor_carrinho_reposicao")
                                if st.button("🛒 Adicionar sugestões ao carrinho de compras", key="adicionar_reposicao"):
                                    carrinho = st.session_state.carrinho_compras
                                    ja_no_carrinho = {str(item['produto']).strip().casefold() for item in carrinho}
                                    novos, pendencias = [], []
                                    selecionados = itens_reposicao[itens_reposicao['Fornecedor'].eq(fornecedor_reposicao)]
                                    for indice, linha in selecionados.iterrows():
                                        produto = str(linha['Produto'])
                                        chave_produto = produto.strip().casefold()
                                        if chave_produto in ja_no_carrinho:
                                            pendencias.append(f"{produto}: já está no carrinho.")
                                            continue
                                        custo = float(linha['Preço Compra (R$)'])
                                        if not 0 < custo < float('inf'):
                                            pendencias.append(f"{produto}: informe um custo de compra positivo no cadastro.")
                                            continue
                                        cadastro = df_filtrado_est.loc[indice]
                                        try:
                                            unidade = validar_unidade_entrada(conn, produto, cadastro['unidade'])
                                        except ValueError as erro:
                                            pendencias.append(f"{produto}: {erro}")
                                            continue
                                        novos.append({
                                            'produto': produto, 'grupo': cadastro['grupo'],
                                            'fornecedor': fornecedor_reposicao, 'unidade': unidade,
                                            'quantidade': float(linha['Sugestão de compra']),
                                            'valor_compra': custo, 'valor_venda': float(linha['Preço Venda (R$)']),
                                            'produto_id_reposicao': int(linha['ID']),
                                        })
                                        ja_no_carrinho.add(chave_produto)
                                    carrinho.extend(novos)
                                    if novos:
                                        st.success(f"{len(novos)} item(ns) adicionado(s). Abra Entrada de Estoque (Compras) para revisar e finalizar.")
                                    for pendencia in pendencias:
                                        st.warning(pendencia)
                            if itens_reposicao['Fornecedor'].eq('Sem fornecedor').any():
                                st.caption("Para enviar itens sem fornecedor ao carrinho, vincule um fornecedor no cadastro ou prepare a compra pela tela de entrada.")
                    else:
                        st.info("Nenhum produto dos filtros atuais precisa de reposição pelo mínimo definido.")

                if not df_filtrado_est.empty:
                    st.markdown("---")
                    st.markdown("### 🛠️ Editar ou Excluir Produto do Estoque")
                    
                    df_prods['label_prod'] = df_prods['id'].astype(str) + " - " + df_prods['produto'].astype(str)
                    lista_prods_edit = df_prods.loc[df_filtrado_est.index, 'label_prod'].tolist()
                    
                    prod_selecionado_est = st.selectbox("Selecione o Produto para Gerenciar:", lista_prods_edit, key="select_prod_gerenciar_est")
                    
                    p_row_est = df_prods[df_prods['label_prod'] == prod_selecionado_est].iloc[0]
                    id_prod_atual = int(p_row_est['id'])
                    gerenciar_imagem_produto(p_row_est, "estoque")
                    with st.expander("📊 Histórico de movimentações deste produto"):
                        st.caption("Registros gerados a partir desta atualização. O saldo anterior de produtos existentes não é reconstituído automaticamente.")
                        historico_estoque = pd.read_sql_query('SELECT data,tipo,quantidade,unidade,saldo_antes,saldo_depois,usuario,referencia FROM movimentos_estoque WHERE produto_id=? ORDER BY id DESC', conn, params=(id_prod_atual,))
                        if historico_estoque.empty:
                            st.info("Ainda não há movimentos registrados para este produto nesta versão.")
                        else:
                            st.dataframe(historico_estoque, use_container_width=True, hide_index=True,
                                         column_config={col: st.column_config.NumberColumn(format='%.3f') for col in ['quantidade','saldo_antes','saldo_depois']})
    
        
                    grupos_disponiveis = carregar_coluna("grupos", "grupo") or ["GERAL"]
                    grupo_atual = str(p_row_est.get('grupo', 'GERAL'))
                    indice_grupo = grupos_disponiveis.index(grupo_atual) if grupo_atual in grupos_disponiveis else 0
        
                    fornecedor_atual = texto_filtro_estoque(p_row_est.get('fornecedor'))
                    fornecedores_edicao = sorted({
                        nome for valor in carregar_coluna("fornecedores", "fornecedor")
                        if (nome := texto_filtro_estoque(valor))
                    } | ({fornecedor_atual} if fornecedor_atual else set()), key=str.casefold)
                    opcoes_fornecedor_edicao = [None] + fornecedores_edicao
                    with st.form("form_editar_produto_estoque"):
                        unidade_est_atual = normalizar_unidade_medida(p_row_est.get('unidade'))
                        ed_unidade = st.selectbox("Unidade de medida", UNIDADES_MEDIDA, index=UNIDADES_MEDIDA.index(unidade_est_atual) if unidade_est_atual in UNIDADES_MEDIDA else None, placeholder="Selecione a unidade", key=f"editar_unidade_{id_prod_atual}")
                        st.caption("A quantidade e os preços usam esta unidade. Alterar a unidade não converte o saldo; com saldo existente, mantenha a unidade cadastrada.")
                        col_e1, col_e2, col_e3 = st.columns(3)
                        with col_e1:
                            ed_codigo = st.text_input("Código / Código de Barras", value=str(p_row_est.get('codigo', '') or ''))
                            ed_produto = st.text_input("Nome do Produto", value=str(p_row_est.get('produto', '') or ''))
                        with col_e2:
                            ed_qtd = st.number_input("Quantidade em Estoque", value=float(p_row_est.get('quantidade', 0) or 0), step=0.001, format="%.3f")
                            ed_minimo = st.number_input("Estoque mínimo", min_value=0.0,
                                value=float(p_row_est['minimo_tela']), step=0.001, format="%.3f",
                                key=f"estoque_minimo_{id_prod_atual}",
                                help="Na unidade do produto. Use zero para desativar a reposição sugerida.")
                            ed_pr_compra = st.number_input("Preço de Compra (R$)", value=float(p_row_est.get('valor_compra', 0.0) or 0.0), format="%.2f")
                        with col_e3:
                            ed_pr_venda = st.number_input("Preço de Venda (R$)", value=float(p_row_est.get('valor_venda', 0.0) or 0.0), format="%.2f")
                            ed_grupo = st.selectbox("Grupo", grupos_disponiveis, index=indice_grupo)
                            ed_fornecedor = st.selectbox("Fornecedor", opcoes_fornecedor_edicao,
                                index=opcoes_fornecedor_edicao.index(fornecedor_atual or None),
                                format_func=lambda nome: "Sem fornecedor" if nome is None else nome,
                                key=f"fornecedor_editar_produto_{id_prod_atual}")
        
                        col_btn_est1, col_btn_est2 = st.columns(2)
                        with col_btn_est1:
                            btn_salvar_prod = st.form_submit_button("✏️ Salvar Alterações", type="primary", use_container_width=True)
                        with col_btn_est2:
                            btn_excluir_prod = st.form_submit_button("🗑️ Excluir Produto", use_container_width=True)
        
                        if btn_salvar_prod:
                            try:
                                if not ed_unidade:
                                    raise ValueError('Selecione a unidade de medida.')
                                unidade_bd = conn.execute('SELECT unidade, quantidade FROM produtos WHERE id=?', (id_prod_atual,)).fetchone()
                                if unidade_bd and normalizar_unidade_medida(unidade_bd[0]) and normalizar_unidade_medida(unidade_bd[0]) != ed_unidade and abs(float(unidade_bd[1] or 0)) > 0:
                                    raise ValueError('Não é possível trocar a unidade com saldo em estoque. A mudança não faz conversão de quantidades.')
                                garantir_colunas_produtos(conn)
                                cursor = conn.cursor()
                                cursor.execute('BEGIN IMMEDIATE')
                                saldo_edicao_atual = cursor.execute('SELECT quantidade FROM produtos WHERE id=?', (id_prod_atual,)).fetchone()
                                saldo_edicao_atual = float(saldo_edicao_atual[0] or 0)
                                if abs(saldo_edicao_atual - float(p_row_est.get('quantidade', 0) or 0)) > 0.000000001:
                                    raise ValueError('O estoque mudou desde que esta tela foi aberta. Recarregue antes de salvar.')
                                cursor.execute("""
                                    UPDATE produtos 
                                    SET codigo = ?, produto = ?, quantidade = ?, valor_compra = ?, valor_venda = ?, grupo = ?, unidade = ?, estoque_minimo = ?, fornecedor = ?
                                    WHERE id = ?
                                """, (ed_codigo.strip(), ed_produto.strip().upper(), ed_qtd, ed_pr_compra, ed_pr_venda, ed_grupo, ed_unidade, round(ed_minimo, 3), ed_fornecedor, id_prod_atual))
                                if float(ed_qtd) != saldo_edicao_atual:
                                    registrar_movimento_estoque(conn, id_prod_atual, 'AJUSTE MANUAL', saldo_edicao_atual,
                                                                 ed_qtd, usr_exibicao, 'Edição do estoque')
                                conn.commit()
                                st.success(f"✅ Produto '{ed_produto}' atualizado com sucesso!")
                                st.rerun()
                            except Exception as e:
                                conn.rollback()
                                st.error(f"❌ Erro ao atualizar produto: {e}")
        
                        if btn_excluir_prod:
                            try:
                                cursor = conn.cursor()
                                cursor.execute("DELETE FROM produtos WHERE id = ?", (id_prod_atual,))
                                conn.commit()
                                st.success("🗑️ Produto removido do estoque com sucesso!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Erro ao excluir produto: {e}")

            else:
                st.warning("⚠️ Nenhum produto cadastrado no estoque geral.")
    
        # -------------------------------------------------------------
        # ABA 2: DEPÓSITO / PRODUTOS PARA PROMOÇÃO
        # -------------------------------------------------------------
        with tab_deposito_promo:
            st.markdown("### 🏷️ Enviar Produto para Promoção no PDV")
            st.markdown("Selecione um produto, defina o preço promocional, a quantidade mínima para ativação no PDV e o limite de estoque da promoção.")
            
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS promocoes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        produto_id INTEGER,
                        preco_promo REAL,
                        qtd_minima REAL,
                        qtd_estoque_promo REAL,
                        ativo INTEGER DEFAULT 1
                    )
                """)
                conn.commit()
            except Exception:
                pass
    
            df_prods_promo = carregar_dados("SELECT * FROM produtos")
            
            if df_prods_promo is not None and not df_prods_promo.empty:
                df_prods_promo['label_promo'] = df_prods_promo['id'].astype(str) + " - " + df_prods_promo['produto'].astype(str)
                lista_prods_promo = df_prods_promo['label_promo'].tolist()
                
                prod_selecionado_promo = st.selectbox("Selecione o Produto para Promoção:", lista_prods_promo, key="select_prod_promo_corrigido")
                
                p_row_promo = df_prods_promo[df_prods_promo['label_promo'] == prod_selecionado_promo].iloc[0]
                id_prod_promo = int(p_row_promo['id'])
                qtd_estoque_atual_geral = float(p_row_promo.get('quantidade', 0.0) or 0.0)
                
                col_p1, col_p2, col_p3 = st.columns(3)
                with col_p1:
                    preco_promocional = st.number_input("Preço Promocional (R$)", value=float(p_row_promo.get('valor_venda', 0.0) or 0.0), format="%.2f", key="input_preco_promo_corr")
                with col_p2:
                    qtd_minima_ativacao = st.number_input("Qtd. Mínima p/ Ativar PDV", value=1.0, step=1.0, min_value=1.0, key="input_qtd_min_corr")
                with col_p3:
                    qtd_estoque_promo = st.number_input(
                        "Qtd. Estoque da Promoção", 
                        value=float(max(0.0, qtd_estoque_atual_geral)), 
                        step=1.0, 
                        min_value=0.0, 
                        key="input_qtd_est_promo_corr"
                    )
                
                st.markdown("")
                btn_enviar_pdv = st.button("🚀 Enviar para o PDV (Ativar Promoção)", type="primary", use_container_width=True, key="btn_enviar_promo_corr")
                
                if btn_enviar_pdv:
                    try:
                        cursor = conn.cursor()
                        cursor.execute("SELECT id FROM promocoes WHERE produto_id = ?", (id_prod_promo,))
                        existe_promo = cursor.fetchone()
                        
                        if existe_promo:
                            cursor.execute("""
                                UPDATE promocoes 
                                SET preco_promo = ?, qtd_minima = ?, qtd_estoque_promo = ?, ativo = 1
                                WHERE produto_id = ?
                            """, (preco_promocional, qtd_minima_ativacao, qtd_estoque_promo, id_prod_promo))
                        else:
                            cursor.execute("""
                                INSERT INTO promocoes (produto_id, preco_promo, qtd_minima, qtd_estoque_promo, ativo)
                                VALUES (?, ?, ?, ?, 1)
                            """, (id_prod_promo, preco_promocional, qtd_minima_ativacao, qtd_estoque_promo))
                        
                        conn.commit()
                        st.success(f"✅ Promoção de '{p_row_promo['produto']}' ativada com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Erro ao salvar promoção: {e}")
                
                st.markdown("---")
                st.markdown("### 📋 Promoções Configuradas para o PDV")
                try:
                    df_promos_ativas = carregar_dados("""
                        SELECT 
                            p.id as ID, 
                            pr.produto as Produto, 
                            p.preco_promo as [Preço Promo (R$)], 
                            p.qtd_minima as [Qtd. Mínima PDV],
                            p.qtd_estoque_promo as [Estoque da Promoção]
                        FROM promocoes p 
                        JOIN produtos pr ON p.produto_id = pr.id 
                        WHERE p.ativo = 1
                    """)
                    if df_promos_ativas is not None and not df_promos_ativas.empty:
                        st.dataframe(df_promos_ativas, use_container_width=True)
    
                        st.markdown("---")
                        st.markdown("### 🛠️ Editar ou Excluir Promoção Configurada")
                        
                        df_promos_ativas['label_promo_edit'] = df_promos_ativas['ID'].astype(str) + " - " + df_promos_ativas['Produto'].astype(str)
                        lista_promos_edit = df_promos_ativas['label_promo_edit'].tolist()
                        
                        promo_selecionada_gerir = st.selectbox("Selecione a Promoção para Gerenciar:", lista_promos_edit, key="select_promo_gerenciar_admin")
                        
                        p_row_selecionada = df_promos_ativas[df_promos_ativas['label_promo_edit'] == promo_selecionada_gerir].iloc[0]
                        id_promo_atual = int(p_row_selecionada['ID'])
    
                        cursor = conn.cursor()
                        cursor.execute("SELECT preco_promo, qtd_minima, qtd_estoque_promo FROM promocoes WHERE id = ?", (id_promo_atual,))
                        dados_atuais_promo = cursor.fetchone()
    
                        val_ant_preco = float(dados_atuais_promo[0]) if dados_atuais_promo else 0.0
                        val_ant_min = float(dados_atuais_promo[1]) if dados_atuais_promo else 1.0
                        val_ant_est = float(dados_atuais_promo[2]) if dados_atuais_promo else 0.0
    
                        col_ed1, col_ed2, col_ed3 = st.columns(3)
                        with col_ed1:
                            edit_preco_promo = st.number_input("Novo Preço Promo (R$)", value=val_ant_preco, format="%.2f", key="edit_val_promo")
                        with col_ed2:
                            edit_qtd_min = st.number_input("Nova Qtd. Mínima PDV", value=val_ant_min, step=1.0, min_value=1.0, key="edit_qtd_min_promo")
                        with col_ed3:
                            edit_estoque_promo = st.number_input("Novo Estoque Promo", value=val_ant_est, step=1.0, min_value=0.0, key="edit_est_promo")
    
                        col_btn_p1, col_btn_p2 = st.columns(2)
                        with col_btn_p1:
                            if st.button("✏️ Salvar Alterações da Promoção", type="primary", use_container_width=True, key="btn_salvar_alt_promo"):
                                try:
                                    cursor.execute("""
                                        UPDATE promocoes 
                                        SET preco_promo = ?, qtd_minima = ?, qtd_estoque_promo = ?
                                        WHERE id = ?
                                    """, (edit_preco_promo, edit_qtd_min, edit_estoque_promo, id_promo_atual))
                                    conn.commit()
                                    st.success("✅ Promoção atualizada com sucesso!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Erro ao atualizar promoção: {e}")
    
                        with col_btn_p2:
                            if st.button("🗑️ Excluir / Desativar Promoção", use_container_width=True, key="btn_excluir_promo_pdv"):
                                try:
                                    cursor.execute("UPDATE promocoes SET ativo = 0 WHERE id = ?", (id_promo_atual,))
                                    conn.commit()
                                    st.success("🗑️ Promoção removida/desativada com sucesso!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Erro ao excluir promoção: {e}")
                    else:
                        st.info("ℹ️ Nenhuma promoção ativa configurada no momento.")
                except Exception:
                    st.info("ℹ️ Nenhuma promoção ativa encontrada.")
            else:
                st.warning("⚠️ Cadastre produtos no estoque geral primeiro.")
    
        # -------------------------------------------------------------
        # ABA 3: PRODUTOS COMPRADOS (Com Filtro e Botão de Limpar)
        # -------------------------------------------------------------
        with tab_comprados:
            st.markdown("### 📥 Histórico de Produtos Comprados")
            
            df_compras = carregar_dados("SELECT * FROM compras")
            if df_compras is not None and not df_compras.empty:
                def texto_historico_compra(valor):
                    texto = '' if pd.isna(valor) else str(valor).strip()
                    return texto if texto.lower() not in {'','none','nan','null'} else 'Não informado'
                df_compras['fornecedor_tela'] = df_compras['fornecedor'].apply(texto_historico_compra)
                df_compras['produto_tela'] = df_compras['produto'].apply(texto_historico_compra)
                datas_compras_hist = pd.to_datetime(df_compras['data'], errors='coerce')
                with st.container(border=True):
                    datas_compras_col = st.columns(2)
                    dt_inicio_compra = datas_compras_col[0].date_input("Data Inicial (Compra)", key="dt_ini_compra_filtro")
                    dt_fim_compra = datas_compras_col[1].date_input("Data Final (Compra)", key="dt_fim_compra_filtro")
                    filtros_compras_col = st.columns(2)
                    fornecedor_selecionado = filtros_compras_col[0].selectbox("Fornecedor", ['Todos'] + sorted(df_compras['fornecedor_tela'].unique().tolist()), key="filtro_forn_compras_aba")
                    produto_compra_hist = filtros_compras_col[1].selectbox("Produto", ['Todos'] + sorted(df_compras['produto_tela'].unique().tolist()), key="filtro_prod_compras_aba")
                mascara_compras_hist = datas_compras_hist.dt.date.between(dt_inicio_compra, dt_fim_compra)
                if dt_inicio_compra > dt_fim_compra:
                    st.warning("A data inicial deve ser anterior ou igual à data final.")
                    mascara_compras_hist &= False
                if fornecedor_selecionado != 'Todos':
                    mascara_compras_hist &= df_compras['fornecedor_tela'] == fornecedor_selecionado
                if produto_compra_hist != 'Todos':
                    mascara_compras_hist &= df_compras['produto_tela'] == produto_compra_hist
                df_comp_filtrado = df_compras.loc[mascara_compras_hist].copy()
                quantidade_hist_compra = pd.to_numeric(df_comp_filtrado['quantidade'], errors='coerce')
                custo_hist_compra = pd.to_numeric(df_comp_filtrado.get('preco_compra',pd.Series(index=df_comp_filtrado.index,dtype=float)),errors='coerce')
                custo_hist_compra = custo_hist_compra.fillna(pd.to_numeric(df_comp_filtrado.get('valor_compra',pd.Series(index=df_comp_filtrado.index,dtype=float)),errors='coerce'))
                venda_hist_compra = pd.to_numeric(df_comp_filtrado.get('preco_venda',pd.Series(index=df_comp_filtrado.index,dtype=float)),errors='coerce')
                venda_hist_compra = venda_hist_compra.fillna(pd.to_numeric(df_comp_filtrado.get('valor_venda',pd.Series(index=df_comp_filtrado.index,dtype=float)),errors='coerce'))
                total_hist_compra = quantidade_hist_compra * custo_hist_compra
                def moeda_compras_hist(valor):
                    return 'R$ ' + f'{float(valor):,.2f}'.replace(',','_').replace('.',',').replace('_','.')
                resumo_compras_hist = st.columns(3)
                resumo_compras_hist[0].metric("💰 Total das compras", moeda_compras_hist(total_hist_compra.sum()))
                resumo_compras_hist[1].metric("📦 Linhas de produtos", len(df_comp_filtrado))
                resumo_compras_hist[2].metric("🚚 Fornecedores informados", df_comp_filtrado.loc[df_comp_filtrado['fornecedor_tela'] != 'Não informado','fornecedor_tela'].nunique())
                st.caption("Totais dos filtros selecionados. O total é quantidade × custo unitário registrado na compra; não representa pagamento ou saída do caixa. Quantidades de unidades diferentes não são somadas.")
                if total_hist_compra.isna().any():
                    st.warning(f"{int(total_hist_compra.isna().sum())} registro(s) sem quantidade ou custo válido não entram no total. O resumo está parcial.")
                if df_comp_filtrado.empty:
                    st.info("Nenhuma compra encontrada com esses filtros.")
                else:
                    tabela_compras_hist = pd.DataFrame(index=df_comp_filtrado.index)
                    tabela_compras_hist['ID'] = df_comp_filtrado['id']
                    tabela_compras_hist['Data'] = datas_compras_hist.loc[df_comp_filtrado.index].dt.strftime('%d/%m/%Y %H:%M:%S').fillna('Não informado')
                    tabela_compras_hist['Produto'] = df_comp_filtrado['produto_tela']
                    tabela_compras_hist['Fornecedor'] = df_comp_filtrado['fornecedor_tela']
                    tabela_compras_hist['Quantidade'] = quantidade_hist_compra
                    tabela_compras_hist['Unidade'] = df_comp_filtrado.get('unidade',pd.Series('',index=df_comp_filtrado.index)).apply(rotulo_unidade_medida)
                    tabela_compras_hist['Custo unitário (R$)'] = custo_hist_compra
                    tabela_compras_hist['Preço de venda (R$)'] = venda_hist_compra
                    tabela_compras_hist['Total compra (R$)'] = total_hist_compra
                    if 'grupo' in df_comp_filtrado:
                        tabela_compras_hist['Grupo'] = df_comp_filtrado['grupo'].apply(texto_historico_compra)
                    st.dataframe(tabela_compras_hist, hide_index=True, use_container_width=True,
                        column_config={'Quantidade':st.column_config.NumberColumn(format='%.3f'),
                            **{col:st.column_config.NumberColumn(format='%.2f') for col in ['Custo unitário (R$)','Preço de venda (R$)','Total compra (R$)']}})
                    totais_fornecedor = pd.DataFrame({
                        'Fornecedor': df_comp_filtrado['fornecedor_tela'],
                        'Total (R$)': total_hist_compra,
                    }).groupby('Fornecedor', as_index=False)['Total (R$)'].sum(min_count=1)
                    with st.expander("🚚 Totais por fornecedor"):
                        st.dataframe(totais_fornecedor, hide_index=True, use_container_width=True,
                            column_config={'Total (R$)': st.column_config.NumberColumn(format='%.2f')})
                    st.download_button("📄 Baixar relatório de compras (PDF)",
                        data=gerar_pdf_compras_periodo(nome_empresa_header,
                            f"{dt_inicio_compra:%d/%m/%Y} a {dt_fim_compra:%d/%m/%Y}",
                            fornecedor_selecionado, produto_compra_hist, tabela_compras_hist, totais_fornecedor),
                        file_name=f"compras_{dt_inicio_compra:%Y-%m-%d}_a_{dt_fim_compra:%Y-%m-%d}.pdf",
                        mime="application/pdf", key="baixar_relatorio_compras_periodo")

                st.markdown("---")
                if st.button("🗑️ Limpar Histórico de Compras", key="btn_limpar_hist_compras"):
                    try:
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM compras")
                        conn.commit()
                        st.success("✅ Histórico de compras limpo com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Erro ao limpar histórico de compras: {e}")
            else:
                st.info("ℹ️ Nenhum registo de compras encontrado na base de dados.")    
        # -------------------------------------------------------------
        # ABA 4: PRODUTOS VENDIDOS
        # -------------------------------------------------------------
        with tab_vendidos:
            st.markdown("### 📤 Histórico de Produtos Vendidos")

            col_fv1, col_fv2 = st.columns(2)

            with col_fv1:
                dt_inicio_venda = st.date_input(
                    "Data Inicial (Venda)",
                    key="dt_ini_venda_filtro"
                )

            with col_fv2:
                dt_fim_venda = st.date_input(
                    "Data Final (Venda)",
                    key="dt_fim_venda_filtro"
                )

            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
                tabelas_existentes = [
                    row[0] for row in cursor.fetchall()
                ]

                tabela_vendas_alvo = "vendas"

                df_vendas_hist = carregar_dados(
                    f"SELECT * FROM {tabela_vendas_alvo}"
                )

            except Exception:
                df_vendas_hist = pd.DataFrame()

            if df_vendas_hist is not None and not df_vendas_hist.empty:
                def categoria_pagamento_historico(valor):
                    texto = str(valor or '').strip()
                    for categoria in ['Cartão Crédito','Cartão Débito','Parcelado','Dinheiro','Fiado','Pix']:
                        if texto.casefold().startswith(categoria.casefold()):
                            return categoria
                    return texto or 'Não informado'

                datas_hist = pd.to_datetime(df_vendas_hist['data'], errors='coerce')
                df_vendas_hist['categoria_pagamento'] = df_vendas_hist['forma_pagamento'].apply(categoria_pagamento_historico)
                df_vendas_hist['estornada_tela'] = df_vendas_hist.get('status',pd.Series('',index=df_vendas_hist.index)).fillna('').astype(str).str.casefold().eq('estornada')
                with st.container(border=True):
                    filtros_vendas = st.columns(2)
                    cliente_hist = filtros_vendas[0].selectbox("Cliente", ['Todos'] + sorted(df_vendas_hist['cliente'].fillna('').astype(str).unique().tolist()), key="hist_cliente_venda")
                    produto_hist = filtros_vendas[1].selectbox("Produto", ['Todos'] + sorted(df_vendas_hist['produto'].fillna('').astype(str).unique().tolist()), key="hist_produto_venda")
                    filtros_vendas2 = st.columns(2)
                    pagamento_hist = filtros_vendas2[0].selectbox("Forma de pagamento", ['Todas'] + sorted(df_vendas_hist['categoria_pagamento'].unique().tolist()), key="hist_pagamento_venda")
                    situacao_hist = filtros_vendas2[1].selectbox("Situação", ['Todas', 'Vendas válidas', 'Estornadas'], key="hist_situacao_venda")
                mascara_hist = datas_hist.dt.date.between(dt_inicio_venda, dt_fim_venda)
                if dt_inicio_venda > dt_fim_venda:
                    st.warning("A data inicial deve ser anterior ou igual à data final.")
                    mascara_hist &= False
                if cliente_hist != 'Todos':
                    mascara_hist &= df_vendas_hist['cliente'].fillna('').astype(str) == cliente_hist
                if produto_hist != 'Todos':
                    mascara_hist &= df_vendas_hist['produto'].fillna('').astype(str) == produto_hist
                if pagamento_hist != 'Todas':
                    mascara_hist &= df_vendas_hist['categoria_pagamento'] == pagamento_hist
                if situacao_hist == 'Vendas válidas':
                    mascara_hist &= ~df_vendas_hist['estornada_tela']
                elif situacao_hist == 'Estornadas':
                    mascara_hist &= df_vendas_hist['estornada_tela']
                vendas_filtradas_hist = df_vendas_hist.loc[mascara_hist].copy()
                valores_hist = pd.to_numeric(vendas_filtradas_hist['valor_total'], errors='coerce').fillna(0)
                estornos_hist = vendas_filtradas_hist['estornada_tela']
                total_valido_hist = valores_hist[~estornos_hist].sum()
                total_estornado_hist = valores_hist[estornos_hist].sum()
                resumo_vendas_hist = st.columns(3)
                resumo_vendas_hist[0].metric("✅ Vendas válidas", moeda_historico_venda(total_valido_hist))
                resumo_vendas_hist[1].metric("↩️ Estornadas · fora do total válido", moeda_historico_venda(total_estornado_hist))
                resumo_vendas_hist[2].metric("📦 Linhas de produtos", len(vendas_filtradas_hist))
                st.caption("Totais dos filtros selecionados, somando o valor de cada linha de produto. Venda a prazo representa valor vendido; o recebimento é conferido no caixa e em Contas a Receber.")
                if vendas_filtradas_hist.empty:
                    st.info("Nenhuma venda encontrada com esses filtros.")
                else:
                    resumo_pagamentos_hist = pd.DataFrame({
                        'Forma de pagamento': vendas_filtradas_hist['categoria_pagamento'],
                        'Vendas válidas': valores_hist.where(~estornos_hist, 0),
                        'Estornos': valores_hist.where(estornos_hist, 0),
                    }).groupby('Forma de pagamento', as_index=False).sum()
                    with st.expander("Resumo por forma de pagamento"):
                        st.dataframe(resumo_pagamentos_hist, hide_index=True, use_container_width=True,
                            column_config={col: st.column_config.NumberColumn(format="R$ %.2f")
                                           for col in ['Vendas válidas', 'Estornos']})
                    filtros_pdf_vendas = {
                        'Período': f"{dt_inicio_venda:%d/%m/%Y} a {dt_fim_venda:%d/%m/%Y}",
                        'Cliente': cliente_hist, 'Produto': produto_hist,
                        'Pagamento': pagamento_hist, 'Situação': situacao_hist,
                    }
                    st.download_button("📄 Baixar relatório de vendas (PDF)",
                        data=gerar_pdf_vendas_periodo(nome_empresa_header, filtros_pdf_vendas,
                            resumo_pagamentos_hist, total_valido_hist, total_estornado_hist, len(vendas_filtradas_hist)),
                        file_name=f"vendas_{dt_inicio_venda:%Y-%m-%d}_a_{dt_fim_venda:%Y-%m-%d}.pdf",
                        mime="application/pdf", key="baixar_relatorio_vendas_periodo")
                    colunas_hist = [col for col in ['id','cliente','produto','quantidade','unidade','valor_venda','valor_total','forma_pagamento','data','status','vendedor','estornado_em','estornado_por','autorizado_por','motivo_estorno'] if col in vendas_filtradas_hist.columns]
                    tabela_hist = vendas_filtradas_hist[colunas_hist].copy()
                    nomes_hist = {'id':'ID','cliente':'Cliente','produto':'Produto','quantidade':'Quantidade','unidade':'Unidade',
                        'valor_venda':'Preço unitário (R$)','valor_total':'Total (R$)','forma_pagamento':'Pagamento','data':'Data',
                        'status':'Status','vendedor':'Vendedor','estornado_em':'Estornado em','estornado_por':'Estornado por',
                        'autorizado_por':'Autorizado por','motivo_estorno':'Motivo do estorno'}
                    tabela_hist = tabela_hist.rename(columns=nomes_hist)
                    for coluna_hist in ['Quantidade','Preço unitário (R$)','Total (R$)']:
                        if coluna_hist in tabela_hist:
                            tabela_hist[coluna_hist] = pd.to_numeric(tabela_hist[coluna_hist], errors='coerce')
                    if 'Unidade' in tabela_hist:
                        tabela_hist['Unidade'] = tabela_hist['Unidade'].apply(rotulo_unidade_medida)
                    tabela_hist['Data'] = datas_hist.loc[tabela_hist.index].dt.strftime('%d/%m/%Y %H:%M:%S').fillna('Não informado')
                    def destacar_estorno(linha):
                        return ['background-color:#742936;color:#ffffff;font-weight:bold' if str(linha.get('Status','')).casefold() == 'estornada' else '' for _ in linha]
                    st.dataframe(tabela_hist.style.apply(destacar_estorno,axis=1), hide_index=True, use_container_width=True,
                        column_config={'Quantidade':st.column_config.NumberColumn(format='%.3f'),
                                       'Preço unitário (R$)':st.column_config.NumberColumn(format='%.2f'),
                                       'Total (R$)':st.column_config.NumberColumn(format='%.2f')})
                st.caption("As vendas estornadas permanecem no histórico com status, motivo e responsáveis.")

                # -------------------------------------------------
                # ESTORNO DE VENDA — estoque + caixa, sem afetar outras vendas
                st.markdown("---")
                st.markdown("### 🔄 Estornar Venda e Atualizar Caixa")
                if st.session_state.get('aviso_estorno'):
                    st.success(st.session_state.pop('aviso_estorno'))

                with st.form(key="form_estorno_venda_final"):
                    id_venda_estorno = st.number_input(
                        "Digite o ID da primeira linha da venda (coluna ID):",
                        min_value=1, step=1, value=1
                    )
                    motivo_estorno = st.text_area("Motivo do estorno", key="motivo_estorno_pdv")
                    campos_autorizacao('autorizar_estorno_pdv')
                    submitted = st.form_submit_button(
                        "❌ Confirmar Estorno da Venda", type="primary",
                        on_click=capturar_autorizacao, args=('autorizar_estorno_pdv',)
                    )

                if submitted:
                    login_admin, senha_admin = consumir_autorizacao('autorizar_estorno_pdv')
                    try:
                        principal = estornar_venda_auditada(conn, id_venda_estorno, 'PDV', motivo_estorno,
                                                            login_admin, senha_admin, usr_exibicao)
                    except Exception as erro:
                        st.error(f"Não foi possível estornar: {erro}")
                    else:
                        st.session_state['aviso_estorno'] = f"Venda #{principal} ESTORNADA. Motivo e responsáveis registrados no histórico."
                        st.cache_data.clear()
                        st.rerun()
                    finally:
                        senha_admin = ''

            else:
                st.info(
                    "ℹ️ Nenhum registro de vendas encontrado."
                )
    # -------------------------------------------------------------
    # 11. CONFIGURAÇÕES
    # -------------------------------------------------------------
    elif menu_admin == "🏢 Configurações da Empresa":
        st.subheader("🏢 Configurações e Dados da Empresa")

        st.markdown("### 🔑 Ativação e Limite de Dispositivos")

        doc_atual = str(reg_emp.get('cnpj', doc_empresa_padrao))
        doc_limpo_atual = normalizar_documento(doc_atual)
        total_ativados = contar_dispositivos_ativos(doc_atual)
        limite_permitido = max(1, min(50, int(reg_emp.get('limite_dispositivos', 1) or 1)))
        st.info(f"📊 **Licença desta empresa:** {total_ativados} de {limite_permitido} aparelho(s) ativado(s).")

        if dispositivo_esta_ativado:
            dias_val = st.session_state.get('dias_licenca', 30)
            if licenca_expira_em:
                vencimento = datetime.fromisoformat(licenca_expira_em).astimezone(dt.timezone(timedelta(hours=-3)))
                st.success(f"✅ Dispositivo ativado até {vencimento:%d/%m/%Y às %H:%M} (horário de Brasília).")
            else:
                st.success(f"✅ Ativação anterior sem data de vencimento registrada. Plano informado: {dias_val} dias.")
            st.caption("Você pode inserir uma nova chave para renovar. O identificador deste aparelho será mantido.")
        elif licenca_vencida:
            st.warning("⚠️ A licença deste aparelho venceu.")
        else:
            st.warning("⚠️ Este aparelho ainda não está ativado.")

        st.info(f"Empresa atual (CNPJ/CPF): `{doc_atual}`")
        chave_digitada = st.text_input("Chave de Ativação / Renovação:", key="input_chave_ativacao_config")

        alterar_limite = dispositivo_registrado and st.checkbox(
            "Aplicar o limite de dispositivos da chave", key="alterar_limite_renovacao"
        )
        if st.button("🔓 Ativar / Renovar Licença", type="primary", key="btn_ativar_dispositivo_config"):
            chave_limpa = str(chave_digitada).strip().upper()
            if empresa_doc:
                try:
                    aplicar_chave_unica(conn, empresa_doc, device_id, chave_limpa, alterar_limite, empresa_config)
                except ValueError as erro:
                    st.error(str(erro))
                else:
                    st.rerun()
            else:
                sucesso = False
                dias_validade = 0
                limite_extraido = 0
                for sufixo, dias in [("TESTE", 7), ("MENSAL", 30), ("ANUAL", 365)]:
                    for lim_test in range(1, 51):
                        hash_hex = hash_chave_licenca(doc_limpo_atual, sufixo, lim_test)
                        chave_esperada = f"CRM-{sufixo}-{lim_test}D-{hash_hex[:4]}-{hash_hex[4:8]}"
                        if chave_limpa == chave_esperada:
                            sucesso = True
                            dias_validade = dias
                            limite_extraido = lim_test
                            break
                    if sucesso:
                        break

                if not sucesso:
                    st.error("❌ Chave inválida para o CNPJ/CPF desta empresa ou limite incorreto.")
                else:
                    ativos_antes = contar_dispositivos_ativos(doc_atual)
                    ja_ativado = dispositivo_registrado
                    if ja_ativado and not alterar_limite:
                        limite_extraido = limite_permitido
                    if not ja_ativado and ativos_antes >= limite_extraido:
                        st.error(f"❌ Limite atingido: já existem {ativos_antes} aparelho(s) ativado(s) para esta empresa. A chave permite {limite_extraido}.")
                    else:
                        cursor = conn.cursor()
                        cursor.execute("""
                            UPDATE empresas_dispositivos
                            SET limite_dispositivos = ?
                            WHERE REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(cnpj,''),'.',''),'/',''),'-',''),' ','') = ?
                        """, (limite_extraido, doc_limpo_atual))
                        inicio = datetime.now(dt.timezone.utc)
                        novo_vencimento = (inicio + timedelta(days=dias_validade)).isoformat(timespec="seconds")
                        cursor.execute("""
                            UPDATE empresas_dispositivos
                            SET ativado = 1, dias_licenca = ?, limite_dispositivos = ?, licenca_expira_em = ?
                            WHERE device_id = ?
                        """, (dias_validade, limite_extraido, novo_vencimento, device_id))
                        conn.commit()
                        st.session_state['dispositivo_ativado'] = True
                        st.session_state['dias_licenca'] = dias_validade
                        st.session_state['limite_dispositivos'] = limite_extraido
                        st.success(f"🎉 Licença ativada/renovada! Validade: {dias_validade} dias. Limite compartilhado: {limite_extraido} aparelho(s).")
                        st.rerun()

        st.markdown("---")
        with st.form("form_cfg_emp"):
            st.markdown("### 📝 Dados Gerais e Limites da Empresa")
            nome_emp = st.text_input("Razão Social / Nome Fantasia", value=str(reg_emp.get('nome_empresa', nome_empresa_padrao)))
            cnpj_emp = st.text_input("CNPJ ou CPF", value=empresa_doc or str(reg_emp.get('cnpj', doc_empresa_padrao)), disabled=bool(empresa_doc))
            inscr_est_emp = st.text_input("INSCR. EST", value=str(reg_emp.get('inscr_est', inscricao_empresa_padrao)))
            tel_emp = st.text_input("Telefone de Contato", value=str(reg_emp.get('fone', fone_empresa_padrao)))
            end_emp = st.text_input("Endereço Completo", value=str(reg_emp.get('endereco', endereco_empresa_padrao)))
            lim_disp = st.number_input("💻 Limite Máximo de Dispositivos Permitidos", min_value=1, max_value=50, value=int(reg_emp.get('limite_dispositivos', 1)))
            
            if st.form_submit_button("💾 Salvar Configurações", type="primary"):
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE empresas_dispositivos
                    SET nome_empresa = ?, cnpj = ?, fone = ?, endereco = ?,
                        limite_dispositivos = ?
                    WHERE device_id = ?
                """, (nome_emp, cnpj_emp, tel_emp, end_emp, int(lim_disp), device_id))
                # Mantém o limite atualizado para todos os aparelhos da mesma empresa.
                cursor.execute("""
                    UPDATE empresas_dispositivos SET limite_dispositivos = ?
                    WHERE REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(cnpj,''),'.',''),'/',''),'-',''),' ','') = ?
                """, (int(lim_disp), normalizar_documento(cnpj_emp)))
                conn.commit()
                st.session_state['limite_dispositivos'] = lim_disp
                st.success("✅ Configurações e limites salvos com sucesso!")
                st.rerun()

        # --- GESTÃO DE CHAVES PIX MÚLTIPLAS NAS CONFIGURAÇÕES ---
        st.markdown("---")
        st.markdown("### 💳 Gestão de Chaves Pix")
        
        with st.form("form_cad_chave_pix"):
            col_cp1, col_cp2 = st.columns(2)
            with col_cp1:
                tipo_chave = st.selectbox("Tipo de Chave", ["CNPJ", "CPF", "Celular", "E-mail", "Chave Aleatória"])
                valor_chave = st.text_input("Valor da Chave (ex: seu e-mail, celular ou CNPJ)")
            with col_cp2:
                favorecido_chave = st.text_input("Nome do Favorecido", value=nome_empresa_header)
                cidade_chave = st.text_input("Cidade", value="SAO LUIS")
            
            if st.form_submit_button("➕ Cadastrar Nova Chave Pix", type="primary"):
                if valor_chave.strip():
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO chaves_pix (tipo, chave, favorecido, cidade)
                        VALUES (?, ?, ?, ?)
                    """, (tipo_chave, valor_chave.strip(), favorecido_chave.strip(), cidade_chave.strip()))
                    conn.commit()
                    st.success("✅ Chave Pix cadastrada com sucesso!")
                    st.rerun()
                else:
                    st.error("Preencha o valor da chave Pix.")

        df_chaves_cadastradas = carregar_dados("SELECT * FROM chaves_pix")
        if not df_chaves_cadastradas.empty:
            st.markdown("#### 📋 Chaves Pix Já Cadastradas")
            st.dataframe(df_chaves_cadastradas, use_container_width=True)
            
            id_para_excluir = st.number_input("ID da Chave para Excluir (opcional):", min_value=0, step=1)
            if st.button("🗑️ Excluir Chave Selecionada"):
                if id_para_excluir > 0:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM chaves_pix WHERE id = ?", (int(id_para_excluir),))
                    conn.commit()
                    st.success(f"Chave ID {id_para_excluir} excluída com sucesso!")
                    st.rerun()
# --- PREPARACAO PARA EMISSAO DE NFC-e ---
        st.markdown("---")
        st.markdown("### 🧾 Preparação para emissão de NFC-e (modelo 65)")
        st.info(
            "Esta etapa salva somente os parâmetros básicos da NFC-e. "
            "Ela ainda não transmite vendas à SEFAZ e não substitui o cupom atual. "
            "A emissão real será ativada depois da validação do CSC, certificado A1, "
            "credenciamento da empresa e dados fiscais dos produtos."
        )

        df_nfce_cfg = carregar_dados("SELECT * FROM config_nfce WHERE id = 1")
        cfg_nfce = df_nfce_cfg.iloc[0].to_dict() if not df_nfce_cfg.empty else {}
        with st.form("form_config_nfce"):
            col_nfce1, col_nfce2 = st.columns(2)
            with col_nfce1:
                uf_nfce = st.selectbox("Estado da emissão", ["MA"], index=0, disabled=True)
                ambiente_opcoes = ["Homologacao", "Producao"]
                ambiente_atual = str(cfg_nfce.get("ambiente", "Homologacao"))
                ambiente_nfce = st.selectbox(
                    "Ambiente SEFAZ",
                    ambiente_opcoes,
                    index=ambiente_opcoes.index(ambiente_atual) if ambiente_atual in ambiente_opcoes else 0,
                    format_func=lambda x: "Homologação (testes)" if x == "Homologacao" else "Produção (emissão oficial)"
                )
            with col_nfce2:
                serie_nfce = st.text_input("Série da NFC-e", value=str(cfg_nfce.get("serie", "1")))
                numero_nfce = st.number_input(
                    "Próximo número da NFC-e", min_value=1, step=1,
                    value=max(1, int(cfg_nfce.get("proximo_numero", 1) or 1))
                )
            st.caption("Modelo fiscal: 65 (NFC-e). O ambiente de produção só deverá ser usado após autorização e testes.")
            if st.form_submit_button("💾 Salvar parâmetros da NFC-e", type="primary"):
                if not serie_nfce.strip():
                    st.error("Informe a série da NFC-e.")
                else:
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE config_nfce
                        SET uf = ?, ambiente = ?, serie = ?, proximo_numero = ?,
                            modelo = '65', atualizado_em = ?
                        WHERE id = 1
                    """, (uf_nfce, ambiente_nfce, serie_nfce.strip(), int(numero_nfce), datetime.now().isoformat(timespec="seconds")))
                    conn.commit()
                    st.success("Parâmetros básicos da NFC-e salvos. A emissão ainda depende das credenciais e validações fiscais.")
                    st.rerun()

        st.markdown("#### 🔐 Credenciais necessárias para ativar a emissão")
        st.markdown(
            "Quando estiver com o contador, serão necessários: **CSC (ID e token)**, "
            "certificado **A1 (.pfx/.p12) e senha**, credenciamento da NFC-e na SEFAZ-MA "
            "e os dados tributários dos produtos. As credenciais não serão gravadas "
            "nesta tabela nem colocadas diretamente no código; serão configuradas "
            "nos Secrets do Streamlit Cloud."
        )
        st.warning("Ainda não emite NFC-e oficial. Não informe dados fictícios nem mude para Produção antes da liberação da SEFAZ e da conferência do contador.")
          
