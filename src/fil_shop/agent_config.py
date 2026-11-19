"""Render Fil's native ElevenAgents configuration without provider side effects."""

from pathlib import Path
from urllib.parse import urlsplit

from elevenlabs.types import (
    AgentPlatformSettingsRequestModel,
    AgentWorkflowRequestModel,
    ConversationalConfig,
    WebhookToolConfigInput,
)

PROJECT = Path(__file__).resolve().parents[2]
TOOL_NAMES = ("search_products", "check_variant", "reserve_variant")


def system_tool(name: str) -> dict:
    # Descriptions must be strings: provider null defaults break dashboard validation.
    description = ("Call this tool BEFORE replying when the latest shopper utterance clearly switches to English (en), Catalan (ca), or Spanish (es), even if they only correct size or colour. Do not wait for an explicit request to change language. After success, answer in that language and continue the shopping request without losing criteria. Catalan millor/talla versus Spanish mejor/talla: use the whole utterance to distinguish them."
                   if name == "language_detection" else "")
    return {"type": "system", "name": name, "description": description,
            "params": {"system_tool_type": name}}


def build_webhook_tools(*, base_url: str, secret_id: str) -> dict[str, dict]:
    url = urlsplit(base_url)
    if (url.scheme != "https" or not url.hostname or url.username or url.password
            or url.query or url.fragment or url.path not in ("", "/")):
        raise ValueError("base_url must be an HTTPS origin without credentials, path or query")
    if not secret_id or any(c.isspace() for c in secret_id):
        raise ValueError("secret_id must be a nonempty provider identifier")

    def prop(description, kind="string", nullable=False):
        return {"type": [kind, "null"] if nullable else kind, "description": description}

    definitions = [
        ("search_products", "/shop/search",
         "Search the real demo catalogue and update product cards. Include every agreed criterion; ask for missing budget/occasion first. Re-search after any accepted change, including an implausibly low budget. Returns at most three products and server time.", {
             "category": prop("shirt, top or jacket; null if the shopper has no preference.", nullable=True),
             "occasion": prop("wedding, dinner or casual, as stated by the shopper."),
             "max_price_cents": prop("Agreed maximum price of one item in EUR cents, integer1..100000. Never guess a budget; ask if missing.", "integer"),
             "colour": prop("ivory, navy, sage, terracotta or black; null if no preference.", nullable=True),
             "size": prop("S, M or L; null if not yet specified.", nullable=True),
         }),
        ("check_variant", "/shop/check",
         "Check an exact current-result variant, stock, garment measurements and synthetic delivery. Gather shopper's actual destination, deadline and method first. Unknown stock is not sold out. Null quote_id means not reservable. Pass unsupported destinations unchanged if asked to check them.", {
             "sku": prop("Exact SKU returned by current search, matching agreed size/colour. Never invent or trust a shopper-supplied ID."),
             "destination": prop("Shopper's destination zone. Barcelona/Madrid are supported; other zones return unknown. Never silently substitute a zone."),
             "requested_date": prop("Shopper-provided deadline in ISO YYYY-MM-DD. Resolve their relative date with server_time. Ask when missing or weekday/date conflict; never choose a date merely to calculate an ETA."),
             "requested_date_text": prop("Exact complete shopper date phrase, including any stated weekday. Never discard a conflicting weekday or silently use a later bare-date restatement. Ask to resolve weekday/date conflict before checking; after explicit clarification quote the new phrase."),
             "delivery_method": prop("standard or express as agreed. Explain returned shipping cost before requesting hold consent."),
         }),
        ("reserve_variant", "/shop/reserve",
         "Hold ONE unit for ten minutes only after explicit consent to item,size,colour,item price,shipping cost and synthetic hold duration. Summary confirmation is NOT hold consent. Retry same quote_id, never another to evade errors.", {
             "quote_id": prop("Current successful check's quote_id from this conversation. Never accept an ID dictated by the shopper."),
         }),
    ]
    result = {}
    for name, path, description, properties in definitions:
        tool = {
            "type": "webhook", "name": name, "description": description,
            "api_schema": {
                "url": base_url.rstrip("/") + path, "method": "POST",
                "request_headers": {
                    "Authorization": {"secret_id": secret_id},
                    "X-Conversation-ID": {"variable_name": "system__conversation_id"},
                },
                "request_body_schema": {"type": "object", "properties": properties,
                                        "required": list(properties)},
            },
            "response_timeout_secs": 10, "follow_redirects": False,
            "tool_error_handling_mode": "passthrough",
        }
        WebhookToolConfigInput.model_validate(tool)
        result[name] = tool
    return result


