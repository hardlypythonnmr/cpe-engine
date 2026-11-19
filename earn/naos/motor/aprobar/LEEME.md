# motor/aprobar

La aprobación de N por pieza, desde el celular (OPS-06.1, D-228, D-234). Un issue por pieza en n-system (privado) con la
vista previa dentro. **`ok` o 👍 de N en ese issue es su aprobación**; sin ella `ig.py publicar` y `subir.py` no publican.

| Archivo | Qué es |
|---|---|
| `aprobar.py` | `abrir`, `leer`, `registrar`, `procesar`, `version`, `cerrar`, `error`, `caducar`, `reprogramar`, `estado`, `tanda abrir`, `tanda version`, `retirar`, `piezas` (stdlib; `--simulado` para probar sin red) |
| `programador.py` | qué toca despachar: Reels (`naos-reel.yml`, lo hace la operadora) y Shorts (`--subir-shorts` corre `subir.py`) |
| `registro.py` | el libro `motor/instagram/publicados.csv`, la huella de cada canal y la compuerta que importan `ig.py` y `subir.py` |
| `agente.json`, `agente.py` | el agente aprobador (D-461): la regla, el dictamen por pieza, el freno y el registro. Ver "Agente aprobador" |
| `vp.json` | la regla de la aprobación del VP (D-274, D-322): desde cuándo, qué canales, regresos, horas de veto y exclusiones. La cambia solo un PR con el 👍 de N |
| `plantilla-issue.md` | los textos fijos de los issues (inglés) |
| `prueba_aprobar.py` | 202 pruebas sin red (más un repo git local con remoto), 43 de ellas de la tanda y 25 de la aprobación del VP (D-274): `python3 prueba_aprobar.py` |
| `mesa_estado.py`, `prueba_mesa_estado.py` | la sección "Mesa" de `estado-hoy.md` (la engancha `estado.py`): tandas sin 👍, posibles salidas fallidas, falta de cierre y lo que sale en 6 h; sin red, solo lectura, 10 pruebas: `python3 mesa_estado.py` |
| `prueba_retirar.py` | 14 pruebas sin red de `retirar` y de `retirar --bajar-shorts` (GitHub y YouTube simulados): `python3 prueba_retirar.py` |
| `cierre_auto.py` | cierra solo las piezas `aprobado` o `subiendo` que ya salieron (Short, medio o largo con `url_short` en el libro): `python3 cierre_auto.py [--seco] [--git] [--maximo N]` |
| `prueba_cierre_auto.py` | 31 pruebas sin red del cierre automático: `python3 prueba_cierre_auto.py` |
| `prueba_programador.py` | 52 pruebas sin red del programador (Reel y Short), de la guarda anti duplicado de `subir.py`, de la espera del veto de N (D-274) y de `--marca` (9): `python3 prueba_programador.py` |
| `../../../.github/workflows/naos-aprobar.yml` | corre `procesar` cuando N comenta (o cierra el issue), o por disparo de la ronda con uno o hasta 8 issues |
| `aprobar_varios.sh` | el cuerpo de `naos-aprobar.yml`: valida `ISSUE` y procesa cada issue en serie (LFS, `procesar`, `bajar-vetados`, guardar en main, avisos) |

## La pieza

`cola/aprobar/<slug>/` con `pieza.json`, `video.mp4`, `portada.jpg` y, después de `abrir`, `estado.json`.

```json
{"slug": "cierre", "titulo": "US close: stocks end mixed", "clave": "2026-10-19|close", "sale_utc": "2026-10-19T23:00:00Z",
 "caption": "US close: stocks end mixed. ...\n\nMore today: link in bio. Not financial advice.", "descripcion": "texto del Short",
 "sintetico": true, "alt": "alt text de la portada", "datos_utc": "2026-10-19T22:00:00Z",
 "canales": ["short", "reel"], "revisiones": [{"que": "Duration", "estado": "OK", "nota": "42 s"}]}
```

`estado.json`: `{slug, issue, version, estado, sale_utc, hash_contenido, hashes{short, reel}, comentario_vista_previa_id,
aviso_utc, aviso_canal (github), fix, aprobador}`. Estados: `por-aprobar`, `aprobado`, `subiendo`, `publicado`, `error`, `caducado` (son las etiquetas del issue).

## Contrato de `publicados.csv` (privado; una fila por aprobación y canal)

| Columna | Quién la escribe | Qué guarda |
|---|---|---|
| `slug`, `canal` (`short`, `reel`, `carrusel`, `imagen` o `historia`), `issue`, `version` | `registrar` | la pieza y la versión de la vista previa que N vio |
| `aprobado_por`, `aprobado_utc`, `via` (`reaccion` o `comentario`) | `registrar` | usuario de N y hora UTC de **su** toque (no la del proceso) |
| `cita` | `registrar` | `👍 de @<usuario> en <repo>#<n>, <fecha UTC>` (o `ok de @...`); es el `--ok` de `ig.py` |
| `hash` | `registrar` | sha256 de lo que sale en ese canal. Reel: mp4 + caption. Short: mp4 + título + descripción + miniatura. Carrusel: todas las láminas en orden + caption. Imagen: el archivo + caption. Historia: solo el archivo (la API no admite caption) |
| `sale_utc`, `vence_utc` | `registrar` | la hora aprobada; vence tres horas después (el Reel sale justo tras el Short) |
| `url_short`, `url_reel`, `contenedor`, `media_id`, `publicado_utc` | `subir.py`, `ig.py`, `cerrar` | lo que salió (`url_reel` también guarda el enlace del carrusel, la imagen o la historia) |

Las filas viejas de `ig.py` (`fecha_utc, slug, contenedor, media_id, permalink, ok_de_n`) se leen y se dejan, pero no tienen
huella: nunca habilitan una publicación.

## Reglas de la compuerta

1. Vale la fila de la **versión más alta** de ese slug y canal. Una versión nueva anula la anterior.
2. La huella de lo que se publica tiene que ser la de la fila: cualquier cambio en el video, el título, el texto o la portada la anula.
3. Vale hasta `vence_utc`. `subir.py` además exige que `--publicar-en` sea la hora que N aprobó.
4. El último gesto de N no manda: **cualquier comentario que no sea `ok`, o un 👎, frena esa versión** y el `ok` posterior no la aprueba;
   hace falta `version` (vista previa nueva, otro 👍). Si ya estaba aprobada, además anula las filas (`procesar` lo hace al instante con un comentario).
5. Solo cuenta el usuario `NAOS_APROBADOR` (variable del repo; por defecto el dueño), sobre la vista previa vigente.
   Los comentarios del propio script llevan `<!-- naos:... -->` y nunca cuentan como palabra de N.
6. Cifras del titular con más de 12 h cuando N aprueba: caduca y se pide un 👍 nuevo. Sin `datos_utc` en `pieza.json` hay un `Fix`
   ("Data time missing"), salvo `"sin_cifras": true`: toda cifra lleva su fuente y su hora.
7. El caption del Reel contiene el título del Short (mismo título y número); si no, `Fix` ("Reel title").

**Lente de cumplimiento (D-379), consultivo.** Cada vista previa lleva al final la sección "Compliance lens (advisory)" que arma `motor/lente/lente.py`
(salud, peligro, anunciantes, citas, elecciones, apuestas, repetitivo, con la política enlazada y la manera de decirlo). No es una regla de esta lista:
no entra en `fallas_de`, no suma a los `Fix`, no frena la tanda ni cambia texto. Si falla, o con `NAOS_SIN_LENTE=1`, la vista previa sale sin la sección.

## Carrusel

Pieza con `"canales": ["carrusel"]` y `"laminas": ["1.jpg", "2.jpg", ...]` (en orden, en la carpeta de la pieza), sin `video.mp4`.
Va sola (no se mezcla con `short` ni `reel`). Revisiones propias: de 2 a 10 láminas JPEG, 4:5 y del mismo tamaño, caption con el pie.
Paso a paso en `../instagram/LEEME.md`.

## Imagen

Pieza con `"canales": ["imagen"]` y `"archivo": "imagen.jpg"` (JPEG 1080x1350, 4:5, hasta 8 MB, no MPO), sin `video.mp4`. Va sola. El caption es
obligatorio y lleva "link in bio" (sin él, `Fix`), salvo las F5 "Una línea" con `"formato": "una-linea"` (D-361; ig.py recibe
`--formato una-linea`); hasta 2.200 caracteres y 30 hashtags. La huella es el hash del archivo más el
caption (`registro.hash_imagen`). `aprobar.py cerrar <slug> --imagen https://www.instagram.com/p/<id>/`. Paso a paso en `../instagram/LEEME.md`.

