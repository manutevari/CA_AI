"""Dynamic AI/search provider routing for the Streamlit filing agent.

Keys are read from Streamlit secrets first and environment variables second.
No secret values are logged or returned to the UI.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Literal

ProviderUseCase = Literal["official_search", "tax_reasoning", "fallback_summary"]


@dataclass(frozen=True)
class ProviderChoice:
    name: str
    use_case: ProviderUseCase
    reason: str
    model: str | None = None
    configured: bool = False


def available_providers() -> dict[str, bool]:
    return {
        "tavily": bool(_secret("TAVILY_KEY", "tavily_key")),
        "groq": bool(_secret("GROQ_API_KEY")),
        "deepseek": bool(_secret("DEEPSEEK_API_KEY")),
        "mistral": bool(_secret("MISTRAL_API_KEY")),
        "huggingface": bool(_secret("HF_API_KEY")),
    }


def choose_provider(use_case: ProviderUseCase) -> ProviderChoice:
    providers = available_providers()
    if use_case == "official_search":
        if providers["tavily"]:
            return ProviderChoice("tavily", use_case, "Tavily is configured for official source search.", configured=True)
        return ProviderChoice("local_rules", use_case, "No Tavily key found; using bundled official links.", configured=True)

    if use_case == "tax_reasoning":
        if providers["deepseek"]:
            return ProviderChoice(
                "deepseek",
                use_case,
                "DeepSeek is configured for deeper tax reasoning.",
                model=_secret("DEEPSEEK_MODEL") or "deepseek-chat",
                configured=True,
            )
        if providers["groq"]:
            return ProviderChoice(
                "groq",
                use_case,
                "Groq is configured for low-latency reasoning.",
                model=_secret("GROQ_MODEL") or "llama-3.1-8b-instant",
                configured=True,
            )
        if providers["mistral"]:
            return ProviderChoice(
                "mistral",
                use_case,
                "Mistral is configured for tax review reasoning.",
                model=_secret("MISTRAL_MODEL") or "mistral-small-latest",
                configured=True,
            )
        if providers["huggingface"]:
            return ProviderChoice(
                "huggingface",
                use_case,
                "Hugging Face is configured as a fallback model provider.",
                model=_secret("HF_MODEL") or "mistralai/Mistral-7B-Instruct-v0.3",
                configured=True,
            )
        return ProviderChoice("deterministic_rules", use_case, "No model key found; using deterministic checks.", configured=True)

    if providers["groq"]:
        return ProviderChoice(
            "groq",
            use_case,
            "Groq is configured for fast summarization.",
            model=_secret("GROQ_MODEL") or "llama-3.1-8b-instant",
            configured=True,
        )
    if providers["deepseek"]:
        return ProviderChoice(
            "deepseek",
            use_case,
            "DeepSeek is configured for summarization.",
            model=_secret("DEEPSEEK_MODEL") or "deepseek-chat",
            configured=True,
        )
    if providers["mistral"]:
        return ProviderChoice(
            "mistral",
            use_case,
            "Mistral is configured for summarization.",
            model=_secret("MISTRAL_MODEL") or "mistral-small-latest",
            configured=True,
        )
    if providers["huggingface"]:
        return ProviderChoice(
            "huggingface",
            use_case,
            "Hugging Face is configured for fallback summarization.",
            model=_secret("HF_MODEL") or "mistralai/Mistral-7B-Instruct-v0.3",
            configured=True,
        )
    return ProviderChoice("deterministic_rules", use_case, "No model key found; using deterministic summary.", configured=True)


def provider_status() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for name, configured in available_providers().items():
        out.append({"provider": name, "status": "configured" if configured else "missing"})
    return out


def tavily_search(query: str, *, max_results: int = 5) -> dict[str, Any] | None:
    key = _secret("TAVILY_KEY", "tavily_key")
    if not key:
        return None
    payload = {
        "api_key": key,
        "query": query,
        "search_depth": "advanced",
        "include_answer": True,
        "max_results": max_results,
        "include_domains": ["incometax.gov.in", "incometaxindia.gov.in"],
    }
    return _post_json("https://api.tavily.com/search", payload, headers={"Content-Type": "application/json"})


def reason_with_best_model(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    choice = choose_provider("tax_reasoning")
    if choice.name == "deepseek":
        return _openai_compatible_chat(
            endpoint="https://api.deepseek.com/chat/completions",
            key=_secret("DEEPSEEK_API_KEY") or "",
            model=choice.model or "deepseek-chat",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            provider=choice.name,
        )
    if choice.name == "groq":
        return _openai_compatible_chat(
            endpoint="https://api.groq.com/openai/v1/chat/completions",
            key=_secret("GROQ_API_KEY") or "",
            model=choice.model or "llama-3.1-8b-instant",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            provider=choice.name,
        )
    if choice.name == "mistral":
        return _openai_compatible_chat(
            endpoint="https://api.mistral.ai/v1/chat/completions",
            key=_secret("MISTRAL_API_KEY") or "",
            model=choice.model or "mistral-small-latest",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            provider=choice.name,
        )
    if choice.name == "huggingface":
        return _huggingface_chat(system_prompt, user_prompt, choice.model or "mistralai/Mistral-7B-Instruct-v0.3")
    return {"provider": choice.name, "content": "", "error": "no_llm_provider_configured"}


def _openai_compatible_chat(
    *,
    endpoint: str,
    key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    provider: str,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
        "max_tokens": 700,
    }
    data = _post_json(endpoint, payload, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    if not data:
        return {"provider": provider, "model": model, "content": "", "error": "provider_request_failed"}
    content = ""
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return {"provider": provider, "model": model, "content": "", "error": "unexpected_provider_response"}
    return {"provider": provider, "model": model, "content": content}


def _huggingface_chat(system_prompt: str, user_prompt: str, model: str) -> dict[str, Any]:
    key = _secret("HF_API_KEY")
    if not key:
        return {"provider": "huggingface", "model": model, "content": "", "error": "missing_hf_key"}
    endpoint = _secret("HF_CHAT_ENDPOINT") or f"https://api-inference.huggingface.co/models/{model}"
    payload = {
        "inputs": f"{system_prompt}\n\n{user_prompt}",
        "parameters": {"max_new_tokens": 500, "temperature": 0.1, "return_full_text": False},
    }
    data = _post_json(endpoint, payload, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    if not data:
        return {"provider": "huggingface", "model": model, "content": "", "error": "provider_request_failed"}
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return {"provider": "huggingface", "model": model, "content": str(data[0].get("generated_text", ""))}
    if isinstance(data, dict):
        return {"provider": "huggingface", "model": model, "content": str(data.get("generated_text") or data.get("summary_text") or "")}
    return {"provider": "huggingface", "model": model, "content": "", "error": "unexpected_provider_response"}


def _post_json(url: str, payload: dict[str, Any], *, headers: dict[str, str], timeout: int = 25) -> dict[str, Any] | list[Any] | None:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def _secret(*names: str) -> str | None:
    for name in names:
        value = _streamlit_secret(name)
        if value:
            return value
        value = os.getenv(name)
        if value:
            return value
    return None


def _streamlit_secret(name: str) -> str | None:
    try:
        import streamlit as st

        value = st.secrets.get(name)
    except Exception:
        return None
    return str(value).strip() if value else None
