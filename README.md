# ComfyUI LTX2.3 Cinematic Prompt Director (Single Image)

A ComfyUI custom node that generates LTX-2.3 cinematic prompt JSON from a
**single reference image** and scene description.  It faithfully reproduces the
prompt protocol from the original `ltx-2.3-cinematic-director` application and
calls **Gemini 3.1 Pro** through the **Yunwu Gemini native generateContent
HTTP API**.

## Features

- **Single-image mode only** — provide one frame, the AI infers smooth
  subsequent action and camera movement.
- Outputs six fields:
  - `ltx_model_prompt` — **main output** for the LTX model: complete JSON + two newlines + final_cinematic_prompt in one string. Wire this to the LTX2.3 prompt input.
  - `complete_prompt_json` — **preview/debug**: the full JSON prompt engineering (pretty-printed).
  - `final_cinematic_prompt` — **preview/debug**: extracted `final_cinematic_prompt` field.
  - `camera_and_reveal_map` — **preview/debug**: camera move and revealed-content map.
  - `action_choreography_plan` — **preview/debug**: action choreography with timeblocks.
  - `continuity_database` — **preview/debug**: Visual Archetypes and Voice Profiles tracker.
- Preserves the tuned V57 "4 Pillars of Cinematic Mastery" prompt rules.
- Final prompt always starts with `[SYSTEM: Visuals contain NO on-screen text.]`.
- No Google SDK dependency — uses standard `requests` + Gemini native
  `/v1beta/models/{model}:generateContent` endpoint with `x-goog-api-key` header.
- Sends Gemini native `responseSchema` for structured JSON output.
- API key is configurable via node input, environment variables, or
  `config.json` — never hardcoded.

## Installation

1. Copy this entire folder into your ComfyUI `custom_nodes` directory:

   ```
   ComfyUI/
     custom_nodes/
       comfyui-ltx23-prompt-director/
         __init__.py
         nodes.py
         yunwu_client.py
         prompt_templates.py
         config.example.json
         requirements.txt
         README.md
   ```

2. Install Python dependencies (ComfyUI's own Python environment):

   ```bash
   cd ComfyUI/custom_nodes/comfyui-ltx23-prompt-director
   pip install -r requirements.txt
   ```

   > Note: `torch` and `Pillow` are already part of ComfyUI; `requests` is
   > usually present as well.  The requirements file is a safety net.

3. Restart ComfyUI.

## Configuration

You must provide a Yunwu API key.  Choose one method (in order of precedence):

### A. Node input (per-workflow)
Set the `api_key` string input on the node directly.

### B. Environment variable
```bash
export YUNWU_API_KEY="***"
export YUNWU_BASE_URL="https://yunwu.ai"      # optional
export YUNWU_MODEL="gemini-3.1-pro-preview"    # optional
```

### C. config.json
Copy `config.example.json` to `config.json` and fill in your key:
```json
{
    "api_key": "***",
    "base_url": "",
    "model": "gemini-3.1-pro-preview"
}
```

## API Transport

This plugin calls the **Gemini native generateContent REST endpoint**:

```
POST https://yunwu.ai/v1beta/models/gemini-3.1-pro-preview:generateContent
```

- **Headers:** `x-goog-api-key: <your-yunwu-key>`, `Content-Type: application/json`
- **Payload:** Gemini `contents` / `systemInstruction` / `generationConfig` format
- **Structured output:** Sends `responseSchema` + `responseMimeType: "application/json"`

The `base_url` config value should be `https://yunwu.ai` (or your custom
endpoint).  The `/v1beta/models/{model}:generateContent` path is appended
automatically unless the base URL already includes `/v1beta` or the full
`:generateContent` suffix.

## Node Usage

### Node: LTX2.3 Cinematic Prompt Director (Single Image)

**Category:** `LTX2.3/Prompt`

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `image` | IMAGE | *required* | Reference first frame |
| `scene_description` | STRING (multiline) | *required* | Describe the scene |
| `duration` | INT | 5 (min 4, max 10) | Target video duration in seconds |
| `base_url` | STRING | *empty* | (Advanced) Optional override; leave empty for Yunwu |
| `api_key` | STRING | *empty* | Yunwu API key (optional — env/config recommended) |
| `model` | STRING | `gemini-3.1-pro-preview` | Model name |
| `temperature` | FLOAT | 0.7 (0–1.5) | Generation temperature |

**Base URL is an advanced compatibility override** — it exists only to preserve widget positional compatibility with older saved workflows. You do NOT need to fill it in. For normal use, leave it empty and the node automatically resolves `https://yunwu.ai` via its internal default. If you are using a non-default or self-hosted Yunwu endpoint, configure `base_url` in `config.json` or via the `YUNWU_BASE_URL` environment variable instead.

> **Compatibility note:** The `base_url` widget was re-introduced in positional order (before `api_key`) so that workflows saved before its removal continue to load correctly. The node also includes defensive guards against corrupted widget values (e.g. a model name accidentally fed as temperature) that could occur when loading workflows saved during the transitional period.

| Output | Type | Description |
|--------|------|-------------|
| `ltx_model_prompt` | STRING | **Main output — wire this to LTX2.3.** Contains the complete JSON prompt engineering (pretty-printed) followed by two newlines and the `final_cinematic_prompt` pure text. This is the single string the LTX model needs. |
| `complete_prompt_json` | STRING | **Preview/debug.** Full JSON prompt engineering (all four fields — `camera_and_reveal_map`, `action_choreography_plan`, `continuity_database`, `final_cinematic_prompt`) serialized as pretty-printed JSON. |
| `final_cinematic_prompt` | STRING | **Preview/debug.** Extracted `final_cinematic_prompt` field. Starts with `[SYSTEM: Visuals contain NO on-screen text.]`. |
| `camera_and_reveal_map` | STRING | **Preview/debug.** Camera move definition and revealed-content map |
| `action_choreography_plan` | STRING | **Preview/debug.** Action choreography with timeblocks and micro-expressions |
| `continuity_database` | STRING | **Preview/debug.** Visual Archetypes and Voice Profiles tracker |

### Wiring to LTX2.3

Connect **`ltx_model_prompt`** → LTX2.3 prompt input.  This is the single output that delivers both the complete JSON prompt engineering AND the final cinematic prompt together — exactly what the LTX model needs.  The `complete_prompt_json`, `final_cinematic_prompt`, `camera_and_reveal_map`, `action_choreography_plan`, and `continuity_database` outputs are provided as separate preview/debug channels and are NOT needed for generation — they exist for inspection and optional conditioning.

## Troubleshooting

- **"API key is required"** — set the key via one of the three config methods.
- **"HTTP request to Yunwu failed"** — verify network connectivity. If you are using a non-default Yunwu endpoint, set `YUNWU_BASE_URL` or the `base_url` key in `config.json`.
- **"JSON PARSE ERROR"** in `ltx_model_prompt` — the model returned
  non-JSON output.  The raw text is available in `ltx_model_prompt`,
  `complete_prompt_json`, and `final_cinematic_prompt`.  Check the model
  endpoint and `responseSchema` compatibility.
- **No ComfyUI imports available** — the plugin gracefully degrades for
  `py_compile` checks outside ComfyUI.

## License

MIT — see the original `ltx-2.3-cinematic-director` project.
