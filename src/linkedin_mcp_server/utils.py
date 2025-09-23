"""Utility functions for the LinkedIn MCP server."""

import yaml
from pathlib import Path


class PromptLoadError(Exception):
    """Exception raised when a prompt file cannot be loaded."""
    pass


def get_prompts_directory() -> Path:
    """Get the path to the prompts directory."""
    current_file = Path(__file__)
    return current_file.parent / "prompts"


def load_prompt_from_yaml(prompt_name: str) -> str:
    """
    Load a prompt from a YAML file in the prompts directory.

    Args:
        prompt_name: Name of the prompt file (without .yaml extension)

    Returns:
        str: The prompt content

    Raises:
        PromptLoadError: If the prompt file cannot be found or loaded
    """
    prompts_dir = get_prompts_directory()
    prompt_file = prompts_dir / f"{prompt_name}.yaml"

    if not prompt_file.exists():
        raise PromptLoadError(f"Prompt file not found: {prompt_file}")

    try:
        with open(prompt_file, 'r', encoding='utf-8') as f:
            prompt_data = yaml.safe_load(f)

        if not isinstance(prompt_data, dict):
            raise PromptLoadError(f"Invalid prompt file format: {prompt_file}. Expected a dictionary.")

        if 'prompt' not in prompt_data:
            raise PromptLoadError(f"Missing 'prompt' key in file: {prompt_file}")

        return prompt_data['prompt']

    except yaml.YAMLError as e:
        raise PromptLoadError(f"Failed to parse YAML file {prompt_file}: {e}")
    except IOError as e:
        raise PromptLoadError(f"Failed to read file {prompt_file}: {e}")


