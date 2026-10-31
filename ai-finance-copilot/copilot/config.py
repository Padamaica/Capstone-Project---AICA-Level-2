"""Central configuration. All values can be overridden by environment variables or a .env file.

Data-localisation defaults: every path is local, and the LLM endpoint defaults to localhost.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (no external dependency)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


_load_dotenv(ROOT / ".env")


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


@dataclass(frozen=True)
class Settings:
    # ---- Storage (local only) ----
    data_dir: Path = Path(_env("COPILOT_DATA_DIR", str(ROOT / "data")))
    db_path: Path = Path(_env("COPILOT_DB_PATH", str(ROOT / "data" / "copilot.db")))
    output_dir: Path = Path(_env("COPILOT_OUTPUT_DIR", str(ROOT / "output")))
    log_dir: Path = Path(_env("COPILOT_LOG_DIR", str(ROOT / "logs")))
    coa_mapping_path: Path = Path(_env("COPILOT_COA_MAPPING", str(ROOT / "config" / "coa_mapping.csv")))

    # ---- Company ----
    company_name: str = _env("COPILOT_COMPANY_NAME", "Demo Manufacturing Pvt Ltd")
    currency: str = _env("COPILOT_CURRENCY", "INR")
    fy_start_month: int = int(_env("COPILOT_FY_START_MONTH", "4"))  # April (India)

    # ---- LLM (self-hosted) ----
    llm_provider: str = _env("LLM_PROVIDER", "ollama")  # ollama | openai_compatible (vLLM/TGI/LM Studio) | none
    llm_base_url: str = _env("LLM_BASE_URL", "http://localhost:11434")
    llm_model: str = _env("LLM_MODEL", "qwen2.5:7b-instruct")
    llm_api_key: str = _env("LLM_API_KEY", "")
    llm_timeout_s: int = int(_env("LLM_TIMEOUT_S", "120"))
    llm_temperature: float = float(_env("LLM_TEMPERATURE", "0.1"))

    # ---- Data localisation ----
    # Comma-separated hostnames that are approved in-country endpoints (e.g. a GPU VM in AWS Mumbai).
    allowed_llm_hosts: tuple[str, ...] = field(
        default_factory=lambda: tuple(h.strip() for h in _env("ALLOWED_LLM_HOSTS", "").split(",") if h.strip())
    )
    mask_pii_before_llm: bool = _env("MASK_PII_BEFORE_LLM", "true").lower() == "true"
    block_outbound_network: bool = _env("BLOCK_OUTBOUND_NETWORK", "true").lower() == "true"

    # ---- Analysis thresholds ----
    variance_threshold_pct: float = float(_env("VARIANCE_THRESHOLD_PCT", "10"))
    anomaly_z_threshold: float = float(_env("ANOMALY_Z_THRESHOLD", "3.0"))
    duplicate_window_days: int = int(_env("DUPLICATE_WINDOW_DAYS", "7"))

    # ---- API ----
    api_keys: tuple[str, ...] = field(
        default_factory=lambda: tuple(k.strip() for k in _env("COPILOT_API_KEYS", "change-me").split(",") if k.strip())
    )

    def ensure_dirs(self) -> None:
        for p in (self.data_dir, self.output_dir, self.log_dir, self.db_path.parent):
            p.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
