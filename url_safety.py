"""Validação básica de destinos públicos para o monitoramento.

Este módulo bloqueia URLs locais, IPs literais e portas não padrão.
A proteção contra DNS rebinding também é aplicada após a resolução DNS,
no próprio monitor e no verificador SSL.
"""
from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit


_SUFFIXES_NAO_PUBLICOS = (
    ".localhost",
    ".local",
    ".internal",
    ".lan",
    ".home.arpa",
    ".test",
)


def validar_url_publica(url: str) -> str:
    """Valida uma URL de website destinada a monitoramento externo.

    Retorna a URL limpa ou lança ValueError com motivo seguro para exibição.
    Por segurança, aceita somente HTTP/HTTPS nas portas padrão e nomes DNS
    públicos; URLs com credenciais ou IP literal são rejeitadas.
    """
    if not isinstance(url, str):
        raise ValueError("Informe uma URL válida.")

    url = url.strip()
    if not url or len(url) > 2048:
        raise ValueError("A URL deve ter entre 1 e 2048 caracteres.")

    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        raise ValueError("A URL informada está malformada.") from None

    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        raise ValueError("Use uma URL que comece com http:// ou https://.")

    if not hostname:
        raise ValueError("A URL precisa conter um domínio válido.")

    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Não inclua usuário ou senha dentro da URL.")

    hostname = hostname.rstrip(".").lower()
    if hostname in {"localhost", "localhost.localdomain"}:
        raise ValueError("Endereços locais não podem ser monitorados.")

    if hostname.endswith(_SUFFIXES_NAO_PUBLICOS):
        raise ValueError("Domínios locais ou internos não podem ser monitorados.")

    try:
        ipaddress.ip_address(hostname.strip("[]"))
    except ValueError:
        pass
    else:
        raise ValueError("Informe um nome de domínio público, não um endereço IP direto.")

    # Bloqueia formatos numéricos alternativos usados por alguns resolvedores
    # como representações de IPv4 (por exemplo, 127.1 ou decimal).
    if hostname and all(ch in "0123456789." for ch in hostname):
        raise ValueError("Endereços IP diretos não podem ser monitorados; informe um domínio público.")

    if "." not in hostname or hostname.startswith(".") or ".." in hostname:
        raise ValueError("Informe um nome de domínio público válido.")

    porta_padrao = 80 if scheme == "http" else 443
    if port is not None and port != porta_padrao:
        raise ValueError("Por segurança, somente as portas HTTP 80 e HTTPS 443 são permitidas.")

    # Impede caracteres de controle e hosts obviamente malformados.
    if any(ord(ch) < 33 or ch in "\\/" for ch in hostname):
        raise ValueError("O domínio informado é inválido.")

    return url


def exigir_ip_publico(ip: str) -> str:
    """Garante que o endereço retornado pelo DNS é globalmente roteável."""
    try:
        endereco = ipaddress.ip_address(str(ip).strip())
    except ValueError:
        raise ValueError("O domínio retornou um endereço IP inválido.") from None

    if not endereco.is_global:
        raise ValueError("O domínio resolveu para um IP privado ou reservado; monitoramento bloqueado.")

    return str(endereco)
