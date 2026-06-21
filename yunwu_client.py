"""
Yunwu API client — Gemini native generateContent HTTP interface.

Calls POST {base_url}/v1beta/models/{model}:generateContent with
Gemini-native REST payload.  Uses x-goog-api-key header (no Authorization
Bearer).  No Google SDK / @google/genai dependency.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional

import requests

# Default fallback: documented as a known Yunwu endpoint pattern, not an
# assertion that it is live or guaranteed.  Users SHOULD set their own.
_DEFAULT_YUNWU_BASE_URL = "https://yunwu.ai"

# Hard limit in seconds for a single API call so the ComfyUI node does not
# hang indefinitely.
_REQUEST_TIMEOUT = 120


class YunwuClientError(Exception):
    """Raised when the Yunwu API returns an error or is unreachable."""


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
      2. env YUNWU_BASE_URL
      3. plugin config.json (base_url key)
      4. documented fallback placeholder (_DEFAULT_YUNWU_BASE_URL)
    """
    if node_input and node_input.strip():
        return node_input.strip().rstrip("/")

    env_val = os.environ.get("YUNWU_BASE_URL", "").strip()
    if env_val:
        return env_val.rstrip("/")

    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    config = _load_config_json(os.path.join(plugin_dir, "config.json"))
    if config.get("base_url", "").strip():
        return config["base_url"].strip().rstrip("/")

    return _DEFAULT_YUNWU_BASE_URL


def resolve_api_key(node_input: str = "") -> str:
    """
    Resolve api_key with this precedence:
      1. non-empty node input
      2. env YUNWU_API_KEY
      3. plugin config.json (api_key key)
    Returns "" if nothing is found.
    """
    if node_input and node_input.strip():
        return node_input.strip()

    env_val = os.environ.get("YUNWU_API_KEY", "").strip()
    if env_val:
        return env_val

    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    config = _load_config_json(os.path.join(plugin_dir, "config.json"))
    return config.get("api_key", "").strip()


def resolve_model(node_input: str = "") -> str:
    """Resolve model with precedence: node input > env YUNWU_MODEL > config > default."""
    if node_input and node_input.strip():
        return node_input.strip()

    env_val = os.environ.get("YUNWU_MODEL", "").strip()
    if env_val:
        return env_val

    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    config = _load_config_json(os.path.join(plugin_dir, "config.json"))
    if config.get("model", "").strip():
        return config["model"].strip()

    return "gemini-3.1-pro-preview"


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


def call_yunwu(
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
    Send a multimodal request to the Yunwu Gemini generateContent endpoint.

    Returns a dict with keys:
        ltx_model_prompt       (complete_prompt_json + two newlines + final_cinematic_prompt;
                                this is the single main output to wire to the LTX model)
        complete_prompt_json   (full JSON prompt engineering, formatted with indent=2)
        final_cinematic_prompt
        camera_and_reveal_map
        action_choreography_plan
        continuity_database

    Raises YunwuClientError on failure.
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

    # Some proxies may reject responseSchema; try once with, once without.
    raw_text: Optional[str] = None

    for attempt in range(2):
        if attempt == 1:
            # Retry without responseSchema / responseMimeType to handle
            # strict proxies that don't support structured output yet.
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
            raise YunwuClientError(
                f"HTTP request to Yunwu failed: {exc}"
            ) from exc

        if resp.status_code == 200:
            body = resp.json()
            # Gemini REST response: candidates[0].content.parts[*].text
            candidates = body.get("candidates", [])
            if not candidates:
                raise YunwuClientError(
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
                raise YunwuClientError(
                    f"API returned empty text from parts. "
                    f"Response snippet: {json.dumps(body)[:500]}"
                )
            break  # success

        # If we got a rejection specifically about structured output, retry
        if attempt == 0 and resp.status_code in (400, 415, 422):
            continue

        # Any other error — raise
        raise YunwuClientError(
            f"Yunwu API error {resp.status_code}: {resp.text[:1000]}"
        )

    if raw_text is None:
        raise YunwuClientError("Failed to get a valid response from Yunwu API")

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
