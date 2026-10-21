#!/usr/bin/env python3

import json
import os
import random
import struct
import time
import urllib.error
import urllib.parse
import urllib.request
import xmlrpc.client
import zlib
from pathlib import Path


TARGET_URL = os.getenv("TARGET_URL", "http://nginx").rstrip("/")
SITE_URL = os.getenv("SITE_URL", "http://localhost:8080").rstrip("/")
HOST_HEADER = os.getenv("SITE_HOST_HEADER", "localhost:8080")
ADMIN_USER = os.getenv("WP_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ["WP_ADMIN_PASSWORD"]
ADMIN_EMAIL = os.getenv("WP_ADMIN_EMAIL", "admin@example.com")
SITE_TITLE = os.getenv("WP_SITE_TITLE", "WordPress Load Test")

UPLOAD_DIR = Path("/var/www/html/wp-content/uploads/load-tests")
RUNTIME_DIR = Path("/work/runtime")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


def request(path, data=None, timeout=20):
    headers = {"Host": HOST_HEADER, "User-Agent": "wordpress-load-test-setup/1.0"}
    if data is not None:
        data = urllib.parse.urlencode(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(f"{TARGET_URL}{path}", data=data, headers=headers)
    try:
        with OPENER.open(req, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        if exc.code in (301, 302, 303, 307, 308):
            return exc.code, exc.read()
        raise


def wait_for_wordpress():
    for attempt in range(60):
        try:
            status, _ = request("/wp-admin/install.php")
            if status in (200, 301, 302, 303):
                return
        except (OSError, urllib.error.URLError):
            pass
        print(f"Aguardando WordPress... ({attempt + 1}/60)")
        time.sleep(2)
    raise RuntimeError("WordPress nao ficou disponivel dentro do tempo esperado")


def install_wordpress():
    status, body = request("/wp-admin/install.php")
    text = body.decode("utf-8", errors="ignore")
    if "Already Installed" in text or "já está instalado" in text:
        print("WordPress ja estava instalado.")
        return

    form = {
        "weblog_title": SITE_TITLE,
        "user_name": ADMIN_USER,
        "admin_password": ADMIN_PASSWORD,
        "admin_password2": ADMIN_PASSWORD,
        "pw_weak": "on",
        "admin_email": ADMIN_EMAIL,
        "blog_public": "0",
        "Submit": "Install WordPress",
        "language": "pt_BR",
    }
    request("/wp-admin/install.php?step=2", data=form)
    print("Instalacao inicial do WordPress enviada.")


def xmlrpc_call(method, *params):
    payload = xmlrpc.client.dumps(params, methodname=method, allow_none=True).encode()
    req = urllib.request.Request(
        f"{TARGET_URL}/xmlrpc.php",
        data=payload,
        headers={
            "Host": HOST_HEADER,
            "Content-Type": "text/xml",
            "User-Agent": "wordpress-load-test-setup/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        values, _ = xmlrpc.client.loads(response.read())
    return values[0] if values else None


def wait_for_xmlrpc():
    for attempt in range(30):
        try:
            xmlrpc_call("wp.getPosts", 0, ADMIN_USER, ADMIN_PASSWORD, {"number": 1})
            return
        except Exception as exc:
            if attempt == 29:
                raise RuntimeError(f"XML-RPC indisponivel: {exc}") from exc
            time.sleep(2)


def png_chunk(kind, data):
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def create_png(path, width, height, seed):
    rng = random.Random(seed)
    raw = bytearray()
    for _ in range(height):
        raw.append(0)
        raw.extend(rng.randbytes(width * 3))

    compressed = zlib.compress(bytes(raw), level=0)
    png = b"\x89PNG\r\n\x1a\n"
    png += png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += png_chunk(b"IDAT", compressed)
    png += png_chunk(b"IEND", b"")
    path.write_bytes(png)
    print(f"Criado {path.name}: {len(png) / 1024:.1f} KiB")


def build_text(size_bytes=400 * 1024):
    paragraph = (
        "Testes de carga ajudam a medir latencia, vazao e estabilidade de uma "
        "aplicacao web sob diferentes niveis de concorrencia. Este conteudo foi "
        "gerado especificamente para o cenario de texto do experimento com Locust. "
    )
    parts = []
    current = 0
    while current < size_bytes:
        block = f"<p>{paragraph}</p>\n"
        parts.append(block)
        current += len(block.encode("utf-8"))
    return "".join(parts)


def upsert_post(slug, title, content):
    posts = xmlrpc_call(
        "wp.getPosts",
        0,
        ADMIN_USER,
        ADMIN_PASSWORD,
        {"post_type": "post", "number": 100},
    )
    post = {
        "post_type": "post",
        "post_status": "publish",
        "post_title": title,
        "post_name": slug,
        "post_content": content,
        "comment_status": "closed",
    }
    for existing in posts:
        if existing.get("post_name") == slug:
            post_id = str(existing["post_id"])
            xmlrpc_call("wp.editPost", 0, ADMIN_USER, ADMIN_PASSWORD, post_id, post)
            return post_id
    return str(xmlrpc_call("wp.newPost", 0, ADMIN_USER, ADMIN_PASSWORD, post))


def canonical_post_path(post_id):
    post = xmlrpc_call("wp.getPost", 0, ADMIN_USER, ADMIN_PASSWORD, post_id)
    link = post.get("link", "")
    parsed = urllib.parse.urlsplit(link)
    if parsed.path:
        return parsed.path + (f"?{parsed.query}" if parsed.query else "")
    return f"/?p={post_id}"


def main():
    wait_for_wordpress()
    install_wordpress()
    wait_for_xmlrpc()

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    image_1mb = UPLOAD_DIR / "imagem-1mb.png"
    image_300kb = UPLOAD_DIR / "imagem-300kb.png"
    create_png(image_1mb, 600, 583, seed=1000)
    create_png(image_300kb, 320, 320, seed=300)

    asset_1mb = "/wp-content/uploads/load-tests/imagem-1mb.png"
    asset_300kb = "/wp-content/uploads/load-tests/imagem-300kb.png"

    post_1mb = upsert_post(
        "cenario-imagem-1mb",
        "Cenario 1 - Imagem de aproximadamente 1 MB",
        f'<p>Post utilizado no teste de carga.</p><img src="{SITE_URL}{asset_1mb}" alt="Imagem de 1 MB">',
    )
    post_text = upsert_post(
        "cenario-texto-400kb",
        "Cenario 2 - Texto de aproximadamente 400 KB",
        build_text(),
    )
    post_300kb = upsert_post(
        "cenario-imagem-300kb",
        "Cenario 3 - Imagem de aproximadamente 300 KB",
        f'<p>Post utilizado no teste de carga.</p><img src="{SITE_URL}{asset_300kb}" alt="Imagem de 300 KB">',
    )

    scenarios = {
        "imagem_1mb": {"post_path": canonical_post_path(post_1mb), "asset_path": asset_1mb},
        "texto_400kb": {"post_path": canonical_post_path(post_text), "asset_path": None},
        "imagem_300kb": {"post_path": canonical_post_path(post_300kb), "asset_path": asset_300kb},
    }
    output = RUNTIME_DIR / "scenarios.json"
    output.write_text(json.dumps(scenarios, indent=2) + "\n", encoding="utf-8")
    print(f"Cenarios preparados em {output}")
    print(json.dumps(scenarios, indent=2))


if __name__ == "__main__":
    main()
