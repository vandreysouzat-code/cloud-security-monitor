import os
import ipaddress
import requests
import secrets

from datetime import timedelta
from functools import wraps
from urllib.parse import urlparse

from flask import (
    Flask,
    jsonify,
    request,
    session,
    redirect,
    url_for,
    render_template
)

from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash

from database import (
    criar_banco,
    criar_usuario,
    buscar_usuario_por_email,
    buscar_usuario_por_id,
    listar_usuarios,
    alterar_usuario_admin,
    criar_site,
    listar_sites,
    buscar_site,
    excluir_site,
    listar_monitoramentos,
    listar_ssl,
    listar_todos_sites_admin,
    listar_todos_ssl_admin,
    registrar_auditoria,
    listar_auditoria
)

from metrics import obter_metricas

from alerts import (
    listar_incidentes
)

from scheduler import (
    iniciar_monitoramento_automatico
)


# ============================================================
# CONFIGURAÇÃO
# ============================================================

app = Flask(
    __name__,
    template_folder="templates"
)


# ------------------------------------------------------------
# AMBIENTE
# ------------------------------------------------------------

PRODUCAO = (
    os.environ.get("FLASK_ENV") == "production"
    or os.environ.get("RENDER") == "true"
)


# ------------------------------------------------------------
# SECRET KEY
# ------------------------------------------------------------

SECRET_KEY = os.environ.get("SECRET_KEY")


if not SECRET_KEY:

    if PRODUCAO:

        raise RuntimeError(
            "SECRET_KEY não configurada no ambiente de produção."
        )

    SECRET_KEY = "chave-local-desenvolvimento"


app.secret_key = SECRET_KEY


# ------------------------------------------------------------
# PROXY
# ------------------------------------------------------------
#
# O Render fica na frente da aplicação.
#
# x_for=1:
#   considera um proxy confiável imediatamente à frente.
#
# x_proto=1:
#   permite que Flask saiba que a requisição original
#   chegou por HTTPS.
#
# x_host=1:
#   preserva o host original informado pelo proxy.
#
# IMPORTANTE:
# Não usamos mais manualmente X-Forwarded-For.
# O Flask/Werkzeug passa a tratar isso através do ProxyFix.
#

app.wsgi_app = ProxyFix(
    app.wsgi_app,
    x_for=1,
    x_proto=1,
    x_host=1
)


# ------------------------------------------------------------
# SESSÃO
# ------------------------------------------------------------

app.config.update(

    SECRET_KEY=SECRET_KEY,

    SESSION_COOKIE_NAME="csm_session",

    SESSION_COOKIE_HTTPONLY=True,

    SESSION_COOKIE_SAMESITE="Lax",

    SESSION_COOKIE_SECURE=PRODUCAO,

    SESSION_REFRESH_EACH_REQUEST=True,

    PERMANENT_SESSION_LIFETIME=timedelta(
        hours=12
    ),

    MAX_CONTENT_LENGTH=1 * 1024 * 1024

)


# ============================================================
# CLOUDFLARE DNS OVER HTTPS
# ============================================================

DOH_URL = "https://1.1.1.1/dns-query"


# ============================================================
# BANCO
# ============================================================

criar_banco()


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

# ============================================================
# PROTEÇÃO CSRF
# ============================================================

METODOS_QUE_EXIGEM_CSRF = {
    "POST",
    "PUT",
    "PATCH",
    "DELETE"
}


def obter_token_csrf():

    token = session.get(
        "csrf_token"
    )

    if not token:

        token = secrets.token_urlsafe(32)

        session["csrf_token"] = token

    return token


def validar_csrf():

    if request.method not in METODOS_QUE_EXIGEM_CSRF:

        return True


    if request.path in (
        "/login",
        "/register"
    ):

        return True


    token_sessao = session.get(
        "csrf_token"
    )


    token_requisicao = request.headers.get(
        "X-CSRF-Token"
    )


    if not token_sessao or not token_requisicao:

        return False


    return secrets.compare_digest(
        token_sessao,
        token_requisicao
    )


