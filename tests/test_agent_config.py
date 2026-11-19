"""Offline provider contracts, not proof of audible voice or live provider behavior."""

import json
from urllib.parse import urlsplit

import pytest
from elevenlabs.types import (
    AgentPlatformSettingsRequestModel,
    AgentWorkflowRequestModel,
    ConversationalConfig,
    WebhookToolConfigInput,
)

from fil_shop.agent_config import TOOL_NAMES, build_config, build_webhook_tools


@pytest.fixture
def config():
    return build_config(voice_id="fixture-voice", tool_ids={n: f"tool-{n}" for n in TOOL_NAMES},
                        test_ids=["fixture-test"])


def test_sdk_models_accept_complete_rendered_configuration(config):
    loaded = json.loads(json.dumps(config))
    ConversationalConfig.model_validate(loaded["conversation_config"])
    AgentWorkflowRequestModel.model_validate(loaded["workflow"])
    AgentPlatformSettingsRequestModel.model_validate(loaded["platform_settings"])
    tools = build_webhook_tools(base_url="https://shop.example.test", secret_id="fixture-secret")
    for tool in tools.values():
        WebhookToolConfigInput.model_validate(tool)


@pytest.mark.parametrize("url", ["http://shop.test", "https://u:p@shop.test",
                                 "https://shop.test/path", "https://shop.test?q=secret",
                                 "https://shop.test#fragment", "https://"])
def test_rejects_unsafe_or_ambiguous_provider_origins(url):
    with pytest.raises(ValueError):
        build_webhook_tools(base_url=url, secret_id="s")


def test_tool_identity_owned_by_provider_and_no_legacy_account_arguments():
    tools = build_webhook_tools(base_url="https://shop.example.test", secret_id="fixture-secret")
    assert set(tools) == set(TOOL_NAMES)
    for name, tool in tools.items():
        schema = tool["api_schema"]
        assert schema["method"] == "POST"
        assert urlsplit(schema["url"]).path == {
            "search_products": "/shop/search", "check_variant": "/shop/check",
            "reserve_variant": "/shop/reserve",
        }[name]
        assert schema["request_headers"] == {
            "Authorization": {"secret_id": "fixture-secret"},
            "X-Conversation-ID": {"variable_name": "system__conversation_id"},
        }
        assert not {"conversation_id", "customer_id", "pin", "stock", "consent"}.intersection(
            schema["request_body_schema"]["properties"])
        assert tool["follow_redirects"] is False
    assert set(tools["reserve_variant"]["api_schema"]["request_body_schema"]["properties"]) == {
        "quote_id"
    }
    assert "Bearer " not in json.dumps(tools)


def test_workflow_exposes_only_shop_tools_and_clears_old_knowledge(config):
    nodes = config["workflow"]["nodes"]
    assert set(nodes) == {"start_node", "shop", "farewell", "end"}
    assert nodes["shop"]["additional_tool_ids"] == [f"tool-{n}" for n in TOOL_NAMES]
    prompts = [config["conversation_config"]["agent"]["prompt"],
               nodes["shop"]["conversation_config"]["agent"]["prompt"]]
    for prompt in prompts:
        assert prompt["tool_ids"] == prompt["knowledge_base"] == []
        assert prompt["rag"]["enabled"] is False
        for tool in prompt["built_in_tools"].values():
            assert isinstance(tool["description"], str)
        assert "BEFORE replying" in prompt["built_in_tools"]["language_detection"]["description"]
    for edge in config["workflow"]["edges"].values():
        assert edge["source"] in nodes and edge["target"] in nodes
    assert "verify_customer" not in json.dumps(config)
    assert "get_billing_summary" not in json.dumps(config)


