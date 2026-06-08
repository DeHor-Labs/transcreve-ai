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

    def test_sha256_url_youtube_equivalentes(self) -> None:
        from video_kb.utils import sha256_url

        h1 = sha256_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ&utm_source=x")
        h2 = sha256_url("https://youtu.be/dQw4w9WgXcQ")
        h3 = sha256_url("https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ")

        self.assertEqual(h1, h2)
        self.assertEqual(h1, h3)

    def test_sha256_url_youtube_id_invalido_cai_no_fallback(self) -> None:
        from video_kb.utils import sha256_url

        h1 = sha256_url("https://www.youtube.com/watch?v=curto")
        h2 = sha256_url("https://youtu.be/curto")

        self.assertNotEqual(h1, h2)

    def test_sha256_url_vimeo_player_equivalente(self) -> None:
        from video_kb.utils import sha256_url

        h1 = sha256_url("https://vimeo.com/123456789/deadbeef")
        h2 = sha256_url("https://player.vimeo.com/video/123456789")

        self.assertEqual(h1, h2)


class TestUniqueStrings(unittest.TestCase):
    def test_unique_strings_preserva_falsy_significativo(self) -> None:
        from video_kb.utils import unique_strings

        self.assertEqual(unique_strings([None, "", 0, "0", False, "false"]), ["0", "False"])


if __name__ == "__main__":
    unittest.main()
