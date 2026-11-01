"""Authentication and RSA encryption utilities for AHUT Electricity Service."""

import base64
import binascii
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import requests

# AHUT Cloud URP 2048-bit RSA public key (SubjectPublicKeyInfo, base64 DER).
# Same key the login page passes to JSEncrypt setPublicKey(); see docs/architecture.md §2.3.
RSA_PUBLIC_KEY_B64 = (
    "MIIBITANBgkqhkiG9w0BAQEFAAOCAQ4AMIIBCQKCAQBwpjFh5e65q6X/L3aRYGLs"
    "D2+jvGlzcQ/gwyeZSx/vvbLKf/OcqoUxWst6I8FVfChflFKrWpz2K9GWTeE+be1F"
    "SD83abG0TXE6xL7UX6+gbkU+1KfcbZjI8KOx4NJkY2+NG8CQ0g/MrEnYs1lA2j5b"
    "84byjPrLycoDg5Ia6yIpad5xFmRLJkwCZB4HdhvpPxDvrR6QtIhz5Q0qM2dSdXeM"
    "O11FidTZ9C3bARZ+CqysBTr77Z2NaOhUwSBvvZt/jpbkErSe9Fbv5efH7mVK+w9q"
    "PU/zYkUHKFzd1LVlbm1UQMeKCLwHtMyxMHugiOORT7J1hCFeVfU1/UlmSdEFNFK/"
    "AgMBAAE="
)
# SHA-256 of the SPKI DER above; used to pin the key and to check the login page.
RSA_PUBLIC_KEY_SHA256 = "bd3f025b73e2b84ce42b86cebcdb3e8e65c5340b8aa91434060c3c5135957995"

_RSA_ENCRYPTION_OID = bytes.fromhex("2a864886f70d010101")  # 1.2.840.113549.1.1.1


def _der_read(buf: bytes, pos: int, expected_tag: int) -> Tuple[int, int]:
    """Read one DER TLV at pos; return (content_start, content_end)."""
    if pos >= len(buf) or buf[pos] != expected_tag:
        raise ValueError(f"DER 解析失败：偏移 {pos} 处期望标签 0x{expected_tag:02x}")
    pos += 1
    length = buf[pos]
    pos += 1
    if length & 0x80:
        num_bytes = length & 0x7F
        if num_bytes == 0 or num_bytes > 4:
            raise ValueError("DER 解析失败：不支持的长度编码")
        length = int.from_bytes(buf[pos:pos + num_bytes], "big")
        pos += num_bytes
    end = pos + length
    if end > len(buf):
        raise ValueError("DER 解析失败：长度越界")
    return pos, end


def parse_rsa_public_key(spki_der: bytes) -> Tuple[int, int]:
    """
    Parse an RSA SubjectPublicKeyInfo (X.509 / PEM "PUBLIC KEY") DER blob.
    Returns (modulus, exponent). Pure Python standard library.
    """
    start, end = _der_read(spki_der, 0, 0x30)  # SubjectPublicKeyInfo
    if end != len(spki_der):
        raise ValueError("DER 解析失败：存在多余数据")
    alg_start, alg_end = _der_read(spki_der, start, 0x30)  # AlgorithmIdentifier
    oid_start, oid_end = _der_read(spki_der, alg_start, 0x06)
    if spki_der[oid_start:oid_end] != _RSA_ENCRYPTION_OID:
        raise ValueError("公钥算法不是 rsaEncryption")
    bits_start, bits_end = _der_read(spki_der, alg_end, 0x03)  # BIT STRING
    if spki_der[bits_start] != 0:
        raise ValueError("DER 解析失败：BIT STRING 含未用位")
    rsa_start, _ = _der_read(spki_der, bits_start + 1, 0x30)  # RSAPublicKey
    n_start, n_end = _der_read(spki_der, rsa_start, 0x02)
    e_start, e_end = _der_read(spki_der, n_end, 0x02)
    n = int.from_bytes(spki_der[n_start:n_end], "big")
    e = int.from_bytes(spki_der[e_start:e_end], "big")
    return n, e


