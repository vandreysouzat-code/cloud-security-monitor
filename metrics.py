import database
from database import conectar


def _placeholder():
    """
    Retorna o placeholder correto para o banco de dados.

    SQLite:
        ?

    PostgreSQL:
        %s
    """
    return "%s" if database.USANDO_POSTGRES else "?"


def obter_metricas(site_id):
    """
    Obtém as métricas de monitoramento de um site.

    Retorna:
        - total_verificacoes
        - online
        - offline
        - disponibilidade
        - tempo_medio_ms
    """

    conexao = conectar()

    try:
        cursor = conexao.cursor()
        placeholder = _placeholder()

        cursor.execute(
            f"""
            SELECT
                COUNT(*) AS total,
                SUM(
                    CASE
                        WHEN UPPER(status) = 'ONLINE'
                        THEN 1
                        ELSE 0
                    END
                ) AS online,
                SUM(
                    CASE
                        WHEN UPPER(status) = 'OFFLINE'
                        THEN 1
                        ELSE 0
                    END
                ) AS offline,
                AVG(tempo_resposta) AS tempo_medio
            FROM monitoramentos
            WHERE site_id = {placeholder}
            """,
            (site_id,)
        )

        resultado = cursor.fetchone()

    finally:
        conexao.close()

    if resultado is None:
        return {
            "total_verificacoes": 0,
            "online": 0,
            "offline": 0,
            "disponibilidade": 0,
            "tempo_medio_ms": 0
        }

    # Compatibilidade com diferentes tipos de resultado
    try:
        total = resultado["total"] or 0
        online = resultado["online"] or 0
        offline = resultado["offline"] or 0
        tempo_medio = resultado["tempo_medio"] or 0
    except (TypeError, KeyError, IndexError):
        total = resultado[0] or 0
        online = resultado[1] or 0
        offline = resultado[2] or 0
        tempo_medio = resultado[3] or 0

    if total > 0:
        disponibilidade = (online / total) * 100
    else:
        disponibilidade = 0

    return {
        "total_verificacoes": int(total),
        "online": int(online),
        "offline": int(offline),
        "disponibilidade": round(disponibilidade, 2),
        "tempo_medio_ms": round(float(tempo_medio), 2)
    }


if __name__ == "__main__":
    banco = "PostgreSQL" if database.USANDO_POSTGRES else "SQLite"

    print(f"ℹ️ metrics.py carregado com sucesso.")
    print(f"🗄️ Banco detectado: {banco}")