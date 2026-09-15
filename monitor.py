import socket
import ssl
import time
from urllib.parse import urlparse

import requests


# ============================================================
# CLOUDFLARE DNS OVER HTTPS
# ============================================================

DOH_URL = "https://1.1.1.1/dns-query"


# ============================================================
# RESOLVER DOMÍNIO
# ============================================================

def resolver_dominio(dominio, timeout=5):

    resposta = requests.get(
        DOH_URL,
        params={
            "name": dominio,
            "type": "A"
        },
        headers={
            "Accept": "application/dns-json"
        },
        timeout=timeout
    )

    resposta.raise_for_status()

    dados = resposta.json()

    if dados.get("Status") != 0:
        raise RuntimeError(
            f"Falha na resolução DNS de {dominio}"
        )

    respostas = dados.get(
        "Answer",
        []
    )

    for registro in respostas:

        if registro.get("type") == 1:

            ip = registro.get("data")

            if ip:
                return ip

    raise RuntimeError(
        f"Nenhum endereço IPv4 encontrado para {dominio}"
    )


# ============================================================
# ENVIAR REQUISIÇÃO HTTP
# ============================================================

def enviar_requisicao_http(
    ip,
    dominio,
    porta,
    caminho,
    timeout=5
):

    inicio = time.time()

    conexao = socket.create_connection(
        (ip, porta),
        timeout=timeout
    )

    try:

        requisicao = (
            f"HEAD {caminho} HTTP/1.1\r\n"
            f"Host: {dominio}\r\n"
            f"User-Agent: CloudSecurityMonitor/1.0\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        )

        conexao.sendall(
            requisicao.encode("utf-8")
        )

        resposta = b""

        while b"\r\n" not in resposta:

            parte = conexao.recv(4096)

            if not parte:
                break

            resposta += parte

        tempo_resposta = (
            time.time() - inicio
        ) * 1000

        primeira_linha = resposta.split(
            b"\r\n",
            1
        )[0].decode(
            "iso-8859-1",
            errors="replace"
        )

        partes = primeira_linha.split()

        if len(partes) < 2:

            raise RuntimeError(
                "Resposta HTTP inválida"
            )

        codigo_http = int(
            partes[1]
        )

        return codigo_http, tempo_resposta

    finally:

        conexao.close()


# ============================================================
# ENVIAR REQUISIÇÃO HTTPS
# ============================================================

def enviar_requisicao_https(
    ip,
    dominio,
    caminho,
    timeout=5
):

    inicio = time.time()

    contexto = ssl.create_default_context()

    conexao = socket.create_connection(
        (ip, 443),
        timeout=timeout
    )

    try:

        with contexto.wrap_socket(
            conexao,
            server_hostname=dominio
        ) as conexao_ssl:

            requisicao = (
                f"HEAD {caminho} HTTP/1.1\r\n"
                f"Host: {dominio}\r\n"
                f"User-Agent: CloudSecurityMonitor/1.0\r\n"
                f"Connection: close\r\n"
                f"\r\n"
            )

            conexao_ssl.sendall(
                requisicao.encode("utf-8")
            )

            resposta = b""

            while b"\r\n" not in resposta:

                parte = conexao_ssl.recv(4096)

                if not parte:
                    break

                resposta += parte

            tempo_resposta = (
                time.time() - inicio
            ) * 1000

            primeira_linha = resposta.split(
                b"\r\n",
                1
            )[0].decode(
                "iso-8859-1",
                errors="replace"
            )

            partes = primeira_linha.split()

            if len(partes) < 2:

                raise RuntimeError(
                    "Resposta HTTP inválida"
                )

            codigo_http = int(
                partes[1]
            )

            return codigo_http, tempo_resposta

    finally:

        try:
            conexao.close()
        except Exception:
            pass


# ============================================================
# VERIFICAR URL
# ============================================================

def verificar_url(url, timeout=5):

    inicio_total = time.time()

    try:

        dados_url = urlparse(
            url
        )

        dominio = dados_url.hostname

        if not dominio:

            return {
                "status": "OFFLINE",
                "codigo_http": None,
                "tempo_resposta": None
            }

        if dados_url.scheme not in (
            "http",
            "https"
        ):

            return {
                "status": "OFFLINE",
                "codigo_http": None,
                "tempo_resposta": None
            }

        caminho = (
            dados_url.path
            or "/"
        )

        if dados_url.query:

            caminho += (
                "?"
                + dados_url.query
            )

        # ----------------------------------------------------
        # RESOLVER DOMÍNIO
        # ----------------------------------------------------

        ip = resolver_dominio(
            dominio,
            timeout
        )

        # ----------------------------------------------------
        # HTTP
        # ----------------------------------------------------

        if dados_url.scheme == "http":

            porta = (
                dados_url.port
                or 80
            )

            codigo_http, tempo_resposta = (
                enviar_requisicao_http(
                    ip=ip,
                    dominio=dominio,
                    porta=porta,
                    caminho=caminho,
                    timeout=timeout
                )
            )

        # ----------------------------------------------------
        # HTTPS
        # ----------------------------------------------------

        else:

            if dados_url.port:
                porta = dados_url.port

                if porta != 443:

                    # Para HTTPS em porta diferente,
                    # ainda utilizamos TLS normalmente.

                    pass

            codigo_http, tempo_resposta = (
                enviar_requisicao_https(
                    ip=ip,
                    dominio=dominio,
                    caminho=caminho,
                    timeout=timeout
                )
            )

        # ----------------------------------------------------
        # DETERMINAR STATUS
        # ----------------------------------------------------

        if 200 <= codigo_http < 400:

            status = "ONLINE"

        else:

            status = "OFFLINE"

        tempo_total = (
            time.time() - inicio_total
        ) * 1000

        return {

            "status": status,

            "codigo_http": codigo_http,

            "tempo_resposta": round(
                tempo_total,
                2
            )

        }

    # ========================================================
    # ERROS
    # ========================================================

    except socket.timeout:

        return {
            "status": "OFFLINE",
            "codigo_http": None,
            "tempo_resposta": None
        }

    except ssl.SSLError as erro:

        print(
            f"❌ Erro SSL em {url}: {erro}"
        )

        return {
            "status": "OFFLINE",
            "codigo_http": None,
            "tempo_resposta": None
        }

    except requests.exceptions.RequestException as erro:

        print(
            f"❌ Erro DNS/HTTP em {url}: {erro}"
        )

        return {
            "status": "OFFLINE",
            "codigo_http": None,
            "tempo_resposta": None
        }

    except (ConnectionError, OSError) as erro:

        print(
            f"❌ Erro de conexão em {url}: {erro}"
        )

        return {
            "status": "OFFLINE",
            "codigo_http": None,
            "tempo_resposta": None
        }

    except Exception as erro:

        print(
            f"❌ Erro ao verificar {url}: {erro}"
        )

        return {
            "status": "OFFLINE",
            "codigo_http": None,
            "tempo_resposta": None
        }