"""Consultes opcionals a l'API de GitHub i a crates.io. Tot és best-effort: si no hi ha
xarxa o token, cada secció retorna {"ok": False, "error": ...} i el digest ho diu.

Sense token, l'API de GitHub permet 60 peticions/hora, que per a una execució diària
és de sobres; a GitHub Actions el GITHUB_TOKEN puja el límit a 1.000/hora.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

from .gitlog import Window

REPO = "tangency-labs/solidcore"
UPSTREAM_REPO = "NVIDIA-Omniverse/usd-brep"
USER_AGENT = "solidcore-digest (arque)"


def _get(url: str, token: str | None = None, timeout: int = 20):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _in(ts: str | None, w: Window) -> bool:
    if not ts:
        return False
    t = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)
    return w.start <= t < w.end


def github_activity(w: Window) -> dict:
    """Issues i PR obertes o tancades dins el dia, i recomptes d'obertes al final."""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    try:
        items: list[dict] = []
        page = 1
        while page <= 5:  # 500 elements actualitzats des de l'inici del dia: de sobres
            batch = _get(f"https://api.github.com/repos/{REPO}/issues?state=all&sort=updated"
                         f"&direction=desc&per_page=100&page={page}&since={w.start.isoformat()}", token)
            items.extend(batch)
            if len(batch) < 100:
                break
            page += 1

        def brief(i: dict) -> dict:
            return {"number": i["number"], "title": i["title"], "author": i.get("user", {}).get("login"),
                    "labels": [l["name"] for l in i.get("labels", [])], "url": i.get("html_url")}

        issues = [i for i in items if "pull_request" not in i]
        prs = [i for i in items if "pull_request" in i]
        out = {
            "ok": True,
            "issues_opened": [brief(i) for i in issues if _in(i.get("created_at"), w)],
            "issues_closed": [brief(i) for i in issues if _in(i.get("closed_at"), w)],
            "prs_opened": [brief(p) for p in prs if _in(p.get("created_at"), w)],
            "prs_closed_unmerged": [brief(p) for p in prs if _in(p.get("closed_at"), w)
                                    and not p.get("pull_request", {}).get("merged_at")],
        }
        for key, q in (("open_issues", "is:issue is:open"), ("open_prs", "is:pr is:open")):
            try:
                out[key] = _get(f"https://api.github.com/search/issues?q=repo:{REPO}+{q.replace(' ', '+')}&per_page=1",
                                token).get("total_count")
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
                out[key] = None
        return out
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def releases(w: Window) -> dict:
    """Versions noves de solidcore a crates.io i releases de l'upstream usd-brep."""
    out: dict = {"ok": True, "crates_io": None, "upstream": []}
    try:
        c = _get("https://crates.io/api/v1/crates/solidcore")
        vers = [v for v in c.get("versions", []) if _in(v.get("created_at"), w)]
        out["crates_io"] = {"max_version": c.get("crate", {}).get("max_version"),
                            "new_versions": [v["num"] for v in vers]}
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as e:
        out["crates_io"] = {"error": f"{type(e).__name__}: {e}"}
    try:
        rel = _get(f"https://api.github.com/repos/{UPSTREAM_REPO}/releases?per_page=10",
                   os.environ.get("GITHUB_TOKEN"))
        out["upstream"] = [{"tag": r.get("tag_name"), "name": r.get("name"), "url": r.get("html_url")}
                           for r in rel if _in(r.get("published_at"), w)]
        out["upstream_latest"] = rel[0].get("tag_name") if rel else None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as e:
        out["upstream_error"] = f"{type(e).__name__}: {e}"
    return out
