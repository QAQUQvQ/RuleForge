"""Immutable artifact references and fail-closed provenance checks."""
import hashlib
import json
import re
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path

SOURCE_URL = "https://media.dndbeyond.com/compendium-images/srd/5.1/SRD_CC_v5.1.pdf"
PDF_PATH = "data/sources/SRD_CC_v5.1.pdf"
_json_cache = ContextVar('evidence_json_cache', default=None)


@contextmanager
def evidence_snapshot():
    """Cache decoding only within one operation. File hashes are still checked on every read."""
    if _json_cache.get() is not None:
        yield
        return
    token = _json_cache.set({})
    try:
        yield
    finally:
        _json_cache.reset(token)


def verified_json(root, ref):
    path = checked_file(root, ref)
    cache = _json_cache.get()
    key = (str(path.resolve()), ref['sha256'])
    if cache is not None and key in cache:
        return cache[key]
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    if cache is not None:
        cache[key] = value
    return value

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
            if re.search(r"~(?![01])", token):
                raise EvidenceError("invalid JSON pointer escape")
            if isinstance(value, list) and not re.fullmatch(r"0|[1-9][0-9]*", token):
                raise EvidenceError("invalid JSON array index")
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
    raw = verified_json(root, manifest["raw"])
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


def verify_reference(root: Path, manifest: dict, reference):
    """Add identity/grid checks to the unchanged M1 artifact/quote verification."""
    from ruleforge.rules.sources import SourceReference
    from ruleforge.ingestion.tables import table_grid
    span = SourceReference.model_validate(reference).model_dump()
    if manifest.get("ruleset") != span["ruleset"] or manifest["id"] != span["run_id"]:
        raise EvidenceError("source ruleset/run mismatch")
    if manifest["document"]["sha256"] != span["document_id"]:
        raise EvidenceError("source document mismatch")
    verify_span(root, manifest, span)
    raw = verified_json(root, manifest["raw"])
    element = json_pointer(raw, span["element_pointer"])
    if not isinstance(element, dict) or element.get("element_id") != span["element_id"]:
        raise EvidenceError("element identity mismatch")
    if span["json_pointer"] != span["element_pointer"] + "/text":
        raise EvidenceError("quote must belong to referenced element")
    if span["fragment_type"] != element.get("type"):
        raise EvidenceError("fragment type mismatch")
    from ruleforge.ingestion.provenance import section_hierarchy
    if span["section_hierarchy"] != section_hierarchy(raw, span["element_id"]):
        raise EvidenceError("section hierarchy mismatch")
    if span["coordinates"] is not None and span["coordinates"] != element.get("coordinates"):
        raise EvidenceError("coordinates mismatch")
    if span["physical_page"] is not None:
        if span["page_pointer"] != span["element_pointer"] + "/page_number":
            raise EvidenceError("page pointer not bound to element")
        pages = [p for p in raw["data"]["pages"] if p["page_number"] == span["physical_page"]]
        if len(pages) != 1 or pages[0].get("status") != "Success" or span["element_id"] not in pages[0]["element_ids"]:
            raise EvidenceError("element/page membership mismatch")
    if span["printed_page"] is not None:
        footer = json_pointer(raw, span["printed_page_pointer"].rsplit("/", 1)[0])
        if (footer.get("type") != "Footer" or footer.get("page_number") != span["physical_page"]
            or str(json_pointer(raw, span["printed_page_pointer"])).strip() != span["printed_page"]
            or not span["printed_page"].isdigit()):
            raise EvidenceError("printed page mismatch")
    if span["table_location"]:
        loc = span["table_location"]
        cells = [c for row in table_grid(span["quote"]) for c in row
                 if c["row"] == loc["row"] and c["column"] == loc["column"]]
        if len(cells) != 1 or cells[0]["text"] != loc["text"]:
            raise EvidenceError("table location mismatch")
    return True
