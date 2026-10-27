"""Vendor side: ask ITSG for a run ID, then submit the hash of the finished report and keep the receipt.

  python seal/client.py start
  python seal/client.py submit <report.json> [--run RUN-...]

Environment: SEAL_URL (for example http://wsvm33), SEAL_VENDOR_TOKEN.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from seal_common import report_hash

CURRENT_RUN_FILE = Path(".seal_current_run")


class SealError(RuntimeError):
    pass


def _base_url(url: str) -> str:
    """SSRF guard: only plain http(s) URLs with a hostname, no userinfo."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username is not None:
        raise SealError(f"SEAL_URL must be a plain http(s) URL with a hostname: {url!r}")
    return url


def _call(method, path, body=None, url=None, token=None):
    url = _base_url((url or os.environ.get("SEAL_URL") or "").rstrip("/"))
    token = token or os.environ.get("SEAL_VENDOR_TOKEN") or ""
    if not url or not token:
        raise SealError("set SEAL_URL and SEAL_VENDOR_TOKEN")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url + path, data=data, method=method,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        try:
            msg = json.loads(exc.read()).get("error", "")
        except ValueError:
            msg = ""
        raise SealError(f"server said {exc.code}: {msg}") from None
    except (urllib.error.URLError, OSError) as exc:
        raise SealError(f"cannot reach the seal server: {exc}") from None


def start_run(url=None, token=None, state_file=CURRENT_RUN_FILE) -> dict:
    run = _call("POST", "/runs/start", url=url, token=token)
    Path(state_file).write_text(run["run_id"], encoding="utf-8")
    return run


def submit(report_path, run_id=None, url=None, token=None, state_file=CURRENT_RUN_FILE) -> dict:
    """Hash the report, send the hash (not the report), save <report>.receipt.json next to it."""
    report_path = Path(report_path)
    try:
        report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise SealError(f"cannot read report as JSON: {exc}") from None
    if not isinstance(report, dict):
        raise SealError("the report must be a JSON object")
    if run_id is None:
        try:
            run_id = Path(state_file).read_text(encoding="utf-8").strip()
        except OSError:
            raise SealError("no current run: run 'start' first or pass --run") from None
    receipt = _call("POST", f"/runs/{run_id}/submit", {"report_sha256": report_hash(report)}, url=url, token=token)
    out = report_path.with_name(report_path.name + ".receipt.json")
    out.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return {"receipt": receipt, "receipt_file": str(out)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("start")
    p = sub.add_parser("submit")
    p.add_argument("report")
    p.add_argument("--run")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "start":
            run = start_run()
            print(f"Run started: {run['run_id']} (issued {run['issued_at']})")
        else:
            res = submit(args.report, args.run)
            print(f"Receipt saved: {res['receipt_file']}  (run {res['receipt']['run_id']}, seq {res['receipt']['seq']})")
    except SealError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
