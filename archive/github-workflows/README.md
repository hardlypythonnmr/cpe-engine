# Archived workflows

The per-channel publishing and dispatch Actions, moved here on 25-nov-2026 when the single publishing line
(`.github/workflows/publicar.yml`, `earn/naos/motor/publicar.py`, registry `earn/naos/motor/canales.json`) passed its
dry tests (`earn/naos/motor/prueba_publicar.py`). GitHub does not run files outside `.github/workflows/`, so nothing
here can fire. They are kept whole for how things were built. Their content is not a rule.

| File | What it did | Where it lives now |
|---|---|---|
| `naos-reel.yml` | Reel, image, carousel, story on Instagram (NAOS and DD), with the waits | `publicar.yml` modo publicar, donde instagram |
| `mercury-publicar.yml` | DD Shorts upload and Instagram dispatch, 5 crons | `publicar.yml` modo publicar or programar, canal deedee |
| `naos-despacho-media.yml`, `naos-ronda-sombra.yml` | dispatchers on dated or 3-hourly crons | removed: Lauren dispatches on N's word (PUBLICAR.md) |
| `naos-aprobar.yml`, `naos-avisar.yml` | the GitHub issue approval and the ping to N | removed: N approves in conversation, `aprobar.py mesa` |
| `dd-bajar.yml` | take DD Shorts private | `publicar.yml` modo retirar |
| `dd-mover-hora.yml` | move a DD Short's time | `publicar.yml` modo mover |
| `dd-perfil.yml` | DD YouTube and Page profile | `publicar.yml` modo perfil |
| `dd-cuenta.yml`, `naos-fb-prueba.yml` | account and token probes | `publicar.yml` modo comprobar |
| `fb-pagina.yml` | Facebook Page posts every 2 h | `publicar.yml` donde facebook (off in canales.json for now) |

`earn/naos/motor/aprobar/prueba_flujos.py` and `prueba_avisar.py` read these archived files.
