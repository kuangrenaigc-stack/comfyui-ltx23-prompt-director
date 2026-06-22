# ComfyUI LTX2.3 Cinematic Prompt Director (Single Image)

A ComfyUI custom node that generates LTX-2.3 cinematic prompt JSON from a
**single reference image** and scene description.  It faithfully reproduces the
prompt protocol from the original `ltx-2.3-cinematic-director` application and
calls the **Yunwu Gemini-native API** (`https://yunwu.ai`).

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
- Uses Yunwu's Gemini-native API — no Google SDK dependency, standard `requests`
  with `x-goog-api-key` header.
- Requests structured JSON output via Gemini-native `responseSchema` +
  `responseMimeType: "application/json"` in `generationConfig`.
- Falls back gracefully if `responseSchema` is rejected (retries without it,
  keeping the textual schema directive in the system instruction).
- API key is configurable via node input, environment variables, or
  `config.json` — never hardcoded.

### Bonus: Interactive Model Selection

The Prompt Director node has a **built-in model selector** so you don't
need the separate `Yunwu Model List` node just to pick a model:

1. Paste your Yunwu API key into the `api_key` widget on the
   `LTX23CinematicPromptDirectorSingle` node.
2. Click the **Refresh Yunwu Models** button.
3. Pick a model from the `available_model` dropdown.
4. The selected model is automatically written into the `model` text widget.

The existing `model` text widget is preserved — workflows saved before this
update continue to work.  The default model is `gemini-3.1-pro-preview` as a
fallback; you are never locked to a single model.

**Additional read-only widgets:**
- `available_models_text` — always shows the full model list from the last refresh (multiline, read-only).
- `model_refresh_status` — shows the last refresh result or any error message.

**How it works under the hood:** the button calls `POST /ltx23/gemini/models`
on ComfyUI's built-in server, which fetches `GET /v1beta/models` from the
Yunwu API with your key via `x-goog-api-key`, reads Gemini-native model IDs,
and returns a clean list.  Your API key is sent in the request body and is
**never logged or returned** in the response.

### Yunwu Model List node (legacy)

A second utility node **Yunwu Model List** is included.  It calls
`GET /v1beta/models` with `x-goog-api-key` and returns model IDs, one per line.
Use it to browse available models and copy the desired name into the
Prompt Director node — one key for both discovery and generation.

## Installation

1. Copy this entire folder into your ComfyUI `custom_nodes` directory:

   ```
   ComfyUI/
     custom_nodes/
       comfyui-ltx23-prompt-director/
         __init__.py
         nodes.py
         gemini_client.py
         prompt_templates.py
         config.example.json
         requirements.txt
         README.md
         web/
           ltx23_model_selector.js
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

You must provide a **Yunwu API key**.  Get one from
your Yunwu account.

Choose one method (in order of precedence):

### A. Node input (per-workflow)
Set the `api_key` string input on the node directly.

### B. Environment variable
```bash
export YUNWU_API_KEY="your-key-here"
# or (legacy compatibility)
export GOOGLE_API_KEY="your-key-here"
export GEMINI_API_KEY="your-key-here"

export GEMINI_MODEL="gemini-3.1-pro-preview"    # optional, override model name
```

### C. config.json
Copy `config.example.json` to `config.json` and fill in your key:
```json
{
    "api_key": "your-key-here",
    "base_url": "",
    "model": "gemini-3.1-pro-preview"
}
```

> **base_url is optional.**  Leave it empty and the default
> `https://yunwu.ai` endpoint is used automatically.
> Only set it if you need to route through a proxy or custom endpoint.

## API Transport

This plugin calls **Yunwu's Gemini-native generateContent endpoint**:

```
POST https://yunwu.ai/v1beta/models/{model}:generateContent
```

- **Auth:** `x-goog-api-key: <your-key>` header
- **Content-Type:** `application/json`
- **Payload format (Gemini-native):**
  ```json
  {
    "contents": [
      {
        "role": "user",
        "parts": [
          {"text": "首帧参考图："},
          {"inline_data": {"mime_type": "image/png", "data": "<base64>"}},
          {"text": "<user prompt text>"}
        ]
      }
    ],
    "systemInstruction": {
      "parts": [{"text": "<system instruction>"}]
    },
    "generationConfig": {
      "temperature": 0.7,
      "responseMimeType": "application/json",
      "responseSchema": { ... }
    }
  }
  ```
