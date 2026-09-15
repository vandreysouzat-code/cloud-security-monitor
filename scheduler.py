import threading
import time
from datetime import datetime

import config

from monitor import verificar_url

from database import (
    listar_todos_sites_admin,
    registrar_monitoramento
)

from alerts import (
    processar_alerta,
    criar_tabela_incidentes
)


INTERVALO_MONITORAMENTO = 60

_monitoramento_iniciado = False

_lock = threading.Lock()


# ==============================================================
# EXECUTAR UM CICLO
# ==============================================================

def executar_monitoramento():

    print()
    print("=" * 60)
    print("🔄 INICIANDO CICLO DE MONITORAMENTO")
    print("=" * 60)

    try:

        sites = listar_todos_sites_admin()

    except Exception as erro:

        print(
            f"❌ Erro ao buscar sites: {erro}"
        )

        return

    if not sites:

        print(
            "ℹ️ Nenhum site cadastrado "
            "para monitoramento."
        )

        return

    print(
        f"🌐 Sites encontrados: {len(sites)}"
    )

    for site in sites:

        site_id = site["id"]

        nome = site["nome"]

        url = site["url"]

        print()
        print("-" * 60)

        print(
            f"🔎 Verificando: {nome}"
        )

        print(
            f"🌐 URL: {url}"
        )

        print(
            f"⏱️ Timeout configurado: "
            f"{config.TIMEOUT} segundos"
        )

        try:

            # ==================================================
            # VERIFICAR SITE
            # ==================================================

            resultado = verificar_url(
                url,
                config.TIMEOUT
            )

            # ==================================================
            # SALVAR MONITORAMENTO
            # ==================================================

            registrar_monitoramento(
                site_id=site_id,
                status=resultado["status"],
                tempo_resposta=(
                    resultado["tempo_resposta"]
                ),
                codigo_http=(
                    resultado["codigo_http"]
                )
            )

            # ==================================================
            # EXIBIR RESULTADO
            # ==================================================

            print(
                f"📊 Status: "
                f"{resultado['status']}"
            )

            print(
                f"📡 HTTP: "
                f"{resultado['codigo_http']}"
            )

            if resultado["tempo_resposta"] is not None:

                print(
                    f"⚡ Resposta: "
                    f"{resultado['tempo_resposta']:.2f} ms"
                )

            # ==================================================
            # PROCESSAR INCIDENTE
            # ==================================================

            try:

                alerta = processar_alerta(
                    site_id
                )

                print(
                    f"🔔 Estado do alerta: "
                    f"{alerta['estado']}"
                )

            except Exception as erro_alerta:

                print(
                    "❌ Erro ao processar alerta: "
                    f"{erro_alerta}"
                )

        except Exception as erro:

            print(
                f"❌ Erro ao verificar "
                f"{url}: {erro}"
            )

    print()
    print("=" * 60)

    print(
        "✅ Ciclo finalizado:",
        datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    )

    print("=" * 60)


# ==============================================================
# LOOP
# ==============================================================

def loop_monitoramento():

    while True:

        try:

            executar_monitoramento()

        except Exception as erro:

            print(
                "❌ Erro no monitoramento "
                f"automático: {erro}"
            )

        print()

        print(
            f"⏱️ Próximo ciclo em "
            f"{INTERVALO_MONITORAMENTO} segundos."
        )

        time.sleep(
            INTERVALO_MONITORAMENTO
        )


# ==============================================================
# INICIAR MONITORAMENTO
# ==============================================================

def iniciar_monitoramento_automatico():

    global _monitoramento_iniciado

    with _lock:

        if _monitoramento_iniciado:

            print(
                "ℹ️ Monitor automático "
                "já está funcionando."
            )

            return

        _monitoramento_iniciado = True

        thread = threading.Thread(
            target=loop_monitoramento,
            daemon=False,
            name="CloudSecurityMonitor"
        )

        thread.start()

        print()
        print("=" * 60)

        print(
            "🚀 MONITORAMENTO AUTOMÁTICO INICIADO"
        )

        print(
            f"⏱️ Timeout: "
            f"{config.TIMEOUT} segundos"
        )

        print(
            f"⏱️ Intervalo entre ciclos: "
            f"{INTERVALO_MONITORAMENTO} segundos"
        )

        print("=" * 60)
        print()


# ==============================================================
# EXECUÇÃO DIRETA
# ==============================================================

if __name__ == "__main__":

    criar_tabela_incidentes()

    iniciar_monitoramento_automatico()

    try:

        while True:

            time.sleep(1)

    except KeyboardInterrupt:

        print()
        print(
            "🛑 Monitoramento encerrado "
            "pelo usuário."
        )