"""Patched ChatOpenAI that preserves reasoning_content for EPFL RCP models."""

from __future__ import annotations

from typing import Any

import openai
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_openai import ChatOpenAI


class PatchedChatOpenAI(ChatOpenAI):
    """ChatOpenAI with reasoning_content preservation in streaming and final outputs."""

    def _create_chat_result(
        self,
        response: dict | openai.BaseModel,
        generation_info: dict | None = None,
    ) -> ChatResult:
        result = super()._create_chat_result(response, generation_info)
        try:
            response_dict = response if isinstance(response, dict) else response.model_dump()
            choices = response_dict.get("choices", [])
        except Exception:
            return result

        for generation, choice in zip(result.generations, choices):
            message_payload = choice.get("message") or {}
            reasoning_content = message_payload.get("reasoning_content")
            if isinstance(generation.message, AIMessage) and isinstance(reasoning_content, str) and reasoning_content.strip():
                generation.message.additional_kwargs["reasoning_content"] = reasoning_content

        return result

    def _create_chat_generation_chunk(
        self,
        chunk: dict,
        default_chunk_class: type,
        base_generation_info: dict | None,
    ) -> ChatGenerationChunk | None:
        generation_chunk = super()._create_chat_generation_chunk(chunk, default_chunk_class, base_generation_info)
        if generation_chunk is None:
            return None

        choices = chunk.get("choices", []) or chunk.get("chunk", {}).get("choices", [])
        if not choices:
            return generation_chunk

        delta = choices[0].get("delta") or {}
        reasoning_content = delta.get("reasoning_content")
        if isinstance(generation_chunk.message, AIMessageChunk) and isinstance(reasoning_content, str) and reasoning_content.strip():
            generation_chunk.message.additional_kwargs["reasoning_content"] = reasoning_content

        return generation_chunk
