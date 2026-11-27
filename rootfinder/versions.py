"""
Version generator — turn one catalogued root into 10+ producible executions
for Divya Patel's Digital University + Affiliate Program, spread across
image / audio / video, each self-checked against the ASCI/Meta compliance
ruleset (compliance/validate.py).

Works on ANY root, including ones sourced from a competitor ad — by design
the output is always written as our own executable idea for our business,
never a reskin of the competitor's actual copy or branding.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone

from . import store
from .llm import gemini_json

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

_SYSTEM = (
    "You are a senior creative director for Divya Patel's Digital University — "
    "an affordable platform selling 21st-century digital & social media courses with "
    "lifetime access, government certification, and an automatic 70% affiliate commission "
    "per referral. Target audience: educated leads — students, housewives, business owners, "
    "job-holders wanting extra income. Lead channel: Instagram DMs after seeing Meta ads. "
    "Given one ad ROOT (a persuasion mechanism + story), you write a slate of DIFFERENT "
    "executable versions of that root for OUR brand — varying the angle, hook, and "
    "medium, never repeating one idea with a synonym swap. "
    "COMPLIANCE RULES THAT TRIP PEOPLE UP: "
    "(1) NEVER guarantee specific income — 'earn ₹50K/month guaranteed' is banned. Use "
    "'earning potential' or 'income opportunity' with disclaimer. "
    "(2) NEVER promise jobs/placement — 'guaranteed placement' is banned. Use 'career support' "
    "or 'job-ready skills'. "
    "(3) NEVER use MLM/pyramid language — 'passive income', 'money while you sleep', "
    "'chain system' triggers Meta's rejection + legal risk. This is AFFILIATE marketing. "
    "(4) Income testimonials MUST have disclaimer: 'Individual results may vary'. "
    "(5) Certification claims must name the SPECIFIC certifying body, not just 'government certified'. "
    "(6) Urgency/scarcity ('last 5 seats') must be genuinely true, not evergreen fake scarcity. "
    "(7) NEVER use fake testimonials or stock-photo 'students'. "
    "(8) The tone should be conversational, relatable, and empowering — NOT pushy or scammy. "
    "Think of a friend who found something good and is genuinely sharing it. "
    "LANGUAGE: Use Hindi or Hinglish for maximum relatability with Indian audience. English "
    "is fine for professional/corporate-targeting versions. "
    "Return ONLY JSON."
)


def _prompt(root: dict, counts: dict[str, int]) -> str:
    total = sum(counts.values())
    return f"""ROOT
  name: {root.get('name')}
  mechanism: {root.get('mechanism')}
  visual motif: {root.get('visual_motif')}
  story (brand speaking): {root.get('story') or '(not captured — infer from mechanism/motif)'}
  line of attack: {root.get('line_of_attack_type') or '?'} — {root.get('line_of_attack') or ''}
  reason to believe: {root.get('reason_to_believe') or ''}
  attributes — verbal: {root.get('attributes_verbal') or ''}; visual: {root.get('attributes_visual') or ''}

OUR BUSINESS DETAILS:
  - Affordable digital/social media courses
  - Lifetime access + government certification
  - Automatic affiliate partner on purchase (70% commission per referral)
  - No targets, no pressure, no chain system
  - Target: students, housewives, business owners, job-holders
  - Lead channel: Instagram DMs

Write {total} DIFFERENT executable versions of this root for our brand:
  - {counts['image']} IMAGE versions (static ad creatives for Meta)
  - {counts['audio']} AUDIO versions (reel voiceover / ad audio)
  - {counts['video']} VIDEO versions (short-form reels, scene by scene)

Vary the angle/hook across versions. Each should target a slightly different
sub-audience or emotional trigger. Use Hindi/Hinglish for most versions, English
for 1-2 professional-targeting ones.

Separately, ESTIMATE capacity: for each medium, how many genuinely DIFFERENT versions
could this root support before you'd be repeating yourself?

