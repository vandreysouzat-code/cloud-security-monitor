import hashlib
import hmac
import os

import requests
from flask import (
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

import database


# ==============================================================
# PLANOS
# ==============================================================

PLANOS = {
    "gratis": {
        "nome": "Grátis",
        "preco": 0.00,
        "limite_sites": 1,
        "historico_dias": 7,
        "descricao": "Para conhecer o Cloud Security Monitor.",
    },
    "basico": {
        "nome": "Básico",
        "preco": 29.90,
        "limite_sites": 5,
        "historico_dias": 30,
        "descricao": "Para pequenos projetos e sites.",
    },
    "profissional": {
        "nome": "Profissional",
        "preco": 59.90,
        "limite_sites": 20,
        "historico_dias": 90,
        "descricao": "Para monitoramento profissional.",
    },
    "empresarial": {
        "nome": "Empresarial",
        "preco": 119.90,
        "limite_sites": 50,
        "historico_dias": 365,
        "descricao": "Para empresas e operações maiores.",
    },
}


# ==============================================================
# MERCADO PAGO
# ==============================================================

MERCADO_PAGO_API = "https://api.mercadopago.com"


def obter_access_token():
    return os.environ.get(
        "MP_ACCESS_TOKEN",
        "",
    ).strip()


def obter_base_publica():
    base = os.environ.get(
        "PUBLIC_BASE_URL",
        "",
    ).strip().rstrip("/")

    if base:
        return base

    return request.url_root.rstrip("/")


def mercado_pago_request(
    metodo,
    caminho,
    payload=None,
):
    token = obter_access_token()

    if not token:
        raise RuntimeError(
            "MP_ACCESS_TOKEN não configurado."
        )

    resposta = requests.request(
        method=metodo,
        url=f"{MERCADO_PAGO_API}{caminho}",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )

    if resposta.status_code >= 400:

        try:
            detalhe = resposta.json()

        except Exception:
            detalhe = resposta.text

        raise RuntimeError(
            "Erro retornado pelo Mercado Pago "
            f"(HTTP {resposta.status_code}): {detalhe}"
        )

    try:
        return resposta.json()

    except Exception:
        return {}


# ==============================================================
# BANCO DE DADOS
# ==============================================================

def inicializar_billing():

    # Garante que as tabelas principais do sistema
    # existam antes de criar as tabelas de cobrança.
    database.criar_banco()

    conexao = database.conectar()

    try:

        cursor = conexao.cursor()

        # ------------------------------------------------------
        # PLANOS DE COBRANÇA
        # ------------------------------------------------------

        if database.USANDO_POSTGRES:

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS billing_plans (
                    id SERIAL PRIMARY KEY,
                    slug TEXT NOT NULL UNIQUE,
                    nome TEXT NOT NULL,
                    preco NUMERIC(10,2) NOT NULL,
                    limite_sites INTEGER NOT NULL,
                    historico_dias INTEGER NOT NULL,
                    mp_plan_id TEXT,
                    mp_init_point TEXT,
                    criado_em TIMESTAMP
                        DEFAULT CURRENT_TIMESTAMP,
                    atualizado_em TIMESTAMP
                        DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

        else:

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS billing_plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slug TEXT NOT NULL UNIQUE,
                    nome TEXT NOT NULL,
                    preco REAL NOT NULL,
                    limite_sites INTEGER NOT NULL,
                    historico_dias INTEGER NOT NULL,
                    mp_plan_id TEXT,
                    mp_init_point TEXT,
                    criado_em TIMESTAMP
                        DEFAULT CURRENT_TIMESTAMP,
                    atualizado_em TIMESTAMP
                        DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

        # ------------------------------------------------------
        # ASSINATURAS
        # ------------------------------------------------------

        if database.USANDO_POSTGRES:

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id SERIAL PRIMARY KEY,
                    usuario_id INTEGER NOT NULL,
                    plano_slug TEXT NOT NULL,
                    mp_plan_id TEXT,
                    mp_subscription_id TEXT UNIQUE,
                    status TEXT NOT NULL
                        DEFAULT 'pending',
                    payer_email TEXT,
                    proxima_cobranca TEXT,
                    criado_em TIMESTAMP
                        DEFAULT CURRENT_TIMESTAMP,
                    atualizado_em TIMESTAMP
                        DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (usuario_id)
                        REFERENCES users(id)
                )
                """
            )

        else:

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario_id INTEGER NOT NULL,
                    plano_slug TEXT NOT NULL,
                    mp_plan_id TEXT,
                    mp_subscription_id TEXT UNIQUE,
                    status TEXT NOT NULL
                        DEFAULT 'pending',
                    payer_email TEXT,
                    proxima_cobranca TEXT,
                    criado_em TIMESTAMP
                        DEFAULT CURRENT_TIMESTAMP,
                    atualizado_em TIMESTAMP
                        DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (usuario_id)
                        REFERENCES users(id)
                )
                """
            )

        # ------------------------------------------------------
        # INSERIR PLANOS
        # ------------------------------------------------------

        for slug, plano in PLANOS.items():

            cursor.execute(
                """
                SELECT id
                FROM billing_plans
                WHERE slug = ?
                """,
                (slug,),
            )

            existente = cursor.fetchone()

            if existente:
                continue

            cursor.execute(
                """
                INSERT INTO billing_plans (
                    slug,
                    nome,
                    preco,
                    limite_sites,
                    historico_dias
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    slug,
                    plano["nome"],
                    plano["preco"],
                    plano["limite_sites"],
                    plano["historico_dias"],
                ),
            )

        conexao.commit()

    except Exception:

        conexao.rollback()
        raise

    finally:

        conexao.close()


# ==============================================================
# BUSCAR PLANO
# ==============================================================

def buscar_plano(slug):

    conexao = database.conectar()

    try:

        cursor = conexao.cursor()

        cursor.execute(
            """
            SELECT *
            FROM billing_plans
            WHERE slug = ?
            """,
            (slug,),
        )

        return cursor.fetchone()

    finally:

        conexao.close()


# ==============================================================
# CRIAR PLANO NO MERCADO PAGO
# ==============================================================

def criar_plano_mercado_pago(slug):

    if slug not in PLANOS:

        raise ValueError(
            "Plano inválido."
        )

    plano = PLANOS[slug]

    if plano["preco"] <= 0:

        raise ValueError(
            "O plano gratuito não utiliza checkout."
        )

    base_publica = obter_base_publica()

    payload = {
        "reason": (
            "Cloud Security Monitor - "
            f"Plano {plano['nome']}"
        ),
        "auto_recurring": {
            "frequency": 1,
            "frequency_type": "months",
            "transaction_amount": plano["preco"],
            "currency_id": "BRL",
        },
        "back_url": (
            f"{base_publica}/planos"
        ),
    }

    resultado = mercado_pago_request(
        "POST",
        "/preapproval_plan",
        payload,
    )

    mp_plan_id = resultado.get("id")
    mp_init_point = resultado.get(
        "init_point"
    )

    if not mp_plan_id:

        raise RuntimeError(
            "Mercado Pago não retornou o ID do plano."
        )

    conexao = database.conectar()

    try:

        cursor = conexao.cursor()

        cursor.execute(
            """
            UPDATE billing_plans
            SET
                mp_plan_id = ?,
                mp_init_point = ?,
                atualizado_em = CURRENT_TIMESTAMP
            WHERE slug = ?
            """,
            (
                mp_plan_id,
                mp_init_point,
                slug,
            ),
        )

        conexao.commit()

    except Exception:

        conexao.rollback()
        raise

    finally:

        conexao.close()

    return resultado


# ==============================================================
# OBTER OU CRIAR PLANO MERCADO PAGO
# ==============================================================

def obter_checkout_plano(slug):

    plano = buscar_plano(slug)

    if plano:

        mp_plan_id = plano["mp_plan_id"]
        mp_init_point = plano["mp_init_point"]

        if mp_plan_id and mp_init_point:

            return {
                "id": mp_plan_id,
                "init_point": mp_init_point,
            }

    return criar_plano_mercado_pago(
        slug
    )


# ==============================================================
# REGISTRAR ASSINATURA PENDENTE
# ==============================================================

def registrar_assinatura_pendente(
    usuario_id,
    slug,
    mp_plan_id,
):

    conexao = database.conectar()

    try:

        cursor = conexao.cursor()

        cursor.execute(
            """
            INSERT INTO subscriptions (
                usuario_id,
                plano_slug,
                mp_plan_id,
                status
            )
            VALUES (?, ?, ?, 'pending')
            """,
            (
                usuario_id,
                slug,
                mp_plan_id,
            ),
        )

        conexao.commit()

    except Exception:

        conexao.rollback()

        raise

    finally:

        conexao.close()


# ==============================================================
# BUSCAR USUÁRIO POR E-MAIL
# ==============================================================

def buscar_usuario_email(email):

    if not email:
        return None

    conexao = database.conectar()

    try:

        cursor = conexao.cursor()

        cursor.execute(
            """
            SELECT *
            FROM users
            WHERE email = ?
            """,
            (
                email.strip().lower(),
            ),
        )

        return cursor.fetchone()

    finally:

        conexao.close()


# ==============================================================
# BUSCAR ASSINATURA MERCADO PAGO
# ==============================================================

def buscar_assinatura_mercado_pago(
    subscription_id
):

    return mercado_pago_request(
        "GET",
        f"/preapproval/{subscription_id}",
    )


# ==============================================================
# ATUALIZAR ASSINATURA LOCAL
# ==============================================================

def atualizar_assinatura_local(
    dados
):

    subscription_id = str(
        dados.get("id") or ""
    ).strip()

    if not subscription_id:
        return

    status = str(
        dados.get("status")
        or "pending"
    ).strip().lower()

    payer = dados.get(
        "payer"
    ) or {}

    payer_email = str(
        dados.get("payer_email")
        or payer.get("email")
        or ""
    ).strip().lower()

    mp_plan_id = str(
        dados.get("preapproval_plan_id")
        or ""
    ).strip()

    proxima_cobranca = str(
        dados.get("next_payment_date")
        or ""
    ).strip()

    usuario = None

    if payer_email:

        usuario = buscar_usuario_email(
            payer_email
        )

    if not usuario:
        return

    usuario_id = usuario["id"]

    conexao = database.conectar()

    try:

        cursor = conexao.cursor()

        # ------------------------------------------------------
        # Descobrir plano pelo ID do Mercado Pago
        # ------------------------------------------------------

        cursor.execute(
            """
            SELECT slug
            FROM billing_plans
            WHERE mp_plan_id = ?
            """,
            (
                mp_plan_id,
            ),
        )

        plano = cursor.fetchone()

        if plano:

            plano_slug = plano["slug"]

        else:

            plano_slug = "gratis"

        # ------------------------------------------------------
        # Verificar se assinatura já existe
        # ------------------------------------------------------

        cursor.execute(
            """
            SELECT id
            FROM subscriptions
            WHERE mp_subscription_id = ?
            """,
            (
                subscription_id,
            ),
        )

        existente = cursor.fetchone()

        if existente:

            cursor.execute(
                """
                UPDATE subscriptions
                SET
                    usuario_id = ?,
                    plano_slug = ?,
                    mp_plan_id = ?,
                    status = ?,
                    payer_email = ?,
                    proxima_cobranca = ?,
                    atualizado_em = CURRENT_TIMESTAMP
                WHERE mp_subscription_id = ?
                """,
                (
                    usuario_id,
                    plano_slug,
                    mp_plan_id,
                    status,
                    payer_email,
                    proxima_cobranca,
                    subscription_id,
                ),
            )

        else:

            cursor.execute(
                """
                INSERT INTO subscriptions (
                    usuario_id,
                    plano_slug,
                    mp_plan_id,
                    mp_subscription_id,
                    status,
                    payer_email,
                    proxima_cobranca
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    usuario_id,
                    plano_slug,
                    mp_plan_id,
                    subscription_id,
                    status,
                    payer_email,
                    proxima_cobranca,
                ),
            )

        conexao.commit()

    except Exception:

        conexao.rollback()
        raise

    finally:

        conexao.close()