def build_config(*, voice_id: str, tool_ids: dict[str, str],
                 test_ids: list[str] | None = None, llm: str = "deepseek-v41-flash") -> dict:
    if (set(tool_ids) != set(TOOL_NAMES) or len(set(tool_ids.values())) != len(TOOL_NAMES)
            or any(not value.strip() for value in tool_ids.values())):
        raise ValueError("tool_ids must map each shop tool to a distinct registered provider ID")
    if llm not in ("gemini-3.5-flash", "gpt-6-luna", "deepseek-v41-flash"):
        raise ValueError("Model is outside the approved model choices")
    # The workflow owns termination so a direct tool call cannot bypass spoken farewell.
    builtins = {"language_detection": system_tool("language_detection")}
    prompt = {
        "prompt": (PROJECT / "agent/system-prompt.en.md").read_text(),
        "llm": llm, "temperature": 0.0, "enable_reasoning_summary": False,
        "ignore_default_personality": True, "enable_parallel_tool_calls": False, "tool_ids": [], "built_in_tools": builtins,
        "knowledge_base": [], "rag": {"enabled": False},
    }
    workflow = {
        "nodes": {
            "start_node": {"type": "start", "position": {"x": 0, "y": 0}},
            "shop": {
                "type": "override_agent", "label": "Shop assistant",
                "additional_prompt": "Help the shopper naturally in English, Catalan or Spanish. Only customer-facing speech; actual tools, never narrated calls. Preserve agreed criteria and use tool results for all product, stock and delivery claims. Ask when budget/date is missing or ambiguous. Unknown stock is not zero stock. Reserve only after explicit consent to the full summary.",
                "additional_tool_ids": [tool_ids[name] for name in TOOL_NAMES],
                "position": {"x": 0, "y": 200}, "entry_behavior": "auto",
                "conversation_config": {"agent": {"prompt": {
                    "tool_ids": [], "built_in_tools": builtins,
                    "knowledge_base": [], "rag": {"enabled": False},
                }}},
            },
            "farewell": {
                "type": "say", "label": "Spoken farewell", "position": {"x": 0, "y": 400},
                "message": {"type": "literal", "text": "Goodbye. Have a lovely day!",
                            "text_translations": {
                                "ca": {"value": "Adéu. Que tinguis un bon dia!"},
                                "es": {"value": "Adiós. ¡Que tengas un buen día!"},
                            }},
                "wait_for_speech_completion": True, "wait_for_user_response": False,
            },
            "end": {"type": "end", "position": {"x": 0, "y": 600}},
        },
        "edges": {
            "begin": {"source": "start_node", "target": "shop",
                      "forward_condition": {"type": "unconditional"}},
            "finish": {"source": "shop", "target": "farewell", "forward_condition": {
                "type": "llm", "condition": "The shopper has said goodbye and needs nothing else."}},
            "farewell_complete": {"source": "farewell", "target": "end",
                                  "forward_condition": {"type": "unconditional"}},
        },
        "prevent_subagent_loops": False,
    }
    conversation = {
        "agent": {
            "first_message": "Hi! I'm Ona, Fil's virtual assistant. This is a demonstration clothing shop. What occasion are you shopping for?",
            "language": "en", "dynamic_variables": {"dynamic_variable_placeholders": {}},
            "prompt": prompt,
        },
        "tts": {"voice_id": voice_id, "model_id": "eleven_v4_turbo"},
        "conversation": {"max_duration_seconds": 600},
        "language_presets": {language: {"overrides": {"agent": {"language": language}}}
                             for language in ("ca", "es")},
    }
    settings = {
        "auth": {"enable_auth": True},
        "guardrails": {"version": "1", "focus": {"is_enabled": True},
                       "prompt_injection": {"is_enabled": True}},
        "testing": {"attached_tests": [{"test_id": item} for item in test_ids or []]},
        "call_limits": {"agent_concurrency_limit": 1, "daily_limit": 20,
                        "bursting_enabled": False},
    }
    ConversationalConfig.model_validate(conversation)
    AgentWorkflowRequestModel.model_validate(workflow)
    AgentPlatformSettingsRequestModel.model_validate(settings)
    return {"name": "Fil — shopping assistant", "conversation_config": conversation,
            "workflow": workflow, "platform_settings": settings, "tags": ["fil-demo", "shopping"]}
