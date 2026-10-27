"""Phase B: nothing personal reaches Langfuse from run_review.py / harness/run_harness.py. Fake Langfuse, no network."""
import contextlib
import json
import shutil
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))

import run_review  # noqa: E402
from privacy import schleuse  # noqa: E402
from privacy.langfuse_guard import WITHHELD, LangfuseGuard  # noqa: E402

TEEL0 = ROOT / "ITSG Files" / "TEEL0-Test1-DBVO"
CASE = ROOT / "data" / "case_correct.json"
SECRETS = ("17241280Q497", "Mustermann", "Peter", "Testfrau", "Mia", "systemuntersuchung", "069/8700", "069-8700",
           "19801224", "99302811", "Meier", "a.meier@example.org")
pytestmark = pytest.mark.skipif(not (TEEL0.exists() and CASE.exists()), reason="TEEL0 file or test case missing")


class FakeLangfuse:
    """Records every keyword argument of every call it receives."""

    def __init__(self):
        self.received = []
        self.public_calls = []

    def _log(self, kind, kw):
        self.received.append(json.dumps({"call": kind, "kw": kw}, ensure_ascii=False, default=str))

    def start_as_current_span(self, **kw):
        self._log("span", kw)
        return contextlib.nullcontext()

    def update_current_trace(self, **kw):
        self._log("trace", kw)
        if kw.get("public"):
            self.public_calls.append(len(self.received))

    def get_trace_url(self, **kw):
        return "https://fake/trace"

    def get_current_trace_id(self):
        return "t1"

    def flush(self):
        pass

    @property
    def blob(self):
        return "\n".join(self.received)


def install_fake(monkeypatch, fake):
    module = types.ModuleType("langfuse")
    module.get_client = lambda: fake
    monkeypatch.setitem(sys.modules, "langfuse", module)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")


def personal_case(tmp_path):
    case = json.loads(CASE.read_text(encoding="utf-8-sig"))
    case["source"] = "Fall Frau Anna Meier, 17241280Q497, a.meier@example.org"  # lands in trace metadata
    path = tmp_path / "case.json"
    path.write_text(json.dumps(case), encoding="utf-8")
    return path


def run_main(monkeypatch, tmp_path, capsys, *extra, case=None):
    original = run_review.parse_teel0

    def leaky_parse(path):  # a future change that carries personal fields into the observed dict
        observed = original(path)
        text = Path(path).read_bytes().decode("latin-1")
        observed.update({"RAW": text, "VSNR": "17241280Q497", "FAMILIENNAME": "Mustermann", "VORNAME": "Peter",
                         "EMAIL": "systemuntersuchung@gmx.de"})
        return observed

    monkeypatch.setattr(run_review, "parse_teel0", leaky_parse)
    monkeypatch.setattr(run_review, "ROOT", tmp_path)  # reports go to tmp, no real .env is read
    monkeypatch.setattr(sys, "argv", ["run_review.py", "--case", str(case or CASE), "--teel0", str(TEEL0),
                                      "--checker-dir", str(ROOT / "checker"), *extra])
    run_review.main()
    return capsys.readouterr().out, json.loads(next((tmp_path / "reports").glob("RPT-*.json")).read_text(encoding="utf-8"))


