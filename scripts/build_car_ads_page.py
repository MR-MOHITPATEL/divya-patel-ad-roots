"""Build the standalone HTML artifact for the used-car-brand ad scan.
Fully static, server-rendered markup -- no data blob, no client-side JS."""
from __future__ import annotations

import html
import json
from datetime import date
from pathlib import Path

DATA_PATH = Path("data/car_brands_ads_thumbs.json")
OUT_PATH = Path(
    r"C:\Users\mahar\AppData\Local\Temp\claude\c--Users-mahar-Documents-Projects-ZenJeevani-themes-roots-claude"
    r"\59ed5f0f-061f-4e34-b24a-39c15934b375\scratchpad\car_ad_scan_v3.html"
)

data = json.loads(DATA_PATH.read_text(encoding="utf-8"))

total_ads = sum(len(v) for v in data.values())
brands_with_ads = sum(1 for v in data.values() if v)
brands_zero = sum(1 for v in data.values() if not v)
n_image = sum(1 for v in data.values() for a in v if a["image_urls"] and not a["video_url"])
n_video = sum(1 for v in data.values() for a in v if a["video_url"])
n_carousel = sum(1 for v in data.values() for a in v if a["is_carousel"])


def esc(s: str | None) -> str:
    return html.escape(s or "", quote=True)


def slug(s: str) -> str:
    return "".join(c.lower() if c.isalnum() else "-" for c in s).strip("-")


def card_html(ad: dict) -> str:
    fmt = "carousel" if ad["is_carousel"] else ("video" if ad["video_url"] else "image")
    if ad.get("thumb"):
        thumb = f'<img src="{ad["thumb"]}" alt="" loading="lazy">'
    else:
        note = "Video &mdash; no preview frame captured" if fmt == "video" else "No preview available"
        thumb = f'<div class="thumb-ph">{note}</div>'
    headline = (f'<div class="headline">{esc(ad["headline"])}</div>' if ad.get("headline")
               else '<div class="headline" style="color:var(--muted)">No headline text</div>')
    return f'''<div class="card">
      <div class="thumb-wrap"><span class="badge {fmt}">{fmt}</span>{thumb}</div>
      <div class="card-body">
        {headline}
        <div class="page-name">{esc(ad["page_name"])}</div>
        <a href="{esc(ad["snapshot_url"])}" target="_blank" rel="noopener">View in Ad Library &rarr;</a>
      </div>
    </div>'''


jump_links = []
brand_sections = []
for brand, ads in data.items():
    bid = slug(brand)
    cls = ' class="zero"' if not ads else ""
    jump_links.append(f'<a href="#{bid}"{cls}>{esc(brand)} ({len(ads)})</a>')

    if ads:
        cards = "\n".join(card_html(a) for a in ads)
        body = f'<div class="grid">\n{cards}\n</div>'
    else:
        body = '<p class="empty">No active Meta ads found under this name at scan time.</p>'

    brand_sections.append(f'''<section class="brand" id="{bid}">
  <div class="brand-head"><h2>{esc(brand)}</h2>
    <span class="count-pill">{len(ads)} ad{"" if len(ads) == 1 else "s"}</span></div>
  {body}
</section>''')