```json
{"slug": "faro", "titulo": "Lighthouse", "sale_utc": "2026-10-22T11:00:00Z", "canales": ["imagen"], "archivo": "imagen.jpg",
 "caption": "One light, many ships. Save it.\n\nMore today: link in bio.", "sin_cifras": true, "alt": "A lighthouse at dusk"}
```

## Historia

Pieza con `"canales": ["historia"]` y `"archivo": "historia.jpg"` (JPEG 1080x1920) o `"historia.mp4"` (9:16, 3 a 60 s), sin caption: la API
no lo admite y, si la pieza lo trae, `abrir` lo marca Fix. Va sola. La huella es el hash del archivo (`registro.hash_historia`).
`aprobar.py cerrar <slug> --historia https://www.instagram.com/stories/<usuario>/<id>/`. Paso a paso en `../instagram/LEEME.md`.

## Tanda: un issue, varias piezas (D-308)

A tres o más piezas por día, un issue por pieza es mucho celular. La tanda junta las piezas de un lote en **un issue** y **un 👍**.
`python3 aprobar.py tanda abrir <nombre> <slug> [<slug> ...] [--seco]` (hasta 12 piezas; todas con su `cola/aprobar/<slug>/` lista,
sin ninguna en Fix: si una falla no se abre nada). Hace, desde un worktree de main como `abrir`: un issue `Approve batch: <nombre> · n pieces · <primera> to <última>`
con la etiqueta `por-aprobar` (la Action `naos-avisar` menciona a N), **un comentario por pieza** con su vista previa (video, portada, título, caption,
descripción, `sale_utc`, revisiones) y, **al final, el comentario de la aprobación** con la tabla de la tanda. Cada pieza guarda su `estado.json`
(con `tanda` y el número del issue de la tanda) y la tanda guarda `cola/aprobar/_tandas/<nombre>.json`.

| N hace | Pasa |
|---|---|
| 👍 bajo el comentario de la aprobación, 👍 en el cuerpo (si es posterior a ese comentario) o `ok` | aprueba todas las piezas vivas de la tanda |
| `no <slug>` (varios: `no a b`; con motivo: `no a, muy largo`; junto al ok: `ok, no a`) | esa pieza queda `vetada`: sin filas, sin salir. Las demás siguen. Vale antes o después del 👍 |
| cualquier otro comentario, o 👎 | frena **toda** la tanda (pegajoso, igual que una pieza); hace falta `tanda version` |
| nada | no sale nada |

`procesar <issue>` reconoce el issue de tanda (la Action no cambia: mismo disparo, mismas etiquetas) y escribe en `publicados.csv` **una fila por pieza y canal**
como siempre (huella de cada canal, `version` de la pieza, `cita` = `ok de @N en <repo>#<issue de la tanda>, <fecha>`). Reglas propias:

1. Una pieza cuya hora de salida más la gracia ya pasó, o con cifras de más de 12 h al momento del toque, **no se registra** (queda `caducado`; el comentario de aprobación lo dice). Las demás sí.
2. Si una pieza viva cambia después de la vista previa, se frena toda la tanda (`tanda version`). Una pieza vetada puede cambiar sin frenar a las otras.
3. Un `no <slug>` después de aprobar anula solo las filas de esa pieza (y avisa que, si su Short ya está programado, hay que desprogramarlo en Studio); otro comentario después de aprobar anula toda la tanda.
4. `tanda version <nombre> [--sacar <slug>...]`: vistas previas nuevas de todas las piezas (otra versión de cada una), el 👍 viejo ya no cuenta, lo vetado no vuelve salvo con `--reponer`, y las piezas ya publicadas quedan fuera. Si N cerró el issue, se abre otra tanda con otro nombre.
5. `tanda version` no trae de vuelta lo vetado (`--reponer <slug>`), un 👎 de N sobre la vista previa de una pieza la veta, un `ok` con otra línea que pide algo frena, y `version`/`tanda version` se niegan si la pieza ya tiene `url_short` hasta pasar `--retirado` (desprogramar el Short viejo en Studio).
6. `version <slug>` de una pieza de tanda se niega y manda a `tanda version`. Una pieza vetada que se arregla va por `abrir <slug>` (issue suelto, versión siguiente).
7. `cerrar <slug>` de una pieza de tanda comenta ese enlace y cierra el issue (etiqueta `publicado`) cuando ninguna pieza sigue viva. `error <slug>` solo comenta. `caducar` no le cambia la etiqueta al issue por una pieza.
8. `leer <issue>` y `registrar <issue>` también entienden la tanda; `estado` la lista; `piezas <issue>` imprime las carpetas (`earn/naos/cola/aprobar/<slug>/*`) para el LFS de la Action.

Nadie aprueba por N (D-301): solo cuenta `NAOS_APROBADOR`, y los comentarios con `<!-- naos:` o "Generated by [Claude Code]" no son palabra suya.

**Action y LFS.** `cola/aprobar/*/video.mp4` va por LFS y el checkout de `naos-aprobar` deja el puntero: la huella salía del puntero y la pieza parecía cambiada
(sin comentario ni fila). La Action ahora instala LFS con `--skip-smudge` y en cada vuelta hace `git lfs pull` de las carpetas que imprime `aprobar.py piezas <issue>`.
Esa parte no se probó en una runner real (sin red en la sesión 2.9): al primer `ok` de N, revisar la corrida; si falla, `procesar` a mano como en la 2.9.

## Reprogramar lo que N aprobó y no salió (D-512, 13-nov)

N: "todas las piezas deben salir". `python3 aprobar.py reprogramar <slug>... [--seco] [--desde <ISO UTC>]`.

- **La huella no incluye la hora** (`registro.hash_canal`: mp4, texto, título y portada). La hora vive en la fila de `publicados.csv` (`sale_utc`, `vence_utc`) y en `estado.json`, y `verificar` exige que `--publicar-en` sea la de la fila. Por eso reprogramar no toca el contenido: escribe una fila nueva por canal (versión + 1, misma huella, `via` = `D-512`, `aprobado_por` = el usuario de N) cuya `cita` dice la hora vieja, la nueva y el 👍 original. La fila vieja queda. `estado.json` sube a esa versión, `aprobado`, con `reprogramada` {de, a, cita_origen}; `pieza.json` solo cambia `sale_utc`. Anota una fila "Reprogramación D-512" en `decisiones-sistema.csv` y comenta el issue.
- **Cuándo**: 👍 vigente de N (no del VP ni del agente) sobre la versión actual, huella igual a la aprobada, sin `url_short`, `url_reel` ni `publicado_utc` en la fila vigente (eso ya salió: se salta, también en `caducar`), y la hora más la gracia ya pasó o el estado es `caducado` o `error`.
- **Hora nueva**: desde `--desde` (por defecto ahora) más 2 h (`--margen-h`), cada media hora entre las 8:00 y las 23:30 de Nueva York, a 60 min o más de toda otra pieza de la misma marca (Instagram) o 30 min si la pieza es solo Short. Las piezas de una misma corrida no caen juntas.
- **Se niega y va a N** (se lista con la razón): contenido cambiado; pieza de fecha (tipo FIESTA, ST o LUNA, revisión `Moon` o `Luna`, campos de fecha o fiesta, `datos_utc`, o texto con un día de la semana, tonight/today/tomorrow, una fecha, una fase de la luna o una fiesta; "Sunday dinner" es un ritual y no cuenta); pieza de tendencia (`tendencia` o `cazador` en `pieza.json`, tipo TENDENCIA, origen del cazador); reserva condicional sin `liberada`; vetada por N.
- `caducar` reprograma (con un `AVISO`) la pieza aprobada, sin salir y no excluida en vez de caducarla; las excluidas caducan como siempre y quedan listadas como `PARA N`.

## Retirar una pieza que N ya aprobó (D-467)