def public_key_fingerprint(spki_der: bytes) -> str:
    """Return the hex SHA-256 of an SPKI DER blob."""
    return hashlib.sha256(spki_der).hexdigest()


_RSA_PUBLIC_KEY_DER = base64.b64decode(RSA_PUBLIC_KEY_B64)
if public_key_fingerprint(_RSA_PUBLIC_KEY_DER) != RSA_PUBLIC_KEY_SHA256:
    raise RuntimeError("内置 RSA 公钥与固定指纹不一致，源码可能被误改")
RSA_MODULUS, RSA_EXPONENT = parse_rsa_public_key(_RSA_PUBLIC_KEY_DER)


def extract_page_public_key(html: str) -> Optional[bytes]:
    """
    Extract the SPKI DER of the key the login page passes to JSEncrypt.
    Accepts a bare base64 string or a PEM block (with real or escaped newlines).
    Calls commented out with // are skipped (the page keeps an old 1024-bit key
    that way); if several remain, the last one wins, as it does in JSEncrypt.
    Returns None when no key is found.
    """
    candidate = None
    for match in re.finditer(r"""setPublicKey\(\s*(['"])(.+?)\1""", html, re.S):
        line_start = html.rfind("\n", 0, match.start()) + 1
        if "//" in html[line_start:match.start()]:
            continue
        candidate = match.group(2)
    if candidate is None:
        fallback = re.search(r"MIIB[0-9A-Za-z+/=\s\\]{300,}", html)
        candidate = fallback.group(0) if fallback else None
    if candidate is None:
        return None
    body = re.sub(r"-----(BEGIN|END) PUBLIC KEY-----", "", candidate)
    body = body.replace("\\n", "").replace("\\r", "")  # JS-escaped newlines
    body = re.sub(r"\s+", "", body)
    try:
        return base64.b64decode(body, validate=True)
    except (ValueError, binascii.Error):
        return None


def verify_login_page_key(
    session: requests.Session,
    base_url: str = "https://pay.ahut.edu.cn",
) -> Tuple[bool, str]:
    """
    GET /Account/Login and check that its public key matches RSA_PUBLIC_KEY_SHA256.
    Returns (ok, message).
    """
    url = f"{base_url.rstrip('/')}/Account/Login"
    try:
        resp = session.get(url, timeout=10)
    except requests.RequestException as e:
        return False, f"获取登录页失败: {e}"
    if resp.status_code != 200:
        return False, f"获取登录页 HTTP 错误: {resp.status_code}"
    der = extract_page_public_key(resp.text)
    if der is None:
        return False, "登录页中未找到 RSA 公钥，页面结构可能已变化"
    fingerprint = public_key_fingerprint(der)
    if fingerprint != RSA_PUBLIC_KEY_SHA256:
        return False, f"登录页公钥指纹 {fingerprint} 与内置值不一致，学校可能已更换公钥"
    return True, "公钥一致"


def rsa_encrypt_pkcs1v15(data: bytes, n: int = RSA_MODULUS, e: int = RSA_EXPONENT) -> bytes:
    """
    Encrypt arbitrary data using RSA with PKCS#1 v1.5 padding (RFC 2313).
    Zero external dependencies (pure Python standard library).
    """
    k = (n.bit_length() + 7) // 8  # 256 bytes for 2048-bit RSA
    ps_len = k - 3 - len(data)
    if ps_len < 8:
        raise ValueError(f"数据过长（{len(data)} 字节），无法放入 2048 位 RSA 块中")

    # Generate non-zero random bytes for PS
    ps = bytearray()
    while len(ps) < ps_len:
        raw_bytes = os.urandom(ps_len - len(ps))
        ps.extend(b for b in raw_bytes if b != 0)

    em = b"\x00\x02" + bytes(ps) + b"\x00" + data
    m_int = int.from_bytes(em, "big")
    c_int = pow(m_int, e, n)
    return c_int.to_bytes(k, "big")


