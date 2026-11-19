"""Run isolated real shop tools for native evaluations, never the browser demo server."""

import argparse
import os
from pathlib import Path

import uvicorn

from fil_shop.evaluation import create_evaluation_app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True,
                        help="Fresh inventory directory; existing marked roots require --resume")
    parser.add_argument("--resume", action="store_true", help="Preserve and reopen an existing evaluation run")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    secret = os.environ.get("FIL_EVALUATION_WEBHOOK_SECRET", "")
    app = create_evaluation_app(args.root, secret, resume=args.resume)
    uvicorn.run(app, host=args.host, port=args.port, proxy_headers=False)


if __name__ == "__main__":
    main()
