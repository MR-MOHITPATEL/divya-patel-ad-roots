"""
Two-layer compliance checker for Divya Patel's Digital University ad copy.

Layer 1 — deterministic keyword / regex (fast, offline).
Layer 2 — one LLM call for judgment calls (income promise detection, MLM language,
          fake urgency, testimonial validity) and a compliant rewrite.

Used for:
  - our generated ad versions  -> hard gate
  - competitor ads             -> "how usable is this for us as-is"

Rules: compliance/ruleset.yaml
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

RULESET_PATH = Path(__file__).with_name("ruleset.yaml")

PASS, NEEDS_EDIT, FAIL = "PASS", "NEEDS_EDIT", "FAIL"
_ORDER = {PASS: 0, NEEDS_EDIT: 1, FAIL: 2}


@dataclass
class Finding:
    rule: str
    severity: str          # NEEDS_EDIT | FAIL
    message: str
    evidence: str = ""


@dataclass
class Verdict:
    status: str = PASS
    findings: list[Finding] = field(default_factory=list)
    rewrite: str | None = None
    headline_type: str | None = None
    notes: str = ""

    def add(self, f: Finding) -> None:
        self.findings.append(f)
        if _ORDER[f.severity] > _ORDER[self.status]:
            self.status = f.severity

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "headline_type": self.headline_type,
            "findings": [f.__dict__ for f in self.findings],
            "rewrite": self.rewrite,
            "notes": self.notes,
        }


@lru_cache(maxsize=1)
def load_ruleset() -> dict:
    return yaml.safe_load(RULESET_PATH.read_text(encoding="utf-8"))


# ── Layer 1 ──────────────────────────────────────────────────────────────────

def _layer1(text: str, v: Verdict) -> None:
    r = load_ruleset()
    low = text.lower()

    for phrase in r["verbs"]["banned"]:
        if re.search(rf"\b{re.escape(phrase)}\b", low):
            v.add(Finding("banned_phrase", FAIL,
                          f"Banned phrase: '{phrase}'", phrase))
    for phrase in r["verbs"].get("banned_hindi", []):
        if phrase in text:
            v.add(Finding("banned_phrase_hindi", FAIL,
                          f"Banned phrase (Hindi): '{phrase}'", phrase))

    for pat in r.get("timeline_patterns", []):
        m = re.search(pat, low)
        if m:
            v.add(Finding("timeline_promise", FAIL,
                          "Income-timeline promise — not allowed without substantiation",
                          m.group(0)))

    for phrase in r.get("employment_claims", {}).get("banned", []):
        if phrase.lower() in low or phrase in text:
            v.add(Finding("employment_guarantee", FAIL,
                          f"Employment/placement guarantee: '{phrase}'", phrase))

    for phrase in r.get("affiliate_disclosure", {}).get("banned", []):
        if phrase.lower() in low or phrase in text:
            v.add(Finding("mlm_language", FAIL,
                          f"MLM/pyramid language detected: '{phrase}' — use affiliate marketing language instead",
                          phrase))

    income_re = re.compile(r"(?:earn|कमा|income|salary|₹)\s*[\d,]+.*(?:month|महीन|week|हफ्त|day|दिन)", re.I)
    m = income_re.search(text)
    if m:
        if not any(d in low for d in ("results may vary", "individual results", "परिणाम भिन्न")):
            v.add(Finding("income_no_disclaimer", NEEDS_EDIT,
                          "Specific income figure without disclaimer — add 'Individual results may vary'",
                          m.group(0)))


# ── Layer 2 ──────────────────────────────────────────────────────────────────

_L2_SYSTEM = (
    "You are a compliance analyst for Indian digital education and affiliate marketing "
    "advertising (ASCI Code, Consumer Protection Act 2019, Meta Advertising Policies). "
    "You judge ad copy for Divya Patel's Digital University — an affordable course platform "
    "with a 70% affiliate commission model. Return ONLY JSON."
)


def _l2_prompt(text: str, r: dict) -> str:
    return f"""AD COPY (headline + body + visible text):
\"\"\"{text}\"\"\"

