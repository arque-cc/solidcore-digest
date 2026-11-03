"""Recull totes les dades d'un dia en un únic diccionari (el que es desa a data/<dia>.json).
Aquest és el punt on s'ajunten git, la classificació, els diffs de plan/ i les API.
"""

from __future__ import annotations

import re
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from . import classify, github_api, plan_diff
from .gitlog import (Commit, Window, commits_between, day_window, merged_prs, remove_worktree,
                     tags_in_window, worktree)

REPO_URL = "https://github.com/tangency-labs/solidcore"
SITE_URL = "https://tangency-labs.github.io/solidcore"

_AI_COAUTHOR_RE = re.compile(r"co-authored-by:.*\b(claude|codex|gpt|copilot|cursor|gemini|anthropic|openai)\b", re.I)


def _watch_entries(rules: list[classify.WatchRule]) -> dict[str, dict]:
    return {r.id: {"id": r.id, "label": r.label, "cases": r.cases, "hits": []} for r in rules}


def collect_day(repo: Path, day, watchlist_path: Path, with_network: bool = True, branch: str = "main") -> dict:
    w: Window = day_window(repo, day, branch)
    commits = commits_between(repo, w.start_sha, w.end_sha)
    rules = classify.load_watchlist(watchlist_path)
    watch = _watch_entries(rules)

    def add_hit(rule: classify.WatchRule, source: str, ref: str, text: str, url: str | None = None,
                matched: str | None = None):
        """`text` és el títol de l'element; `matched`, la línia on ha coincidit la regla si
        no és el títol (p. ex. una línia del cos del commit)."""
        h = {"source": source, "ref": ref, "text": text[:200], "url": url}
        if matched and matched.strip() != text.strip():
            h["matched"] = matched[:200]
        watch[rule.id]["hits"].append(h)

    # --- commits ---
    non_merge = [c for c in commits if not c.is_merge]
    classified = [classify.classify_commit(c) for c in non_merge]
    # Els commits "claim:" són buits (reserven una unitat o una issue per a un agent):
    # compten al tipus, però no als mòduls ni a la vigilància.
    claims = sum(1 for cl in classified if cl.kind == "claim")
    classified = [cl for cl in classified if cl.kind != "claim"]
    by_module: dict[str, dict] = defaultdict(lambda: {"commits": 0, "files": 0})
    by_kind: Counter = Counter()
    commit_rows = []
    for cl in classified:
        c = cl.commit
        by_module[cl.primary]["commits"] += 1
        by_module[cl.primary]["files"] += sum(cl.modules.values())
        by_kind[cl.kind] += 1
        hits = classify.watch_hits(c.subject + "\n" + c.body, rules)
        for r, line in hits:
            add_hit(r, "commit", c.short, c.subject, f"{REPO_URL}/commit/{c.sha}", line)
        commit_rows.append({
            "sha": c.sha, "short": c.short, "author": c.author, "date": c.date, "subject": c.subject,
            "kind": cl.kind, "module": cl.primary, "modules": sorted(cl.modules),
            "files": sum(cl.modules.values()), "watch": [r.id for r, _ in hits],
            "ai": bool(_AI_COAUTHOR_RE.search(c.body)),
        })

    # --- PR fusionades (dels commits de merge) ---
    prs = merged_prs(commits)
    pr_rows = []
    for p in prs:
        hits = classify.watch_hits(p.title + "\n" + p.branch, rules)
        for r, line in hits:
            add_hit(r, "pr", f"#{p.number}", p.title, f"{REPO_URL}/pull/{p.number}", line)
        kind, mod = classify.kind_of_subject(p.title)
        pr_rows.append({"number": p.number, "title": p.title, "branch": p.branch, "owner": p.author_handle,
                        "merged_by": p.merged_by, "merged_at": p.merged_at, "issue_refs": p.issue_refs,
                        "upstream_refs": p.upstream_refs, "kind": kind, "module": mod,
                        "watch": [r.id for r, _ in hits]})

    # --- estat de plan/ abans i després (dos worktrees) ---
    tmp = Path(tempfile.mkdtemp(prefix="solidcore-digest-"))
    before, after = tmp / "before", tmp / "after"
    try:
        worktree(repo, w.start_sha, before)
        worktree(repo, w.end_sha, after)
        units = plan_diff.diff_units(before, after)
        upstream = plan_diff.diff_upstream_issues(before, after)
        findings = plan_diff.diff_findings(before, after)
        solidcraft = plan_diff.diff_solidcraft_cases(before, after)
        fixes = plan_diff.diff_upstream_fixes(before, after)
        gates = plan_diff.diff_gates(before, after)
        pin = plan_diff.diff_pin(before, after)
        status_md_changed = plan_diff.diff_status_md(before, after)
    finally:
        remove_worktree(repo, before)
        remove_worktree(repo, after)
        try:
            tmp.rmdir()
        except OSError:
            pass

    for it in upstream["new"]:
        for r, _ in classify.watch_hits(it["id"] + " " + it["title"], rules):
            add_hit(r, "upstream-issue", it["id"], it["title"],
                    f"{REPO_URL}/blob/{w.end_sha}/plan/upstream-issues/{it['file']}")
    for it in findings["new"]:
        for r, _ in classify.watch_hits(it["file"] + " " + it["title"], rules):
            add_hit(r, "finding", it["file"].split("--")[0], it["title"],
                    f"{REPO_URL}/blob/{w.end_sha}/plan/findings/{it['file']}")
    for it in fixes["new"]:
        for r, _ in classify.watch_hits(it["flag"] + " " + it["doc"], rules):
            add_hit(r, "upstream-fix", it["flag"], it["doc"])
    for it in solidcraft["changes"] + solidcraft["new"]:
        for r, _ in classify.watch_hits(it["id"], rules):
            add_hit(r, "solidcraft-case", it["id"], f"{it.get('before', 'nou')} → {it.get('after', it.get('verdict'))}", it.get("issue"))
    for it in units["status_changes"]:
        for r, _ in classify.watch_hits(it["unit"], rules):
            add_hit(r, "unit", it["unit"], f"{it['before']} → {it['after']}", f"{SITE_URL}/units/index.html")

    # --- xarxa (opcional) ---
    github = github_api.github_activity(w) if with_network else {"ok": False, "error": "desactivat (--no-network)"}
    rel = github_api.releases(w) if with_network else {"ok": False}
    if github.get("ok"):
        for it in github["issues_opened"] + github["prs_opened"]:
            for r, _ in classify.watch_hits(it["title"], rules):
                add_hit(r, "github", f"#{it['number']}", it["title"], it["url"])

    authors = Counter(c.author for c in non_merge)
    return {
        "day": day.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "window": {"start": w.start.isoformat(), "end": w.end.isoformat(),
                   "start_sha": w.start_sha, "end_sha": w.end_sha},
        "summary": {
            "commits": len(non_merge), "merges": len(commits) - len(non_merge), "claims": claims,
            "prs_merged": len(prs), "authors": len(authors),
            "top_authors": authors.most_common(8),
            "ai_coauthored": sum(1 for r in commit_rows if r["ai"]),
            "files_touched": len({f for c in non_merge for f in c.files}),
        },
        "by_module": {m: by_module[m] for m in classify.MODULE_ORDER if m in by_module},
        "by_kind": {k: by_kind[k] for k in classify.KIND_ORDER if by_kind.get(k)},
        "commits": commit_rows,
        "prs": pr_rows,
        "watch": [v for v in watch.values()],
        "units": units, "upstream_issues": upstream, "findings": findings, "solidcraft": solidcraft,
        "upstream_fixes": fixes, "gates": gates, "pin": pin, "status_md_changed": status_md_changed,
        "tags": tags_in_window(repo, w),
        "github": github, "releases": rel,
    }
