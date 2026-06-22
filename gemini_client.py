"""
Gemini official API client — calls the Gemini Developer API generateContent HTTP endpoint.

Uses POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
with x-goog-api-key header.  No Google SDK / @google/genai dependency.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional

import requests

# Default to the official Gemini Developer API endpoint.
_DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com"

# Hard limit in seconds for a single API call so the ComfyUI node does not
# hang indefinitely.
_REQUEST_TIMEOUT = 120


_REDACTED = "***REDACTED***"

# Known-deprecated model names mapped to current equivalents.
_MODEL_REMAP: dict[str, str] = {
    "gemini-3-pro-preview": "gemini-3.1-pro-preview",
}

# Exclude deprecated names from fetched model lists.
_MODEL_BLOCKLIST: set[str] = {
    "gemini-3-pro-preview",
}


class GeminiClientError(Exception):
    """Raised when the Gemini API returns an error or is unreachable."""


def _sanitize_error_text(text: str, api_key: str) -> str:
    """Remove the API key from error text so it never leaks into logs or UI."""
    if not api_key or not text:
        return text
    # Redact the literal key string if it appears anywhere.
    return text.replace(api_key, _REDACTED)


def _load_config_json(config_path: str) -> Dict[str, Any]:
    """Load config.json if it exists, otherwise return empty dict."""
    if os.path.isfile(config_path):
        with open(config_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def resolve_base_url(node_input: str = "") -> str:
    """
    Resolve base_url with this precedence:
      1. non-empty node input
      2. plugin config.json (base_url key)
      3. documented fallback (_DEFAULT_GEMINI_BASE_URL)

    There is NO dedicated base_url environment variable by design —
    the official endpoint is always the default.  Only advanced users
    who need a proxy or override should set base_url in config.json
    or via the node input.
    """
    if node_input and node_input.strip():
        return node_input.strip().rstrip("/")

    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    config = _load_config_json(os.path.join(plugin_dir, "config.json"))
    if config.get("base_url", "").strip():
        return config["base_url"].strip().rstrip("/")

    return _DEFAULT_GEMINI_BASE_URL


def resolve_api_key(node_input: str = "") -> str:
    """
    Resolve api_key with this precedence:
      1. non-empty node input
      2. env GOOGLE_API_KEY           (official docs: GOOGLE_API_KEY takes precedence)
      3. env GEMINI_API_KEY
      4. plugin config.json (api_key key)
    Returns "" if nothing is found.
    """
    if node_input and node_input.strip():
        return node_input.strip()

    for env_var in ("GOOGLE_API_KEY", "GEMINI_API_KEY"):
        env_val = os.environ.get(env_var, "").strip()
        if env_val:
            return env_val

    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    config = _load_config_json(os.path.join(plugin_dir, "config.json"))
    return config.get("api_key", "").strip()


def resolve_model(node_input: str = "") -> str:
    """Resolve model with precedence: node input > env GEMINI_MODEL > config > default.

    Deprecated model names (e.g. gemini-3-pro-preview) are transparently
    remapped to their current equivalents so saved workflows and old
    configurations never cause 404 errors.
    """
    raw: str = ""
    if node_input and node_input.strip():
        raw = node_input.strip()
    else:
        env_val = os.environ.get("GEMINI_MODEL", "").strip()
        if env_val:
            raw = env_val
        else:
            plugin_dir = os.path.dirname(os.path.abspath(__file__))
            config = _load_config_json(os.path.join(plugin_dir, "config.json"))
            if config.get("model", "").strip():
                raw = config["model"].strip()
            else:
                raw = "gemini-3.1-pro-preview"

    normalized = raw
    if normalized.startswith("models/"):
        normalized = normalized[len("models/"):]
    return _MODEL_REMAP.get(normalized, normalized)


def _strip_markdown_fences(text: str) -> str:
    """Remove ```json ... ``` fences if present."""
    text = text.strip()
    # Try ```json / ``` first
    m = re.match(r"^```(?:json)?\s*\n(.*?)\n```\s*$", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text


def _parse_llm_json(raw: str) -> Dict[str, Any]:
    """Parse LLM output as JSON, stripping markdown fences if needed."""
    cleaned = _strip_markdown_fences(raw)
    return json.loads(cleaned)


def _build_generate_content_endpoint(base_url: str, model: str) -> str:
    """
    Build the Gemini generateContent endpoint robustly.

    - If base_url already ends with :generateContent, use as-is.
    - Else strip trailing slash; if it ends with /v1beta, append
      /models/{model}:generateContent.
    - Else append /v1beta/models/{model}:generateContent.
    """
    url = base_url.rstrip("/")

    if url.endswith(":generateContent"):
        return url

    if url.endswith("/v1beta"):
        return f"{url}/models/{model}:generateContent"

    return f"{url}/v1beta/models/{model}:generateContent"


def filter_gemini_models(models_json: list) -> list:
    """
    Filter a parsed models list response by supportedGenerationMethods
    and strip the ``models/`` prefix from names.

    Returns a sorted list of model display names (no prefix).
    Never logs or returns API keys.
    """
    filtered: list = []
    for m in models_json:
        methods = m.get("supportedGenerationMethods", [])
        if "generateContent" not in methods:
            continue
        name = m.get("name", "")
        if name.startswith("models/"):
            name = name[len("models/"):]
        if name and name not in _MODEL_BLOCKLIST:
            filtered.append(name)
    return sorted(filtered)


def fetch_models_list(api_key: str, base_url: str = "") -> list:
    """
    Synchronous fetch of Gemini models from GET /v1beta/models with
    pagination.  Uses the ``requests`` library so it works inside
    ComfyUI node execution (which is synchronous).

    Returns the filtered, sorted list of model names.
    Raises RuntimeError on HTTP or API errors.
    Never logs or returns the API key.
    """
    import logging

    _logger = logging.getLogger(__name__)

    # Resolve base URL
    if base_url and base_url.strip():
        base = base_url.strip().rstrip("/")
    else:
        base = resolve_base_url("")
    endpoint = f"{base}/v1beta/models"
    headers = {"x-goog-api-key": api_key}

    filtered: list = []
    page_token: Optional[str] = None

    while True:
        params: Dict[str, Any] = {"pageSize": 1000}
        if page_token:
            params["pageToken"] = page_token

        try:
            resp = requests.get(endpoint, headers=headers, params=params, timeout=30)
        except requests.ConnectionError as exc:
            raise RuntimeError(
                f"Network error — cannot reach Gemini API at {endpoint}: {exc}"
            ) from exc
        except requests.Timeout as exc:
            raise RuntimeError(
                f"Timeout — Gemini API did not respond within 30 s: {exc}"
            ) from exc
        except requests.RequestException as exc:
            raise RuntimeError(
                f"Failed to fetch model list from Gemini API: {exc}"
            ) from exc

        if resp.status_code == 401 or resp.status_code == 403:
            raise RuntimeError(
                "Gemini API authentication failed (HTTP %d) — "
                "check your API key." % resp.status_code
            )
        if resp.status_code != 200:
            safe_body = _sanitize_error_text(resp.text[:1000], api_key)
            raise RuntimeError(
                f"Gemini API models list error {resp.status_code}: {safe_body}"
            )

        body = resp.json()
        models: list = body.get("models", [])
        filtered.extend(filter_gemini_models(models))

        page_token = body.get("nextPageToken")
        if not page_token:
            break

    _logger.info(
        "fetch_models_list: found %d models supporting generateContent",
        len(filtered),
    )
    return filtered


def call_gemini(
    *,
    base_url: str,
    api_key: str,
    model: str,
    image_base64: str,
    user_text: str,
    system_instruction: str,
    temperature: float,
    response_schema: Dict[str, Any],
) -> Dict[str, str]:
    """
    Send a multimodal request to the official Gemini generateContent endpoint.

    Returns a dict with keys:
        ltx_model_prompt       (complete_prompt_json + two newlines + final_cinematic_prompt;
                                this is the single main output to wire to the LTX model)
        complete_prompt_json   (full JSON prompt engineering, formatted with indent=2)
        final_cinematic_prompt
        camera_and_reveal_map
        action_choreography_plan
        continuity_database

    Raises GeminiClientError on failure.
    """

    # Build endpoint URL
    endpoint = _build_generate_content_endpoint(base_url, model)

    # Gemini REST uses x-goog-api-key, not Authorization Bearer
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
    }

    # Build Gemini generateContent payload
    contents = [
        {
            "role": "user",
            "parts": [
                {"text": "首帧参考图："},
                {
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": image_base64,
                    }
                },
                {"text": user_text},
            ],
        }
    ]

    payload: Dict[str, Any] = {
        "contents": contents,
        "systemInstruction": {
            "parts": [{"text": system_instruction}]
        },
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
            "responseSchema": response_schema,
        },
    }

    # Some endpoints may reject responseSchema; try once with, once without.
    raw_text: Optional[str] = None

    for attempt in range(2):
        if attempt == 1:
            # Retry without responseSchema / responseMimeType to handle
            # endpoints that don't support structured output yet.
            payload["generationConfig"].pop("responseSchema", None)
            payload["generationConfig"].pop("responseMimeType", None)

        try:
            resp = requests.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=_REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise GeminiClientError(
                f"HTTP request to Gemini API failed: {exc}"
            ) from exc

        if resp.status_code == 200:
            body = resp.json()
            # Gemini REST response: candidates[0].content.parts[*].text
            candidates = body.get("candidates", [])
            if not candidates:
                raise GeminiClientError(
                    f"API returned empty candidates list. "
                    f"Response snippet: {json.dumps(body)[:500]}"
                )
            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            text_parts = [
                p.get("text", "")
                for p in parts
                if "text" in p
            ]
            raw_text = "\n".join(text_parts)
            if not raw_text:
                raise GeminiClientError(
                    f"API returned empty text from parts. "
                    f"Response snippet: {json.dumps(body)[:500]}"
                )
            break  # success

        # If we got a rejection specifically about structured output, retry
        if attempt == 0 and resp.status_code in (400, 415, 422):
            continue

        # Any other error — raise
        raise GeminiClientError(
            f"Gemini API error {resp.status_code}: {resp.text[:1000]}"
        )

    if raw_text is None:
        raise GeminiClientError("Failed to get a valid response from Gemini API")

    # Parse JSON output
    try:
        parsed = _parse_llm_json(raw_text)
    except json.JSONDecodeError as exc:
        # Parsing failed — return raw content everywhere but flag the error.
        return {
            "ltx_model_prompt": (
                f"JSON PARSE ERROR: {exc}\n\nRaw output:\n{raw_text}"
            ),
            "complete_prompt_json": (
                f"JSON PARSE ERROR: {exc}\n\nRaw output:\n{raw_text}"
            ),
            "final_cinematic_prompt": raw_text,
            "camera_and_reveal_map": "",
            "action_choreography_plan": "",
            "continuity_database": (
                f"JSON PARSE ERROR: Model output was not valid JSON. "
                f"Raw output returned in ltx_model_prompt/complete_prompt_json/final_cinematic_prompt. "
                f"Error: {exc}"
            ),
        }

    # Validate required fields; fill missing with empty strings.
    complete_prompt_json = json.dumps(
        parsed, ensure_ascii=False, indent=2
    )
    final_cinematic_prompt = parsed.get("final_cinematic_prompt", "")
    return {
        "ltx_model_prompt": complete_prompt_json + "\n\n" + final_cinematic_prompt,
        "complete_prompt_json": complete_prompt_json,
        "final_cinematic_prompt": final_cinematic_prompt,
        "camera_and_reveal_map": parsed.get("camera_and_reveal_map", ""),
        "action_choreography_plan": parsed.get("action_choreography_plan", ""),
        "continuity_database": parsed.get("continuity_database", ""),
    }