Return JSON: {{
  "version_capacity": {{
    "image": {{"count": <int>, "why": "<one line>"}},
    "audio": {{"count": <int>, "why": "<one line>"}},
    "video": {{"count": <int>, "why": "<one line>"}}
  }},
  "versions": [
  {{
    "medium": "image"|"audio"|"video",
    "version_name": "<short label, e.g. 'Housewife freedom angle'>",
    "target_sub_audience": "<who this version speaks to — e.g. 'housewives wanting independence'>",
    "language": "hindi"|"hinglish"|"english",
    "headline": "<headline for this version>",
    "hook": "<one line: the specific angle/twist>",
    "image_prompt": "<only if medium=image: a full image-generation prompt>",
    "key_visual_elements": "<only if medium=image: one line>",
    "script": "<only if medium=audio: the full VO script>",
    "tone": "<only if medium=audio: one line>",
    "scenes": [{{"visual": "...", "vo_line": "...", "on_screen_text": "..."}}],
    "duration_sec": 15,
    "cta": "<call to action — DM us / Link in bio / Comment 'YES'>",
    "disclaimer": "<required disclaimer if income/earning is mentioned>"
  }}
]}}
("scenes" and "duration_sec" only for medium=video; "duration_sec" also for medium=audio.)"""


def _version_text(v: dict) -> str:
    parts = [v.get("headline") or "", v.get("hook") or "", v.get("script") or ""]
    for sc in v.get("scenes") or []:
        parts += [sc.get("vo_line") or "", sc.get("on_screen_text") or ""]
    return "\n".join(p for p in parts if p)


def _build_versions(root_like: dict, counts: dict[str, int]) -> tuple[list[dict], dict]:
    from compliance.validate import validate_copy

    out = gemini_json(_SYSTEM, _prompt(root_like, counts), max_tokens=6000)
    versions = out.get("versions") or []
    if not versions and out.get("error"):
        raise RuntimeError(out["error"])

    now = datetime.now(timezone.utc).isoformat()
    for v in versions:
        verdict = validate_copy(_version_text(v), is_ours=True, use_llm=True)
        v["compliance"] = verdict.to_dict()
        v["generated_at"] = now
    return versions, (out.get("version_capacity") or {})


def generate(root_id: str, *, n_image: int = 1, n_audio: int = 1, n_video: int = 1) -> list[dict]:
    cat = store.catalogue_load()
    root = next((r for r in cat["roots"] if r["root_id"] == root_id), None)
    if not root:
        raise ValueError(f"root not found: {root_id}")

    counts = {"image": n_image, "audio": n_audio, "video": n_video}
    versions, capacity = _build_versions(root, counts)
    root["versions"] = versions
    root["version_capacity"] = capacity
    store.catalogue_save(cat)
    return versions


def _pseudo_root(m: dict) -> dict:
    r = m.get("root") or {}
    name = m.get("headline") or r.get("root_id") or r.get("candidate_name") or m.get("ad_id")
    return {"name": name, **{k: r.get(k) for k in (
        "mechanism", "visual_motif", "story", "line_of_attack_type", "line_of_attack",
        "reason_to_believe", "attributes_verbal", "attributes_visual")}}


def generate_for_ad(m: dict, *, n_image: int = 1, n_audio: int = 1, n_video: int = 1) -> tuple[list[dict], dict]:
    counts = {"image": n_image, "audio": n_audio, "video": n_video}
    return _build_versions(_pseudo_root(m), counts)


def run_for_all_ads(*, force: bool = False, workers: int = 4, limit: int | None = None) -> None:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    matches = store.matches_all()
    todo = [m for m in matches if not m.get("is_noise") and (force or not m.get("versions"))]
    if limit:
        todo = todo[:limit]
    print(f"{len(todo)} ads to version (of {len(matches)} total, {len(matches) - len(todo)} skipped)")

    def _do(m: dict):
        try:
            m["versions"], m["version_capacity"] = generate_for_ad(m)
            return m, None
        except Exception as e:  # noqa: BLE001
            return m, str(e)

    FLUSH_EVERY = 20
    pending: dict[str, list[dict]] = {}
    ok = fail = since_flush = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_do, m): m for m in todo}
        for i, fut in enumerate(as_completed(futs), 1):
            m, err = fut.result()
            if err:
                fail += 1
                print(f"  [{i}/{len(todo)}] {m['ad_id']} FAILED: {err}")
                continue
            ok += 1
            since_flush += 1
            pending.setdefault(m["_competitor_file"], []).append(m)
            statuses = [v["compliance"]["status"] for v in m["versions"]]
            print(f"  [{i}/{len(todo)}] {m['ad_id']} ({m.get('_competitor_file')}) -> {statuses}")
            if since_flush >= FLUSH_EVERY:
                for competitor, ms in pending.items():
                    store.matches_save(competitor, ms)
                print(f"    -- flushed {since_flush} --")
                pending = {}
                since_flush = 0

    for competitor, ms in pending.items():
        store.matches_save(competitor, ms)
    print(f"done: {ok} ok, {fail} failed")


if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser()
    ap.add_argument("root_id", nargs="?")
    ap.add_argument("--image", type=int, default=1)
    ap.add_argument("--audio", type=int, default=1)
    ap.add_argument("--video", type=int, default=1)
    ap.add_argument("--all-ads", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    if a.all_ads:
        run_for_all_ads(force=a.force, workers=a.workers, limit=a.limit)
    elif a.root_id:
        vs = generate(a.root_id, n_image=a.image, n_audio=a.audio, n_video=a.video)
        print(json.dumps(vs, indent=2, ensure_ascii=False))
        print(f"\n{len(vs)} versions generated for root '{a.root_id}'")
    else:
        ap.error("give a root_id or --all-ads")
