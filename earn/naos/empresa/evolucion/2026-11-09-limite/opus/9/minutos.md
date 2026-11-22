# Minutos de Actions al mes (30 días), antes y después de cada palanca

Opus 9, 12-nov-2026. Plan: 2.000 min al mes. Meta pedida: menos de 1.800 sin dejar de publicar nada. Fuente de lo medido: `scratchpad/minutos-nov.md`
(881 corridas, 1 a 12-nov 20:44Z, 11,86 días; cada corrida redondeada hacia arriba al minuto). Lo demás son supuestos, marcados con S.

## Resultado corto

La meta NO se alcanza con las cuatro palancas de este encargo: quedan ~3.280 min al mes en el modelo central, con DD encendida. Bajan
~1.275 min respecto a lo que quedaba después de #1068 (4.555), pero faltan ~1.480. Lo que pesa ahora es naos-reel (2.052 de 3.280, el 63 %).
La salida honesta para llegar a 1.800 está en la sección "Lo que falta".

## Supuestos (S)

- S1. NAOS: 13 piezas al día por naos-reel (promedio de publicados.csv del 10 al 12-nov: 6,5 Reels, 3 historias, 1,5 carruseles, 2 imágenes).
  De esas, ~5 al día no traen video (carruseles de JPEG, imágenes, la mitad de las historias). Lo medido del 1 al 12-nov fue 10,2 corridas al día.
- S2. DD (Difficult Decision, días 8 a 30 de LINEA.md): 6 piezas al día por naos-reel (2 tachones, 2 historias, lámina, expediente), de las cuales ~3 sin video.
  Los Shorts de DD suben por mercury-publicar.yml, no por naos-reel.
- S3. naos-reel antes de #1068: 13,1 min por corrida (1.590 min / 121 corridas medidas). El paso LFS se comía 9,5 (run 43295572599). Después: 13,1 menos 9,5 = 3,6 min.
  No pude medir por paso (gh sin sesión en este contenedor): el resto de los 3,6 min es un promedio, no una medición.
- S4. apt de ffmpeg: ~0,7 min por corrida (supuesto, apt-get install con --no-install-recommends, de 30 a 60 s más el redondeo).
- S5. mercury-publicar.yml con el disparo nuevo: ~6 corridas al día (una por hora con algo en ventana) x ~1,3 min, más 5 respaldos de ~1 min = ~13 min al día.
  Antes: 48 corridas al día x 1 min = 1.440 (lo dice el propio yml).
- S6. naos-aprobar: lo medido es 785 min en 12 días, 480 de 490 corridas por comentarios de sesiones. Con #1068 solo corren los comentarios de N y los
  despachos: ~190 + ~50 = ~240 al mes (la cuenta del encabezado del workflow).
- S7. naos-ronda-sombra: nominal 8 corridas al día x 1,9 min (17 min / 9 corridas medidas). GitHub entregó menos de las 8 (9 en ~2 días), así que 456 es un techo.
- S8. naos-avisar: 82 min en 12 días (67 corridas ejecutadas, 80 saltadas a 0 min) = 207 al mes. dependabot: 29 min en 12 días (8 corridas).
- S9. Fijos medidos y proyectados a 30 días: maestria-tablero 33, naos-ig-salud 30, dd-cuenta ~20 (a mano), naos-palabras ~4.

## La cuenta

| Paso | naos-reel NAOS | naos-reel DD | mercury-publicar | naos-aprobar | naos-avisar | sombra | dependabot | otros | Total |
|---|---|---|---|---|---|---|---|---|---|
| Medido 1 a 12-nov, a 30 días (sin DD) | 4.017 | 0 | 3 | 1.986 | 207 | (43) | 73 | 87 | ~6.420 |
| Antes de las palancas, con DD encendida (modelo) | 5.109 | 2.358 | 1.440 | 1.986 | 207 | 456 | 73 | 87 | ~11.716 |
| Después de #1068 (LFS por smudge, aprobar sin sesiones) | 1.404 | 648 | 1.440 | 240 | 207 | 456 | 73 | 87 | ~4.555 |
| + palanca 1: mercury-publicar sin cron de 30 min | 1.404 | 648 | ~390 | 240 | 207 | 456 | 73 | 87 | ~3.505 |
| + palanca 2: naos-reel sin ffmpeg si no hay video (-168) | 1.299 | 585 | ~390 | 240 | 207 | 456 | 73 | 87 | ~3.337 |
| + palanca 3: dependabot monthly (73 a ~18) | 1.299 | 585 | ~390 | 240 | 207 | 456 | 18 | 87 | ~3.282 |
| + palanca 4: naos-avisar (sin cambio, ver abajo) | igual | igual | igual | igual | 207 | igual | igual | igual | ~3.282 |

