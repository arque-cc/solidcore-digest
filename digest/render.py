"""Del diccionari del dia (data/<dia>.json) al Markdown del digest (digests/<dia>.md).
Les seccions surten sempre en el mateix ordre, per poder-les llegir en diagonal."""

from __future__ import annotations

from .classify import KIND_ORDER, MODULE_ORDER
from .collect import REPO_URL, SITE_URL

MODULE_NAMES = {
    "geom": "geom (base geomètrica)", "nurbs": "nurbs", "curve": "curve (corbes)",
    "surface": "surface (superfícies)", "topology": "topology (B-rep)", "intersect": "intersect",
    "primitive": "primitive", "query": "query", "mass": "mass (propietats màssiques)",
    "sweep": "sweep", "heal": "heal (reparació)", "offset": "offset (offset / buidat)",
    "boolean": "boolean", "blend": "blend (arrodoniments i xamfrans)",
    "kernel": "kernel (API, UpstreamFixes, límits)", "tests": "tests d'integració del kernel",
    "step": "STEP (import / export)", "ssi": "ssi (intersecció superfície-superfície)",
    "eines": "altres crates i eines", "difftest": "difftest (comparació Rust vs C++)",
    "harness": "harness / FFI (C++ de referència)", "plan": "plan/ (unitats, issues, findings)",
    "docs": "documentació", "site": "web de progrés", "ci": "CI i scripts", "altres": "altres",
}
KIND_NAMES = {
    "fix": "fix (correccions)", "feat": "feat (funcionalitat nova)", "port": "port (unitats portades)",
    "wire": "wire (connexió d'unitats)", "test": "test", "difftest": "difftest",
    "plan": "plan", "docs": "docs", "perf": "perf", "chore": "chore", "claim": "claim (reserva d'unitat)",
    "style": "style", "altres": "sense prefix / altres",
}
SOURCE_NAMES = {"commit": "commit", "pr": "PR", "upstream-issue": "defecte upstream", "finding": "finding",
                "upstream-fix": "flag UpstreamFixes", "solidcraft-case": "cas SolidCraft", "unit": "unitat",
                "github": "GitHub"}

MAX_VISIBLE = 12  # commits visibles per mòdul abans de plegar la resta


def _n(x) -> str:
    return f"{x:,}".replace(",", ".")


def _commit_line(c: dict) -> str:
    flag = " 🤖" if c["ai"] else ""
    return f"- [`{c['short']}`]({REPO_URL}/commit/{c['sha']}) {c['subject']} — {c['author']}{flag}"


def _pr_line(p: dict) -> str:
    refs = ""
    if p["issue_refs"]:
        refs += " · " + ", ".join(f"[#{n}]({REPO_URL}/issues/{n})" for n in p["issue_refs"])
    if p["upstream_refs"]:
        refs += " · " + ", ".join(p["upstream_refs"])
    return f"- [#{p['number']}]({REPO_URL}/pull/{p['number']}) {p['title'] or '(sense títol)'} — {p['owner']}{refs}"


def _list(items: list[str], visible: int = MAX_VISIBLE, label: str = "més") -> list[str]:
    if len(items) <= visible:
        return items
    out = items[:visible]
    out.append(f"<details><summary>{len(items) - visible} {label}</summary>\n")
    out.extend(items[visible:])
    out.append("\n</details>")
    return out


