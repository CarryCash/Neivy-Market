from __future__ import annotations
import hashlib, json, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUN = Path(__file__).resolve().parent
OUTPUT = RUN / "btc_usd_l2.parquet"
MANIFEST = RUN / "btc_usd_l2.parquet.manifest.json"
MAX_STREAM_SECONDS = 110
TOTAL_TIMEOUT_SECONDS = 125

if OUTPUT.exists() or MANIFEST.exists():
    raise SystemExit("Refusing to overwrite an existing output or manifest")
command = [sys.executable, str(ROOT / "scripts" / "capture_kraken_l2.py"),
           "--symbol", "BTC/USD", "--depth", "10", "--seconds", str(MAX_STREAM_SECONDS),
           "--batch-size", "2000", "--output", str(OUTPUT)]
started = datetime.now(timezone.utc)
t0 = time.monotonic()
status = "FAILED"
exit_code = 1
try:
    proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                          timeout=TOTAL_TIMEOUT_SECONDS, check=False)
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    exit_code = proc.returncode
    status = "PROCESS_EXITED"
except subprocess.TimeoutExpired as exc:
    def decode(value):
        if value is None: return ""
        return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value
    stdout, stderr = decode(exc.stdout), decode(exc.stderr)
    stderr += f"\nExternal timeout after {TOTAL_TIMEOUT_SECONDS} seconds; child terminated by subprocess timeout.\n"
    exit_code = 124
    status = "EXTERNAL_TIMEOUT"
finally:
    (RUN / "stdout.log").write_text(stdout, encoding="utf-8")
    (RUN / "stderr.log").write_text(stderr, encoding="utf-8")
    (RUN / "exit_code.txt").write_text(str(exit_code) + "\n", encoding="ascii")
    ended = datetime.now(timezone.utc)
    metadata = {
        "run_status": status,
        "started_at_utc": started.isoformat(),
        "ended_at_utc": ended.isoformat(),
        "total_wall_seconds": round(time.monotonic() - t0, 3),
        "max_stream_seconds": MAX_STREAM_SECONDS,
        "external_timeout_seconds": TOTAL_TIMEOUT_SECONDS,
        "command": command,
        "exit_code": exit_code,
    }
    if OUTPUT.exists():
        metadata["output_sha256"] = hashlib.sha256(OUTPUT.read_bytes()).hexdigest()
    partials = sorted(RUN.glob(".btc_usd_l2.parquet.*.partial"))
    metadata["partial_files"] = [
        {"path": item.name, "sha256": hashlib.sha256(item.read_bytes()).hexdigest()}
        for item in partials if item.is_file()
    ]
    (RUN / "driver_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    if status == "EXTERNAL_TIMEOUT":
        timeout_manifest = RUN / "external_timeout.incomplete.json"
        timeout_manifest.write_text(json.dumps({**metadata, "status": "INCOMPLETE"}, indent=2), encoding="utf-8")
print(json.dumps(metadata, indent=2))
raise SystemExit(exit_code)
