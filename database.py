import os
import sqlite3

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)


# ==============================================================
# CONFIGURAÇÃO DO BANCO
#
# LOCAL:
#   DATABASE_URL ausente -> SQLite
#
# PRODUÇÃO:
#   DATABASE_URL presente -> PostgreSQL
# ==============================================================

DB_NAME = "monitor.db"

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

# Compatibilidade com URLs antigas do PostgreSQL
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgres://",
        "postgresql://",
        1
    )

USANDO_POSTGRES = bool(DATABASE_URL)


# ==============================================================
# CURSOR COMPATÍVEL COM SQLITE / POSTGRESQL
# ==============================================================

class _CursorPostgresCompativel:
    """
    Camada de compatibilidade para manter as consultas atuais
    funcionando tanto no SQLite quanto no PostgreSQL.

    PostgreSQL utiliza %s.
    SQLite utiliza ?.

    Também fornece comportamento semelhante ao lastrowid
    através de RETURNING id.
    """

    def __init__(self, cursor_real):
        self._cursor = cursor_real
        self.lastrowid = None

    def execute(self, sql, parametros=()):
        """
        Executa uma consulta PostgreSQL.

        Converte automaticamente:
            ? -> %s

        Para INSERTs que não possuem RETURNING id, adiciona:
            RETURNING id

        Isso permite manter o uso de cursor.lastrowid no
        restante do sistema.
        """

        sql_traduzido = sql.replace("?", "%s")

        sql_limpo = sql_traduzido.strip()

        if not sql_limpo:
            self._cursor.execute(
                sql_traduzido,
                parametros
            )
            self.lastrowid = None
            return

        comando = sql_limpo.split(None, 1)[0].upper()

        precisa_retornar_id = (
            comando == "INSERT"
            and "RETURNING" not in sql_traduzido.upper()
        )

        if precisa_retornar_id:
            sql_traduzido = (
                sql_traduzido.rstrip()
                .rstrip(";")
                + " RETURNING id"
            )

        self._cursor.execute(
            sql_traduzido,
            parametros
        )

        if precisa_retornar_id:
            resultado = self._cursor.fetchone()

            if resultado:
                try:
                    self.lastrowid = resultado["id"]
                except (TypeError, KeyError, IndexError):
                    self.lastrowid = resultado[0]
            else:
                self.lastrowid = None

        else:
            self.lastrowid = None

    def __getattr__(self, nome):
        return getattr(
            self._cursor,
            nome
        )


class _ConexaoPostgresCompativel:
    """
    Camada de compatibilidade para que o restante do projeto
    continue usando:

        conexao.cursor()
        conexao.commit()
        conexao.rollback()
        conexao.close()

    normalmente.
    """

    def __init__(self, conexao_real):
        self._conexao = conexao_real

    def cursor(self):
        return _CursorPostgresCompativel(
            self._conexao.cursor()
        )

    def __getattr__(self, nome):
        return getattr(
            self._conexao,
            nome
        )


# ==============================================================
# CONEXÃO
# ==============================================================

def conectar():
    """
    Abre conexão com o banco configurado.

    PostgreSQL:
        DATABASE_URL presente.

    SQLite:
        DATABASE_URL ausente.
    """

    if USANDO_POSTGRES:

        import psycopg2
        import psycopg2.extras

        conexao_real = psycopg2.connect(
            DATABASE_URL,
            cursor_factory=psycopg2.extras.DictCursor
        )

        return _ConexaoPostgresCompativel(
            conexao_real
        )

    conexao = sqlite3.connect(
        DB_NAME,
        timeout=10
    )

    conexao.row_factory = sqlite3.Row

    conexao.execute(
        "PRAGMA foreign_keys = ON"
    )

    conexao.execute(
        "PRAGMA busy_timeout = 10000"
    )

    return conexao


# ==============================================================
# UTILITÁRIOS
# ==============================================================

