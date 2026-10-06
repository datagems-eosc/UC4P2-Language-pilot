"""Language-model setup aligned with dg-query-disambiguation.

There is no YAML for LLM calls in this pilot. Selection is environment
variables, read by this module. Put them in ``UC4P2-Language-pilot/.env``
or reuse ``dg-query-disambiguation/.env``.

``LLM_PROVIDER`` selects the chat endpoint:

- ``scayle`` — ``SCAYLE_BASE_URL``, ``SCAYLE_USERNAME``, ``SCAYLE_PASSWORD``,
  ``SCAYLE_MODEL_NAME`` (default ``qwen3``).
- ``ollama`` — local OpenAI-compatible server at ``OLLAMA_BASE_URL``
  (default ``http://127.0.0.1:11434/v1``) and ``OLLAMA_MODEL``.
- ``openai`` — ``OPENAI_API_KEY``, optional ``OPENAI_BASE_URL``,
  ``OPENAI_MODEL_NAME``.
- ``gemini`` — Gemini's OpenAI-compatible endpoint.

Judge calls stay on Scayle (``JUDGE_LLM_MODEL``, default ``glm-5.3-flash``)
and never reuse the pipeline model (``SCAYLE_MODEL_NAME``, default ``qwen3``).
"""

from __future__ import annotations

import json
import os
import ssl
import urllib.request
from pathlib import Path
from typing import Any

import dspy
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[1]
_PILOT_ENV = _ROOT / ".env"
_SIBLING_ENV = _ROOT.parent / "dg-query-disambiguation" / ".env"


def _gemini_api_key() -> str:
    """Accept the Gemini key under the names used in local env files."""
    for name in ("GEMINI_API_KEY", "GEMENEI_API_KEY", "GEMET_API_KEY"):
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


_PROVIDER_ALIASES = {
    "local": "ollama",
    "ollama-local": "ollama",
    "scayle-llm": "scayle",
}


def _provider() -> str:
    explicit = os.getenv("LLM_PROVIDER", "").strip().lower()
    explicit = _PROVIDER_ALIASES.get(explicit, explicit)
    if explicit:
        return explicit
    if os.getenv("SCAYLE_USERNAME", "").strip() and os.getenv("SCAYLE_PASSWORD", "").strip():
        return "scayle"
    if _gemini_api_key():
        return "gemini"
    if os.getenv("OPENAI_API_KEY", "").strip():
        return "openai"
    return "scayle"


def _ollama_base_url() -> str:
    raw = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1").rstrip("/")
    if raw.endswith("/v1"):
        return raw
    return f"{raw}/v1"


def _openai_base_url() -> str:
    return os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")


def llm_endpoint(provider: str | None = None) -> str:
    """Base URL of the selected chat endpoint."""
    name = (provider or _provider()).strip().lower()
    name = _PROVIDER_ALIASES.get(name, name)
    if name == "ollama":
        return _ollama_base_url()
    if name == "openai":
        return _openai_base_url()
    if name == "gemini":
        return "https://generativelanguage.googleapis.com/v1beta/openai"
    return _scayle_base_url()


def _scayle_base_url() -> str:
    return os.getenv("SCAYLE_BASE_URL", "https://chat.scayle.es/api").rstrip("/")


def _scayle_verify_ssl() -> bool:
    return os.getenv("SCAYLE_VERIFY_SSL", "true").strip().lower() not in {
        "0",
        "false",
        "no",
    }


def _scayle_model() -> str:
    return os.getenv("SCAYLE_MODEL_NAME") or os.getenv("LLM_MODEL") or "qwen3"


