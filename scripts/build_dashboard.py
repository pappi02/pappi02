"""Build the profile dashboard SVGs from live GitHub data.

Writes assets/{header,stats,languages}-{dark,light}.svg.
Standard library only. Needs GITHUB_TOKEN (the Actions token is enough) and
optionally GH_USER (defaults to the repository owner).
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import urllib.request
from pathlib import Path

USER = os.environ.get("GH_USER") or os.environ.get("GITHUB_REPOSITORY_OWNER") or "pappi02"
TOKEN = os.environ["GITHUB_TOKEN"]
OUT = Path(__file__).resolve().parent.parent / "assets"

FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', Arial, sans-serif"
MONO = "'Cascadia Code', 'SFMono-Regular', Consolas, 'Liberation Mono', monospace"

THEMES = {
    "dark": {
        "bg": "#030407", "card": "#080C16", "line": "#18223A", "text": "#EEF2FA",
        "muted": "#8D97AC", "accent": "#1558C9", "accent2": "#4F86E8", "lime": "#D4FF24",
        "limeText": "#D4FF24", "limeBar": "#D4FF24", "pill": "#0B1A3A", "pillLine": "#2B4C8F", "glow": "0.55", "grid": "#0E1528",
    },
    "light": {
        "bg": "#FFFFFF", "card": "#F6F8FD", "line": "#DCE3F0", "text": "#0A0F1E",
        "muted": "#5A6479", "accent": "#1558C9", "accent2": "#3A74DB", "lime": "#D4FF24",
        "limeText": "#4D6600", "limeBar": "#8DB000", "pill": "#FFFFFF", "pillLine": "#B9C8E6", "glow": "0.22", "grid": "#EDF1F8",
    },
}

# Languages that are tooling noise rather than real project work.
IGNORED_LANGS = {"Batchfile", "Roff", "Nushell", "Procfile", "Shell", "PowerShell", "Cython", "Makefile", "Dockerfile", "Jupyter Notebook"}


def gql(query: str, variables: dict) -> dict:
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "User-Agent": "profile-dashboard"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        body = json.load(r)
    if body.get("errors"):
        raise RuntimeError(body["errors"])
    return body["data"]


def fetch() -> dict:
    now = dt.datetime.now(dt.timezone.utc)
    q = """
    query($login:String!, $from:DateTime!, $to:DateTime!, $after:String) {
      user(login:$login) {
        createdAt
        followers { totalCount }
        contributionsCollection(from:$from, to:$to) {
          totalCommitContributions totalPullRequestContributions totalIssueContributions
          restrictedContributionsCount
          contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } }
        }
        repositories(first:100, after:$after, ownerAffiliations:OWNER, isFork:false, privacy:PUBLIC) {
          totalCount
          pageInfo { hasNextPage endCursor }
          nodes { name stargazerCount languages(first:10, orderBy:{field:SIZE, direction:DESC}) { edges { size node { name color } } } }
        }
      }
    }"""
    v = {"login": USER, "from": (now - dt.timedelta(days=365)).isoformat(), "to": now.isoformat(), "after": None}
    data = gql(q, v)["user"]
    repos = data["repositories"]["nodes"]
    while data["repositories"]["pageInfo"]["hasNextPage"]:
        v["after"] = data["repositories"]["pageInfo"]["endCursor"]
        more = gql(q, v)["user"]
        repos += more["repositories"]["nodes"]
        data["repositories"]["pageInfo"] = more["repositories"]["pageInfo"]
    data["repos"] = repos
    return data


def streaks(days: list[dict]) -> tuple[int, int]:
    counts = [d["contributionCount"] for d in sorted(days, key=lambda d: d["date"])]
    longest = run = 0
    for c in counts:
        run = run + 1 if c else 0
        longest = max(longest, run)
    current = 0
    # Today may still be empty; the streak is alive if yesterday counted.
    tail = counts[:-1] if counts and counts[-1] == 0 else counts
    for c in reversed(tail):
        if not c:
            break
        current += 1
    return current, longest


def language_share(repos: list[dict]) -> list[tuple[str, str, float]]:
    """Each repo contributes its own language mix, so one huge repo can't dominate."""
    share: dict[str, float] = {}
    colors: dict[str, str] = {}
    counted = 0
    for r in repos:
        edges = [e for e in r["languages"]["edges"] if e["node"]["name"] not in IGNORED_LANGS]
        total = sum(e["size"] for e in edges)
        if not total:
            continue
        counted += 1
        for e in edges:
            n = e["node"]["name"]
            share[n] = share.get(n, 0) + e["size"] / total
            colors[n] = e["node"]["color"] or "#8D97AC"
    if not counted:
        return []
    top = sorted(share.items(), key=lambda kv: -kv[1])
    items = [(n, colors[n], s / counted) for n, s in top[:6]]
    rest = sum(s for _, s in top[6:]) / counted
    if rest > 0.005:
        items.append(("Other", "#5A6479", rest))
    return items


def esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def frame(w: int, h: int, t: dict, body: str, title: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}">
<title>{esc(title)}</title>
<style>
  .t {{ font-family: {FONT}; fill: {t['text']}; }}
  .m {{ font-family: {FONT}; fill: {t['muted']}; }}
  .mono {{ font-family: {MONO}; }}
  @keyframes rise {{ from {{ opacity: 0; transform: translateY(6px); }} to {{ opacity: 1; transform: none; }} }}
  @keyframes grow {{ from {{ transform: scaleX(0); }} to {{ transform: scaleX(1); }} }}
  @keyframes pulse {{ 0%,100% {{ opacity: 1; }} 50% {{ opacity: .35; }} }}
  .rise {{ animation: rise .6s ease-out both; }}
  .grow {{ transform-box: fill-box; transform-origin: left; animation: grow .9s cubic-bezier(.2,.8,.2,1) both; }}
  .pulse {{ animation: pulse 2.2s ease-in-out infinite; }}
  @media (prefers-reduced-motion: reduce) {{ .rise, .grow, .pulse {{ animation: none; }} }}
</style>
<rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="18" fill="{t['card']}" stroke="{t['line']}"/>
{body}
</svg>
"""


def header(t: dict, name: str) -> str:
    w, h = 1200, 300
    chips = ["IT Support", "Networking", "ERP Support", "Cybersecurity", "Full-Stack"]
    x, chip_svg = 64, []
    for i, c in enumerate(chips):
        cw = 22 + len(c) * 8.4
        chip_svg.append(
            f'<g class="rise" style="animation-delay:{.25 + i*.08:.2f}s"><rect x="{x}" y="206" width="{cw:.0f}" height="34" rx="17" fill="none" stroke="{t["line"]}"/>'
            f'<text x="{x + cw/2:.0f}" y="228" text-anchor="middle" class="t" font-size="14" font-weight="600">{esc(c)}</text></g>')
        x += cw + 10
    grid = "".join(f'<line x1="{gx}" y1="0" x2="{gx}" y2="{h}" stroke="{t["grid"]}"/>' for gx in range(0, w, 40))
    grid += "".join(f'<line x1="0" y1="{gy}" x2="{w}" y2="{gy}" stroke="{t["grid"]}"/>' for gy in range(0, h, 40))
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{esc(name)}, IT Support and Networking, Full-Stack Developer">
<title>{esc(name)}</title>
<defs>
  <radialGradient id="g" cx="82%" cy="30%" r="60%"><stop offset="0" stop-color="{t['accent']}" stop-opacity="{t['glow']}"/><stop offset="1" stop-color="{t['accent']}" stop-opacity="0"/></radialGradient>
  <linearGradient id="fade" x1="0" x2="1"><stop offset="0" stop-color="{t['bg']}" stop-opacity="1"/><stop offset=".55" stop-color="{t['bg']}" stop-opacity=".4"/><stop offset="1" stop-color="{t['bg']}" stop-opacity="0"/></linearGradient>
  <clipPath id="c"><rect width="{w}" height="{h}" rx="22"/></clipPath>
</defs>
<style>
  .t {{ font-family: {FONT}; fill: {t['text']}; }}
  .m {{ font-family: {FONT}; fill: {t['muted']}; }}
  @keyframes rise {{ from {{ opacity: 0; transform: translateY(8px); }} to {{ opacity: 1; transform: none; }} }}
  @keyframes drift {{ 0%,100% {{ transform: translate(0,0); }} 50% {{ transform: translate(-30px,14px); }} }}
  @keyframes pulse {{ 0%,100% {{ opacity: 1; }} 50% {{ opacity: .3; }} }}
  .rise {{ animation: rise .7s ease-out both; }}
  .drift {{ animation: drift 14s ease-in-out infinite; }}
  .pulse {{ animation: pulse 2.2s ease-in-out infinite; }}
  @media (prefers-reduced-motion: reduce) {{ .rise, .drift, .pulse {{ animation: none; }} }}
</style>
<g clip-path="url(#c)">
  <rect width="{w}" height="{h}" fill="{t['bg']}"/>
  <g opacity=".9">{grid}</g>
  <g class="drift"><rect width="{w}" height="{h}" fill="url(#g)"/></g>
  <rect width="{w}" height="{h}" fill="url(#fade)"/>
  <rect x="64" y="58" width="44" height="4" rx="2" fill="{t['lime']}"/>
  <g class="rise"><text x="64" y="128" class="t" font-size="54" font-weight="800" letter-spacing="-1.5">{esc(name)}</text></g>
  <g class="rise" style="animation-delay:.12s"><text x="64" y="170" class="m" font-size="21">IT Support &amp; Networking  ·  ERP User Support  ·  Full-Stack Developer</text></g>
  {''.join(chip_svg)}
  <g class="rise" style="animation-delay:.6s">
    <rect x="{w-300}" y="58" width="236" height="36" rx="18" fill="{t['pill']}" stroke="{t['pillLine']}"/>
    <circle cx="{w-280}" cy="76" r="7" fill="{t['limeBar']}" opacity=".25"/>
    <circle class="pulse" cx="{w-280}" cy="76" r="4.5" fill="{t['limeBar']}"/>
    <text x="{w-266}" y="81" class="t" font-size="14" font-weight="600">Open to work  ·  Nairobi, KE</text>
  </g>
  <text x="{w-64}" y="{h-36}" text-anchor="end" class="m" font-size="13" font-family="{MONO}">BSc Computer Technology · Cisco Ethical Hacker</text>
</g>
<rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="22" fill="none" stroke="{t['line']}"/>
</svg>
"""


