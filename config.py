"""
Configuration management - reads/writes .env file.
Allows dynamic UI updates without container restart.
"""

import os
import re
from pathlib import Path

# Default values (fallback if not in .env)
DEFAULTS = {
    "INSTAGRAM_USERNAME": "",
    "CRON_SCHEDULE": "0 * * * *",
    "MAX_WORKERS": "3",
    "LLM_BASE_URL": "http://host.docker.internal:1234/v1",
    "LLM_MODEL": "qwen2.5-vl-7b-instruct",
    "LLM_API_KEY": "",
    "LLM_CONCURRENCY": "1",
    "LLM_NATIVE_VIDEO": "false",
    "LLM_THINKING_BUDGET": "512",
    "LLM_MAX_TOKENS_VISUAL": "4096",
    "LLM_MAX_TOKENS_METADATA": "8192",
}

# Keys that can be edited via UI (excludes CRON_SCHEDULE)
UI_EDITABLE_KEYS = [
    "INSTAGRAM_USERNAME",
    "MAX_WORKERS",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "LLM_API_KEY",
    "LLM_CONCURRENCY",
    "LLM_NATIVE_VIDEO",
    "LLM_THINKING_BUDGET",
    "LLM_MAX_TOKENS_VISUAL",
    "LLM_MAX_TOKENS_METADATA",
]

# Keys that are NOT editable via UI
NON_EDITABLE_KEYS = [
    "CRON_SCHEDULE",
    "COOKIES_FILE",
    "ARCHIVE_DB",
    "RAW_DIR",
    "META_DIR",
    "DOWNLOAD_CMD",
    "ANALYZE_CMD",
]


def load_env(path: str = ".env") -> dict[str, str]:
    """
    Load .env file and return as dict.
    Falls back to DEFAULTS for missing keys.
    """
    result = dict(DEFAULTS)

    env_path = Path(path)
    if not env_path.exists():
        return result

    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    continue
                # Parse KEY=value
                match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=(.*)$', line)
                if match:
                    key, value = match.groups()
                    # Remove quotes if present
                    value = value.strip('"').strip("'")
                    result[key] = value
    except Exception:
        pass

    return result


def save_config(config: dict[str, str], path: str = ".env") -> None:
    """
    Save config dict to .env file, preserving structure and comments.
    """
    env_path = Path(path)

    # Read existing content to preserve comments
    existing_lines = []
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            existing_lines = f.readlines()

    # Build new content
    output_lines = []
    processed_keys = set()

    for line in existing_lines:
        stripped = line.strip()
        # Preserve comments and empty lines
        if not stripped or stripped.startswith("#"):
            output_lines.append(line)
            continue

        # Parse existing key
        match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=(.*)$', stripped)
        if match:
            key = match.group(1)
            if key in config:
                # Update with new value
                value = config[key]
                # Quote value if it contains spaces or special chars
                if " " in value or "=" in value or '"' in value:
                    value = f'"{value}"'
                output_lines.append(f"{key}={value}\n")
                processed_keys.add(key)
            else:
                # Keep existing
                output_lines.append(line)
        else:
            output_lines.append(line)

    # Add any new keys that weren't in the original file
    for key, value in config.items():
        if key not in processed_keys and key not in NON_EDITABLE_KEYS:
            output_lines.append(f"{key}={value}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(output_lines)


def get_config() -> dict[str, str]:
    """
    Get current configuration from .env file.
    """
    return load_env(".env")


def save_config_wrapper(config: dict[str, str]) -> None:
    """
    Wrapper for save_config that only saves UI-editable keys.
    """
    current = load_env(".env")
    # Merge: keep non-editable keys from current
    for key in NON_EDITABLE_KEYS:
        if key in current:
            config[key] = current[key]
    save_config(config, ".env")


def get_ui_config() -> dict[str, str]:
    """
    Get only UI-editable configuration keys.
    """
    full_config = load_env(".env")
    return {k: full_config.get(k, DEFAULTS.get(k, "")) for k in UI_EDITABLE_KEYS}


def update_ui_config(updates: dict[str, str]) -> None:
    """
    Update only UI-editable keys in .env file.
    """
    current = load_env(".env")
    current.update(updates)
    save_config_wrapper(current)
