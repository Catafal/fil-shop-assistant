"""Uvicorn factory; operational credentials are required rather than defaulted."""

import os
from pathlib import Path

from fil_shop.api import create_app
from fil_shop.demo import DEFAULT_ORIGINS, DemoSettings


def setting(name: str, default: str = "") -> str:
    return os.environ.get(f"FIL_{name}", os.environ.get(f"TELECAT_{name}", default))


def app():
    token_getter = None
    api_key, agent_id = os.environ.get("ELEVENLABS_API_KEY"), os.environ.get("ELEVENLABS_AGENT_ID")
    if api_key and agent_id:
        from elevenlabs import ElevenLabs
        client = ElevenLabs(api_key=api_key)

        def token_getter():
            return client.conversational_ai.conversations.get_webrtc_token(
                agent_id=agent_id, request_options={"timeout_in_seconds": 20, "max_retries": 0},
            )

    origins = setting("DEMO_ORIGINS")
    settings = DemoSettings(
        access_code=setting("DEMO_ACCESS_CODE"),
        origins=tuple(o.strip() for o in origins.split(",")) if origins else DEFAULT_ORIGINS,
        secure_cookies=setting("DEMO_SECURE_COOKIES").lower() == "true",
        static_dir=str(Path(__file__).resolve().parents[2] / "web" / "dist"),
    )
    return create_app(
        os.environ.get("FIL_DB_PATH", "data/fil.sqlite"),
        setting("WEBHOOK_SECRET"),
        token_getter=token_getter, demo_settings=settings,
    )
