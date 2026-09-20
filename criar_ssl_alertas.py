import database


def criar_tabela_ssl_alertas():
    conexao = database.conectar()

    try:
        cursor = conexao.cursor()

        print("=" * 60)
        print("CRIANDO TABELA SSL_ALERTAS")
        print("=" * 60)

        if database.USANDO_POSTGRES:

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ssl_alertas (
                    id SERIAL PRIMARY KEY,
                    site_id INTEGER NOT NULL,
                    nivel TEXT NOT NULL,
                    mensagem TEXT,
                    dias_restantes INTEGER,
                    ativo INTEGER NOT NULL DEFAULT 1,
                    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (site_id)
                        REFERENCES sites(id)
                        ON DELETE CASCADE
                )
            """)

        else:

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ssl_alertas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site_id INTEGER NOT NULL,
                    nivel TEXT NOT NULL,
                    mensagem TEXT,
                    dias_restantes INTEGER,
                    ativo INTEGER NOT NULL DEFAULT 1,
                    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (site_id)
                        REFERENCES sites(id)
                        ON DELETE CASCADE
                )
            """)

        conexao.commit()

        print()
        print("✅ Tabela ssl_alertas criada/verificada com sucesso.")
        print()
        print(
            "Banco utilizado:",
            "PostgreSQL"
            if database.USANDO_POSTGRES
            else "SQLite"
        )
        print("=" * 60)

    except Exception as erro:

        conexao.rollback()

        print()
        print("❌ ERRO AO CRIAR TABELA SSL_ALERTAS")
        print()
        print(erro)

        raise

    finally:

        conexao.close()


if __name__ == "__main__":
    criar_tabela_ssl_alertas()

