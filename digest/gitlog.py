"""Lectura de l'historial de git: finestra d'un dia, commits, fitxers tocats i PR fusionades.

Tot passa per la línia d'ordres de git (subprocess). No hi ha cap dependència externa.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


def git(repo: Path, *args: str) -> str:
    """Executa `git <args>` dins el repositori i retorna la sortida (text)."""
    out = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return out.stdout


@dataclass
class Window:
    """Un dia UTC: [start, end). `start_sha` és l'últim commit de `main` abans del dia,
    `end_sha` l'últim commit dins el dia. Els commits del dia són `start_sha..end_sha`."""

    day: date
    start: datetime
    end: datetime
    start_sha: str
    end_sha: str


def day_window(repo: Path, day: date, branch: str = "main") -> Window:
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    # --first-parent: seguim només la línia principal, així el SHA és "l'estat de main"
    # en aquell moment i no un commit d'una branca fusionada més tard.
    start_sha = git(repo, "rev-list", "-1", "--first-parent",
                    f"--until={(start - timedelta(seconds=1)).isoformat()}", branch).strip()
    end_sha = git(repo, "rev-list", "-1", "--first-parent",
                  f"--until={(end - timedelta(seconds=1)).isoformat()}", branch).strip()
    if not start_sha or not end_sha:
        raise SystemExit(f"No hi ha commits a {branch} abans de {day}")
    return Window(day, start, end, start_sha, end_sha)


@dataclass
class Commit:
    sha: str
    parents: list[str]
    author: str
    date: str
    subject: str
    body: str
    files: list[str] = field(default_factory=list)  # camins tocats

    @property
    def is_merge(self) -> bool:
        return len(self.parents) > 1

    @property
    def short(self) -> str:
        return self.sha[:9]


# Separadors de registre: \x01 obre un commit, \x02 separa camps, \x03 tanca el cos.
_FMT = "%x01%H%x02%P%x02%an%x02%cI%x02%s%x02%b%x03"


def commits_between(repo: Path, start_sha: str, end_sha: str) -> list[Commit]:
    """Tots els commits que van entrar a main entre els dos estats, amb els fitxers tocats.

    Per què --name-only --no-renames i no --numstat: per comptar línies git ha de llegir
    el contingut dels fitxers, i amb un clon --filter=blob:none els baixa d'un en un
    (minuts per dia). Per saber quins fitxers canvien n'hi ha prou amb comparar els
    arbres, que ja són locals: dècimes de segon. Els merges no porten llista de fitxers,
    cosa que ja ens va bé: els seus canvis ja compten als commits fills."""
    raw = git(repo, "log", f"--format={_FMT}", "--name-only", "--no-renames", f"{start_sha}..{end_sha}")
    commits: list[Commit] = []
    for rec in raw.split("\x01")[1:]:
        head, _, tail = rec.partition("\x03")
        sha, parents, author, cdate, subject, body = head.split("\x02", 5)
        c = Commit(sha, parents.split(), author, cdate, subject.strip(), body.strip())
        c.files = [line.strip() for line in tail.splitlines() if line.strip()]
        commits.append(c)
    return commits


@dataclass
class MergedPR:
    number: int
    title: str
    author_handle: str  # el "owner" de la branca (owner/branch), no sempre l'autor humà
    branch: str
    merged_by: str
    merged_at: str
    sha: str
    issue_refs: list[int]  # números #NNNN del títol o el número inicial de la branca
    upstream_refs: list[str]  # WR-123, HANG-39... citats al títol o a la branca


_MERGE_RE = re.compile(r"^Merge pull request #(\d+) from ([^/\s]+)/(\S+)")
_TITLE_REF_RE = re.compile(r"#(\d{2,5})\b")
_BRANCH_REF_RE = re.compile(r"^[a-z]+/(\d{3,5})-")
UPSTREAM_ID_RE = re.compile(r"\b(WR|HANG|UB|ND|DOC|FAIL|ISSUE)-(\d+)\b", re.IGNORECASE)


def merged_prs(commits: list[Commit]) -> list[MergedPR]:
    """Reconstrueix les PR fusionades a partir dels commits de merge, sense API.
    El títol de la PR és la primera línia del cos del commit de merge."""
    prs: list[MergedPR] = []
    for c in commits:
        m = _MERGE_RE.match(c.subject)
        if not m:
            continue
        number, owner, branch = int(m.group(1)), m.group(2), m.group(3)
        title = c.body.splitlines()[0].strip() if c.body else ""
        refs = {int(n) for n in _TITLE_REF_RE.findall(title)}
        if bm := _BRANCH_REF_RE.match(branch):
            refs.add(int(bm.group(1)))
        refs.discard(number)
        ups = sorted({f"{k.upper()}-{n}" for k, n in UPSTREAM_ID_RE.findall(branch + " " + title)})
        prs.append(MergedPR(number, title, owner, branch, c.author, c.date, c.sha, sorted(refs), ups))
    prs.sort(key=lambda p: p.number)
    return prs


def tags_in_window(repo: Path, w: Window) -> list[tuple[str, str]]:
    """Tags creats dins el dia (per data de creació del tag o del commit)."""
    out = git(repo, "for-each-ref", "--format=%(refname:short)\t%(creatordate:iso-strict)", "refs/tags")
    found = []
    for line in out.splitlines():
        name, _, when = line.partition("\t")
        try:
            t = datetime.fromisoformat(when)
        except ValueError:
            continue
        if w.start <= t.astimezone(timezone.utc) < w.end:
            found.append((name, when))
    return found


def worktree(repo: Path, sha: str, dest: Path) -> None:
    """Deixa a `dest` els fitxers del repositori tal com eren a `sha`.
    Amb un clon --filter=blob:none, git baixa els blobs que falten en un sol lot."""
    if dest.exists():
        git(repo, "worktree", "remove", "--force", str(dest))
    git(repo, "worktree", "add", "--detach", str(dest), sha)


def remove_worktree(repo: Path, dest: Path) -> None:
    if dest.exists():
        git(repo, "worktree", "remove", "--force", str(dest))
