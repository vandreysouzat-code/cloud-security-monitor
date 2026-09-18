from datetime import datetime

import database
from database import conectar
from email_service import enviar_email


def _placeholder():
    """
    SQLite: ?
    PostgreSQL: %s
    """
    return "%s" if database.USANDO_POSTGRES else "?"


def criar_tabela_ssl_alertas():
    conexao = conectar()

    try:
        cursor = conexao.cursor()

        if database.USANDO_POSTGRES:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS ssl_alertas (
                    id SERIAL PRIMARY KEY,
                    site_id INTEGER NOT NULL,
                    nivel TEXT NOT NULL,
                    dias_restantes INTEGER,
                    mensagem TEXT NOT NULL,
                    ativo INTEGER NOT NULL DEFAULT 1,
                    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    enviado_em TIMESTAMP,
                    FOREIGN KEY (site_id)
                        REFERENCES sites(id)
                        ON DELETE CASCADE
                )
                """
            )
        else:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS ssl_alertas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site_id INTEGER NOT NULL,
                    nivel TEXT NOT NULL,
                    dias_restantes INTEGER,
                    mensagem TEXT NOT NULL,
                    ativo INTEGER NOT NULL DEFAULT 1,
                    criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                    enviado_em TEXT,
                    FOREIGN KEY (site_id)
                        REFERENCES sites(id)
                        ON DELETE CASCADE
                )
                """
            )

        conexao.commit()

    finally:
        conexao.close()


def buscar_alerta_ativo(site_id, nivel):
    conexao = conectar()

    try:
        cursor = conexao.cursor()
        p = _placeholder()

        cursor.execute(
            f"""
            SELECT *
            FROM ssl_alertas
            WHERE site_id = {p}
              AND nivel = {p}
              AND ativo = 1
            ORDER BY id DESC
            LIMIT 1
            """,
            (site_id, nivel)
        )

        return cursor.fetchone()

    finally:
        conexao.close()


def buscar_dados_site(site_id):
    conexao = conectar()

    try:
        cursor = conexao.cursor()
        p = _placeholder()

        cursor.execute(
            f"""
            SELECT
                sites.id,
                sites.nome,
                sites.url,
                users.email
            FROM sites
            INNER JOIN users
                ON users.id = sites.usuario_id
            WHERE sites.id = {p}
            LIMIT 1
            """,
            (site_id,)
        )

        return cursor.fetchone()

    finally:
        conexao.close()


def enviar_email_alerta_ssl(
    site_id,
    nivel,
    dias_restantes,
    mensagem_alerta
):
    site = buscar_dados_site(site_id)

    if not site:
        print("⚠️ Não foi possível encontrar os dados do site.")
        return False

    try:
        destinatario = site["email"]
        nome_site = site["nome"]
        url_site = site["url"]
    except (TypeError, KeyError, IndexError):
        destinatario = site[3]
        nome_site = site[1]
        url_site = site[2]

    assunto = f"🔐 Alerta SSL - {nome_site} - {nivel}"

    mensagem = f"""
Olá!

O Cloud Security Monitor detectou uma situação relacionada ao certificado SSL do seu site.

SITE
Nome: {nome_site}
URL: {url_site}

CERTIFICADO SSL
Nível: {nivel}
Dias restantes: {dias_restantes}

ALERTA
{mensagem_alerta}

Recomendamos verificar o certificado SSL do domínio para evitar interrupções no serviço.

Cloud Security Monitor
Sistema automático de monitoramento e segurança.
""".strip()

    try:
        enviar_email(
            destinatario=destinatario,
            assunto=assunto,
            mensagem=mensagem
        )

        print(
            f"📧 Alerta SSL enviado para {destinatario}"
        )

        return True

    except Exception as erro:
        print(
            f"⚠️ Não foi possível enviar o alerta SSL: {erro}"
        )

        return False