def usuario_logado():

    usuario_id = session.get(
        "usuario_id"
    )

    if not usuario_id:

        return None


    usuario = buscar_usuario_por_id(
        usuario_id
    )


    if not usuario:

        session.clear()

        return None


    if not usuario["ativo"]:

        session.clear()

        return None


    return usuario


def obter_ip():

    # --------------------------------------------------------
    # O endereço agora vem do Flask/Werkzeug depois do
    # processamento seguro do proxy.
    # --------------------------------------------------------

    ip = request.remote_addr


    if not ip:

        return ""


    return ip.strip()


def registrar_log(
    usuario_id,
    acao,
    descricao=None,
    detalhes=None
):

    try:

        registrar_auditoria(
            usuario_id=usuario_id,
            acao=acao,
            descricao=descricao,
            detalhes=detalhes,
            ip=obter_ip()
        )

    except Exception as erro:

        print(
            f"⚠️ Erro ao registrar auditoria: {erro}"
        )


def resposta_erro_api(
    mensagem,
    status
):

    return jsonify({

        "erro": mensagem

    }), status


# ============================================================
# PROTEÇÃO CSRF - BEFORE REQUEST
# ============================================================

@app.before_request
def proteger_contra_csrf():

    if validar_csrf():

        return None


    if (
        request.path.startswith("/api/")
        or request.path.startswith("/admin/")
        or request.path in (
            "/logout",
            "/login",
            "/register"
        )
    ):

        return resposta_erro_api(
            "Token CSRF inválido ou ausente.",
            403
        )


    return (
        "Token CSRF inválido ou ausente.",
        403
    )


# ============================================================
# VERIFICAR SE UM IP É PERMITIDO
# ============================================================

def ip_e_permitido(ip):

    try:

        endereco_ip = ipaddress.ip_address(
            ip
        )

    except ValueError:

        return False


    if (
        endereco_ip.is_private
        or endereco_ip.is_loopback
        or endereco_ip.is_link_local
        or endereco_ip.is_reserved
        or endereco_ip.is_multicast
        or endereco_ip.is_unspecified
    ):

        return False


    return True


# ============================================================
# RESOLVER DOMÍNIO COM CLOUDFLARE DOH
# ============================================================

def resolver_enderecos_publicos(
    dominio,
    timeout=5
):

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

        raise ValueError(
            "Não foi possível resolver o domínio."
        )


    respostas = dados.get(
        "Answer",
        []
    )


    ips = []


    for registro in respostas:

        if registro.get("type") != 1:

            continue


        endereco = registro.get(
            "data"
        )


        if not endereco:

            continue


        try:

            endereco_ip = ipaddress.ip_address(
                endereco
            )

        except ValueError:

            continue


        if not ip_e_permitido(
            endereco_ip
        ):

            raise ValueError(
                "O domínio resolve para uma rede não permitida."
            )


        ips.append(
            str(endereco_ip)
        )


    if not ips:

        raise ValueError(
            "Não foi possível encontrar um endereço IPv4 público para o domínio."
        )


    return list(
        dict.fromkeys(ips)
    )


# ============================================================
# VALIDAÇÃO DE URL
# ============================================================

