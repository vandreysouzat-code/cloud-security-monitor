"""Assina uma distribuicao oficial do Cloud Security Monitor com Ed25519.

Uso do mantenedor:
    python tools/sign_release.py --init   # apenas primeira assinatura/chave
    python tools/sign_release.py --sign   # releases seguintes

A chave privada e guardada fora do repositorio, em ~/.csm-signing, protegida
por senha. Nunca copie a chave privada para o GitHub.
"""
from __future__ import annotations

import argparse
import base64
import getpass
import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from cryptography.exceptions import InvalidKey  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

import release_integrity as integrity  # noqa: E402

PLACEHOLDER = "__PUBLIC_KEY_PLACEHOLDER__"
DEFAULT_KEY_PATH = Path.home() / ".csm-signing" / "cloud-security-monitor-ed25519-private.pem"


def _public_key_b64(private_key: Ed25519PrivateKey) -> str:
    raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode("ascii")


def _load_or_create_key(path: Path, create: bool) -> Ed25519PrivateKey:
    if path.exists():
        password = getpass.getpass("Senha da chave privada: ").encode("utf-8")
        try:
            key = serialization.load_pem_private_key(path.read_bytes(), password=password)
        except (ValueError, TypeError, InvalidKey) as exc:
            raise SystemExit("Nao foi possivel abrir a chave. Confira a senha e o arquivo de backup.") from exc
        if not isinstance(key, Ed25519PrivateKey):
            raise SystemExit("O arquivo indicado nao contem uma chave privada Ed25519.")
        return key

    if not create:
        raise SystemExit(
            f"Chave privada nao encontrada: {path}\n"
            "Nao gere uma chave nova para substituir a chave oficial. Restaure o backup da chave original."
        )

    first = getpass.getpass("Crie uma senha forte para proteger a chave privada: ")
    second = getpass.getpass("Repita a senha: ")
    if len(first) < 12:
        raise SystemExit("Use uma senha com pelo menos 12 caracteres.")
    if first != second:
        raise SystemExit("As senhas nao coincidem. Nenhuma chave foi criada.")

    key = Ed25519PrivateKey.generate()
    path.parent.mkdir(parents=True, exist_ok=True)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.BestAvailableEncryption(first.encode("utf-8")),
    )
    path.write_bytes(pem)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # Windows usa as permissoes ACL da pasta do perfil do usuario.
    print(f"Chave privada criada fora do repositorio: {path}")
    print("Faça uma copia de seguranca offline da chave e guarde a senha separadamente.")
    print("Nunca publique, anexe ou envie a chave privada a ninguem.")
    return key


def _read_public_key_pins() -> dict[str, str]:
    pins: dict[str, str] = {}
    patterns = {
        "release_integrity.py": r'^PUBLIC_KEY_B64 = "([^"]*)"',
        "launch.py": r'^OFFICIAL_RELEASE_PUBLIC_KEY_B64 = "([^"]*)"',
        "api.py": r'^OFFICIAL_RELEASE_PUBLIC_KEY_B64 = "([^"]*)"',
    }
    for filename, pattern in patterns.items():
        text = (PROJECT_ROOT / filename).read_text(encoding="utf-8")
        match = re.search(pattern, text, flags=re.MULTILINE)
        if not match:
            raise SystemExit(f"Nao foi possivel localizar o pin da chave em {filename}.")
        pins[filename] = match.group(1)
    return pins


def _pin_public_key(public_b64: str) -> None:
    specifications = (
        ("release_integrity.py", r'^PUBLIC_KEY_B64 = "[^"]*"', f'PUBLIC_KEY_B64 = "{public_b64}"'),
        ("launch.py", r'^OFFICIAL_RELEASE_PUBLIC_KEY_B64 = "[^"]*"', f'OFFICIAL_RELEASE_PUBLIC_KEY_B64 = "{public_b64}"'),
        ("api.py", r'^OFFICIAL_RELEASE_PUBLIC_KEY_B64 = "[^"]*"', f'OFFICIAL_RELEASE_PUBLIC_KEY_B64 = "{public_b64}"'),
    )
    for filename, pattern, replacement in specifications:
        path = PROJECT_ROOT / filename
        source = path.read_text(encoding="utf-8")
        updated, count = re.subn(pattern, replacement, source, count=1, flags=re.MULTILINE)
        if count != 1:
            raise SystemExit(f"Nao foi possivel fixar a chave publica em {filename}.")
        path.write_text(updated, encoding="utf-8", newline="\n")


def _write_signature(key: Ed25519PrivateKey, key_b64: str) -> None:
    manifest = integrity.criar_manifesto(PROJECT_ROOT)
    manifest_bytes = integrity.serializar_manifesto(manifest)
    signature = key.sign(manifest_bytes)
    (PROJECT_ROOT / integrity.MANIFEST_NAME).write_bytes(manifest_bytes)
    (PROJECT_ROOT / integrity.SIGNATURE_NAME).write_text(
        base64.b64encode(signature).decode("ascii"), encoding="ascii"
    )
    # Verifica a assinatura recem-gerada antes de considerar a operacao concluida.
    integrity.verificar_integridade_release(PROJECT_ROOT, public_key_b64=key_b64)
    print(f"Arquivos protegidos: {len(manifest['files'])}")
    print(f"Manifesto: {integrity.MANIFEST_NAME}")
    print(f"Assinatura: {integrity.SIGNATURE_NAME}")
    print("Assinatura e hashes validados com sucesso.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Assina uma versao oficial do Cloud Security Monitor.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--init", action="store_true", help="Gera a primeira chave e assina a versao inicial.")
    group.add_argument("--sign", action="store_true", help="Assina uma nova versao usando a chave existente.")
    parser.add_argument(
        "--key-path", type=Path, default=DEFAULT_KEY_PATH,
        help="Caminho alternativo para a chave privada (padrao fora do repositorio).",
    )
    args = parser.parse_args()

    pins = _read_public_key_pins()
    distinct_pins = set(pins.values())
    if len(distinct_pins) != 1:
        raise SystemExit("Os pins da chave publica divergem entre launch.py, api.py e release_integrity.py; revise manualmente antes de assinar.")
    pinned = next(iter(distinct_pins))

    if args.init:
        if pinned != PLACEHOLDER and not args.key_path.exists():
            raise SystemExit(
                "Esta copia ja possui uma chave publica oficial fixada, mas a chave privada nao foi encontrada. "
                "Nao inicialize outra chave; restaure a chave privada original."
            )
        key = _load_or_create_key(args.key_path, create=(pinned == PLACEHOLDER))
        derived_public = _public_key_b64(key)
        if pinned not in (PLACEHOLDER, derived_public):
            raise SystemExit("A chave privada nao corresponde a chave publica oficial fixada no codigo.")
        if pinned == PLACEHOLDER:
            _pin_public_key(derived_public)
        _write_signature(key, derived_public)
        print("Primeira assinatura oficial preparada. Revise o diff e publique a chave publica, o manifesto e a assinatura.")
        return 0

    if pinned == PLACEHOLDER:
        raise SystemExit("A chave publica ainda nao foi inicializada. Use --init somente como autor da primeira versao oficial.")
    key = _load_or_create_key(args.key_path, create=False)
    derived_public = _public_key_b64(key)
    if derived_public != pinned:
        raise SystemExit("A chave privada selecionada nao corresponde a chave publica oficial do projeto.")
    _write_signature(key, derived_public)
    print("Nova versao assinada com a chave oficial existente.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except integrity.ReleaseIntegrityError as exc:
        print(f"ERRO DE INTEGRIDADE: {exc}", file=sys.stderr)
        raise SystemExit(2)
