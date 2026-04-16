PROVIDER_PRESETS = {
    "openai_compatible": {
        "label": "OpenAI Compatible",
        "default_url": "https://api.openai.com/v1",
    },
    "ollama": {
        "label": "Ollama",
        "default_url": "http://localhost:11434/v1",
    },
}


def list_provider_presets() -> dict:
    return dict(PROVIDER_PRESETS)