# Run Fil with live voice

Install the dependencies and build the browser app first. See the [README](../README.md#run-locally).

## Start the local app

Create `.env` from [`.env.example`](../.env.example) if you do not already have one. Set `FIL_WEBHOOK_SECRET` to a locally generated value of at least 32 ASCII characters. For example, use `openssl rand -hex 32`. `FIL_DB_PATH` defaults to `data/fil.sqlite`. Older private configurations can still use their original webhook and demo variables. The current names take precedence.

```sh
make run
```

Open [Fil on localhost](http://127.0.0.1:8000). The page renders before you configure voice. For frontend development, run `npm --prefix web run dev` alongside the API. The development server proxies `/demo` requests.

## Connect an agent

1. Make the shop API reachable from ElevenLabs at an HTTPS origin you control. Configure `FIL_DEMO_ACCESS_CODE`, `FIL_DEMO_ORIGINS`, and `FIL_DEMO_SECURE_COOKIES=true` if serving the browser UI over HTTPS outside localhost.
2. Register the three shop tools in ElevenAgents. The `build_webhook_tools` function defines the request schemas for `/shop/search`, `/shop/check`, and `/shop/reserve`. Set `Authorization` to a workspace secret containing `Bearer ` followed by the local webhook secret. Bind `X-Conversation-ID` to `system__conversation_id`. [Tool definitions](../src/fil_shop/agent_config.py) · [ElevenLabs webhook tools](https://elevenlabs.io/docs/eleven-agents/customization/tools/webhook-tools) · [ElevenLabs system variables](https://elevenlabs.io/docs/eleven-agents/customization/personalization/dynamic-variables)
3. Run `uv run --locked python scripts/agent_config.py --help` for the local renderer. Give it a voice ID, the three registered tool IDs, and an output path. The resulting JSON uses the active prompt and includes the English, Catalan, and Spanish configuration. Apply it to your agent, then check the saved tool IDs and URLs. The renderer makes no provider calls. [Active prompt](../agent/system-prompt.en.md)
4. Put `ELEVENLABS_API_KEY` and `ELEVENLABS_AGENT_ID` in `.env` and restart the API. The server uses them to mint a browser conversation token. Keep the API key, webhook secret, and any hosted access code in server configuration or secret storage. [ElevenLabs SDK authentication](https://elevenlabs.io/docs/eleven-agents/libraries/java-script)
5. Run **Test microphone** and **Test speaker** before selecting **Talk to Ona**. Try a language change and check **View activity** for an actual search outcome. If you change the HTTPS origin, update all three webhook URLs and rerun the check. [Example call](demo-script.md)

If you can see text but cannot hear Ona, check the selected speaker and browser audio permissions. End the call before reconnecting. If the app reports an active session after a reload, use the control to close the previous session.

## Build the container

```sh
docker build -f scripts/Dockerfile -t fil-demo .
```

The Dockerfile uses an allowlist for its build context. Mount durable storage at `/app/data` and pass provider credentials at runtime. The image still needs the same agent and HTTPS configuration for live voice. [Container recipe](../scripts/Dockerfile)
