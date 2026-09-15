import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash


# ==============================================================
# CONFIGURAÇÃO
# ==============================================================

DB_NAME = "monitor.db"


# ==============================================================
# CONEXÃO COM BANCO
# ==============================================================

def conectar():
    conexao = sqlite3.connect(
        DB_NAME,
        timeout=10
    )

    conexao.row_factory = sqlite3.Row

    conexao.execute("PRAGMA foreign_keys = ON")
    conexao.execute("PRAGMA busy_timeout = 10000")

    return conexao


# ==============================================================
# UTILITÁRIOS
# ==============================================================

def obter_colunas(conexao, tabela):
    cursor = conexao.cursor()

    cursor.execute(
        f"PRAGMA table_info({tabela})"
    )

    return [
        coluna["name"]
        for coluna in cursor.fetchall()
    ]


# ==============================================================
# MIGRAÇÃO DE MONITORAMENTOS
#
# Objetivo:
# - remover codigo_status
# - manter somente codigo_http
# - preservar os registros antigos
# - preservar IDs
# - preservar datas
# - preservar status NULL
# ==============================================================

def migrar_monitoramentos(conexao):

    cursor = conexao.cursor()

    # ----------------------------------------------------------
    # Verifica se a tabela existe
    # ----------------------------------------------------------

    cursor.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        AND name = 'monitoramentos'
    """)

    tabela_existe = cursor.fetchone()

    if not tabela_existe:
        return

    colunas = obter_colunas(
        conexao,
        "monitoramentos"
    )

    # ----------------------------------------------------------
    # Se já estiver no padrão correto, não faz nada
    # ----------------------------------------------------------

    if (
        "codigo_http" in colunas
        and "codigo_status" not in colunas
    ):
        return

    # ----------------------------------------------------------
    # Remove uma tabela temporária deixada por uma migração
    # anterior que tenha falhado.
    #
    # IMPORTANTE:
    # A tabela original ainda existe neste ponto.
    # ----------------------------------------------------------

    cursor.execute("""
        DROP TABLE IF EXISTS monitoramentos_novo
    """)

    # ----------------------------------------------------------
    # Cria a tabela nova
    #
    # status NÃO é NOT NULL porque existem registros históricos
    # antigos onde status está NULL.
    # ----------------------------------------------------------

    cursor.execute("""
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
    """)

    # ----------------------------------------------------------
    # Descobre quais colunas existem na tabela antiga
    # ----------------------------------------------------------

    colunas_antigas = set(colunas)

    # ----------------------------------------------------------
    # Monta origem do código HTTP
    #
    # Se o banco antigo tiver:
    #
    # codigo_http
    #
    # usamos ele.
    #
    # Se tiver somente:
    #
    # codigo_status
    #
    # usamos codigo_status.
    #
    # Se tiver os dois:
    #
    # COALESCE escolhe codigo_http primeiro.
    # ----------------------------------------------------------

    if (
        "codigo_http" in colunas_antigas
        and "codigo_status" in colunas_antigas
    ):
        expressao_codigo = """
            COALESCE(codigo_http, codigo_status)
        """

    elif "codigo_http" in colunas_antigas:
        expressao_codigo = """
            codigo_http
        """

    elif "codigo_status" in colunas_antigas:
        expressao_codigo = """
            codigo_status
        """

    else:
        expressao_codigo = """
            NULL
        """

    # ----------------------------------------------------------
    # Outras colunas
    # ----------------------------------------------------------

    if "site_id" in colunas_antigas:
        expressao_site = "site_id"
    else:
        expressao_site = "NULL"

    if "status" in colunas_antigas:
        expressao_status = "status"
    else:
        expressao_status = "NULL"

    if "tempo_resposta" in colunas_antigas:
        expressao_tempo = "tempo_resposta"
    else:
        expressao_tempo = "NULL"

    if "data_hora" in colunas_antigas:
        expressao_data = "data_hora"
    else:
        expressao_data = "CURRENT_TIMESTAMP"

    # ----------------------------------------------------------
    # Copia os dados
    #
    # NÃO usamos NOT NULL.
    # Portanto registros históricos com status NULL
    # continuam existindo.
    # ----------------------------------------------------------

    cursor.execute(f"""
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
    """)

    # ----------------------------------------------------------
    # Remove tabela antiga
    # ----------------------------------------------------------

    cursor.execute("""
        DROP TABLE monitoramentos
    """)

    # ----------------------------------------------------------
    # Renomeia tabela nova
    # ----------------------------------------------------------

    cursor.execute("""
        ALTER TABLE monitoramentos_novo
        RENAME TO monitoramentos
    """)


# ==============================================================
# CRIAÇÃO / ATUALIZAÇÃO DO BANCO
# ==============================================================

def criar_banco():

    conexao = conectar()

    try:

        cursor = conexao.cursor()

        # ======================================================
        # USUÁRIOS
        # ======================================================

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                senha TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                ativo INTEGER NOT NULL DEFAULT 1
            )
        """)

        # ------------------------------------------------------
        # MIGRAÇÃO ROLE
        # ------------------------------------------------------

        colunas_users = obter_colunas(
            conexao,
            "users"
        )

        if "role" not in colunas_users:

            cursor.execute("""
                ALTER TABLE users
                ADD COLUMN role TEXT
                NOT NULL
                DEFAULT 'user'
            """)

        # ------------------------------------------------------
        # MIGRAÇÃO ATIVO
        # ------------------------------------------------------

        colunas_users = obter_colunas(
            conexao,
            "users"
        )

        if "ativo" not in colunas_users:

            cursor.execute("""
                ALTER TABLE users
                ADD COLUMN ativo INTEGER
                NOT NULL
                DEFAULT 1
            """)

        # ======================================================
        # SITES
        # ======================================================

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL,
                nome TEXT NOT NULL,
                url TEXT NOT NULL,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id)
                    REFERENCES users(id)
            )
        """)

        # ======================================================
        # MONITORAMENTOS
        # ======================================================

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS monitoramentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id INTEGER,
                status TEXT,
                tempo_resposta REAL,
                codigo_http INTEGER,
                data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (site_id)
                    REFERENCES sites(id)
            )
        """)

        # ======================================================
        # MIGRAÇÃO MONITORAMENTOS
        # ======================================================

        migrar_monitoramentos(
            conexao
        )

        # ======================================================
        # SSL
        # ======================================================

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ssl_monitoramentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id INTEGER NOT NULL,
                dominio TEXT,
                ip TEXT,
                valido INTEGER,
                data_expiracao TEXT,
                dias_restantes INTEGER,
                data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (site_id)
                    REFERENCES sites(id)
            )
        """)

        # ======================================================
        # AUDITORIA
        # ======================================================

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER,
                acao TEXT NOT NULL,
                detalhes TEXT,
                ip TEXT,
                data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id)
                    REFERENCES users(id)
            )
        """)

        # ------------------------------------------------------
        # Migração de auditoria caso exista descricao antiga
        # ------------------------------------------------------

        colunas_auditoria = obter_colunas(
            conexao,
            "audit_logs"
        )

        if "detalhes" not in colunas_auditoria:

            cursor.execute("""
                ALTER TABLE audit_logs
                ADD COLUMN detalhes TEXT
            """)

        # ======================================================
        # ADMIN INICIAL
        # ======================================================

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM users
        """)

        total_usuarios = cursor.fetchone()["total"]

        if total_usuarios == 0:

            senha_admin = generate_password_hash(
                "admin123"
            )

            cursor.execute("""
                INSERT INTO users (
                    nome,
                    email,
                    senha,
                    role,
                    ativo
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                "Administrador",
                "admin@cloudmonitor.local",
                senha_admin,
                "admin",
                1
            ))

        conexao.commit()

    except Exception:

        conexao.rollback()

        raise

    finally:

        conexao.close()