def criar_alerta_ssl(
    site_id,
    nivel,
    dias_restantes,
    mensagem
):
    criar_tabela_ssl_alertas()

    alerta_existente = buscar_alerta_ativo(
        site_id,
        nivel
    )

    if alerta_existente:
        return {
            "criado": False,
            "enviado": False,
            "alerta": alerta_existente
        }

    conexao = conectar()

    try:
        cursor = conexao.cursor()
        p = _placeholder()

        agora = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        if database.USANDO_POSTGRES:
            cursor.execute(
                f"""
                INSERT INTO ssl_alertas (
                    site_id,
                    nivel,
                    dias_restantes,
                    mensagem,
                    ativo,
                    criado_em
                )
                VALUES (
                    {p},
                    {p},
                    {p},
                    {p},
                    1,
                    {p}
                )
                RETURNING id
                """,
                (
                    site_id,
                    nivel,
                    dias_restantes,
                    mensagem,
                    agora
                )
            )

            resultado = cursor.fetchone()

            if not resultado:
                raise RuntimeError(
                    "Não foi possível obter o ID do alerta SSL."
                )

            alerta_id = resultado[0]

        else:
            cursor.execute(
                f"""
                INSERT INTO ssl_alertas (
                    site_id,
                    nivel,
                    dias_restantes,
                    mensagem,
                    ativo,
                    criado_em
                )
                VALUES (
                    {p},
                    {p},
                    {p},
                    {p},
                    1,
                    {p}
                )
                """,
                (
                    site_id,
                    nivel,
                    dias_restantes,
                    mensagem,
                    agora
                )
            )

            alerta_id = cursor.lastrowid

        conexao.commit()

    finally:
        conexao.close()

    print(
        f"🚨 Novo alerta SSL registrado (ID {alerta_id})"
    )

    enviado = enviar_email_alerta_ssl(
        site_id=site_id,
        nivel=nivel,
        dias_restantes=dias_restantes,
        mensagem_alerta=mensagem
    )

    if enviado:
        conexao = conectar()

        try:
            cursor = conexao.cursor()
            p = _placeholder()

            cursor.execute(
                f"""
                UPDATE ssl_alertas
                SET enviado_em = {p}
                WHERE id = {p}
                """,
                (
                    datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    alerta_id
                )
            )

            conexao.commit()

        finally:
            conexao.close()

    return {
        "criado": True,
        "enviado": enviado,
        "alerta_id": alerta_id
    }


def desativar_alertas_ssl(site_id):
    conexao = conectar()

    try:
        cursor = conexao.cursor()
        p = _placeholder()

        cursor.execute(
            f"""
            UPDATE ssl_alertas
            SET ativo = 0
            WHERE site_id = {p}
              AND ativo = 1
            """,
            (site_id,)
        )

        quantidade = cursor.rowcount

        conexao.commit()

        return quantidade

    finally:
        conexao.close()


def listar_alertas_ssl(
    site_id=None,
    limite=100
):
    conexao = conectar()

    try:
        cursor = conexao.cursor()
        p = _placeholder()

        limite = int(limite)

        if site_id is None:
            cursor.execute(
                f"""
                SELECT *
                FROM ssl_alertas
                ORDER BY id DESC
                LIMIT {p}
                """,
                (limite,)
            )
        else:
            cursor.execute(
                f"""
                SELECT *
                FROM ssl_alertas
                WHERE site_id = {p}
                ORDER BY id DESC
                LIMIT {p}
                """,
                (
                    site_id,
                    limite
                )
            )

        return cursor.fetchall()

    finally:
        conexao.close()


if __name__ == "__main__":
    criar_tabela_ssl_alertas()

    banco = (
        "PostgreSQL"
        if database.USANDO_POSTGRES
        else "SQLite"
    )

    print("✅ Tabela ssl_alertas criada/verificada.")
    print(f"🗄️ Banco detectado: {banco}")