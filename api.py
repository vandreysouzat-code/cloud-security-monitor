from flask import Flask, jsonify, render_template

from monitor import verificar_url
import config
from metrics import registrar_check, obter_metricas


app = Flask(__name__)


@app.route("/status")
def status():

    resultado = verificar_url(
        config.URL,
        config.TIMEOUT
    )

    registrar_check(
        resultado["status"] != "ONLINE",
        resultado["tempo_resposta"]
    )

    return jsonify({
        "projeto": "Cloud Security Monitor",
        "url": config.URL,
        "status": resultado["status"],
        "codigo_http": resultado["codigo_http"],
        "tempo_resposta_ms": resultado["tempo_resposta"]
    })


@app.route("/metrics")
def metrics():

    resultado = obter_metricas()

    return jsonify(resultado)

@app.route("/dashboard")
def dashboard():

    return render_template("dashboard.html")

if __name__ == "__main__":

    app.run(debug=True)