def encrypt_password(raw_password: str) -> str:
    """
    Replicate frontend Cloud URP password encryption:
    1. Base64 encode the UTF-8 password string
    2. Encrypt with RSA-2048 PKCS#1 v1.5 padding using the public key
    3. Base64 encode the resulting 256-byte ciphertext
    """
    b64_pwd = base64.b64encode(raw_password.encode("utf-8"))
    encrypted_bytes = rsa_encrypt_pkcs1v15(b64_pwd)
    return base64.b64encode(encrypted_bytes).decode("utf-8")


def load_credentials(
    config_path: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Load credentials from:
    1. Environment variables: AHUT_USERNAME, AHUT_PASSWORD
    2. Local JSON config file (config.json) if present
    Returns (username, password) or (None, None).
    """
    username = os.environ.get("AHUT_USERNAME")
    password = os.environ.get("AHUT_PASSWORD")
    if username and password:
        return username.strip(), password.strip()

    # Search for config.json
    candidates = []
    if config_path:
        candidates.append(Path(config_path))
    candidates.append(Path.cwd() / "config.json")
    candidates.append(Path(__file__).resolve().parent.parent / "config.json")

    for path in candidates:
        if path.is_file():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    u = cfg.get("username")
                    p = cfg.get("password")
                    if u and p:
                        return str(u).strip(), str(p).strip()
            except Exception:
                pass

    return username, password


def login_service(
    session: requests.Session,
    username: str,
    password: str,
    base_url: str = "https://pay.ahut.edu.cn",
    vcode: str = "",
    verify_key: bool = True,
) -> Dict[str, Any]:
    """
    Perform authentication against /Account/LoginService.
    When verify_key is True, the login page's public key is checked first and
    login is refused on mismatch (code -5) instead of silently failing.
    On success, session.cookies will contain EF.WAP.Auth and EF.SessionId.
    """
    if verify_key:
        ok, key_msg = verify_login_page_key(session, base_url)
        if not ok:
            return {
                "success": False,
                "code": -5,
                "msg": f"拒绝登录：{key_msg}",
                "cookies": {},
            }

    url = f"{base_url.rstrip('/')}/Account/LoginService"
    encrypted_pwd = encrypt_password(password)

    payload = {
        "username": username.strip(),
        "pwd": encrypted_pwd,
    }
    if vcode:
        payload["vcode"] = vcode.strip()

    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{base_url.rstrip('/')}/Account/Login",
    }

    try:
        resp = session.post(url, data=payload, headers=headers, timeout=10)
    except requests.RequestException as e:
        return {
            "success": False,
            "code": -1,
            "msg": f"登录网络请求失败: {e}",
            "cookies": {},
        }

    if resp.status_code != 200:
        return {
            "success": False,
            "code": resp.status_code,
            "msg": f"登录 HTTP 错误: {resp.status_code}",
            "cookies": {},
        }

    try:
        data = resp.json()
    except ValueError:
        return {
            "success": False,
            "code": -3,
            "msg": f"登录返回内容非 JSON: {resp.text[:200]}",
            "cookies": {},
        }

    code = data.get("Code", -1)
    msg = data.get("Msg", "")

    if code == 0:
        cookies_dict = {
            "EF.WAP.Auth": session.cookies.get("EF.WAP.Auth", ""),
            "EF.SessionId": session.cookies.get("EF.SessionId", ""),
        }
        return {
            "success": True,
            "code": 0,
            "msg": "登录成功",
            "cookies": cookies_dict,
        }
    else:
        return {
            "success": False,
            "code": code,
            "msg": msg or f"登录失败 (错误代码 {code})",
            "cookies": {},
        }
