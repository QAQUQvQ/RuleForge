"""Download only the pinned official SRD; never parse or call paid services."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

URL = "https://media.dndbeyond.com/compendium-images/srd/5.1/SRD_CC_v5.1.pdf"
SHA256 = "2504d2a0abb0a4d491a939be4f17910a2dde0312570ab8d208080225ccf0a1f0"
target = Path("data/sources/SRD_CC_v5.1.pdf")
if target.exists():
    if hashlib.sha256(target.read_bytes()).hexdigest() != SHA256:
        raise SystemExit("Existing PDF differs from pinned source; will not overwrite.")
    print("Verified existing official SRD. No download required.")
else:
    with urlopen(URL, timeout=60) as response:
        blob = response.read(20 * 1024 * 1024 + 1)
    if not blob.startswith(b"%PDF-") or hashlib.sha256(blob).hexdigest() != SHA256:
        raise SystemExit("Official download differs from pinned PDF; manual review required.")
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(blob)
    target.with_suffix(".source.json").write_text(json.dumps({
        "source_url":URL,"sha256":SHA256,"downloaded_at":datetime.now(timezone.utc).isoformat(),
        "license":"CC-BY-4.0","ruleset":"srd-5.1"},indent=2),encoding="utf-8")
    print("Saved official SRD with verified hash.")
