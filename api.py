import os
import secrets
from datetime import timedelta
from functools import wraps

from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix

import database

from database import (
    conectar,
    criar_usuario,
    buscar_usuario_por_email,
    buscar_usuario_por_id,
    criar_site,
    buscar_site,
    listar_sites,
    excluir_site,
    listar_monitoramentos,
    listar_ssl,
    registrar_auditoria,
)

from alerts import listar_incidentes
from ssl_alert_manager import listar_alertas_ssl
from metrics import obter_metricas

from scheduler import iniciar_monitoramento_automatico
from billing import registrar_rotas as registrar_rotas_billing


# ============================================================
# CONFIGURAÃ‡ÃƒO
# ============================================================


def serializar_registro(valor):
    """Converte sqlite3.Row/dict/list para dados compat?veis com JSON."""
    if valor is None:
        return None

    if isinstance(valor, dict):
        return {
            str(chave): serializar_registro(item)
            for chave, item in valor.items()
        }

    if hasattr(valor, "keys"):
        return {
            str(chave): serializar_registro(valor[chave])
            for chave in valor.keys()
        }

    if isinstance(valor, (list, tuple)):
        return [serializar_registro(item) for item in valor]

    return valor


def serializar_lista(valores):
    return [
        serializar_registro(valor)
        for valor in (valores or [])
    ]


app = Flask(__name__)

PRODUCAO = (
    os.environ.get("FLASK_ENV", "").lower() == "production"
    or os.environ.get("RENDER", "").lower() == "true"
)

SECRET_KEY = os.environ.get("SECRET_KEY")

if PRODUCAO and not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY nÃ£o configurada. Defina a variÃ¡vel SECRET_KEY no ambiente."
    )

if not SECRET_KEY:
    SECRET_KEY = "chave-local-desenvolvimento"

app.secret_key = SECRET_KEY

app.config["SESSION_COOKIE_NAME"] = "csm_session"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = PRODUCAO
app.config["SESSION_REFRESH_EACH_REQUEST"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=12)

app.wsgi_app = ProxyFix(
    app.wsgi_app,
    x_for=1,
    x_proto=1,
    x_host=1,
)


# ============================================================
# CSRF
# ============================================================

METODOS_QUE_EXIGEM_CSRF = {
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
}


def obter_token_csrf():
    """
    ObtÃ©m o token CSRF da sessÃ£o.
    Caso ainda nÃ£o exista, cria um novo.
    """

    token = session.get("csrf_token")

    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token

    return token


def validar_csrf():
    """
    Valida o token CSRF enviado pelo navegador.

    Aceita token por:
    - Header X-CSRF-Token
    - JSON csrf_token
    - Form csrf_token
    """

    if request.method not in METODOS_QUE_EXIGEM_CSRF:
        return True

    # Login e cadastro nÃ£o dependem de uma sessÃ£o anterior.
    if request.path in ("/login", "/register"):
        return True

    token_sessao = session.get("csrf_token")

    if not token_sessao:
        return False

    token_requisicao = request.headers.get("X-CSRF-Token")

    if not token_requisicao:
        dados_json = request.get_json(silent=True)

        if isinstance(dados_json, dict):
            token_requisicao = dados_json.get("csrf_token")

    if not token_requisicao:
        token_requisicao = request.form.get("csrf_token")

    if not token_requisicao:
        return False

    try:
        return secrets.compare_digest(
            token_sessao,
            token_requisicao,
        )
    except Exception:
        return False


@app.before_request
def proteger_contra_csrf():

    if request.method not in METODOS_QUE_EXIGEM_CSRF:
        return None

    caminhos_protegidos = (
        request.path.startswith("/api/"),
        request.path.startswith("/admin/"),
        request.path in (
            "/logout",
            "/login",
            "/register",
        ),
    )

    if request.path == "/api/billing/webhook":
        return None

    if not any(caminhos_protegidos):
        return None

    if validar_csrf():
        return None

    if request.path.startswith("/api/") or request.is_json:
        return jsonify({
            "sucesso": False,
            "erro": "Token CSRF invÃ¡lido ou ausente."
        }), 403

    return "Token CSRF invÃ¡lido ou ausente.", 403


# ============================================================
# AUTENTICAÃ‡ÃƒO
# ============================================================

