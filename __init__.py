"""
ComfyUI plugin: LTX2.3 Cinematic Prompt Director (Single Image).

Copies the single-image prompt generation capability from the original
local app at C:\\应用\\ltx-2.3-cinematic-director into a ComfyUI custom
node that calls the Yunwu Gemini native generateContent API.
"""

from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