def test_voice_language_hygiene_and_call_limits_preserved(config):
    conversation, settings = config["conversation_config"], config["platform_settings"]
    assert conversation["tts"]["voice_id"] == "fixture-voice"
    assert conversation["agent"]["language"] == "en"
    assert set(conversation["language_presets"]) == {"ca", "es"}
    assert conversation["agent"]["prompt"]["llm"] == "deepseek-v41-flash"
    assert settings["auth"]["enable_auth"] is True
    assert settings["guardrails"]["focus"]["is_enabled"] is True
    assert settings["guardrails"]["prompt_injection"]["is_enabled"] is True
    assert settings["testing"]["attached_tests"] == [{"test_id": "fixture-test"}]
    assert settings["call_limits"] == {"agent_concurrency_limit": 1, "daily_limit": 20,
                                       "bursting_enabled": False}


@pytest.mark.parametrize("mapping", [{}, {n: "same" for n in TOOL_NAMES},
                                      {n: "" for n in TOOL_NAMES}])
def test_rejects_missing_duplicate_or_empty_tool_registrations(mapping):
    with pytest.raises(ValueError):
        build_config(voice_id="voice", tool_ids=mapping)


def test_rendered_tool_contract_executes_real_local_shop(tmp_path):
    from fastapi.testclient import TestClient

    from fil_shop.api import create_app

    secret = "synthetic-contract-credential-0000000000000"
    client = TestClient(create_app(str(tmp_path / "shop.sqlite"), secret))
    tools = build_webhook_tools(base_url="https://shop.example.test", secret_id="secret-id")
    headers = {"Authorization": f"Bearer {secret}", "X-Conversation-ID": "provider-contract"}

    def invoke(name, payload):
        schema = tools[name]["api_schema"]
        assert set(payload) == set(schema["request_body_schema"]["required"])
        return client.request(schema["method"], urlsplit(schema["url"]).path,
                              headers=headers, json=payload)

    result = invoke("search_products", {"category": "shirt", "occasion": "wedding",
                    "max_price_cents": 12000, "colour": "navy", "size": "M"})
    assert result.status_code == 200
    products = result.json()["products"]
    sku = next(v["sku"] for p in products for v in p["variants"]
               if v["size"] == "M" and v["colour"] == "navy" and v["available_quantity"])
    checked = invoke("check_variant", {"sku": sku, "destination": "Barcelona",
                     "requested_date": "2099-12-31", "requested_date_text": "2099-12-31",
                     "delivery_method": "standard"})
    assert checked.status_code == 200
    quote_id = checked.json()["quote_id"]
    assert quote_id
    first = invoke("reserve_variant", {"quote_id": quote_id}).json()
    retry = invoke("reserve_variant", {"quote_id": quote_id}).json()
    assert first["created"] is True and retry["created"] is False
    assert first["reservation"]["id"] == retry["reservation"]["id"]
    assert first["reservation"]["sku"] == sku


@pytest.mark.parametrize("model", ["gpt-6-luna", "deepseek-v41-flash"])
def test_comparison_model_is_explicit_and_bounded(model):
    tools = {n: f"tool-{n}" for n in TOOL_NAMES}
    config = build_config(voice_id="voice", tool_ids=tools, llm=model)
    assert config["conversation_config"]["agent"]["prompt"]["llm"] == model
    with pytest.raises(ValueError):
        build_config(voice_id="voice", tool_ids=tools, llm="unapproved-model")


def test_every_termination_path_waits_for_localized_farewell(config):
    workflow = config["workflow"]
    assert [e["source"] for e in workflow["edges"].values() if e["target"] == "end"] == ["farewell"]
    assert workflow["edges"]["finish"]["target"] == "farewell"
    farewell = workflow["nodes"]["farewell"]
    assert farewell["type"] == "say"
    assert farewell["wait_for_speech_completion"] is True
    assert farewell["wait_for_user_response"] is False
    assert farewell["message"]["text"].startswith("Goodbye.")
    assert set(farewell["message"]["text_translations"]) == {"ca", "es"}
    assert all(t["value"].strip() for t in farewell["message"]["text_translations"].values())
    for prompt in (config["conversation_config"]["agent"]["prompt"],
                   workflow["nodes"]["shop"]["conversation_config"]["agent"]["prompt"]):
        assert "end_call" not in prompt["built_in_tools"]
