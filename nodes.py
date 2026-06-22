"""
ComfyUI custom node: LTX2.3 Cinematic Prompt Director (Single Image).

Converts a ComfyUI IMAGE tensor to a raw base64 PNG, sends it
together with a scene description and duration to the Yunwu
Gemini-native generateContent endpoint, and returns the four-field
cinematic prompt JSON plus the final executable prompt string.
"""

from __future__ import annotations

import base64
import io
import logging
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import torch
from PIL import Image

from .gemini_client import (
    call_gemini,
    resolve_api_key,
    resolve_base_url,
    resolve_model,
    fetch_models_list,
    filter_gemini_models,
    _sanitize_error_text,
    GeminiClientError,
)
from .prompt_templates import (
    SYSTEM_INSTRUCTION,
    RESPONSE_SCHEMA,
    build_schema_directive,
    build_single_image_user_text,
)

logger = logging.getLogger(__name__)

# ComfyUI node registration helpers
# ---------------------------------------------------------------------------
# If ComfyUI is not importable (e.g. during standalone syntax-check), provide
# graceful stubs so py_compile succeeds.
try:
    from comfy.utils import common_ksampler  # noqa: F401 — unused, for env check
    _IN_COMFY = True
except ImportError:
    _IN_COMFY = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitize_base_url(raw: str) -> str:
    """
    Return *raw* if it looks like a real URL, otherwise return "".

    This prevents leaked/corrupted widget values (e.g. an API key or model
    name that shifted into the base_url slot from an old workflow) from being
    used as a URL.  Only values that start with ``http://`` or ``https://``,
    or end with ``:generateContent``, are considered intentional.
    """
    if not raw or not raw.strip():
        return ""
    v = raw.strip()
    if v.startswith("http://") or v.startswith("https://"):
        return v
    if v.endswith(":generateContent"):
        return v
    # Looks like a leaked non-URL value — discard it so the resolver
    # falls through to env / config / default.
    return ""


def _safe_temperature(value: Any) -> float:
    """
    Return *value* as a float, falling back to 0.7 if conversion fails.

    Protects against legacy corrupted workflows where a non-numeric string
    (e.g. a model name) shifted into the temperature widget.
    """
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.7


# ---------------------------------------------------------------------------
# Tensor -> raw base64 PNG (no data URL prefix — for Gemini inline_data)
# ---------------------------------------------------------------------------

def _tensor_to_base64(image_tensor: torch.Tensor) -> str:
    """
    Convert a ComfyUI IMAGE tensor to a PNG base64 string (raw, no prefix).

    ComfyUI IMAGE tensors are typically [B, H, W, C] float32 in 0..1.
    We handle [B,H,W,C] and [H,W,C] shapes.  Only the first batch
    element (index 0) is used.

    Handles RGB, RGBA, and grayscale (1-channel) inputs.
    """
    if image_tensor.dim() == 4:
        img = image_tensor[0]  # [H, W, C]
    elif image_tensor.dim() == 3:
        img = image_tensor  # [H, W, C]
    else:
        raise ValueError(
            f"Expected IMAGE tensor with 3 or 4 dims, got shape {image_tensor.shape}"
        )

    # Safe for CUDA tensors: detach and move to CPU before numpy conversion
    img = img.detach().cpu()

    # Clamp to 0..1, scale to 0..255 uint8
    img = img.clamp(0.0, 1.0)
    img = (img * 255.0).round().to(torch.uint8)

    # Handle channel count
    channels = img.shape[-1]

    if channels == 4:
        # RGBA → RGB (slice alpha channel)
        img = img[..., :3]
    elif channels == 1:
        # Grayscale → RGB (repeat single channel to 3 channels)
        img = img.repeat(1, 1, 3)

    # Convert to PIL Image (H, W, 3) → RGB
    pil_img = Image.fromarray(img.numpy(), mode="RGB")

    # Encode as PNG base64 (raw base64, no data URL prefix)
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    return b64


# ---------------------------------------------------------------------------
# Node: LTX2.3 Cinematic Prompt Director (Single Image)
# ---------------------------------------------------------------------------

