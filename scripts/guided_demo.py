"""Serve the credential-free guided demo on loopback."""

import argparse
import secrets
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn

from fil_shop.api import create_app
from fil_shop.demo import DemoSettings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default=8000, type=int)
    port = parser.parse_args().port
    static = Path(__file__).resolve().parents[1] / "web" / "dist"
    if not (static / "index.html").is_file():
        parser.error("Build the browser app with make build first")
    origins = (f"http://127.0.0.1:{port}", f"http://localhost:{port}")
    with TemporaryDirectory(prefix="fil-preview-") as directory:
        app = create_app(
            str(Path(directory) / "preview.sqlite"),
            secrets.token_hex(32),
            demo_settings=DemoSettings(origins=origins, static_dir=str(static)),
        )
        uvicorn.run(app, host="127.0.0.1", port=port, proxy_headers=False)


if __name__ == "__main__":
    main()