def usuario_logado():
    """
    Retorna o usuÃ¡rio atualmente autenticado.
    """

    usuario_id = session.get("usuario_id")

    if not usuario_id:
        return None

    try:
        usuario = buscar_usuario_por_id(usuario_id)
    except Exception:
        usuario = None

    if not usuario:
        session.clear()
        return None

    if isinstance(usuario, dict):

        ativo = usuario.get("ativo", 1)

        if ativo in (False, 0, "0"):
            session.clear()
            return None

    return usuario


def login_required(func):
    """
    Exige usuÃ¡rio autenticado.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):

        usuario = usuario_logado()

        if not usuario:

            if request.path.startswith("/api/") or request.is_json:
                return jsonify({
                    "sucesso": False,
                    "erro": "AutenticaÃ§Ã£o necessÃ¡ria."
                }), 401

            return redirect(url_for("login"))

        return func(*args, **kwargs)

    return wrapper


def admin_required(func):
    """
    Exige usuÃ¡rio autenticado com role admin.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):

        usuario = usuario_logado()

        if not usuario:

            if request.path.startswith("/api/") or request.is_json:
                return jsonify({
                    "sucesso": False,
                    "erro": "AutenticaÃ§Ã£o necessÃ¡ria."
                }), 401

            return redirect(url_for("login"))

        # sqlite3.Row nao possui atributos como .role.
        # Tratamos dict, sqlite3.Row e objetos normalmente.
        if isinstance(usuario, dict):
            role = usuario.get("role", "")
        else:
            try:
                role = usuario["role"]
            except Exception:
                role = getattr(usuario, "role", "")

        role = str(role).strip().lower()

        if role != "admin":
            return jsonify({
                "sucesso": False,
                "erro": "Acesso administrativo nÃ£o autorizado."
            }), 403

        return func(*args, **kwargs)

    return wrapper


registrar_rotas_billing(app, login_required)


# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "GET":

        if usuario_logado():
            return redirect(url_for("dashboard"))

        obter_token_csrf()

        return render_template("login.html")

    dados = request.get_json(silent=True)

    if not isinstance(dados, dict):
        dados = request.form.to_dict()

    email = str(
        dados.get("email", "")
    ).strip().lower()

    senha = str(
        dados.get("senha", "")
    )

    if not email or not senha:

        if request.is_json:
            return jsonify({
                "sucesso": False,
                "erro": "E-mail e senha sÃ£o obrigatÃ³rios."
            }), 400

        return render_template(
            "login.html",
            erro="E-mail e senha sÃ£o obrigatÃ³rios."
        ), 400

    try:
        usuario = buscar_usuario_por_email(email)

    except Exception as erro:

        print(f"Erro ao buscar usuÃ¡rio: {erro}")
        usuario = None

    if not usuario:

        if request.is_json:
            return jsonify({
                "sucesso": False,
                "erro": "E-mail ou senha invÃ¡lidos."
            }), 401

        return render_template(
            "login.html",
            erro="E-mail ou senha invÃ¡lidos."
        ), 401

    if isinstance(usuario, dict):

        usuario_id = usuario.get("id")
        usuario_nome = usuario.get("nome", "")
        usuario_email = usuario.get("email", "")
        usuario_role = usuario.get("role", "user")
        usuario_ativo = usuario.get("ativo", 1)
        senha_hash = usuario.get("senha_hash") or usuario.get("senha")

    else:

        usuario_id = usuario["id"]
        usuario_nome = usuario["nome"]
        usuario_email = usuario["email"]
        usuario_role = usuario["role"]
        usuario_ativo = (
            usuario["ativo"]
            if "ativo" in usuario.keys()
            else 1
        )
        senha_hash = (
            usuario["senha_hash"]
            if "senha_hash" in usuario.keys()
            else usuario["senha"]
        )

    if usuario_ativo in (False, 0, "0"):

        if request.is_json:
            return jsonify({
                "sucesso": False,
                "erro": "UsuÃ¡rio inativo."
            }), 403

        return render_template(
            "login.html",
            erro="UsuÃ¡rio inativo."
        ), 403

    senha_valida = False

    if senha_hash:

        try:

            senha_valida = check_password_hash(
                senha_hash,
                senha
            )

        except Exception:

            senha_valida = False

    # Compatibilidade com senha antiga.
    if not senha_valida and senha_hash == senha:
        senha_valida = True

    if not senha_valida:

        if request.is_json:
            return jsonify({
                "sucesso": False,
                "erro": "E-mail ou senha invÃ¡lidos."
            }), 401

        return render_template(
            "login.html",
            erro="E-mail ou senha invÃ¡lidos."
        ), 401

    # ========================================================
    # CRIAR SESSÃƒO
    # ========================================================

    session.clear()

    session.permanent = True

    session["csrf_token"] = secrets.token_urlsafe(32)
    session["usuario_id"] = usuario_id
    session["usuario_nome"] = usuario_nome
    session["usuario_email"] = usuario_email
    session["usuario_role"] = usuario_role

    # ========================================================
    # AUDITORIA
    # ========================================================

    try:

        registrar_auditoria(
            usuario_id=usuario_id,
            acao="LOGIN",
            detalhes=f"Login realizado para {usuario_email}"
        )

    except Exception as erro:

        print(
            f"Aviso: nÃ£o foi possÃ­vel registrar auditoria do login: {erro}"
        )

    # ========================================================
    # RESPOSTA
    # ========================================================

    resposta = {
        "sucesso": True,
        "mensagem": "Login realizado com sucesso.",
        "redirect": url_for("dashboard"),
        "csrf_token": session["csrf_token"],
        "usuario": {
            "id": usuario_id,
            "nome": usuario_nome,
            "email": usuario_email,
            "role": usuario_role,
        }
    }

    if request.is_json:
        return jsonify(resposta), 200

    return redirect(
        url_for("dashboard")
    )


