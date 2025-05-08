# LoopForge rendering module

"""Rendering module for LoopForge."""

# from src.rendering.local_renderer import *  # Removed to fix circular import
from .base import BaseRenderer
from .comfyui import ComfyUIRenderer
from .invokeai import InvokeAIRenderer

RENDERERS = {
    "comfyui": ComfyUIRenderer,
    "invokeai": InvokeAIRenderer,
}

def get_available_renderers():
    """
    Return a dict of available renderer names to their classes.
    """
    return RENDERERS.copy()
