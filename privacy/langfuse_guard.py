"""Guard between our code and Langfuse (T10-007, phase B).

Everything that is sent to Langfuse (span input/output, trace input/output/metadata, dataset items, scores)
first goes through the policy "langfuse": minimize (only listed top-level keys), pseudonymize, check_clean.
If anything personal is still found, the payload is replaced by a placeholder and the guard remembers it:
`all_clean` turns False and a trace may then NOT be made public.

Usage (see run_review.py and harness/run_harness.py):
    guard = LangfuseGuard()
    lf.start_as_current_span(**guard.kwargs(name="x", input=..., output=...))
    some_call(input=guard.safe(payload))
"""
import json

try:
    from . import schleuse
except ImportError:  # loaded as a plain module
    import schleuse

WITHHELD = "[withheld: personal data suspected]"
# keyword arguments that are labels, not payload: they pass unchanged
_PASS = frozenset({"name", "level", "tags", "version", "session_id", "dataset_name", "run_name", "data_type", "value"})
# keyword arguments that must never be sent (they identify a person or control publication)
_DROP = frozenset({"user_id", "public"})


class LangfuseGuard:
    def __init__(self, key=None):
        self._schleuse = schleuse.Schleuse(key)
        self.checked = 0
        self.withheld = 0
        self.categories_removed = {}

    @property
    def all_clean(self) -> bool:
        """True while every payload passed check_clean (nothing had to be withheld)."""
        return self.withheld == 0

    def safe(self, payload):
        """Minimized, pseudonymized copy of payload; a placeholder if check_clean still finds something."""
        policy = schleuse.POLICY["langfuse"]
        minimized = schleuse._minimize(payload, policy)
        clean, summary = self._schleuse.pseudonymize(minimized)
        for category, n in summary["categories"].items():
            self.categories_removed[category] = self.categories_removed.get(category, 0) + n
        self.checked += 1
        blob = clean if isinstance(clean, str) else json.dumps(clean, ensure_ascii=False, default=str)
        if self._schleuse.check_clean(blob):
            self.withheld += 1
            return WITHHELD
        return clean

    def kwargs(self, **kw):
        """Make keyword arguments for a Langfuse call safe. Unknown payload arguments are sanitized, not trusted."""
        out = {}
        for key, value in kw.items():
            if key in _DROP:
                continue
            out[key] = value if key in _PASS else self.safe(value)
        return out

    def summary(self) -> dict:
        return {"policy_version": schleuse.POLICY_VERSION, "payloads_checked": self.checked,
                "payloads_withheld": self.withheld, "categories_removed": dict(self.categories_removed)}
