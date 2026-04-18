"""
AI 客户端适配层 — 统一支持 OpenAI 兼容 API 和 Ollama

配置持久化到 ~/.aline_config.json
使用标准 httpx 库，无需安装 openai 包
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Literal, Optional
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict

_CONFIG_PATH = Path.home() / ".aline_config.json"


def _list_builtin_models(provider: str) -> List[str]:
    from core.ai.providers import list_builtin_models

    return list_builtin_models(provider)


class AIConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider: Literal["openai_compatible", "ollama"] = "openai_compatible"
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o-mini"
    timeout: int = 60
    temperature: float = 0.7
    top_p: float = 1.0
    max_tokens: int = 2048
    show_assistant: bool = True
    system_prompt: str = ""
    ollama_keep_alive: str = "5m"
    ollama_num_ctx: int = 4096

    @classmethod
    def load(cls) -> "AIConfig":
        """从 ~/.aline_config.json 加载；文件不存在时返回默认值。"""
        if _CONFIG_PATH.exists():
            try:
                data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
                return cls(**data)
            except Exception:
                pass
        return cls()

    def save(self) -> None:
        """保存到 ~/.aline_config.json。"""
        _CONFIG_PATH.write_text(
            self.model_dump_json(indent=2), encoding="utf-8"
        )


class AIResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    content: str = ""
    tool_calls: List[Dict[str, Any]] = []
    error: Optional[str] = None


class AIClient:
    """统一适配 OpenAI 兼容 API（含 Ollama /v1 端点）。"""

    def __init__(self, config: Optional[AIConfig] = None):
        self._config = config or AIConfig.load()

    @property
    def config(self) -> AIConfig:
        return self._config

    def _auth_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        api_key = self._config.api_key.strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _get_client(self):
        """返回 httpx AsyncClient（已配置 base_url 和 Authorization)。"""
        try:
            import httpx
        except ImportError:
            raise ImportError("需要安装 httpx 包：pip install httpx")

        return httpx.AsyncClient(
            base_url=self._config.base_url.rstrip("/"),
            headers=self._auth_headers(),
            timeout=float(self._config.timeout),
        )

    def _with_global_system_prompt(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        system_prompt = self._config.system_prompt.strip()
        cloned = [dict(message) for message in messages]
        if not system_prompt:
            return cloned
        if cloned and cloned[0].get("role") == "system":
            content = str(cloned[0].get("content") or "").strip()
            cloned[0]["content"] = system_prompt if not content else f"{system_prompt}\n\n{content}"
        else:
            cloned.insert(0, {"role": "system", "content": system_prompt})
        return cloned

    def _ollama_tags_url(self) -> str:
        parsed = urlparse(self._config.base_url)
        path = (parsed.path or "").rstrip("/")
        if path.endswith("/v1"):
            path = path[:-3]
        path = f"{path}/api/tags"
        return urlunparse(parsed._replace(path=path, params="", query="", fragment=""))

    def list_available_models_sync(self) -> List[str]:
        if self._config.provider != "ollama":
            return _list_builtin_models(self._config.provider)

        headers = {"Accept": "application/json"}
        auth_header = self._auth_headers().get("Authorization")
        if auth_header:
            headers["Authorization"] = auth_header
        request = Request(self._ollama_tags_url(), headers=headers)
        with urlopen(request, timeout=self._config.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))

        models: List[str] = []
        for item in payload.get("models", []):
            name = item.get("model") or item.get("name")
            if isinstance(name, str) and name.strip():
                models.append(name.strip())
        return models or _list_builtin_models("ollama")

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        stream: bool = False,
    ) -> AIResponse:
        """发送对话请求，返回 AIResponse（使用 httpx，无需 openai 包）。"""
        payload = self._build_chat_payload(messages, tools=tools)

        try:
            async with self._get_client() as client:
                response = await client.post("/chat/completions", json=payload)
                response.raise_for_status()
                data = response.json()

            choice = data["choices"][0]
            message = choice.get("message", {})
            content = message.get("content") or ""
            tool_calls = []
            for tc in message.get("tool_calls") or []:
                tool_calls.append({
                    "id": tc.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": tc["function"]["name"],
                        "arguments": tc["function"]["arguments"],
                    },
                })
            return AIResponse(content=content, tool_calls=tool_calls)
        except Exception as e:
            return AIResponse(error=str(e))

    def _build_chat_payload(
        self,
        messages: List[Dict[str, Any]],
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        request_messages = self._with_global_system_prompt(messages)
        payload: Dict[str, Any] = {
            "model": self._config.model,
            "messages": request_messages,
            "temperature": self._config.temperature,
            "top_p": self._config.top_p,
            "max_tokens": self._config.max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        return payload

    async def test_connection(self) -> tuple[bool, str]:
        """发送简单消息测试连通性。返回 (success, message)。"""
        resp = await self.chat([{"role": "user", "content": "ping"}])
        if resp.error:
            return False, resp.error
        return True, "连接成功"
