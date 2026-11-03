"""Fetch reviewed official pages through Keenable without changing catalog facts.

Run from the repository root. Raw source text stays in ignored local runtime files.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from equalstart.catalog import ROOT, load_catalog
from equalstart.providers import Keenable

client = Keenable()
out = ROOT / "runtime" / "source-review"
out.mkdir(parents=True, exist_ok=True)
results = []
for record in load_catalog():
    if "--missing-only" in sys.argv and (out / f"{record.id}.json").exists():
        continue
    url = str(record.official_url)
    try:
        page = client.fetch(url, {urlparse(url).hostname})
        content = page.get("content", "")
        (out / f"{record.id}.json").write_text(json.dumps({"url": url, "fetched_at": datetime.now(timezone.utc).isoformat(), "content": content}, ensure_ascii=False), encoding="utf-8")
        results.append({"id": record.id, "status": "fetched" if content else "empty", "characters": len(content)})
    except Exception as error:
        results.append({"id": record.id, "status": type(error).__name__})
    print(json.dumps(results[-1]), flush=True)
receipt = out / "receipt.json"
if "--missing-only" in sys.argv and receipt.exists():
    previous = {x["id"]: x for x in json.loads(receipt.read_text(encoding="utf-8"))}
    previous.update({x["id"]: x for x in results})
    results = list(previous.values())
receipt.write_text(json.dumps(results, indent=2), encoding="utf-8")