- `python3 aprobar.py retirar <slug> [<slug> ...] --cita "<palabras de N>" [--decision D-467] [--seco] [--sin-git] [--bajar-shorts]`. Solo con una orden de N: la cita es obligatoria.
- Por pieza viva: sus filas de `publicados.csv` pierden validez (`vence_utc` = ahora) y `estado.json` queda `vetada`, con `retirado_utc` y `retirado_por`. La compuerta la niega por las dos vías y `programador.py` no la despacha ni la sube.
- Las demás piezas de la tanda no se tocan: ni sus filas, ni su estado, ni la etiqueta del issue. El issue se cierra solo si ya no queda ninguna viva.
- Deja una fila por pieza en `medicion/decisiones-sistema.csv` (fila "Retiro de N de una pieza ya aprobada", autor `vp`, con la cita y la decisión) y un comentario por issue con `<!-- naos:retiro -->`, que no cuenta como palabra de N.
- Todo o nada: si una pieza ya salió (Reel, imagen, historia o carrusel publicado, o Short con la fecha pasada) o no está en la cola, no se cambia nada. No despublica.
- Idempotente: lo ya retirado, vetado o caducado se dice y se deja igual. `--seco` solo imprime qué haría; no escribe ni llama a GitHub ni a YouTube.
- Short ya subido con fecha: sale solo a su hora aunque la pieza esté retirada. `retirar` imprime (y deja en el issue) el comando exacto para bajarlo, y no lo corre.
- `--bajar-shorts` lo pasa a privado y sin fecha (`idiomas.quitar_fecha`, 52 u. por video), solo en piezas que este comando retiró (`vetada` con `retirado_utc`); nunca toca una viva ni una pública. Sale con código 1 si algo sigue programado. Se corre desde una copia de main, como `procesar`.
- `retirar` no toca una pieza ya retirada, ni una cuya versión actual es más nueva que la retirada, ni una en una tanda abierta después del retiro: imprime "ya retirada, no se toca la versión nueva" y sigue con las demás. Con `--bajar-shorts` sí baja los Shorts viejos de esas piezas.
- Para bajar los Shorts viejos sin retirar de nuevo: `python3 aprobar.py bajar-shorts <slug>... [--seco]` (solo llama a `quitar_fecha`; no baja el Short de una versión que sigue viva). `agente.py bajar-shorts` no sirve aquí: solo ve Shorts del agente.

## Tanda del VP (D-274, D-322)

Desde las piezas que salen el 9-nov (`vp.json` `desde_utc`), el VP aprueba solo historias, carruseles y regresos (una conducta que ya
salió con el 👍 de N, contada de otra forma; `pieza.json` trae `"regreso_de": {"slug": "<origen>", "enlace": "https://github.com/.../issues/<n>"}`
y el origen tiene fila de N publicada en `publicados.csv`), con veto de N de 12 h. Regla completa: `gobierno.md`, sección «Autonomía del VP desde el 9-nov».

- `python3 aprobar.py tanda abrir <nombre> <slug>... --vp` revisa cada pieza contra `vp.json` antes de crear nada (canal o regreso, nada de
  "Qué no cubre": fiestas de fe o tradición, luna con astrología, lo divino, condicionales, imágenes sueltas; y que salga después del fin del veto,
  más una hora si lleva Short). Si una no cabe, no se abre nada: esa pieza va a la tanda de N. Si caben, abre "Tanda del VP (D-274): veto de N
  hasta <hora Bogotá>" y la aprueba como VP en el acto.
- `python3 aprobar.py vp <nombre>` es esa aprobación (idempotente): filas `aprobado_por` = `via` = `vp` en `publicados.csv` con la cita
  "VP (D-274, D-322) en <repo>#<n>, <utc>; veto de N hasta <utc + 12 h>", `estado.json` con `aprobacion` = `vp`, `aprobado_evento_utc` y
  `veto_hasta_utc`, una fila por pieza en `medicion/decisiones-sistema.csv` (fila "Aprobación del VP (D-274)", autor `vp`, `vence_veto_utc`),
  un comentario con `<!-- naos:vp -->` y la etiqueta `vp-aprobado`. Nunca reacciona ni pone el 👍 de N (D-301).
- Cómo veta N, por los caminos de siempre: 👎 en la vista previa de una pieza o `no <slug>` la quita (`vetada`); cualquier otro comentario,
  un 👎 en el cuerpo o cerrar el issue frena toda la tanda. Cada veto queda en la columna `veto` de `decisiones-sistema.csv` y la pieza vetada
  no la vuelve a aprobar el VP. "veto <slug>" en la mesa: `aprobar.py vp <nombre> --veto <slug> --cita "<palabras de N>"`.
  Su 👍 (o `ok`) sobre la tanda del VP la vuelve aprobación de N: su fila convive con la del VP y gana.
- La compuerta (`registro.verificar`): la fila del VP vale solo con todo lo anterior; mientras corre el veto dice "veto de N abierto hasta X",
  que es espera y no error: `programador.py` lo lista como AVISO, `accion_reel.py datos` termina con `ya=true` y `espera=true`, `ig.py` y
  `subir.py` salen con código 75. Un Short de regreso se sube recién al vencer el veto. `estado.py` (sección 4b) muestra las aprobaciones
  del VP, los vetos abiertos y los vetos de N por semana.

## Agente aprobador (D-461)

Un agente aprueba sin N, en NAOS y en Mercury, lo que pasa tres filtros. N tiene 12 horas para vetar. Lo sensible sube a N.

| Archivo | Qué es |
|---|---|
| `agente.json` | la regla: `activo`, corte 9,0, veto de 12 h (y por carril), canales, la vara de cada marca, las listas de lo sensible y de lo que Mercury nunca saca solo |
| `agente.py` | `huella`, `vara`, `estetico`, `dictamen`, `freno`, `soltar`, `programados`, `bajar-shorts`, `bajar-vetados`, `releer`, `estado`, `registro` |
| `prueba_agente.py` | 81 pruebas sin red (29 de la revisión adversarial del 10-nov; 4 de la llave de Instagram de Mercury; YouTube simulado con `ytapi.Simulado`): `python3 prueba_agente.py` |
| `prueba_cifra_viva.py` | 83 pruebas sin red del carril de cifra viva y de D-474 (28 de la revisión adversarial del 11-nov; fuente inyectada; `subir.py` corre de verdad con YouTube de mentira): `python3 prueba_cifra_viva.py` |

**Camino de una pieza.** Con la pieza lista en `cola/aprobar/<slug>/`:
1. Los lectores fríos dejan `vara.json`: `agente.py vara <slug> --total 9.3 --lectores 2 --puntajes 9.5,9.1` (o `--rubrica` sobre `lector-*.json` y `medidas.json`).
2. El lector estético deja `estetico.json`: `agente.py estetico <slug> --pasa --referencia "<caso>" --lector <modelo>`. Sin una referencia nombrada no pasa.
3. `agente.py dictamen <slug>` corre el lente como compuerta y escribe `dictamen.json` con una de tres decisiones:
   - `no-pasa`: falta evidencia, es de otra versión, hay menos de 2 lectores, el puntaje no llega al corte, el estético no pasa, o el lente ve algo grave (riesgo alto).
   - `sube-a-N`: toca duelo, soledad, salud mental o cuerpo; es de lo que Mercury nunca saca solo (resultados electorales, muertes y desastres, voz de una persona real, consejo médico, legal o financiero, fuentes sin abrir); es condicional; o es dudosa.
   - `aprueba`: todo lo demás.
4. `aprobar.py tanda abrir <nombre> <slug>... --agente`: entran solo las que aprueban; las otras se listan para la tanda de N. La tanda nace aprobada: filas `aprobado_por` = `agente`, `estado.json` con `aprobacion` = `agente`, una fila "Aprobación del agente (D-461)" en `decisiones-sistema.csv`, comentario `<!-- naos:agente -->` y etiqueta `agente-aprobado`. Nunca pone el 👍 de N.

**Veto de N.** Igual que con el VP: 👎 en una pieza o `no <slug>` la quita; otro comentario, 👎 en el cuerpo o cerrar el issue frena todo; su 👍 la vuelve aprobación suya. Desde la mesa: `aprobar.py agente <nombre> --veto <slug> --cita "<palabras de N>"`. Mientras corre el veto nada sale: `programador.py` lo da como AVISO y `ig.py` y `subir.py` salen con código 75.

**Compuerta.** `registro.verificar` no se fía del dictamen: antes de cada salida vuelve a revisar que el agente esté suelto, que la pieza no toque lo sensible, que el dictamen apruebe con el corte de `agente.json` y que las huellas del dictamen, de `estado.json` y de la fila sean las mismas. La evidencia y el dictamen llevan la huella del contenido: si la pieza cambia, hay que leerla otra vez.

**Freno, un solo comando:** `python3 earn/naos/motor/aprobar/agente.py freno "<motivo>"`. Crea `FRENO-AGENTE` y lo sube a main (ya no hace falta `--empujar`; si el empuje falla lo dice y sale con código 1). Desde ahí ninguna fila del agente vale, ni las ya aprobadas sin publicar: todo vuelve al 👍 de N. Lo que aprobó N o el VP no se toca. `agente.py soltar --empujar` lo quita. `--sin-empujar` lo deja solo en esa copia: no sirve para frenar de verdad, porque la Action lee main y la ronda de la operadora (`copia.py al-dia`) limpia su copia y lo borra.

