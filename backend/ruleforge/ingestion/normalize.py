"""Narrow reviewed compiler for one evidence-backed SRD rule."""
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from ruleforge.ingestion.evidence import EvidenceError, checked_file, digest_text, verify_span
from ruleforge.rules.models import SourceSpan

class TableRows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cell = [], None, None
    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag in ("td", "th"):
            self.cell = ""
    def handle_data(self, data):
        if self.cell is not None:
            self.cell += data
    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            if self.row is not None:
                self.row.append(self.cell.strip())
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None

def compact(text):
    return re.sub(r"[\s$*]", "", text).casefold()

def normalize(root: Path, manifest: dict) -> dict:
    if manifest["status"] != "succeeded":
        raise EvidenceError("parse has not succeeded")
    raw_path = checked_file(root, manifest["raw"])
    raw = json.loads(raw_path.read_text(encoding="utf-8-sig"))
    if raw.get("code") != 200:
        raise EvidenceError("parser returned non-success status")
    data = raw["data"]
    metadata = data["metadata"]
    pages = data["pages"]
    count = metadata["page_count"]
    info = json.loads((root / "data/setup/document-info.json").read_text(encoding="utf-8-sig"))
    if (type(count) is not int or count < 1 or count != info["page_count"]
        or data["success_count"] != count or len(pages) != count
        or {p["page_number"] for p in pages} != set(range(1, count+1))
        or any(p.get("status") != "Success" for p in pages)):
        raise EvidenceError("complete page coverage not confirmed")
    elements = data["elements"]
    matches = {"armor_table": [], "light_armor": [], "ability_modifier": []}
    for index, element in enumerate(elements):
        text = element.get("text", "")
        if element.get("type") == "Table":
            table = TableRows()
            table.feed(text)
            for row in table.rows:
                if len(row) >= 3 and row[0] == "Leather" and compact(row[2]) == "11+dexmodifier":
                    matches["armor_table"].append(index)
        if "If you wear light armor, you add your Dexterity modifier to the base number from your armor type to determine your Armor Class." in text:
            matches["light_armor"].append(index)
        if "subtract 10 from the ability score and then divide the total by 2 (round down)" in text:
            matches["ability_modifier"].append(index)
    if any(len(indices) != 1 for indices in matches.values()):
        raise EvidenceError("reviewed source patterns missing or ambiguous; manual review required")
    spans = []
    section_labels = {"armor_table": "Armor / Leather", "light_armor": "Light Armor", "ability_modifier": "Ability Scores and Modifiers"}
    for role, indices in matches.items():
        index = indices[0]
        element = elements[index]
        page = element["page_number"]
        if type(page) is not int or not 1 <= page <= count:
            raise EvidenceError("invalid source page")
        page_record = next(p for p in pages if p["page_number"] == page)
        if element["element_id"] not in page_record["element_ids"]:
            raise EvidenceError("element does not belong to declared page")
        footer = [(i,e) for i,e in enumerate(elements)
                  if e.get("type") == "Footer" and e.get("page_number") == page and e.get("text","").strip().isdigit()]
        printed = footer[0][1]["text"].strip() if len(footer) == 1 else None
        span = {"id": f"{manifest['id']}:{role}", "run_id": manifest["id"], "role": role,
                "json_pointer": f"/data/elements/{index}/text",
                "page_pointer": f"/data/elements/{index}/page_number",
                "physical_page": page, "printed_page": printed,
                "printed_page_pointer": f"/data/elements/{footer[0][0]}/text" if printed else None,
                "section": section_labels[role], "quote": element["text"],
                "quote_sha256": digest_text(element["text"]), "element_id": element["element_id"],
                "coordinates": element.get("coordinates")}
        span = SourceSpan.model_validate(span).model_dump()
        verify_span(root, manifest, span)
        spans.append(span)
    return {"schema_version": "ruleforge.normalized.v1", "run_id": manifest["id"],
            "coverage": "full", "page_count": count, "element_count": len(elements),
            "spans": spans}
