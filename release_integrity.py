"""Verificacao de integridade da versao oficial do Cloud Security Monitor.

A assinatura protege o manifesto de hashes com uma chave publica Ed25519 fixa no
codigo. A chave privada de assinatura nunca deve ser guardada neste repositorio.
"""
from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ROOT = Path(__file__).resolve().parent
PUBLIC_KEY_B64 = "FIWhYrETSqIRmVISiPJ7gqdpUde66LFTTsbQvv4dr8E="  # preenchida pelo autor ao assinar a primeira versao
MANIFEST_NAME = "release-manifest.json"
SIGNATURE_NAME = "release-manifest.sig"
SCHEMA_VERSION = 1

STATIC_PROTECTED_FILES = (
    ".dockerignore",
    ".env.example",
    ".gitattributes",
    ".gitignore",
    "Dockerfile",
    "LICENSE",
    "README.md",
    "compose.yaml",
    "requirements.txt",
)
EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "__pycache__", "node_modules", "backups",
    "logs", "uploads", ".pytest_cache", ".mypy_cache",
}
EXCLUDED_FILES = {
    MANIFEST_NAME,
    SIGNATURE_NAME,
    "ver_colunas.py",
    "reset_senha.py",
    "teste_alerta.py",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".db", ".sqlite", ".sqlite3", ".pem", ".key", ".p8", ".log"}


class ReleaseIntegrityError(RuntimeError):
    """A versao local nao corresponde a um manifesto oficial valido."""


def _is_excluded(relative: Path) -> bool:
    parts = relative.parts
    if any(part in EXCLUDED_DIRS for part in parts):
        return True
    name = relative.name
    if name in EXCLUDED_FILES or name == ".env":
        return True
    if name.startswith(".env.") and name != ".env.example":
        return True
    if relative.suffix.lower() in EXCLUDED_SUFFIXES:
        return True
    if "_backup" in name.lower():
        return True
    return False