**Shorts ya programados en YouTube.** Un Short subido como privado con fecha sale solo a su hora: la compuerta ya no lo ve. `agente.py freno "<motivo>" --bajar-shorts` frena y además los baja; `agente.py bajar-shorts [<slug> ...] [--seco]` los baja cuando se quiera: lee cada video (`videos.list`, 1 u.) y lo pasa a privado sin fecha (`idiomas.quitar_fecha`: `videos.update part=status`, 50 u., sin tocar título ni traducciones) con el token del canal de su marca (`GOOGLE_OAUTH_*` para NAOS, `MERCURY_OAUTH_*` para Mercury), vuelve a leer para confirmar y sale con código 1 si alguno quedó programado. No toca lo que ya es público ni lo que N hizo suyo con su 👍. Deja `short_bajado_utc` en `estado.json` y una fila en `decisiones-sistema.csv` (hay que subirlos a main). Cuando N veta, frena o cierra una tanda del agente con un Short ya programado, el comentario del issue y la salida de `procesar` traen el comando exacto (`agente.py bajar-shorts <slug>`); nadie lo corre solo. `agente.py programados` lista los que hay.

**Lo que el freno NO para.** (1) Sin `--bajar-shorts`, los Shorts de arriba. (2) Un Reel cuya Action ya hizo checkout (hasta unos 20 minutos antes de su hora): esa corrida no ve un freno que llegue después; se cancela en Actions. (3) `soltar` revive las filas que no vencieron: si el freno fue por una pieza, vétala (`aprobar.py agente <tanda> --veto <slug> --cita "..."`) antes de soltar.

**Lo que la compuerta exige además del dictamen** (revisión del 10-nov): `vara.json` y `estetico.json` en la carpeta, con el sello de la misma versión, el mismo puntaje del dictamen sobre el corte, lectores suficientes, `pasa` en true y referencias (un dictamen escrito a mano sin evidencia no vale); aprobada y con salida desde `desde_utc` (las dos horas); puntaje y lectores que sean números de verdad (NaN, infinito, `true` o un 97 no pasan); el dictamen de esa pieza, de esa marca y de ese carril; un veto de al menos 1 hora (un `veto_h` de 0, negativo o raro vuelve a 12; la única excepción es el carril de cifra viva, por nombre y con todo cumplido) que no se acorta después de aprobar; un margen de lectura después del veto (`margen_lectura_h`, 2 h: la pieza tiene que salir al menos 14 h después de aprobada, 15 h si lleva Short), porque el 👎 de N lo lee la ronda horaria y en esa misma ronda corrían el despacho y la subida de Shorts con la copia vieja; y que N no haya parado ya esa misma versión (su veto, o su tanda aprobada y después frenada).

**Mercado de predicción como fuente (D-474; N, 11-nov-2026).** Una nota media del lente en una categoría de `lente_sube` manda la pieza a N. Hay una sola excepción, en `agente.json` `lente_medio_permitido`: la nota media de **apuestas** no sube a N si la pieza es de la marca mercury, de la serie `odds_moved`, y su texto público (los `campos_texto`) cumple las tres cosas: ningún dominio de un mercado de predicción o casa de apuestas (`dominios`: con o sin https, y también "polymarket dot com"), la frase "prediction market", y la hora del dato ("as of 6:26 PM ET, Nov 10, 2026": "as of", una hora y una fecha). Si falta algo, o la regla está mal escrita, sube a N como siempre. El riesgo alto sigue bloqueando: el lente da alto con un enlace o con el dominio escrito, y medio con la palabra "Polymarket" sola. La compuerta lo vuelve a comprobar en cada salida con las notas guardadas en `dictamen.json` (`registro.lente_sube_a_n`). Vale para Odds Moved dentro y fuera del carril de cifra viva.

**Para la mesa:** `agente.py estado` (una línea) y `agente.py registro --horas 24` (tabla de todo lo decidido, con puntaje, estético, fin del veto y vetos de N).

**Mercury.** La pieza lleva `"marca": "mercury"` en `pieza.json`; `programador.py` le pasa `--canal mercury` a `subir.py`, que comprueba que el token sea de ese canal. Sin la marca la pieza se trata como NAOS, así que hay tres defensas: (1) `registro.marca_delatada`: si el slug, la clave, la serie (agreed, lookup, lineage, odds_moved, day_played, news_before_noon, today, drops), los campos del esquema de Mercury (sello, tramos, kokoro, evidencia) o el handle `mercury.now` delatan Mercury y falta la marca, el dictamen da no-pasa, la compuerta niega la fila del agente y `programador.py` no la sube; (2) `subir.py` niega cualquier pieza de Mercury (lo diga o lo delate) camino al canal de NAOS, con fila de N o del agente, y la del agente solo sube al canal de su marca; (3) la marca queda en el dictamen: quitarla o ponerla después lo invalida. De Mercury el agente aprueba solo el Short mientras la llave `agente.json` `marcas.mercury.instagram` esté en `false` (así nace): un Reel, carrusel, imagen o historia de Mercury sube a N con el motivo "Instagram publica solo en la cuenta de NAOS". Con la llave en `true` (solo el booleano; se enciende por PR cuando la cuenta de Mercury ya publica por la Action) ese motivo desaparece y lo demás sigue igual: lo sensible y lo que Mercury nunca saca solo suben a N. Apagarla después niega en la compuerta las filas del agente que no hayan salido (`registro.instagram_de_marca`). `canales.json` trae el `canal_id` de NAOS (`UC7Lo3rK5sEOWuDYhAaQKtNw`: lo dan `motor/investigacion/datos/2026-11-10/channels-*.json`, que es `channels.list mine=true` con el token de NAOS, `empresa/marca/yt-branding-antes-2026-11-03.json` y `motor/comentarios/LEEME.md`), así que `subir.py` también comprueba el token con `--canal naos` (una llamada `channels.list`, 1 u. por subida). El handle (`@naos-v3`) no se puso: si el canal cambia de handle, bloquearía todas las subidas.

## Carril de cifra viva (Mercury)

N, 11-nov-2026: "Que el agente apruebe ahí mismo". Una pieza con una cifra que se mueve no espera 12 h de veto: sale a su hora, con la cifra releída, y N veta después.

- **Regla:** `agente.json` `carriles."cifra-viva"`. Dos llaves: `activo` (el carril) y `activa` (cada plantilla). Nace todo apagado; lo enciende un PR.
- **Vale solo si todo se cumple** (`registro.fallas_carril_viva`; la compuerta lo repite en cada salida): marca mercury; canal `["short"]` (el Reel con `reel: true`, cuando `ig.py` tenga la cuenta de Mercury); `"carril": "cifra-viva"`; `"plantilla": "<serie>/<nombre>"` listada y activa, de la serie de la pieza; `cifras_vivas` bien declaradas; nada sensible, nunca-solo ni condicional; dictamen completo.
- **Cifra:** `{"id", "que", "valor", "unidad", "fuente_url", "leido_utc", "donde": [rutas de pieza.json donde está escrito el número], "tolerancia", "extractor"}`. `fuente_url` es https y de un host de `hosts`. La tolerancia no pasa del 5 % del valor. `donde` solo admite campos que la gente lee u oye (`titulo`, `descripcion`, `narracion`, `comentario_fijado`, `caption`, `alt`, `texto_en_pantalla`).
- **Extractor:** `{"tipo": "json", "ruta": "0.markets.0.outcomePrices.0", "escala": 100, "comprobar": [{"ruta", "igual"}]}` o `{"tipo": "regex", "patron": "Yes ([0-9.]+)%"}`. `escala` va de 0,001 a 1000. El patrón corre en otro proceso con 3 s de tope.
- **La plantilla fija sus cifras (obligatorio):** `plantillas."<serie>/<nombre>".cifras = {"<id>": {"fuente_url", "extractor", "tolerancia_max"}}`. Una plantilla sin `cifras` no vale. La pieza no puede declarar una cifra viva que la plantilla no tenga, ni cambiarle la dirección o el extractor; en la tolerancia manda `tolerancia_max` y la de la pieza solo puede ser igual o menor (y nunca más del 5 % del valor). Si la pieza eligiera su fuente y su extractor podría elegir uno que siempre dé `igual`. Hoy solo `odds_moved/gta-vi` fija una (`precio-yes`, copiada del guion `13-1-short-odds-record.json`, tolerancia 1 punto, **sin probar contra la fuente**); `drops/gta-vi` y `agreed/gta-vi` no fijan ninguna y no valen hasta que alguien las defina.
- **Relectura:** `agente.py releer <slug>` abre cada fuente (GET, 10 s, sin redirecciones) y escribe `relectura.json` con la huella del contenido, la de las cifras, la hora y un sello. No va a git.
  - `igual`: dentro de la tolerancia; se publica tal cual.
  - `cambió`: no se publica. La pieza vuelve a producción, se dibuja con la cifra nueva y necesita dictamen nuevo. Es pegajoso: aunque la cifra vuelva, esa versión ya no sale.
  - `no-se-pudo-leer`: no se publica; se reintenta en la ronda siguiente.
  - Nunca se cambia un número dentro de una pieza ya dictaminada.
