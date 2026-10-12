"""Immutable artifact references and fail-closed provenance checks."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

SOURCE_URL = "https://media.dndbeyond.com/compendium-images/srd/5.1/SRD_CC_v5.1.pdf"
PDF_PATH = "data/sources/SRD_CC_v5.1.pdf"

class EvidenceError(ValueError):
    pass

def now():
    return datetime.now(timezone.utc).isoformat()

def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()

def digest_text(value: str) -> str:
    return digest_bytes(value.encode("utf-8"))

def contained(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise EvidenceError("artifact path escapes workspace")
    return candidate

def artifact(root: Path, path: Path) -> dict:
    relative = path.resolve().relative_to(root.resolve()).as_posix()
    raw = path.read_bytes()
    return {"path": relative, "sha256": digest_bytes(raw), "bytes": len(raw)}

def checked_file(root: Path, ref: dict) -> Path:
    file = contained(root, ref["path"])
    if not file.is_file() or digest_bytes(file.read_bytes()) != ref["sha256"]:
        raise EvidenceError("artifact missing or SHA-256 mismatch: " + ref["path"])
    return file

def json_pointer(value, pointer: str):
    if pointer == "":
        return value
    if not pointer.startswith("/"):
        raise EvidenceError("invalid JSON pointer")
    try:
        for token in pointer[1:].split("/"):
            key = token.replace("~1", "/").replace("~0", "~")
            value = value[int(key)] if isinstance(value, list) else value[key]
        return value
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        raise EvidenceError("source JSON pointer missing") from exc

def structured_error(stderr: str):
    # CLI may mix progress lines and pretty-printed JSON. Retain the last envelope.
    decoder, last = json.JSONDecoder(), None
    for index, char in enumerate(stderr):
        if char != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(stderr[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("schema_version") == "xparse_error.v1":
            last = obj
    return last

def verify_span(root: Path, manifest: dict, span: dict):
    if manifest["status"] != "succeeded" or manifest["api_mode"] != "free":
        raise EvidenceError("no successful free parse evidence")
    checked_file(root, manifest["document"])
    for ref in manifest["artifacts"]:
        checked_file(root, ref)
    raw_path = checked_file(root, manifest["raw"])
    raw = json.loads(raw_path.read_text(encoding="utf-8-sig"))
    quote = json_pointer(raw, span["json_pointer"])
    if not isinstance(quote, str) or quote != span["quote"] or digest_text(quote) != span["quote_sha256"]:
        raise EvidenceError("quote integrity failure")
    if span.get("page_pointer"):
        page = json_pointer(raw, span["page_pointer"])
        if type(page) is not int or page != span["physical_page"] or page < 1:
            raise EvidenceError("page mapping mismatch")
    elif span["physical_page"] is not None:
        raise EvidenceError("page without evidence")
    return True