def obter_colunas(conexao, tabela):
    """
    Retorna as colunas existentes em uma tabela.
    """

    cursor = conexao.cursor()

    if USANDO_POSTGRES:

        cursor.execute(
            """
            SELECT column_name AS name
            FROM information_schema.columns
            WHERE table_name = ?
            ORDER BY ordinal_position
            """,
            (tabela,)
        )

    else:

        cursor.execute(
            f"""
            PRAGMA table_info({tabela})
            """
        )

    return [
        coluna["name"]
        for coluna in cursor.fetchall()
    ]


def _tabela_existe(conexao, tabela):
    """
    Verifica se uma tabela existe.
    """

    cursor = conexao.cursor()

    if USANDO_POSTGRES:

        cursor.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = ?
            LIMIT 1
            """,
            (tabela,)
        )

    else:

        cursor.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table'
              AND name = ?
            LIMIT 1
            """,
            (tabela,)
        )

    return cursor.fetchone() is not None


# ==============================================================
# MIGRAÇÃO DE MONITORAMENTOS
# ==============================================================

def migrar_monitoramentos(conexao):
    """
    Migração exclusiva para bancos SQLite antigos.

    Objetivo:
        codigo_status -> codigo_http

    Registros existentes são preservados.
    """

    if not _tabela_existe(
        conexao,
        "monitoramentos"
    ):
        return

    colunas = obter_colunas(
        conexao,
        "monitoramentos"
    )

    # Já está no formato atual.
    if (
        "codigo_http" in colunas
        and "codigo_status" not in colunas
    ):
        return

    # PostgreSQL já cria a tabela no formato correto.
    if USANDO_POSTGRES:
        return

    cursor = conexao.cursor()

    # Remove uma tabela temporária de migração,
    # caso tenha sobrado de uma execução anterior.
    cursor.execute(
        """
        DROP TABLE IF EXISTS monitoramentos_novo
        """
    )

    cursor.execute(
        """
        CREATE TABLE monitoramentos_novo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_id INTEGER,
            status TEXT,
            tempo_resposta REAL,
            codigo_http INTEGER,
            data_hora TEXT,
            FOREIGN KEY (site_id)
                REFERENCES sites(id)
        )
        """
    )

    colunas_antigas = set(colunas)

    if (
        "codigo_http" in colunas_antigas
        and "codigo_status" in colunas_antigas
    ):
        expressao_codigo = """
            COALESCE(codigo_http, codigo_status)
        """

    elif "codigo_http" in colunas_antigas:
        expressao_codigo = "codigo_http"

    elif "codigo_status" in colunas_antigas:
        expressao_codigo = "codigo_status"

    else:
        expressao_codigo = "NULL"

    expressao_site = (
        "site_id"
        if "site_id" in colunas_antigas
        else "NULL"
    )

    expressao_status = (
        "status"
        if "status" in colunas_antigas
        else "NULL"
    )

    expressao_tempo = (
        "tempo_resposta"
        if "tempo_resposta" in colunas_antigas
        else "NULL"
    )

    expressao_data = (
        "data_hora"
        if "data_hora" in colunas_antigas
        else "CURRENT_TIMESTAMP"
    )

    cursor.execute(
        f"""
        INSERT INTO monitoramentos_novo (
            id,
            site_id,
            status,
            tempo_resposta,
            codigo_http,
            data_hora
        )
        SELECT
            id,
            {expressao_site},
            {expressao_status},
            {expressao_tempo},
            {expressao_codigo},
            {expressao_data}
        FROM monitoramentos
        """
    )

    cursor.execute(
        """
        DROP TABLE monitoramentos
        """
    )

    cursor.execute(
        """
        ALTER TABLE monitoramentos_novo
        RENAME TO monitoramentos
        """
    )


# ==============================================================
# CRIAÇÃO DO BANCO
# ==============================================================