def validar_url_monitoramento(url):

    if not isinstance(url, str):

        return False, "URL inválida."


    url = url.strip()


    if len(url) > 2048:

        return False, "A URL é muito longa."


    try:

        partes = urlparse(
            url
        )

    except Exception:

        return False, "URL inválida."


    if partes.scheme not in (
        "http",
        "https"
    ):

        return (
            False,
            "A URL deve começar com http:// ou https://"
        )


    if not partes.hostname:

        return (
            False,
            "A URL não possui um domínio válido."
        )


    hostname = partes.hostname.strip().lower()


    # --------------------------------------------------------
    # VALIDAR PORTA
    # --------------------------------------------------------

    try:

        porta = partes.port

    except ValueError:

        return (
            False,
            "A porta informada na URL é inválida."
        )


    if porta is not None:

        if porta < 1 or porta > 65535:

            return (
                False,
                "A porta informada é inválida."
            )


    # --------------------------------------------------------
    # ENDEREÇOS LOCAIS
    # --------------------------------------------------------

    if hostname in (
        "localhost",
        "localhost.localdomain"
    ):

        return (
            False,
            "Este endereço não pode ser monitorado."
        )


    if hostname.endswith(
        ".local"
    ):

        return (
            False,
            "Domínios locais não podem ser monitorados."
        )


    if hostname == "metadata.google.internal":

        return (
            False,
            "Este endereço não pode ser monitorado."
        )


    # --------------------------------------------------------
    # SE FOR IP DIRETO
    # --------------------------------------------------------

    try:

        endereco_ip = ipaddress.ip_address(
            hostname
        )


        if not ip_e_permitido(
            endereco_ip
        ):

            return (
                False,
                "Endereços de rede interna não podem ser monitorados."
            )


        return True, None


    except ValueError:

        pass


    # --------------------------------------------------------
    # SE FOR DOMÍNIO
    # --------------------------------------------------------

    try:

        resolver_enderecos_publicos(
            hostname
        )


    except requests.exceptions.RequestException:

        return (
            False,
            "Não foi possível validar o domínio agora."
        )


    except ValueError as erro:

        return (
            False,
            str(erro)
        )


    except Exception as erro:

        print(
            f"❌ Erro ao validar domínio {hostname}: {erro}"
        )

        return (
            False,
            "Não foi possível validar a URL."
        )


    return True, None


# ============================================================
# DECORATOR LOGIN
# ============================================================

def login_required(func):

    @wraps(func)
    def wrapper(*args, **kwargs):

        usuario = usuario_logado()


        if not usuario:

            if request.path.startswith(
                "/api/"
            ):

                return resposta_erro_api(
                    "Não autenticado.",
                    401
                )


            return redirect(
                url_for("login")
            )


        return func(
            *args,
            **kwargs
        )


    return wrapper


# ============================================================
# DECORATOR ADMIN
# ============================================================

def admin_required(func):

    @wraps(func)
    def wrapper(*args, **kwargs):

        usuario = usuario_logado()


        if not usuario:

            if request.path.startswith(
                "/api/"
            ):

                return resposta_erro_api(
                    "Não autenticado.",
                    401
                )


            return redirect(
                url_for("login")
            )


        if usuario["role"] != "admin":

            if request.path.startswith(
                "/api/"
            ):

                return resposta_erro_api(
                    "Acesso negado.",
                    403
                )


            return redirect(
                url_for("dashboard")
            )


        return func(
            *args,
            **kwargs
        )


    return wrapper


# ============================================================
# HOME
# ============================================================

@app.route("/")
def index():

    usuario = usuario_logado()


    if usuario:

        return redirect(
            url_for("dashboard")
        )


    return redirect(
        url_for("login")
    )


# ============================================================
# LOGIN
# ============================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "GET":

        usuario = usuario_logado()


        if usuario:

            return redirect(
                url_for("dashboard")
            )


        return render_template(
            "login.html"
        )


    dados = request.get_json(
        silent=True
    )


    if dados:

        email = (
            dados.get("email")
            or ""
        ).strip().lower()


        senha = (
            dados.get("senha")
            or ""
        )


    else:

        email = (
            request.form.get("email")
            or ""
        ).strip().lower()


        senha = (
            request.form.get("senha")
            or ""
        )


    if not email or not senha:

        return resposta_erro_api(
            "Informe email e senha.",
            400
        )


    usuario = buscar_usuario_por_email(
        email
    )


    if not usuario:

        return resposta_erro_api(
            "Email ou senha inválidos.",
            401
        )


    if not usuario["ativo"]:

        return resposta_erro_api(
            "Email ou senha inválidos.",
            401
        )


    if not check_password_hash(
        usuario["senha"],
        senha
    ):

        return resposta_erro_api(
            "Email ou senha inválidos.",
            401
        )


    session.clear()


    session.permanent = True


    session["csrf_token"] = secrets.token_urlsafe(32)


    session["usuario_id"] = usuario["id"]


    session["usuario_nome"] = usuario["nome"]


    session["usuario_role"] = usuario["role"]


    registrar_log(
        usuario["id"],
        "LOGIN",
        "Usuário realizou login."
    )


    return jsonify({

        "sucesso": True,

        "mensagem":
            "Login realizado com sucesso.",

        "usuario": {

            "id":
                usuario["id"],

            "nome":
                usuario["nome"],

            "email":
                usuario["email"],

            "role":
                usuario["role"]

        }

    })


