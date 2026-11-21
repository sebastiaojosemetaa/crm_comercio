"""Identidade estável e dados cadastrais compartilhados, separados das bases e licenças."""
from contextlib import closing
from pathlib import Path
from datetime import datetime, timezone
import json
import re
import sqlite3
import uuid


def normalizar_documento(valor):
    return re.sub(r'[^0-9]', '', str(valor or ''))


def preparar_estrutura(c):
    c.execute('CREATE SCHEMA IF NOT EXISTS crm_producao')
    c.execute('''CREATE TABLE IF NOT EXISTS crm_producao.identidades_empresas (
        chave_interna TEXT PRIMARY KEY,id_interno TEXT UNIQUE NOT NULL,
        documento TEXT UNIQUE NOT NULL,nome_fantasia TEXT NOT NULL,razao_social TEXT NOT NULL,
        versao BIGINT NOT NULL DEFAULT 1)''')
    c.execute('''CREATE TABLE IF NOT EXISTS crm_producao.documentos_empresas (
        documento TEXT PRIMARY KEY,chave_interna TEXT NOT NULL
        REFERENCES crm_producao.identidades_empresas(chave_interna))''')
    c.execute('''CREATE TABLE IF NOT EXISTS crm_producao.historico_identidade (
        operacao TEXT PRIMARY KEY,chave_interna TEXT NOT NULL,versao_anterior BIGINT NOT NULL,
        dados_anteriores TEXT NOT NULL,dados_novos TEXT NOT NULL,
        usuario TEXT NOT NULL,criado_em TEXT NOT NULL)''')


def _perfil(linha):
    return dict(zip(('chave_interna','id_interno','documento','nome_fantasia','razao_social','versao'),linha))


def _todos(c):
    perfis={r[0]:_perfil(r) for r in c.execute('SELECT chave_interna,id_interno,documento,nome_fantasia,razao_social,versao '
                                            'FROM crm_producao.identidades_empresas').fetchall()}
    aliases=dict(c.execute('SELECT documento,chave_interna FROM crm_producao.documentos_empresas').fetchall())
    return perfis,aliases


def _inicializar(c):
    preparar_estrutura(c)
    c.execute('LOCK TABLE crm_producao.identidades_empresas, crm_producao.documentos_empresas IN SHARE ROW EXCLUSIVE MODE')
    if not c.execute("SELECT to_regclass('crm_producao.catalogo_empresas')").fetchone()[0]:return
    empresas=c.execute('SELECT documento,nome FROM crm_producao.catalogo_empresas ORDER BY documento').fetchall()
    migradas={}
    if c.execute("SELECT to_regclass('crm_producao.migracoes_documentos')").fetchone()[0]:
        migradas=dict(c.execute('SELECT origem,destino FROM crm_producao.migracoes_documentos').fetchall())
    for chave,nome in empresas:
        if chave in migradas:continue
        if c.execute('SELECT 1 FROM crm_producao.identidades_empresas WHERE chave_interna=%s',(chave,)).fetchone():continue
        ocupado=c.execute('SELECT chave_interna FROM crm_producao.documentos_empresas WHERE documento=%s',(chave,)).fetchone()
        if ocupado and ocupado[0]!=chave:
            raise ValueError('Um documento do catálogo já está reservado para outra empresa. Confira o cadastro antes de continuar.')
        c.execute('INSERT INTO crm_producao.identidades_empresas '
                  '(chave_interna,id_interno,documento,nome_fantasia,razao_social,versao) VALUES(%s,%s,%s,%s,%s,1)',
                  (chave,str(uuid.uuid4()),chave,str(nome).strip(),''))
        c.execute('INSERT INTO crm_producao.documentos_empresas VALUES(%s,%s) ON CONFLICT(documento) DO NOTHING',(chave,chave))
    for origem,destino in migradas.items():
        if c.execute('SELECT 1 FROM crm_producao.identidades_empresas WHERE chave_interna=%s',(destino,)).fetchone():
            existente=c.execute('SELECT chave_interna FROM crm_producao.documentos_empresas WHERE documento=%s',(origem,)).fetchone()
            if existente and existente[0]!=destino:raise ValueError('Há uma identidade anterior que precisa ser conciliada com a migração.')
            c.execute('INSERT INTO crm_producao.documentos_empresas VALUES(%s,%s) ON CONFLICT(documento) DO NOTHING',(origem,destino))


def ler_cache(caminho):
    caminho=Path(caminho)
    if not caminho.is_file():return {},{}
    with closing(sqlite3.connect(caminho.resolve().as_uri()+'?mode=ro',uri=True)) as c:
        tabelas={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'identidades_compartilhadas','documentos_compartilhados'}<=tabelas:return {},{}
        return ({chave:json.loads(dados) for chave,dados in c.execute('SELECT chave_interna,dados FROM identidades_compartilhadas')},
                dict(c.execute('SELECT documento,chave_interna FROM documentos_compartilhados')))


