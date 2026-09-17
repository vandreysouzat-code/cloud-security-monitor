from datetime import datetime

import database
from database import conectar
from email_service import enviar_email


FALHAS_PARA_ALERTA = 3


def _placeholder():
    """
    SQLite:
        ?

    PostgreSQL:
        %s
    """
    return "%s" if database.USANDO_POSTGRES else "?"


def _obter_valor(row, chave, indice):
    """
    Obtém um valor de uma linha retornada pelo banco.

    Funciona tanto com linhas que permitem acesso por nome
    quanto com linhas que permitem acesso por índice.
    """
    if row is None:
        return None

    try:
        return row[chave]
    except (TypeError, KeyError, IndexError):
        return row[indice]


def criar_tabela_incidentes():
    """
    Cria a tabela de incidentes caso ela ainda não exista.
    """

    conexao = conectar()

    try:
        cursor = conexao.cursor()

        if database.USANDO_POSTGRES:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS incidentes (
                    id SERIAL PRIMARY KEY,
                    site_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    falhas_consecutivas INTEGER DEFAULT 0,
                    inicio_em TIMESTAMP NOT NULL,
                    fim_em TIMESTAMP,
                    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (site_id)
                        REFERENCES sites(id)
                        ON DELETE CASCADE
                )
                """
            )

        else:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS incidentes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    falhas_consecutivas INTEGER DEFAULT 0,
                    inicio_em TEXT NOT NULL,
                    fim_em TEXT,
                    criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (site_id)
                        REFERENCES sites(id)
                        ON DELETE CASCADE
                )
                """
            )

        conexao.commit()

    finally:
        conexao.close()


def buscar_incidente_aberto(site_id):
    conexao = conectar()

    try:
        cursor = conexao.cursor()
        p = _placeholder()

        cursor.execute(
            f"""
            SELECT *
            FROM incidentes
            WHERE site_id = {p}
              AND status = 'ABERTO'
            ORDER BY id DESC
            LIMIT 1
            """,
            (site_id,)
        )

        return cursor.fetchone()

    finally:
        conexao.close()


def contar_falhas_consecutivas(site_id):
    conexao = conectar()

    try:
        cursor = conexao.cursor()
        p = _placeholder()

        cursor.execute(
            f"""
            SELECT status
            FROM monitoramentos
            WHERE site_id = {p}
            ORDER BY id DESC
            """,
            (site_id,)
        )

        registros = cursor.fetchall()

    finally:
        conexao.close()

    contador = 0

    for registro in registros:
        status = _obter_valor(
            registro,
            "status",
            0
        )

        if str(status).upper() == "OFFLINE":
            contador += 1
        else:
            break

    return contador


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


def enviar_email_incidente_aberto(
    site_id,
    falhas_consecutivas
):
    try:
        site = buscar_dados_site(site_id)

        if not site:
            print(
                "⚠️ Não foi possível encontrar os dados "
                "do site para enviar o e-mail."
            )
            return

        destinatario = _obter_valor(
            site,
            "email",
            3
        )

        nome_site = _obter_valor(
            site,
            "nome",
            1
        )

        url_site = _obter_valor(
            site,
            "url",
            2
        )

        assunto = (
            f"🚨 Incidente detectado - "
            f"{nome_site}"
        )

        mensagem = f"""
Olá!

O Cloud Security Monitor detectou um incidente no seu site.

SITE
Nome: {nome_site}
URL: {url_site}

STATUS
O site apresentou {falhas_consecutivas} falhas consecutivas.

Um incidente foi aberto automaticamente pelo sistema.

A equipe responsável deve verificar o serviço monitorado.

Cloud Security Monitor
Sistema automático de monitoramento e segurança.
""".strip()

        enviar_email(
            destinatario=destinatario,
            assunto=assunto,
            mensagem=mensagem
        )

        print(
            f"📧 Alerta de incidente enviado para "
            f"{destinatario}"
        )

    except Exception as erro:
        print(
            f"⚠️ Não foi possível enviar o e-mail "
            f"de incidente: {erro}"
        )


def enviar_email_incidente_resolvido(site_id):
    try:
        site = buscar_dados_site(site_id)

        if not site:
            print(
                "⚠️ Não foi possível encontrar os dados "
                "do site para enviar o e-mail."
            )
            return

        destinatario = _obter_valor(
            site,
            "email",
            3
        )

        nome_site = _obter_valor(
            site,
            "nome",
            1
        )

        url_site = _obter_valor(
            site,
            "url",
            2
        )

        assunto = (
            f"🟢 Incidente resolvido - "
            f"{nome_site}"
        )

        mensagem = f"""
Olá!

O Cloud Security Monitor detectou que o incidente do seu site foi resolvido.

SITE
Nome: {nome_site}
URL: {url_site}

STATUS
O site voltou a responder normalmente.

O incidente foi encerrado automaticamente pelo sistema.

Cloud Security Monitor
Sistema automático de monitoramento e segurança.
""".strip()

        enviar_email(
            destinatario=destinatario,
            assunto=assunto,
            mensagem=mensagem
        )

        print(
            f"📧 E-mail de recuperação enviado para "
            f"{destinatario}"
        )

    except Exception as erro:
        print(
            f"⚠️ Não foi possível enviar o e-mail "
            f"de recuperação: {erro}"
        )