# ============================================================
# REGISTRO
# ============================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if request.method == "GET":

        usuario = usuario_logado()


        if usuario:

            return redirect(
                url_for("dashboard")
            )


        return render_template(
            "register.html"
        )


    dados = request.get_json(
        silent=True
    ) or {}


    if dados:

        nome = (
            dados.get("nome")
            or ""
        ).strip()


        email = (
            dados.get("email")
            or ""
        ).strip().lower()


        senha = (
            dados.get("senha")
            or ""
        )


    else:

        nome = (
            request.form.get("nome")
            or ""
        ).strip()


        email = (
            request.form.get("email")
            or ""
        ).strip().lower()


        senha = (
            request.form.get("senha")
            or ""
        )


    if not nome:

        return resposta_erro_api(
            "Informe seu nome.",
            400
        )


    if len(nome) > 120:

        return resposta_erro_api(
            "O nome é muito longo.",
            400
        )


    if not email:

        return resposta_erro_api(
            "Informe seu email.",
            400
        )


    if len(email) > 254 or "@" not in email:

        return resposta_erro_api(
            "Informe um email válido.",
            400
        )


    if not senha:

        return resposta_erro_api(
            "Informe sua senha.",
            400
        )


    if len(senha) < 8:

        return resposta_erro_api(
            "A senha deve possuir pelo menos 8 caracteres.",
            400
        )


    if len(senha) > 128:

        return resposta_erro_api(
            "A senha é muito longa.",
            400
        )


    existente = buscar_usuario_por_email(
        email
    )


    if existente:

        return resposta_erro_api(
            "Este email já está cadastrado.",
            409
        )


    try:

        usuario_id = criar_usuario(
            nome,
            email,
            senha
        )


    except Exception as erro:

        print(
            f"❌ Erro ao criar usuário: {erro}"
        )


        return resposta_erro_api(
            "Não foi possível criar o usuário.",
            500
        )


    registrar_log(
        usuario_id,
        "REGISTRO",
        "Novo usuário criado."
    )


    return jsonify({

        "sucesso": True,

        "mensagem":
            "Usuário criado com sucesso.",

        "usuario_id":
            usuario_id

    }), 201


# ============================================================
# LOGOUT
# ============================================================

@app.route(
    "/logout",
    methods=["GET", "POST"]
)
def logout():

    usuario = usuario_logado()


    if usuario:

        registrar_log(
            usuario["id"],
            "LOGOUT",
            "Usuário encerrou a sessão."
        )


    session.clear()


    if request.method == "POST":

        return jsonify({

            "sucesso": True

        })


    return redirect(
        url_for("login")
    )


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
@login_required
def dashboard():

    return render_template(
        "dashboard.html"
    )


# ============================================================
# API - TOKEN CSRF
# ============================================================

@app.route(
    "/api/csrf-token",
    methods=["GET"]
)
@login_required
def api_csrf_token():

    token = obter_token_csrf()

    return jsonify({

        "csrf_token":
            token

    })


# ============================================================
# API - USUÁRIO ATUAL
# ============================================================