HTML = f"""<title>Used Car Ad Scan</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Big+Shoulders+Display:wght@600;700;800&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@500&display=swap" rel="stylesheet">
<style>
/* Layout: a spec-sheet / showroom-floor grid -- one labeled bay per brand, cards
   inside laid out like windshield price stickers (format badge in the corner). */
:root {{
  --bg:#EEF0F2; --panel:#FFFFFF; --panel-2:#F5F6F8; --ink:#14181F; --muted:#5B6472;
  --line:#D8DCE2; --accent:#2A5DB0; --accent-soft:#E3EBF8;
  --video:#B5651D; --video-soft:#F6E9DC; --carousel:#3E7D5A; --carousel-soft:#E5F1EA;
  --zero:#9AA2AD;
  --font-display:'Big Shoulders Display',system-ui,sans-serif;
  --font-body:'IBM Plex Sans',system-ui,-apple-system,sans-serif;
  --font-mono:'IBM Plex Mono',ui-monospace,monospace;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --bg:#14171C; --panel:#1D2128; --panel-2:#20242B; --ink:#ECEEF1; --muted:#8B93A0;
    --line:#2B3038; --accent:#6C9BEA; --accent-soft:#233350;
    --video:#E3A15C; --video-soft:#3A2C1C; --carousel:#7FC69C; --carousel-soft:#1E3327;
    --zero:#5E6672; color-scheme:dark;
  }}
}}
:root[data-theme="dark"] {{
  --bg:#14171C; --panel:#1D2128; --panel-2:#20242B; --ink:#ECEEF1; --muted:#8B93A0;
  --line:#2B3038; --accent:#6C9BEA; --accent-soft:#233350;
  --video:#E3A15C; --video-soft:#3A2C1C; --carousel:#7FC69C; --carousel-soft:#1E3327;
  --zero:#5E6672; color-scheme:dark;
}}
* {{ box-sizing:border-box; }}
body {{ background:var(--bg); color:var(--ink); font-family:var(--font-body);
  margin:0; padding-inline:20px; }}
a {{ color:var(--accent); }}
.wrap {{ max-width:1180px; margin:0 auto; }}

header {{ padding-block:36px 24px; border-bottom:1px solid var(--line); }}
h1 {{ font-family:var(--font-display); font-weight:800; font-size:clamp(2.2rem,5vw,3.4rem);
  letter-spacing:.01em; margin:0 0 6px; text-transform:uppercase; text-wrap:balance; }}
.sub {{ color:var(--muted); font-size:.95rem; max-width:62ch; line-height:1.5; }}

.stats {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr)); gap:10px;
  margin-top:22px; }}
.stat {{ background:var(--panel); border:1px solid var(--line); border-radius:10px;
  padding:12px 14px; }}
.stat b {{ display:block; font-family:var(--font-mono); font-variant-numeric:tabular-nums;
  font-size:1.5rem; line-height:1.1; }}
.stat span {{ color:var(--muted); font-size:.72rem; text-transform:uppercase; letter-spacing:.06em; }}
.stat.image b {{ color:var(--accent); }}
.stat.video b {{ color:var(--video); }}
.stat.carousel b {{ color:var(--carousel); }}

nav.jump {{ display:flex; flex-wrap:wrap; gap:6px; padding-block:16px; border-bottom:1px solid var(--line); }}
nav.jump a {{ font-size:.78rem; padding:.3rem .65rem; border:1px solid var(--line); border-radius:999px;
  text-decoration:none; color:var(--muted); background:var(--panel); }}
nav.jump a.zero {{ color:var(--zero); border-style:dashed; }}
nav.jump a:hover {{ border-color:var(--accent); color:var(--accent); }}

section.brand {{ padding-block:26px; border-bottom:1px solid var(--line); scroll-margin-top:14px; }}
.brand-head {{ display:flex; align-items:baseline; gap:.6rem; flex-wrap:wrap; margin-bottom:14px; }}
.brand-head h2 {{ font-family:var(--font-display); font-weight:700; font-size:1.5rem;
  margin:0; text-transform:uppercase; letter-spacing:.01em; }}
.count-pill {{ font-family:var(--font-mono); font-size:.72rem; color:var(--muted);
  background:var(--panel-2); border:1px solid var(--line); border-radius:999px; padding:.15rem .6rem; }}
.empty {{ color:var(--muted); font-size:.88rem; font-style:italic; }}

.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:14px; }}
.card {{ background:var(--panel); border:1px solid var(--line); border-radius:12px; overflow:hidden;
  display:flex; flex-direction:column; min-width:0; }}
.thumb-wrap {{ position:relative; aspect-ratio:1/1; background:var(--panel-2); }}
.thumb-wrap img {{ width:100%; height:100%; object-fit:cover; display:block; }}
.thumb-ph {{ width:100%; height:100%; display:flex; align-items:center; justify-content:center;
  color:var(--muted); font-size:.72rem; text-align:center; padding:8px; }}
.badge {{ position:absolute; top:8px; left:8px; font-size:.66rem; font-weight:600; text-transform:uppercase;
  letter-spacing:.04em; padding:.2rem .5rem; border-radius:6px; }}
.badge.image {{ background:var(--accent-soft); color:var(--accent); }}
.badge.video {{ background:var(--video-soft); color:var(--video); }}
.badge.carousel {{ background:var(--carousel-soft); color:var(--carousel); }}
.card-body {{ padding:10px 12px 12px; display:flex; flex-direction:column; gap:5px; flex:1; }}
.headline {{ font-weight:600; font-size:.86rem; line-height:1.35;
  display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; }}
.page-name {{ color:var(--muted); font-size:.74rem; }}
.card-body a {{ margin-top:auto; font-size:.76rem; text-decoration:none; font-weight:600; }}
.card-body a:hover {{ text-decoration:underline; }}

footer {{ padding-block:24px 40px; color:var(--muted); font-size:.78rem; line-height:1.6; max-width:65ch; }}
footer b {{ color:var(--ink); }}
</style>

<div class="wrap">
  <header>
    <h1>Used Car Ad Scan</h1>
    <p class="sub">A snapshot of live Meta ads (Facebook &amp; Instagram) from 21 used-car and
      certified pre-owned brands active in India, pulled from the public Ad Library on {date.today():%d %b %Y}.</p>
    <div class="stats">
      <div class="stat"><b>{total_ads}</b><span>Ads found</span></div>
      <div class="stat"><b>{brands_with_ads}/21</b><span>Brands with ads</span></div>
      <div class="stat image"><b>{n_image}</b><span>Static image</span></div>
      <div class="stat video"><b>{n_video}</b><span>Video</span></div>
      <div class="stat carousel"><b>{n_carousel}</b><span>Carousel</span></div>
      <div class="stat"><b>{brands_zero}</b><span>No ads found</span></div>
    </div>
  </header>

  <nav class="jump">
{chr(10).join(jump_links)}
  </nav>

  <main>
{chr(10).join(brand_sections)}
  </main>

  <footer>
    <p><b>How this was built.</b> Each brand name was searched directly in Meta's public Ad
      Library (country: India, active ads only), matched to that brand's real advertiser page,
      and up to 14 ads sampled per brand. A brand showing 0 means no ad from a page matching
      that name turned up active at scan time &mdash; some certified pre-owned programs (Honda
      Auto Terrace, BMW Premium Selection) run ads through individual dealer pages rather than
      one central page, so the true count there is likely higher than shown.</p>
  </footer>
</div>
"""

OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
OUT_PATH.write_text(HTML, encoding="utf-8")
print("wrote", OUT_PATH, "size MB:", OUT_PATH.stat().st_size / 1e6)