- **Camino:** `a_cola.py` (copia carril, plantilla y cifras), `agente.py vara`, `estetico`, `releer`, `dictamen`, y `aprobar.py tanda abrir <nombre> <slug> --agente` (tanda propia, sin mezclar). Sin relectura `igual` de menos de 12 h no hay dictamen ni aprobación.
- **Regla 6:** para este carril la hora de las cifras es la de la relectura. Para todas las demás piezas no cambia.
- **Salida:** `programador.py --subir-shorts` espera hasta 60 min antes de `sale_utc` (`subir_antes_min`), relee él mismo y, si da `igual`, corre `subir.py`: con fecha si faltan más de 15 min, público ya desde 5 min antes de la hora. La compuerta pide relectura `igual` de menos de 30 min (`relectura_max_min`) con la huella vigente.
- **Límites:** `tope_dia` (3 en cualquier ventana de 24 h sobre la hora de salida, al aprobar y al subir: cuenta todo lo que sale a menos de 24 h, antes o después; cuenta cada versión subida, no cada slug), `horas_utc` (opcional), plantillas y hosts listados a mano.
- **Aviso:** al subir queda la fila "Aprobación del agente (D-461), cifra viva" en `decisiones-sistema.csv` (fin del veto a 12 h), un comentario en el issue y la línea `AVISAR-N <slug> <url> veto hasta <hora>`, que `ronda.py` repite. La operadora o la mesa le avisan a N; el código no llama a ningún servicio. `agente.py registro` la marca CIFRA VIVA.
- **Veto de N:** 12 h después de publicar, por los caminos de siempre. El aviso trae `agente.py bajar-shorts <slug>`, que dentro de esas 12 h pasa a privado también un Short ya público de este carril (solo de Mercury), solo si se nombra. Después de las 12 h no lo toca y el comentario del veto dice que ya es público. Mientras corre el veto, `cerrar` y `caducar` no tocan la pieza; tampoco desde que abre la ventana en una copia que todavía no ve el `url_short` (hasta `sale_utc` + 3 h + 12 h).
- **Veto con el Short arriba:** el veto se registra en main, que puede no tener todavía el `url_short` (llega con `copia.py guardar`): ahí el comentario sale sin el comando. La copia que subió sí lo tiene: `programador.py --subir-shorts` imprime en cada ronda `BAJAR-SHORT <slug> <url>: ... agente.py bajar-shorts <slug>` y `ronda.py` lo repite, hasta que alguien lo corra o pasen las 12 h. `agente.py bajar-vetados` baja de una vez todos los vetados que siguen arriba, y ninguno más. Desde el 11-nov (D-476) lo corre `naos-aprobar.yml` justo después de `procesar`, con los secretos `MERCURY_OAUTH_*` de GitHub Actions, y comenta en el issue si lo bajó o si no pudo; si faltan los secretos o YouTube falla, el veto se registra igual y queda un aviso en el log (`empresa/evolucion/2026-11-09-limite/fable/7/propuesta-bajar-short-al-veto.md`, "Aplicado el 11-nov").
  - **Queda abierto:** si main todavía no tiene el `url_short` cuando llega el veto, la Action dice "nada que bajar" y no vuelve a correr sola; ese Short lo baja a mano quien vea `BAJAR-SHORT` en la ronda de la operadora (`agente.py bajar-shorts <slug>`).
  - No se cerró en código porque pide tocar la operadora (subir `publicados.csv` a main apenas sube el Short, o que la ronda vuelva a disparar la Action), y eso es otro cambio con su propia revisión de N.
- **Freno:** `FRENO-AGENTE` apaga también este carril. `"activo": false` en el carril lo apaga solo a él.
- **Lo que no cubre:** entre la relectura y la hora de salida pueden pasar hasta 60 min; cuando N veta, la Action baja el Short solo si main ya tiene su `url_short` (si no, sigue siendo a mano) y un 👎 tarda hasta la ronda de la hora; la relectura y el dictamen los puede escribir quien escribe en la cola (punto E de la revisión; el sello de `relectura.json` es un sha256 sin llave, y aquí ya no hay 12 h de veto antes de salir que lo acoten); `cambió` es pegajoso solo en la máquina que releyó (`relectura.json` no va a git); después de las 12 h `caducar` deja la pieza publicada en `caducado` si nadie corrió `cerrar`.
- **De `decisiones-sistema.csv` la copia de la operadora sube una sola clase de fila:** la de "cifra viva" publicada, de autor `agente` y con la columna `veto` vacía (`copia.decision_permitida`). Lo demás se descarta con un AVISO.

## Mercury: plantilla aprobada (D-499)

N, 11-nov-2026: en Mercury la vara completa (dos lectores con 9,0 y lector estético) se usa para diseñar y pulir plantillas. Una pieza de Mercury hecha con una plantilla que ya pasó la vara sale sin vara ni lector estético propios. NAOS no cambia, y una pieza de Mercury sin plantilla aprobada sigue el camino de siempre.

- **La lista:** `agente.json`, `marcas.mercury.plantillas_aprobadas`. Cada plantilla trae `activa`, la evidencia de su ejemplar (`ejemplar`, `vara`, `estetico`, `aprobada_utc`) y su `forma` (tramos, papeles, segundos y, si quiere pedir más que golpe y giro, `obligatorios`). Desde D-502 (Fable 7, 11-nov-2026) están encendidas dos: `simple/worth_it@5` (ejemplar `formatos-nuevos/v5/worth-it`, vara 9,0 y estético 13/14; termina en `sello`) y `simple/fine_print@4` (ejemplar `formatos-nuevos/v4/fine-print`, 9,5 y 12/14; termina en `firma`). Las tres @2 siguen listadas y en `activa: false`, y `simple/the_number` no se enciende en ninguna versión: sale de la línea diaria y solo se hace en días de noticia grande, con aprobación de N. Encender una es un PR que pone `activa: true` y llena `vara` (9,0 o más), `estetico` (`"11/14"` o más) y `aprobada_utc`. Con los ceros con que nace no vale aunque `activa` esté en true.
- **Los comandos, en orden, para una pieza:**
  1. `python3 a_cola.py <carpeta producida> --sale <hora UTC>` (en `mercury/`): deja la pieza en la cola con su `plantilla` y su `origen`.
  2. `python3 agente.py verificado <slug>`: si la carpeta de origen trae el archivo `verificado`, y el video, el título, la descripción y el comentario fijado de la cola son los de esa carpeta, copia su `medidas.json` y escribe `verificado.json` con la huella de hoy. Sin `verificado` no escribe nada.
  3. `python3 agente.py lector <slug> --archivo lector-linea.json`: sella lo que escribió el lector de la línea (`que_es`, `que_gano`, `entiende`).
  4. `python3 agente.py dictamen <slug>`: corre el lente y los controles. Si todo pasa dice `aprueba (plantilla aprobada <nombre> (D-499))` y deja en `dictamen.json` el campo `plantilla_aprobada` con los controles que pasó.
  5. `python3 aprobar.py tanda abrir <nombre> <slug>... --agente`: como cualquier tanda del agente. El veto de N corre igual (12 h).