- **Response:** parsed from `candidates[0].content.parts[*].text`
- **Fallback:** if Yunwu rejects `responseSchema` (HTTP 400/415/422), retries
  once without it while keeping `responseMimeType: "application/json"` and
  the textual schema directive in `systemInstruction`.

The model list node and refresh button call:

```
GET https://yunwu.ai/v1beta/models
```

with `x-goog-api-key` header.  Both Gemini-native (`{"models": [...]}`) and
OpenAI-style (`{"data": [...]}`) responses are supported defensively.
Models are filtered to those supporting `generateContent` when
`supportedGenerationMethods` is present.

## Node Usage

### Node: LTX2.3 Cinematic Prompt Director (Single Image)

**Category:** `LTX2.3/Prompt`

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `image` | IMAGE | *required* | Reference first frame |
| `scene_description` | STRING (multiline) | *required* | Describe the scene |
| `duration` | INT | 5 (min 4, max 10) | Target video duration in seconds |
| `base_url` | STRING | *empty* | (Advanced) Override API base URL — leave empty for `https://yunwu.ai` |
| `api_key` | STRING | *empty* | Yunwu API key (optional — env/config recommended) |
| `model` | STRING | `gemini-3.1-pro-preview` | Model name |
| `temperature` | FLOAT | 0.7 (0–1.5) | Generation temperature |

**Base URL is an advanced compatibility override** — it exists only to preserve
widget positional compatibility with older saved workflows. You do NOT need to
fill it in. For normal use, leave it empty and the node automatically uses
`https://yunwu.ai`. If you are using a proxy, configure
`base_url` in `config.json` instead.

| Output | Type | Description |
|--------|------|-------------|
| `ltx_model_prompt` | STRING | **Main output — wire this to LTX2.3.** Contains the complete JSON prompt engineering (pretty-printed) followed by two newlines and the `final_cinematic_prompt` pure text. |
| `complete_prompt_json` | STRING | **Preview/debug.** Full JSON prompt engineering (all four fields) serialized as pretty-printed JSON. |
| `final_cinematic_prompt` | STRING | **Preview/debug.** Extracted `final_cinematic_prompt` field. |
| `camera_and_reveal_map` | STRING | **Preview/debug.** Camera move definition and revealed-content map |
| `action_choreography_plan` | STRING | **Preview/debug.** Action choreography with timeblocks |
| `continuity_database` | STRING | **Preview/debug.** Visual Archetypes and Voice Profiles tracker |

### Node: Yunwu Model List

**Category:** `LTX2.3/Prompt`

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `api_key` | STRING | *empty* | Yunwu API key (env/config recommended) |
| `base_url` | STRING | *empty* | (Advanced) Override base URL for models endpoint |

| Output | Type | Description |
|--------|------|-------------|
| `model_list` | STRING | Available models supporting `generateContent`, one per line |

### Wiring to LTX2.3

Connect **`ltx_model_prompt`** → LTX2.3 prompt input.  This is the single output
that delivers both the complete JSON prompt engineering AND the final cinematic
prompt together — exactly what the LTX model needs.

## Troubleshooting

- **"API key is required"** — set the key via one of the three config methods.
- **"HTTP request to Yunwu API failed"** — verify network connectivity and
  that your API key is valid.  If using a proxy, check your `base_url` setting.
- **"JSON PARSE ERROR"** in `ltx_model_prompt` — the model returned
  non-JSON output.  The raw text is available in `ltx_model_prompt`,
  `complete_prompt_json`, and `final_cinematic_prompt`.  Check the model
  endpoint and `responseSchema` compatibility.
- **No ComfyUI imports available** — the plugin gracefully degrades for
  `py_compile` checks outside ComfyUI.
- **Model refresh button says "API key required"** — make sure you filled
  in the `api_key` widget (or set `YUNWU_API_KEY` / `GOOGLE_API_KEY` /
  `GEMINI_API_KEY` env var or `config.json`).  The route uses the same
  `resolve_api_key` chain as generation.
- **Model list is empty** — verify your API key is valid at
  your Yunwu account.  Also check that
  `base_url` is empty (unless you're intentionally using a proxy).

## License

MIT — see the original `ltx-2.3-cinematic-director` project.
