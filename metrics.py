import sqlite3

from database import DATABASE


def obter_metricas(site_id=1):

    conexao = sqlite3.connect(
        DATABASE
    )

    cursor = conexao.cursor()


    cursor.execute("""
        SELECT COUNT(*)
        FROM monitoramentos
        WHERE site_id = ?
    """, (
        site_id,
    ))


    checks = cursor.fetchone()[0]


    cursor.execute("""
        SELECT COUNT(*)
        FROM monitoramentos
        WHERE site_id = ?
        AND status != 'ONLINE'
    """, (
        site_id,
    ))


    falhas = cursor.fetchone()[0]


    cursor.execute("""
        SELECT
            AVG(tempo_resposta),
            MAX(tempo_resposta)
        FROM monitoramentos
        WHERE site_id = ?
        AND tempo_resposta IS NOT NULL
    """, (
        site_id,
    ))


    resultado = cursor.fetchone()


    tempo_medio = resultado[0]

    maior_tempo = resultado[1]


    conexao.close()


    if tempo_medio is None:
        tempo_medio = 0


    if maior_tempo is None:
        maior_tempo = 0


    if checks > 0:

        uptime = (
            (checks - falhas)
            / checks
        ) * 100

    else:

        uptime = 0


    return {

        "checks":
            checks,

        "falhas":
            falhas,

        "uptime":
            uptime,

        "tempo_medio_ms":
            tempo_medio,

        "maior_tempo_ms":
            maior_tempo

    }