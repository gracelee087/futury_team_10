"""Local demo of the ITSG receipt office. Uses throwaway secrets and a temp folder; nothing is kept.

  python seal/demo.py [report.json]

Without an argument a small built-in example report is used.
"""
import copy
import json
import secrets
import sys
import tempfile
import threading
from pathlib import Path

import client
import server
import verify

EXAMPLE_REPORT = {
    "report": {"id": "RPT-DEMO", "overall_status": "MISMATCH"},
    "findings": [
        {"id": "F1", "rule": "Abgabegrund = 41", "expected": "41", "actual": "41", "status": "PASS"},
        {"id": "C2", "rule": "Exactly one cancellation (88) is sent", "expected": 1, "actual": 0, "status": "MISMATCH"},
    ],
}


def flip_one_failure(report):
    """Return a copy where the first MISMATCH/FAIL/BLOCKED/NOT EVALUATED status becomes PASS, and what changed."""
    forged = copy.deepcopy(report)

    def walk(node):
        items = node.items() if isinstance(node, dict) else enumerate(node) if isinstance(node, list) else ()
        for key, value in list(items):
            if value in ("MISMATCH", "FAIL", "BLOCKED", "NOT EVALUATED"):
                node[key] = "PASS"
                return value
            found = walk(value)
            if found:
                return found
        return None

    old = walk(forged)
    if old is None:  # a report with no failure at all: just change one character of the first text value
        forged["demo_note"] = "edited"
        old = "(nothing)"
    return forged, old


def say(text=""):
    print(text, flush=True)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    report = json.loads(Path(argv[0]).read_text(encoding="utf-8-sig")) if argv else EXAMPLE_REPORT
    vendor, admin = secrets.token_hex(16), secrets.token_hex(16)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        env = {"SEAL_SECRET": secrets.token_hex(32), "SEAL_VENDOR_TOKEN": vendor, "SEAL_ADMIN_TOKEN": admin,
               "SEAL_LEDGER": str(tmp / "ledger.jsonl")}
        httpd = server.make_server(env, "127.0.0.1", 0)
        url = f"http://127.0.0.1:{httpd.server_address[1]}"
        threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        state = tmp / "current_run"
        say(f"Step 0: ITSG starts its receipt office on {url} (throwaway secrets, temp folder).")

        say("\nStep 1: the vendor asks ITSG for a run ID before running the review.")
        run = client.start_run(url, vendor, state_file=state)
        say(f"        ITSG issued {run['run_id']}")

        say("\nStep 2: the vendor finishes the review and submits the fingerprint (hash) of the report.")
        rpt = tmp / "report.json"
        rpt.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        res = client.submit(rpt, url=url, token=vendor, state_file=state)
        say(f"        ITSG stamped it: sequence number {res['receipt']['seq']}, receipt saved next to the report.")

        say("\nStep 3: ITSG checks the report and receipt it received.")
        result = verify.verify_files(rpt, res["receipt_file"], url, admin)
        say(f"        Result: {result['result']} - {result['reason']}")
        assert result["result"] == "GENUINE"

        forged, old = flip_one_failure(report)
        bad = tmp / "report_edited.json"
        bad.write_text(json.dumps(forged, indent=2, ensure_ascii=False), encoding="utf-8")
        say(f"\nStep 4: a dishonest vendor changes one result ({old} -> PASS) and sends the edited report.")
        result = verify.verify_files(bad, res["receipt_file"], url, admin)
        say(f"        Result: {result['result']} - {result['reason']}")
        assert result["result"] == "TAMPERED"

        say("\nStep 5: the vendor starts a second run, sees a bad result and never submits it.")
        second = client.start_run(url, vendor, state_file=state)
        say(f"        ITSG issued {second['run_id']} and hears nothing more about it.")

        say("\nStep 6: ITSG lists ALL runs. The hidden run cannot be hidden.")
        say(verify.format_runs(verify.list_runs(url, admin)))

        httpd.shutdown()
        httpd.server_close()
    say("\nDemo finished. Temp folder and throwaway secrets are gone.")


if __name__ == "__main__":
    main()
