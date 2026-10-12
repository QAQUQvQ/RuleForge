"""Official CLI adapter. No direct API client, paid mode, or automatic retries."""
import json
import subprocess
from pathlib import Path
from uuid import uuid4
from ruleforge.ingestion.evidence import artifact, now, structured_error, SOURCE_URL, PDF_PATH, checked_file

def command(executable: Path, root: Path, output: Path) -> list[str]:
    if not executable.is_file():
        raise FileNotFoundError("Install official xparse-cli and provide its executable")
    return [str(executable.resolve()), "parse", str((root / PDF_PATH).resolve()),
            "--api", "free", "--view", "json", "--output", str(output.resolve())]

def run_parse(root: Path, executable: Path) -> dict:
    # An interrupted or failed attempt must be reviewed, never automatically resubmitted.
    for path in (root / "data/runs").glob("*/manifest.json"):
        old = json.loads(path.read_text(encoding="utf-8"))
        if old.get("status") in ("running", "failed"):
            raise ValueError("Prior attempt needs explicit recovery review: " + str(path))
        if old.get("status") == "succeeded":
            checked_file(root, old["document"])
            for ref in old["artifacts"]:
                checked_file(root, ref)
            return old
    run_id = "srd51-" + uuid4().hex
    directory = root / "data/runs" / run_id
    raw_dir = directory / "raw"
    raw_dir.mkdir(parents=True)
    args = command(executable, root, raw_dir)
    record = {"id": run_id, "status": "running", "api_mode": "free",
              "started_at": now(), "command": args, "source_url": SOURCE_URL,
              "document": artifact(root, root / PDF_PATH)}
    (directory / "manifest.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    try:
        with (directory / "stdout.log").open("wb") as out, (directory / "stderr.log").open("wb") as err:
            result = subprocess.run(args, stdout=out, stderr=err, shell=False, check=False)
        return finalize(root, run_id, result.returncode, "see data/setup/version.stdout.log")
    except OSError as exc:
        record.update(status="failed", error={"type": type(exc).__name__, "message": str(exc)}, finished_at=now())
        (directory / "manifest.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        raise

def finalize(root: Path, run_id: str, exit_code: int, parser_version: str) -> dict:
    directory = root / "data/runs" / run_id
    stderr = (directory / "stderr.log").read_text(encoding="utf-8-sig")
    error = structured_error(stderr)
    raw_files = list((directory / "raw").glob("*.json"))
    status = "succeeded" if exit_code == 0 and not error and len(raw_files) == 1 else "failed"
    response = None
    if status == "succeeded":
        try:
            response = json.loads(raw_files[0].read_text(encoding="utf-8-sig"))
            data = response.get("data", {})
            count = data.get("metadata", {}).get("page_count")
            pages = data.get("pages", [])
            if (response.get("code") != 200 or type(count) is not int or count < 1
                or data.get("success_count") != count or len(pages) != count
                or {p.get("page_number") for p in pages} != set(range(1, count+1))
                or any(p.get("status") != "Success" for p in pages)
                or not data.get("elements")):
                raise ValueError("API response does not demonstrate complete successful parsing")
        except (ValueError, TypeError, AttributeError) as exc:
            status = "failed"
            error = {"type": "RESPONSE_VALIDATION_FAILED", "message": str(exc)}
    start = directory / "started_at.txt"
    previous = directory / "manifest.json"
    started = (json.loads(previous.read_text(encoding="utf-8")).get("started_at")
               if previous.exists() else start.read_text(encoding="utf-8") if start.exists() else None)
    record = {"schema_version": "ruleforge.parse_run.v1", "id": run_id,
              "parser": "intsig-textin/xparse-skills / xparse-cli", "parser_version": parser_version,
              "api_mode": "free", "status": status, "exit_code": exit_code, "error": error,
              "source_url": SOURCE_URL, "ruleset": "srd-5.1", "license": "CC-BY-4.0",
              "document": artifact(root, root / PDF_PATH),
              "coverage": "unverified", "started_at": started, "finished_at": now(),
              "command": ["xparse-cli", "parse", PDF_PATH, "--api", "free", "--view", "json", "--output", f"data/runs/{run_id}/raw"],
              "artifacts": [artifact(root, p) for p in sorted(directory.rglob("*"))
                            if p.is_file() and p.name != "manifest.json"]}
    if status == "succeeded":
        record["raw"] = artifact(root, raw_files[0])
        record["request_id"] = response.get("x_request_id")
        record["coverage"] = "full"
        record["page_count"] = response["data"]["metadata"]["page_count"]
    elif error is None:
        record["error"] = {"type": "CLI_OR_OUTPUT_FAILURE", "message": "Inspect raw stdout/stderr; no success inferred"}
    (directory / "manifest.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record