def gravar_cache(caminho,perfis,aliases):
    caminho=Path(caminho);caminho.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(caminho,timeout=10)) as c,c:
        c.execute('CREATE TABLE IF NOT EXISTS identidades_compartilhadas(chave_interna TEXT PRIMARY KEY,dados TEXT NOT NULL)')
        c.execute('CREATE TABLE IF NOT EXISTS documentos_compartilhados(documento TEXT PRIMARY KEY,chave_interna TEXT NOT NULL)')
        c.execute('DELETE FROM identidades_compartilhadas');c.execute('DELETE FROM documentos_compartilhados')
        c.executemany('INSERT INTO identidades_compartilhadas VALUES(?,?)',
                      [(k,json.dumps(v,ensure_ascii=False)) for k,v in perfis.items()])
        c.executemany('INSERT INTO documentos_compartilhados VALUES(?,?)',list(aliases.items()))


def atualizar_cadastros(conectar,caminho_cache):
    with conectar() as c:
        _inicializar(c)
        perfis,aliases=_todos(c)
    gravar_cache(caminho_cache,perfis,aliases)
    return perfis,aliases


def _editar(conectar,chave,versao,alteracoes,usuario,operacao):
    if not usuario or not operacao:raise ValueError('Identifique o administrador e a operação.')
    with conectar() as c:
        _inicializar(c)
        anterior=c.execute('SELECT chave_interna,id_interno,documento,nome_fantasia,razao_social,versao '
                           'FROM crm_producao.identidades_empresas WHERE chave_interna=%s FOR UPDATE',(chave,)).fetchone()
        if not anterior:raise ValueError('Empresa ainda não compartilhada. Atualize a lista antes de editar.')
        anterior=_perfil(anterior)
        repetida=c.execute('SELECT chave_interna,dados_novos FROM crm_producao.historico_identidade WHERE operacao=%s',(operacao,)).fetchone()
        if repetida:
            salvo=json.loads(repetida[1])
            if repetida[0]!=chave or any(salvo.get(k)!=v for k,v in alteracoes.items()):
                raise ValueError('Esta operação já foi utilizada com outros dados.')
            return anterior
        if anterior['versao']!=versao:
            raise ValueError('O cadastro foi atualizado em outro aparelho. Recarregue e confira os dados antes de salvar.')
        novo=dict(anterior);novo.update(alteracoes);novo['versao']+=1
        if novo['documento']!=anterior['documento']:
            reservado=c.execute('SELECT chave_interna FROM crm_producao.documentos_empresas WHERE documento=%s',
                                (novo['documento'],)).fetchone()
            if reservado and reservado[0]!=chave:raise ValueError('Este CPF/CNPJ já pertence ou pertenceu a outra empresa.')
            c.execute('INSERT INTO crm_producao.documentos_empresas VALUES(%s,%s) ON CONFLICT(documento) DO NOTHING',
                      (novo['documento'],chave))
        c.execute('UPDATE crm_producao.identidades_empresas SET documento=%s,nome_fantasia=%s,razao_social=%s,versao=%s '
                  'WHERE chave_interna=%s',(novo['documento'],novo['nome_fantasia'],novo['razao_social'],novo['versao'],chave))
        c.execute('UPDATE crm_producao.catalogo_empresas SET nome=%s WHERE documento=%s',(novo['nome_fantasia'],chave))
        c.execute('INSERT INTO crm_producao.historico_identidade '
                  '(operacao,chave_interna,versao_anterior,dados_anteriores,dados_novos,usuario,criado_em) '
                  'VALUES(%s,%s,%s,%s,%s,%s,%s)',
                  (operacao,chave,versao,json.dumps(anterior,ensure_ascii=False),json.dumps(novo,ensure_ascii=False),
                   usuario,datetime.now(timezone.utc).isoformat()))
    return novo


def salvar_nomes(conectar,chave,versao,nome_fantasia,razao_social,usuario,operacao):
    nome_fantasia=str(nome_fantasia).strip();razao_social=str(razao_social).strip()
    if not nome_fantasia or len(nome_fantasia)>150 or len(razao_social)>200:
        raise ValueError('Informe nome fantasia de até 150 caracteres e razão social de até 200 caracteres.')
    return _editar(conectar,chave,versao,{'nome_fantasia':nome_fantasia,'razao_social':razao_social},usuario,operacao)


def alterar_documento(conectar,chave,versao,novo_documento,usuario,operacao,mesma_empresa=False):
    documento=normalizar_documento(novo_documento)
    if len(documento) not in (11,14):raise ValueError('Informe CPF com 11 dígitos ou CNPJ com 14 dígitos.')
    if not mesma_empresa:raise ValueError('Confirme que é uma correção do documento da mesma empresa.')
    return _editar(conectar,chave,versao,{'documento':documento},usuario,operacao)


def documento_exibicao(chave,perfis):
    return perfis.get(chave,{}).get('documento',chave)


def resolver_empresa(documento,empresas,perfis,aliases):
    documento=normalizar_documento(documento)
    # Documentos anteriores ficam reservados à mesma empresa, nunca a um novo cliente.
    chave=aliases.get(documento,documento)
    return chave if chave in empresas else ''