# ==============================================================
# USUÁRIOS
# ==============================================================

def criar_usuario(nome, email, senha):

    conexao = conectar()

    try:

        cursor = conexao.cursor()

        senha_hash = generate_password_hash(
            senha
        )

        cursor.execute("""
            INSERT INTO users (
                nome,
                email,
                senha,
                role,
                ativo
            )
            VALUES (?, ?, ?, 'user', 1)
        """, (
            nome,
            email,
            senha_hash
        ))

        conexao.commit()

        usuario_id = cursor.lastrowid

        return usuario_id

    finally:

        conexao.close()


# ==============================================================
# VERIFICAÇÃO DE E-MAIL
# ==============================================================

def email_existe(email):

    conexao = conectar()

    try:

        cursor = conexao.cursor()

        cursor.execute("""
            SELECT id
            FROM users
            WHERE email = ?
        """, (email,))

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

        cursor.execute("""
            SELECT *
            FROM users
            WHERE email = ?
        """, (email,))

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

        cursor.execute("""
            SELECT *
            FROM users
            WHERE id = ?
        """, (usuario_id,))

        return cursor.fetchone()

    finally:

        conexao.close()


# ==============================================================
# VERIFICAR SENHA
# ==============================================================

def verificar_senha(senha_digitada, senha_hash):

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

        cursor.execute("""
            SELECT
                id,
                nome,
                email,
                role,
                ativo
            FROM users
            ORDER BY id ASC
        """)

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

        # ------------------------------------------------------
        # ROLE
        # ------------------------------------------------------

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

        # ------------------------------------------------------
        # ATIVO
        # ------------------------------------------------------

        if ativo is not None:

            ativo = int(ativo)

            if ativo not in (0, 1):

                raise ValueError(
                    "Status de usuário inválido."
                )

            campos.append(
                "ativo = ?"
            )

            valores.append(
                ativo
            )

        # ------------------------------------------------------
        # NADA PARA ALTERAR
        # ------------------------------------------------------

        if not campos:

            return False

        # ------------------------------------------------------
        # UPDATE
        # ------------------------------------------------------

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

        cursor.execute("""
            INSERT INTO sites (
                usuario_id,
                nome,
                url
            )
            VALUES (?, ?, ?)
        """, (
            usuario_id,
            nome,
            url
        ))

        conexao.commit()

        return cursor.lastrowid

    finally:

        conexao.close()


