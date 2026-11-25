# PUBLICAR: how Lauren calls the publishing line

One line for both channels. The channel is an input. Nothing posts, schedules, takes down or edits a profile any
other way. Lauren runs it only on N's word, one ask at a time.

| Part | Path |
|---|---|
| The registry: accounts, handles, secret and variable NAMES, Pages host, valve | `earn/naos/motor/canales.json` |
| The entry point (all the steps) | `earn/naos/motor/publicar.py` |
| The Action (by hand only, no cron) | `.github/workflows/publicar.yml` |
| Its dry tests (in the battery) | `earn/naos/motor/prueba_publicar.py` |
| The ledger of live runs | `earn/naos/medicion/publicar.csv` |
| The old per-channel Actions (do not run) | `archive/github-workflows/` |

Steps of every run, in order: validate, valve, N's approval, keys, host media on Pages, claim, publish or schedule,
record. A failing check stops the run before anything is written.

## 1. Two ways to call it

**From the Action** (keys live in the repo secrets):

```
gh workflow run publicar.yml -R hardlypythonnmr/cpe-engine \
  -f slug=<slug> -f canal=<naos|deedee> -f donde=<youtube,instagram,facebook> \
  -f cuando=<now|2026-11-25T21:00:00Z> -f modo=<modo> -f seco=true
```

**From a session** (keys in the session environment):

```
python3 earn/naos/motor/publicar.py --slug <slug> --canal <naos|deedee> --donde <...> --cuando <...> --modo <modo>
```

From a session, a live Instagram or Facebook post also needs a checkout of the channel's Pages repo (NAOS:
`hardlypythonnmr/naos`; Dee Dee: the repo in `DD_PAGES_REPO`) at `./sitio`, or at the path in `PUBLICAR_SITIO`. The
Action makes that checkout itself.

The rule for both: run it dry first (`seco=true`, or no `--de-verdad`). Show N what it says. Run it live
(`-f seco=false`, or `--de-verdad`) only on his word. A dry run exits 0 when the live run would go, and 3 when a check
would stop it; the output names every check (`ok` or `NO` with the reason) and prints the exact commands.

## 2. Before the first live run of a channel

| What | Who | How |
|---|---|---|
| Open the valve | N | repo variable `PUBLICAR_NAOS` or `PUBLICAR_DEEDEE` = `on` (Settings > Secrets and variables > Actions > Variables). Off or unset stops every write mode |
| Approve the piece in conversation | Lauren, with N's literal words | `python3 earn/naos/motor/aprobar/aprobar.py mesa <slug> --decision aprobar --version <n> --hash <hash_contenido from estado.json> --decidido-utc <ISO UTC> --cita "<N's words>" --seco`, then the same without `--seco`. The line accepts only this row (via mesa). See `earn/naos/motor/aprobar/LEEME-MESA.md` |
| Keys present | N | the secret names below. Values never go in chat or in a file |

## 3. The cases

`seco=true` everywhere below; repeat with `seco=false` on N's word. `S` is the slug.

| Case | Command (Action) | Secrets it needs (names) | Variables |
|---|---|---|---|
| NAOS Reel now | `-f slug=S -f canal=naos -f donde=instagram -f modo=publicar` | `INSTAGRAM_TOKEN`, `NAOS_PAGINA_TOKEN`; `YOUTUBE_API_KEY` optional | `PUBLICAR_NAOS` |
| Dee Dee Reel now | `-f slug=S -f canal=deedee -f donde=instagram -f modo=publicar` | `DD_INSTAGRAM_TOKEN`, `DD_PAGINA_TOKEN` | `PUBLICAR_DEEDEE`, `DD_PAGES_REPO`, `DD_PAGES_BASE` |
| Image, carousel or story | same as the Reel; the format comes from `pieza.json` `canales` (`["imagen"]`, `["carrusel"]`, `["historia"]`) | same as the Reel | same |
| YouTube Short | `-f slug=S -f canal=<c> -f donde=youtube -f modo=programar -f cuando=<the approved time>` | NAOS: `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REFRESH_TOKEN`. Dee Dee: `DD_OAUTH_CLIENT_ID`, `DD_OAUTH_CLIENT_SECRET`, `DD_OAUTH_REFRESH_TOKEN` | valve |
| YouTube medium or long | as the Short; `pieza.json` carries `formato` (`medio` or `largo`) and `familia` | as the Short | valve |
| Short and Reel of one piece | `-f donde=youtube,instagram` | both sets | valve (and Pages vars for Dee Dee) |
| Instagram at a time N gives | `-f donde=instagram -f modo=programar -f cuando=<ISO>` prints the one-off dispatch; see section 4 | as the Reel, at the time it fires | valve |
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
  minutes early and refuses earlier). For a later time, see section 4.
- **Facebook**: never scheduled by the line; fire `modo publicar` at the time, as for Instagram.

## 4. Instagram at a time: the one-off dispatch

`modo programar` with `donde=instagram` prints both options with the exact command. Never a standing cron.

**A. A Claude scheduled task (preferred).** Lauren creates a one-shot scheduled task (send_later, or a task with
`run_once_at`) at N's time that runs:

```
gh workflow run publicar.yml -R hardlypythonnmr/cpe-engine -f slug=S -f canal=<c> -f donde=instagram \
  -f cuando=<ISO> -f modo=publicar -f seco=false
```

**B. A one-off cron line.** From a session (an Action cannot write workflow files):

```
python3 earn/naos/motor/publicar.py --modo programar --slug S --canal <c> --donde instagram --cuando <ISO> --cron --de-verdad
```

It writes `.github/workflows/publicar-una-vez-S.yml`: one cron for that minute, day and month, a guard on the year,
one dispatch of `publicar.yml`, then `gh workflow disable` of itself. Lauren commits and pushes it. After it fired,
Lauren removes it: `python3 earn/naos/motor/publicar.py --quitar-cron S`, then commit and push.

Either way, the run at the time goes through every step again (valve, approval, keys, claim). If N changes his mind
before the time: cancel the scheduled task (A) or remove the file (B).

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

- NAOS YouTube from the Action stops at the keys step: `GOOGLE_OAUTH_*` are not cpe-engine secrets yet. From a session
  that holds them it works.
- Facebook is off for both channels in `canales.json` (`activo: false`, org v3). Turning it on is one line there, by PR,
  on N's word. NAOS has no Page id and `NAOS_FB_TOKEN` failed its probe on 23-nov.
- A piece whose `pieza.json` `canales` has both `short` and `reel`: `ig.py` still requires the Short to be public before
  the Reel (an old rule, PROD-08.7). For a Reel alone, the piece's `canales` is `["reel"]`.
- `aprobar.py mesa` needs the piece in `por-aprobar`, which today only `aprobar.py abrir` writes, and `abrir` opens a
  GitHub issue. The gate itself does not read the issue.
- The first comment (`fijar.py`) still checks the issue's preview comment, so it refuses pieces approved only via mesa
  until that check is ported.
- Comments (read, reply), measurement (`medir.py`, `dd-medir.yml`, `naos-ig-salud.yml`), voice, music and render stay
  where they are; they do not post pieces.
