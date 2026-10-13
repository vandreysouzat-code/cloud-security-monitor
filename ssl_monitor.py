import socket
import ssl
from datetime import datetime
from urllib.parse import urlsplit

import requests

from url_safety import exigir_ip_publico, validar_url_publica


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

    ips = [
        item.get("data")
        for item in respostas
        if item.get("type") == 1 and item.get("data")
    ]

    if not ips:
        raise ValueError(
            f"Não foi possível encontrar o endereço IP de {dominio}"
        )

    ips_publicos = [exigir_ip_publico(ip) for ip in ips]
    return ips_publicos[0]


# ============================================================
# VERIFICAR CERTIFICADO SSL
# ============================================================

def verificar_ssl(url):

    url = validar_url_publica(url)
    parsed = urlsplit(url)
    dominio = (parsed.hostname or "").rstrip(".").lower()

    if parsed.scheme != "https":
        raise ValueError("A verificação SSL exige uma URL HTTPS.")

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