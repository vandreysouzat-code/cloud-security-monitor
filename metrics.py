total_checks = 0
total_falhas = 0
tempos_resposta = []


def registrar_check(falhou, tempo_resposta):

    global total_checks
    global total_falhas

    total_checks += 1

    if falhou:
        total_falhas += 1

    if tempo_resposta is not None:
        tempos_resposta.append(tempo_resposta)


def obter_metricas():

    if total_checks > 0:

        uptime = (
            (total_checks - total_falhas)
            / total_checks
        ) * 100

    else:

        uptime = 0


    if tempos_resposta:

        tempo_medio = (
            sum(tempos_resposta)
            / len(tempos_resposta)
        )

        maior_tempo = max(tempos_resposta)

    else:

        tempo_medio = 0
        maior_tempo = 0


    return {
        "checks": total_checks,
        "falhas": total_falhas,
        "uptime": uptime,
        "tempo_medio_ms": tempo_medio,
        "maior_tempo_ms": maior_tempo
    }