def abrir_incidente(
    site_id,
    falhas_consecutivas
):
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
                INSERT INTO incidentes (
                    site_id,
                    status,
                    falhas_consecutivas,
                    inicio_em
                )
                VALUES (
                    {p},
                    {p},
                    {p},
                    {p}
                )
                RETURNING id
                """,
                (
                    site_id,
                    "ABERTO",
                    falhas_consecutivas,
                    agora
                )
            )

            resultado = cursor.fetchone()

            if not resultado:
                raise RuntimeError(
                    "Não foi possível obter o ID do incidente."
                )

            incidente_id = resultado[0]

        else:
            cursor.execute(
                f"""
                INSERT INTO incidentes (
                    site_id,
                    status,
                    falhas_consecutivas,
                    inicio_em
                )
                VALUES (
                    {p},
                    {p},
                    {p},
                    {p}
                )
                """,
                (
                    site_id,
                    "ABERTO",
                    falhas_consecutivas,
                    agora
                )
            )

            incidente_id = cursor.lastrowid

        conexao.commit()

    finally:
        conexao.close()

    print()
    print("🚨 INCIDENTE ABERTO")
    print(f"🚨 Site ID: {site_id}")
    print(
        f"🚨 Falhas consecutivas: "
        f"{falhas_consecutivas}"
    )
    print(
        f"🚨 Incidente ID: "
        f"{incidente_id}"
    )

    enviar_email_incidente_aberto(
        site_id=site_id,
        falhas_consecutivas=falhas_consecutivas
    )

    return incidente_id


def atualizar_incidente(
    incidente_id,
    falhas_consecutivas
):
    conexao = conectar()

    try:
        cursor = conexao.cursor()
        p = _placeholder()

        cursor.execute(
            f"""
            UPDATE incidentes
            SET falhas_consecutivas = {p}
            WHERE id = {p}
            """,
            (
                falhas_consecutivas,
                incidente_id
            )
        )

        conexao.commit()

    finally:
        conexao.close()


def encerrar_incidente(incidente_id):
    conexao = conectar()

    try:
        cursor = conexao.cursor()
        p = _placeholder()

        agora = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        cursor.execute(
            f"""
            SELECT site_id
            FROM incidentes
            WHERE id = {p}
            LIMIT 1
            """,
            (incidente_id,)
        )

        resultado = cursor.fetchone()

        if not resultado:
            print(
                f"⚠️ Incidente {incidente_id} "
                f"não encontrado."
            )
            return

        cursor.execute(
            f"""
            UPDATE incidentes
            SET
                status = 'RESOLVIDO',
                fim_em = {p}
            WHERE id = {p}
            """,
            (
                agora,
                incidente_id
            )
        )

        conexao.commit()

    finally:
        conexao.close()

    print()
    print("🟢 INCIDENTE RESOLVIDO")
    print(
        f"🟢 Incidente ID: "
        f"{incidente_id}"
    )

    site_id = _obter_valor(
        resultado,
        "site_id",
        0
    )

    enviar_email_incidente_resolvido(
        site_id=site_id
    )


def processar_alerta(site_id):
    """
    Processa o estado de alerta de um site.

    Regras:
        0 falhas:
            ONLINE

        1 ou 2 falhas:
            AGUARDANDO

        3 ou mais falhas:
            INCIDENTE_ABERTO
    """

    criar_tabela_incidentes()

    falhas = contar_falhas_consecutivas(
        site_id
    )

    incidente = buscar_incidente_aberto(
        site_id
    )

    if falhas == 0:

        if incidente:
            incidente_id = _obter_valor(
                incidente,
                "id",
                0
            )

            encerrar_incidente(
                incidente_id
            )

        return {
            "estado": "ONLINE",
            "falhas": 0,
            "incidente": None
        }

    if falhas < FALHAS_PARA_ALERTA:

        incidente_id = None

        if incidente:
            incidente_id = _obter_valor(
                incidente,
                "id",
                0
            )

            atualizar_incidente(
                incidente_id,
                falhas
            )

        print()
        print(
            f"⚠️ Falha "
            f"{falhas}/{FALHAS_PARA_ALERTA}"
        )

        return {
            "estado": "AGUARDANDO",
            "falhas": falhas,
            "incidente": incidente_id
        }

    if incidente:

        incidente_id = _obter_valor(
            incidente,
            "id",
            0
        )

        atualizar_incidente(
            incidente_id,
            falhas
        )

        print()
        print("🚨 Incidente continua aberto.")
        print(
            f"🚨 Falhas consecutivas: "
            f"{falhas}"
        )

        return {
            "estado": "INCIDENTE_ABERTO",
            "falhas": falhas,
            "incidente": incidente_id
        }

    incidente_id = abrir_incidente(
        site_id,
        falhas
    )

    return {
        "estado": "INCIDENTE_ABERTO",
        "falhas": falhas,
        "incidente": incidente_id
    }


def listar_incidentes(
    site_id=None,
    limite=100
):
    conexao = conectar()

    try:
        cursor = conexao.cursor()
        p = _placeholder()

        limite = int(limite)

        if limite < 1:
            limite = 1

        if limite > 1000:
            limite = 1000

        if site_id is None:
            cursor.execute(
                f"""
                SELECT *
                FROM incidentes
                ORDER BY id DESC
                LIMIT {p}
                """,
                (limite,)
            )

        else:
            cursor.execute(
                f"""
                SELECT *
                FROM incidentes
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
    criar_tabela_incidentes()

    banco = (
        "PostgreSQL"
        if database.USANDO_POSTGRES
        else "SQLite"
    )

    print(
        "✅ Tabela de incidentes "
        "criada/verificada."
    )

    print(
        f"🗄️ Banco detectado: {banco}"
    )