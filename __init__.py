import os


# Contract: expose ComfyUI node mappings for plugin discovery.
# 典型调用场景:
# - ComfyUI loads this plugin and imports NODE_CLASS_MAPPINGS.
# - Core tests skip heavy runtime imports (torch/ComfyUI deps).
if os.getenv("SIMPLE_ITERATOR_SKIP_NODE_IMPORT", "0") == "1":
    NODE_CLASS_MAPPINGS = {}
    NODE_DISPLAY_NAME_MAPPINGS = {}
else:
    try:
        from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
    except ImportError:
        # Fallback for direct module import in local execution.
        from nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
