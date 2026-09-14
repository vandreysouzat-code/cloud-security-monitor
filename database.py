import sqlite3
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "monitor.db")


def criar_banco():
    conexao = sqlite3.connect(DATABASE)
    cursor = conexao.cursor()

    # =========================
    # TABELA DE USUÁRIOS
    # =========================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            senha TEXT NOT NULL
        )
    """)

    # =========================
    # TABELA DE SITES
    # =========================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            url TEXT NOT NULL,
            ativo INTEGER NOT NULL DEFAULT 1
        )
    """)

    # Verifica se usuario_id já existe
    cursor.execute("PRAGMA table_info(sites)")
    colunas_sites = [coluna[1] for coluna in cursor.fetchall()]

    if "usuario_id" not in colunas_sites:
        cursor.execute("""
            ALTER TABLE sites
            ADD COLUMN usuario_id INTEGER
        """)

    # =========================
    # TABELA DE MONITORAMENTOS
    # =========================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS monitoramentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_hora TEXT NOT NULL,
            status TEXT NOT NULL,
            codigo_http INTEGER,
            tempo_resposta REAL
        )
    """)

    # Verifica se site_id já existe
    cursor.execute("PRAGMA table_info(monitoramentos)")
    colunas_monitoramentos = [
        coluna[1]
        for coluna in cursor.fetchall()
    ]

    if "site_id" not in colunas_monitoramentos:
        cursor.execute("""
            ALTER TABLE monitoramentos
            ADD COLUMN site_id INTEGER
        """)

    # =========================
    # CRIA USUÁRIO ADMIN PADRÃO
    # =========================

    cursor.execute("""
        SELECT COUNT(*)
        FROM usuarios
    """)

    quantidade_usuarios = cursor.fetchone()[0]

    if quantidade_usuarios == 0:

        senha_hash = generate_password_hash("admin123")

        cursor.execute("""
            INSERT INTO usuarios (
                nome,
                email,
                senha
            )
            VALUES (?, ?, ?)
        """, (
            "Administrador",
            "admin@cloudmonitor.local",
            senha_hash
        ))

    # =========================
    # PEGA PRIMEIRO USUÁRIO
    # =========================

    cursor.execute("""
        SELECT id
        FROM usuarios
        ORDER BY id
        LIMIT 1
    """)

    primeiro_usuario = cursor.fetchone()

    if primeiro_usuario:

        usuario_id = primeiro_usuario[0]

        # =========================
        # CRIA SITE PADRÃO
        # =========================

        cursor.execute("""
            SELECT COUNT(*)
            FROM sites
        """)

        quantidade_sites = cursor.fetchone()[0]

        if quantidade_sites == 0:

            cursor.execute("""
                INSERT INTO sites (
                    nome,
                    url,
                    ativo,
                    usuario_id
                )
                VALUES (?, ?, ?, ?)
            """, (
                "Example",
                "https://example.com",
                1,
                usuario_id
            ))

        # =========================
        # CORRIGE SITES ANTIGOS
        # =========================

        cursor.execute("""
            UPDATE sites
            SET usuario_id = ?
            WHERE usuario_id IS NULL
        """, (usuario_id,))

        # =========================
        # CORRIGE MONITORAMENTOS
        # =========================

        cursor.execute("""
            SELECT id
            FROM sites
            ORDER BY id
            LIMIT 1
        """)

        primeiro_site = cursor.fetchone()

        if primeiro_site:

            primeiro_site_id = primeiro_site[0]

            cursor.execute("""
                UPDATE monitoramentos
                SET site_id = ?
                WHERE site_id IS NULL
            """, (primeiro_site_id,))

    conexao.commit()
    conexao.close()


# =========================================================
# USUÁRIOS
# =========================================================

def criar_usuario(nome, email, senha):

    conexao = sqlite3.connect(DATABASE)
    cursor = conexao.cursor()

    senha_hash = generate_password_hash(senha)

    cursor.execute("""
        INSERT INTO usuarios (
            nome,
            email,
            senha
        )
        VALUES (?, ?, ?)
    """, (
        nome,
        email,
        senha_hash
    ))

    conexao.commit()

    usuario_id = cursor.lastrowid

    conexao.close()

    return usuario_id


def email_existe(email):

    conexao = sqlite3.connect(DATABASE)
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT id
        FROM usuarios
        WHERE email = ?
    """, (email,))

    resultado = cursor.fetchone()

    conexao.close()

    return resultado is not None