def test_no_personal_value_reaches_langfuse_and_results_are_unchanged(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("PRIVACY_KEY", "x" * 20)
    plain_dir = tmp_path / "plain"
    plain_dir.mkdir()
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    _out, without = run_main(monkeypatch, plain_dir, capsys)

    fake = FakeLangfuse()
    install_fake(monkeypatch, fake)
    guarded_dir = tmp_path / "guarded"
    guarded_dir.mkdir()
    _out, with_lf = run_main(monkeypatch, guarded_dir, capsys, case=personal_case(tmp_path))

    assert len(fake.received) > 10 and "ABGABEGRUND" in fake.blob  # data did flow, only the personal part is gone
    for secret in SECRETS:
        assert secret not in fake.blob, secret
    assert with_lf["findings"] == without["findings"] and with_lf["report"]["counts"] == without["report"]["counts"]
    assert with_lf["report"]["overall_status"] == without["report"]["overall_status"]


def test_without_langfuse_keys_nothing_changes(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    out, report = run_main(monkeypatch, tmp_path, capsys)
    assert "tracing off" in out and report["trace_url"] is None
    assert all(f["status"] == "PASS" for f in report["findings"] if f["id"].startswith("C") and f["id"][1:].isdigit()
               and int(f["id"][1:]) <= 8)


def test_public_is_applied_only_at_the_end_and_only_if_clean(monkeypatch, tmp_path, capsys):
    fake = FakeLangfuse()
    install_fake(monkeypatch, fake)
    run_main(monkeypatch, tmp_path, capsys, "--public")
    assert len(fake.public_calls) == 1 and fake.public_calls[0] == len(fake.received)  # the last call
    assert '"public"' not in "".join(fake.received[:-1])


def test_public_is_refused_when_a_payload_had_to_be_withheld(monkeypatch, tmp_path, capsys):
    fake = FakeLangfuse()
    install_fake(monkeypatch, fake)
    real = schleuse.Schleuse.check_clean
    calls = {"n": 0}

    def dirty_once(self, text, allow_specimen=False):
        calls["n"] += 1
        return [schleuse.Hit("PERSON", 0, 1)] if calls["n"] == 3 else real(self, text, allow_specimen)

    monkeypatch.setattr(schleuse.Schleuse, "check_clean", dirty_once)
    out, _report = run_main(monkeypatch, tmp_path, capsys, "--public")
    assert fake.public_calls == [] and "--public refused" in out and WITHHELD in fake.blob


def test_guard_unit_behaviour():
    guard = LangfuseGuard("g" * 20)
    safe = guard.safe({"rule": "Abgabegrund = 41", "raw": "Frau Anna Meier", "actual": "Frau Anna Meier ruft an"})
    assert "raw" not in safe and "Meier" not in json.dumps(safe) and guard.all_clean
    assert guard.kwargs(name="x", user_id="Anna Meier", public=True, input="a@example.org") == {"name": "x", "input": "EMAIL_1"}
    assert guard.summary()["categories_removed"]["PERSON"] == 1


# ---------------------------------------------------------------- harness

class FakeItem:
    def __init__(self, item_id, owner):
        self.id, self.owner = item_id, owner

    @contextlib.contextmanager
    def run(self, run_name, run_metadata=None):
        self.owner._log("run", {"run_name": run_name, "run_metadata": run_metadata})
        owner = self.owner

        class Span:
            def update_trace(self, **kw):
                owner._log("update_trace", kw)

            def score_trace(self, **kw):
                owner._log("score", kw)

        yield Span()


class FakeHarnessLangfuse(FakeLangfuse):
    def __init__(self):
        super().__init__()
        self.items = []

    def get_dataset(self, name):
        return types.SimpleNamespace(items=list(self.items))

    def create_dataset(self, **kw):
        self._log("create_dataset", kw)

    def create_dataset_item(self, **kw):
        self._log("create_dataset_item", kw)
        self.items.append(FakeItem(kw["id"], self))


def test_harness_sends_nothing_personal_to_langfuse(monkeypatch, tmp_path):
    import run_harness

    fake = FakeHarnessLangfuse()
    install_fake(monkeypatch, fake)
    api = types.ModuleType("langfuse.api.core.api_error")
    api.ApiError = type("ApiError", (Exception,), {})
    for name in ("langfuse.api", "langfuse.api.core"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setitem(sys.modules, "langfuse.api.core.api_error", api)
    (tmp_path / "data").mkdir()
    shutil.copy(ROOT / "data" / "testcases.json", tmp_path / "data" / "testcases.json")
    cases = json.loads((tmp_path / "data" / "testcases.json").read_text(encoding="utf-8"))
    cases[0]["category"] = "Fall Frau Anna Meier, 17241280Q497, a.meier@example.org"  # personal data in a sent field
    cases[0]["scenario"]["note"] = "Herr Peter Mustermann, VSNR 17241280Q497"
    (tmp_path / "data" / "testcases.json").write_text(json.dumps(cases), encoding="utf-8")
    monkeypatch.setattr(run_harness, "ROOT", tmp_path)
    monkeypatch.setattr(run_harness, "load_env", lambda path: None)
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr(sys, "argv", ["run_harness.py", "--langfuse", "--limit", "3"])
    run_harness.main()
    assert len(fake.received) > 10
    for secret in SECRETS:
        assert secret not in fake.blob, secret
    summary = json.loads(next((tmp_path / "reports").glob("harness-*.json")).read_text(encoding="utf-8"))["summary"]
    assert summary["cases"] == 3