Cuenta de cada celda: naos-reel NAOS = 13 x 3,6 x 30 = 1.404 (antes de #1068 13 x 13,1 x 30 = 5.109); DD = 6 x 3,6 x 30 = 648 (6 x 13,1 x 30 = 2.358);
palanca 2 = (5 + 3) piezas sin video x 0,7 x 30 = 168, repartido 105 y 63; mercury = 13 x 30 = ~390.

## Qué hizo cada palanca

1. mercury-publicar sin cron de 48 corridas al día (-1.050 al mes). La despiertan `programador.py --disparar-mercury` desde la operadora (paso M, no gasta
   minutos de Actions) y desde la ronda sombra, solo si hay una pieza de Mercury en ventana. Queda un respaldo de 5 corridas al día en las horas de DD
   (13:58, 16:58, 18:28, 19:58, 21:58 UTC, justo antes de 14:00, 17:00, 18:30, 20:00 y 22:00) por si la operadora cae: 150 min al mes. Detalle:
   la ronda de las :57 ve lo que sale a las :00 y de :10 a :15; lo de las :30 (lámina de las 18:30) no entra en esa ventana (+20 min), por eso el
   respaldo de las 18:28 existe. El Short de cifra viva (en su última hora) sí lo ve la ronda de las 17:57 para el de las 18:30.
   La compuerta no cambió: subir.py, ig.py y la fila de aprobación siguen igual, y el carril de cifra viva relee la cifra como antes.
2. naos-reel no instala ffmpeg si la pieza no trae video (-168 al mes, supuesto S4). `accion_reel.py necesita-ffmpeg` lo decide por pieza.json
   (historia con .mp4/.mov, carrusel con láminas .mp4/.mov, Reel); sin pieza.json instala, por seguridad. El paso se movió después del checkout,
   sin perder el rastro de "Sin ffmpeg". Un carrusel con lámina de video sigue instalándolo (ffprobe lo revisa).
3. dependabot "monthly" (-55 al mes).
4. naos-avisar: no se puede filtrar el disparo. `on: issues: labeled` no acepta filtro por etiqueta (el filtro por nombre solo existe dentro del job:
   `if`, que ya está y deja las 80 corridas ajenas en 0 min). Las 67 que sí corren son las etiquetas por-aprobar y tu-semana, y es el aviso que
   le llega a N al celular. Costo ~207 al mes. Se puede bajar solo si N acepta otro aviso (por ejemplo, uno por tanda y no por pieza).

## Lo que falta (decisiones de N, no las apliqué)

Para pasar de ~3.280 a menos de 1.800 hacen falta ~1.480 min. Candidatos, en orden de peso:
- naos-reel es el 63 %. Cada minuto por corrida vale ~570 min al mes (19 piezas x 30). Bajar de 3,6 a 2,5 min por corrida ahorra ~630. Hace falta medir
  los pasos de una corrida real (el workflow guarda `pasos.log`; `gh run view --log` cuando se desbloqueen las Actions) para ver cuánto es espera
  hasta la hora (se cobra dormida: despachar a las :55 una pieza de las :00 duerme 5 a 9 min), cuánto Meta y cuánto el checkout.
- Repo público: los minutos son gratis. Es el único cambio que lleva todo a 0 sin tocar lo que se publica.
- Ronda sombra cada 6 h en vez de 3 h (-228) o apagada con la operadora viva (-456): cambia la decisión D-415 de N.
- Quitar el respaldo de Mercury (-150): la operadora y la sombra siguen despertándola.
- Menos piezas al día por naos-reel (cada pieza vale ~3,6 x 30 = ~108 al mes), por ejemplo carruseles e imágenes de la grilla.
- naos-avisar por tanda (-100 a -200).
Con la sombra a 6 h, sin respaldo y 2,5 min por corrida en naos-reel quedaría en ~2.280: todavía por encima. Sin repo público o menos piezas no llega.

## Qué no medí

Sin acceso a la API de Actions en este contenedor, los tiempos por paso de naos-reel y de mercury-publicar son supuestos (S3, S4, S5). Hay que
re-medir con la primera semana de corridas: `gh run list --workflow naos-reel.yml` y los minutos por corrida.