def stats_card(t: dict, d: dict) -> str:
    cc = d["contributionsCollection"]
    days = [day for wk in cc["contributionCalendar"]["weeks"] for day in wk["contributionDays"]]
    cur, longest = streaks(days)
    stars = sum(r["stargazerCount"] for r in d["repos"])
    tiles = [
        ("Contributions", cc["contributionCalendar"]["totalContributions"], "last 12 months"),
        ("Commits", cc["totalCommitContributions"], "last 12 months"),
        ("Current streak", cur, f"longest {longest} days"),
        ("Public repos", d["repositories"]["totalCount"], f"{stars} stars" if stars else "original work"),
    ]
    w, h = 495, 230
    body = [f'<text x="28" y="42" class="t" font-size="16" font-weight="700">Activity</text>',
            f'<text x="{w-28}" y="42" text-anchor="end" class="m mono" font-size="11">updated {dt.date.today():%d %b %Y}</text>']
    for i, (label, value, sub) in enumerate(tiles):
        col, row = i % 2, i // 2
        x, y = 28 + col * 226, 62 + row * 78
        body.append(
            f'<g class="rise" style="animation-delay:{i*.08:.2f}s">'
            f'<rect x="{x}" y="{y}" width="212" height="66" rx="12" fill="{t["bg"]}" stroke="{t["line"]}"/>'
            f'<rect x="{x+14}" y="{y+16}" width="3" height="34" rx="1.5" fill="{t["limeBar"] if i == 2 else t["accent"]}"/>'
            f'<text x="{x+28}" y="{y+29}" class="m" font-size="12">{esc(label)}</text>'
            f'<text x="{x+28}" y="{y+52}" class="t" font-size="22" font-weight="800">{value:,}</text>'
            f'<text x="{x+198}" y="{y+52}" text-anchor="end" class="m" font-size="11">{esc(sub)}</text></g>')
    return frame(w, h, t, "\n".join(body), "GitHub activity")


def languages_card(t: dict, d: dict) -> str:
    items = language_share(d["repos"])
    w, h = 495, 230
    body = ['<text x="28" y="42" class="t" font-size="16" font-weight="700">Languages across projects</text>']
    # stacked bar
    x0, bw, x = 28, w - 56, 28.0
    body.append(f'<clipPath id="bar"><rect x="{x0}" y="60" width="{bw}" height="10" rx="5"/></clipPath><g clip-path="url(#bar)" class="grow">')
    for _, color, share in items:
        seg = bw * share
        body.append(f'<rect x="{x:.1f}" y="60" width="{seg + .6:.1f}" height="10" fill="{color}"/>')
        x += seg
    body.append("</g>")
    for i, (name, color, share) in enumerate(items):
        col, row = i % 2, i // 2
        lx, ly = 28 + col * 226, 104 + row * 30
        body.append(
            f'<g class="rise" style="animation-delay:{.2 + i*.06:.2f}s"><circle cx="{lx+6}" cy="{ly-5}" r="5" fill="{color}"/>'
            f'<text x="{lx+20}" y="{ly}" class="t" font-size="14" font-weight="600">{esc(name)}</text>'
            f'<text x="{lx+204}" y="{ly}" text-anchor="end" class="m mono" font-size="13">{share*100:.1f}%</text></g>')
    body.append(f'<text x="28" y="{h-24}" class="m" font-size="11">Averaged per project, so no single repo dominates · excludes build tooling</text>')
    return frame(w, h, t, "\n".join(body), "Languages across projects")


def main() -> None:
    OUT.mkdir(exist_ok=True)
    data = fetch()
    name = os.environ.get("DISPLAY_NAME", "David Baraka Nyongesa")
    for mode, t in THEMES.items():
        (OUT / f"header-{mode}.svg").write_text(header(t, name), encoding="utf-8")
        (OUT / f"stats-{mode}.svg").write_text(stats_card(t, data), encoding="utf-8")
        (OUT / f"languages-{mode}.svg").write_text(languages_card(t, data), encoding="utf-8")
    print("wrote", sorted(p.name for p in OUT.glob("*.svg")))


if __name__ == "__main__":
    main()
