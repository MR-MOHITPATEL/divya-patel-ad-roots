"""
Root-match for scraped competitor ads.

For each ad:
  1. vision model reads the image + copy -> is it a real root? match to a catalogue
     root, or propose a candidate root
  2. judge whether the root can work for our brand (Divya's digital university + affiliate)

Output goes to storage (matches / roots / candidates). Matched ads are appended
to the root's competitor_examples; candidates are listed for the team to name.

Adapted for: Digital education / affiliate marketing / online course space.
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from . import store
from .llm import gemini_json
from .paths import ADS_DIR, slug

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass


def load_catalogue() -> dict:
    return store.catalogue_load()


def save_catalogue(cat: dict) -> None:
    store.catalogue_save(cat)


def _pop_candidate(cat: dict, name: str) -> dict | None:
    for i, c in enumerate(cat.get("candidates", [])):
        if c.get("candidate_name") == name:
            return cat["candidates"].pop(i)
    return None


def promote_candidate(name: str, *, root_id: str, why_it_works: str = "",
                      compliance_notes: str = "", fits_our_brand: str | None = None) -> None:
    """Turn a discovered candidate into a named root in the catalogue."""
    cat = load_catalogue()
    c = _pop_candidate(cat, name)
    if not c:
        raise ValueError(f"candidate not found: {name}")
    cat["roots"].append({
        "root_id": root_id,
        "name": name,
        "status": "named",
        "mechanism": c.get("mechanism", ""),
        "why_it_works": why_it_works,
        "visual_motif": c.get("visual_motif", ""),
        "line_of_attack_type": c.get("line_of_attack_type"),
        "line_of_attack": c.get("line_of_attack"),
        "reason_to_believe": c.get("reason_to_believe"),
        "attributes_verbal": c.get("attributes_verbal"),
        "attributes_visual": c.get("attributes_visual"),
        "story": c.get("story"),
        "root_kind": c.get("root_kind"),
        "fits_our_brand": fits_our_brand or c.get("fits_our_brand") or "conditional",
        "compliance_notes": compliance_notes,
        "competitor_examples": c.get("examples", []),
        "our_executions": [],
    })
    save_catalogue(cat)


def merge_candidate_into_root(name: str, root_id: str) -> None:
    """Fold a candidate's examples into an existing named root and drop the candidate."""
    cat = load_catalogue()
    root = next((r for r in cat["roots"] if r["root_id"] == root_id), None)
    if not root:
        raise ValueError(f"root not found: {root_id}")
    c = _pop_candidate(cat, name)
    if not c:
        raise ValueError(f"candidate not found: {name}")
    ex = root.setdefault("competitor_examples", [])
    for e in c.get("examples", []):
        if not any(x.get("ad_id") == e.get("ad_id") for x in ex):
            ex.append(e)
    save_catalogue(cat)


_SYSTEM = (
    "You are a senior performance-creative strategist specializing in Indian digital education, "
    "online course, affiliate marketing, and 'earn from home' advertising on Meta (Facebook/Instagram). "
    "You reverse-engineer the AD ROOT of a competitor ad: the reusable creative concept = "
    "persuasion mechanism + visual motif (NOT the specific course, price, or brand name). "
    "Two ads share a root if a strategist would rebuild them from the same recipe. "
    "You also storyboard the ad the way a strategist would in a creative review: what line "
    "of attack it opens with (problem / aspiration / transformation / social-proof / fear / opportunity), "
    "the reason to believe backing its claim, the attributes it pushes in words and in the "
    "visual, and the underlying story written as the brand speaking to the consumer. "
    "Return ONLY JSON."
)


