"""Load known local settings without overriding host-provided environment values."""

import os
from pathlib import Path

LOCAL_SETTINGS = {
    "TREND_AUTO_REFRESH", "GROQ_API", "GROQ_API_KEY", "GROQ_MODEL", "PORT", "RUNPOD_API_KEY", "RUNPOD_ENDPOINT_ID",
    "RUNPOD_MODEL", "GEMINI_API_KEY", "GEMINI_MODEL", "GEMINI_FALLBACK_MODELS",
    "LLM_PROVIDER", "LLM_FALLBACK_PROVIDER",
}


def load_local_environment(path: Path | None = None):
    path = path or Path(__file__).resolve().parents[1] / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.removeprefix("export ").split("=", 1)
        name, value = name.strip(), value.strip()
        if name not in LOCAL_SETTINGS:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        os.environ.setdefault(name, value)
