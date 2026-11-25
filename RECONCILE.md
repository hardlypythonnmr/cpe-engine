# RECONCILE: engine drift between n-system and cpe-engine

Step 1 of `content-production-enterprise/MOVE-PLAN.md` (in n-system). Branch `cpe/reconcile`, started from `1117914` on 24-nov-2026.

## How the newer side was decided

cpe-engine has one squashed commit, so its own history cannot say what changed after the copy. n-system keeps full history. For each drifted file I searched n-system's history for the version that is closest to the engine's copy (the fork base, 19-nov 17:01Z to 19:56Z). Then:

- changes only from base to engine: the engine is newer, keep the engine;
- changes only from base to n-system: n-system is newer, port to the engine;
- changes on both sides: three-way merge (`git merge-file`) on that base.

## Decisions, one line per file

All paths are under `earn/naos/motor/`.

| File | Side kept | Reason |
|---|---|---|
| `aprobar/aprobar.py` | merged | both changed; n-system adds the `mesa` order (`fallas_mesa`, `aprobar_mesa`, CLI, D-512 guard), engine keeps its post-fork edits; clean merge |
| `aprobar/registro.py` | merged | both changed; n-system adds the via-mesa row (`es_mesa`, `falla_fila_mesa`, `leyenda_mesa`) and the gate check; clean merge |
| `aprobar/prueba_aprobar.py` | merged | both changed; n-system adds `TestViaMesa` (27 tests, pass); clean merge |
| `aprobar/LEEME-MESA.md` | n-system (new) | only in n-system; the doc of the approve-in-conversation path |
| `aprobar/LEEME.md` | n-system | only n-system changed it: two lines pointing to `LEEME-MESA.md` |
| `aprobar/copia.py` | engine | only the engine changed it after the fork |
| `aprobar/programador.py` | engine | only the engine changed it (respaldo-cron, mover-hora) |
| `aprobar/prueba_plantilla.py` | engine | only the engine changed it |
| `aprobar/prueba_programador.py` | engine | only the engine changed it |
| `aprobar/subida-directa.txt` | engine | only the engine changed it (G15 result notes) |
| `calendario.py` | engine | only the engine changed it |
| `ciclo.py` | n-system | only n-system changed it: drops `rojo-respeto.md` (D-615) |
| `cola_fusiones.py` | engine | only the engine changed it |
| `comentarios/comentarios.py` | engine | only the engine changed it |
| `comentarios/lecturas.csv` | engine | ledger; only the engine appended after the fork |
| `comentarios/registro-rondas.csv` | engine | ledger; only the engine appended after the fork |
| `comentarios/registro.csv` | engine | ledger; only the engine changed it |
| `comentarios/reglas-dd.json` | n-system | only n-system changed it: `respeto.md` note replaced by platform rules (D-615) |
| `comentarios/reglas.json` | n-system | only n-system changed it: same D-615 wording |
| `contexto_hoy.py` | n-system | only n-system changed it: section name "Reglas de plataforma" (D-615) |
| `dd_perfil.py` | engine | engine has the newer `DD_PAGES_BASE` handling; n-system's only extra is `--banner c`, whose image (`banner-c.png`) is not in the engine, so it is left for later |
| `instagram/accion_reel.py` | engine | only the engine changed it |
| `instagram/errores.csv` | engine | ledger; only the engine changed it |
| `instagram/fb-publicados.csv` | engine | ledger; only the engine changed it |
| `instagram/ig.py` | engine | only the engine changed it (`_en_feed`, `naos-fb`) |
| `instagram/prueba_ig.py` | engine | only the engine changed it |
| `instagram/publicados.csv` | engine | both grew; the engine (2,304 lines) already has all 26 rows n-system added after the fork (checked by file hash) |
| `kanban_sync.py` | engine | only the engine changed it |
| `medir.py` | engine | only the engine changed it: adds `--una-al-dia`; n-system's copy is the older one |
| `prueba_claridad.py` | n-system | only n-system changed it: also checks the director skills |
| `prueba_dd_perfil.py` | engine | only the engine changed it |
| `prueba_lema.py` | n-system | only n-system changed it: lemma date moved to 19-nov |
| `texto_como_imagen.py` | n-system | only n-system changed it: D-615 wording |
| `uso_sensor.py` | engine | only the engine changed it |
| `voces/elevenlabs/voces.json` | n-system | only n-system changed it: adds the `naos-casa` voice entry |

`medir.py` reconciled: the engine copy is canonical. When n-system's copy moves to `content-production-enterprise/infrastructure/engine/` (move step 3g), it should be replaced by this engine version, then get the path fixes the plan lists.

Files only in the engine (`fb_ronda.py`, `instagram/audio_*.py`, `banco_audio.py`, `ritmo_audio.py`, `aprobar/respaldo_cron.py` and their tests) stay. Files only in n-system that belong to production (`casa/`, `kit/` judges, `voces/` tools, `tareas.py` and others) are not publishing code and are not ported.

## Old approved queued pieces (to retire)

Found with the engine's own dry listing (`programador.tocan` and `shorts_tocan`, read only, clock 2026-11-24T22:00:00Z). Same four as CAPABILITIES.md section 1.3. All four are `estado = aprobado` today:

