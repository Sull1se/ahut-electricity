"""Unit tests for authentication and encryption in ahut_electricity."""

import base64
import hashlib
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from ahut_electricity.auth import (
    RSA_MODULUS,
    RSA_EXPONENT,
    RSA_PUBLIC_KEY_B64,
    encrypt_password,
    extract_page_public_key,
    load_credentials,
    login_service,
    rsa_encrypt_pkcs1v15,
)
from ahut_electricity.client import AhutElectricityClient

# Fingerprint of the key served by https://pay.ahut.edu.cn/Account/Login
# (SHA-256 of the SPKI DER). Kept independent of auth.py on purpose.
EXPECTED_SPKI_SHA256 = "bd3f025b73e2b84ce42b86cebcdb3e8e65c5340b8aa91434060c3c5135957995"
LEGACY_COMMENTED_KEY = "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCCCUg7rT5UBlDcqoISt9PR"


def _der(tag: int, content: bytes) -> bytes:
    n = len(content)
    if n < 0x80:
        length = bytes([n])
    else:
        raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
        length = bytes([0x80 | len(raw)]) + raw
    return bytes([tag]) + length + content


def _der_int(value: int) -> bytes:
    raw = value.to_bytes(value.bit_length() // 8 + 1, "big")  # keeps sign bit clear
    while len(raw) > 1 and raw[0] == 0 and raw[1] < 0x80:
        raw = raw[1:]
    return _der(0x02, raw)


def build_spki_der(n: int, e: int) -> bytes:
    """Encode an RSA SubjectPublicKeyInfo from (n, e), independent of auth.py's parser."""
    algorithm = _der(0x30, _der(0x06, bytes.fromhex("2a864886f70d010101")) + b"\x05\x00")
    rsa_key = _der(0x30, _der_int(n) + _der_int(e))
    return _der(0x30, algorithm + _der(0x03, b"\x00" + rsa_key))


def _login_page(key_b64: str = RSA_PUBLIC_KEY_B64) -> MagicMock:
    """Fake /Account/Login page: a commented-out legacy key, then the active PEM key."""
    page = MagicMock()
    page.status_code = 200
    page.text = (
        "var encrypt = new JSEncrypt();\r\n"
        f'        //encrypt.setPublicKey("{LEGACY_COMMENTED_KEY}");\r\n'
        f'        encrypt.setPublicKey("-----BEGIN PUBLIC KEY-----\\n{key_b64}\\n-----END PUBLIC KEY-----");\r\n'
    )
    return page


class TestAuthAndEncryption(unittest.TestCase):
    def test_rsa_encryption_structure(self):
        # Raw data encryption
        data = b"HelloAHUT"
        encrypted = rsa_encrypt_pkcs1v15(data)
        self.assertEqual(len(encrypted), 256)

        # Test encrypt_password format
        enc_str = encrypt_password("TestPassword123")
        self.assertIsInstance(enc_str, str)
        self.assertEqual(len(enc_str), 344)
        raw_bytes = base64.b64decode(enc_str)
        self.assertEqual(len(raw_bytes), 256)

    def test_public_key_matches_pinned_fingerprint(self):
        # Rebuild the SPKI from the constants actually used for encryption;
        # a single wrong modulus digit changes the hash.
        der = build_spki_der(RSA_MODULUS, RSA_EXPONENT)
        self.assertEqual(hashlib.sha256(der).hexdigest(), EXPECTED_SPKI_SHA256)
        self.assertEqual(RSA_MODULUS.bit_length(), 2047)
        self.assertEqual(RSA_EXPONENT, 65537)

    def test_extract_page_public_key_skips_commented_call(self):
        der = extract_page_public_key(_login_page().text)
        self.assertEqual(hashlib.sha256(der).hexdigest(), EXPECTED_SPKI_SHA256)

    def test_extract_page_public_key_missing(self):
        self.assertIsNone(extract_page_public_key("<html>no key here</html>"))

    def test_login_refused_on_key_mismatch(self):
        other_key = base64.b64encode(build_spki_der(RSA_MODULUS + 2, RSA_EXPONENT)).decode()
        mock_session = MagicMock()
        mock_session.get.return_value = _login_page(other_key)

        res = login_service(mock_session, "20269999", "mypass")
        self.assertFalse(res["success"])
        self.assertEqual(res["code"], -5)
        mock_session.post.assert_not_called()

    def test_load_credentials_from_env(self):
        with patch.dict(os.environ, {"AHUT_USERNAME": "20269999", "AHUT_PASSWORD": "secret_password"}):
            u, p = load_credentials()
            self.assertEqual(u, "20269999")
            self.assertEqual(p, "secret_password")

    def test_load_credentials_from_file(self):
        with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as tmp:
            json.dump({"username": "file_user", "password": "file_password"}, tmp)
            tmp_path = tmp.name

        try:
            with patch.dict(os.environ, {}, clear=True):
                u, p = load_credentials(config_path=tmp_path)
                self.assertEqual(u, "file_user")
                self.assertEqual(p, "file_password")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    @patch("requests.Session.post")
    def test_login_service_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"Code": 0, "Msg": "", "Data": None}
        mock_post.return_value = mock_resp

        mock_session = MagicMock()
        mock_session.get.return_value = _login_page()
        mock_session.post.return_value = mock_resp
        mock_session.cookies.get.side_effect = lambda k, default="": {
            "EF.WAP.Auth": "mock_auth_token",
            "EF.SessionId": "mock_session_id",
        }.get(k, default)

        res = login_service(mock_session, "20269999", "mypass")
        self.assertTrue(res["success"])
        self.assertEqual(res["code"], 0)
        self.assertEqual(res["cookies"]["EF.WAP.Auth"], "mock_auth_token")

    @patch("requests.Session.post")
    def test_login_service_failure(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"Code": 2, "Msg": "用户名或密码错误", "Data": None}

        mock_session = MagicMock()
        mock_session.get.return_value = _login_page()
        mock_session.post.return_value = mock_resp

        res = login_service(mock_session, "20269999", "wrongpass")
        self.assertFalse(res["success"])
        self.assertEqual(res["code"], 2)
        self.assertIn("用户名或密码错误", res["msg"])

    @patch.object(AhutElectricityClient, "login")
    @patch("requests.Session.post")
    def test_auto_login_on_unauthorized_token(self, mock_post, mock_login):
        client = AhutElectricityClient(username="testuser", password="testpass", auto_login=True)
        # Mock initial query returning 10001 (unauthorized), then success on retry
        mock_resp_fail = MagicMock()
        mock_resp_fail.status_code = 200
        mock_resp_fail.json.return_value = {"Code": 10001, "Msg": "用户未授权或授权已经过期", "Data": None}

        mock_resp_succ = MagicMock()
        mock_resp_succ.status_code = 200
        mock_resp_succ.json.return_value = {
            "Code": 0,
            "Msg": "",
            "Data": {
                "room_id": "12345",
                "AllAmp": 1000.00,
                "UsedAmp": 900.00,
                "RemainAmp": 100.00,
            },
        }

        mock_post.side_effect = [mock_resp_fail, mock_resp_succ]
        mock_login.return_value = {"success": True, "code": 0}

        res = client.query_balance("NewS", "26", "101")
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["remain_amp"], 100.00)
        # Called once on __init__, and once on 10001 unauthorized retry
        self.assertEqual(mock_login.call_count, 2)


if __name__ == "__main__":
    unittest.main()