def _prompt(ad: dict, roots: list[dict], candidates: list[dict] | None = None) -> str:
    known = "\n".join(
        f'  - id="{r["root_id"]}" | {r["name"]} | mechanism: {r["mechanism"]} | motif: {r["visual_motif"]}'
        for r in roots
    )
    cand_names = ", ".join(f'"{c["candidate_name"]}"' for c in (candidates or []))
    if cand_names:
        known += ("\n\nRECURRING CANDIDATE ROOTS — if this ad fits one, set is_candidate=true "
                  "and reuse its EXACT name; only invent a new name when it clearly fits none:\n"
                  + cand_names)
    copy = "\n".join(x for x in [ad.get("headline"), ad.get("body"), ad.get("link_description")] if x)
    return f"""KNOWN ROOTS (match to one of these ids if the recipe is the same):
{known}

COMPETITOR AD
  brand: {ad.get('page_name')}
  headline: {ad.get('headline')}
  body: {(ad.get('body') or '')[:500]}
  cta: {ad.get('cta_type')}
  (image is attached)

First decide if this is even a ROOT worth cataloguing:
  - designed_creative = a deliberately built ad with a persuasion structure (transformation
    story, comparison layout, income proof, certification showcase, mentor authority,
    problem-agitation, social proof display, urgency layout, testimonial card, etc.)
  - NOT a root = plain logo, generic stock photo with no concept, random product listing,
    event announcement with no creative structure, simple text post. Mark designed_creative=false.

Also storyboard it, the way a strategist breaks down a creative in review:
  - line_of_attack_type: what angle does it OPEN with — is it leading with a problem,
    an aspiration, a transformation, social-proof, fear, or an opportunity?
  - line_of_attack: one line naming the specific problem/aspiration/transformation/proof/
    fear/opportunity it leads with.
  - reason_to_believe: one line — why should the consumer believe this? The credential,
    the number, the testimonial, the certification doing the proving.
  - attributes_verbal: one line — what the ad pushes in WORDS (copy, headline, text on image).
  - attributes_visual: one line — what the ad pushes through the VISUAL (e.g. split-screen
    = transformation, phone screenshot = income proof, certificate = legitimacy).
  - story: 2-3 sentences, written as the BRAND SPEAKING to the consumer, e.g.
    "Hey, you're stuck in that 9-5 rut, right? What if I told you there's a way to learn
    digital skills, get certified, and start earning from home? Join 5000+ people who already did."
  - root_kind: is the reusable asset here the LAYOUT (has to look basically like this to
    work), the STORY (this pitch could be told through a completely different visual —
    single image, carousel, video), or BOTH equally load-bearing? -> "visual"|"narrative"|"both"

Return JSON:
{{
  "designed_creative": true|false,
  "creative_type": "transformation"|"comparison"|"income-proof"|"certification"|"testimonial"|"problem-agitation"|"social-proof"|"urgency"|"mentor-authority"|"lifestyle"|"infographic"|"carousel-story"|"ugc"|"minimal"|"text-post"|"product-shot",
  "root_strength": 0.0-1.0,   // how much this is a reusable, transplantable concept vs a one-off
  "noise_reason": "<if root_strength < 0.4, one line why this isn't a root>",
  "root_id": "<known id if it matches, else null>",
  "match_confidence": 0.0-1.0,
  "is_candidate": <true if designed_creative AND no known root fits>,
  "candidate_name": "<short name for the new root, or null>",
  "mechanism": "<one line: how this ad persuades>",
  "visual_motif": "<one line: the reusable visual recipe>",
  "line_of_attack_type": "problem"|"aspiration"|"transformation"|"social-proof"|"fear"|"opportunity",
  "line_of_attack": "<one line>",
  "reason_to_believe": "<one line>",
  "attributes_verbal": "<one line>",
  "attributes_visual": "<one line>",
  "story": "<2-3 sentences, brand speaking to the consumer>",
  "root_kind": "visual"|"narrative"|"both",
  "fits_our_brand": "yes"|"no"|"conditional",
  "fit_reason": "<why it does / doesn't work for Divya's digital university + affiliate program — a company selling affordable digital/social media courses with lifetime access, government certification, and a 70% affiliate commission model. Target: educated leads — students, housewives, business owners wanting extra income. Lead channel: Instagram DMs.>",
  "adaptation_hint": "<one line: what to change to run this root for our courses + affiliate program>"
}}"""


def analyze_ad(ad: dict, roots: list[dict], candidates: list[dict] | None = None) -> dict:
    imgs = (ad.get("local_image_paths") or [])[:1] or (ad.get("image_urls") or [])[:1]
    rec: dict = {
        "ad_id": ad["ad_id"],
        "page_name": ad.get("page_name"),
        "headline": ad.get("headline"),
        "body": ad.get("body"),
        "link_description": ad.get("link_description"),
        "snapshot_url": ad.get("snapshot_url"),
        "image": ad.get("image_url") or (imgs[0] if imgs else None),
        "image_phash": ad.get("image_phash"),
        "start_time": ad.get("start_time"),
        "is_active": ad.get("is_active"),
    }
    try:
        rec["root"] = gemini_json(_SYSTEM, _prompt(ad, roots, candidates), images=imgs)
    except Exception as e:  # noqa: BLE001
        rec["root"] = {"error": str(e)}
    r = rec["root"]
    rec["is_noise"] = bool(
        r.get("error")
        or not r.get("designed_creative", True)
        or (r.get("root_strength") or 0) < 0.4
    )
    return rec


