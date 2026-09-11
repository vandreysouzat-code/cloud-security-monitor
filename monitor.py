import requests
import time


def verificar_url(url, timeout):

    inicio = time.time()

    try:

        resposta = requests.get(
            url,
            timeout=timeout
        )

        fim = time.time()

        tempo_resposta = (fim - inicio) * 1000

        if resposta.status_code == 200:

            status = "ONLINE"

        else:

            status = "ATENCAO"

        return {
            "status": status,
            "codigo_http": resposta.status_code,
            "tempo_resposta": tempo_resposta
        }

    except requests.exceptions.RequestException:

        return {
            "status": "OFFLINE",
            "codigo_http": None,
            "tempo_resposta": None
        }