import json
from pathlib import Path

from equalstart.schema import Opportunity

ROOT = Path(__file__).resolve().parent.parent


def load_catalog(path: Path | None = None) -> list[Opportunity]:
    records = json.loads((path or ROOT / "data" / "opportunities.json").read_text(encoding="utf-8"))
    catalog = [Opportunity.model_validate(r) for r in records]
    if len({r.id for r in catalog}) != len(catalog):
        raise ValueError("Duplicate opportunity IDs")
    return catalog