@app.route("/api/me")
@login_required
def api_me():

    usuario = usuario_logado()


    return jsonify({

        "id":
            usuario["id"],

        "nome":
            usuario["nome"],

        "email":
            usuario["email"],

        "role":
            usuario["role"],

        "ativo":
            usuario["ativo"]

    })


# ============================================================
# SITES DO USUÁRIO
# ============================================================

@app.route(
    "/api/sites",
    methods=["GET"]
)
@login_required
def api_listar_sites():

    usuario = usuario_logado()


    sites = listar_sites(
        usuario["id"]
    )


    return jsonify([

        dict(site)

        for site in sites

    ])


# ============================================================
# CRIAR SITE
# ============================================================

@app.route(
    "/api/sites",
    methods=["POST"]
)
@login_required
def api_criar_site():

    usuario = usuario_logado()


    dados = request.get_json(
        silent=True
    ) or {}


    nome = (
        dados.get("nome")
        or ""
    ).strip()


    url = (
        dados.get("url")
        or ""
    ).strip()


    if not nome:

        return resposta_erro_api(
            "Informe o nome do site.",
            400
        )


    if len(nome) > 120:

        return resposta_erro_api(
            "O nome do site é muito longo.",
            400
        )


    if not url:

        return resposta_erro_api(
            "Informe a URL do site.",
            400
        )


    valida, erro = validar_url_monitoramento(
        url
    )


    if not valida:

        return resposta_erro_api(
            erro,
            400
        )


    try:

        site_id = criar_site(
            usuario["id"],
            nome,
            url
        )


    except Exception as erro:

        print(
            f"❌ Erro ao criar site: {erro}"
        )


        return resposta_erro_api(
            "Não foi possível cadastrar o site.",
            500
        )


    registrar_log(
        usuario["id"],
        "CRIAR_SITE",
        f"Site criado: {nome}"
    )


    return jsonify({

        "sucesso": True,

        "site_id":
            site_id,

        "mensagem":
            "Site cadastrado com sucesso."

    }), 201


# ============================================================
# BUSCAR SITE
# ============================================================

@app.route(
    "/api/sites/<int:site_id>",
    methods=["GET"]
)
@login_required
def api_buscar_site(site_id):

    usuario = usuario_logado()


    site = buscar_site(
        site_id,
        usuario["id"]
    )


    if not site:

        return resposta_erro_api(
            "Site não encontrado.",
            404
        )


    return jsonify(
        dict(site)
    )


# ============================================================
# STATUS DO SITE
# ============================================================

@app.route(
    "/api/sites/<int:site_id>/status",
    methods=["GET"]
)
@login_required
def api_status_site(site_id):

    usuario = usuario_logado()


    site = buscar_site(
        site_id,
        usuario["id"]
    )


    if not site:

        return resposta_erro_api(
            "Site não encontrado.",
            404
        )


    registros = listar_monitoramentos(
        site_id
    )


    ultimo = None


    if registros:

        ultimo = dict(
            registros[0]
        )


    resposta = {

        "site_id":
            site["id"],

        "nome":
            site["nome"],

        "url":
            site["url"],

        "status":
            "AGUARDANDO",

        "codigo_http":
            None,

        "tempo_resposta":
            None,

        "data_hora":
            None

    }


    if ultimo:

        resposta.update({

            "status":
                ultimo.get(
                    "status"
                ),

            "codigo_http":
                ultimo.get(
                    "codigo_http"
                ),

            "tempo_resposta":
                ultimo.get(
                    "tempo_resposta"
                ),

            "data_hora":
                ultimo.get(
                    "data_hora"
                )

        })


    return jsonify(
        resposta
    )


# ============================================================
# EXCLUIR SITE
# ============================================================

