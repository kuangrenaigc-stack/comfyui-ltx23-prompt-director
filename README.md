# ComfyUI LTX2.3 Cinematic Prompt Director (Single Image)

A ComfyUI custom node that generates LTX-2.3 cinematic prompt JSON from a
**single reference image** and scene description.  It faithfully reproduces the
prompt protocol from the original `ltx-2.3-cinematic-director` application and
calls the **official Gemini Developer API** (`generativelanguage.googleapis.com`).

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

### Bonus: Interactive Model Selection (NEW)

The Prompt Director node now has a **built-in model selector** so you don't
need the separate `GeminiOfficialModelList` node just to pick a model:

1. Paste your Gemini API key into the `api_key` widget on the
   `LTX23CinematicPromptDirectorSingle` node.
2. Click the **Refresh Gemini Models** button.
3. Pick a model from the `available_model` dropdown.
4. The selected model is automatically written into the `model` text widget.

The existing `model` text widget is preserved — workflows saved before this
update continue to work.  The default model is `gemini-3.1-pro-preview` as a
fallback; you are never locked to a single model.

**How it works under the hood:** the button calls `POST /ltx23/gemini/models`
on ComfyUI's built-in server, which fetches `GET /v1beta/models` from the
Gemini API with your key, filters to models that support `generateContent`,
and returns a clean list.  Your API key is sent in the request body and is
**never logged or returned** in the response.

### Gemini Official Model List node (legacy)

A second utility node **GeminiOfficialModelList** is included.  It calls
`GET /v1beta/models` with your API key and returns a list of models that
support `generateContent`, one per line (with the `models/` prefix stripped).
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

You must provide a **Gemini API key**.  Get one from
[Google AI Studio](https://aistudio.google.com/apikey).

Choose one method (in order of precedence):

### A. Node input (per-workflow)
Set the `api_key` string input on the node directly.

### B. Environment variable
```bash
export GOOGLE_API_KEY="your-key-here"
# (GOOGLE_API_KEY takes precedence when both are set)
# or
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

> **base_url is optional.**  Leave it empty and the official
> `https://generativelanguage.googleapis.com` endpoint is used automatically.
> Only set it if you need to route through a proxy or custom endpoint.

## API Transport

This plugin calls the **official Gemini Developer API generateContent REST endpoint**:

```
POST https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-pro-preview:generateContent
```

- **Headers:** `x-goog-api-key: <your-gemini-key>`, `Content-Type: application/json`
- **Payload:** Gemini `contents` / `systemInstruction` / `generationConfig` format
- **Structured output:** Sends `responseSchema` + `responseMimeType: "application/json"`

The model list node calls:

```
GET https://generativelanguage.googleapis.com/v1beta/models
```

## Node Usage

### Node: LTX2.3 Cinematic Prompt Director (Single Image)

**Category:** `LTX2.3/Prompt`

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `image` | IMAGE | *required* | Reference first frame |
| `scene_description` | STRING (multiline) | *required* | Describe the scene |
| `duration` | INT | 5 (min 4, max 10) | Target video duration in seconds |
| `base_url` | STRING | *empty* | (Advanced) Override API endpoint — leave empty for official |
| `api_key` | STRING | *empty* | Gemini API key (optional — env/config recommended) |
| `model` | STRING | `gemini-3.1-pro-preview` | Model name |
| `temperature` | FLOAT | 0.7 (0–1.5) | Generation temperature |

**Base URL is an advanced compatibility override** — it exists only to preserve
widget positional compatibility with older saved workflows. You do NOT need to
fill it in. For normal use, leave it empty and the node automatically uses
`https://generativelanguage.googleapis.com`. If you are using a proxy, configure
`base_url` in `config.json` instead.

| Output | Type | Description |
|--------|------|-------------|
| `ltx_model_prompt` | STRING | **Main output — wire this to LTX2.3.** Contains the complete JSON prompt engineering (pretty-printed) followed by two newlines and the `final_cinematic_prompt` pure text. |
| `complete_prompt_json` | STRING | **Preview/debug.** Full JSON prompt engineering (all four fields) serialized as pretty-printed JSON. |
| `final_cinematic_prompt` | STRING | **Preview/debug.** Extracted `final_cinematic_prompt` field. |
| `camera_and_reveal_map` | STRING | **Preview/debug.** Camera move definition and revealed-content map |
| `action_choreography_plan` | STRING | **Preview/debug.** Action choreography with timeblocks |
| `continuity_database` | STRING | **Preview/debug.** Visual Archetypes and Voice Profiles tracker |

### Node: Gemini Official Model List

**Category:** `LTX2.3/Prompt`

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `api_key` | STRING | *empty* | Gemini API key (env/config recommended) |
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
- **"HTTP request to Gemini API failed"** — verify network connectivity and
  that your API key is valid.  If using a proxy, check your `base_url` setting.
- **"JSON PARSE ERROR"** in `ltx_model_prompt` — the model returned
  non-JSON output.  The raw text is available in `ltx_model_prompt`,
  `complete_prompt_json`, and `final_cinematic_prompt`.  Check the model
  endpoint and `responseSchema` compatibility.
- **No ComfyUI imports available** — the plugin gracefully degrades for
  `py_compile` checks outside ComfyUI.
- **Model refresh button says \"API key required\"** — make sure you filled
  in the `api_key` widget (or set `GOOGLE_API_KEY` / `GEMINI_API_KEY` env
  var or `config.json`).  The route uses the same `resolve_api_key` chain
  as generation.
- **Model list is empty** — verify your API key is valid at
  [Google AI Studio](https://aistudio.google.com/apikey).  Also check that
  `base_url` is empty (unless you're intentionally using a proxy).

## License

MIT — see the original `ltx-2.3-cinematic-director` project.