# ==============================================================
# ADICIONAR SITE
# Alias usado pela API
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

        cursor.execute("""
            SELECT *
            FROM sites
            WHERE usuario_id = ?
            ORDER BY id DESC
        """, (
            usuario_id,
        ))

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

        cursor.execute("""
            SELECT *
            FROM sites
            WHERE id = ?
            AND usuario_id = ?
        """, (
            site_id,
            usuario_id
        ))

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
        # MONITORAMENTOS
        # ------------------------------------------------------

        cursor.execute("""
            DELETE FROM monitoramentos
            WHERE site_id = ?
        """, (
            site_id,
        ))

        # ------------------------------------------------------
        # SSL
        # ------------------------------------------------------

        cursor.execute("""
            DELETE FROM ssl_monitoramentos
            WHERE site_id = ?
        """, (
            site_id,
        ))

        # ------------------------------------------------------
        # SITE
        # ------------------------------------------------------

        cursor.execute("""
            DELETE FROM sites
            WHERE id = ?
            AND usuario_id = ?
        """, (
            site_id,
            usuario_id
        ))

        conexao.commit()

        return cursor.rowcount > 0

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

    # ----------------------------------------------------------
    # Compatibilidade com código antigo
    #
    # Se alguma parte do projeto ainda enviar:
    #
    # codigo_status
    #
    # convertemos automaticamente para:
    #
    # codigo_http
    # ----------------------------------------------------------

    if codigo_http is None:
        codigo_http = codigo_status

    conexao = conectar()

    try:

        cursor = conexao.cursor()

        cursor.execute("""
            INSERT INTO monitoramentos (
                site_id,
                status,
                tempo_resposta,
                codigo_http,
                data_hora
            )
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            site_id,
            status,
            tempo_resposta,
            codigo_http
        ))

        conexao.commit()

    finally:

        conexao.close()


# ==============================================================
# ALIAS ANTIGO
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

                cursor.execute("""
                    SELECT *
                    FROM monitoramentos
                    WHERE site_id = ?
                    ORDER BY data_hora DESC
                    LIMIT ?
                """, (
                    site_id,
                    int(limite)
                ))

            else:

                cursor.execute("""
                    SELECT *
                    FROM monitoramentos
                    WHERE site_id = ?
                    ORDER BY data_hora DESC
                """, (
                    site_id,
                ))

        else:

            if limite is not None:

                cursor.execute("""
                    SELECT *
                    FROM monitoramentos
                    ORDER BY data_hora DESC
                    LIMIT ?
                """, (
                    int(limite),
                ))

            else:

                cursor.execute("""
                    SELECT *
                    FROM monitoramentos
                    ORDER BY data_hora DESC
                """)

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

        cursor.execute("""
            INSERT INTO ssl_monitoramentos (
                site_id,
                dominio,
                ip,
                valido,
                data_expiracao,
                dias_restantes,
                data_hora
            )
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            site_id,
            dominio,
            ip,
            valido,
            data_expiracao,
            dias_restantes
        ))

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

        cursor.execute("""
            SELECT *
            FROM ssl_monitoramentos
            WHERE site_id = ?
            ORDER BY data_hora DESC
        """, (
            site_id,
        ))

        return cursor.fetchall()

    finally:

        conexao.close()


# ==============================================================
# ALIAS SSL
# ==============================================================

def listar_ssl_monitoramentos(
    site_id
):

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

        cursor.execute("""
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
        """)

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

        cursor.execute("""
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
        """)

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

    # ----------------------------------------------------------
    # Compatibilidade:
    #
    # Algumas partes antigas usam "descricao".
    #
    # O banco atual usa "detalhes".
    # ----------------------------------------------------------

    if detalhes is None:
        detalhes = descricao

    conexao = conectar()

    try:

        cursor = conexao.cursor()

        cursor.execute("""
            INSERT INTO audit_logs (
                usuario_id,
                acao,
                detalhes,
                ip,
                data_hora
            )
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            usuario_id,
            acao,
            detalhes,
            ip
        ))

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

            cursor.execute("""
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
            """, (
                int(limite),
            ))

        else:

            cursor.execute("""
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
            """)

        return cursor.fetchall()

    finally:

        conexao.close()


# ==============================================================
# EXECUÇÃO DIRETA
# ==============================================================

if __name__ == "__main__":

    criar_banco()

    print()
    print("=" * 60)
    print("BANCO DE DADOS INICIALIZADO COM SUCESSO")
    print("=" * 60)
    print()