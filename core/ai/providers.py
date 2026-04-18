from __future__ import annotations

from copy import deepcopy


PROVIDER_PRESETS = {
    "openai_compatible": {
        "label": "OpenAI 兼容 API",
        "default_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "model_placeholder": "gpt-4o-mini",
        "api_key_required": True,
        "supports_model_discovery": False,
        "builtin_models": ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4o"],
        "help_text": "适用于 OpenAI 及兼容其 /v1/chat/completions 协议的服务。",
    },
    "ollama": {
        "label": "Ollama",
        "default_url": "http://localhost:11434/v1",
        "default_model": "llama3.1:8b",
        "model_placeholder": "llama3.1:8b",
        "api_key_required": False,
        "supports_model_discovery": True,
        "builtin_models": ["llama3.1:8b", "qwen2.5:7b", "mistral:7b"],
        "help_text": "适用于本地或服务端 Ollama 服务；本地部署可不填 API Key，服务端代理可填写。",
    },
}


def list_provider_presets() -> dict:
    return deepcopy(PROVIDER_PRESETS)


def list_provider_keys() -> list[str]:
    return list(PROVIDER_PRESETS.keys())


def get_provider_preset(provider: str) -> dict:
    preset = PROVIDER_PRESETS.get(provider) or PROVIDER_PRESETS["openai_compatible"]
    return deepcopy(preset)


def list_builtin_models(provider: str) -> list[str]:
    preset = PROVIDER_PRESETS.get(provider) or PROVIDER_PRESETS["openai_compatible"]
    return list(preset.get("builtin_models", []))