class LTX23CinematicPromptDirectorSingle:
    """
    ComfyUI node that generates LTX-2.3 cinematic prompt JSON from a single
    reference image and scene description via the Yunwu Gemini-native
    generateContent API.
    """

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                "image": ("IMAGE",),
                "scene_description": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "Describe the scene in detail...",
                }),
                "duration": ("INT", {
                    "default": 5,
                    "min": 4,
                    "max": 10,
                    "step": 1,
                }),
            },
            "optional": {
                "base_url": ("STRING", {
                    "default": "",
                    "placeholder": "Advanced: override base URL (default: https://yunwu.ai)",
                    "advanced": True,
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "placeholder": "Yunwu API key (leave empty to use env / config.json)",
                }),
                "model": ("STRING", {
                    "default": "gemini-3.1-pro-preview",
                    "placeholder": "Model name (e.g. gemini-3.1-pro-preview, gemini-2.5-flash)",
                }),
                "temperature": ("FLOAT", {
                    "default": 0.7,
                    "min": 0.0,
                    "max": 1.5,
                    "step": 0.05,
                }),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = (
        "ltx_model_prompt",
        "complete_prompt_json",
        "final_cinematic_prompt",
        "camera_and_reveal_map",
        "action_choreography_plan",
        "continuity_database",
    )

    FUNCTION = "generate"
    CATEGORY = "LTX2.3/Prompt"
    OUTPUT_NODE = True

    def generate(
        self,
        image: torch.Tensor,
        scene_description: str,
        duration: int,
        base_url: str = "",
        api_key: str = "",
        model: str = "",
        temperature: float = 0.7,
    ) -> Tuple[str, str, str, str, str, str]:
        # --- Input validation -------------------------------------------------
        if not scene_description or not scene_description.strip():
            raise ValueError("scene_description is required and cannot be empty.")

        # Clamp duration defensively
        duration = max(4, min(10, int(duration)))

        # --- Resolve credentials ----------------------------------------------
        resolved_api_key = resolve_api_key(api_key)
        if not resolved_api_key:
            raise ValueError(
                "API key is required. Set it via node input, "
                "YUNWU_API_KEY / GOOGLE_API_KEY / GEMINI_API_KEY environment variable, or config.json."
            )

        # Sanitize base_url: if a corrupted non-URL value leaked in from an
        # old workflow (e.g. api_key or model name in the base_url slot),
        # discard it so the resolver falls through to env / config / default.
        sanitized_base_url = _sanitize_base_url(base_url)
        resolved_base_url = resolve_base_url(sanitized_base_url)

        resolved_model = resolve_model(model)

        # --- Diagnostic logging: start of generation --------------------------
        parsed_url = urllib.parse.urlparse(resolved_base_url)
        safe_endpoint = (parsed_url.hostname or "unknown") + (parsed_url.path or "")
        logger.info(
            "LTX23 starting generation: scene_desc_len=%d, duration=%d, "
            "model=%s, endpoint=%s",
            len(scene_description), duration, resolved_model, safe_endpoint,
        )

        # --- Defensive temperature --------------------------------------------
        safe_temp = _safe_temperature(temperature)

        # --- Convert image tensor to raw base64 PNG ---------------------------
        image_base64 = _tensor_to_base64(image)

        # --- Build user prompt text -------------------------------------------
        user_text = build_single_image_user_text(scene_description, duration)

        # --- Build system instruction (includes textual schema directive) ------
        system_instruction = SYSTEM_INSTRUCTION + build_schema_directive()

        # --- Call Gemini API -------------------------------------------------
        try:
            result = call_gemini(
                base_url=resolved_base_url,
                api_key=resolved_api_key,
                model=resolved_model,
                image_base64=image_base64,
                user_text=user_text,
                system_instruction=system_instruction,
                temperature=safe_temp,
                response_schema=RESPONSE_SCHEMA,
            )
        except GeminiClientError as exc:
            raise RuntimeError(
                f"Gemini API call failed: {exc}"
            ) from exc

        # --- Diagnostic logging: post-API results -----------------------------
        ltx_prompt = result.get("ltx_model_prompt", "")
        cp_json = result.get("complete_prompt_json", "")
        fc_prompt = result.get("final_cinematic_prompt", "")
        cam_map = result.get("camera_and_reveal_map", "")
        action_plan = result.get("action_choreography_plan", "")
        cont_db = result.get("continuity_database", "")

        logger.info(
            "LTX23 generation result lengths: ltx_model_prompt=%d, "
            "complete_prompt_json=%d, final_cinematic_prompt=%d, "
            "camera_and_reveal_map=%d, action_choreography_plan=%d, "
            "continuity_database=%d",
            len(ltx_prompt), len(cp_json), len(fc_prompt),
            len(cam_map), len(action_plan), len(cont_db),
        )

        if not fc_prompt:
            logger.warning("LTX23: final_cinematic_prompt is empty!")
        if not cam_map:
            logger.info("LTX23: camera_and_reveal_map is empty")
        if not action_plan:
            logger.info("LTX23: action_choreography_plan is empty")
        if not cont_db:
            logger.info("LTX23: continuity_database is empty")

        if "JSON PARSE ERROR" in cp_json:
            logger.warning("LTX23: complete_prompt_json contains JSON PARSE ERROR")
        if cont_db.startswith("JSON PARSE ERROR"):
            logger.warning("LTX23: continuity_database starts with JSON PARSE ERROR")

        return (
            result["ltx_model_prompt"],
            result["complete_prompt_json"],
            result["final_cinematic_prompt"],
            result["camera_and_reveal_map"],
            result["action_choreography_plan"],
            result["continuity_database"],
        )


# ---------------------------------------------------------------------------
# Node: Yunwu Model List
# ---------------------------------------------------------------------------

class GeminiOfficialModelList:
    """
    Utility node that fetches available Gemini models from the Yunwu API.

    Calls GET /v1beta/models with x-goog-api-key and returns model IDs, one per line.

    Use this with a single Yunwu API key to browse available models,
    then copy the desired model name into the Prompt Director node.
    """

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {},
            "optional": {
                "api_key": ("STRING", {
                    "default": "",
                    "placeholder": "Yunwu API key (leave empty to use env / config.json)",
                }),
                "base_url": ("STRING", {
                    "default": "",
                    "placeholder": "Advanced: override base URL (default: https://yunwu.ai)",
                    "advanced": True,
                }),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("model_list",)

    FUNCTION = "list_models"
    CATEGORY = "LTX2.3/Prompt"
    OUTPUT_NODE = True

    def list_models(
        self,
        api_key: str = "",
        base_url: str = "",
    ) -> Tuple[str,]:
        # --- Resolve API key --------------------------------------------------
        resolved_api_key = resolve_api_key(api_key)
        if not resolved_api_key:
            raise ValueError(
                "API key is required to list models. Set it via node input, "
                "YUNWU_API_KEY / GOOGLE_API_KEY / GEMINI_API_KEY environment variable, or config.json."
            )

        # --- Resolve base URL -------------------------------------------------
        resolved_base = base_url.strip() if base_url and base_url.strip() else ""

        # --- Fetch models via shared helper -----------------------------------
        filtered = fetch_models_list(
            api_key=resolved_api_key,
            base_url=resolved_base,
        )

        model_list = "\n".join(filtered)

        logger.info(
            "GeminiOfficialModelList: found %d models",
            len(filtered),
        )

        return (model_list,)


# ---------------------------------------------------------------------------
# HTTP route: interactive model list endpoint
# ---------------------------------------------------------------------------
# Registers POST /ltx23/gemini/models on ComfyUI's built-in PromptServer
# so the web JS extension can fetch models interactively.
# Calls GET /v1beta/models with x-goog-api-key.
# Falls back gracefully when ComfyUI is not importable (py_compile checks).

_ROUTE_REGISTERED = False

try:
    from aiohttp import web as aiohttp_web
    from server import PromptServer  # type: ignore[import-untyped]

    @PromptServer.instance.routes.post("/ltx23/gemini/models")
    async def _ltx23_gemini_models_route(request: aiohttp_web.Request):
        """Return filtered Gemini models as JSON: {models: [...]}."""
        import asyncio as _asyncio
        import logging as _route_logging
        _rlog = _route_logging.getLogger(__name__)

        try:
            body = await request.json()
        except Exception:
            return aiohttp_web.json_response(
                {"error": "Invalid JSON body"}, status=400
            )

        raw_api_key = (body.get("api_key") or "").strip()
        raw_base_url = (body.get("base_url") or "").strip()

        # Resolve API key through the standard precedence chain.
        # NEVER log or return the key.
        resolved_key = resolve_api_key(raw_api_key)
        if not resolved_key:
            return aiohttp_web.json_response(
                {"error": "API key required — set via node input, env, or config.json"},
                status=401,
            )

        # Resolve base URL: pass through resolve_base_url for consistent
        # precedence (node input > config.json > Yunwu default).
        # Strip any :generateContent suffix that may have leaked in.
        resolved_base = resolve_base_url(raw_base_url)
        if resolved_base.endswith(":generateContent"):
            resolved_base = resolved_base.rsplit(":", 1)[0]

        # Reuse the existing synchronous helper — no duplicated aiohttp logic.
        try:
            filtered = await _asyncio.to_thread(
                fetch_models_list,
                api_key=resolved_key,
                base_url=resolved_base,
            )
        except RuntimeError as exc:
            # Classify error for a friendlier HTTP status.
            msg = str(exc)
            status = 502
            if (
                "authentication" in msg.lower()
                or "401" in msg
                or "403" in msg
            ):
                status = 401
            elif (
                "network" in msg.lower()
                or "cannot reach" in msg.lower()
                or "timeout" in msg.lower()
            ):
                status = 502
            # Sanitise: never echo the raw API key back.
            safe_msg = _sanitize_error_text(msg, resolved_key)
            _rlog.error("/ltx23/gemini/models error: %s", safe_msg)
            return aiohttp_web.json_response(
                {"error": safe_msg}, status=status
            )
        except Exception as exc:
            _rlog.exception("Unexpected error in /ltx23/gemini/models")
            return aiohttp_web.json_response(
                {"error": f"Internal error: {exc}"},
                status=500,
            )

        _rlog.info(
            "/ltx23/gemini/models: returned %d models: %s",
            len(filtered),
            ", ".join(filtered),
        )

        return aiohttp_web.json_response({"models": filtered})

    _ROUTE_REGISTERED = True

except ImportError:
    # ComfyUI server not available (e.g. py_compile check, standalone test).
    pass


# ---------------------------------------------------------------------------
# Node registration for ComfyUI
# ---------------------------------------------------------------------------
NODE_CLASS_MAPPINGS = {
    "LTX23CinematicPromptDirectorSingle": LTX23CinematicPromptDirectorSingle,
    "GeminiOfficialModelList": GeminiOfficialModelList,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LTX23CinematicPromptDirectorSingle": "LTX2.3 Cinematic Prompt Director (Single Image)",
    "GeminiOfficialModelList": "Yunwu Model List",
}
