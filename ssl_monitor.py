import socket
import ssl
from datetime import datetime

import requests


# ============================================================
# CLOUDFLARE DNS OVER HTTPS
# ============================================================

DOH_URL = "https://1.1.1.1/dns-query"


# ============================================================
# RESOLVER DOMÍNIO
# ============================================================

def resolver_dominio(dominio):

    resposta = requests.get(
        DOH_URL,
        params={
            "name": dominio,
            "type": "A"
        },
        headers={
            "Accept": "application/dns-json"
        },
        timeout=10
    )

    resposta.raise_for_status()

    dados = resposta.json()

    if dados.get("Status") != 0:
        raise ValueError(
            f"Não foi possível resolver o domínio {dominio}"
        )

    respostas = dados.get(
        "Answer",
        []
    )

    for resposta_dns in respostas:

        if resposta_dns.get("type") == 1:

            ip = resposta_dns.get(
                "data"
            )

            if ip:
                return ip

    raise ValueError(
        f"Não foi possível encontrar o endereço IP de {dominio}"
    )


# ============================================================
# VERIFICAR CERTIFICADO SSL
# ============================================================

def verificar_ssl(url):

    dominio = (
        url
        .replace("https://", "")
        .replace("http://", "")
        .split("/")[0]
        .split(":")[0]
        .strip()
        .lower()
    )

    if not dominio:
        raise ValueError(
            "Domínio inválido"
        )

    # --------------------------------------------------------
    # RESOLVER DOMÍNIO
    # --------------------------------------------------------

    ip = resolver_dominio(
        dominio
    )

    # --------------------------------------------------------
    # CRIAR CONTEXTO SSL
    # --------------------------------------------------------

    contexto = ssl.create_default_context()

    inicio = datetime.now()

    # --------------------------------------------------------
    # CONECTAR AO SERVIDOR
    # --------------------------------------------------------

    with socket.create_connection(
        (ip, 443),
        timeout=10
    ) as conexao:

        with contexto.wrap_socket(
            conexao,
            server_hostname=dominio
        ) as conexao_ssl:

            certificado = (
                conexao_ssl.getpeercert()
            )

    fim = datetime.now()

    # --------------------------------------------------------
    # TEMPO DE RESPOSTA
    # --------------------------------------------------------

    tempo_resposta = (
        fim - inicio
    ).total_seconds() * 1000

    # --------------------------------------------------------
    # DATA DE EXPIRAÇÃO
    # --------------------------------------------------------

    data_expiracao = certificado.get(
        "notAfter"
    )

    if not data_expiracao:
        raise ValueError(
            "O certificado não possui data de expiração"
        )

    data_expiracao = datetime.strptime(
        data_expiracao,
        "%b %d %H:%M:%S %Y %Z"
    )

    # --------------------------------------------------------
    # DIAS RESTANTES
    # --------------------------------------------------------

    dias_restantes = (
        data_expiracao - datetime.now()
    ).days

    # --------------------------------------------------------
    # RESULTADO
    # --------------------------------------------------------

    return {
        "dominio": dominio,
        "ip": ip,
        "valido": True,
        "data_expiracao": data_expiracao.strftime(
            "%Y-%m-%d"
        ),
        "dias_restantes": dias_restantes,
        "tempo_resposta": round(
            tempo_resposta,
            2
        )
    }