def _ssl_context() -> ssl.SSLContext | None:
    if _scayle_verify_ssl():
        return None
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def _scayle_token() -> str:
    url = f"{_scayle_base_url()}/v1/auths/ldap"
    payload = json.dumps(
        {
            "user": os.getenv("SCAYLE_USERNAME", ""),
            "password": os.getenv("SCAYLE_PASSWORD", ""),
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60, context=_ssl_context()) as response:
        body = json.loads(response.read().decode("utf-8"))
    token = body.get("token")
    if not token:
        raise RuntimeError("Scayle LDAP authentication did not return a token.")
    return str(token)


def _openai_client(provider: str):
    from openai import OpenAI

    if provider == "gemini":
        return OpenAI(
            api_key=_gemini_api_key(),
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
    if provider == "openai":
        return OpenAI(base_url=_openai_base_url())
    if provider == "ollama":
        return OpenAI(base_url=_ollama_base_url(), api_key="ollama")
    kwargs: dict[str, Any] = {
        "base_url": _scayle_base_url(),
        "api_key": _scayle_token(),
    }
    if not _scayle_verify_ssl():
        import httpx

        kwargs["http_client"] = httpx.Client(verify=False)
    return OpenAI(**kwargs)


def _chat(messages: list[dict[str, str]], model: str) -> str:
    provider = _provider()
    from openai import RateLimitError

    client = _openai_client(provider)
    for attempt in range(3):
        try:
            completion = client.chat.completions.create(
                model=model,
                temperature=0,
                messages=messages,  # type: ignore[arg-type]
            )
            return completion.choices[0].message.content or ""
        except RateLimitError:
            if attempt == 2:
                raise
            import time

            time.sleep(15)


class ProviderChatLM(dspy.LM):
    """DSPy language model backed by the disambiguation service's providers.

    ``forward()`` returns the raw OpenAI ``ChatCompletion`` object so that
    DSPy 3.x can call ``.choices[0].message.content`` on it.
    """

    def __init__(self, model: str, provider: str):
        super().__init__(model=model, temperature=0, cache=False)
        self._model_name = model.split("/", 1)[-1]
        self.provider = provider

    def forward(self, prompt: str | None = None, messages: list[dict[str, Any]] | None = None, **kwargs: Any):
        chat_messages: list[dict[str, str]]
        if messages:
            chat_messages = [
                {"role": str(item.get("role") or "user"), "content": str(item.get("content") or "")}
                for item in messages
            ]
        else:
            chat_messages = [{"role": "user", "content": prompt or ""}]
        from openai import RateLimitError

        client = _openai_client(self.provider)
        for attempt in range(3):
            try:
                return client.chat.completions.create(
                    model=self._model_name,
                    temperature=0,
                    messages=chat_messages,  # type: ignore[arg-type]
                )
            except RateLimitError:
                if attempt == 2:
                    raise
                import time

                time.sleep(15)


def credentials_present_for(provider: str) -> bool:
    name = _PROVIDER_ALIASES.get((provider or "").strip().lower(), (provider or "").strip().lower())
    if name == "gemini":
        return bool(_gemini_api_key())
    if name == "openai":
        return bool(os.getenv("OPENAI_API_KEY", "").strip())
    if name == "ollama":
        return True
    if name == "scayle":
        return bool(os.getenv("SCAYLE_USERNAME", "").strip() and os.getenv("SCAYLE_PASSWORD", "").strip())
    return False


def llm_credentials_present() -> bool:
    return credentials_present_for(_provider())


def pipeline_lm_identity() -> tuple[str, str]:
    """Provider and model used by synthesis / knowledge extension (global DSPy LM)."""
    current = getattr(dspy.settings, "lm", None)
    if current is not None:
        provider = str(getattr(current, "provider", "") or _provider())
        model = str(getattr(current, "_model_name", "") or getattr(current, "model", "") or selected_model(provider))
        return provider, model.split("/", 1)[-1]
    provider = _provider()
    return provider, selected_model(provider)


def chat_completion(
    messages: list[dict[str, str]],
    *,
    provider: str,
    model: str,
) -> str:
    """Chat call that does not use or change the pipeline DSPy LM."""
    name = _PROVIDER_ALIASES.get(provider.strip().lower(), provider.strip().lower())
    from openai import RateLimitError

    client = _openai_client(name)
    for attempt in range(3):
        try:
            completion = client.chat.completions.create(
                model=model.split("/", 1)[-1],
                temperature=0,
                messages=messages,  # type: ignore[arg-type]
            )
            return completion.choices[0].message.content or ""
        except RateLimitError:
            if attempt == 2:
                raise
            import time

            time.sleep(15)
    return ""


def env_files() -> list[Path]:
    """Env files this module reads. No YAML is used for LLM selection."""
    return [path for path in (_PILOT_ENV, _SIBLING_ENV) if path.is_file()]


def _load_local_env() -> None:
    load_dotenv(_PILOT_ENV, override=False)
    load_dotenv()
    if _SIBLING_ENV.is_file():
        load_dotenv(_SIBLING_ENV, override=False)


def selected_model(provider: str | None = None) -> str:
    name = (provider or _provider()).strip().lower()
    if name == "gemini":
        return os.getenv("GEMINI_MODEL_NAME") or os.getenv("LLM_MODEL") or "gemini-3.6-flash"
    if name == "openai":
        return os.getenv("OPENAI_MODEL_NAME") or os.getenv("LLM_MODEL") or "gpt-4o-mini"
    if name == "ollama":
        return os.getenv("OLLAMA_MODEL") or os.getenv("LLM_MODEL") or "llama3:8b"
    return _scayle_model()


def configure_lm_from_env() -> bool:
    """Configure DSPy from ``LLM_PROVIDER`` (scayle, ollama, openai, or gemini)."""
    _load_local_env()
    if not llm_credentials_present():
        return False
    provider = _provider()
    model = selected_model(provider)
    dspy.configure(lm=ProviderChatLM(model=model, provider=provider))
    return True


def configure_refinement_lm(*, prefer: str | None = None, force: bool = False) -> str:
    """Configure the chat endpoint named by ``prefer`` or ``LLM_PROVIDER``.

    ``prefer`` overrides the env for this process (``scayle``, ``ollama``,
    or ``openai``). Returns a label such as ``scayle:qwen3``, or an empty
    string when that provider is not configured. It does not switch to
    another provider on failure.
    """
    _load_local_env()
    if prefer:
        os.environ["LLM_PROVIDER"] = prefer.strip().lower()
    if not force and getattr(dspy.settings, "lm", None) is not None:
        current = dspy.settings.lm
        provider = getattr(current, "provider", None)
        model = getattr(current, "_model_name", None) or getattr(current, "model", None)
        if provider and model:
            return f"{provider}:{model}"
        return "already configured"
    if configure_lm_from_env():
        provider = _provider()
        return f"{provider}:{selected_model(provider)}"
    return ""