def render_markdown(d: dict) -> str:
    s, u, ui, f, sc, fx, g, pin = (d["summary"], d["units"], d["upstream_issues"], d["findings"],
                                  d["solidcraft"], d["upstream_fixes"], d["gates"], d["pin"])
    L: list[str] = []
    L.append(f"# SolidCore, {d['day']}")
    L.append("")
    L.append(f"Estat de `main` de [`{d['window']['start_sha'][:9]}`]({REPO_URL}/commit/{d['window']['start_sha']}) "
             f"a [`{d['window']['end_sha'][:9]}`]({REPO_URL}/commit/{d['window']['end_sha']}) "
             f"(dia UTC). Generat {d['generated_at']}.")
    L.append("")

    # 1. Resum en xifres
    L.append("## 1. Resum en xifres")
    L.append("")
    L.append("| | |")
    L.append("|---|---|")
    L.append(f"| Commits | **{_n(s['commits'] - s['claims'])}** amb canvis, {_n(s['claims'])} reserves (`claim:`), "
             f"{_n(s['merges'])} merges, **{_n(s['prs_merged'])} PR fusionades** |")
    L.append(f"| Autors | {s['authors']} — " + ", ".join(f"{a} ({n})" for a, n in s["top_authors"][:5]) + " |")
    L.append(f"| Commits amb coautoria d'IA | {_n(s['ai_coauthored'])} ({(100 * s['ai_coauthored'] // max(1, s['commits']))} %) |")
    L.append(f"| Fitxers diferents tocats | {_n(s['files_touched'])} |")
    green = u["counts"].get("green", 0)
    L.append(f"| Unitats verdes | {green} / {u['total']}"
             + (f" ({len(u['status_changes'])} canvis d'estat)" if u["status_changes"] else "") + " |")
    L.append(f"| Defectes de l'upstream registrats | {_n(ui['total'])} (+{len(ui['new'])} nous, +{len(ui['new_addenda'])} addenda) · "
             + ", ".join(f"{p} {n}" for p, n in ui["counts"].items() if n) + " |")
    L.append(f"| Findings | {_n(f['total'])} (+{len(f['new'])}) |")
    L.append(f"| Casos SolidCraft | " + ", ".join(f"{k} {v}" for k, v in sorted(sc["counts"].items())) +
             (f" · **{len(sc['changes'])} canvis de veredicte**" if sc["changes"] else "") + " |")
    L.append(f"| Flags d'`UpstreamFixes` | {fx['total']} (+{len(fx['new'])}), {fx['fillet_total']} d'arrodoniments |")
    L.append(f"| Portes difftest | {g['known_mismatches']} mismatches coneguts, {g['waivers_after']} waivers |")
    L.append(f"| Pin de l'upstream | usd-brep v{pin['version']} `{pin['commit']}`" + (" **(ha canviat!)**" if pin["changed"] else "") + " |")
    L.append("")

    # 2. Vigilància arque
    L.append("## 2. Vigilància arque")
    L.append("")
    active = [w for w in d["watch"] if w["hits"]]
    if not active:
        L.append("Cap troballa avui en cap tema de la llista.")
    else:
        L.append("Temes de la llista de vigilància amb activitat avui (els casos entre parèntesis són els de la bateria d'arque):")
        L.append("")
        for w in active:
            cases = f" ({', '.join(w['cases'])})" if w["cases"] else ""
            L.append(f"### {w['label']}{cases} — {len(w['hits'])}")
            seen = set()
            rows = []
            for h in w["hits"]:
                key = (h["source"], h["ref"])
                if key in seen:
                    continue
                seen.add(key)
                ref = f"[{h['ref']}]({h['url']})" if h.get("url") else f"`{h['ref']}`"
                why = f" — «{h['matched']}»" if h.get("matched") else ""
                rows.append(f"- {SOURCE_NAMES.get(h['source'], h['source'])} {ref}: {h['text']}{why}")
            L.extend(_list(rows, 10))
            L.append("")
    L.append("")

    # 3. Per mòdul
    L.append("## 3. Commits per mòdul")
    L.append("")
    if not d["commits"]:
        L.append("Cap commit avui.")
    else:
        L.append("| Mòdul | Commits | Fitxers tocats |")
        L.append("|---|---:|---:|")
        for m, v in d["by_module"].items():
            L.append(f"| {MODULE_NAMES.get(m, m)} | {v['commits']} | {_n(v['files'])} |")
        L.append("")
        for m in MODULE_ORDER:
            rows = [c for c in d["commits"] if c["module"] == m]
            if not rows:
                continue
            L.append(f"### {MODULE_NAMES.get(m, m)} — {len(rows)}")
            L.extend(_list([_commit_line(c) for c in rows]))
            L.append("")

    # 4. Per tipus
    L.append("## 4. Commits per tipus")
    L.append("")
    if d["by_kind"]:
        L.append("| Tipus | Commits |")
        L.append("|---|---:|")
        for k in KIND_ORDER:
            if d["by_kind"].get(k):
                L.append(f"| {KIND_NAMES.get(k, k)} | {d['by_kind'][k]} |")
    L.append("")

    # 5. Canvis a plan/
    L.append("## 5. Canvis a `plan/` i a les portes de qualitat")
    L.append("")
    if u["status_changes"]:
        L.append("**Unitats que han canviat d'estat:**")
        for ch in u["status_changes"]:
            L.append(f"- `{ch['unit']}`: {ch['before'] or 'nova'} → **{ch['after'] or 'retirada'}**")
        L.append("")
    if u["not_green"]:
        L.append("Unitats que no són verdes: " + ", ".join(f"`{x}`" for x in u["not_green"]) + ".")
        L.append("")
    if u["notes_updated"]:
        L.append(f"Notes actualitzades a {len(u['notes_updated'])} unitats: "
                 + ", ".join(f"`{x}`" for x in u["notes_updated"][:15])
                 + (" …" if len(u["notes_updated"]) > 15 else "") + ".")
        L.append("")
    if ui["new"]:
        L.append(f"**Defectes nous de l'upstream (C++ de SMLib), {len(ui['new'])}:**")
        L.extend(_list([f"- **{it['id']}** [{it['title']}]({REPO_URL}/blob/{d['window']['end_sha']}/plan/upstream-issues/{it['file']})"
                        for it in ui["new"]], 20))
        L.append("")
    if ui["new_addenda"]:
        L.append(f"Addenda nous a defectes existents ({len(ui['new_addenda'])}): "
                 + ", ".join(f"`{a.split('--')[0]}`" for a in ui["new_addenda"][:20]) + ".")
        L.append("")
    if ui["removed"]:
        L.append("Defectes retirats: " + ", ".join(ui["removed"]) + ".")
        L.append("")
    if f["new"]:
        L.append(f"**Findings nous, {len(f['new'])}:**")
        L.extend(_list([f"- [{it['file'].split('--')[0]}]({REPO_URL}/blob/{d['window']['end_sha']}/plan/findings/{it['file']}): {it['title']}"
                        for it in f["new"]], 15))
        L.append("")
    if fx["new"] or fx["removed"]:
        L.append(f"**Flags d'`UpstreamFixes` nous ({len(fx['new'])}):**")
        for it in fx["new"]:
            L.append(f"- `{it['flag']}`: {it['doc']}")
        for r in fx["removed"]:
            L.append(f"- ~~`{r}`~~ (retirat)")
        L.append("")
    if sc["changes"] or sc["new"]:
        L.append("**Casos de SolidCraft:**")
        for it in sc["changes"]:
            L.append(f"- `{it['id']}`: {it['before']} → **{it['after']}**" + (f" ([issue]({it['issue']}))" if it.get("issue") else ""))
        for it in sc["new"]:
            L.append(f"- `{it['id']}`: nou, {it['verdict']}" + (f" ([issue]({it['issue']}))" if it.get("issue") else ""))
        L.append("")
    if sc["failing"]:
        L.append("Casos de SolidCraft que fallen: " + ", ".join(f"`{x}`" for x in sc["failing"]) + ".")
        L.append("")
    if g["mismatches_new"] or g["mismatches_removed"] or g["waivers_before"] != g["waivers_after"]:
        L.append(f"Portes difftest: mismatches coneguts +{len(g['mismatches_new'])}/−{len(g['mismatches_removed'])}, "
                 f"waivers {g['waivers_before']} → {g['waivers_after']}.")
        L.append("")
    if pin["changed"]:
        L.append(f"**El pin de l'upstream ha canviat**: v{pin['before_version']} → v{pin['version']} (`{pin['commit']}`). "
                 "Caldrà tornar a passar la bateria d'arque.")
        L.append("")
    if d["status_md_changed"]:
        L.append(f"`plan/STATUS.md` s'ha actualitzat ([veure]({REPO_URL}/blob/{d['window']['end_sha']}/plan/STATUS.md)).")
        L.append("")
    if not any([u["status_changes"], ui["new"], ui["new_addenda"], f["new"], fx["new"], sc["changes"], sc["new"],
                pin["changed"], d["status_md_changed"]]):
        L.append("Sense canvis a `plan/` avui.")
        L.append("")

    # 6. PR fusionades i GitHub
    L.append("## 6. PR fusionades i activitat a GitHub")
    L.append("")
    if d["prs"]:
        L.append(f"**PR fusionades a `main`, {len(d['prs'])}** (reconstruïdes dels commits de merge):")
        L.extend(_list([_pr_line(p) for p in d["prs"]], 20))
        L.append("")
    gh = d["github"]
    if gh.get("ok"):
        L.append(f"Obertes al final del dia: {gh.get('open_issues', '?')} issues, {gh.get('open_prs', '?')} PR.")
        for key, title in (("issues_opened", "Issues obertes avui"), ("issues_closed", "Issues tancades avui"),
                           ("prs_opened", "PR obertes avui"), ("prs_closed_unmerged", "PR tancades sense fusionar")):
            if gh.get(key):
                L.append(f"- {title} ({len(gh[key])}): " + "; ".join(
                    f"[#{i['number']}]({i['url']}) {i['title']}" for i in gh[key][:12])
                    + (" …" if len(gh[key]) > 12 else ""))
    else:
        L.append(f"_API de GitHub no consultada: {gh.get('error', 'sense detall')}._")
    L.append("")

    # 7. Upstream i releases
    L.append("## 7. Upstream i versions")
    L.append("")
    if d["tags"]:
        L.append("Tags nous al repositori: " + ", ".join(f"`{t}`" for t, _ in d["tags"]) + ".")
    rel = d["releases"]
    if rel.get("ok"):
        ci = rel.get("crates_io") or {}
        if ci.get("new_versions"):
            L.append(f"**Versió nova a crates.io:** " + ", ".join(ci["new_versions"]) + f" (última: {ci.get('max_version')}).")
        elif "error" not in ci:
            L.append(f"crates.io: cap versió nova (última {ci.get('max_version')}).")
        if rel.get("upstream"):
            L.append("**Release nova de usd-brep (NVIDIA):** " + ", ".join(f"[{r['tag']}]({r['url']})" for r in rel["upstream"]))
        elif rel.get("upstream_latest"):
            L.append(f"usd-brep: cap release nova (última {rel['upstream_latest']}; solidcore està fixat a v{pin['version']}).")
    else:
        L.append("_Sense consulta de versions (xarxa desactivada)._")
    L.append("")
    L.append(f"---\n_Fonts: [`git log`]({REPO_URL}/commits/main), [`plan/`]({REPO_URL}/tree/main/plan), "
             f"[web de progrés]({SITE_URL}/). Classificació per regles; sense models._")
    return "\n".join(L) + "\n"
