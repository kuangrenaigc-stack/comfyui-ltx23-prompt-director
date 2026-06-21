"""
Prompt templates faithfully migrated from the original
C:\\应用\\ltx-2.3-cinematic-director\\src\\services\\directorService.ts

These are the product core behavior. Do not rewrite creatively.
"""

SYSTEM_INSTRUCTION = r"""# Role: LTX-2.3 Master Cinematic Director (V57 Action & Camera Mastery Edition)

## Profile
- Description: You are an elite AI Cinematic Director building upon the highly successful V55 Fusion Architecture. You introduce a **Master Action Choreographer** (for precise, beautiful, fluid human kinematics) and a **Cinematography Master** (for official Camera LoRA reveal mapping).
- Tone: Masterful, Cinematic, Anatomically Precise (but fluid), Poetic.

## The 4 Pillars of Cinematic Mastery

### Pillar 1: The Cinematography Master (官方运镜映射法则 - NEW)
- **The Official Camera LoRA Rule:** When designing a camera movement (Dolly Right/Left/In/Out, Pan, Tilt), you MUST explicitly describe the **Destination and Revealed Content**. 
- **The Execution:** Give the AI a visual "map" of what exists as the frame shifts.
  - *Dolly Right Example:* "The camera dollies right, revealing a vintage grandfather clock and dust motes catching the light in the far-right corner of the room."
  - *Dolly In Example:* "The camera slowly dollies in, blurring the foreground leaves and revealing the intricate lace details of her collar."
- **Static Shots:** If static, focus entirely on volumetric lighting, textures, and depth of field.

### Pillar 2: The Action Choreographer (电影级动作与表情指导 - UPGRADED)
- **Fluid Joint & Limb Precision:** Do not rigidly "lock" the AI, but guide its joints precisely using the **Macro-Micro Fusion** from V55. Describe how the limbs move gracefully through space.
  - *Example (Blow a kiss):* "She blows a romantic kiss (Macro), gracefully curling her delicate fingers near her softly puckered lips before extending her palm smoothly outward (Micro)."
- **Cinematic Facial Acting:** Translate human emotions into cinematic micro-expressions (e.g., "eyes crinkling with longing," "a subtle, trembling breath," "a wistful, lifted gaze").

### Pillar 3: Time-Space Parity & The Audio-Sync Buffer (V55 时空调度与防结巴协议)
- **Precise Timeblocks:** Allocate exact seconds (e.g., `[0.0-2.0s]`) for actions. Do not rush.
- **The 0.5s Clearance Buffer:** If a hand interacts with the face, allocate a 0.5s block (e.g., `[2.0-2.5s]`) for the hand to lower completely before speech.
- **The Natural Pre-roll:** In the exact 0.5s right before dialogue, explicitly state `lips parting softly`. This is the ONLY transition allowed to prevent mouth-tearing glitches.

### Pillar 4: The Technical Firewalls (底层防呆协议)
- **Global Anti-Text Lock:** Start EVERY prompt exactly with: `[SYSTEM: Visuals contain NO on-screen text.]`
- **Official Audio Syntax:** `[Timecode] NAME (Emotion, Accent): "Dialogue."`

## The Workflow
1. **Design Camera (Agent B):** Choose the camera move and map out the "Revealed Environment" (parallax objects, background structures).
2. **Design Action (Agent A):** Choreograph the fluid, joint-precise physical actions and facial emotions using Macro-Micro Fusion.
3. **Draft Timeline:** Map actions to strict timeblocks (4s-10s), ensuring the 0.5s clearance/pre-roll buffer.
4. **Output:** Generate the `final_cinematic_prompt`."""


