#!/usr/bin/env python3
"""solidcore-digest: diari de novetats de tangency-labs/solidcore.

    python3 digest.py run      --repo PATH [--date AAAA-MM-DD] [--no-network]
    python3 digest.py backfill --repo PATH --from AAAA-MM-DD --to AAAA-MM-DD
    python3 digest.py site

`run` genera data/<dia>.json i digests/<dia>.md per a un dia UTC (ahir per defecte).
`site` reconstrueix public/ (index.html amb la sèrie temporal i un HTML per digest).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from digest.collect import collect_day  # noqa: E402
from digest.render import render_markdown  # noqa: E402
from digest.site import build_site  # noqa: E402


def cmd_run(args: argparse.Namespace) -> int:
    day = date.fromisoformat(args.date) if args.date else (datetime.now(timezone.utc) - timedelta(days=1)).date()
    repo = Path(args.repo).expanduser().resolve()
    if not (repo / ".git").exists():
        print(f"{repo} no és un repositori git", file=sys.stderr)
        return 2
    out = Path(args.out).resolve()
    data = collect_day(repo, day, HERE / "watchlist.toml", with_network=not args.no_network, branch=args.branch)
    (out / "data").mkdir(parents=True, exist_ok=True)
    (out / "digests").mkdir(parents=True, exist_ok=True)
    (out / "data" / f"{day}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    md = render_markdown(data)
    (out / "digests" / f"{day}.md").write_text(md, encoding="utf-8")
    s = data["summary"]
    print(f"{day}: {s['commits']} commits, {s['prs_merged']} PR, "
          f"{sum(len(w['hits']) for w in data['watch'])} troballes de vigilància -> digests/{day}.md")
    return 0


def cmd_backfill(args: argparse.Namespace) -> int:
    """Genera tots els dies entre --from i --to (inclosos), un rere l'altre."""
    d0, d1 = date.fromisoformat(args.from_date), date.fromisoformat(args.to_date)
    rc = 0
    while d0 <= d1:
        args.date = d0.isoformat()
        try:
            rc |= cmd_run(args)
        except SystemExit as e:  # un dia sense commits (abans de l'inici del repo): s'omet
            print(f"{d0}: omès ({e})")
        d0 += timedelta(days=1)
    return rc


def cmd_site(args: argparse.Namespace) -> int:
    out = Path(args.out).resolve()
    n = build_site(out / "data", out / "public")
    print(f"public/: index + {n} digests")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="genera el digest d'un dia")
    r.add_argument("--repo", required=True, help="clon local de tangency-labs/solidcore")
    r.add_argument("--date", help="dia UTC (AAAA-MM-DD); per defecte, ahir")
    r.add_argument("--branch", default="main")
    r.add_argument("--out", default=str(HERE), help="arrel on escriure data/ i digests/")
    r.add_argument("--no-network", action="store_true", help="no consultar GitHub ni crates.io")
    r.set_defaults(func=cmd_run)
    b = sub.add_parser("backfill", help="genera un interval de dies")
    b.add_argument("--repo", required=True)
    b.add_argument("--from", dest="from_date", required=True, help="primer dia (AAAA-MM-DD)")
    b.add_argument("--to", dest="to_date", required=True, help="últim dia (AAAA-MM-DD)")
    b.add_argument("--branch", default="main")
    b.add_argument("--out", default=str(HERE))
    b.add_argument("--no-network", action="store_true")
    b.set_defaults(func=cmd_backfill)
    s = sub.add_parser("site", help="reconstrueix public/ a partir de data/")
    s.add_argument("--out", default=str(HERE))
    s.set_defaults(func=cmd_site)
    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
