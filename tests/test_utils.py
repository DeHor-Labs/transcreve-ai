"""
Testes para utilidades basicas usadas pelo fluxo de indice/duplica.
"""

from __future__ import annotations

import unittest


class TestSha256Url(unittest.TestCase):
    def test_sha256_url_rejeita_scheme_nao_suportado(self) -> None:
        from video_kb.utils import sha256_url

        with self.assertRaises(ValueError):
            sha256_url("ftp://example.com/video")

    def test_sha256_url_sem_scheme_preserva_case(self) -> None:
        from video_kb.utils import sha256_url

        a = sha256_url("Videos/Arquivo.MP4")
        b = sha256_url("videos/Arquivo.MP4")
        self.assertNotEqual(a, b)

    def test_sha256_url_http_normaliza_tomando_http_https(self) -> None:
        from video_kb.utils import sha256_url

        h1 = sha256_url("https://example.com/v?utm_source=x&utm_medium=y")
        h2 = sha256_url("https://example.com/v")
        self.assertEqual(h1, h2)


if __name__ == "__main__":
    unittest.main()