def criar_banco():
    """
    Cria todas as tabelas principais do sistema.

    O banco utilizado depende de DATABASE_URL.
    """

    conexao = conectar()

    try:

        cursor = conexao.cursor()

        # ======================================================
        # USERS
        # ======================================================

        if USANDO_POSTGRES:

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    nome TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    senha TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    ativo INTEGER NOT NULL DEFAULT 1
                )
                """
            )

        else:

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    senha TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    ativo INTEGER NOT NULL DEFAULT 1
                )
                """
            )

        # ======================================================
        # MIGRAÇÃO USERS - ROLE
        # ======================================================

        colunas_users = obter_colunas(
            conexao,
            "users"
        )

        if "role" not in colunas_users:

            cursor.execute(
                """
                ALTER TABLE users
                ADD COLUMN role TEXT
                NOT NULL
                DEFAULT 'user'
                """
            )

        # ======================================================
        # MIGRAÇÃO USERS - ATIVO
        # ======================================================

        colunas_users = obter_colunas(
            conexao,
            "users"
        )

        if "ativo" not in colunas_users:

            cursor.execute(
                """
                ALTER TABLE users
                ADD COLUMN ativo INTEGER
                NOT NULL
                DEFAULT 1
                """
            )

        # ======================================================
        # SITES
        # ======================================================

        if USANDO_POSTGRES:

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS sites (
                    id SERIAL PRIMARY KEY,
                    usuario_id INTEGER NOT NULL,
                    nome TEXT NOT NULL,
                    url TEXT NOT NULL,
                    criado_em TIMESTAMP
                        DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (usuario_id)
                        REFERENCES users(id)
                )
                """
            )

        else:

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS sites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario_id INTEGER NOT NULL,
                    nome TEXT NOT NULL,
                    url TEXT NOT NULL,
                    criado_em TIMESTAMP
                        DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (usuario_id)
                        REFERENCES users(id)
                )
                """
            )

        # ======================================================
        # MONITORAMENTOS
        # ======================================================

        if USANDO_POSTGRES:

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS monitoramentos (
                    id SERIAL PRIMARY KEY,
                    site_id INTEGER,
                    status TEXT,
                    tempo_resposta REAL,
                    codigo_http INTEGER,
                    data_hora TIMESTAMP
                        DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (site_id)
                        REFERENCES sites(id)
                )
                """
            )

        else:

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS monitoramentos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site_id INTEGER,
                    status TEXT,
                    tempo_resposta REAL,
                    codigo_http INTEGER,
                    data_hora TIMESTAMP
                        DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (site_id)
                        REFERENCES sites(id)
                )
                """
            )

        # ======================================================
        # MIGRAÇÃO MONITORAMENTOS
        # ======================================================

        migrar_monitoramentos(
            conexao
        )

        # ======================================================
        # SSL MONITORAMENTOS
        # ======================================================

        if USANDO_POSTGRES:

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS ssl_monitoramentos (
                    id SERIAL PRIMARY KEY,
                    site_id INTEGER NOT NULL,
                    dominio TEXT,
                    ip TEXT,
                    valido INTEGER,
                    data_expiracao TEXT,
                    dias_restantes INTEGER,
                    data_hora TIMESTAMP
                        DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (site_id)
                        REFERENCES sites(id)
                )
                """
            )

        else:

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS ssl_monitoramentos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site_id INTEGER NOT NULL,
                    dominio TEXT,
                    ip TEXT,
                    valido INTEGER,
                    data_expiracao TEXT,
                    dias_restantes INTEGER,
                    data_hora TIMESTAMP
                        DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (site_id)
                        REFERENCES sites(id)
                )
                """
            )

        # ======================================================
        # AUDIT LOGS
        # ======================================================

        if USANDO_POSTGRES:

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id SERIAL PRIMARY KEY,
                    usuario_id INTEGER,
                    acao TEXT NOT NULL,
                    detalhes TEXT,
                    ip TEXT,
                    data_hora TIMESTAMP
                        DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (usuario_id)
                        REFERENCES users(id)
                )
                """
            )

        else:

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario_id INTEGER,
                    acao TEXT NOT NULL,
                    detalhes TEXT,
                    ip TEXT,
                    data_hora TIMESTAMP
                        DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (usuario_id)
                        REFERENCES users(id)
                )
                """
            )

        # ======================================================
        # MIGRAÇÃO AUDITORIA
        # ======================================================

        colunas_auditoria = obter_colunas(
            conexao,
            "audit_logs"
        )

        if "detalhes" not in colunas_auditoria:

            cursor.execute(
                """
                ALTER TABLE audit_logs
                ADD COLUMN detalhes TEXT
                """
            )

        # ======================================================
        # ADMIN INICIAL
        # ======================================================

        cursor.execute(
            """
            SELECT COUNT(*) AS total
            FROM users
            """
        )

        resultado = cursor.fetchone()

        total_usuarios = (
            resultado["total"]
            if resultado
            else 0
        )

        if total_usuarios == 0:

            nome_admin = os.environ.get(
                "ADMIN_INITIAL_NAME",
                "Administrador"
            ).strip()

            email_admin = os.environ.get(
                "ADMIN_INITIAL_EMAIL",
                "admin@cloudmonitor.local"
            ).strip().lower()

            senha_admin_texto = os.environ.get(
                "ADMIN_INITIAL_PASSWORD"
            )

            # PostgreSQL exige senha configurada.
            if USANDO_POSTGRES:

                if not senha_admin_texto:

                    raise RuntimeError(
                        "ADMIN_INITIAL_PASSWORD não foi definida. "
                        "Configure essa variável de ambiente antes "
                        "de iniciar a aplicação em produção."
                    )

            # SQLite mantém compatibilidade com o ambiente local.
            else:

                if not senha_admin_texto:
                    senha_admin_texto = "admin123"

            senha_admin = generate_password_hash(
                senha_admin_texto
            )

            cursor.execute(
                """
                INSERT INTO users (
                    nome,
                    email,
                    senha,
                    role,
                    ativo
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    nome_admin,
                    email_admin,
                    senha_admin,
                    "admin",
                    1
                )
            )

        conexao.commit()

    except Exception:

        conexao.rollback()

        raise

    finally:

        conexao.close()


# ==============================================================
# USUÁRIOS
# ==============================================================

def criar_usuario(
    nome,
    email,
    senha
):

    conexao = conectar()

    try:

        cursor = conexao.cursor()

        senha_hash = generate_password_hash(
            senha
        )

        cursor.execute(
            """
            INSERT INTO users (
                nome,
                email,
                senha,
                role,
                ativo
            )
            VALUES (?, ?, ?, 'user', 1)
            """,
            (
                nome,
                email,
                senha_hash
            )
        )

        conexao.commit()

        return cursor.lastrowid

    finally:

        conexao.close()


# ==============================================================
# VERIFICAR E-MAIL
# ==============================================================

def email_existe(email):

    conexao = conectar()

    try:

        cursor = conexao.cursor()

        cursor.execute(
            """
            SELECT id
            FROM users
            WHERE email = ?
            """,
            (email,)
        )

        return cursor.fetchone() is not None

    finally:

        conexao.close()


# ==============================================================
# BUSCAR USUÁRIO POR E-MAIL
# ==============================================================

def buscar_usuario_por_email(email):

    conexao = conectar()

    try:

        cursor = conexao.cursor()

        cursor.execute(
            """
            SELECT *
            FROM users
            WHERE email = ?
            """,
            (email,)
        )

        return cursor.fetchone()

    finally:

        conexao.close()


# ==============================================================
# BUSCAR USUÁRIO POR ID
# ==============================================================

def buscar_usuario_por_id(usuario_id):

    conexao = conectar()

    try:

        cursor = conexao.cursor()

        cursor.execute(
            """
            SELECT *
            FROM users
            WHERE id = ?
            """,
            (usuario_id,)
        )

        return cursor.fetchone()

    finally:

        conexao.close()


# ==============================================================
# VERIFICAR SENHA
# ==============================================================

def verificar_senha(
    senha_digitada,
    senha_hash
):

    return check_password_hash(
        senha_hash,
        senha_digitada
    )


# ==============================================================
# LISTAR USUÁRIOS
# ==============================================================

def listar_usuarios():

    conexao = conectar()

    try:

        cursor = conexao.cursor()

        cursor.execute(
            """
            SELECT
                id,
                nome,
                email,
                role,
                ativo
            FROM users
            ORDER BY id ASC
            """
        )

        return cursor.fetchall()

    finally:

        conexao.close()


# ==============================================================
# ALTERAR USUÁRIO PELO ADMIN
# ==============================================================

def alterar_usuario_admin(
    usuario_id,
    role=None,
    ativo=None
):

    conexao = conectar()

    try:

        cursor = conexao.cursor()

        campos = []
        valores = []

        if role is not None:

            if role not in (
                "admin",
                "user"
            ):

                raise ValueError(
                    "Função de usuário inválida."
                )

            campos.append(
                "role = ?"
            )

            valores.append(
                role
            )

        if ativo is not None:

            ativo = int(ativo)

            if ativo not in (
                0,
                1
            ):

                raise ValueError(
                    "Status de usuário inválido."
                )

            campos.append(
                "ativo = ?"
            )

            valores.append(
                ativo
            )

        if not campos:
            return False

        valores.append(
            usuario_id
        )

        cursor.execute(
            f"""
            UPDATE users
            SET {", ".join(campos)}
            WHERE id = ?
            """,
            valores
        )

        conexao.commit()

        return cursor.rowcount > 0

    finally:

        conexao.close()


# ==============================================================
# SITES
# ==============================================================

def criar_site(
    usuario_id,
    nome,
    url
):

    conexao = conectar()

    try:

        cursor = conexao.cursor()

        cursor.execute(
            """
            INSERT INTO sites (
                usuario_id,
                nome,
                url
            )
            VALUES (?, ?, ?)
            """,
            (
                usuario_id,
                nome,
                url
            )
        )

        conexao.commit()

        return cursor.lastrowid

    finally:

        conexao.close()


# ==============================================================
# ALIAS DA API
# ==============================================================

def adicionar_site(
    usuario_id,
    nome,
    url
):

    return criar_site(
        usuario_id,
        nome,
        url
    )


# ==============================================================
# LISTAR SITES DO USUÁRIO
# ==============================================================

def listar_sites(usuario_id):

    conexao = conectar()

    try:

        cursor = conexao.cursor()

        cursor.execute(
            """
            SELECT *
            FROM sites
            WHERE usuario_id = ?
            ORDER BY id DESC
            """,
            (usuario_id,)
        )

        return cursor.fetchall()

    finally:

        conexao.close()


# ==============================================================
# BUSCAR SITE
# ==============================================================

def buscar_site(
    site_id,
    usuario_id
):

    conexao = conectar()

    try:

        cursor = conexao.cursor()

        cursor.execute(
            """
            SELECT *
            FROM sites
            WHERE id = ?
              AND usuario_id = ?
            """,
            (
                site_id,
                usuario_id
            )
        )

        return cursor.fetchone()

    finally:

        conexao.close()


# ==============================================================
# EXCLUIR SITE
# ==============================================================

def excluir_site(
    site_id,
    usuario_id
):

    conexao = conectar()

    try:

        cursor = conexao.cursor()

        # ------------------------------------------------------
        # Monitoramentos
        # ------------------------------------------------------

        cursor.execute(
            """
            DELETE FROM monitoramentos
            WHERE site_id = ?
            """,
            (site_id,)
        )

        # ------------------------------------------------------
        # Histórico SSL
        # ------------------------------------------------------

        cursor.execute(
            """
            DELETE FROM ssl_monitoramentos
            WHERE site_id = ?
            """,
            (site_id,)
        )

        # ------------------------------------------------------
        # Incidentes, caso a tabela exista
        # ------------------------------------------------------

        if _tabela_existe(
            conexao,
            "incidentes"
        ):

            cursor.execute(
                """
                DELETE FROM incidentes
                WHERE site_id = ?
                """,
                (site_id,)
            )

        # ------------------------------------------------------
        # Alertas SSL, caso a tabela exista
        # ------------------------------------------------------

        if _tabela_existe(
            conexao,
            "ssl_alertas"
        ):

            cursor.execute(
                """
                DELETE FROM ssl_alertas
                WHERE site_id = ?
                """,
                (site_id,)
            )

        # ------------------------------------------------------
        # Site
        # ------------------------------------------------------

        cursor.execute(
            """
            DELETE FROM sites
            WHERE id = ?
              AND usuario_id = ?
            """,
            (
                site_id,
                usuario_id
            )
        )

        removido = cursor.rowcount > 0

        conexao.commit()

        return removido

    except Exception:

        conexao.rollback()

        raise

    finally:

        conexao.close()


# ==============================================================
# MONITORAMENTO
# ==============================================================

def registrar_monitoramento(
    site_id,
    status,
    tempo_resposta=None,
    codigo_http=None,
    codigo_status=None
):

    # Compatibilidade com código antigo.
    if codigo_http is None:
        codigo_http = codigo_status

    conexao = conectar()

    try:

        cursor = conexao.cursor()

        cursor.execute(
            """
            INSERT INTO monitoramentos (
                site_id,
                status,
                tempo_resposta,
                codigo_http,
                data_hora
            )
            VALUES (
                ?,
                ?,
                ?,
                ?,
                CURRENT_TIMESTAMP
            )
            """,
            (
                site_id,
                status,
                tempo_resposta,
                codigo_http
            )
        )

        conexao.commit()

    finally:

        conexao.close()


# ==============================================================
# ALIAS DE MONITORAMENTO
# ==============================================================

def salvar_monitoramento(
    site_id,
    status,
    tempo_resposta=None,
    codigo_http=None,
    codigo_status=None
):

    registrar_monitoramento(
        site_id=site_id,
        status=status,
        tempo_resposta=tempo_resposta,
        codigo_http=codigo_http,
        codigo_status=codigo_status
    )


# ==============================================================
# LISTAR MONITORAMENTOS
# ==============================================================

def listar_monitoramentos(
    site_id=None,
    limite=None
):

    conexao = conectar()

    try:

        cursor = conexao.cursor()

        if site_id is not None:

            if limite is not None:

                cursor.execute(
                    """
                    SELECT *
                    FROM monitoramentos
                    WHERE site_id = ?
                    ORDER BY data_hora DESC
                    LIMIT ?
                    """,
                    (
                        site_id,
                        int(limite)
                    )
                )

            else:

                cursor.execute(
                    """
                    SELECT *
                    FROM monitoramentos
                    WHERE site_id = ?
                    ORDER BY data_hora DESC
                    """,
                    (site_id,)
                )

        else:

            if limite is not None:

                cursor.execute(
                    """
                    SELECT *
                    FROM monitoramentos
                    ORDER BY data_hora DESC
                    LIMIT ?
                    """,
                    (int(limite),)
                )

            else:

                cursor.execute(
                    """
                    SELECT *
                    FROM monitoramentos
                    ORDER BY data_hora DESC
                    """
                )

        return cursor.fetchall()

    finally:

        conexao.close()


# ==============================================================
# SSL
# ==============================================================

def registrar_ssl(
    site_id,
    dominio,
    ip,
    valido,
    data_expiracao,
    dias_restantes
):

    conexao = conectar()

    try:

        cursor = conexao.cursor()

        # A coluna valido utiliza 0/1 nos dois bancos.
        valido = int(bool(valido))

        cursor.execute(
            """
            INSERT INTO ssl_monitoramentos (
                site_id,
                dominio,
                ip,
                valido,
                data_expiracao,
                dias_restantes,
                data_hora
            )
            VALUES (
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                CURRENT_TIMESTAMP
            )
            """,
            (
                site_id,
                dominio,
                ip,
                valido,
                data_expiracao,
                dias_restantes
            )
        )

        conexao.commit()

    finally:

        conexao.close()


# ==============================================================
# ALIAS SSL
# ==============================================================

def salvar_ssl_monitoramento(
    site_id,
    dominio,
    ip,
    valido,
    data_expiracao,
    dias_restantes
):

    registrar_ssl(
        site_id=site_id,
        dominio=dominio,
        ip=ip,
        valido=valido,
        data_expiracao=data_expiracao,
        dias_restantes=dias_restantes
    )


# ==============================================================
# LISTAR SSL
# ==============================================================

def listar_ssl(site_id):

    conexao = conectar()

    try:

        cursor = conexao.cursor()

        cursor.execute(
            """
            SELECT *
            FROM ssl_monitoramentos
            WHERE site_id = ?
            ORDER BY data_hora DESC
            """,
            (site_id,)
        )

        return cursor.fetchall()

    finally:

        conexao.close()


# ==============================================================
# ALIAS SSL
# ==============================================================

def listar_ssl_monitoramentos(site_id):

    return listar_ssl(
        site_id
    )


# ==============================================================
# ADMIN
# LISTAR TODOS OS SITES
# ==============================================================

def listar_todos_sites_admin():

    conexao = conectar()

    try:

        cursor = conexao.cursor()

        cursor.execute(
            """
            SELECT
                sites.id,
                sites.nome,
                sites.url,
                sites.criado_em,
                users.id AS usuario_id,
                users.nome AS usuario_nome,
                users.email AS usuario_email
            FROM sites
            INNER JOIN users
                ON sites.usuario_id = users.id
            ORDER BY sites.id DESC
            """
        )

        return cursor.fetchall()

    finally:

        conexao.close()


# ==============================================================
# ADMIN
# LISTAR TODOS OS SSL
# ==============================================================

def listar_todos_ssl_admin():

    conexao = conectar()

    try:

        cursor = conexao.cursor()

        cursor.execute(
            """
            SELECT
                ssl_monitoramentos.*,
                sites.nome AS site_nome,
                sites.url AS site_url,
                users.nome AS usuario_nome,
                users.email AS usuario_email
            FROM ssl_monitoramentos
            INNER JOIN sites
                ON ssl_monitoramentos.site_id = sites.id
            INNER JOIN users
                ON sites.usuario_id = users.id
            ORDER BY
                ssl_monitoramentos.data_hora DESC
            """
        )

        return cursor.fetchall()

    finally:

        conexao.close()


# ==============================================================
# AUDITORIA
# ==============================================================

def registrar_auditoria(
    usuario_id,
    acao,
    descricao=None,
    detalhes=None,
    ip=None
):

    # Compatibilidade com código antigo.
    if detalhes is None:
        detalhes = descricao

    conexao = conectar()

    try:

        cursor = conexao.cursor()

        cursor.execute(
            """
            INSERT INTO audit_logs (
                usuario_id,
                acao,
                detalhes,
                ip,
                data_hora
            )
            VALUES (
                ?,
                ?,
                ?,
                ?,
                CURRENT_TIMESTAMP
            )
            """,
            (
                usuario_id,
                acao,
                detalhes,
                ip
            )
        )

        conexao.commit()

    finally:

        conexao.close()


# ==============================================================
# LISTAR AUDITORIA
# ==============================================================

def listar_auditoria(
    limite=None
):

    conexao = conectar()

    try:

        cursor = conexao.cursor()

        if limite is not None:

            cursor.execute(
                """
                SELECT
                    audit_logs.id,
                    audit_logs.usuario_id,
                    audit_logs.acao,
                    audit_logs.detalhes,
                    audit_logs.ip,
                    audit_logs.data_hora,
                    users.nome AS usuario_nome,
                    users.email AS usuario_email
                FROM audit_logs
                LEFT JOIN users
                    ON audit_logs.usuario_id = users.id
                ORDER BY audit_logs.id DESC
                LIMIT ?
                """,
                (int(limite),)
            )

        else:

            cursor.execute(
                """
                SELECT
                    audit_logs.id,
                    audit_logs.usuario_id,
                    audit_logs.acao,
                    audit_logs.detalhes,
                    audit_logs.ip,
                    audit_logs.data_hora,
                    users.nome AS usuario_nome,
                    users.email AS usuario_email
                FROM audit_logs
                LEFT JOIN users
                    ON audit_logs.usuario_id = users.id
                ORDER BY audit_logs.id DESC
                """
            )

        return cursor.fetchall()

    finally:

        conexao.close()


# ==============================================================
# EXECUÇÃO DIRETA
# ==============================================================

if __name__ == "__main__":

    criar_banco()

    banco = (
        "PostgreSQL"
        if USANDO_POSTGRES
        else "SQLite"
    )

    print()
    print("=" * 60)
    print("BANCO DE DADOS INICIALIZADO COM SUCESSO")
    print("=" * 60)
    print(f"Banco utilizado: {banco}")
    print("=" * 60)
    print()