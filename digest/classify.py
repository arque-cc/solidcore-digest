"""Classificació per regles: a quin mòdul pertany un commit, de quin tipus és, i quines
paraules de la llista de vigilància hi apareixen. Cap model, cap heurística opaca:
tot és prefixos, rutes de fitxers i expressions regulars que es poden llegir aquí.
"""

from __future__ import annotations

import re
import tomllib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .gitlog import Commit

# Mòduls del kernel: crates/solidcore/src/<mòdul>/ o crates/solidcore/src/<mòdul>.rs
KERNEL_MODULES = [
    "geom", "nurbs", "curve", "surface", "topology", "intersect", "primitive", "query",
    "mass", "sweep", "heal", "offset", "boolean", "blend",
]

# Ordre en què surten al digest. "altres" recull el que no encaixa enlloc.
MODULE_ORDER = KERNEL_MODULES + [
    "kernel", "tests", "step", "ssi", "difftest", "harness", "eines", "plan", "docs", "site", "ci", "altres",
]

# Tipus de commit segons el prefix del missatge ("fix:", "fix(blend):", "difftest:", ...).
KIND_ORDER = ["fix", "feat", "port", "wire", "test", "difftest", "plan", "docs",
              "perf", "chore", "claim", "style", "altres"]
KIND_ALIASES = {"doc": "docs", "tests": "test", "refactor": "chore", "ci": "chore",
                "build": "chore", "preset": "chore"}

_PREFIX_RE = re.compile(r"^([a-z][a-z0-9_.-]*)(?:\(([^)]*)\))?:")


def module_of_path(path: str) -> str:
    """Mòdul d'un fitxer pel seu camí dins el repositori."""
    if path.startswith("crates/solidcore/src/"):
        rest = path[len("crates/solidcore/src/"):]
        head = rest.split("/", 1)[0].removesuffix(".rs")
        if head in KERNEL_MODULES:
            return head
        return "kernel"  # kernel.rs, lib.rs, error.rs, limits.rs, math.rs...
    if path.startswith("crates/solidcore/tests"):
        return "tests"  # tests d'integració del kernel (crates/solidcore/tests)
    if path.startswith("crates/solidcore/"):
        return "kernel"  # Cargo.toml, benches, dades del crate
    if path.startswith("crates/step-"):
        return "step"  # step-brep, step-import, step-export
    if path.startswith("crates/ssi") or path.startswith("crates/solidcore-ssi"):
        return "ssi"
    if path.startswith("crates/difftest") or path.startswith("fixtures/") or path.startswith("reports/"):
        return "difftest"
    if path.startswith("crates/solidcore-ffi") or path.startswith("harness/"):
        return "harness"
    if path.startswith("crates/"):
        return "eines"  # xtask, solidcore-record, nurbs-grid-mesh...
    if path.startswith("plan/"):
        return "plan"
    if path.startswith("docs/") or path.endswith(".md"):
        return "docs"
    if path.startswith("site/"):
        return "site"
    if path.startswith(".github/") or path.startswith("scripts/"):
        return "ci"
    return "altres"


def kind_of_subject(subject: str) -> tuple[str, str | None]:
    """Retorna (tipus, mòdul-del-prefix). "blend: ..." -> ("altres", "blend");
    "fix(blend): ..." -> ("fix", "blend"); "difftest: ..." -> ("difftest", None)."""
    m = _PREFIX_RE.match(subject)
    if not m:
        return "altres", None
    head, scope = m.group(1), m.group(2)
    head = KIND_ALIASES.get(head, head)
    if head in KIND_ORDER:
        return head, (scope.split(".")[0] if scope else None)
    root = head.split(".")[0]
    if root in KERNEL_MODULES:
        # "blend:" o "blend.feature_executive:": el prefix és el mòdul, el tipus va al scope
        kind = KIND_ALIASES.get(scope, scope) if scope else "altres"
        return (kind if kind in KIND_ORDER else "altres"), root
    return "altres", None


@dataclass
class Classified:
    commit: Commit
    kind: str
    modules: Counter  # mòdul -> fitxers tocats
    primary: str  # el mòdul amb més fitxers (o el del prefix si el commit no té fitxers)


def classify_commit(c: Commit) -> Classified:
    kind, scope_mod = kind_of_subject(c.subject)
    mods: Counter = Counter()
    for path in c.files:
        mods[module_of_path(path)] += 1
    if mods:
        # Empat o no, si el prefix diu un mòdul del kernel i el commit l'ha tocat, mana el
        # prefix: un fix de blend que porta 40 fixtures de difftest segueix sent de blend.
        if scope_mod in KERNEL_MODULES and mods.get(scope_mod):
            primary = scope_mod
        else:
            primary = mods.most_common(1)[0][0]
    else:
        primary = scope_mod or "altres"
    return Classified(c, kind, mods, primary)


@dataclass
class WatchRule:
    id: str
    label: str
    pattern: re.Pattern
    cases: list[str]


def load_watchlist(path: Path) -> list[WatchRule]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    rules = []
    for w in data.get("watch", []):
        flags = 0 if w.get("case_sensitive") else re.IGNORECASE
        rules.append(WatchRule(w["id"], w["label"], re.compile(w["pattern"], flags), list(w.get("cases", []))))
    return rules


def watch_hits(text: str, rules: list[WatchRule]) -> list[tuple[WatchRule, str]]:
    """Regles que coincideixen amb el text, amb la primera línia on ho fan (el fragment
    que surt al digest: així es veu per què s'ha marcat)."""
    out = []
    for r in rules:
        m = r.pattern.search(text)
        if not m:
            continue
        line_start = text.rfind("\n", 0, m.start()) + 1
        line_end = text.find("\n", m.end())
        line = text[line_start: line_end if line_end >= 0 else len(text)].strip()
        out.append((r, line))
    return out