@app.route(
    "/api/sites/<int:site_id>",
    methods=["DELETE"]
)
@login_required
def api_excluir_site(site_id):

    usuario = usuario_logado()


    site = buscar_site(
        site_id,
        usuario["id"]
    )


    if not site:

        return resposta_erro_api(
            "Site não encontrado.",
            404
        )


    excluido = excluir_site(
        site_id,
        usuario["id"]
    )


    if not excluido:

        return resposta_erro_api(
            "Não foi possível excluir o site.",
            500
        )


    registrar_log(
        usuario["id"],
        "EXCLUIR_SITE",
        f"Site excluído: {site['nome']}"
    )


    return jsonify({

        "sucesso": True,

        "mensagem":
            "Site excluído com sucesso."

    })


# ============================================================
# HISTÓRICO DE MONITORAMENTO
# ============================================================

@app.route(
    "/api/sites/<int:site_id>/monitoramentos"
)
@login_required
def api_monitoramentos(site_id):

    usuario = usuario_logado()


    site = buscar_site(
        site_id,
        usuario["id"]
    )


    if not site:

        return resposta_erro_api(
            "Site não encontrado.",
            404
        )


    registros = listar_monitoramentos(
        site_id
    )


    return jsonify([

        dict(registro)

        for registro in registros

    ])


# ============================================================
# MÉTRICAS
# ============================================================

@app.route(
    "/api/sites/<int:site_id>/metrics"
)
@login_required
def api_metrics(site_id):

    usuario = usuario_logado()


    site = buscar_site(
        site_id,
        usuario["id"]
    )


    if not site:

        return resposta_erro_api(
            "Site não encontrado.",
            404
        )


    metricas = obter_metricas(
        site_id
    )


    return jsonify(
        metricas
    )


# ============================================================
# SSL
# ============================================================

@app.route(
    "/api/sites/<int:site_id>/ssl"
)
@login_required
def api_ssl(site_id):

    usuario = usuario_logado()


    site = buscar_site(
        site_id,
        usuario["id"]
    )


    if not site:

        return resposta_erro_api(
            "Site não encontrado.",
            404
        )


    registros = listar_ssl(
        site_id
    )


    return jsonify([

        dict(registro)

        for registro in registros

    ])


# ============================================================
# INCIDENTES DO USUÁRIO
# ============================================================

@app.route(
    "/api/sites/<int:site_id>/incidentes",
    methods=["GET"]
)
@login_required
def api_incidentes(site_id):

    usuario = usuario_logado()


    site = buscar_site(
        site_id,
        usuario["id"]
    )


    if not site:

        return resposta_erro_api(
            "Site não encontrado.",
            404
        )


    incidentes = listar_incidentes(
        site_id=site_id,
        limite=100
    )


    return jsonify([

        dict(incidente)

        for incidente in incidentes

    ])


# ============================================================
# TODOS OS INCIDENTES DO USUÁRIO
# ============================================================

@app.route(
    "/api/incidentes",
    methods=["GET"]
)
@login_required
def api_todos_incidentes_usuario():

    usuario = usuario_logado()


    sites = listar_sites(
        usuario["id"]
    )


    resultado = []


    for site in sites:

        incidentes = listar_incidentes(
            site_id=site["id"],
            limite=100
        )


        for incidente in incidentes:

            item = dict(
                incidente
            )


            item["site_id"] = site["id"]

            item["site_nome"] = site["nome"]

            item["site_url"] = site["url"]


            resultado.append(
                item
            )


    return jsonify(
        resultado
    )


# ============================================================
# STATUS DO SERVIÇO
# ============================================================

@app.route("/status")
def status():

    return jsonify({

        "status":
            "online",

        "servico":
            "Cloud Security Monitor"

    })


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():

    return jsonify({

        "status":
            "healthy"

    })


# ============================================================
# MÉTRICAS GERAIS
# ============================================================

@app.route("/metrics")
@login_required
def metrics():

    usuario = usuario_logado()


    sites = listar_sites(
        usuario["id"]
    )


    resultado = []


    for site in sites:

        metricas = obter_metricas(
            site["id"]
        )


        resultado.append({

            "site":
                site["nome"],

            "site_id":
                site["id"],

            "url":
                site["url"],

            "metricas":
                metricas

        })


    return jsonify(
        resultado
    )


