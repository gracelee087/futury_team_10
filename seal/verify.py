"""ITSG side: check a report against its receipt, or list all runs.

  python seal/verify.py <report.json> <receipt.json>
  python seal/verify.py --runs

Environment: SEAL_URL, SEAL_ADMIN_TOKEN.  Exit code 0 only for GENUINE.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


class VerifyError(RuntimeError):
    pass


def _base_url(url: str) -> str:
    """SSRF guard: only plain http(s) URLs with a hostname, no userinfo."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username is not None:
        raise VerifyError(f"SEAL_URL must be a plain http(s) URL with a hostname: {url!r}")
    return url


def _call(method, path, body=None, url=None, token=None):
    url = _base_url((url or os.environ.get("SEAL_URL") or "").rstrip("/"))
    token = token or os.environ.get("SEAL_ADMIN_TOKEN") or ""
    if not url or not token:
        raise VerifyError("set SEAL_URL and SEAL_ADMIN_TOKEN")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url + path, data=data, method=method,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read())
        except ValueError:
            payload = {}
        if exc.code == 409 and payload.get("result"):  # LEDGER_TAMPERED
            return payload
        raise VerifyError(f"server said {exc.code}: {payload.get('error', '')}") from None
    except (urllib.error.URLError, OSError) as exc:
        raise VerifyError(f"cannot reach the seal server: {exc}") from None


def verify_files(report_path, receipt_path, url=None, token=None) -> dict:
    try:
        report = json.loads(Path(report_path).read_text(encoding="utf-8-sig"))
        receipt = json.loads(Path(receipt_path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise VerifyError(f"cannot read input as JSON: {exc}") from None
    if not isinstance(report, dict) or not isinstance(receipt, dict):
        return {"result": "TAMPERED", "reason": "report and receipt must both be JSON objects"}
    return _call("POST", "/verify", {"report": report, "receipt": receipt}, url, token)


def list_runs(url=None, token=None) -> dict:
    return _call("GET", "/runs", url=url, token=token)


def format_runs(data: dict) -> str:
    if "runs" not in data:
        return f"{data.get('result', 'ERROR')}: {data.get('reason', '')}"
    lines = [f"{data['total']} run(s), {data['never_submitted']} never submitted"]
    for r in data["runs"]:
        state = f"submitted {r['submitted_at']}" if r["submitted"] else "NEVER SUBMITTED"
        lines.append(f"  {r['run_id']}  issued {r['issued_at']}  {state}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", help="<report.json> <receipt.json>")
    ap.add_argument("--runs", action="store_true", help="list all runs, including never-submitted ones")
    args = ap.parse_args(argv)
    try:
        if args.runs:
            print(format_runs(list_runs()))
            return 0
        if len(args.files) != 2:
            ap.error("give a report file and a receipt file, or use --runs")
        res = verify_files(*args.files)
    except VerifyError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"{res['result']}: {res['reason']}")
    return 0 if res["result"] == "GENUINE" else 1


if __name__ == "__main__":
    sys.exit(main())
