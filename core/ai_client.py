"""
AI 客户端适配层 — 统一支持 OpenAI 兼容 API 和 Ollama

配置持久化到 ~/.aline_config.json
依赖：openai 包（pip install openai）
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict

_CONFIG_PATH = Path.home() / ".aline_config.json"


class AIConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider: Literal["openai_compatible", "ollama"] = "openai_compatible"
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o-mini"
    timeout: int = 60
    temperature: float = 0.7
    max_tokens: int = 2048
    show_assistant: bool = True

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

    def _get_client(self):
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError("需要安装 openai 包：pip install openai")

        return AsyncOpenAI(
            base_url=self._config.base_url,
            api_key=self._config.api_key or "ollama",  # Ollama 不需要真实 key
            timeout=self._config.timeout,
        )

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        stream: bool = False,
    ) -> AIResponse:
        """发送对话请求，返回 AIResponse。"""
        client = self._get_client()
        kwargs: Dict[str, Any] = {
            "model": self._config.model,
            "messages": messages,
            "temperature": self._config.temperature,
            "max_tokens": self._config.max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            resp = await client.chat.completions.create(**kwargs)
            choice = resp.choices[0]
            content = choice.message.content or ""
            tool_calls = []
            if choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    tool_calls.append({
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    })
            return AIResponse(content=content, tool_calls=tool_calls)
        except Exception as e:
            return AIResponse(error=str(e))

    async def test_connection(self) -> tuple[bool, str]:
        """发送简单消息测试连通性。返回 (success, message)。"""
        resp = await self.chat([{"role": "user", "content": "ping"}])
        if resp.error:
            return False, resp.error
        return True, "连接成功"
