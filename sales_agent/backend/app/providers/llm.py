from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel

from app.config import settings


StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


class LLMProvider:
    """Small abstraction over Groq structured calls.

    Nodes can fall back to deterministic behavior when a key or dependency is absent.
    """

    def __init__(self) -> None:
        self._client: Any | None = None

    @property
    def available(self) -> bool:
        return bool(settings.groq_api_key)

    async def structured(
        self,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[StructuredModel],
    ) -> StructuredModel | None:
        if not self.available:
            return None
        try:
            from langchain_groq import ChatGroq
        except Exception:
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
        except Exception:
            return None


llm_provider = LLMProvider()