- **Los controles** (`registro.fallas_plantilla`): marca mercury; plantilla listada, activa y con la evidencia de su ejemplar; `verificado.json` y `lector-linea.json` con la huella de esta versión; `medidas.json` sin cambios desde que se verificó; medidas de forma en regla (texto del gancho, apertura, rachas, gancho de 7 s o menos); la forma de la plantilla (cuenta de tramos, papeles permitidos, golpe y giro presentes, duración); lente sin graves; el lector dice `"entiende": true` y llena `que_es` y `que_gano`.
- **Lo que no cambia:** lo sensible, lo que Mercury nunca saca solo y lo dudoso (nota media del lente, lente que no pudo leer) suben a N. El veto de N y el freno valen igual. Una pieza del carril de cifra viva tiene que cumplir además todo lo del carril.
- **Cuál camino manda:** si la carpeta trae `vara.json` o `estetico.json`, manda el de siempre (una vara mala no se salta por tener plantilla). Sin ninguno de los dos y con los controles en regla, manda la plantilla.
- **La compuerta** vuelve a correr todos los controles en cada salida (`registro.fallas_dictamen_plantilla`): apagar la plantilla en `agente.json` niega lo que todavía no salió.
- **Para contarlas:** la `cita` de la fila en `publicados.csv` termina en `; plantilla aprobada <nombre> (D-499)` y la fila de `decisiones-sistema.csv` dice `por plantilla aprobada <nombre> (D-499), sin vara propia`.
- **Límites:** los sellos son huellas sin llave: quien escribe en la cola puede escribirlos a mano (igual que `vara.json`). `agente.py verificado` comprueba que el video y el texto sean los de la carpeta verificada, pero no puede saber si alguien cambió esa carpeta después de verificar. El nombre `simple/<serie>@N` no cabe en el patrón de plantillas del carril de cifra viva, así que hoy ninguna pieza usa las dos cosas a la vez.
- **Difficult Decision (D-504, D-506), el canal que reemplaza a Mercury.** Sus piezas llevan la marca interna `mercury`, slug `dd-...` y `"canal": "difficult-decision"`; las deja en la cola `c2/a_cola.py` (línea diaria: `c2/LINEA.md`, flujo `dd-dia`). En la lista hay siete plantillas suyas, todas en `activa: false` y con ceros: tres del tachón (Short) y cuatro fijas. Las del tachón: `dd/tachon@1` (la forma de antes de la vara 1: 6 tramos `gancho, golpe, dato, cuenta, giro, firma`, de 15 a 24 s) y las dos que `c2/producir.py` escribe en `medidas.json` desde la ronda 3 del 11-nov, `dd/tachon-f@1` (orden F: 7 tramos, con `aclara`) y `dd/tachon-n@1` (orden N: 6 tramos, sin `dato`), las dos de 16 a 24 s y con todos sus papeles obligatorios; se enciende la variante que gane la vara. Las fijas: `dd/lamina@1`, `dd/expediente@1`, `dd/historia@1`, `dd/said@1` (piezas fijas de Instagram). El tachón no necesitó código nuevo: encendido con la evidencia de su ejemplar aprueba por plantilla y entra al carril de plantilla (D-503). Las cuatro fijas no traen `forma` a propósito y fallan cerradas aunque se enciendan: `fallas_forma` solo mide un Short, `agente.py verificado` pide un mp4, el carril de plantilla es solo del Short y `marcas.mercury.instagram` está en false. Qué falta para que salgan sin N: `c2/LINEA.md`, sección 9.
- Pruebas: `prueba_plantilla.py` (42; la clase `TestDifficultDecision`, con 8, cubre las `dd/`).

## Programador: Reels y Shorts

`python3 programador.py` (sin banderas) imprime los slugs de Reel que tocan y nada más (la operadora los despacha a `naos-reel.yml`). Para los Shorts:

- `python3 programador.py --shorts` lista los Shorts que tocan subir (solo lee).
- `python3 programador.py --subir-shorts [--seco]` corre `motor/youtube/subir.py` por cada uno, hasta 4 por ronda, con `--slug`, `--titulo`, `--descripcion` (el texto de `pieza.json`, lo mismo que aprobó N),
  `--miniatura portada.jpg`, `--publicar-en <sale_utc>` y `--seccion humanity`, **sin** `--sintetico` (D-243). Imprime `short <slug> <url>`; los avisos y errores van a stderr y el código de salida es 1 si hubo un `ERROR`. `--seco` no llama a YouTube.
- Toca si: canal `short`, fila vigente de N con huella, sin `url_short` ni `publicado_utc`, aprobación sin vencer y `sale_utc` a más de 15 minutos (YouTube pide un `publishAt` futuro; el Short se sube **apenas hay aprobación**, no a la hora). Si ya no da tiempo o la aprobación venció, avisa y no sube.
- Sin duplicar: con `url_short` en la fila no toca. `subir.py` además se niega ("ya está subido") y anota el `url_short` apenas existe el video, antes de la miniatura; si la miniatura falla, sale con aviso y el Short no se vuelve a subir.
- La compuerta de N sigue en `subir.py`: sin la fila con esa huella (video, título, descripción, miniatura) y esa hora, no sube.
- Otro canal: `subir.py <carpeta de la pieza> --canal mercury` (token `MERCURY_OAUTH_*`, su propio libro de cuota, comprueba que el token sea de @mercury.now). Detalle en `empresa/duplicar/canal-lucro/mercury/LEEME.md`.
- Por marca: `python3 programador.py --marca mercury [--shorts | --subir-shorts [--seco] | --despachar]` deja solo las piezas cuyo `pieza.json` dice `"marca": "mercury"`. `--marca naos` deja las de NAOS (sin `pieza.json` cuenta como naos). Una pieza que solo parece de Mercury (`registro.marca_delatada`) queda fuera de las dos, con un AVISO, hasta que `pieza.json` lo diga. Sin `--marca` todo sigue igual.
- Quién saca qué (11-nov-2026): la operadora (`ronda.py`, pasos D y S) y la ronda sombra corren con `--marca naos`. Las piezas de Mercury salen solo por la Action `mercury-publicar.yml` (`--marca mercury`, cada 30 minutos, apagada hasta que la variable `MERCURY_PUBLICAR` valga `on`). Antes las dos máquinas podían subir el mismo Short de Mercury. Pasos del dueño en `empresa/duplicar/canal-lucro/mercury/linea/PUBLICAR.md`.
- `--guarda-main` (con `--subir-shorts`; lo usa la Action): antes de cada subida trae `origin/main` y mira su `publicados.csv`. Si esa fila ya tiene `url_short`, no sube y deja un AVISO; si no puede leer main, no sube y sale con ERROR.
- `--despachar --a-la-hora [--tope-espera MIN]` (lo usa el paso D de `ronda.py`): la sesión duerme y la Action no. Cada pieza se despacha en su hora objetivo: Reel con Short `sale_utc` + 4 min - 100 s (la misma regla que `accion_reel.esperar`); historia, imagen, carrusel y Reel sin Short `sale_utc` - 90 s. Lo ya vencido sale de una; lo que pasaría del tope (18 min, porque `ronda.py` corta cada paso a 1500 s) sale al llegar al tope y la Action duerme lo que falte. Nunca antes que hoy ni después de su hora; ANTES y DESPUES no cambian, ni la compuerta de la Action.
- Un fallo de un despacho no frena a los otros. La salida dice `despachado <slug> a HH:MM:SSZ (objetivo HH:MM:SSZ)`. Sin `--a-la-hora` todo sigue como antes. Pruebas: `TestALaHora` en `prueba_programador.py`.
- **Varias piezas por corrida (13-nov-2026).** GitHub cobra cada corrida de `naos-reel.yml` redondeada hacia arriba al minuto, y el checkout, ffmpeg, la espera de Pages y "Guardar en main" se pagaban una vez por pieza. `--despachar` (con o sin `--a-la-hora`) agrupa en UN despacho, con el input `slugs` (lista separada por espacios), las piezas de NAOS cuya hora objetivo y hora de despacho caen a menos de 90 segundos de la primera del grupo, hasta 4 (`VENTANA_LOTE`, `MAX_LOTE`; solo lo que de verdad comparte minuto: una historia y un Reel con Short de la misma hora se llevan 3 min 50 s y no se agrupan; dos Reels o dos imágenes de las :00 sí; la cuarta pieza sale como mucho unos 3 min tarde). El despacho sale a la hora de la primera pieza. Una pieza sola sale suelta con `slug`, como antes; las de otra marca (Mercury) salen siempre sueltas. `--sin-lote` deja un despacho por pieza (lo de antes). Si el despacho del lote falla, cada pieza se despacha suelta (línea `AVISO lote de N ... no salió`); el reclamo de la Action impide que alguna salga dos veces. La ronda sombra corre con `--marca naos --despachar --sin-lote`: no agrupa (es el respaldo y debe ser simple). La salida de un lote es `despachado en lote de N a b c ... a HH:MM:SSZ (objetivo ...)`; `ronda.py` y el paso D de `ronda.md` cuentan cada slug. Pruebas: `TestLote` en `prueba_programador.py`.
- **Qué hace la Action con `slugs`** (job `lote` de `naos-reel.yml`, `instagram/lote_reel.py`): un checkout, el LFS de cada pieza, ffmpeg una sola vez si alguna trae video y las piezas en serie. Primero la compuerta de cada una (`accion_reel.py datos`: la fila de N para ESE video y ese caption; sin ella la pieza se niega y se avisa en su issue) y la subida a Pages de todas sin esperar el despliegue; después, por hora de salida, confirmar Pages, esperar su hora (la propia), Short, reclamar, publicar y cerrar. Una pieza que falla se avisa y no frena a las otras (la corrida termina en rojo). Después de cada pieza publicada se guarda en main y al final hay un "Guardar en main" más; los dos usan `instagram/guardar_lote.sh` (pieza por pieza, solo lo que exista, con reintento: una pieza sin carpeta o sin `estado.json` no corta el guardado de las demás). Nada de la compuerta cambia: `ig.py` se niega sin la fila de N pieza por pieza.
- **Sin publicar dos veces.** Un lote no puede tener el grupo de concurrencia por slug, así que hay dos guardas por pieza antes de publicar: `datos` ve `url_reel` en `publicados.csv` y sale (como siempre) y `accion_reel.py reclamar` crea la etiqueta `reel-claim/<slug>-v<N>` en el remoto (crearla es atómico: el servidor rechaza a la segunda corrida). La usan el lote y el despacho suelto, así que si un suelto y un lote coinciden, publica el que reclama primero y el otro termina en verde sin publicar. El reclamo no se suelta: si la pieza salió es la prueba; si falló caduca a los 20 minutos (un reintento manual antes de eso sale "ocupada": `git push origin --delete refs/tags/reel-claim/<slug>-v<N>` lo libera). Un reclamo vencido no se toma si la pieza ya tiene `url_reel` en el `publicados.csv` de la corrida o su estado dice publicado. Si el remoto no deja crear la etiqueta por otra razón: el despacho suelto sigue sin reclamo, como antes (tiene concurrencia por slug); el lote es estricto (`reclamar --estricto`): esa pieza no se publica y sale como fallo de infraestructura (`infra.txt`, `infra_fallo_utc`) con aviso en su issue, y la ronda siguiente la manda suelta. Pruebas: `instagram/prueba_lote.py` y `VariasPiezasPorCorrida` en `prueba_flujos.py`.
- Si la sesión cae mientras duerme, nada queda a medias: la pieza sigue sin `url_reel` y la ronda horaria siguiente puede rescatarla, porque la ventana de `tocan` es de 75 min hacia atrás (`DESPUES`, antes 45) y la aprobación vence a las 3 h. De 45 a 75 min (zona de rescate) solo se despacha si ninguna otra pieza de IG está a menos de `aprobar.D512_IG_MIN` de ahora (por sale_utc si no salió, por publicado_utc si salió); si choca, `AVISO <slug>: rescate frenado, vecina <slug2> a N min; usar aprobar.py reprogramar`. Hipótesis, no medida: que la caída de runners del 12-nov dejara piezas sin despachar por esta ventana. Pruebas: `TestRescate`.
- Un Short vetado o retirado (`estado.json`), o una fila del agente con el freno puesto, no se lista ni se intenta: sale como AVISO y la ronda no queda en rojo.
- `copia.py guardar` avisa con `AVISO DOBLE` si la copia trae un `url_short` o `url_reel` distinto del que main ya tiene para la misma fila: main conserva el suyo y el segundo hay que bajarlo a mano.