Answer as JSON:
{{
  "guarantees_specific_income": true|false,         // promises exact ₹ amount with certainty -> FAIL
  "income_figure_without_disclaimer": true|false,   // mentions income figure but no disclaimer -> NEEDS_EDIT
  "guarantees_job_placement": true|false,            // promises guaranteed job -> FAIL
  "uses_mlm_pyramid_language": true|false,           // passive income, chain, money-while-sleeping -> FAIL
  "fake_urgency": true|false,                        // obviously evergreen 'last 5 seats' type -> NEEDS_EDIT
  "unverified_testimonial": true|false,              // stock-photo student, too-good-to-be-true story -> NEEDS_EDIT
  "vague_certification_claim": true|false,           // 'government certified' without naming the body -> NEEDS_EDIT
  "headline_type": "A"|"B"|"C"|"D",                 // A=aspiration, B=problem-agitation, C=specific-benefit, D=banned
  "issues": ["short phrase", ...],
  "compliant_rewrite": "A fully compliant version of this copy: aspiration/problem-agitation headline (Type A/B) OR specific-benefit with disclaimers (Type C). Income mentions get disclaimer. Affiliate = earning opportunity, not guaranteed income. Certification names the body. Keep original language (Hindi/English/Hinglish)."
}}"""


def _layer2(text: str, v: Verdict, *, use_llm: bool) -> None:
    if not use_llm or not text.strip():
        return
    r = load_ruleset()
    try:
        from rootfinder.llm import gemini_json
        ans = gemini_json(_L2_SYSTEM, _l2_prompt(text, r))
    except Exception as e:  # noqa: BLE001
        v.notes += f" [layer2 skipped: {e}]"
        return

    v.headline_type = ans.get("headline_type")
    v.rewrite = ans.get("compliant_rewrite") or v.rewrite

    if ans.get("guarantees_specific_income"):
        v.add(Finding("income_guarantee", FAIL,
                      "Guarantees specific income — must use 'earning potential' with disclaimer",
                      "; ".join(ans.get("issues", []))))
    if ans.get("income_figure_without_disclaimer"):
        v.add(Finding("income_no_disclaimer", NEEDS_EDIT,
                      "Income figure mentioned without 'results may vary' disclaimer"))
    if ans.get("guarantees_job_placement"):
        v.add(Finding("job_guarantee", FAIL,
                      "Guarantees job/placement — use 'placement assistance' or 'career support' instead"))
    if ans.get("uses_mlm_pyramid_language"):
        v.add(Finding("mlm_language", FAIL,
                      "MLM/pyramid language — rewrite as affiliate marketing"))
    if ans.get("fake_urgency"):
        v.add(Finding("fake_urgency", NEEDS_EDIT,
                      "Urgency/scarcity claim may not be genuine"))
    if ans.get("unverified_testimonial"):
        v.add(Finding("unverified_testimonial", NEEDS_EDIT,
                      "Testimonial appears unverified — must use real, documented student stories"))
    if ans.get("vague_certification_claim"):
        v.add(Finding("vague_cert", NEEDS_EDIT,
                      "Certification claim too vague — name the specific certifying body"))
    if ans.get("headline_type") == "D":
        v.add(Finding("headline_banned", FAIL,
                      "Headline uses banned pattern (income guarantee / MLM language / get-rich-quick)"))


# ── Public ───────────────────────────────────────────────────────────────────

def validate_copy(text: str, *, is_ours: bool = True, use_llm: bool = True) -> Verdict:
    v = Verdict()
    text = (text or "").strip()
    if not text:
        v.notes = "no text to check"
        return v
    _layer1(text, v)
    _layer2(text, v, use_llm=use_llm)
    if not is_ours and v.status == FAIL:
        v.notes = ("Competitor copy — not usable verbatim; adapt for our brand "
                   "per the rewrite.") + v.notes
    return v


if __name__ == "__main__":
    import json
    import sys

    src = sys.stdin.read() if not sys.argv[1:] else " ".join(sys.argv[1:])
    print(json.dumps(validate_copy(src).to_dict(), indent=2, ensure_ascii=False))