def build_single_image_user_text(scene_description: str, duration: int) -> str:
    """
    Build the user message text for single-image mode.
    Faithfully reproduces the mode === '1' path from the original directorService.ts.

    The original Chinese mode instruction is preserved as-is:
    "当前为【单图生成】模式。请以提供的首帧图为起点，顺滑地推演后续的动作和运镜。"
    """
    mode_instruction = (
        "当前为【单图生成】模式。"
        "请以提供的首帧图为起点，顺滑地推演后续的动作和运镜。"
    )
    return (
        f"请根据以上剧情和提供的参考图，生成符合剧情的电影级视频分镜提示词"
        f"（目标时长：{duration}秒）。\n"
        f"{mode_instruction}\n\n"
        f"剧情描述：\n"
        f"\"{scene_description}\""
    )


# --- Response field descriptions (used for textual schema directive) ----------

RESPONSE_FIELDS = {
    "camera_and_reveal_map": (
        "Define Camera move (e.g., Dolly Right, Zoom In). "
        "CRITICAL: Describe the visual 'map' of what is REVEALED as the camera "
        "moves (e.g., revealing a window on the right)."
    ),
    "action_choreography_plan": (
        "Design precise but fluid human kinematics using Macro-Micro Fusion "
        "(e.g., macro: 'blow kiss', micro: 'fingers curling near puckered lips'). "
        "Translate emotions to micro-expressions. Set exact timeblocks with "
        "0.5s pre-roll buffer."
    ),
    "continuity_database": (
        "Tracker for Visual Archetypes and Voice Profiles."
    ),
    "final_cinematic_prompt": (
        "THE EXECUTABLE PROMPT. Start with: "
        "'[SYSTEM: Visuals contain NO on-screen text.] Setting, Audio & Camera:'. "
        "Integrate the Camera Reveal map. Use fluid Macro-Micro action "
        "descriptions in strict time blocks. Ensure the 0.5s hand clearance "
        "and 'lips parting softly' buffer before speech. Use Official Audio "
        "Syntax. CRITICAL: NO robotic meta-jargon."
    ),
}


def build_schema_directive() -> str:
    """Force the four-field JSON contract the original responseSchema enforced."""
    lines = [
        "\n\n## Output Format (STRICT)",
        "Return a single valid JSON object (no markdown, no prose) with EXACTLY these keys:",
    ]
    for key, desc in RESPONSE_FIELDS.items():
        lines.append(f'- "{key}": {desc}')
    return "\n".join(lines)


# --- Gemini native responseSchema (sent in generationConfig) ------------------
# Equivalent to the original TypeScript getResponseSchema() function.
# Uses the Gemini REST API schema convention: type values are uppercase
# ("OBJECT", "STRING"), and camelCase field names.

RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "camera_and_reveal_map": {
            "type": "STRING",
            "description": (
                "Define Camera move (e.g., Dolly Right, Zoom In). "
                "CRITICAL: Describe the visual 'map' of what is REVEALED "
                "as the camera moves (e.g., revealing a window on the right)."
            ),
        },
        "action_choreography_plan": {
            "type": "STRING",
            "description": (
                "Design precise but fluid human kinematics using Macro-Micro "
                "Fusion (e.g., macro: 'blow kiss', micro: 'fingers curling "
                "near puckered lips'). Translate emotions to micro-expressions. "
                "Set exact timeblocks with 0.5s pre-roll buffer."
            ),
        },
        "continuity_database": {
            "type": "STRING",
            "description": (
                "Tracker for Visual Archetypes and Voice Profiles."
            ),
        },
        "final_cinematic_prompt": {
            "type": "STRING",
            "description": (
                "THE EXECUTABLE PROMPT. Start with: "
                "'[SYSTEM: Visuals contain NO on-screen text.] Setting, "
                "Audio & Camera:'. Integrate the Camera Reveal map. Use "
                "fluid Macro-Micro action descriptions in strict time "
                "blocks. Ensure the 0.5s hand clearance and 'lips parting "
                "softly' buffer before speech. Use Official Audio Syntax. "
                "CRITICAL: NO robotic meta-jargon."
            ),
        },
    },
    "required": [
        "camera_and_reveal_map",
        "action_choreography_plan",
        "continuity_database",
        "final_cinematic_prompt",
    ],
}
