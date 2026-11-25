"""Internal TonAPI URL naming must not change the external endpoint."""

import unittest
from app.integrations.ton_api_urls import ton_api_base_url


class TonApiUrlContract(unittest.TestCase):
    def test_uses_the_required_provider_endpoint(self):
        expected = "https://tonapi.io/v2"
        for value in ("", "https://tonapi.io", "https://tonapi.io/v2/", " https://tonapi.io/ "):
            with self.subTest(value=value):
                self.assertEqual(ton_api_base_url(value), expected)

    def test_accepts_configured_provider_origin(self):
        self.assertEqual(ton_api_base_url("https://api.example.test"), "https://api.example.test/v2")
