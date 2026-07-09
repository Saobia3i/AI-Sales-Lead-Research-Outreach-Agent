from __future__ import annotations

import json
import logging
import re
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


class LLMProvider:
    """Small abstraction over structured LLM calls.

    Groq is the primary provider. OpenRouter is used as a fallback when Groq is
    unavailable, errors, or returns no structured result.
    """

    def __init__(self) -> None:
        self._client: Any | None = None

    @property
    def available(self) -> bool:
        return bool(settings.groq_api_key or settings.openrouter_api_key)

    async def structured(
        self,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[StructuredModel],
    ) -> StructuredModel | None:
        if not self.available:
            return None

        groq_result = await self._structured_groq(system_prompt, user_prompt, output_schema)
        if groq_result is not None:
            return groq_result

        return await self._structured_openrouter(system_prompt, user_prompt, output_schema)

    async def _structured_groq(
        self,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[StructuredModel],
    ) -> StructuredModel | None:
        if not settings.groq_api_key:
            return None

        try:
            from langchain_groq import ChatGroq
        except Exception as exc:
            logger.warning(f"Groq import failed for {output_schema.__name__}: {exc}")
            return None

        try:
            client = self._client or ChatGroq(
                api_key=settings.groq_api_key,
                model=settings.groq_model,
                temperature=0,
            )
            self._client = client
            structured_client = client.with_structured_output(output_schema)
            return await structured_client.ainvoke(
                [
                    ("system", system_prompt),
                    ("human", user_prompt),
                ]
            )
        except Exception as exc:
            logger.warning(f"Groq structured output failed for {output_schema.__name__}: {exc}")
            return None

    async def _structured_openrouter(
        self,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[StructuredModel],
    ) -> StructuredModel | None:
        if not settings.openrouter_api_key:
            return None

        schema = self._openrouter_schema(output_schema.model_json_schema())
        system = (
            f"{system_prompt}\n\n"
            "Return ONLY valid JSON matching the provided schema. "
            "Do not include markdown fences or explanatory text."
        )
        user = (
            f"{user_prompt}\n\n"
            f"JSON schema:\n{json.dumps(schema, ensure_ascii=False)}"
        )

        headers = {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
        }
        if settings.openrouter_site_url:
            headers["HTTP-Referer"] = settings.openrouter_site_url
        if settings.openrouter_app_name:
            headers["X-Title"] = settings.openrouter_app_name

        payload: dict[str, Any] = {
            "model": settings.openrouter_model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": output_schema.__name__,
                    "strict": True,
                    "schema": schema,
                },
            },
        }

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )

                if response.status_code >= 400:
                    logger.warning(
                        "OpenRouter json_schema output failed for %s: %s %s. Retrying with prompt-only JSON.",
                        output_schema.__name__,
                        response.status_code,
                        response.text[:500],
                    )
                    fallback_payload = dict(payload)
                    fallback_payload.pop("response_format", None)
                    response = await client.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers=headers,
                        json=fallback_payload,
                    )

                if response.status_code >= 400:
                    logger.warning(
                        "OpenRouter structured output failed for %s: %s %s",
                        output_schema.__name__,
                        response.status_code,
                        response.text[:500],
                    )
                    return None

                data = response.json()
        except Exception as exc:
            logger.warning(f"OpenRouter request failed for {output_schema.__name__}: {exc}")
            return None

        try:
            content = data["choices"][0]["message"]["content"]
            parsed = self._extract_json(content)
            return output_schema.model_validate(parsed)
        except Exception as exc:
            logger.warning(f"OpenRouter JSON validation failed for {output_schema.__name__}: {exc}")
            return None

    @staticmethod
    def _extract_json(content: Any) -> Any:
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        if not isinstance(content, str):
            return content

        text = content.strip()
        fence_match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
        if fence_match:
            text = fence_match.group(1).strip()
        return json.loads(text)

    @classmethod
    def _openrouter_schema(cls, schema: dict[str, Any]) -> dict[str, Any]:
        """Make Pydantic JSON schema friendlier to OpenRouter/OpenAI strict mode."""
        copied = json.loads(json.dumps(schema))
        cls._mark_objects_strict(copied)
        return copied

    @classmethod
    def _mark_objects_strict(cls, node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object":
                node.setdefault("additionalProperties", False)
            for value in node.values():
                cls._mark_objects_strict(value)
        elif isinstance(node, list):
            for item in node:
                cls._mark_objects_strict(item)


llm_provider = LLMProvider()