def buscar_usuario_por_email(email):

    conexao = sqlite3.connect(DATABASE)
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT
            id,
            nome,
            email,
            senha
        FROM usuarios
        WHERE email = ?
    """, (email,))

    registro = cursor.fetchone()

    conexao.close()

    if registro is None:
        return None

    return {
        "id": registro[0],
        "nome": registro[1],
        "email": registro[2],
        "senha": registro[3]
    }


def verificar_senha(senha, senha_hash):

    return check_password_hash(
        senha_hash,
        senha
    )


# =========================================================
# MONITORAMENTO
# =========================================================

def salvar_monitoramento(
    status,
    codigo_http,
    tempo_resposta,
    site_id
):

    conexao = sqlite3.connect(DATABASE)
    cursor = conexao.cursor()

    cursor.execute("""
        INSERT INTO monitoramentos (
            data_hora,
            status,
            codigo_http,
            tempo_resposta,
            site_id
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        datetime.now().isoformat(),
        status,
        codigo_http,
        tempo_resposta,
        site_id
    ))

    conexao.commit()
    conexao.close()


def listar_monitoramentos(
    limite=50,
    site_id=1
):

    conexao = sqlite3.connect(DATABASE)
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT
            id,
            data_hora,
            status,
            codigo_http,
            tempo_resposta
        FROM monitoramentos
        WHERE site_id = ?
        ORDER BY id DESC
        LIMIT ?
    """, (
        site_id,
        limite
    ))

    registros = cursor.fetchall()

    conexao.close()

    historico = []

    for registro in registros:

        historico.append({
            "id": registro[0],
            "data_hora": registro[1],
            "status": registro[2],
            "codigo_http": registro[3],
            "tempo_resposta_ms": registro[4]
        })

    return historico


# =========================================================
# SITES
# =========================================================

def listar_sites(usuario_id):

    conexao = sqlite3.connect(DATABASE)
    cursor = conexao.cursor()

    # IMPORTANTE:
    # Só retorna sites pertencentes ao usuário logado.

    cursor.execute("""
        SELECT
            id,
            nome,
            url,
            ativo
        FROM sites
        WHERE usuario_id = ?
        ORDER BY id
    """, (usuario_id,))

    registros = cursor.fetchall()

    conexao.close()

    sites = []

    for registro in registros:

        sites.append({
            "id": registro[0],
            "nome": registro[1],
            "url": registro[2],
            "ativo": bool(registro[3])
        })

    return sites


def buscar_site(site_id, usuario_id):

    conexao = sqlite3.connect(DATABASE)
    cursor = conexao.cursor()

    # IMPORTANTE:
    # O site precisa pertencer ao usuário.

    cursor.execute("""
        SELECT
            id,
            nome,
            url,
            ativo
        FROM sites
        WHERE id = ?
        AND usuario_id = ?
    """, (
        site_id,
        usuario_id
    ))

    registro = cursor.fetchone()

    conexao.close()

    if registro is None:
        return None

    return {
        "id": registro[0],
        "nome": registro[1],
        "url": registro[2],
        "ativo": bool(registro[3])
    }


def adicionar_site(
    nome,
    url,
    usuario_id
):

    conexao = sqlite3.connect(DATABASE)
    cursor = conexao.cursor()

    cursor.execute("""
        INSERT INTO sites (
            nome,
            url,
            usuario_id
        )
        VALUES (?, ?, ?)
    """, (
        nome,
        url,
        usuario_id
    ))

    conexao.commit()

    site_id = cursor.lastrowid

    conexao.close()

    return site_id