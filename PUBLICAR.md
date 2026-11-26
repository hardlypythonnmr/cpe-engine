# PUBLICAR: how Lauren calls the publishing line

One line for both channels. The channel is an input. Nothing posts, schedules, takes down or edits a profile any
other way. Lauren runs it only on N's word, one ask at a time.

| Part | Path |
|---|---|
| The registry: accounts, handles, secret and variable NAMES, Pages host, valve | `earn/naos/motor/canales.json` |
| The entry point (all the steps) | `earn/naos/motor/publicar.py` |
| The Action (by hand only, no cron) | `.github/workflows/publicar.yml` |
| Its dry tests (in the battery) | `earn/naos/motor/prueba_publicar.py` |
| The approval and post ledger (N's rows, links of what went out) | `earn/naos/motor/instagram/publicados.csv` |
| The ledger of the line's live runs (created on the first live run) | `earn/naos/medicion/publicar.csv` |
| The old per-channel Actions (do not run) | `archive/github-workflows/` |
| The daily read-only measurement of both channels (posts nothing) | `.github/workflows/medir.yml`, `earn/naos/motor/medir_diario.py` |

**Status on 25-nov-2026:** `publicar.yml` is on `main` (merged in #137), so it can be dispatched. N decided the same day
(25-nov-2026): a piece goes out with ONE command from a session (section 1), Instagram at a time goes by the
self-removing one-off cron (section 4), and both channels are measured with one daily read (`medir.yml`).

Steps of every run, in order: validate, valve, N's approval, keys, host media on Pages, claim, publish or schedule,
record. A failing check stops the run before anything is written.

## 1. Two ways to call it

**From the Action** (keys live in the repo secrets). The session command dispatches it by itself for the platforms whose
keys the session lacks; by hand it is the fallback. The Action checks out `main`, so it reads the piece, `estado.json`
and the approval row from `main`:

```
gh workflow run publicar.yml -R hardlypythonnmr/cpe-engine \
  -f slug=<slug> -f canal=<naos|deedee> -f donde=<youtube,instagram,facebook> \
  -f cuando=<now|2026-11-25T21:00:00Z> -f modo=<modo> -f seco=true
```

**From a session** (the route Lauren uses; decided by N on 25-nov-2026):

```
python3 earn/naos/motor/publicar.py --slug <slug> --canal <naos|deedee> --donde <...> --cuando <...> --modo <modo>
```

One command for every platform in `--donde`. For each platform the line looks at the environment: when that platform's
keys are present (names in `canales.json`), it runs here; when they are not, it goes to `publicar.yml` in one dispatch
(`gh workflow run publicar.yml -R hardlypythonnmr/cpe-engine -f slug=... -f canal=... -f donde=<those platforms> -f cuando=...
-f modo=... -f seco=...`, the same values as the session run). The output says which platform runs where. Before
anything runs or is dispatched, the session checks the valve and N's approval for every platform; the dispatched run
checks them again. Local platforms run first; if one fails, nothing is dispatched. Dry (no `--de-verdad`) prints the
dispatch command with `seco=true` and never runs it. Each platform goes one way only, and the claim tags
(`reel-claim/<slug>-v<N>` for Instagram, `reel-claim/<slug>-<platform>-v<N>` for the others) are the same tags on the
same remote whichever route runs it, so a session and an Action can never both post one platform. Inside the Action
nothing is dispatched: a missing key stops the run.

The dispatched run checks out `main`, so the piece, `estado.json` and N's approval row must be on `main` first.

The valve from a session: `PUBLICAR_NAOS` and `PUBLICAR_DEEDEE` are repo variables, so they are not in a session's
environment. `publicar.py` reads the variable read-only with `gh api repos/hardlypythonnmr/cpe-engine/actions/variables/<name>`
when it is not set in the environment, and prints what it read. Never export the valve by hand in a session: that
sidesteps N's setting. If `gh` cannot read it (the Claude session proxy answers 403 on `actions/variables`), use section 7.

From a session, a live Instagram or Facebook post also needs a checkout of the channel's Pages repo (NAOS:
`hardlypythonnmr/naos-site`, renamed from `naos` on 25-nov-2026; Dee Dee: the repo in `DD_PAGES_REPO`) at `./sitio`, or at the path in `PUBLICAR_SITIO`. The
Action makes that checkout itself.

The rule for both: run it dry first (`seco=true`, or no `--de-verdad`). Show N what it says. Run it live
(`-f seco=false`, or `--de-verdad`) only on his word. A dry run exits 0 when the live run would go, and 3 when a check
would stop it; the output names every check (`ok` or `NO` with the reason) and prints the exact commands.

## 2. Before the first live run of a channel

| What | Who | How |
|---|---|---|
| Open the valve | N | repo variable `PUBLICAR_NAOS` or `PUBLICAR_DEEDEE` = `on` (Settings > Secrets and variables > Actions > Variables). Off or unset stops every write mode |
| Put the piece in `por-aprobar` | Lauren | copy the piece to `earn/naos/cola/aprobar/<slug>/` (`pieza.json` and its files), then `python3 earn/naos/motor/aprobar/aprobar.py preparar <slug> --seco`, then without `--seco`. It writes `estado.json` (`por-aprobar`, version, `hash_contenido`, the per-channel hashes) from `pieza.json` and opens no issue. It refuses Fix revisions and a release time that already passed. Then commit the folder on the branch the line runs from and push the media with LFS (`git lfs push origin <branch>`). `abrir` (the GitHub issue) is the retired route |
| Approve the piece in conversation | Lauren, with N's literal words | `python3 earn/naos/motor/aprobar/aprobar.py mesa <slug> --decision aprobar --version <n> --hash <hash_contenido from estado.json> --decidido-utc <ISO UTC> --cita "<N's words>" --seco`, then the same without `--seco`. The line accepts only this row (via mesa). See `earn/naos/motor/aprobar/LEEME-MESA.md`. Without `--sin-git`, `mesa` pulls and pushes to `main` and refuses any other branch; the Action reads the rows from `main` |
| Keys present | N | the secret names below. Values never go in chat or in a file |

## 3. The cases

**Keys by route** (decided by N, 25-nov-2026: one route from a session). A session's environment holds `INSTAGRAM_TOKEN`,
`GOOGLE_OAUTH_*` and `YOUTUBE_API_KEY`; it does not hold `NAOS_PAGINA_TOKEN`, any `DD_*` key, `DD_PAGES_REPO` or
`DD_PAGES_BASE`. cpe-engine's secrets hold the Instagram and Dee Dee keys but not `GOOGLE_OAUTH_*`. So the session
command sends NAOS YouTube from the session and dispatches NAOS Instagram (`modo publicar`) and all of Dee Dee to the
Action, by itself. Nobody copies keys between the two.

The one command Lauren uses for a NAOS piece on both platforms (a Short and a Reel, at the time N approved):

```
python3 earn/naos/motor/publicar.py --slug S --canal naos --donde youtube,instagram --modo programar --cuando now --cron
```

Dry first; then the same with `--de-verdad` on N's word. YouTube is uploaded from the session, private with `publishAt`
= the approved time. Instagram gets the one-off cron (section 4) for 5 minutes after that time (the Reel waits for its
Short to be public). Then Lauren commits and pushes to `main`: `publicados.csv` (it carries the Short's link the Reel
needs), `medicion/publicar.csv` and `.github/workflows/publicar-una-vez-S.yml`. For a piece whose Instagram part goes
alone (a Reel without a Short, an image, a carousel, a story) and should go now: `--modo publicar`, and the Instagram part
is dispatched at once.

The table lists the Action form of each case; from a session the same flags (`--slug S --canal ... --donde ... --modo
...`) route by themselves. `seco=true` everywhere below; repeat with `seco=false` on N's word. `S` is the slug.

| Case | Command (Action) | Secrets it needs (names) | Variables |
|---|---|---|---|
| NAOS Reel now | `-f slug=S -f canal=naos -f donde=instagram -f modo=publicar` | `INSTAGRAM_TOKEN`, `NAOS_PAGINA_TOKEN`; `YOUTUBE_API_KEY` optional | `PUBLICAR_NAOS` |
| Dee Dee Reel now | `-f slug=S -f canal=deedee -f donde=instagram -f modo=publicar` | `DD_INSTAGRAM_TOKEN`, `DD_PAGINA_TOKEN` | `PUBLICAR_DEEDEE`, `DD_PAGES_REPO`, `DD_PAGES_BASE` |
| Image, carousel or story | same as the Reel; the format comes from `pieza.json` `canales` (`["imagen"]`, `["carrusel"]`, `["historia"]`) | same as the Reel | same |
| YouTube Short | `-f slug=S -f canal=<c> -f donde=youtube -f modo=programar -f cuando=<the approved time>` | NAOS: `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REFRESH_TOKEN`. Dee Dee: `DD_OAUTH_CLIENT_ID`, `DD_OAUTH_CLIENT_SECRET`, `DD_OAUTH_REFRESH_TOKEN` | valve |
| YouTube medium or long | as the Short; `pieza.json` carries `formato` (`medio` or `largo`) and `familia` | as the Short | valve |
| Short and Reel of one piece | from a session: `--donde youtube,instagram --modo programar --cuando now --cron` (above) | both sets | valve (and Pages vars for Dee Dee) |
| Instagram at a time N gives | from a session: `--donde instagram --modo programar --cuando <ISO> --cron`; see section 4 | none in the session; the Reel's set in the Action at the time it fires | valve |
| Move a scheduled YouTube video | `-f slug=S -f canal=<c> -f donde=youtube -f modo=mover -f cuando=<new ISO> -f cita="<N's words>"` | the channel's YouTube OAuth | valve |
| Take a YouTube video private (privacy change) | `-f slug=S -f canal=<c> -f donde=youtube -f modo=retirar -f cita="<N's words>"` | the channel's YouTube OAuth | valve |
| YouTube channel text or images | `-f canal=<c> -f donde=youtube -f modo=perfil -f campo=<banner\|descripcion\|palabras\|marca-de-agua> -f archivo=<repo path> -f cita="<N's words>"` | the channel's YouTube OAuth | valve |
| Dee Dee Facebook Page fields | `-f canal=deedee -f donde=facebook -f modo=perfil -f campo=<fb-about\|fb-description\|fb-foto\|fb-portada> [-f opcion=<letter>] -f cita="<N's words>"` | `DD_INSTAGRAM_TOKEN` (and `DD_PAGINA_TOKEN` for images) | valve, `DD_FB_PAGE_ID` |
| First comment of a piece | `-f slug=S -f canal=<c> -f donde=youtube,instagram -f modo=comentario` | the platform keys | valve |
| Facebook Page post | `-f slug=S -f canal=<c> -f donde=facebook -f modo=publicar` (image or carousel after Instagram; a Reel from Pages) | Dee Dee: `DD_INSTAGRAM_TOKEN`, `DD_PAGINA_TOKEN`. NAOS: `NAOS_FB_TOKEN` | valve; `DD_FB_PAGE_ID` or `NAOS_FB_PAGE_ID` |
| Check the accounts and tokens | `-f canal=<c> -f modo=comprobar -f seco=false` (read only; no valve) | the platform keys | none |

From a session, the same with flags: `--slug`, `--canal`, `--donde`, `--cuando`, `--modo`, `--cita`, `--campo`,
`--archivo`, `--opcion`, `--de-verdad`.

What each platform does underneath (library functions the line calls, not copies):
YouTube `youtube/subir.py` (private with `publishAt`), `aprobar.py mover-fecha`, `agente.bajar_shorts` with
`idiomas.quitar_fecha`, `youtube/canal.py`; Instagram `instagram/accion_reel.py` (`datos`, `pagina`, `publicar`) and
`instagram/ig.py`; Facebook `fb_pagina.py`, `dd_perfil.py`; first comment `comentarios/fijar.py`.

### How "cuando" works per platform

- **YouTube**: native scheduling. The video goes up private with `publishAt` = the time N approved (the row's
  `sale_utc`). `cuando=now` means that approved time. If `cuando` names another time, the line stops: use `modo mover`
  for an uploaded video, or approve again with the new time. `publishAt` must be 15 minutes ahead or more; for "right
  now", approve with a time about 20 minutes ahead.
- **Instagram**: no native scheduling. `modo publicar` posts at once (with `cuando` = an ISO time, it starts at most 10
  minutes early and refuses earlier). For a later time, see section 4. With `modo programar`, `cuando=now` means the
  approved time, plus 5 minutes when the piece also has a Short. For "now": `preparar` and `mesa` refuse a
  `sale_utc` that already passed, so set `pieza.json` `sale_utc` to now plus about 20 minutes before `preparar`, approve,
  then fire `modo publicar` before `sale_utc` plus the grace window (3 hours, `registro.GRACIA`), when the row expires.
- **Facebook**: never scheduled by the line; fire `modo publicar` at the time, as for Instagram.

## 4. Instagram at a time: the self-removing one-off cron

**Decided by N on 25-nov-2026** (SOURCE-OF-TRUTH section 10.3, option B): Instagram at a time N names goes by a one-off
cron file. Never a standing cron. From a session (an Action cannot write workflow files):

```
python3 earn/naos/motor/publicar.py --modo programar --slug S --canal <c> --donde instagram --cuando <ISO|now> --cron --de-verdad
```

It writes `.github/workflows/publicar-una-vez-S.yml`: one cron for that minute, day and month, a guard on the year,
one dispatch of `publicar.yml` (`modo publicar`, `seco=false`), then `gh workflow disable` of itself. It needs no key in
the session: the Action it dispatches holds them. Lauren commits and pushes it to `main` (a scheduled workflow runs
only from the default branch). GitHub can start a cron a few minutes late; the approval row stays valid for 3 hours after
the approved time. After it fired, Lauren removes it: `python3 earn/naos/motor/publicar.py --quitar-cron S`, then commit
and push.

The run at the time goes through every step again (valve, approval, keys, claim). If N changes his mind before the time,
Lauren removes the file (`--quitar-cron S`) and pushes.

## 5. What N does by hand (no API)

| What | Where |
|---|---|
| Instagram bio, name, profile photo | Instagram app > Edit profile |
| YouTube profile photo (avatar) | YouTube Studio > Customization > Branding |
| Delete or archive an Instagram post | Instagram app > the post > ... > Archive (or Delete) |
| Delete a Facebook Page post | Meta Business Suite |
| Pin a comment (Instagram or YouTube) | in the app or in Studio; the API only posts the first comment |
| Public or unlisted on YouTube (the line only takes private) | YouTube Studio > Content > Visibility |
| Open the valve, add or rotate a secret | cpe-engine Settings > Secrets and variables > Actions |
| Refresh the NAOS Instagram token (expires 2026-12-15) | `python3 earn/naos/motor/instagram/ig.py refrescar`, from a session, with N's go |

## 6. Known limits today

- NAOS YouTube from the Action stops at the keys step: `GOOGLE_OAUTH_*` are not cpe-engine secrets. The session command
  sends it from the session, so this only matters when someone dispatches the Action by hand.
- Facebook is off for both channels in `canales.json` (`activo: false`, org v3). Turning it on is one line there, by PR,
  on N's word. NAOS has no Page id and `NAOS_FB_TOKEN` failed its probe on 23-nov.
- A piece whose `pieza.json` `canales` has both `short` and `reel`: the code still requires the Short to be uploaded
  and public before the Reel (an old rule, PROD-08.7, that org v3 section 5 lists as stripped; the code removal is not
  ported yet). `accion_reel.py datos` needs the Short's `url_short` in `publicados.csv` (on `main`, for the Action), and
  `ig.py` checks the Short is public. That is why the one command uses `modo programar --cuando now --cron`: YouTube at
  `sale_utc`, Instagram 5 minutes later. `modo publicar --donde youtube,instagram` on such a piece stops at the Instagram
  checks (the Short is still private). Instagram and YouTube at the same minute need two pieces: one with `canales`
  `["short"]` and one with `["reel"]`, each approved by N.
- `aprobar.py mesa` needs the piece in `por-aprobar`: `aprobar.py preparar` writes it with no issue (section 2).
- The gate (`registro.verificar`) still accepts old VP and agent rows (`es_auto`) when `subir.py`, `ig.py` or
  `accion_reel.py` are called directly. `publicar.py` refuses any row that is not via mesa. Call the platform scripts only
  through the line.
- The first comment (`fijar.py`) still checks the issue's preview comment, so it refuses pieces approved only via mesa
  until that check is ported.
- Comments (read, reply), voice, music and render stay where they are; they do not post pieces. Measurement is one
  daily read-only run for both channels, `.github/workflows/medir.yml` (decided by N, 25-nov-2026), which replaced
  `dd-medir.yml` and `naos-ig-salud.yml` (archived).
- Dispatching from a session needs `gh` with permission to run workflows on cpe-engine. If the session's proxy refuses
  it, the line prints the GitHub MCP spec (section 7) and exits 4.

## 7. From a session whose proxy blocks the Actions API

Found 26-nov-2026: the Claude session proxy answers 403 on `actions/variables` (the valve) but lets `gh api` read runs
and job logs. Lauren's GitHub MCP tools can dispatch (`actions_run_trigger`, `run_workflow`) and list runs. So:

1. **Valve.** Run the session command dry. When the valve is unknown it prints `MCP run_workflow {...}` with `seco: "true"`.
   Lauren pastes that JSON into the MCP tool, takes the run id from the MCP run list, and runs the same command again with
   `--valvula-run <run id>`. The line reads that run's log itself (read only): the Action prints
   `valvula: PUBLICAR_NAOS=<value> (repo variable, read by this Action run)`. The run must be `publicar.yml`, dispatched on
   `main`, finished, of the same channel, and at most 3 hours old; nobody types the value. A live run writes a `valvula`
   row in `medicion/publicar.csv` with the run's link. Before this change reaches `main`, the old `ok  valvula` check line
   is read the same way, but only when the piece is on `main` (the line prints checks after it finds the piece).
2. **Dispatch.** Every dispatch step prints its `MCP run_workflow {...}` line next to the `gh workflow run` command: owner,
   repo, `workflow_id` `publicar.yml`, `ref` `main`, and the inputs of `publicar.yml` as strings. Live, if `gh` is refused,
   the line exits 4, writes `despacho-pendiente` in the ledger and prints the spec with `seco: "false"`. Lauren pastes it
   into the MCP tool on N's word, then records the run:
   `python3 earn/naos/motor/publicar.py --anotar-despacho <run id> --slug S --canal naos --donde instagram --modo publicar`
   (it checks the run is the live `publicar.yml` run of that piece; it posts nothing).
3. **NAOS YouTube** still runs from the session (`GOOGLE_OAUTH_*` are not cpe-engine secrets). If N adds the three
   secrets to cpe-engine, the whole piece can go through the MCP dispatch.

