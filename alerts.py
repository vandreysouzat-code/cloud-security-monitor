import sqlite3
from datetime import datetime

DB_NAME = "monitor.db"

FALHAS_PARA_ALERTA = 3


# ==============================================================
# CONEXÃO
# ==============================================================

def conectar():
    conexao = sqlite3.connect(DB_NAME)
    conexao.row_factory = sqlite3.Row

    return conexao


# ==============================================================
# CRIAÇÃO DA TABELA DE INCIDENTES
# ==============================================================

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

            FOREIGN KEY (site_id)
                REFERENCES sites(id)
        )
    """)

    conexao.commit()
    conexao.close()


# ==============================================================
# BUSCAR INCIDENTE ABERTO
# ==============================================================

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


# ==============================================================
# CONTAR FALHAS CONSECUTIVAS
# ==============================================================

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

        status = registro["status"]

        if status == "OFFLINE":
            contador += 1

        else:
            break

    return contador


# ==============================================================
# ABRIR INCIDENTE
# ==============================================================

def abrir_incidente(site_id, falhas_consecutivas):

    conexao = conectar()
    cursor = conexao.cursor()

    agora = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

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
    print(
        f"🚨 Falhas consecutivas: "
        f"{falhas_consecutivas}"
    )
    print(f"🚨 Incidente ID: {incidente_id}")

    return incidente_id


# ==============================================================
# ATUALIZAR INCIDENTE
# ==============================================================

def atualizar_incidente(
    incidente_id,
    falhas_consecutivas
):

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


# ==============================================================
# ENCERRAR INCIDENTE
# ==============================================================

def encerrar_incidente(incidente_id):

    conexao = conectar()
    cursor = conexao.cursor()

    agora = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

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

    conexao.commit()

    conexao.close()

    print()
    print("🟢 INCIDENTE RESOLVIDO")
    print(f"🟢 Incidente ID: {incidente_id}")


# ==============================================================
# PROCESSAR ALERTA
# ==============================================================

def processar_alerta(site_id):

    criar_tabela_incidentes()

    falhas = contar_falhas_consecutivas(site_id)

    incidente = buscar_incidente_aberto(site_id)

    # ==========================================================
    # SITE ONLINE
    # ==========================================================

    if falhas == 0:

        if incidente:

            encerrar_incidente(
                incidente["id"]
            )

        return {
            "estado": "ONLINE",
            "falhas": 0,
            "incidente": None
        }

    # ==========================================================
    # SITE OFFLINE
    # ==========================================================

    if falhas < FALHAS_PARA_ALERTA:

        if incidente:

            atualizar_incidente(
                incidente["id"],
                falhas
            )

        print()
        print(
            f"⚠️ Falha {falhas}/"
            f"{FALHAS_PARA_ALERTA}"
        )

        return {
            "estado": "AGUARDANDO",
            "falhas": falhas,
            "incidente": (
                incidente["id"]
                if incidente
                else None
            )
        }

    # ==========================================================
    # 3 OU MAIS FALHAS
    # ==========================================================

    if falhas >= FALHAS_PARA_ALERTA:

        # Se já existe incidente, não cria outro.
        if incidente:

            atualizar_incidente(
                incidente["id"],
                falhas
            )

            print()
            print(
                f"🚨 Incidente continua aberto."
            )
            print(
                f"🚨 Falhas consecutivas: "
                f"{falhas}"
            )

            return {
                "estado": "INCIDENTE_ABERTO",
                "falhas": falhas,
                "incidente": incidente["id"]
            }

        # Caso ainda não exista incidente,
        # cria um novo.

        incidente_id = abrir_incidente(
            site_id,
            falhas
        )

        return {
            "estado": "INCIDENTE_ABERTO",
            "falhas": falhas,
            "incidente": incidente_id
        }


# ==============================================================
# HISTÓRICO DE INCIDENTES
# ==============================================================

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


# ==============================================================
# TESTE
# ==============================================================

if __name__ == "__main__":

    criar_tabela_incidentes()

    print(
        "✅ Tabela de incidentes criada/verificada."
    )
    