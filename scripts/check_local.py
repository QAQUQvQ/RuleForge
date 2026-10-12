"""Real HTTP smoke check with a temporary server; no external API calls."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
import httpx

root = Path(__file__).resolve().parents[1]
directory = root / "data/local-checks" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
directory.mkdir(parents=True, exist_ok=False)
with socket.socket() as reservation:
    reservation.bind(("127.0.0.1", 0))
    port = reservation.getsockname()[1]
report = {"python": sys.version, "port": port, "checks": [], "status": "failed"}
with (directory/"server.stdout.log").open("wb") as out, (directory/"server.stderr.log").open("wb") as err:
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "ruleforge.api:create_app", "--factory",
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=root, stdout=out, stderr=err,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=20, trust_env=False) as client:
            deadline = time.monotonic()+30
            while True:
                if process.poll() is not None:
                    raise RuntimeError("Server exited during startup; inspect server.stderr.log")
                try:
                    response = client.get("/api/health")
                    break
                except httpx.ConnectError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Server did not become ready in 30 seconds")
                    time.sleep(0.2)
            response.raise_for_status()
            health = response.json()
            assert health["ac_ready"] is True, health
            report["checks"].append({"endpoint":"/api/health","status":response.status_code,"ac_ready":health["ac_ready"]})
            response = client.get("/docs")
            response.raise_for_status()
            report["checks"].append({"endpoint":"/docs","status":response.status_code})
            response = client.post("/api/evaluate/ac",json={"abilities":{"dexterity":14},"equipment":{"armor":"leather"}})
            response.raise_for_status()
            result = response.json()
            assert result["ac"] == 13, result
            assert {s["physical_page"] for s in result["sources"]} == {63,64,76}
            report["checks"].append({"endpoint":"/api/evaluate/ac","status":response.status_code,
                                     "ac":result["ac"],"source_pages":sorted(s["physical_page"] for s in result["sources"])})
            response = client.post("/api/evaluate/ac",json={"abilities":{"dexterity":14},"equipment":{"armor":"leather","shield":True}})
            assert response.status_code == 422
            report["checks"].append({"case":"unsupported shield","status":response.status_code})
            report["status"] = "passed"
    except BaseException as exc:
        report["error"] = repr(exc)
        raise
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        report["temporary_server_stopped"] = process.poll() is not None
        (directory/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(report,ensure_ascii=False,indent=2))
print("Report:",directory/"report.json")