def coletar_arquivos_protegidos(root: Path | str = ROOT) -> list[str]:
    """Retorna os caminhos relativos a proteger, sem dados locais/segredos.

    Em um checkout Git, considera arquivos versionados e novos que nao estejam
    ignorados. Em um ZIP sem .git, usa os tipos e diretorios da distribuicao.
    """
    root = Path(root).resolve()
    git_marker = root / ".git"
    candidatos: set[str] = set()

    if git_marker.exists():
        try:
            proc = subprocess.run(
                ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard"],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            for raw in proc.stdout.splitlines():
                rel = Path(raw.replace("\\", "/"))
                if rel.is_absolute() or ".." in rel.parts or _is_excluded(rel):
                    continue
                if (root / rel).is_file():
                    candidatos.add(rel.as_posix())
        except (OSError, subprocess.CalledProcessError):
            candidatos.clear()

    if not candidatos:
        for filename in STATIC_PROTECTED_FILES:
            path = root / filename
            if path.is_file():
                rel = Path(filename)
                if not _is_excluded(rel):
                    candidatos.add(rel.as_posix())

        patterns = ("*.py", "templates/**/*.html", "templates/*.html", "tests/**/*.py", "tests/*.py", "tools/**/*.py", "tools/*.py", "static/**/*")
        for pattern in patterns:
            for path in root.glob(pattern):
                if not path.is_file():
                    continue
                try:
                    rel = path.relative_to(root)
                except ValueError:
                    continue
                if not _is_excluded(rel):
                    candidatos.add(rel.as_posix())

    return sorted(candidatos)


TEXT_SUFFIXES = {
    ".py", ".html", ".md", ".txt", ".yaml", ".yml", ".json", ".js",
    ".css", ".svg", ".toml", ".ini", ".cfg", ".sh", ".ps1", ".example",
}
TEXT_FILENAMES = {".gitignore", ".gitattributes", ".dockerignore", "Dockerfile", "LICENSE"}


def sha256_arquivo(path: Path) -> str:
    """Hash de conteudo com EOL canonico para texto e bytes exatos para binarios."""
    if path.suffix.lower() in TEXT_SUFFIXES or path.name in TEXT_FILENAMES:
        data = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        return hashlib.sha256(data).hexdigest()

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for bloco in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def criar_manifesto(root: Path | str = ROOT) -> dict[str, Any]:
    root = Path(root).resolve()
    files = []
    for relative in coletar_arquivos_protegidos(root):
        path = root / relative
        files.append({"path": relative, "sha256": sha256_arquivo(path)})
    return {
        "schema_version": SCHEMA_VERSION,
        "project": "Cloud Security Monitor",
        "algorithm": "Ed25519 + SHA-256",
        "files": files,
    }


def serializar_manifesto(manifesto: dict[str, Any]) -> bytes:
    return (json.dumps(manifesto, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _validar_caminho_manifesto(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ReleaseIntegrityError("O manifesto contem um caminho de arquivo invalido.")
    path = Path(value.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or value.startswith(("/", "\\")):
        raise ReleaseIntegrityError("O manifesto contem um caminho fora da pasta do projeto.")
    return path.as_posix()


def verificar_integridade_release(
    root: Path | str = ROOT,
    public_key_b64: str | None = None,
) -> bool:
    """Verifica assinatura do manifesto e hashes dos arquivos da distribuicao.

    O argumento public_key_b64 existe para testes automatizados. A aplicacao usa
    a chave publica fixa em PUBLIC_KEY_B64.
    """
    root = Path(root).resolve()
    key_text = PUBLIC_KEY_B64 if public_key_b64 is None else public_key_b64
    if not key_text or key_text == "__PUBLIC_KEY_PLACEHOLDER__":
        raise ReleaseIntegrityError(
            "A assinatura oficial ainda nao foi configurada pelo autor. "
            "Nao inicialize uma nova chave em uma copia baixada do projeto."
        )

    manifest_path = root / MANIFEST_NAME
    signature_path = root / SIGNATURE_NAME
    if not manifest_path.is_file() or not signature_path.is_file():
        raise ReleaseIntegrityError(
            "Faltam os arquivos de assinatura da versao oficial. "
            "A copia nao pode ser verificada."
        )

    manifest_bytes = manifest_path.read_bytes()
    signature_text = signature_path.read_text(encoding="ascii").strip()
    try:
        public_raw = base64.b64decode(key_text, validate=True)
        signature = base64.b64decode(signature_text, validate=True)
        public_key = Ed25519PublicKey.from_public_bytes(public_raw)
        public_key.verify(signature, manifest_bytes)
    except (ValueError, TypeError, InvalidSignature) as exc:
        raise ReleaseIntegrityError(
            "A assinatura do manifesto e invalida. O manifesto ou a chave de verificacao pode ter sido alterado."
        ) from exc
    except Exception as exc:
        raise ReleaseIntegrityError("Nao foi possivel validar a assinatura da versao oficial.") from exc

    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseIntegrityError("O manifesto assinado nao e um JSON valido.") from exc

    if manifest.get("schema_version") != SCHEMA_VERSION or not isinstance(manifest.get("files"), list):
        raise ReleaseIntegrityError("A versao do formato do manifesto nao e suportada.")

    expected: dict[str, str] = {}
    for item in manifest["files"]:
        if not isinstance(item, dict):
            raise ReleaseIntegrityError("O manifesto possui uma entrada de arquivo invalida.")
        rel = _validar_caminho_manifesto(item.get("path"))
        digest = item.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ReleaseIntegrityError(f"Hash invalido no manifesto para {rel}.")
        if rel in expected:
            raise ReleaseIntegrityError(f"Arquivo duplicado no manifesto: {rel}.")
        expected[rel] = digest

    actual_paths = set(coletar_arquivos_protegidos(root))
    expected_paths = set(expected)
    extras = sorted(actual_paths - expected_paths)
    missing_from_scan = sorted(expected_paths - actual_paths)
    altered: list[str] = []
    for rel, digest in expected.items():
        path = root / rel
        if not path.is_file():
            altered.append(rel + " (ausente)")
        elif sha256_arquivo(path) != digest:
            altered.append(rel)

    if extras or missing_from_scan or altered:
        details = []
        if altered:
            details.append("alterados/ausentes: " + ", ".join(altered[:8]))
        if extras:
            details.append("arquivos adicionais: " + ", ".join(extras[:8]))
        if missing_from_scan:
            details.append("arquivos nao encontrados: " + ", ".join(missing_from_scan[:8]))
        raise ReleaseIntegrityError(
            "A integridade da versao oficial NAO foi confirmada (" + "; ".join(details) + "). "
            "A marca de autoria pode ter sido removida ou os arquivos podem ter sido modificados. "
            "Nao apresente esta copia como uma versao oficial intacta."
        )

    return True
