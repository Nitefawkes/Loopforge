from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseRenderer(ABC):
    """
    Abstract base class for all rendering engines in LoopForge.
    Each renderer must implement this interface.
    """

    @abstractmethod
    def render(self, prompt: str, workflow: str, output_path: str, **kwargs) -> str:
        """
        Render a video based on the prompt and workflow.
        Args:
            prompt: The text prompt or prompt file.
            workflow: Path to the workflow file (JSON, etc.).
            output_path: Where to save the rendered video.
            **kwargs: Additional renderer-specific options.
        Returns:
            Path to the rendered video file.
        """
        pass

    @abstractmethod
    def validate_environment(self) -> bool:
        """
        Check if the renderer's dependencies and environment are ready.
        Returns:
            True if ready, False otherwise.
        """
        pass

    @abstractmethod
    def get_supported_options(self) -> Dict[str, Any]:
        """
        Return a dictionary of supported options/parameters for this renderer.
        Returns:
            Dict of option names to descriptions/defaults.
        """
        pass 