## Rutina de una pieza

1. Dejar `cola/aprobar/<slug>/` (con `clave` y `datos_utc`) y `python3 aprobar.py abrir <slug> --seco` primero.
2. `python3 aprobar.py abrir <slug>`. GitHub no le avisa a N de lo que abre su propio token; desde la sesión 8 lo cubre la Action
   `naos-avisar` (`.github/workflows/naos-avisar.yml`), que comenta como bot con la @mención de N en cada issue `por-aprobar`. Si esa
   Action no existe, `abrir` se niega con el token de N tras preguntar `GET /user` (`NAOS_AVISO_GITHUB=1` salta la guarda).
   Hace, en este orden: crea el issue (`por-aprobar`) y la vista previa; escribe `estado.json`; **commit y push de
   `cola/aprobar/<slug>/` a main** (la Action hace checkout de main: sin `estado.json` ahí, el `ok` de N no se registra). El aviso a
   N es el propio issue con su @mención (D-235: avisos solo por GitHub, sin Telegram). Con `--sin-git` (pruebas) no empuja.
3. Si N comenta `ok`, la Action registra sola (hasta 2 min). Si falla, comenta en el issue `Could not register: <causa>`.
   El 👍 vale en el cuerpo del issue (si es posterior a la vista previa vigente) o bajo la vista previa. Si pone 👍, nada dispara: `python3 aprobar.py procesar <issue>` cada 5 minutos desde la sesión, hasta 2 h.
4. Sesión y Action escriben los mismos archivos (`estado.json`, `publicados.csv`): cada orden que escribe hace `git pull --rebase`
   antes y commit + push después, así que no hay que tocar `git` a mano; si un push falla, la orden sale con error. Ante un
   conflicto en `estado.json` o `publicados.csv`, gana main (lo que escribió la Action) y se vuelve a correr `procesar`.
5. `subir.py ... --slug <slug>` y `ig.py preparar` / `publicar` (ver `instagram/LEEME.md`).
6. `python3 aprobar.py cerrar <slug> --short URL --reel URL --enlaces <naos>/data/enlaces.json --semana <naos>/data/semana.json`:
   "Live", etiqueta `publicado`, cierra el issue y escribe el enlace en `enlaces.json`. Luego commit y push en el repo `naos`.
   Si falla algo: `aprobar.py error <slug> --causa "..."`. Si N pide un cambio: editar la pieza y `aprobar.py version <slug>`.

## Quién escribe el enlace en la página

`data/enlaces.json` del repo `naos` es la fuente única del enlace de lo publicado (README de `naos`). Lo escribe `aprobar.py cerrar
--enlaces` (la sesión que publica), con la `clave` de `pieza.json`; `semana.json` no se toca: la página marca la pieza como
publicada porque su clave tiene `yt` en `enlaces.json`. El paso del lunes 19 es ese commit y push en `naos`, hecho por la sesión que
publica; `node scripts/validar.mjs` lo valida.

## Evidencia y pendientes de N

- Salida de `abrir --seco` y captura del issue a 390 px: `empresa/infraestructura/2026-10-14-historias/evidencia-publicar/`.
- Pendiente de N antes del sáb 17-oct, con su celular y sus credenciales (no se simula): `abrir` con una pieza de prueba privada y
  el token de un bot; anotar la hora en que llega el @mención al celular (la guarda `aviso_utc` en `estado.json`); `ok` y 👍 desde
  la app de GitHub; ver la Action `naos-aprobar` correr en GitHub; `git pull`, `subir.py` e `ig.py` sin publicar antes del 👍; y
  capturar el issue real a 390 px (la captura de `evidencia-publicar/` es un mock, y el 👍 del cuerpo queda en la primera pantalla).
- `ig.py` sin `YOUTUBE_API_KEY` comprueba el Short por oEmbed, que no distingue un video no listado: imprime un AVISO. Probar
  `revisar_short` con un video privado o programado real de YouTube (credenciales OAuth de N) sigue pendiente.

## Edad del dato: regla contextual (D-483)

N, 11-nov: "Esa regla tiene que ser contextual porque necesitamos cosas que salgan el mismo día o en horas". La regla 6 ya no es un plazo fijo para todo. Depende de qué cifra es:

| Qué cifra | Qué pide | Cómo se declara |
|---|---|---|
| Fija, con fuente y fecha (precio de lista, récord, fecha) | no vence; sigue llevando `datos_utc` | `"cifras_fijas": true` en pieza.json |
| Se mueve, en un video de YouTube de Mercury (Short o medio) | carril de cifra viva: el agente aprueba sin espera, la cifra se relee en la última hora antes de subir y el veto de N corre después | `"carril": "cifra-viva"`, `plantilla` y `cifras_vivas` |
| Se mueve, en cualquier otra pieza (imagen, carrusel, historia, o lo que aprueba N) | se relee el mismo día: su hora es la de la última relectura "igual" de esta versión, y tiene que tener 12 h o menos al salir y al aprobar | `cifras_vivas` sin `carril`; `agente.py releer <slug>` |

