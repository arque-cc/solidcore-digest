# solidcore-digest

Diari de novetats de [tangency-labs/solidcore](https://github.com/tangency-labs/solidcore),
el port a Rust del kernel SMLib de NVIDIA. Un fitxer per dia UTC, sempre amb les mateixes
seccions, classificat **per regles** (prefixos de commit, rutes de fitxers, expressions
regulars): cap model hi decideix res. Projecte *arque*.

## Què conté cada digest

1. **Resum en xifres**: commits, PR fusionades, autors, coautoria d'IA, unitats verdes,
   defectes de l'upstream, findings, casos de SolidCraft, flags d'`UpstreamFixes`, portes
   difftest, pin de l'upstream.
2. **Vigilància arque**: tot el que toca els temes de `watchlist.toml` (setback, radi variable,
   ball patch, arrodoniment més gran que la paret, buidat, penjaments, STEP...), amb el cas de la
   bateria d'arque al qual correspon i la línia exacta que ha disparat la regla.
3. **Commits per mòdul**: `blend`, `boolean`, `topology`, ... segons els fitxers que toca cada
   commit (si el prefix diu un mòdul del kernel i el commit l'ha tocat, mana el prefix).
4. **Commits per tipus**: `fix`, `port`, `wire`, `test`, `difftest`, `plan`, `docs`...
5. **Canvis a `plan/`**: unitats que canvien d'estat, defectes nous de l'upstream (WR, UB, HANG,
   ND...), addenda, findings, flags nous d'`UpstreamFixes` (amb la primera frase de la seva
   documentació), veredictes de casos de SolidCraft, waivers i *known mismatches*, pin de l'upstream.
6. **PR fusionades i GitHub**: les PR es reconstrueixen dels commits de merge (sense API); issues
   i PR obertes o tancades vénen de l'API si hi ha xarxa.
7. **Upstream i versions**: tags, versions noves de `solidcore` a crates.io, releases de usd-brep.

## Fonts i com es llegeixen

| Font | Com | Per què |
|---|---|---|
| `git log start..end` | `--name-only --no-renames` | Comparar arbres no necessita el contingut dels fitxers: amb un clon `--filter=blob:none` és instantani (`--numstat` els baixaria d'un en un). |
| Commits de merge | `Merge pull request #N from owner/branch` + títol al cos | Número, autor, branca i títol de cada PR fusionada sense API. |
| `plan/units/*.toml` | dos *worktrees* (estat d'ahir i d'avui) | Estat de cada unitat del port. |
| `plan/upstream-issues/*.md` | nom de fitxer = id, primera línia = títol | Defectes del C++ de SMLib trobats pel port. |
| `plan/findings/*.md` | fitxers nous | Desacords Rust/C++ i notes de harness. |
| `reports/solidcraft-cases.json` | veredicte per cas | Els casos reals de SolidCraft que el kernel passa o falla. |
| `crates/solidcore/src/kernel.rs` | `pub struct UpstreamFixes` | Cada correcció opcional és un flag; els nous surten amb el seu comentari. |
| `scripts/upstream-pin.env` | `UPSTREAM_VERSION`, `UPSTREAM_COMMIT` | Si el pin es mou, cal tornar a passar la bateria. |
| API de GitHub, crates.io | opcional, best-effort | Issues/PR obertes i versions. Si no hi ha xarxa, el digest ho diu. |

El dia és UTC: `start` és l'últim commit de `main` (`--first-parent`) abans de les 00:00 i
`end` l'últim abans de les 24:00. Els commits del dia són `start..end`. Dues execucions sobre el
mateix repositori donen el mateix digest.

## Ús

```sh
git clone --filter=blob:none https://github.com/tangency-labs/solidcore.git ~/sc/solidcore
python3 digest.py run --repo ~/sc/solidcore                      # ahir (UTC)
python3 digest.py run --repo ~/sc/solidcore --date 2026-11-02    # un dia concret
python3 digest.py backfill --repo ~/sc/solidcore --from 2026-10-12 --to 2026-11-02
python3 digest.py site                                           # public/index.html
```

Només cal Python 3.11+ i git; cap dependència. `--no-network` salta GitHub i crates.io.
Abans de tornar a executar un dia, fes `git -C ~/sc/solidcore fetch origin main:main` (o `pull`)
perquè el clon tingui els commits.

## Automatització

`.github/workflows/digest.yml` corre cada dia a les 05:37 UTC: clona solidcore, genera el digest
d'ahir, fa commit de `data/` i `digests/` i publica `public/` a GitHub Pages. Es pot llançar a mà
(*Run workflow*) amb un dia concret o un interval (`backfill_from`).

Per activar-ho un cop pujat el repositori: *Settings → Pages → Source: GitHub Actions*.

## Estructura

```
digest.py            CLI (run, backfill, site)
digest/gitlog.py     finestra del dia, commits, PR fusionades, worktrees
digest/classify.py   mòdul per ruta, tipus per prefix, llista de vigilància
digest/plan_diff.py  diffs de plan/, reports/, kernel.rs, waivers, pin
digest/github_api.py API de GitHub i crates.io (opcional)
digest/collect.py    ajunta tot en un diccionari (data/<dia>.json)
digest/render.py     JSON -> Markdown (digests/<dia>.md)
digest/site.py       Markdown -> HTML, index amb gràfics SVG (public/)
watchlist.toml       temes de vigilància i casos d'arque
```

## Limitacions conegudes

- La classificació per mòdul mira els fitxers tocats; un commit que toca només tests
  d'integració surt a "tests d'integració del kernel" encara que provi arrodoniments.
- La vigilància busca text a títols i cossos de commit: si un commit parla de *seam* de passada,
  surt. Ajusta `watchlist.toml` (hi ha `case_sensitive`) si una regla fa massa soroll.
- Els commits `claim:` són buits (reserven feina per a un agent): es compten a part i no entren
  als mòduls.
- Si el repositori canvia l'estructura de `plan/`, caldrà retocar `plan_diff.py`.
