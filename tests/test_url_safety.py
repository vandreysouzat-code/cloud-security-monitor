import unittest

from url_safety import exigir_ip_publico, validar_url_publica


class UrlSafetyTests(unittest.TestCase):
    def test_accepts_public_https_domain(self):
        self.assertEqual(
            validar_url_publica("https://example.com/health"),
            "https://example.com/health",
        )

    def test_rejects_localhost(self):
        with self.assertRaises(ValueError):
            validar_url_publica("http://localhost:5000")

    def test_rejects_private_ip_literal(self):
        with self.assertRaises(ValueError):
            validar_url_publica("http://192.168.1.1")

    def test_rejects_nonstandard_port(self):
        with self.assertRaises(ValueError):
            validar_url_publica("http://example.com:8080")

    def test_rejects_numeric_ipv4_alias(self):
        with self.assertRaises(ValueError):
            validar_url_publica("http://127.1")

    def test_rejects_credentials_in_url(self):
        with self.assertRaises(ValueError):
            validar_url_publica("https://user:password@example.com")

    def test_rejects_non_global_dns_answer(self):
        with self.assertRaises(ValueError):
            exigir_ip_publico("127.0.0.1")
        with self.assertRaises(ValueError):
            exigir_ip_publico("169.254.169.254")

    def test_accepts_global_ipv4(self):
        self.assertEqual(exigir_ip_publico("1.1.1.1"), "1.1.1.1")


if __name__ == "__main__":
    unittest.main()
