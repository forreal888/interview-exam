"""Configuration loader for enterprise-qa skill."""

import os
import re
from pathlib import Path

# Skill root directory (where this script lives: skills/enterprise-qa/)
SKILL_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = SKILL_DIR.parent.parent.parent / "enterprise-qa-data"


def _resolve_path(raw_path: str) -> str:
    """Resolve a path relative to the data directory."""
    p = Path(raw_path)
    if p.is_absolute():
        return str(p)
    resolved = (DATA_DIR / p).resolve()
    return str(resolved)


def load_config() -> dict:
    """Load config from environment variables, falling back to config.yaml defaults."""
    config = {
        "db_path": None,
        "kb_path": None,
        "timezone": "Asia/Shanghai",
    }

    # Environment variables take priority
    if os.environ.get("ENTERPRISE_QA_DB_PATH"):
        config["db_path"] = _resolve_path(os.environ["ENTERPRISE_QA_DB_PATH"])
    if os.environ.get("ENTERPRISE_QA_KB_PATH"):
        config["kb_path"] = _resolve_path(os.environ["ENTERPRISE_QA_KB_PATH"])

    # Fallback: try to read config.yaml
    yaml_path = SKILL_DIR / "config.yaml"
    if yaml_path.exists():
        try:
            content = yaml_path.read_text(encoding="utf-8")
            for key, pattern in [("db_path", r"path:\s*(\S+)"), ("kb_path", r"root_path:\s*(\S+)")]:
                if not config[key]:
                    match = re.search(pattern, content)
                    if match:
                        config[key] = _resolve_path(match.group(1))
        except Exception:
            pass

    # Hard defaults
    if not config["db_path"]:
        config["db_path"] = _resolve_path("./enterprise.db")
    if not config["kb_path"]:
        config["kb_path"] = _resolve_path("./knowledge")

    return config