# ============================================================
# CADASTRO
# ============================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "GET":

        if usuario_logado():
            return redirect(url_for("dashboard"))

        obter_token_csrf()

        return render_template("register.html")

    dados = request.get_json(silent=True)

    if not isinstance(dados, dict):
        dados = request.form.to_dict()

    nome = str(
        dados.get("nome", "")
    ).strip()

    email = str(
        dados.get("email", "")
    ).strip().lower()

    senha = str(
        dados.get("senha", "")
    )

    if not nome or not email or not senha:

        resposta = {
            "sucesso": False,
            "erro": "Nome, e-mail e senha sÃ£o obrigatÃ³rios."
        }

        if request.is_json:
            return jsonify(resposta), 400

        return render_template(
            "register.html",
            erro=resposta["erro"]
        ), 400

    if len(senha) < 6:

        resposta = {
            "sucesso": False,
            "erro": "A senha deve possuir pelo menos 6 caracteres."
        }

        if request.is_json:
            return jsonify(resposta), 400

        return render_template(
            "register.html",
            erro=resposta["erro"]
        ), 400

    try:

        usuario_existente = buscar_usuario_por_email(email)

    except Exception as erro:

        print(
            f"Erro ao verificar usuÃ¡rio: {erro}"
        )

        usuario_existente = None

    if usuario_existente:

        resposta = {
            "sucesso": False,
            "erro": "E-mail jÃ¡ cadastrado."
        }

        if request.is_json:
            return jsonify(resposta), 409

        return render_template(
            "register.html",
            erro=resposta["erro"]
        ), 409

    try:

        usuario_id = criar_usuario(
            nome=nome,
            email=email,
            senha=senha
        )

    except TypeError:

        usuario_id = criar_usuario(
            nome,
            email,
            senha
        )

    except Exception as erro:

        print(
            f"Erro ao criar usuÃ¡rio: {erro}"
        )

        resposta = {
            "sucesso": False,
            "erro": "NÃ£o foi possÃ­vel criar o usuÃ¡rio."
        }

        if request.is_json:
            return jsonify(resposta), 500

        return render_template(
            "register.html",
            erro=resposta["erro"]
        ), 500

    session.clear()

    session.permanent = True

    session["csrf_token"] = secrets.token_urlsafe(32)
    session["usuario_id"] = usuario_id
    session["usuario_nome"] = nome
    session["usuario_email"] = email
    session["usuario_role"] = "user"

    try:

        registrar_auditoria(
            usuario_id=usuario_id,
            acao="REGISTER",
            detalhes=f"Novo usuÃ¡rio cadastrado: {email}"
        )

    except Exception as erro:

        print(
            f"Aviso: nÃ£o foi possÃ­vel registrar auditoria do cadastro: {erro}"
        )

    resposta = {
        "sucesso": True,
        "mensagem": "Cadastro realizado com sucesso.",
        "redirect": url_for("dashboard"),
        "csrf_token": session["csrf_token"],
        "usuario": {
            "id": usuario_id,
            "nome": nome,
            "email": email,
            "role": "user",
        }
    }

    if request.is_json:
        return jsonify(resposta), 201

    return redirect(
        url_for("dashboard")
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout", methods=["GET", "POST"])
def logout():

    usuario_id = session.get("usuario_id")

    if request.method == "POST":

        try:

            if usuario_id:

                registrar_auditoria(
                    usuario_id=usuario_id,
                    acao="LOGOUT",
                    detalhes="Logout realizado"
                )

        except Exception as erro:

            print(
                f"Aviso: erro ao registrar logout: {erro}"
            )

        session.clear()

        return jsonify({
            "sucesso": True,
            "mensagem": "Logout realizado.",
            "redirect": url_for("login")
        })

    session.clear()

    return redirect(
        url_for("login")
    )


# ============================================================
# PÃGINA PRINCIPAL
# ============================================================

@app.route("/")
def index():

    if usuario_logado():
        return redirect(url_for("dashboard"))

    return redirect(url_for("login"))


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
@login_required
def dashboard():

    usuario = usuario_logado()

    return render_template(
        "dashboard.html",
        usuario=usuario
    )


# ============================================================
# USUÃRIO AUTENTICADO
# ============================================================

@app.route("/api/me", methods=["GET"])
@login_required
def api_me():

    usuario = usuario_logado()

    return jsonify({
        "id": usuario["id"],
        "nome": usuario["nome"],
        "email": usuario["email"],
        "role": usuario.get("role", "user"),
        "ativo": usuario.get("ativo", 1),
    })


# ============================================================
# TOKEN CSRF
# ============================================================

@app.route("/api/csrf-token", methods=["GET"])
@login_required
def csrf_token():

    return jsonify({
        "sucesso": True,
        "csrf_token": obter_token_csrf()
    })


# ============================================================
# STATUS DA API
# ============================================================

@app.route("/health", methods=["GET"])
def health():

    return jsonify({
        "status": "healthy"
    })


@app.route("/status", methods=["GET"])
def status():

    return jsonify({
        "projeto": "Cloud Security Monitor",
        "status": "online"
    })


# ============================================================
# SITES
# ============================================================

@app.route("/api/sites", methods=["GET"])
@login_required
def api_listar_sites():
    try:
        usuario = usuario_logado()

        if not usuario:
            return jsonify({
                "sucesso": False,
                "erro": "UsuÃ¡rio nÃ£o autenticado."
            }), 401

        sites = listar_sites(usuario["id"])
        resultado = []

        for site in sites:
            resultado.append({
                "id": site["id"],
                "usuario_id": site["usuario_id"],
                "nome": site["nome"],
                "url": site["url"],
                "criado_em": site["criado_em"]
            })

        return jsonify({
            "sucesso": True,
            "sites": resultado
        })

    except Exception as e:
        print("ERRO /api/sites:", repr(e))
        return jsonify({
            "sucesso": False,
            "erro": "Erro interno do servidor."
        }), 500

@app.route("/api/sites", methods=["POST"])
@login_required
def api_criar_site():

    usuario = usuario_logado()

    dados = request.get_json(silent=True)

    if not isinstance(dados, dict):
        dados = request.form.to_dict()

    nome = str(
        dados.get("nome", "")
    ).strip()

    url = str(
        dados.get("url", "")
    ).strip()

    if not nome:

        return jsonify({
            "sucesso": False,
            "erro": "Nome do site Ã© obrigatÃ³rio."
        }), 400

    if not url:

        return jsonify({
            "sucesso": False,
            "erro": "URL do site Ã© obrigatÃ³ria."
        }), 400

    if not (
        url.startswith("http://")
        or url.startswith("https://")
    ):

        return jsonify({
            "sucesso": False,
            "erro": "A URL deve comeÃ§ar com http:// ou https://."
        }), 400

    try:

        site_id = criar_site(
            usuario_id=usuario["id"],
            nome=nome,
            url=url
        )

    except TypeError:

        site_id = criar_site(
            usuario["id"],
            nome,
            url
        )

    except Exception as erro:

        print(
            f"Erro ao criar site: {erro}"
        )

        return jsonify({
            "sucesso": False,
            "erro": "NÃ£o foi possÃ­vel adicionar o site."
        }), 500

    try:

        registrar_auditoria(
            usuario_id=usuario["id"],
            acao="SITE_CRIADO",
            detalhes=f"Site criado: {nome} - {url}"
        )

    except Exception as erro:

        print(
            f"Aviso: nÃ£o foi possÃ­vel registrar auditoria do site: {erro}"
        )

    return jsonify({
        "sucesso": True,
        "mensagem": "Site adicionado com sucesso.",
        "site_id": site_id
    }), 201


@app.route("/api/sites/<int:site_id>", methods=["GET"])
@login_required
def api_obter_site(site_id):

    usuario = usuario_logado()

    site = buscar_site(
        site_id,
        usuario["id"]
    )

    if not site:

        return jsonify({
            "sucesso": False,
            "erro": "Site nÃ£o encontrado."
        }), 404

    return jsonify({
        "sucesso": True,
        "site": site
    })


@app.route("/api/sites/<int:site_id>", methods=["DELETE"])
@login_required
def api_excluir_site(site_id):

    usuario = usuario_logado()

    site = buscar_site(
        site_id,
        usuario["id"]
    )

    if not site:

        return jsonify({
            "sucesso": False,
            "erro": "Site nÃ£o encontrado."
        }), 404

    try:

        excluir_site(
            site_id,
            usuario["id"]
        )

    except TypeError:

        excluir_site(
            site_id
        )

    except Exception as erro:

        print(
            f"Erro ao excluir site: {erro}"
        )

        return jsonify({
            "sucesso": False,
            "erro": "NÃ£o foi possÃ­vel excluir o site."
        }), 500

    try:

        registrar_auditoria(
            usuario_id=usuario["id"],
            acao="SITE_EXCLUIDO",
            detalhes=f"Site excluÃ­do: {site_id}"
        )

    except Exception as erro:

        print(
            f"Aviso: nÃ£o foi possÃ­vel registrar auditoria: {erro}"
        )

    return jsonify({
        "sucesso": True,
        "mensagem": "Site excluÃ­do com sucesso."
    })


# ============================================================
# MONITORAMENTOS
# ============================================================

@app.route(
    "/api/sites/<int:site_id>/monitoramentos",
    methods=["GET"]
)
@login_required
def api_monitoramentos(site_id):

    usuario = usuario_logado()

    site = buscar_site(
        site_id,
        usuario["id"]
    )

    if not site:

        return jsonify({
            "sucesso": False,
            "erro": "Site nÃ£o encontrado."
        }), 404

    try:

        monitoramentos = listar_monitoramentos(site_id)

    except TypeError:

        monitoramentos = listar_monitoramentos(
            site_id
        )

    return jsonify({
        "sucesso": True,
        "monitoramentos": serializar_lista(monitoramentos)
    })


# ============================================================
# INCIDENTES
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

        return jsonify({
            "sucesso": False,
            "erro": "Site nÃ£o encontrado."
        }), 404

    try:

        incidentes = listar_incidentes(
            site_id
        )

    except TypeError:

        incidentes = listar_incidentes()

    return jsonify({
        "sucesso": True,
        "incidentes": serializar_lista(incidentes)
    })


# ============================================================
# ALERTAS SSL
# ============================================================

@app.route(
    "/api/sites/<int:site_id>/ssl-alertas",
    methods=["GET"]
)
@login_required
def api_ssl_alertas(site_id):

    usuario = usuario_logado()

    site = buscar_site(
        site_id,
        usuario["id"]
    )

    if not site:

        return jsonify({
            "sucesso": False,
            "erro": "Site nÃ£o encontrado."
        }), 404

    try:

        alertas = listar_alertas_ssl(
            site_id
        )

    except TypeError:

        alertas = listar_alertas_ssl()

    return jsonify({
        "sucesso": True,
        "ssl_alertas": serializar_lista(alertas)
    })


# ============================================================
# MÃ‰TRICAS
# ============================================================

@app.route(
    "/api/sites/<int:site_id>/metricas",
    methods=["GET"]
)
@login_required
def api_metricas(site_id):

    usuario = usuario_logado()

    site = buscar_site(
        site_id,
        usuario["id"]
    )

    if not site:

        return jsonify({
            "sucesso": False,
            "erro": "Site nÃ£o encontrado."
        }), 404

    try:

        metricas = obter_metricas(
            site_id
        )

    except TypeError:

        metricas = obter_metricas(
            site_id,
            usuario["id"]
        )

    return jsonify({
        "sucesso": True,
        "metricas": serializar_registro(metricas)
    })


# ============================================================
# COMPATIBILIDADE COM O DASHBOARD
# ============================================================

@app.route(
    "/api/sites/<int:site_id>/metrics",
    methods=["GET"]
)
@login_required
def api_metrics_alias(site_id):

    return api_metricas(site_id)


@app.route(
    "/api/sites/<int:site_id>/ssl",
    methods=["GET"]
)
@login_required
def api_ssl(site_id):

    usuario = usuario_logado()

    site = buscar_site(
        site_id,
        usuario["id"]
    )

    if not site:

        return jsonify({
            "sucesso": False,
            "erro": "Site nÃ£o encontrado."
        }), 404

    try:

        registros = listar_ssl(
            site_id
        )

    except TypeError:

        registros = listar_ssl()

    return jsonify({
        "sucesso": True,
        "ssl": serializar_lista(registros)
    })


# ============================================================
# ADMIN
# ============================================================

@app.route("/admin")
@admin_required
def admin():

    usuario = usuario_logado()

    return render_template(
        "admin.html",
        usuario=usuario
    )


@app.route(
    "/admin/api/usuarios",
    methods=["GET"]
)
@admin_required
def admin_usuarios():

    conexao = conectar()

    try:

        cursor = conexao.cursor()

        cursor.execute("""
            SELECT
                id,
                nome,
                email,
                role,
                ativo
            FROM users
            ORDER BY id DESC
        """)

        usuarios = cursor.fetchall()

        resultado = []

        for usuario in usuarios:

            if isinstance(usuario, dict):

                resultado.append(
                    dict(usuario)
                )

            else:

                resultado.append({
                    "id": usuario[0],
                    "nome": usuario[1],
                    "email": usuario[2],
                    "role": usuario[3],
                    "ativo": usuario[4],
                })

        return jsonify({
            "sucesso": True,
            "usuarios": resultado
        })

    finally:

        conexao.close()


# ============================================================
# AUDITORIA ADMIN
# ============================================================

@app.route(
    "/admin/api/auditoria",
    methods=["GET"]
)
@admin_required
def admin_auditoria():

    conexao = conectar()

    try:

        cursor = conexao.cursor()

        cursor.execute("""
            SELECT *
            FROM audit_logs
            ORDER BY id DESC
            LIMIT 500
        """)

        registros = cursor.fetchall()

        resultado = []

        for registro in registros:

            if isinstance(registro, dict):

                resultado.append(
                    dict(registro)
                )

            else:

                try:

                    resultado.append(
                        dict(registro)
                    )

                except Exception:

                    resultado.append({
                        "dados": list(registro)
                    })

        return jsonify({
            "sucesso": True,
            "auditoria": resultado
        })

    finally:

        conexao.close()


# ============================================================
# TRATAMENTO DE ERROS
# ============================================================

@app.errorhandler(404)
def pagina_nao_encontrada(erro):

    if request.path.startswith("/api/"):

        return jsonify({
            "sucesso": False,
            "erro": "Recurso nÃ£o encontrado."
        }), 404

    return "PÃ¡gina nÃ£o encontrada.", 404


@app.errorhandler(500)
def erro_interno(erro):

    print(
        f"Erro interno: {erro}"
    )

    if request.path.startswith("/api/"):

        return jsonify({
            "sucesso": False,
            "erro": "Erro interno do servidor."
        }), 500

    return "Erro interno do servidor.", 500


# ============================================================
# CABEÃ‡ALHOS DE SEGURANÃ‡A
# ============================================================

@app.after_request
def adicionar_headers_seguranca(response):

    response.headers["X-Content-Type-Options"] = "nosniff"

    response.headers["X-Frame-Options"] = "SAMEORIGIN"

    response.headers["Referrer-Policy"] = (
        "strict-origin-when-cross-origin"
    )

    if PRODUCAO:

        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

    return response


# ============================================================
# INICIALIZAÃ‡ÃƒO
# ============================================================

if __name__ == "__main__":

    print("=" * 60)
    print("CLOUD SECURITY MONITOR")
    print("=" * 60)

    print(
        "Banco:",
        "PostgreSQL"
        if getattr(database, "USANDO_POSTGRES", False)
        else "SQLite"
    )

    print(
        "Ambiente:",
        "PRODUÃ‡ÃƒO"
        if PRODUCAO
        else "DESENVOLVIMENTO"
    )

    print("=" * 60)

    try:

        iniciar_monitoramento_automatico()

    except Exception as erro:

        print(
            f"Aviso: monitoramento automÃ¡tico nÃ£o foi iniciado: {erro}"
        )

    porta = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    app.run(
        host="0.0.0.0",
        port=porta,
        debug=False
    )