# ==============================================================
# VALIDAR ASSINATURA DO WEBHOOK
# ==============================================================

def validar_webhook():

    segredo = os.environ.get(
        "MP_WEBHOOK_SECRET",
        "",
    ).strip()

    # Durante desenvolvimento, se o segredo
    # ainda não estiver configurado, aceita.
    #
    # Em produção, configure MP_WEBHOOK_SECRET.
    if not segredo:
        return True

    assinatura = request.headers.get(
        "x-signature",
        "",
    )

    request_id = request.headers.get(
        "x-request-id",
        "",
    )

    data_id = str(
        request.args.get(
            "data.id"
        )
        or ""
    ).lower()

    if not assinatura:
        return False

    partes = {}

    for parte in assinatura.split(","):

        if "=" not in parte:
            continue

        chave, valor = parte.split(
            "=",
            1,
        )

        partes[chave.strip()] = (
            valor.strip()
        )

    timestamp = partes.get(
        "ts"
    )

    assinatura_v1 = partes.get(
        "v1"
    )

    if not timestamp:
        return False

    if not assinatura_v1:
        return False

    if not data_id:
        return False

    manifesto = (
        f"id:{data_id};"
        f"request-id:{request_id};"
        f"ts:{timestamp};"
    )

    assinatura_calculada = hmac.new(
        segredo.encode(),
        manifesto.encode(),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(
        assinatura_calculada,
        assinatura_v1,
    )


# ==============================================================
# STATUS DA ASSINATURA DO USUÁRIO
# ==============================================================

def buscar_status_assinatura(
    usuario_id
):

    conexao = database.conectar()

    try:

        cursor = conexao.cursor()

        cursor.execute(
            """
            SELECT *
            FROM subscriptions
            WHERE usuario_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (
                usuario_id,
            ),
        )

        assinatura = cursor.fetchone()

        if not assinatura:

            return None

        return dict(
            assinatura
        )

    finally:

        conexao.close()


# ==============================================================
# LIMITE DE SITES
# ==============================================================

def obter_plano_usuario(
    usuario_id
):

    assinatura = buscar_status_assinatura(
        usuario_id
    )

    # Sem assinatura paga = gratuito.
    if not assinatura:

        return PLANOS["gratis"]

    status = str(
        assinatura.get(
            "status",
            ""
        )
    ).lower()

    # Estados considerados ativos.
    estados_ativos = {
        "authorized",
        "active",
        "approved",
    }

    if status not in estados_ativos:

        return PLANOS["gratis"]

    slug = assinatura.get(
        "plano_slug"
    )

    return PLANOS.get(
        slug,
        PLANOS["gratis"],
    )


def usuario_pode_adicionar_site(
    usuario_id
):

    plano = obter_plano_usuario(
        usuario_id
    )

    limite = int(
        plano["limite_sites"]
    )

    conexao = database.conectar()

    try:

        cursor = conexao.cursor()

        cursor.execute(
            """
            SELECT COUNT(*) AS total
            FROM sites
            WHERE usuario_id = ?
            """,
            (
                usuario_id,
            ),
        )

        resultado = cursor.fetchone()

        total = int(
            resultado["total"]
        )

        return (
            total < limite,
            total,
            limite,
            plano["nome"],
        )

    finally:

        conexao.close()


# ==============================================================
# REGISTRO DAS ROTAS
# ==============================================================

def registrar_rotas(
    app,
    login_required,
):

    inicializar_billing()

    # ==========================================================
    # PÁGINA DE PLANOS
    # ==========================================================

    @app.route(
        "/planos",
        methods=["GET"],
    )
    def planos():

        usuario_id = session.get(
            "usuario_id"
        )

        assinatura = None

        if usuario_id:

            try:

                assinatura = (
                    buscar_status_assinatura(
                        usuario_id
                    )
                )

            except Exception as erro:

                print(
                    "Aviso ao buscar assinatura: "
                    f"{erro}"
                )

        return render_template(
            "planos.html",
            planos=PLANOS,
            assinatura=assinatura,
            usuario_logado=bool(
                usuario_id
            ),
        )

    # ==========================================================
    # CHECKOUT
    # ==========================================================

    @app.route(
        "/api/billing/checkout/<slug>",
        methods=["GET"],
    )
    @login_required
    def billing_checkout(
        slug
    ):

        if slug not in PLANOS:

            return jsonify({
                "sucesso": False,
                "erro": "Plano inválido.",
            }), 404

        if slug == "gratis":

            return redirect(
                url_for("dashboard")
            )

        usuario_id = session.get(
            "usuario_id"
        )

        if not usuario_id:

            return jsonify({
                "sucesso": False,
                "erro": "Autenticação necessária.",
            }), 401

        try:

            checkout = obter_checkout_plano(
                slug
            )

            mp_plan_id = checkout.get(
                "id"
            )

            init_point = checkout.get(
                "init_point"
            )

            if not mp_plan_id:

                raise RuntimeError(
                    "ID do plano não retornado "
                    "pelo Mercado Pago."
                )

            if not init_point:

                raise RuntimeError(
                    "Link de checkout não retornado "
                    "pelo Mercado Pago."
                )

            registrar_assinatura_pendente(
                usuario_id=usuario_id,
                slug=slug,
                mp_plan_id=mp_plan_id,
            )

            return redirect(
                init_point
            )

        except Exception as erro:

            print(
                "Erro ao iniciar checkout: "
                f"{erro}"
            )

            return jsonify({
                "sucesso": False,
                "erro": (
                    "Não foi possível iniciar "
                    "o pagamento."
                ),
                "detalhes": str(erro),
            }), 503

    # ==========================================================
    # WEBHOOK MERCADO PAGO
    # ==========================================================

    @app.route(
        "/api/billing/webhook",
        methods=["POST"],
    )
    def billing_webhook():

        if not validar_webhook():

            return jsonify({
                "sucesso": False,
                "erro": "Assinatura do webhook inválida.",
            }), 401

        dados = (
            request.get_json(
                silent=True
            )
            or {}
        )

        tipo = str(
            dados.get("type")
            or request.args.get("type")
            or ""
        ).strip()

        data = (
            dados.get("data")
            or {}
        )

        data_id = str(
            data.get("id")
            or request.args.get("data.id")
            or ""
        ).strip()

        try:

            # --------------------------------------------------
            # Assinatura criada / atualizada
            # --------------------------------------------------

            if (
                tipo
                == "subscription_preapproval"
                and data_id
            ):

                assinatura = (
                    buscar_assinatura_mercado_pago(
                        data_id
                    )
                )

                atualizar_assinatura_local(
                    assinatura
                )

            # --------------------------------------------------
            # Plano alterado
            # --------------------------------------------------

            elif (
                tipo
                == "subscription_preapproval_plan"
            ):

                print(
                    "Webhook de plano recebido."
                )

            # --------------------------------------------------
            # Pagamento autorizado
            # --------------------------------------------------

            elif (
                tipo
                == "subscription_authorized_payment"
            ):

                print(
                    "Webhook de pagamento de assinatura recebido."
                )

        except Exception as erro:

            # O webhook responde 200 para evitar
            # reenvios intermináveis enquanto registramos
            # o problema nos logs.
            print(
                "Erro ao processar webhook "
                f"do Mercado Pago: {erro}"
            )

        return jsonify({
            "sucesso": True
        }), 200

    # ==========================================================
    # STATUS DA ASSINATURA
    # ==========================================================

    @app.route(
        "/api/billing/status",
        methods=["GET"],
    )
    @login_required
    def billing_status():

        usuario_id = session.get(
            "usuario_id"
        )

        assinatura = (
            buscar_status_assinatura(
                usuario_id
            )
        )

        plano = obter_plano_usuario(
            usuario_id
        )

        return jsonify({
            "sucesso": True,
            "assinatura": assinatura,
            "plano": {
                "nome": plano["nome"],
                "preco": plano["preco"],
                "limite_sites": plano["limite_sites"],
                "historico_dias": plano["historico_dias"],
            },
        })

    # ==========================================================
    # LIMITE DO PLANO
    # ==========================================================

    @app.route(
        "/api/billing/limite-sites",
        methods=["GET"],
    )
    @login_required
    def billing_limite_sites():

        usuario_id = session.get(
            "usuario_id"
        )

        pode_adicionar, total, limite, nome_plano = (
            usuario_pode_adicionar_site(
                usuario_id
            )
        )

        return jsonify({
            "sucesso": True,
            "pode_adicionar": pode_adicionar,
            "sites_utilizados": total,
            "limite_sites": limite,
            "plano": nome_plano,
        })