import sqlite3
from datetime import datetime

from email_service import enviar_email


DB_NAME = "monitor.db"
FALHAS_PARA_ALERTA = 3


def conectar():
    conexao = sqlite3.connect(DB_NAME)
    conexao.row_factory = sqlite3.Row
    return conexao


def criar_tabela_incidentes():
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS incidentes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            falhas_consecutivas INTEGER DEFAULT 0,
            inicio_em TEXT NOT NULL,
            fim_em TEXT,
            criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (site_id) REFERENCES sites(id)
        )
    """)

    conexao.commit()
    conexao.close()


def buscar_incidente_aberto(site_id):
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT *
        FROM incidentes
        WHERE site_id = ?
        AND status = 'ABERTO'
        ORDER BY id DESC
        LIMIT 1
    """, (site_id,))

    incidente = cursor.fetchone()

    conexao.close()

    return incidente


def contar_falhas_consecutivas(site_id):
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT status
        FROM monitoramentos
        WHERE site_id = ?
        ORDER BY id DESC
    """, (site_id,))

    registros = cursor.fetchall()

    conexao.close()

    contador = 0

    for registro in registros:
        if registro["status"] == "OFFLINE":
            contador += 1
        else:
            break

    return contador


def buscar_dados_site(site_id):
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT
            sites.id,
            sites.nome,
            sites.url,
            users.email
        FROM sites
        INNER JOIN users
            ON users.id = sites.usuario_id
        WHERE sites.id = ?
        LIMIT 1
    """, (site_id,))

    resultado = cursor.fetchone()

    conexao.close()

    return resultado


def enviar_email_incidente_aberto(site_id, falhas_consecutivas):
    try:
        site = buscar_dados_site(site_id)

        if not site:
            print("⚠️ Não foi possível encontrar os dados do site para enviar o e-mail.")
            return

        destinatario = site["email"]

        assunto = f"🚨 Incidente detectado - {site['nome']}"

        mensagem = f"""
Olá!

O Cloud Security Monitor detectou um incidente no seu site.

SITE
Nome: {site['nome']}
URL: {site['url']}

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

        print(f"📧 Alerta de incidente enviado para {destinatario}")

    except Exception as erro:
        print(f"⚠️ Não foi possível enviar o e-mail de incidente: {erro}")


def enviar_email_incidente_resolvido(site_id):
    try:
        site = buscar_dados_site(site_id)

        if not site:
            print("⚠️ Não foi possível encontrar os dados do site para enviar o e-mail.")
            return

        destinatario = site["email"]

        assunto = f"🟢 Incidente resolvido - {site['nome']}"

        mensagem = f"""
Olá!

O Cloud Security Monitor detectou que o incidente do seu site foi resolvido.

SITE
Nome: {site['nome']}
URL: {site['url']}

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

        print(f"📧 E-mail de recuperação enviado para {destinatario}")

    except Exception as erro:
        print(f"⚠️ Não foi possível enviar o e-mail de recuperação: {erro}")


def abrir_incidente(site_id, falhas_consecutivas):
    conexao = conectar()
    cursor = conexao.cursor()

    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        INSERT INTO incidentes (
            site_id,
            status,
            falhas_consecutivas,
            inicio_em
        )
        VALUES (?, ?, ?, ?)
    """, (
        site_id,
        "ABERTO",
        falhas_consecutivas,
        agora
    ))

    conexao.commit()

    incidente_id = cursor.lastrowid

    conexao.close()

    print()
    print("🚨 INCIDENTE ABERTO")
    print(f"🚨 Site ID: {site_id}")
    print(f"🚨 Falhas consecutivas: {falhas_consecutivas}")
    print(f"🚨 Incidente ID: {incidente_id}")

    # Tenta enviar o e-mail.
    # Se o SMTP falhar, o incidente continua registrado normalmente.
    enviar_email_incidente_aberto(
        site_id=site_id,
        falhas_consecutivas=falhas_consecutivas
    )

    return incidente_id


def atualizar_incidente(incidente_id, falhas_consecutivas):
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        UPDATE incidentes
        SET falhas_consecutivas = ?
        WHERE id = ?
    """, (
        falhas_consecutivas,
        incidente_id
    ))

    conexao.commit()
    conexao.close()


def encerrar_incidente(incidente_id):
    conexao = conectar()
    cursor = conexao.cursor()

    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        UPDATE incidentes
        SET
            status = 'RESOLVIDO',
            fim_em = ?
        WHERE id = ?
    """, (
        agora,
        incidente_id
    ))

    # Descobre o site relacionado ao incidente.
    cursor.execute("""
        SELECT site_id
        FROM incidentes
        WHERE id = ?
        LIMIT 1
    """, (incidente_id,))

    resultado = cursor.fetchone()

    conexao.commit()
    conexao.close()

    print()
    print("🟢 INCIDENTE RESOLVIDO")
    print(f"🟢 Incidente ID: {incidente_id}")

    # Tenta enviar o e-mail de recuperação.
    if resultado:
        enviar_email_incidente_resolvido(
            site_id=resultado["site_id"]
        )


def processar_alerta(site_id):
    criar_tabela_incidentes()

    falhas = contar_falhas_consecutivas(site_id)

    incidente = buscar_incidente_aberto(site_id)

    # SITE ONLINE
    if falhas == 0:

        if incidente:
            encerrar_incidente(incidente["id"])

        return {
            "estado": "ONLINE",
            "falhas": 0,
            "incidente": None
        }

    # AINDA NÃO ATINGIU O LIMITE
    if falhas < FALHAS_PARA_ALERTA:

        if incidente:
            atualizar_incidente(
                incidente["id"],
                falhas
            )

        print()
        print(f"⚠️ Falha {falhas}/{FALHAS_PARA_ALERTA}")

        return {
            "estado": "AGUARDANDO",
            "falhas": falhas,
            "incidente": incidente["id"] if incidente else None
        }

    # ATINGIU O LIMITE DE FALHAS
    if falhas >= FALHAS_PARA_ALERTA:

        # Incidente já existe.
        # Não envia outro e-mail.
        if incidente:

            atualizar_incidente(
                incidente["id"],
                falhas
            )

            print()
            print("🚨 Incidente continua aberto.")
            print(f"🚨 Falhas consecutivas: {falhas}")

            return {
                "estado": "INCIDENTE_ABERTO",
                "falhas": falhas,
                "incidente": incidente["id"]
            }

        # Primeiro incidente.
        incidente_id = abrir_incidente(
            site_id,
            falhas
        )

        return {
            "estado": "INCIDENTE_ABERTO",
            "falhas": falhas,
            "incidente": incidente_id
        }


def listar_incidentes(site_id=None, limite=100):
    conexao = conectar()
    cursor = conexao.cursor()

    if site_id is None:

        cursor.execute("""
            SELECT *
            FROM incidentes
            ORDER BY id DESC
            LIMIT ?
        """, (limite,))

    else:

        cursor.execute("""
            SELECT *
            FROM incidentes
            WHERE site_id = ?
            ORDER BY id DESC
            LIMIT ?
        """, (
            site_id,
            limite
        ))

    incidentes = cursor.fetchall()

    conexao.close()

    return incidentes


if __name__ == "__main__":
    criar_tabela_incidentes()

    print("✅ Tabela de incidentes criada/verificada.")