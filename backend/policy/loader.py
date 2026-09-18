from pathlib import Path

import yaml

from backend.policy.models import SOPConfig


def load_sop_config(path: str | Path) -> SOPConfig:
    """
    Load and validate the SOP configuration from YAML.
    """

    sop_path = Path(path)

    if not sop_path.exists():
        raise FileNotFoundError(f"SOP file not found: {sop_path}")

    with sop_path.open("r", encoding="utf-8") as file:
        raw_config = yaml.safe_load(file)

    if not raw_config:
        raise ValueError("SOP file is empty.")

    return SOPConfig.model_validate(raw_config)