def _attach_to_catalogue(cat: dict, matches: list[dict], competitor: str) -> None:
    by_id = {r["root_id"]: r for r in cat["roots"]}
    candidates = cat.setdefault("candidates", [])
    today = datetime.now(timezone.utc).date().isoformat()
    for m in matches:
        r = m.get("root") or {}
        if r.get("error") or m.get("is_noise"):
            continue
        rid = r.get("root_id")
        entry = {
            "brand": m.get("page_name") or competitor,
            "ad_id": m["ad_id"],
            "image_url": m.get("image"),
            "snapshot_url": m.get("snapshot_url"),
            "note": (m.get("headline") or "")[:120],
            "first_seen": today,
        }
        if rid and rid in by_id and (r.get("match_confidence") or 0) >= 0.6:
            ex = by_id[rid].setdefault("competitor_examples", [])
            if not any(e.get("ad_id") == m["ad_id"] for e in ex):
                ex.append(entry)
        elif r.get("is_candidate"):
            name = r.get("candidate_name") or "unnamed"
            cand = next((c for c in candidates if c.get("candidate_name") == name), None)
            if not cand:
                cand = {
                    "candidate_name": name,
                    "mechanism": r.get("mechanism"),
                    "visual_motif": r.get("visual_motif"),
                    "fits_our_brand": r.get("fits_our_brand"),
                    "line_of_attack_type": r.get("line_of_attack_type"),
                    "line_of_attack": r.get("line_of_attack"),
                    "reason_to_believe": r.get("reason_to_believe"),
                    "attributes_verbal": r.get("attributes_verbal"),
                    "attributes_visual": r.get("attributes_visual"),
                    "story": r.get("story"),
                    "root_kind": r.get("root_kind"),
                    "examples": [],
                }
                candidates.append(cand)
            if not any(e.get("ad_id") == m["ad_id"] for e in cand["examples"]):
                cand["examples"].append(entry)


def run(terms: list[str] | None = None, *, force: bool = False, workers: int = 4,
        limit: int | None = None) -> None:
    cat = load_catalogue()
    roots = cat["roots"]
    files = (
        [ADS_DIR / f"{slug(t)}.json" for t in terms]
        if terms else sorted(ADS_DIR.glob("*.json"))
    )
    prior_versions = {m["ad_id"]: (m.get("versions"), m.get("version_capacity"))
                      for m in store.matches_all() if m.get("versions")}
    for f in files:
        if not f.exists():
            print(f"skip (no scrape): {f.name}")
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        competitor = data.get("term", f.stem)
        ads = data.get("ads", [])

        seen_ids = set() if force else store.matches_existing_ids(competitor)
        todo = [a for a in ads if a["ad_id"] not in seen_ids]
        if limit:
            todo = todo[:limit]

        print(f">> {competitor}: {len(todo)} new / {len(ads)} ads")
        results = []
        if todo:
            cands_hint = sorted(
                (c for c in cat.get("candidates", []) if len(c.get("examples") or []) >= 3),
                key=lambda c: len(c.get("examples") or []), reverse=True,
            )[:25]
            with ThreadPoolExecutor(max_workers=workers) as ex:
                futs = {ex.submit(analyze_ad, a, roots, cands_hint): a for a in todo}
                for i, fut in enumerate(as_completed(futs), 1):
                    m = fut.result()
                    results.append(m)
                    r = m.get("root") or {}
                    if m.get("is_noise"):
                        tag = f"noise ({r.get('creative_type','?')})"
                    else:
                        tag = r.get("root_id") or (f"candidate:{r.get('candidate_name')}" if r.get("is_candidate") else "?")
                    print(f"   [{i}/{len(todo)}] {m['ad_id']}  strength={r.get('root_strength')}  {tag}  fits={r.get('fits_our_brand')}")

        for m in results:
            if m["ad_id"] in prior_versions:
                m["versions"], m["version_capacity"] = prior_versions[m["ad_id"]]

        if results:
            _attach_to_catalogue(cat, results, competitor)
            store.matches_save(competitor, results)

    save_catalogue(cat)
    n_cand = len(cat.get("candidates", []))
    print(f"catalogue ({store.mode()}): {len(cat['roots'])} named roots, {n_cand} candidates")
    print("Review candidates in the UI and Promote / Merge them by hand.")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("terms", nargs="*")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    run(a.terms or None, force=a.force, limit=a.limit)
