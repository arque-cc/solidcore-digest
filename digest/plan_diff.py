"""Comparació de l'estat del repositori entre dos moments: unitats del port, defectes de
l'upstream, findings, casos de SolidCraft, flags d'UpstreamFixes, waivers i el pin de
l'upstream. Treballa sobre dos directoris (dos worktrees) i retorna diccionaris que es
poden desar com a JSON.
"""

from __future__ import annotations

import json
import re
import tomllib
from collections import Counter
from pathlib import Path

UPSTREAM_ID_RE = re.compile(r"^(WR|HANG|UB|ND|DOC|FAIL|ISSUE)-(\d+)", re.IGNORECASE)
UPSTREAM_PREFIXES = ["WR", "UB", "HANG", "ND", "DOC", "FAIL", "ISSUE"]


def _first_heading(path: Path) -> str:
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if s:
            return s.lstrip("#").strip().strip("*").strip()
    return path.stem


# ---------- unitats del port (plan/units/*.toml) ----------

def _units(tree: Path) -> dict[str, dict]:
    out = {}
    for f in sorted((tree / "plan" / "units").glob("*.toml")):
        try:
            d = tomllib.loads(f.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError:
            continue
        out[d.get("id", f.stem)] = {
            "status": d.get("status", "?"),
            "notes": d.get("notes", ""),
            "module": d.get("id", f.stem).split(".")[0],
        }
    return out


def diff_units(before: Path, after: Path) -> dict:
    a, b = _units(before), _units(after)
    changes = []
    for uid in sorted(set(a) | set(b)):
        sa, sb = a.get(uid, {}).get("status"), b.get(uid, {}).get("status")
        if sa != sb:
            changes.append({"unit": uid, "before": sa, "after": sb})
    notes_updated = sorted(u for u in set(a) & set(b) if a[u]["notes"] != b[u]["notes"])
    counts = Counter(u["status"] for u in b.values())
    return {
        "total": len(b),
        "counts": dict(counts),
        "status_changes": changes,
        "notes_updated": notes_updated,
        "not_green": sorted(u for u, d in b.items() if d["status"] != "green"),
    }


# ---------- defectes de l'upstream (plan/upstream-issues/*.md) ----------

def _upstream_issues(tree: Path) -> tuple[dict[str, dict], list[str]]:
    """Retorna (id -> {title, file}, fitxers d'addenda)."""
    ids: dict[str, dict] = {}
    addenda = []
    for f in sorted((tree / "plan" / "upstream-issues").glob("*.md")):
        if f.name == "README.md":
            continue
        m = UPSTREAM_ID_RE.match(f.name)
        if not m:
            continue
        uid = f"{m.group(1).upper()}-{m.group(2)}"
        if "addendum" in f.name.lower():
            addenda.append(f.name)
            continue
        ids[uid] = {"title": _first_heading(f), "file": f.name}
    return ids, addenda


def diff_upstream_issues(before: Path, after: Path) -> dict:
    a, addenda_a = _upstream_issues(before)
    b, addenda_b = _upstream_issues(after)
    new = [{"id": k, **b[k]} for k in b if k not in a]
    removed = [k for k in a if k not in b]
    retitled = [{"id": k, "before": a[k]["title"], "after": b[k]["title"]}
                for k in b if k in a and a[k]["title"] != b[k]["title"]]
    new_addenda = sorted(set(addenda_b) - set(addenda_a))
    counts = Counter(k.split("-")[0] for k in b)
    return {
        "total": len(b),
        "counts": {p: counts.get(p, 0) for p in UPSTREAM_PREFIXES},
        "new": sorted(new, key=lambda x: (x["id"].split("-")[0], int(x["id"].split("-")[1]))),
        "removed": removed,
        "retitled": retitled,
        "new_addenda": new_addenda,
    }


# ---------- findings (plan/findings/*.md) ----------

def diff_findings(before: Path, after: Path) -> dict:
    fa = {f.name for f in (before / "plan" / "findings").glob("*.md")}
    fb = {f.name: f for f in (after / "plan" / "findings").glob("*.md")}
    new = [{"file": n, "title": _first_heading(fb[n])} for n in sorted(fb) if n not in fa and n != "README.md"]
    return {"total": len(fb) - (1 if "README.md" in fb else 0), "new": new}


# ---------- casos de SolidCraft (reports/solidcraft-cases.json) ----------

def _cases(tree: Path) -> dict:
    p = tree / "reports" / "solidcraft-cases.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def diff_solidcraft_cases(before: Path, after: Path) -> dict:
    a, b = _cases(before), _cases(after)
    va = {c["id"]: c.get("rust", {}).get("verdict") for c in a.get("cases", [])}
    cb = {c["id"]: c for c in b.get("cases", [])}
    changes, new = [], []
    for cid, c in cb.items():
        v = c.get("rust", {}).get("verdict")
        if cid not in va:
            new.append({"id": cid, "verdict": v, "issue": c.get("issue")})
        elif va[cid] != v:
            changes.append({"id": cid, "before": va[cid], "after": v, "issue": c.get("issue")})
    counts = Counter(c.get("rust", {}).get("verdict") for c in cb.values())
    return {"total": len(cb), "counts": dict(counts), "changes": changes, "new": new,
            "failing": sorted(cid for cid, c in cb.items() if c.get("rust", {}).get("verdict") in ("FAIL", "ERROR"))}


# ---------- flags d'UpstreamFixes (crates/solidcore/src/kernel.rs) ----------

_FLAG_RE = re.compile(r"^\s*pub ([a-z0-9_]+): bool,")


def _upstream_fixes(tree: Path) -> dict[str, str]:
    """flag -> primera frase del seu comentari de documentació."""
    p = tree / "crates" / "solidcore" / "src" / "kernel.rs"
    if not p.exists():
        return {}
    flags: dict[str, str] = {}
    inside, depth, doc = False, 0, []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if not inside:
            if line.startswith("pub struct UpstreamFixes {"):
                inside, depth = True, 1
            continue
        depth += line.count("{") - line.count("}")
        if depth <= 0:
            break
        s = line.strip()
        if s.startswith("///"):
            doc.append(s[3:].strip())
        elif m := _FLAG_RE.match(line):
            text = " ".join(doc)
            first = re.split(r"(?<=[.])\s", text, maxsplit=1)[0] if text else ""
            flags[m.group(1)] = first
            doc = []
        elif not s.startswith("#"):
            doc = []
    return flags


def diff_upstream_fixes(before: Path, after: Path) -> dict:
    a, b = _upstream_fixes(before), _upstream_fixes(after)
    return {
        "total": len(b),
        "new": [{"flag": k, "doc": b[k]} for k in b if k not in a],
        "removed": [k for k in a if k not in b],
        "fillet_total": sum(1 for k in b if "fillet" in k or "blend" in k or "round" in k or "corner" in k),
    }


# ---------- waivers i mismatches coneguts ----------

def diff_gates(before: Path, after: Path) -> dict:
    def waivers(tree: Path) -> int:
        p = tree / "plan" / "difftest-waivers.toml"
        if not p.exists():
            return 0
        try:
            return len(tomllib.loads(p.read_text(encoding="utf-8")).get("waiver", []))
        except tomllib.TOMLDecodeError:
            return -1

    def mismatches(tree: Path) -> set[str]:
        d = tree / "crates" / "difftest" / "known_mismatches"
        return {f.name for f in d.glob("*.toml")} if d.exists() else set()

    ma, mb = mismatches(before), mismatches(after)
    return {
        "waivers_before": waivers(before), "waivers_after": waivers(after),
        "known_mismatches": len(mb),
        "mismatches_new": sorted(mb - ma), "mismatches_removed": sorted(ma - mb),
    }


# ---------- pin de l'upstream (scripts/upstream-pin.env) ----------

def _pin(tree: Path) -> dict[str, str]:
    p = tree / "scripts" / "upstream-pin.env"
    out = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                out[k.strip()] = v.strip()
    return out


def diff_pin(before: Path, after: Path) -> dict:
    a, b = _pin(before), _pin(after)
    return {"version": b.get("UPSTREAM_VERSION"), "commit": b.get("UPSTREAM_COMMIT", "")[:9],
            "changed": a != b, "before_version": a.get("UPSTREAM_VERSION")}


def diff_status_md(before: Path, after: Path) -> bool:
    pa, pb = before / "plan" / "STATUS.md", after / "plan" / "STATUS.md"
    return pa.exists() and pb.exists() and pa.read_bytes() != pb.read_bytes()