# ============================================================
# ADMIN
# ============================================================

@app.route("/admin")
@admin_required
def admin_dashboard():

    return render_template(
        "admin.html"
    )


# ============================================================
# ADMIN - USUÁRIOS
# ============================================================

@app.route(
    "/admin/users",
    methods=["GET"]
)
@admin_required
def admin_users():

    usuarios = listar_usuarios()


    return jsonify([

        dict(usuario)

        for usuario in usuarios

    ])


# ============================================================
# ADMIN - ALTERAR ROLE
# ============================================================

@app.route(
    "/admin/users/<int:usuario_id>/role",
    methods=["POST", "PUT"]
)
@admin_required
def admin_alterar_role(usuario_id):

    admin = usuario_logado()


    dados = request.get_json(
        silent=True
    ) or {}


    role = dados.get(
        "role"
    )


    if role not in (
        "admin",
        "user"
    ):

        return resposta_erro_api(
            "Role inválida.",
            400
        )


    if usuario_id == admin["id"]:

        return resposta_erro_api(
            "Você não pode alterar sua própria função.",
            400
        )


    usuario = buscar_usuario_por_id(
        usuario_id
    )


    if not usuario:

        return resposta_erro_api(
            "Usuário não encontrado.",
            404
        )


    try:

        alterado = alterar_usuario_admin(
            usuario_id,
            role=role
        )


    except ValueError as erro:

        return resposta_erro_api(
            str(erro),
            400
        )


    if not alterado:

        return resposta_erro_api(
            "Nenhuma alteração realizada.",
            400
        )


    registrar_log(
        admin["id"],
        "ALTERAR_ROLE",
        f"Usuário {usuario['email']} alterado para {role}."
    )


    return jsonify({

        "sucesso": True,

        "mensagem":
            "Função alterada com sucesso."

    })


# ============================================================
# ADMIN - BLOQUEAR / ATIVAR
# ============================================================

@app.route(
    "/admin/users/<int:usuario_id>/status",
    methods=["POST", "PUT"]
)
@admin_required
def admin_alterar_status(usuario_id):

    admin = usuario_logado()


    dados = request.get_json(
        silent=True
    ) or {}


    ativo = dados.get(
        "ativo"
    )


    if ativo not in (
        0,
        1,
        True,
        False
    ):

        return resposta_erro_api(
            "Status inválido.",
            400
        )


    ativo = int(
        ativo
    )


    if usuario_id == admin["id"]:

        return resposta_erro_api(
            "Você não pode bloquear sua própria conta.",
            400
        )


    usuario = buscar_usuario_por_id(
        usuario_id
    )


    if not usuario:

        return resposta_erro_api(
            "Usuário não encontrado.",
            404
        )


    try:

        alterado = alterar_usuario_admin(
            usuario_id,
            ativo=ativo
        )


    except ValueError as erro:

        return resposta_erro_api(
            str(erro),
            400
        )


    if not alterado:

        return resposta_erro_api(
            "Nenhuma alteração realizada.",
            400
        )


    acao = (

        "ATIVAR_USUARIO"

        if ativo

        else

        "BLOQUEAR_USUARIO"

    )


    descricao = (

        f"Usuário {usuario['email']} "

        f"{'ativado' if ativo else 'bloqueado'}."

    )


    registrar_log(
        admin["id"],
        acao,
        descricao
    )


    return jsonify({

        "sucesso": True,

        "mensagem":
            descricao

    })


# ============================================================
# ADMIN - SITES
# ============================================================

@app.route(
    "/admin/sites",
    methods=["GET"]
)
@admin_required
def admin_sites():

    sites = listar_todos_sites_admin()


    return jsonify([

        dict(site)

        for site in sites

    ])


# ============================================================
# ADMIN - HISTÓRICO SSL
# ============================================================