- Una pieza con `cifras_vivas` nunca cuenta como de cifras fijas, diga lo que diga.
- Fuera del carril, la fuente y el extractor los declara la pieza (dentro, los fija la plantilla). Por eso esa relectura solo dice de cuándo es el dato: no quita ningún veto ni cambia quién aprueba. La fuente tiene que estar en los `hosts` del carril.
- Si la relectura dice "cambió", la pieza no sale con ese número: vuelve a producción.
- Una relectura hecha después de abrir el issue o la tanda también cuenta: se mira al leer la respuesta de N.

Límite: `cifras_fijas` lo declara quien hace la pieza. El código no comprueba que una cifra "fija" lo sea; eso lo mira el verificador.
Pruebas: `prueba_edad_dato.py` (9) y `prueba_cifra_viva.py`, clases `TestRegla6` y `TestRegla6FueraDelCarril`.

## Carril de plantilla (Mercury, D-503)

N, 11-nov-2026: "Entregamos lo que prometemos el presente, el sistema tiene autonomía y debe publicar solo si algo yo lo veo y luego del hecho".
- Un Short de Mercury que el agente aprobó por una plantilla activa (D-499, D-502) y que entró a la cola con `a_cola.py --carril plantilla` tiene **1 hora** de veto de N antes de salir, en vez de 12. Así la línea corre a las 11:30 UTC y sale el mismo día.
- La regla vive en `agente.json` (`carriles.plantilla`: `activo`, `veto_h`) y en `registro.fallas_carril_plantilla`. `veto_h` va de 1 a 12; cualquier valor raro vuelve a 12. El código nunca deja menos de 1 hora.
- Sin tope por día (N: "Sin tope"). Lo sensible y lo que Mercury nunca saca solo siguen yendo a N antes (N: "Sí, sigue antes").
- Solo Mercury, solo Short (sin Reel), y solo si el dictamen la aprobó por esa misma plantilla. Si falla cualquier cosa, la pieza vuelve a 12 horas.
- Para apagar el carril: `"activo": false`.
- **Veto después de publicar (D-505).** N: "Sí, que baje solo esa pieza". El veto de N sigue abierto 12 horas después de la hora de salida (`carriles.plantilla.veto_despues_h`; el código nunca deja menos de 12). N veta en el issue de la tanda con 👎 en la vista previa de la pieza o con el comentario `no <slug>`. Ese Short se pasa a privado solo: `procesar` la marca `vetada` y `agente.py bajar-vetados`, que `naos-aprobar.yml` corre en esa misma corrida, la baja. Las demás piezas siguen arriba y el agente no se frena. Un comentario suelto, 👎 en el post o cerrar el issue quitan todas las piezas de esa tanda, igual que en cifra viva.
  - Cómo queda escrito: al aprobar, `estado.json` lleva `"carril": "plantilla"` y `veto_despues_utc`; mientras corre la ventana, `cerrar` y `caducar` no tocan la pieza (`registro.veto_viva_abierto`). `registro.shorts_vetados_despues` (antes `shorts_viva_vetados`, que sigue como alias) lista los vetados de los dos carriles. Un Short subido con fecha y vetado antes de su hora también se baja.
  - Aviso: al aprobar, un comentario en el issue dice hasta qué hora y cómo vetar; al subir, otro comentario y la línea `AVISAR-N <slug> <url> veto hasta <hora>` (`programador.publicado_plantilla`).
  - Fuera de la ventana el veto anula la pieza en el libro y no baja nada: el comentario del veto dice que ya es pública y `bajar-shorts <slug>` responde que el veto venció. Se baja en Studio.
  - El 👎 no dispara la Action solo: lo lee la ronda horaria (`programador.py --aprobaciones`), así que puede tardar hasta una hora. El comentario `no <slug>` la dispara al momento.
  - **Límite, Instagram:** el veto baja el Short de YouTube y nada más. El carril es solo del Short y el agente no publica en la cuenta de Instagram de Mercury (`marcas.mercury.instagram` en false). Si N aprobó aparte un Reel, imagen, carrusel o historia del mismo tema y ya salió, vetar el Short no lo toca: `ig.py` no tiene borrado y no hay bajada automática para Instagram. Se borra a mano en la app. El aviso lo dice.
  - Para bajar todo de una vez sigue `agente.py freno "<motivo>" --bajar-shorts`.
- Pruebas: `prueba_carril_plantilla.py` (26; la clase `TestVetoDespuesDePublicarPlantilla` cubre D-505).

## Cierre automático

Solo `accion_reel.py cerrar` (naos-reel.yml) llamaba a `aprobar.py cerrar`. Los Shorts, medios y largos que sube `subir.py` dejan `url_short` en `publicados.csv` y la pieza quedaba `aprobado` aunque ya hubiera salido (15 el 13-nov). `cierre_auto.py` lo cierra:

- **Cuándo cierra:** `estado` `aprobado` o `subiendo`, la fila vigente de su versión trae una URL válida (`aprobar.url_valida`) y `sale_utc` ya pasó o la fila trae `publicado_utc`. Un Short programado privado con fecha futura no se cierra.
- **Con qué argumentos:** Short, medio o largo solo, `--short` (`watch?v=` vale para medios y largos); con Reel, `--short` y `--reel`, y si el Reel todavía no tiene `url_reel` no se cierra (lo cierra naos-reel); carrusel, imagen e historia, su flag con `url_reel`.
- **Veto de N abierto** (`registro.veto_viva_abierto`): AVISO y se salta; cierra cuando vence la ventana. Una pieza que falla no tumba las demás. Tope de 20 por ronda (`--maximo`). Idempotente.
- **Salida:** `cerrado <slug>` por pieza y `cierre_auto: N cerradas, M saltadas, K errores`. Código 0 aunque falle una pieza; 1 solo si falla todo (sin GitHub, o la copia no pudo subir sus registros).
- **`--git`:** primero `copia.py guardar` (sube a main las `url_short` de la copia; `copia.py guardar` no sube `estado.json`), cierra, y guarda `cola/aprobar` en main con "naos: cierre automático" (sin commit si no cambió nada). `--seco` no escribe, no llama a GitHub ni toca git.
- **Dónde corre:** paso X de `ronda.py` (después de S, antes de C; su fallo no corta los demás) y un paso de `mercury-publicar.yml` después de "Guardar en main" (`continue-on-error`, 3 min de tope).
- **Límite:** no escribe `data/enlaces.json` del repo naos (la página); eso sigue siendo de `accion_reel.py cerrar --enlaces`.

## Varios issues por corrida (13-nov-2026)

- **Problema.** `programador.py --aprobaciones` despachaba UN issue por ronda (rotado por hora) porque `naos-aprobar.yml` tiene un solo grupo de concurrencia y GitHub deja un solo disparo en espera: un tercero cancela al segundo. El 13-nov N dio 👍 a las 19:14Z a #1138, #985, #1125, #1158 y #1161 y la ronda de las 19:57Z solo despachó #1161; con 5 tandas la última tardaba 5 h.
- **Ahora.** La ronda manda UN disparo con `issue="1138 985 1125 ..."` (hasta 8, `MAX_APROBAR`; los demás salen como `en espera <n> (tope 8 por disparo)` y los toma la ronda siguiente). La línea de salida es `despachado 1138 985 1125`; `ronda.py` cuenta cada número como un 👍 registrado. Si ese disparo falla, cae al de uno por ronda, rotado por hora, con un AVISO (`TestAprobacionesPorReaccion`).
- **La Action.** `aprobar_varios.sh validar` revisa cada número (solo dígitos, sin repetidos, máximo 8, hasta 9 dígitos); el número llega por la variable `ISSUE`, nunca por `${{ }}` dentro de `run:`. `aprobar_varios.sh correr` procesa en serie, por issue: LFS de sus piezas, `procesar`, `bajar-vetados`, guardar en main (hasta 4 intentos) y avisos. Cada issue deja su propio commit en main (`naos: aprobación registrada (issue #N)`), así que lo de los que salieron bien no se pierde si otro falla o la corrida se corta. Uno que falla comenta en su issue y no frena a los demás; la corrida termina en rojo si alguno falló. Los disparos por comentario y por cierre siguen con su número de siempre.
- **Tiempo.** ~1 min por issue más ~25 s de checkout, una vez. El job tiene `timeout-minutes: 30`; pasados 23 min (`LIMITE_S`) no abre otro issue y lo deja para la ronda siguiente.
- **La compuerta no cambia.** `procesar` decide igual, issue por issue, y solo cuenta el 👍 de `NAOS_APROBADOR`. Pruebas: `AprobarVariosIssues` en `prueba_flujos.py`.
