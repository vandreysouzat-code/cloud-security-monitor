"""Ponto de entrada para desenvolvimento e hospedagem de instância única."""
import os

from dotenv import load_dotenv
load_dotenv()

from release_integrity import ReleaseIntegrityError, verificar_integridade_release  # noqa: E402

# Pin separado do verificador: a chave precisa coincidir nos pontos de entrada.
OFFICIAL_RELEASE_PUBLIC_KEY_B64 = "FIWhYrETSqIRmVISiPJ7gqdpUde66LFTTsbQvv4dr8E="

try:
    verificar_integridade_release(public_key_b64=OFFICIAL_RELEASE_PUBLIC_KEY_B64)
except ReleaseIntegrityError as exc:
    raise SystemExit(
        "\nERRO DE INTEGRIDADE DO CLOUD SECURITY MONITOR:\n"
        f"{exc}\n"
        "A inicializacao foi interrompida para nao executar uma copia que nao corresponde "
        "a versao oficial assinada.\n"
    ) from exc

from api import app  # noqa: E402
from scheduler import iniciar_monitoramento_automatico  # noqa: E402
from waitress import serve  # noqa: E402


if __name__ == "__main__":
    # A aplicação registra as rotas e inicializa as tabelas ao importar api.py.
    # Use uma única instância deste processo para não duplicar o agendador.
    iniciar_monitoramento_automatico()
    porta = int(os.environ.get("PORT", "5000"))
    threads = int(os.environ.get("WAITRESS_THREADS", "4"))
    # Safer default for a public GitHub project run on a personal computer.
    # Set HOST=0.0.0.0 only intentionally when a deployment requires it.
    host = os.environ.get("HOST", "127.0.0.1")
    print(f"Cloud Security Monitor iniciado em {host}:{porta}")
    serve(app, host=host, port=porta, threads=threads)
