import os

from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    redirect,
    session
)

from dotenv import load_dotenv

from monitor import verificar_url
import config
from metrics import obter_metricas

from database import (
    criar_banco,
    salvar_monitoramento,
    listar_monitoramentos,
    listar_sites,
    buscar_site,
    adicionar_site,
    criar_usuario,
    email_existe,
    buscar_usuario_por_email,
    verificar_senha
)


load_dotenv()


app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY")


criar_banco()


def usuario_logado():
    return session.get("usuario_id")


# ==========================================
# HEALTH CHECK
# ==========================================

@app.route("/health")
def health():
    return jsonify({
        "status": "healthy"
    }), 200


# ==========================================
# HOME
# ==========================================

@app.route("/")
def home():

    if usuario_logado():
        return redirect("/dashboard")

    return redirect("/login")


# ==========================================
# LOGIN
# ==========================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get(
        "email",
        ""
    ).strip().lower()

    senha = request.form.get(
        "senha",
        ""
    )

    usuario = buscar_usuario_por_email(email)

    if usuario is None:

        return render_template(
            "login.html",
            erro="E-mail ou senha incorretos."
        )

    if not verificar_senha(
        senha,
        usuario["senha"]
    ):

        return render_template(
            "login.html",
            erro="E-mail ou senha incorretos."
        )

    session["usuario_id"] = usuario["id"]

    session["usuario_nome"] = usuario["nome"]

    session["usuario_email"] = usuario["email"]

    return redirect("/dashboard")


# ==========================================
# LOGOUT
# ==========================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/login")


# ==========================================
# CADASTRO
# ==========================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "GET":

        return render_template(
            "register.html"
        )

    nome = request.form.get(
        "nome",
        ""
    ).strip()

    email = request.form.get(
        "email",
        ""
    ).strip().lower()

    senha = request.form.get(
        "senha",
        ""
    )

    if not nome or not email or not senha:

        return render_template(
            "register.html",
            erro="Preencha todos os campos."
        )

    if len(senha) < 6:

        return render_template(
            "register.html",
            erro="A senha precisa ter pelo menos 6 caracteres."
        )

    if email_existe(email):

        return render_template(
            "register.html",
            erro="Este e-mail já está cadastrado."
        )

    criar_usuario(
        nome,
        email,
        senha
    )

    return redirect("/login")


# ==========================================
# STATUS DO SITE
# ==========================================

@app.route("/status")
def status():

    usuario_id = usuario_logado()

    if not usuario_id:

        return jsonify({
            "erro": "Não autenticado"
        }), 401

    site_id = request.args.get(
        "site_id",
        default=1,
        type=int
    )

    site = buscar_site(
        site_id,
        usuario_id
    )

    if site is None:

        return jsonify({
            "erro": "Site não encontrado"
        }), 404

    resultado = verificar_url(
        site["url"],
        config.TIMEOUT
    )

    salvar_monitoramento(
        resultado["status"],
        resultado["codigo_http"],
        resultado["tempo_resposta"],
        site_id
    )

    return jsonify({

        "projeto": "Cloud Security Monitor",

        "site_id": site["id"],

        "nome": site["nome"],

        "url": site["url"],

        "status": resultado["status"],

        "codigo_http": resultado["codigo_http"],

        "tempo_resposta_ms": resultado["tempo_resposta"]

    })


# ==========================================
# MÉTRICAS
# ==========================================

@app.route("/metrics")
def metrics():

    usuario_id = usuario_logado()

    if not usuario_id:

        return jsonify({
            "erro": "Não autenticado"
        }), 401

    site_id = request.args.get(
        "site_id",
        default=1,
        type=int
    )

    site = buscar_site(
        site_id,
        usuario_id
    )

    if site is None:

        return jsonify({
            "erro": "Site não encontrado"
        }), 404

    resultado = obter_metricas(
        site_id
    )

    return jsonify(
        resultado
    )


# ==========================================
# HISTÓRICO
# ==========================================

@app.route("/history")
def history():

    usuario_id = usuario_logado()

    if not usuario_id:

        return jsonify({
            "erro": "Não autenticado"
        }), 401

    site_id = request.args.get(
        "site_id",
        default=1,
        type=int
    )

    site = buscar_site(
        site_id,
        usuario_id
    )

    if site is None:

        return jsonify({
            "erro": "Site não encontrado"
        }), 404

    historico = listar_monitoramentos(
        limite=50,
        site_id=site_id
    )

    return jsonify(
        historico
    )


# ==========================================
# LISTAR SITES
# ==========================================

@app.route("/sites")
def sites():

    usuario_id = usuario_logado()

    if not usuario_id:

        return jsonify({
            "erro": "Não autenticado"
        }), 401

    resultado = listar_sites(
        usuario_id
    )

    return jsonify(
        resultado
    )


# ==========================================
# ADICIONAR SITE
# ==========================================

@app.route("/sites", methods=["POST"])
def criar_site():

    usuario_id = usuario_logado()

    if not usuario_id:

        return jsonify({
            "erro": "Não autenticado"
        }), 401

    dados = request.get_json()

    if not dados:

        return jsonify({
            "erro": "JSON não enviado"
        }), 400

    nome = dados.get(
        "nome"
    )

    url = dados.get(
        "url"
    )

    if not nome or not url:

        return jsonify({
            "erro": "Nome e URL são obrigatórios"
        }), 400

    site_id = adicionar_site(
        nome,
        url,
        usuario_id
    )

    return jsonify({

        "mensagem": "Site adicionado com sucesso",

        "site_id": site_id,

        "nome": nome,

        "url": url

    }), 201


# ==========================================
# DASHBOARD
# ==========================================

@app.route("/dashboard")
def dashboard():

    if not usuario_logado():

        return redirect(
            "/login"
        )

    return render_template(
        "dashboard.html"
    )