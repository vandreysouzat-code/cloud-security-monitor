from database import conectar


def obter_metricas(site_id):

    conexao = conectar()

    cursor = conexao.cursor()

    cursor.execute(
        """
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

        WHERE site_id = ?
        """,
        (site_id,)
    )

    resultado = cursor.fetchone()

    conexao.close()

    total = resultado["total"] or 0

    online = resultado["online"] or 0

    offline = resultado["offline"] or 0

    tempo_medio = resultado["tempo_medio"] or 0


    # ========================================================
    # DISPONIBILIDADE
    # ========================================================

    if total > 0:

        disponibilidade = (
            online / total
        ) * 100

    else:

        disponibilidade = 0


    # ========================================================
    # RESULTADO
    # ========================================================

    return {

        "total_verificacoes":
            total,

        "online":
            online,

        "offline":
            offline,

        "disponibilidade":
            round(
                disponibilidade,
                2
            ),

        "tempo_medio_ms":
            round(
                tempo_medio,
                2
            )

    }