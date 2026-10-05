"""One-off: scrape a sample of ads (image / video / carousel, any format) for a
list of used-car / certified-pre-owned brands, for a shareable round-up -- NOT
part of the Ad Root Finder pipeline (no Gemini analysis, no Firestore write).

Keeps whichever media each ad actually has, unlike the main scraper which
only keeps image ads. Writes one JSON file the artifact-builder reads.
"""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rootfinder import fetch as F
from rootfinder.paths import ROOT

BRANDS = [
    "CARS24", "Spinny", "CarDekho", "CarWale", "Droom", "OLX",
    "Mahindra First Choice Wheels", "Maruti Suzuki True Value", "Toyota U Trust",
    "Hyundai H-Promise", "Honda Auto Terrace", "Tata OK", "Volkswagen Das WeltAuto",
    "Renault Selection", "Nissan Intelligent Choice", "MG Reassure", "Ford Assured",
    "Big Boy Toyz", "BMW Premium Selection", "Audi Approved Plus", "Mercedes-Benz Certified",
]

MAX_ADS = 14
OUT = ROOT / "data" / "car_brands_ads.json"


def _normalize_any_media(unit: dict) -> dict | None:
    """Like fetch._normalize but keeps the video preview image separately from
    the playable video URL, so a video ad still has a real thumbnail.

    _collect() falls back to fetch._extract_ssr() (already-normalized dicts,
    keyed "ad_id"/"snapshot_url", no raw "snapshot") when the GraphQL response
    listener hasn't caught anything yet -- handle that shape too."""
    if "ad_archive_id" not in unit and unit.get("ad_id"):
        return {
            "ad_id": unit["ad_id"], "page_name": unit.get("page_name") or "",
            "is_active": bool(unit.get("is_active", True)),
            "headline": unit.get("headline"), "body": unit.get("body"),
            "cta_type": unit.get("cta_type"), "display_format": unit.get("display_format"),
            "snapshot_url": unit.get("snapshot_url"),
            "image_urls": unit.get("image_urls") or [],
            "video_url": (unit.get("video_urls") or [None])[0], "video_thumb": None,
            "cards": [{"title": c.get("title"), "image_url": c.get("image_url")}
                     for c in (unit.get("cards") or [])],
            "is_carousel": len(unit.get("cards") or []) > 1,
            "start_date": None,
        }
    ad_id = str(unit.get("ad_archive_id") or "")
    if not ad_id:
        return None
    snap = unit.get("snapshot") or {}
    body_raw = snap.get("body")
    body = body_raw.get("text") if isinstance(body_raw, dict) else str(body_raw or "")
    images = [u for img in (snap.get("images") or [])
              if (u := img.get("original_image_url") or img.get("resized_image_url"))]
    video_url = video_thumb = None
    for vid in snap.get("videos") or []:
        video_url = video_url or vid.get("video_hd_url") or vid.get("video_sd_url")
        video_thumb = video_thumb or vid.get("video_preview_image_url")
    cards = []
    for card in snap.get("cards") or []:
        ci = card.get("original_image_url") or card.get("resized_image_url")
        if ci and ci not in images:
            images.append(ci)
        cards.append({"title": card.get("title"), "image_url": ci})
    page_name = (unit.get("page_name") or snap.get("page_name") or "").strip()
    return {
        "ad_id": ad_id, "page_name": page_name,
        "is_active": bool(unit.get("is_active", True)),
        "headline": snap.get("title") or None, "body": (body or "").strip() or None,
        "cta_type": snap.get("cta_type") or snap.get("cta_text") or None,
        "display_format": snap.get("display_format") or None,
        "snapshot_url": f"https://www.facebook.com/ads/library/?id={ad_id}",
        "image_urls": images, "video_url": video_url, "video_thumb": video_thumb,
        "cards": cards, "is_carousel": len(cards) > 1,
        "start_date": unit.get("start_date"),
    }


def scrape_brand(context, term: str, max_ads: int, started_budget: float) -> list[dict]:
    page = context.new_page()
    page.add_init_script(F._STEALTH)

    # Harvest the raw ad units ourselves (not fetch._normalize) so we can keep
    # the video URL and its preview thumbnail separately for a real gallery.
    raw_units: dict[str, dict] = {}

    def on_response(resp):
        try:
            if F.GRAPHQL_MARK not in resp.url or resp.request.method != "POST":
                return
            body = resp.text()
            if "ad_archive_id" not in body:
                return
            for obj in F._iter_json(body):
                _harvest(obj, raw_units)
        except Exception:  # noqa: BLE001
            pass

    page.on("response", on_response)
    started = time.monotonic()
    o = F.FetchOptions(country="IN", active_status="active", max_ads=max_ads,
                       brand_filter=True, hard_cap_seconds=started_budget)
    try:
        F._collect(page, raw_units, F.build_search_url(term, o), o, started, target=max_ads * 3)
    finally:
        page.close()

    out = []
    for u in raw_units.values():
        n = _normalize_any_media(u)
        if n and (n["image_urls"] or n["video_url"]):
            out.append(n)
    out = [a for a in out if a.get("is_active")]
    out = [a for a in out if "{{" not in (a.get("headline") or "") + (a.get("body") or "")]
    out = [a for a in out if F._brand_match(term, a.get("page_name", ""))]
    random.shuffle(out)
    return out[:max_ads]


def _harvest(obj, sink: dict, depth: int = 0) -> None:
    if depth > 18 or not isinstance(obj, (dict, list)):
        return
    if isinstance(obj, list):
        for it in obj:
            _harvest(it, sink, depth + 1)
        return
    if "ad_archive_id" in obj and isinstance(obj.get("snapshot"), dict):
        sink.setdefault(str(obj["ad_archive_id"]), obj)
        return
    for wrapper in ("collated_results", "collationUnits", "results", "edges", "node"):
        if wrapper in obj:
            v = obj[wrapper]
            for unit in (v if isinstance(v, list) else [v]):
                _harvest(unit, sink, depth + 1)
            return
    for v in obj.values():
        if isinstance(v, (dict, list)):
            _harvest(v, sink, depth + 1)


def main() -> None:
    from playwright.sync_api import sync_playwright

    results: dict[str, list[dict]] = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox",
                                     "--disable-blink-features=AutomationControlled"])
        context = F._make_context(browser, F.FetchOptions())
        for i, brand in enumerate(BRANDS, 1):
            if i > 1:
                pause = random.uniform(8, 15)
                print(f"  (pausing {pause:0.1f}s)", flush=True)
                time.sleep(pause)
                context.close()
                context = F._make_context(browser, F.FetchOptions())
            print(f">> [{i}/{len(BRANDS)}] {brand}", flush=True)
            try:
                ads = scrape_brand(context, brand, MAX_ADS, 90)
            except Exception as e:  # noqa: BLE001
                print(f"  ERROR: {e}", flush=True)
                ads = []
            print(f"  {len(ads)} ads "
                  f"(images: {sum(1 for a in ads if a['image_urls'] and not a['video_url'])}, "
                  f"video: {sum(1 for a in ads if a['video_url'])}, "
                  f"carousel: {sum(1 for a in ads if a['is_carousel'])})", flush=True)
            results[brand] = ads
            OUT.parent.mkdir(parents=True, exist_ok=True)
            OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        context.close()
        browser.close()
    print("done", flush=True)


if __name__ == "__main__":
    main()
