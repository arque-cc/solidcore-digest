"""Pàgina estàtica a public/: index.html amb la sèrie temporal i enllaços, i un HTML per
digest (el Markdown convertit amb un conversor mínim, suficient per al subconjunt que
escriu render.py: títols, llistes, taules, negreta, codi, enllaços i <details>).
Sense dependències ni JavaScript: els gràfics són SVG generats aquí."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

CSS = """
:root{--bg:#faf9f6;--fg:#1f1e1b;--muted:#6b6860;--line:#e3e0d8;--acc:#b5532a;--acc2:#2d6a8f;--card:#fff}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--fg:#ece9e2;--muted:#9a968d;--line:#2d2c29;--acc:#e08a5c;--acc2:#6fa8cf;--card:#1c1b19}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:920px;margin:0 auto;padding:24px 16px 64px}h1{font-size:1.6rem;margin:.2em 0}h2{font-size:1.2rem;margin:1.6em 0 .5em;border-bottom:1px solid var(--line);padding-bottom:.2em}
h3{font-size:1rem;margin:1.2em 0 .3em}a{color:var(--acc2)}code{font:.9em ui-monospace,SFMono-Regular,Menlo,monospace;background:var(--line);padding:0 .25em;border-radius:3px}
table{border-collapse:collapse;width:100%;font-size:.95em}td,th{border-bottom:1px solid var(--line);padding:.3em .5em;text-align:left;vertical-align:top}th{color:var(--muted);font-weight:600}
ul{padding-left:1.2em}li{margin:.15em 0}details{margin:.3em 0 .6em}summary{cursor:pointer;color:var(--muted)}
.muted{color:var(--muted)}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:14px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 12px}.card b{display:block;font-size:1.4rem}.card span{color:var(--muted);font-size:.85em}
svg{width:100%;height:auto;display:block;margin:6px 0 16px}.ax{stroke:var(--line)}.lbl{fill:var(--muted);font-size:11px}.l1{stroke:var(--acc);fill:none;stroke-width:2}.l2{stroke:var(--acc2);fill:none;stroke-width:2}
.bar{fill:var(--acc2);opacity:.85}.bar.w{fill:var(--acc)}.days a{display:block;padding:.35em 0;border-bottom:1px solid var(--line);text-decoration:none;color:var(--fg)}.days small{color:var(--muted);margin-left:.6em}
"""


# ---------- Markdown mínim -> HTML ----------

_INLINE = [
    (re.compile(r"`([^`]+)`"), lambda m: f"<code>{html.escape(m.group(1))}</code>"),
    (re.compile(r"\*\*(.+?)\*\*"), lambda m: f"<b>{m.group(1)}</b>"),
    (re.compile(r"~~(.+?)~~"), lambda m: f"<s>{m.group(1)}</s>"),
    (re.compile(r"_([^_]+)_(?=[\s.,;:)]|$)"), lambda m: f"<i>{m.group(1)}</i>"),
    (re.compile(r"\[([^\]]+)\]\(([^)]+)\)"), lambda m: f'<a href="{html.escape(m.group(2), quote=True)}">{m.group(1)}</a>'),
]


def _inline(text: str) -> str:
    # El codi s'escapa dins el seu propi patró; la resta s'escapa abans.
    parts = re.split(r"(`[^`]+`)", text)
    out = []
    for p in parts:
        if p.startswith("`") and p.endswith("`") and len(p) > 1:
            out.append(f"<code>{html.escape(p[1:-1])}</code>")
        else:
            s = html.escape(p, quote=False)
            for rx, fn in _INLINE[1:]:
                s = rx.sub(fn, s)
            out.append(s)
    return "".join(out)


def md_to_html(md: str) -> str:
    out: list[str] = []
    lines = md.splitlines()
    i, in_list, in_table = 0, False, False
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if in_list and not s.startswith("- "):
            out.append("</ul>")
            in_list = False
        if in_table and not s.startswith("|"):
            out.append("</tbody></table>")
            in_table = False
        if not s:
            i += 1
            continue
        if s.startswith("<details>") or s.startswith("</details>"):
            out.append(s)
        elif s.startswith("#"):
            level = len(s) - len(s.lstrip("#"))
            out.append(f"<h{level}>{_inline(s[level:].strip())}</h{level}>")
        elif s.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_inline(s[2:])}</li>")
        elif s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(re.fullmatch(r":?-+:?", c) for c in cells if c):
                i += 1
                continue
            if not in_table:
                out.append("<table><tbody>")
                in_table = True
            out.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in cells) + "</tr>")
        elif s == "---":
            out.append("<hr>")
        else:
            out.append(f"<p>{_inline(s)}</p>")
        i += 1
    if in_list:
        out.append("</ul>")
    if in_table:
        out.append("</tbody></table>")
    return "\n".join(out)


# ---------- gràfics SVG ----------

def _line_chart(days: list[str], series: list[tuple[str, list[float], str]], title: str, ymax: float | None = None) -> str:
    W, H, L, B, T = 900, 220, 40, 30, 20
    n = max(1, len(days) - 1)
    allv = [v for _, vals, _ in series for v in vals if v is not None]
    top = ymax if ymax is not None else (max(allv) if allv else 1) or 1
    def x(i): return L + (W - L - 10) * i / n
    def y(v): return T + (H - T - B) * (1 - v / top)
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{html.escape(title)}">',
             f'<text class="lbl" x="{L}" y="12">{html.escape(title)}</text>']
    for k in range(5):
        v = top * k / 4
        parts.append(f'<line class="ax" x1="{L}" x2="{W - 10}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>'
                     f'<text class="lbl" x="2" y="{y(v) + 4:.1f}">{v:.0f}</text>')
    step = max(1, len(days) // 10)
    for i, d in enumerate(days):
        if i % step == 0 or i == len(days) - 1:
            parts.append(f'<text class="lbl" x="{x(i):.1f}" y="{H - 8}" text-anchor="middle">{d[5:]}</text>')
    for name, vals, cls in series:
        pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vals) if v is not None)
        parts.append(f'<polyline class="{cls}" points="{pts}"><title>{html.escape(name)}</title></polyline>')
    legend = " · ".join(f"{name}" for name, _, _ in series)
    parts.append(f'<text class="lbl" x="{W - 10}" y="12" text-anchor="end">{html.escape(legend)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _bar_chart(days: list[str], vals: list[int], hi: list[int], title: str) -> str:
    """Barres apilades: commits del dia (clar) i, en color, els que han disparat la vigilància."""
    W, H, L, B, T = 900, 200, 40, 30, 20
    top = max(vals) if vals else 1
    bw = (W - L - 10) / max(1, len(days))
    def y(v): return T + (H - T - B) * (1 - v / (top or 1))
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{html.escape(title)}">',
             f'<text class="lbl" x="{L}" y="12">{html.escape(title)}</text>']
    for k in range(5):
        v = top * k / 4
        parts.append(f'<line class="ax" x1="{L}" x2="{W - 10}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>'
                     f'<text class="lbl" x="2" y="{y(v) + 4:.1f}">{v:.0f}</text>')
    step = max(1, len(days) // 10)
    for i, (d, v, w) in enumerate(zip(days, vals, hi)):
        x0 = L + i * bw + 1
        parts.append(f'<rect class="bar" x="{x0:.1f}" y="{y(v):.1f}" width="{max(1, bw - 2):.1f}" height="{H - B - y(v):.1f}"><title>{d}: {v} commits, {w} amb vigilància</title></rect>')
        parts.append(f'<rect class="bar w" x="{x0:.1f}" y="{y(w):.1f}" width="{max(1, bw - 2):.1f}" height="{H - B - y(w):.1f}"/>')
        if i % step == 0 or i == len(days) - 1:
            parts.append(f'<text class="lbl" x="{x0 + bw / 2:.1f}" y="{H - 8}" text-anchor="middle">{d[5:]}</text>')
    parts.append(f'<text class="lbl" x="{W - 10}" y="12" text-anchor="end">commits · amb vigilància arque</text></svg>')
    return "".join(parts)


# ---------- construcció ----------

def _page(title: str, body: str, back: bool = False) -> str:
    nav = '<p class="muted"><a href="index.html">← índex</a></p>' if back else ""
    return (f'<!doctype html><html lang="ca"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{html.escape(title)}</title><style>{CSS}</style></head><body><main>{nav}{body}</main></body></html>")


def build_site(data_dir: Path, public: Path) -> int:
    public.mkdir(parents=True, exist_ok=True)
    days = sorted(data_dir.glob("*.json"))
    rows = [json.loads(p.read_text(encoding="utf-8")) for p in digest_jsons(days)]
    digests_dir = data_dir.parent / "digests"
    for d in rows:
        md = digests_dir / f"{d['day']}.md"
        if md.exists():
            (public / f"{d['day']}.html").write_text(
                _page(f"SolidCore, {d['day']}", md_to_html(md.read_text(encoding="utf-8")), back=True), encoding="utf-8")
    labels = [d["day"] for d in rows]
    commits = [d["summary"]["commits"] - d["summary"].get("claims", 0) for d in rows]
    watched = [len({h["ref"] for w in d["watch"] for h in w["hits"] if h["source"] == "commit"}) for d in rows]
    body = ["<h1>solidcore-digest</h1>",
            '<p class="muted">Diari de <a href="https://github.com/tangency-labs/solidcore">tangency-labs/solidcore</a>, '
            'classificat per regles. Un fitxer per dia UTC. Projecte <i>arque</i>.</p>']
    if rows:
        last = rows[-1]
        s, u, ui = last["summary"], last["units"], last["upstream_issues"]
        body.append('<div class="cards">'
                    f'<div class="card"><b>{s["commits"] - s.get("claims", 0)}</b><span>commits, {last["day"]}</span></div>'
                    f'<div class="card"><b>{s["prs_merged"]}</b><span>PR fusionades</span></div>'
                    f'<div class="card"><b>{u["counts"].get("green", 0)}/{u["total"]}</b><span>unitats verdes</span></div>'
                    f'<div class="card"><b>{ui["total"]}</b><span>defectes upstream (+{len(ui["new"])})</span></div>'
                    f'<div class="card"><b>{last["upstream_fixes"]["total"]}</b><span>flags UpstreamFixes</span></div>'
                    f'<div class="card"><b>{sum(len(w["hits"]) for w in last["watch"])}</b><span>troballes de vigilància</span></div>'
                    "</div>")
        body.append(_bar_chart(labels, commits, watched, "Commits per dia"))
        body.append(_line_chart(labels, [
            ("defectes upstream", [d["upstream_issues"]["total"] for d in rows], "l1"),
            ("flags UpstreamFixes", [d["upstream_fixes"]["total"] for d in rows], "l2")],
            "Defectes de l'upstream registrats i flags d'UpstreamFixes"))
        body.append(_line_chart(labels, [
            ("casos SolidCraft PASS", [d["solidcraft"]["counts"].get("PASS", 0) for d in rows], "l2"),
            ("FAIL+ERROR", [d["solidcraft"]["counts"].get("FAIL", 0) + d["solidcraft"]["counts"].get("ERROR", 0) for d in rows], "l1")],
            "Casos de SolidCraft"))
        body.append(_line_chart(labels, [("unitats verdes", [d["units"]["counts"].get("green", 0) for d in rows], "l2")],
                                "Unitats verdes", ymax=max(d["units"]["total"] for d in rows)))
    body.append("<h2>Digests</h2><div class=\"days\">")
    for d in reversed(rows):
        s = d["summary"]
        hot = ", ".join(w["label"] for w in d["watch"] if w["hits"])
        body.append(f'<a href="{d["day"]}.html">{d["day"]}<small>{s["commits"] - s.get("claims", 0)} commits · {s["prs_merged"]} PR · '
                    f'+{len(d["upstream_issues"]["new"])} defectes · {len(d["units"]["status_changes"])} canvis d\'unitat</small>'
                    + (f'<br><small>{html.escape(hot)}</small>' if hot else "") + "</a>")
    body.append("</div>")
    (public / "index.html").write_text(_page("solidcore-digest", "\n".join(body)), encoding="utf-8")
    (public / "series.json").write_text(json.dumps([{
        "day": d["day"], "commits": d["summary"]["commits"] - d["summary"].get("claims", 0),
        "prs": d["summary"]["prs_merged"], "green": d["units"]["counts"].get("green", 0), "units": d["units"]["total"],
        "upstream_issues": d["upstream_issues"]["total"], "fixes": d["upstream_fixes"]["total"],
        "solidcraft": d["solidcraft"]["counts"], "watch_hits": sum(len(w["hits"]) for w in d["watch"]),
        "by_module": d["by_module"], "by_kind": d["by_kind"]} for d in rows], ensure_ascii=False, indent=1), encoding="utf-8")
    return len(rows)


def digest_jsons(paths: list[Path]) -> list[Path]:
    return [p for p in paths if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.json", p.name)]
