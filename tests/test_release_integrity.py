import base64
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from release_integrity import (
    ReleaseIntegrityError,
    criar_manifesto,
    serializar_manifesto,
    verificar_integridade_release,
)


class ReleaseIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "templates").mkdir()
        (self.root / "README.md").write_text("Projeto por Victor Andrey\n", encoding="utf-8")
        (self.root / "LICENSE").write_text("Atribuicao obrigatoria\n", encoding="utf-8")
        (self.root / "release_integrity.py").write_text("verificador oficial\n", encoding="utf-8")
        (self.root / "templates" / "_creator_brand.html").write_text(
            "Desenvolvido por Victor Andrey\n", encoding="utf-8"
        )
        self.private_key = Ed25519PrivateKey.generate()
        raw_public = self.private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        self.public_key_b64 = base64.b64encode(raw_public).decode("ascii")
        self._sign_fixture()

    def tearDown(self):
        self.temp.cleanup()

    def _sign_fixture(self):
        raw = serializar_manifesto(criar_manifesto(self.root))
        signature = self.private_key.sign(raw)
        (self.root / "release-manifest.json").write_bytes(raw)
        (self.root / "release-manifest.sig").write_text(
            base64.b64encode(signature).decode("ascii"), encoding="ascii"
        )

    def test_accepts_untampered_release(self):
        self.assertTrue(verificar_integridade_release(self.root, self.public_key_b64))

    def test_detects_watermark_removal(self):
        (self.root / "templates" / "_creator_brand.html").write_text("", encoding="utf-8")
        with self.assertRaisesRegex(ReleaseIntegrityError, "integridade.*NAO foi confirmada"):
            verificar_integridade_release(self.root, self.public_key_b64)

    def test_detects_manifest_tampering(self):
        path = self.root / "release-manifest.json"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(ReleaseIntegrityError, "assinatura.*invalida"):
            verificar_integridade_release(self.root, self.public_key_b64)

    def test_detects_unlisted_source_file(self):
        (self.root / "extra.py").write_text("print('extra')\n", encoding="utf-8")
        with self.assertRaisesRegex(ReleaseIntegrityError, "arquivos adicionais"):
            verificar_integridade_release(self.root, self.public_key_b64)


if __name__ == "__main__":
    unittest.main()
