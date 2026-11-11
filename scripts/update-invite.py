#!/usr/bin/env python3
"""update-invite.py — Buzz コミュニティの招待リンクを発行し、index.html を自動更新するスクリプト。

外部依存パッケージなし (標準ライブラリのみで動作)。
NIP-98 署名付き POST リクエストを Relay API に送信し、有効期限最大30日の招待リンクを取得して index.html を書き換えます。
"""

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import uuid

P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
GX = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
GY = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8

_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def _inv(a, m=P):
    return pow(a, m - 2, m)


def _add(p, q):
    if p is None:
        return q
    if q is None:
        return p
    if p[0] == q[0] and (p[1] + q[1]) % P == 0:
        return None
    if p == q:
        lam = 3 * p[0] * p[0] % P * _inv(2 * p[1] % P) % P
    else:
        lam = (q[1] - p[1]) % P * _inv((q[0] - p[0]) % P) % P
    x = (lam * lam - p[0] - q[0]) % P
    return (x, (lam * (p[0] - x) - p[1]) % P)


def _mul(k, point=(GX, GY)):
    result, addend = None, point
    while k:
        if k & 1:
            result = _add(result, addend)
        addend = _add(addend, addend)
        k >>= 1
    return result


def _tagged_hash(tag, msg):
    th = hashlib.sha256(tag.encode()).digest()
    return hashlib.sha256(th + th + msg).digest()


def pubkey_hex(sk):
    return _mul(sk)[0].to_bytes(32, "big").hex()


def schnorr_sign(msg32, sk, aux=None):
    aux = aux or os.urandom(32)
    pt = _mul(sk)
    d = sk if pt[1] % 2 == 0 else N - sk
    t = (d ^ int.from_bytes(_tagged_hash("BIP0340/aux", aux), "big")).to_bytes(32, "big")
    k0 = int.from_bytes(_tagged_hash("BIP0340/nonce", t + pt[0].to_bytes(32, "big") + msg32), "big") % N
    if k0 == 0:
        raise RuntimeError("nonce is zero")
    r = _mul(k0)
    k = k0 if r[1] % 2 == 0 else N - k0
    e = int.from_bytes(_tagged_hash("BIP0340/challenge", r[0].to_bytes(32, "big") + pt[0].to_bytes(32, "big") + msg32), "big") % N
    return r[0].to_bytes(32, "big") + ((k + e * d) % N).to_bytes(32, "big")


def _bech32_polymod(values):
    gen = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for v in values:
        b = chk >> 25
        chk = (chk & 0x1FFFFFF) << 5 ^ v
        for i in range(5):
            chk ^= gen[i] if ((b >> i) & 1) else 0
    return chk


def nsec_to_hex(nsec):
    nsec = nsec.strip().lower()
    pos = nsec.rfind("1")
    hrp, data = nsec[:pos], [_CHARSET.find(c) for c in nsec[pos + 1:]]
    expand = [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp]
    if _bech32_polymod(expand + data) != 1:
        raise ValueError("bad bech32 checksum")
    acc = bits = 0
    out = bytearray()
    for v in data[:-6]:
        acc = (acc << 5) | v
        bits += 5
        while bits >= 8:
            bits -= 8
            out.append((acc >> bits) & 0xFF)
    if len(out) != 32:
        raise ValueError("nsec payload is not 32 bytes")
    return out.hex()


def nip98_header(sk, method, url, body):
    tags = [
        ["u", url],
        ["method", method],
        ["nonce", str(uuid.uuid4())],
        ["payload", hashlib.sha256(body).hexdigest()],
    ]
    event = [0, pubkey_hex(sk), int(time.time()), 27235, tags, ""]
    eid = hashlib.sha256(json.dumps(event, separators=(",", ":"), ensure_ascii=False).encode()).digest()
    signed = {
        "id": eid.hex(),
        "pubkey": event[1],
        "created_at": event[2],
        "kind": 27235,
        "tags": tags,
        "content": "",
        "sig": schnorr_sign(eid, sk).hex(),
    }
    raw = json.dumps(signed, separators=(",", ":"), ensure_ascii=False).encode()
    return "Nostr " + base64.b64encode(raw).decode()


def fetch_invite(relay_url, private_key_str, ttl_hours=720.0, max_uses=None):
    """Relay API から招待リンク情報を取得する"""
    key = private_key_str.strip()
    sk = int(nsec_to_hex(key) if key.lower().startswith("nsec") else key, 16)
    if not (0 < sk < N):
        raise ValueError("private key is out of range")

    url = relay_url.rstrip("/") + "/api/invites"
    payload = {}
    if ttl_hours is not None:
        payload["ttl_secs"] = int(ttl_hours * 3600)
    if max_uses is not None:
        payload["max_uses"] = max_uses
    body = json.dumps(payload, separators=(",", ":")).encode()

    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "buzz-cli/0.0.0")  # Cloudflare ブロック対策
    req.add_header("Authorization", nip98_header(sk, "POST", url, body))
    if os.environ.get("BUZZ_AUTH_TAG"):
        req.add_header("x-auth-tag", os.environ["BUZZ_AUTH_TAG"])

    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def update_html(html_path, new_url):
    """index.html 内のコミュニティ招待URLを置換する"""
    if not os.path.exists(html_path):
        raise FileNotFoundError(f"Target HTML not found: {html_path}")

    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()

    # https://png.communities.buzz.xyz/invite/v2.XXXX 形式にマッチ
    pattern = re.compile(r"https://png\.communities\.buzz\.xyz/invite/v2\.[a-zA-Z0-9_\.-]+")
    matches = pattern.findall(content)

    if not matches:
        raise RuntimeError("No invite links found in target HTML.")

    new_content, count = pattern.subn(new_url, content)
    print(f"Replaced {count} invite link(s) in {html_path}")

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(new_content)


def main():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    default_html = os.path.join(repo_root, "index.html")

    ap = argparse.ArgumentParser(description="Update community invite link in index.html")
    ap.add_argument("--relay", default=os.environ.get("BUZZ_RELAY_URL", "https://png.communities.buzz.xyz"))
    ap.add_argument("--private-key", default=None, help="Buzz admin private key (nsec or hex)")
    ap.add_argument("--ttl-hours", type=float, default=720.0, help="TTL in hours (default: 720 = 30 days)")
    ap.add_argument("--max-uses", type=int, default=None, help="Max uses (default: unlimited)")
    ap.add_argument("--html-path", default=default_html, help="Path to index.html")
    ap.add_argument("--dry-run", action="store_true", help="Print invite without updating file")
    args = ap.parse_args()

    key = (args.private_key or os.environ.get("BUZZ_PRIVATE_KEY", "")).strip()
    if not key:
        print("Error: BUZZ_PRIVATE_KEY environment variable or --private-key argument is required", file=sys.stderr)
        return 1

    try:
        data = fetch_invite(args.relay, key, ttl_hours=args.ttl_hours, max_uses=args.max_uses)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode(errors='replace')}", file=sys.stderr)
        return 2 if e.code >= 500 else 1
    except urllib.error.URLError as e:
        print(f"Relay unreachable: {e.reason}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    new_url = data["url"]
    expires_str = time.strftime("%Y-%m-%d %H:%M %Z", time.localtime(data["expires_at"]))
    print(f"New invite URL: {new_url}")
    print(f"Expires at:     {expires_str}")

    if args.dry_run:
        print("[Dry Run] Skipped updating HTML file.")
        return 0

    try:
        update_html(args.html_path, new_url)
    except Exception as e:
        print(f"Failed to update HTML: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