| Slug | Title | Version, issue, batch | Channels, sale_utc |
|---|---|---|---|
| `dd-2026-11-24-f6-antes-bp` | BP Oil Spill From Space: Before, After and the $5.5B Penalty | v1, #121, `dd-2026-11-21-tanda8` | short+reel, 2026-11-24T21:30:00Z |
| `family-dinner-receipt` | Family dinner | v1, #54, `instagram-23-24-nov` | imagen, 2026-11-24T21:35:00Z |
| `dd-2026-11-24-marriott-historia` | Marriott (Mar 2025): $21.9 million CEO total pay, $46,211 median pay. The math. | v2, #16, `dd-reserva-1730-b` | historia, 2026-11-24T22:00:00Z |
| `not-avoidant-hard-to-reach-moving` | Not avoidant. Just very, very hard to reach. | v1, #108, `piloto-corona-2428` | short+reel, 2026-11-24T22:15:00Z |

Status: retired on 25-nov-2026 (state only), with `dd-2026-11-24-marriott-expediente`. See step 2 in the log below.

## Step log

### Step 1 (cpe-engine), 24-nov-2026

- Moved: nothing moved (no `git mv` in this step). Ported into the engine: 1 new file (`aprobar/LEEME-MESA.md`), 3 files three-way merged, 9 files taken from n-system. 22 drifted files kept on the engine side. 34 drifted files reviewed in total (the plan said about 22 `.py`; the count here includes ledgers, JSON and docs).
- Refs rewritten: 0 (the engine keeps its `earn/naos/` layout, plan step 9).
- Checks:
  - `python3 earn/naos/motor/bateria.py --json` before: 52 OK, 22 FALLA, 4 SALTA. After: 52 OK, 22 FALLA, 4 SALTA, the same tests with the same notes. The 22 failures exist on `main` before this branch (files missing from the engine copy such as `kit/tramos/naos_tramos.js`, `casa/lib/lema.py`, `empresa/estrategia/...`, and tests that need `gh`). The plan's "bateria green" was not true at the start; the bar used here is "no new failure".
  - `prueba_aprobar.py TestViaMesa`: 27 tests OK. `prueba_aprobar.py` overall: 292 tests, 1 failure (`test_c7_alone_sola...`), the same one that fails on `main`.
  - Some engine tests write `investigacion/datos/cuota.json` and `investigacion/datos/<date>/`; those generated files were restored after each run and are not committed.
  - No non-dry publish or dispatch was run. No GitHub, YouTube, Instagram or Facebook call was made.
- Deviations from the plan:
  - Retiring the 4 pieces was not done. The engine's `aprobar.py retirar` refuses them (its ledger believes the two Shorts already went out by `publishAt`, which is the reason it will not touch them), and `retirar` also comments on and labels GitHub issues. Applying the same state change by hand (`estado = vetada`, `retirado_utc`, `retirado_por`, rows' `vence_utc` set to now, one row in `medicion/decisiones-sistema.csv`) without GitHub was denied by the session's permission system, so it was not attempted another way. N or Lauren must run it with explicit approval.
  - `aprobar/TOKEN-SESION.md` (an n-system-only proposal note from before the fork) was not ported; it stays in n-system and goes to the archive with the rest.
  - `LEEME-MESA.md` cites `empresa/mesa/ARTEFACTO-APROBACION.md`, which lives in n-system only (moving to `content-production-enterprise/history/mesa/` in step 3a). Left as written.
- Left for later:
  - Retire the 4 pieces above (needs approval). Also note `dd-2026-11-24-marriott-expediente`: the listing held it only because its neighbour was in the same minute ("rescate frenado"); it is approved and queued too.
  - `dd_perfil.py --banner c` and the DD profile assets (`empresa/duplicar/canal-lucro/c2/identidad/perfil/`: `banner-c.png`, newer `textos.json`, `foto-d.png`, `portada-c.png` differ). These are channel identity, still pending N's choices per n-system's own note; not engine code.
  - n-system's `medir.py` should take this engine version when it moves (step 3g).
  - `.claude/settings.json` in this repo was not edited (stale allow rules for `copia.py` and `fusionar.sh` are harmless, per N).
  - Not pushed. The plan expects one PR in cpe-engine merged by N.

### Step 2 (cpe-engine), 25-nov-2026: the single publishing line

- New: `earn/naos/motor/canales.json` (registry), `earn/naos/motor/publicar.py` (the line), `.github/workflows/publicar.yml`
  (workflow_dispatch only), `earn/naos/motor/prueba_publicar.py` (dry tests, in the battery), `PUBLICAR.md` (how Lauren
  calls it), `.claude/settings.propuesta.json` (proposal; `settings.json` untouched).
- `ig.py` and `youtube/ytapi.py` take the handles from the registry (Dee Dee: @artdirection_dd, @debtdesiredirection).
- Moved (`git mv`): 12 per-channel publishing Actions to `archive/github-workflows/`, after the line's dry tests passed.
- Retired (state only, no GitHub, no network): the 4 pieces above and `dd-2026-11-24-marriott-expediente`; `estado.json`
  `vetada` with `retirado_utc` and `retirado_por` "N via Lauren, 24-nov"; one row in `decisiones-sistema.csv`. Their rows
  in `publicados.csv` had already expired (00:00Z to 01:15Z on 25-nov) and were left as they were.
- Battery without keys or network: before 49 OK, 24 FALLA, 4 SALTA; after 51 OK, 23 FALLA, 4 SALTA. No new failure
  (`prueba_disco.py` fails the same way at `a1e7e20` in this container).

