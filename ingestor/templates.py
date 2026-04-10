"""
Template loader for Verdify prompts and text templates.

Uses Jinja2 for structured templates (.j2) and plain text for markdown prompts.
All templates live in /srv/verdify/templates/ (or the TEMPLATES_DIR env var).
"""

import os
from functools import lru_cache
from pathlib import Path

TEMPLATES_DIR = Path(os.environ.get("TEMPLATES_DIR", Path(__file__).parent.parent / "templates"))


@lru_cache(maxsize=32)
def _load_raw(name: str) -> str:
    """Load a template file as raw text. Cached."""
    path = TEMPLATES_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Template not found: {path}")
    return path.read_text()


def render(name: str, **kwargs) -> str:
    """Render a Jinja2 template (.j2) with the given variables."""
    from jinja2 import BaseLoader, Environment

    env = Environment(loader=BaseLoader(), keep_trailing_newline=True)
    template = env.from_string(_load_raw(name))
    return template.render(**kwargs)


def load(name: str) -> str:
    """Load a plain text template (markdown prompts, etc.)."""
    return _load_raw(name)
