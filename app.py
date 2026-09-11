import time
from datetime import datetime

import config

from monitor import verificar_url
from logger import salvar_monitor, salvar_seguranca
from security import verificar_alerta


# ==========================
# CONTROLE DE FALHAS
# ==========================

falhas_consecutivas = 0


# ==========================
# ESTADO DO SISTEMA
# ==========================

estado_anterior = "NORMAL"


# ==========================
# MÉTRICAS
# ==========================

total_checks = 0
total_falhas = 0
tempos_resposta = []


# ==========================
# MONITORAMENTO
# ==========================

while True:

    agora = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    total_checks += 1


    # ==========================
    # VERIFICA URL
    # ==========================

    resultado = verificar_url(
        config.URL,
        config.TIMEOUT
    )


    status = resultado["status"]

    codigo_http = resultado["codigo_http"]

    tempo_resposta = resultado["tempo_resposta"]


    # ==========================
    # CONTROLE DE FALHAS
    # ==========================

    if status == "ONLINE":

        falhas_consecutivas = 0

    else:

        falhas_consecutivas += 1
        total_falhas += 1


    # ==========================
    # MÉTRICAS DE RESPOSTA
    # ==========================

    if tempo_resposta is not None:

        tempos_resposta.append(
            tempo_resposta
        )


    # ==========================
    # MENSAGEM DO MONITOR
    # ==========================

    if codigo_http is not None:

        mensagem = (
            f"{agora} | {config.URL} | "
            f"{status} | HTTP {codigo_http} | "
            f"{tempo_resposta:.2f} ms"
        )

    else:

        mensagem = (
            f"{agora} | {config.URL} | "
            f"OFFLINE"
        )


    print(mensagem)

    salvar_monitor(mensagem)


    # ==========================
    # ALERTAS
    # ==========================

    tipo_alerta = verificar_alerta(
        falhas_consecutivas,
        estado_anterior,
        config.LIMITE_FALHAS
    )


    if tipo_alerta == "WARNING":

        alerta = (
            f"{agora} | WARNING | "
            f"Primeira falha detectada"
        )

        print("⚠️ " + alerta)

        salvar_seguranca(alerta)

        estado_anterior = "WARNING"


    elif tipo_alerta == "CRITICAL":

        alerta = (
            f"{agora} | CRITICAL | "
            f"{falhas_consecutivas} "
            f"falhas consecutivas"
        )

        print("🚨 " + alerta)

        salvar_seguranca(alerta)

        estado_anterior = "CRITICAL"


    elif tipo_alerta == "RECOVERY":

        alerta = (
            f"{agora} | RECOVERY | "
            f"Serviço voltou ao normal"
        )

        print("✅ " + alerta)

        salvar_seguranca(alerta)

        estado_anterior = "NORMAL"


    # ==========================
    # MÉTRICAS
    # ==========================

    if total_checks > 0:

        uptime = (
            (total_checks - total_falhas)
            / total_checks
        ) * 100

    else:

        uptime = 0


    if tempos_resposta:

        media_resposta = (
            sum(tempos_resposta)
            / len(tempos_resposta)
        )

        maior_resposta = max(
            tempos_resposta
        )

    else:

        media_resposta = 0
        maior_resposta = 0


    # ==========================
    # EXIBE MÉTRICAS
    # ==========================

    print()
    print("----- METRICAS -----")
    print(f"Checks: {total_checks}")
    print(f"Falhas: {total_falhas}")
    print(f"Uptime: {uptime:.2f}%")
    print(
        f"Tempo medio: "
        f"{media_resposta:.2f} ms"
    )
    print(
        f"Maior tempo: "
        f"{maior_resposta:.2f} ms"
    )
    print("--------------------")
    print()


    time.sleep(config.INTERVALO)