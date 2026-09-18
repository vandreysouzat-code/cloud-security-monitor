import threading
import time
from datetime import datetime

import config

from monitor import verificar_url
from ssl_monitor import verificar_ssl
from ssl_alerts import analisar_expiracao_ssl

from database import (
    listar_todos_sites_admin,
    registrar_monitoramento,
    salvar_ssl_monitoramento
)

from alerts import (
    processar_alerta,
    criar_tabela_incidentes
)

from ssl_alert_manager import (
    criar_tabela_ssl_alertas,
    criar_alerta_ssl,
    desativar_alertas_ssl
)


INTERVALO_MONITORAMENTO = 60

_monitoramento_iniciado = False
_lock = threading.Lock()


def executar_monitoramento():

    print()
    print("=" * 60)
    print("🔄 INICIANDO CICLO DE MONITORAMENTO")
    print("=" * 60)

    try:

        sites = listar_todos_sites_admin()

    except Exception as erro:

        print(f"❌ Erro ao buscar sites: {erro}")

        return

    if not sites:

        print("ℹ️ Nenhum site cadastrado para monitoramento.")

        return

    print(f"🌐 Sites encontrados: {len(sites)}")

    for site in sites:

        site_id = site["id"]
        nome = site["nome"]
        url = site["url"]

        print()
        print("-" * 60)

        print(f"🔎 Verificando: {nome}")
        print(f"🌐 URL: {url}")
        print(f"⏱️ Timeout configurado: {config.TIMEOUT} segundos")

        # ==========================================================
        # MONITORAMENTO HTTP/HTTPS
        # ==========================================================

        try:

            resultado = verificar_url(
                url,
                config.TIMEOUT
            )

            registrar_monitoramento(
                site_id=site_id,
                status=resultado["status"],
                tempo_resposta=resultado["tempo_resposta"],
                codigo_http=resultado["codigo_http"]
            )

            print(f"📊 Status: {resultado['status']}")
            print(f"📡 HTTP: {resultado['codigo_http']}")

            if resultado["tempo_resposta"] is not None:

                print(
                    f"⚡ Resposta: "
                    f"{resultado['tempo_resposta']:.2f} ms"
                )

            # ======================================================
            # ALERTAS / INCIDENTES
            # ======================================================

            try:

                alerta = processar_alerta(site_id)

                print(
                    f"🔔 Estado do alerta: "
                    f"{alerta['estado']}"
                )

            except Exception as erro_alerta:

                print(
                    f"❌ Erro ao processar alerta: "
                    f"{erro_alerta}"
                )

        except Exception as erro:

            print(
                f"❌ Erro ao verificar "
                f"{url}: {erro}"
            )

        # ==========================================================
        # MONITORAMENTO SSL
        # ==========================================================

        if url.lower().startswith("https://"):

            print()
            print("🔐 Verificando certificado SSL...")

            try:

                ssl_resultado = verificar_ssl(url)

                salvar_ssl_monitoramento(
                    site_id=site_id,
                    dominio=ssl_resultado["dominio"],
                    ip=ssl_resultado["ip"],
                    valido=ssl_resultado["valido"],
                    data_expiracao=ssl_resultado["data_expiracao"],
                    dias_restantes=ssl_resultado["dias_restantes"]
                )

                print(
                    f"🔐 SSL válido: "
                    f"{ssl_resultado['valido']}"
                )

                print(
                    f"🌐 IP: "
                    f"{ssl_resultado['ip']}"
                )

                print(
                    f"📅 Expira em: "
                    f"{ssl_resultado['data_expiracao']}"
                )

                print(
                    f"⏳ Dias restantes: "
                    f"{ssl_resultado['dias_restantes']}"
                )

                # ==================================================
                # ANÁLISE INTELIGENTE DE EXPIRAÇÃO SSL
                # ==================================================

                ssl_alerta = analisar_expiracao_ssl(
                    ssl_resultado["dias_restantes"]
                )

                print(
                    f"🛡️ Nível SSL: "
                    f"{ssl_alerta['nivel']}"
                )

                print(
                    f"📢 {ssl_alerta['mensagem']}"
                )

                # ==================================================
                # GERENCIAMENTO DE ALERTA SSL
                # ==================================================

                if ssl_alerta["nivel"] == "NORMAL":

                    quantidade_desativada = (
                        desativar_alertas_ssl(site_id)
                    )

                    if quantidade_desativada > 0:

                        print(
                            f"🟢 Alertas SSL anteriores "
                            f"desativados: "
                            f"{quantidade_desativada}"
                        )

                else:

                    resultado_alerta_ssl = criar_alerta_ssl(
                        site_id=site_id,
                        nivel=ssl_alerta["nivel"],
                        dias_restantes=ssl_resultado["dias_restantes"],
                        mensagem=ssl_alerta["mensagem"]
                    )

                    if resultado_alerta_ssl["criado"]:

                        print(
                            "🚨 Novo alerta SSL registrado."
                        )

                    else:

                        print(
                            "ℹ️ Alerta SSL já registrado "
                            "para este nível."
                        )

            except Exception as erro_ssl:

                print(
                    f"⚠️ Erro na verificação SSL: "
                    f"{erro_ssl}"
                )

        else:

            print()
            print("ℹ️ Site HTTP — verificação SSL ignorada.")

    print()
    print("=" * 60)

    print(
        "✅ Ciclo finalizado:",
        datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    )

    print("=" * 60)


def loop_monitoramento():

    while True:

        try:

            executar_monitoramento()

        except Exception as erro:

            print(
                f"❌ Erro no monitoramento automático: "
                f"{erro}"
            )

        print()

        print(
            f"⏱️ Próximo ciclo em "
            f"{INTERVALO_MONITORAMENTO} segundos."
        )

        time.sleep(
            INTERVALO_MONITORAMENTO
        )


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


if __name__ == "__main__":

    criar_tabela_incidentes()
    criar_tabela_ssl_alertas()

    iniciar_monitoramento_automatico()

    try:

        while True:

            time.sleep(1)

    except KeyboardInterrupt:

        print()
        print(
            "🛑 Monitoramento encerrado pelo usuário."
        )