@app.route(
    "/admin/ssl-history",
    methods=["GET"]
)
@admin_required
def admin_ssl_history():

    registros = listar_todos_ssl_admin()


    return jsonify([

        dict(registro)

        for registro in registros

    ])


# ============================================================
# ADMIN - INCIDENTES
# ============================================================

@app.route(
    "/admin/incidentes",
    methods=["GET"]
)
@admin_required
def admin_incidentes():

    incidentes = listar_incidentes(
        site_id=None,
        limite=200
    )


    return jsonify([

        dict(incidente)

        for incidente in incidentes

    ])


# ============================================================
# COMPATIBILIDADE
# ============================================================

@app.route(
    "/admin/incidents",
    methods=["GET"]
)
@admin_required
def admin_incidents_compatibilidade():

    incidentes = listar_incidentes(
        site_id=None,
        limite=200
    )


    return jsonify([

        dict(incidente)

        for incidente in incidentes

    ])


# ============================================================
# ADMIN - AUDITORIA
# ============================================================

@app.route(
    "/admin/audit-logs",
    methods=["GET"]
)
@admin_required
def admin_audit_logs():

    logs = listar_auditoria()


    return jsonify([

        dict(log)

        for log in logs

    ])


# ============================================================
# DASHBOARD API
# ============================================================

@app.route(
    "/api/dashboard"
)
@login_required
def api_dashboard():

    usuario = usuario_logado()


    sites = listar_sites(
        usuario["id"]
    )


    dados = []


    for site in sites:

        metricas = obter_metricas(
            site["id"]
        )


        dados.append({

            "id":
                site["id"],

            "nome":
                site["nome"],

            "url":
                site["url"],

            "criado_em":
                site["criado_em"],

            "metricas":
                metricas

        })


    return jsonify(
        dados
    )


# ============================================================
# HEADERS DE SEGURANÇA
# ============================================================

@app.after_request
def adicionar_headers_seguranca(
    response
):

    response.headers[
        "X-Content-Type-Options"
    ] = "nosniff"


    response.headers[
        "X-Frame-Options"
    ] = "SAMEORIGIN"


    response.headers[
        "Referrer-Policy"
    ] = (
        "strict-origin-when-cross-origin"
    )


    response.headers[
        "Permissions-Policy"
    ] = (
        "camera=(), microphone=(), geolocation=()"
    )


    response.headers[
        "X-XSS-Protection"
    ] = "0"


    # --------------------------------------------------------
    # HSTS
    # --------------------------------------------------------
    #
    # Só enviamos HSTS em produção.
    # Com ProxyFix, request.is_secure pode reconhecer
    # corretamente HTTPS atrás do Render.
    #

    if PRODUCAO and request.is_secure:

        response.headers[
            "Strict-Transport-Security"
        ] = (
            "max-age=31536000; "
            "includeSubDomains"
        )


    return response


# ============================================================
# TRATAMENTO DE ERROS
# ============================================================

@app.errorhandler(413)
def erro_413(erro):

    if request.path.startswith(
        "/api/"
    ):

        return resposta_erro_api(
            "Requisição muito grande.",
            413
        )


    return (
        "Requisição muito grande.",
        413
    )


@app.errorhandler(404)
def erro_404(erro):

    if (
        request.path.startswith("/api/")
        or request.path.startswith("/admin/")
    ):

        return resposta_erro_api(
            "Recurso não encontrado.",
            404
        )


    return (
        "Página não encontrada.",
        404
    )


@app.errorhandler(500)
def erro_500(erro):

    print(
        f"❌ Erro interno: {erro}"
    )


    if (
        request.path.startswith("/api/")
        or request.path.startswith("/admin/")
    ):

        return resposta_erro_api(
            "Erro interno do servidor.",
            500
        )


    return (
        "Erro interno do servidor.",
        500
    )


# ============================================================
# EXECUÇÃO LOCAL
# ============================================================

if __name__ == "__main__":

    iniciar_monitoramento_automatico()


    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )


    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )