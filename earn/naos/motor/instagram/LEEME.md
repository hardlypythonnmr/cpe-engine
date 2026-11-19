# motor/instagram

Reels, carruseles, imágenes sueltas e historias de NAOS en Instagram (`naos.v3`) por la API de Instagram con Instagram Login (PROD-08.3, #125).
App de Meta 1890518642122191 sin revisión: alcanza el acceso estándar porque solo publica en la cuenta propia.

## Publicador de Reels: la Action `naos-reel` (decisión de N del 2026-10-18: "GitHub Action publisher (Recommended)")

> **Qué tiene que hacer N (una vez, 3 minutos)**
>
> 1. Agregar el secreto del repo **INSTAGRAM_TOKEN**: en GitHub, `hardlypythonnmr/n-system` > **Settings** > **Secrets and
>    variables** > **Actions** > **New repository secret**. Name: `INSTAGRAM_TOKEN`. Secret: el mismo token que está en
>    `INSTAGRAM_TOKEN` del entorno de Claude (el de naos.v3, generado el 16-oct; si hace falta otro: developers.facebook.com/apps
>    > app 1890518642122191 > Instagram > API setup with Instagram business login > Generate token junto a naos.v3, con el
>    navegador logueado como naos.v3). **Add secret**. Nadie lo ve después, ni en los registros de la Action.
> 2. Cada vez que el token cambie (nuevo o `refrescar`), actualizar ese secreto (Update) y la variable del entorno de Claude.
>    Si es un token nuevo, la sesión corre `ig.py salud --emitido AAAA-MM-DD` con el día en que se generó y hace commit de
>    `token_estado.json` (sin eso la salud diaria avisa "expiry unknown").
> 3. Opcional: `YOUTUBE_API_KEY` como secreto (sin ella el Short se comprueba por oEmbed, que no distingue un video no listado).
> 4. Minutos de Actions: el barrido de respaldo viene APAGADO (el repo ya usa ~74 % de los 2.000 min gratis; con el barrido
>    serían ~950 min más al mes). El camino normal es el despacho de la sesión (~2 min por Reel). Para encenderlo, variable
>    del repo `NAOS_REEL_BARRIDO=on` (Settings > Secrets and variables > Actions > Variables), sabiendo que pasa del plan gratis.

**Cómo la dispara la sesión.** Con la pieza aprobada (fila `reel` en `publicados.csv`) y el Short subido por `subir.py` (que deja
`url_short`), entre 20 minutos antes y 3 horas después de la hora del Short:

```
gh workflow run naos-reel.yml --repo hardlypythonnmr/n-system --ref main -f slug=<slug>
gh run list --workflow naos-reel.yml --limit 3        # para seguirla
```

Si llega antes, sube el mp4 a Pages y duerme hasta la hora del Short + 4 minutos. **Barrido de respaldo**: cada 15 minutos en las
horas UTC de salida de la grilla (0, 13, 19 y 22; si la grilla suma otra hora, agregarla al cron) despacha lo mismo para cada pieza
cuya hora del Short + 4 min pasó, con Reel aprobado y sin publicar, y no más de 3 h tarde.

Qué hace, en orden (los pasos están en `accion_reel.py`; el texto de terceros nunca pasa por el shell):

1. Checkout de main (solo `motor/aprobar`, `motor/instagram`, la carpeta de la pieza) y, con `NAOS_PAGINA_TOKEN`, de
   `hardlypythonnmr/naos` (`data/enlaces.json`, `data/semana.json` y `assets/reels/<slug>.mp4`).
2. `datos`: la fila de aprobación de N para ESE video y ese caption (`registro.verificar`, la misma compuerta de `ig.py`), el
   enlace del Short (`url_short` de la versión aprobada), el título y la cita de N (columna `cita`). Si el Reel ya salió, no hace nada.
3. `pagina`: el mp4 en `https://hardlypythonnmr.github.io/naos/assets/reels/<slug>.mp4`. Si no está, lo copia con `NAOS_PAGINA_TOKEN`,
   empuja a `naos` y espera el despliegue (hasta 15 min). Sin ese secreto falla con la nota: alguien tiene que subirlo a mano.
4. `esperar` hasta la hora del Short + 4 min; `short`: el Short es público y con ese título (`ig.revisar_short`; Data API con
   `YOUTUBE_API_KEY`, si no oEmbed).
5. `publicar`: `ig.py preparar` (espera FINISHED) e `ig.py publicar --ok "<cita de N>"`, con el orden de los Shorts del día.
6. `cerrar`: `aprobar.py cerrar --short --reel --enlaces --semana`: comenta "Live. Short: ... · Reel: ..." como github-actions[bot]
   (N es el autor del issue: le llega el aviso), etiqueta `publicado` y cierra el issue.
7. Guarda `publicados.csv`, `estado.json` y `errores.csv` en main con la identidad `naos-reel` (vuelve a aplicar sobre main
   recién traído, como `naos-aprobar`) y empuja `data/enlaces.json` a `naos`.

Si algo falla: comentario del bot en el issue de la pieza con @N, el error exacto de Meta (HTTP, code, subcode, type, clase y qué
hacer) y la etiqueta `resp:n`; `estado.json` queda con `reel_fallo_utc` y el barrido no reintenta. Reintento: el mismo
`gh workflow run` (la aprobación vale hasta `vence_utc`, 3 h después de la hora). Si el Reel salió pero falló el cierre, el comentario
lo dice con los dos enlaces y la sesión corre `aprobar.py cerrar`.

**Historias, carruseles e imágenes sueltas** (N, 19-oct: "Las historias se aprueban igual que lo demas"). El mismo `gh workflow run naos-reel.yml -f slug=<slug>`
con una pieza de `canales` `["historia"]`, `["carrusel"]` o `["imagen"]`: `datos` verifica la fila `historia` (`hash_historia`), `carrusel` (`hash_carrusel`) o `imagen` (`hash_imagen`),
`pagina` sube las imágenes a `assets/historias/<slug>/`, `assets/carruseles/<slug>/` o `assets/imagenes/<slug>/` de naos, `esperar` duerme hasta `sale_utc` (sin +4 min,
tope 20 min), no hay paso del Short, `publicar` corre `ig.py preparar-/publicar-historia|carrusel|imagen --ok "<cita de N>"` y `cerrar`,
`aprobar.py cerrar --historia|--carrusel|--imagen URL`. Despacharla ~15 min antes de `sale_utc` (acepta de 20 min antes a 3 h después). `publicar --seco` no llama a Meta.

## Segunda cuenta: Mercury

`ig.py` publica en dos cuentas y elige por la pieza, no por una bandera. Una pieza con `"marca": "mercury"` en `cola/aprobar/<slug>/pieza.json`
(o que `registro.marca_delatada` delate como de Mercury) usa solo las credenciales de Mercury. Las de NAOS nunca se usan para ella.

| Nombre | Tipo | Qué es |
|---|---|---|
| `MERCURY_INSTAGRAM_TOKEN` | secreto | token de **usuario del sistema** (no vence) del portafolio comercial "Difficult Decision", con `instagram_basic`, `instagram_content_publish` e `instagram_manage_comments`. Mercury va por **Facebook Login**: `graph.facebook.com/v23.0` (Meta ya no ofrece Instagram Login a apps nuevas) |
| `MERCURY_INSTAGRAM_USER_ID` | variable (en la Action `DD_INSTAGRAM_USER_ID`) | **obligatoria con Facebook Login**: el ID de la cuenta de Instagram de empresa. Si falta, `ig.py --marca mercury cuenta` lo busca con el token (ver abajo) |
| `MERCURY_PAGES_BASE` | variable | URL https pública donde se alojan los mp4 de los Reels de Mercury (`https://<dueño>.github.io/<repo>/assets/reels`). La lee `accion_reel.py` |
| `MERCURY_PAGES_REPO` | variable | `dueño/repo` del sitio aparte de Mercury en GitHub Pages |
| `MERCURY_PAGINA_TOKEN` | secreto | token fino con Contents: Read and write solo en ese repo. Solo lo usa el checkout de `naos-reel.yml` |

- Sin `MERCURY_INSTAGRAM_TOKEN`, `preparar` y `publicar` de una pieza de Mercury salen con "falta MERCURY_INSTAGRAM_TOKEN" y no llaman a Meta. Si esa variable trae el mismo token de NAOS, también se niegan.
- Antes de la primera escritura `ig.py` pregunta `GET /{ig-user-id}?fields=id,username` y exige `@difficultdecisionhq` (con Instagram Login era `me`). Si N cambia el handle, se cambia en `CUENTAS`, en `ig.py`.
- La compuerta no cambia: `registro.exigir` y `publicados.csv` son los mismos para las dos marcas.
- Lo de Mercury queda en archivos aparte: `errores-mercury.csv`, `contenedores-mercury.json`, `token_estado-mercury.json`.
- Órdenes sin slug: `python3 ig.py --marca mercury yo`, `cupo`, `salud`, `cuenta`.
- **Dos caminos, uno por marca** (`CUENTAS[marca]["api"]` en `ig.py`): NAOS `"instagram"` (graph.instagram.com, `me/...`, token de 60 días, sin cambios); Mercury `"facebook"` (graph.facebook.com, las mismas rutas con `me` cambiado por el ID: `/{id}/media`, `/{id}/media_publish`, `/{id}/content_publishing_limit`, `/{id}/stories`, `/{contenedor}?fields=status_code`, `/{media}/comments`, `/{comentario}/replies`). Mismo flujo de contenedor, estado y publicación, misma compuerta de aprobación.
- El token de usuario del sistema no vence: `refrescar` imprime "no aplica" y sale bien; `salud` comprueba token, cuenta y cupo, pero no vigila vencimiento ni pide `--emitido`.
- **Encontrar el ID de la cuenta**: `python3 ig.py --marca mercury cuenta [--negocio <business-id>]` (con `MERCURY_INSTAGRAM_TOKEN` en el entorno). Solo lee. Prueba en orden, imprime lo que devolvió cada ruta (sin el token) y, si Meta da error, muestra code y message y sigue: `GET /me?fields=id,name`; `/me/accounts` (Páginas y su cuenta ligada); `/me/businesses`; y por cada business id (de `/me/businesses`, de la Página o de `--negocio`) `/{id}/owned_instagram_accounts` y `/{id}/instagram_accounts`. Sale 0 e imprime el ID si encuentra `difficultdecisionhq`; si no, sale 1 con el diagnóstico (qué ruta falló y qué falta: `pages_show_list`, `business_management`, cuenta no asignada al usuario del sistema, cuenta no ligada a una Página).

### ¿Publicar con Facebook Login exige una Página de Facebook? (verificado 12-nov-2026)

**Sí.** Fuente: <https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login/overview>: "your app users' Instagram professional accounts must be connected to a Facebook Page." y "Facebook Login serves app users whose Instagram professional account is linked to a Facebook Page." La tabla de requisitos de esa página marca la Página como "Required". La guía <https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login/get-started> lo repite: "A Facebook Page connected to that account" y el usuario "must be able to perform Tasks on the Facebook Page connected to the Instagram account" (MANAGE, CREATE_CONTENT, MODERATE o ADVERTISE). Ahí también se obtiene el ID: `GET /me/accounts` y luego `GET /{page-id}?fields=instagram_business_account` ("Connected IG User ID").

Permisos (misma doc): la guía pide `instagram_basic` y `pages_show_list`. La página de publicación (<https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login/content-publishing>) lista, para Facebook Login for Business, `instagram_basic`, `instagram_content_publish` y `pages_read_engagement` (más `ads_management` y `ads_read` si el rol en la Página viene por Business Manager); para Unified Login, `instagram_basic` e `instagram_content_publish`. Endpoints: `/{ig-user-id}/media` y `/{ig-user-id}/media_publish`. `business_management` NO aparece en esas páginas: no lo exige la API de Instagram; solo sirve para que nuestro `cuenta` lea `/me/businesses` y los bordes de un business id (los permisos del token se piden a Meta por ese lado, no está probado aquí).

- `accion_reel.py` nunca copia un archivo de Mercury a la página de NAOS. Lo copia al checkout de su repo (`pagina --sitio-marca`), con la misma estructura (`assets/reels/`, `assets/historias/`, `assets/carruseles/`, `assets/imagenes/`). Sin `MERCURY_PAGES_BASE` o sin `MERCURY_PAGES_REPO` se niega en el paso `datos`; también si apuntan al sitio o al repo de NAOS, o si el checkout que llega no es el de ese repo.

Para que un Reel, imagen, carrusel o historia de Mercury salga sin sesión (11-nov-2026): `naos-reel.yml` lee la marca de la pieza y, si es de Mercury, usa
`MERCURY_INSTAGRAM_TOKEN`; `mercury-publicar.yml` lo despacha cada 30 minutos (`programador.py --marca mercury --despachar`); `naos-ig-salud.yml` comprueba
también ese token si el secreto existe. El agente aprueba Instagram de Mercury solo con `agente.json` `marcas.mercury.instagram` en `true` (nace en `false`).
Falta la primera corrida real. Pasos del dueño para el sitio: `empresa/duplicar/canal-lucro/mercury/linea/SITIO-MERCURY.md`; lo demás, `linea/PUBLICAR.md`.

## Salud del token y errores de Meta

- `python3 ig.py salud [--emitido AAAA-MM-DD]`: token vivo, de naos.v3 (user_id 17841452348710663), cupo usado y vencimiento.
  Sale con 1 si el token no sirve o vence en 10 días o menos. El vencimiento sale de `debug_token` si algún día responde (hoy
  Instagram Login da 403) o de `token_estado.json`, que guarda por huella (12 hex de sha256, nunca el token) la emisión y el
  vencimiento. `--emitido` anota el token actual. Comprobado el 2026-10-18: OK, vence 2026-12-15.
- `.github/workflows/naos-ig-salud.yml` lo corre cada día a las 12:30 UTC; si falla, comenta en la bitácora #544 como bot con @N y
  la razón (la mención va en el comentario porque un comentario del bot no dispara `naos-avisar`). Reintenta una vez un error transitorio.
- Cada error de Meta queda en `errores.csv` (hora UTC, método, ruta sin parámetros, HTTP, code, error_subcode, type, clase,
  is_transient, fbtrace_id, mensaje sin token). Clases: INVALIDADO (subcode 460/467 o "session has been invalidated": generar
  otro), VENCIDO (463), CHECKPOINT (459/464/2207050: N entra a la app como naos.v3 y resuelve), APP_QUITADA (458), PERMISO (10,
  200-299), MEDIA (2207xxx), TRANSITORIO (1, 2, 4, 17, 32, 341, 613, is_transient o HTTP 5xx), TOKEN (otro 190), OTRO.
- `token()`: manda `INSTAGRAM_TOKEN`; el archivo `~/.config/naos/instagram_token` solo si la variable falta.
- `python3 ig.py refrescar`: renueva el token, lo deja en ese archivo (600), anota su vencimiento en `token_estado.json` e imprime la
  fecha y dónde guardarlo (secreto del repo con `gh secret set INSTAGRAM_TOKEN --repo hardlypythonnmr/n-system < archivo`, y el
  entorno de Claude). Nunca imprime el token.

## A mano, desde la sesión

Paso a paso de una pieza (el Short sale primero; el Reel nunca antes que su Short):

1. N aprueba la pieza en su issue (`ok` o 👍, ver `../aprobar/LEEME.md`). La Action escribe su aprobación en
   `publicados.csv` con la huella del video y el caption; hacer `git pull` antes de seguir.
2. El Short ya está público en YouTube (`youtube/subir.py ... --slug <pieza>`, que tampoco sube sin esa aprobación ni antes de la hora aprobada si es `--publico`).
3. El mp4 va a `assets/reels/<slug>.mp4` en `hardlypythonnmr/naos` (push a main, esperar el despliegue de Pages).
4. `python3 ig.py revisar <url> --caption caption.txt --short-url <enlace del Short> --titulo "<título del Short>" --archivo <mp4>
   [--clave AAAA-MM-DD|slot --semana semana.json --enlaces enlaces.json]`: revisión sin llamar a Meta. Falla si el caption no trae
   el pie "More today: link in bio. Not financial advice." ni el título del Short; si el Short no es público de verdad (Data API
   `videos.list part=status`: `privacyStatus=public`, sin `publishAt` futuro y procesado; con `YOUTUBE_API_KEY`. Un video privado o
   programado no vuelve con la llave. Sin llave usa oEmbed, que da 404/400 para privados pero no distingue uno no listado); si el título
   en YouTube no es el mismo; o si una pieza anterior del mismo día tiene Short y todavía no Reel (orden de los Shorts).
5. `python3 ig.py preparar <slug> <url> --caption caption.txt --short-url <enlace> --archivo <mp4>`: contenedor en Meta,
   nada público; anota en `contenedores.json` la huella de lo preparado. **El Reel sale solo en la pestaña de Reels**
   (`share_to_feed=false`) y el grid queda para los carruseles; `--con-feed` lo muestra también en el grid (`--sin-feed` sigue
   aceptándose, pero ya es lo normal). `share_to_feed` figura en la referencia oficial de IG User Media, solo para Reels
   (`true` = pestañas Feed y Reels, `false` = solo Reels).
6. `python3 ig.py publicar <slug> <contenedor> --ok "<cita de N>" --short-url <enlace> --archivo <mp4> --caption caption.txt`.
   La compuerta exige la fila de aprobación de N para ESE video y ese caption; si algo cambió después del `ok`, se niega
   aunque llegue `--ok`. La cita sale de la columna `cita` de `publicados.csv`. Al publicar, `ig.py` completa esa fila con
   el enlace del Reel y `aprobar.py cerrar --enlaces` cierra el issue y escribe el enlace en `enlaces.json` de la página.

Token de 60 días: `python3 ig.py refrescar` (ver "Salud del token" arriba).
Comprobado el 2026-10-14: `yo` y `cupo` responden (MEDIA_CREATOR, 0 de 100 publicaciones en 24 h).
Punta a punta el 2026-10-14: E13 en `https://hardlypythonnmr.github.io/naos/assets/reels/e13.mp4`, contenedor
18017987081744958 en FINISHED, sin publicar (vence solo a las 24 h). Trial Reels: Meta pide más seguidores
(error 2207081 con 3 seguidores).

## Carrusel (panorámico que se une al deslizar)

Un carrusel es una sola publicación de hasta **10 láminas** (límite oficial de hoy; no 20), todas JPEG de 1080x1350 (4:5). Una
imagen ancha de N x 1080 por 1350 se corta en N láminas exactas: al deslizar parece una sola pieza. Va solo: sin Short, sin
`--short-url` ni orden de Shorts. No lleva video (los hijos podrían ser video, pero aquí son imágenes).

1. **Imagen ancha.** N x 1080 de ancho por 1350 de alto, N de 2 a 10 (hasta 10.800 x 1350). Ideas para que se guarde y se comparta:
   la lámina 1 tiene que valer sola en el grid (es la que se ve); un elemento que cruce cada costura invita a deslizar; la
   última lámina cierra o devuelve a la primera. Todas se recortan según la primera, por eso todas miden lo mismo.
2. **Cortar.** `python3 carrusel.py panoramica.png --salida laminas/ --prefijo noche` deja `noche-1.jpg ... noche-N.jpg`
   (JPEG sRGB 4:4:4 sin EXIF; la costura no deja marca) y las revisa. Pruebas: `python3 prueba_carrusel.py`. Requiere Pillow.
3. **Aprobación de N.** Pieza en `cola/aprobar/<slug>/` con `"canales": ["carrusel"]`, `"laminas": ["noche-1.jpg", ...]` (en orden,
   dentro de esa carpeta), `caption`, `titulo`, `sale_utc` y `datos_utc` (o `"sin_cifras": true`); sin `video.mp4`. Se abre con
   `python3 ../aprobar/aprobar.py abrir <slug>` (la vista previa muestra las láminas en orden). Cuando N responde `ok` o pone 👍,
   `publicados.csv` recibe una fila de canal `carrusel` cuya huella es el hash de **todas las láminas en orden + el caption**.
   Cambiar una lámina, el orden o una coma anula la aprobación (`aprobar.py version`). `git pull` antes de seguir.
4. **Subir las láminas** a una URL pública (por ejemplo `assets/carruseles/<slug>/noche-1.jpg ...` en `hardlypythonnmr/naos`,
   push a main, esperar Pages). Solo lo que N aprobó.
5. **Revisar.** `python3 ig.py revisar-carrusel <url1> ... <urlN> --archivos noche-1.jpg ... noche-N.jpg --caption caption.txt`.
   Sin llamar a Meta (solo un HEAD a cada URL). Falla si: no son de 2 a 10; una no es JPEG (o es MPO), pesa más de 8 MB, no es 4:5
   o mide distinto; la URL no es https, no devuelve `image/jpeg` o pesa distinto que el archivo local; el caption pasa de 2.200
   caracteres, de 30 hashtags, o no trae el pie "More today: link in bio. Not financial advice."
6. **Preparar.** `python3 ig.py preparar-carrusel <slug> <url1> ... <urlN> --archivos ... --caption caption.txt`: un contenedor hijo por
   lámina (`image_url` + `is_carousel_item=true`), espera a que cada uno termine, crea el contenedor `media_type=CAROUSEL` con
   `children` (los ids en orden) y el caption, y anota en `contenedores.json` la huella. Nada sale público; vence a las 24 h.
7. **Publicar.** `python3 ig.py publicar-carrusel <slug> <contenedor> --ok "<cita de N>" --archivos ... --caption caption.txt`.
   Exige la fila de N del canal `carrusel` con esa huella (sin ella, o con otras láminas, otro orden u otro caption, se niega
   aunque llegue `--ok`; el `--ok` de un Reel o un Short no sirve), que el contenedor se haya preparado con esa huella y que esté
   en FINISHED. Completa la fila con el enlace (columna `url_reel`), el contenedor y el `media_id`.
8. **Cerrar.** `python3 ../aprobar/aprobar.py cerrar <slug> --carrusel https://www.instagram.com/p/<id>/`.

Documentación oficial (comprobada el 2026-10-15): límites del carrusel en
<https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/content-publishing>
("Carousels are limited to 10 images, videos, or a mix of the two"; solo JPEG, no MPO; se recorta según la primera imagen; el
carrusel cuenta como una publicación) y parámetros (`children` hasta 10 ids, `is_carousel_item`, `share_to_feed`; imagen JPEG de
8 MB, relación entre 4:5 y 1.91:1, ancho 320 a 1440) en
<https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media>.
La misma página dice 100 publicaciones por API en 24 h y, en la sección de carruseles, 50: `ig.py cupo` dice la cifra real de la cuenta.

## Imagen suelta del feed

Una publicación de **una sola imagen** con caption: JPEG de 1080x1350 (4:5), hasta 8 MB, no MPO. Va sola (`"canales": ["imagen"]`,
`"archivo": "imagen.jpg"`). Sale con la misma Action que el carrusel (`naos-reel.yml`, despacho por slug; la imagen se sube a
`assets/imagenes/<slug>/imagen.jpg` de naos y de ahí sale la URL pública).

1. **Aprobación de N.** Pieza en `cola/aprobar/<slug>/` con `pieza.json` (`slug`, `titulo`, `sale_utc`, `canales: ["imagen"]`, `archivo`,
   `caption` con "link in bio" (salvo `"formato": "una-linea"`, D-361), `sin_cifras` o `datos_utc`). `python3 ../aprobar/aprobar.py abrir <slug>`; la vista previa muestra la
   imagen y el caption. La fila de `publicados.csv` es de canal `imagen` y su huella es el hash del **archivo + el caption**.
2. **Revisar.** `python3 ig.py revisar-imagen <url> --archivo imagen.jpg --caption caption.txt`: JPEG de 1080x1350, la URL https
   devuelve `image/jpeg` y pesa lo mismo que el archivo, caption de 2.200 caracteres o menos, 30 hashtags o menos, con "link in bio" (con `--formato una-linea`
   no se exige, D-361; la Action lo pasa desde pieza.json).
3. **Preparar.** `python3 ig.py preparar-imagen <slug> <url> --archivo imagen.jpg --caption caption.txt`: crea el contenedor con
   `image_url` y `caption`, sin `media_type` (así se crea una imagen en la API con Instagram Login), espera FINISHED y anota la huella.
   Nada sale público.
4. **Publicar.** `python3 ig.py publicar-imagen <slug> <contenedor> --ok "<cita de N>" --archivo imagen.jpg --caption caption.txt`.
   Exige la fila de N del canal `imagen` con esa huella (otro archivo u otro caption, o la aprobación de otro canal, se niega), que el
   contenedor se haya preparado con ella y que esté en FINISHED. Completa la fila con el enlace (`url_reel`), el contenedor y el `media_id`.
5. **Cerrar.** `python3 ../aprobar/aprobar.py cerrar <slug> --imagen https://www.instagram.com/p/<id>/`.

Pruebas: `python3 ../aprobar/prueba_aprobar.py` (clase `TestImagen`) y `python3 prueba_ig.py` (clase `AccionReelImagen`). Requieren Pillow.

## Historia (media_type=STORIES)

Una historia es **un solo archivo**: una imagen JPEG de 1080x1920 (9:16) o un video 9:16. Dura 24 horas y no se ve en el grid. Va sola:
sin Short, sin `--short-url` y sin orden de Shorts. **No lleva caption**: la referencia de IG User Media no lista `caption` para
historias y sus ejemplos no lo usan; tampoco acepta `alt_text` ni `collaborators`, y no se pueden publicar stickers (enlace, encuesta,
ubicación). Por eso el contenedor lleva solo `media_type=STORIES` y `image_url` o `video_url`, y la huella aprobada es el hash del archivo.

1. **Archivo.** Imagen: JPEG común (no MPO), sRGB, hasta 8 MB, exactamente 1080x1920. Video: 9:16, de 3 a 60 s, hasta 100 MB, H.264 o
   HEVC con audio AAC (los mismos códecs de los Reels). La doc oficial dice "9:16 recomendado"; la casa exige 1080x1920 en las imágenes.
2. **Aprobación de N.** Pieza en `cola/aprobar/<slug>/` con `"canales": ["historia"]` y `"archivo": "historia.jpg"` (o `.mp4`), `titulo`
   (interno, no sale), `sale_utc` y `datos_utc` (o `"sin_cifras": true`); sin `caption` (si lo lleva, `abrir` lo marca Fix: no se publicaría).
   `python3 ../aprobar/aprobar.py abrir <slug>`. Cuando N responde `ok` o pone 👍, `publicados.csv` recibe una fila de canal `historia` con
   el hash del archivo. Cambiar el archivo anula la aprobación (`aprobar.py version`). `git pull` antes de seguir.
3. **Subir el archivo** a una URL pública (por ejemplo `assets/historias/<slug>.jpg` en `hardlypythonnmr/naos`, push a main, esperar Pages).
   Solo lo que N aprobó.
4. **Revisar.** `python3 ig.py revisar-historia <url> --archivo historia.jpg`. Sin llamar a Meta (solo un HEAD a la URL). Falla si el
   archivo no es JPEG ni .mp4/.mov, si la imagen es MPO, pesa más de 8 MB o no mide 1080x1920, si el video dura menos de 3 s o más de
   60 s, pesa más de 100 MB, no es 9:16, ni H.264/HEVC, ni AAC; o si la URL no es https, no devuelve `image/jpeg` (o `video/mp4`) o
   pesa distinto que el archivo local.
5. **Preparar.** `python3 ig.py preparar-historia <slug> <url> --archivo historia.jpg`: crea el contenedor `STORIES`, espera FINISHED y anota
   la huella en `contenedores.json`. Nada sale público; vence a las 24 h.
6. **Publicar.** `python3 ig.py publicar-historia <slug> <contenedor> --ok "<cita de N>" --archivo historia.jpg`. Exige la fila de N del
   canal `historia` con esa huella (sin ella, o con otro archivo, se niega aunque llegue `--ok`; la aprobación de un Reel, un Short o un
   carrusel no sirve), que el contenedor se haya preparado con esa huella y que esté en FINISHED. Completa la fila con el enlace
   (columna `url_reel`), el contenedor y el `media_id`.
7. **Cerrar.** `python3 ../aprobar/aprobar.py cerrar <slug> --historia https://www.instagram.com/stories/<usuario>/<id>/`.

Fuera a propósito: `user_tags` en historias (la doc lo admite desde el 9-jul-2025, con x/y opcionales). No va en `ig.py` porque no entraría
en la huella y N no lo vería en la vista previa; si se agrega, tiene que entrar al hash y a la vista previa antes que a la API.
No está documentado si las historias cuentan para el tope de 100 publicaciones por API en 24 h: `ig.py cupo` dice cuánto se usó.

## Qué se puede y qué no (con el token de hoy)

Token de Instagram Login de `naos.v3` (cuenta MEDIA_CREATOR, app 1890518642122191, acceso estándar, solo cuenta propia). Instagram Login no
tiene endpoint para listar los permisos concedidos: `GET me/permissions` responde 400 ("nonexisting field") y `debug_token` responde 403
("Application does not have permission", código 10). Los permisos de abajo se **infieren de lecturas que respondieron 200 el 2026-10-15**
(solo GET, sin crear contenedores): `me?fields=...` y `me/stories` (instagram_business_basic), `me/content_publishing_limit` (publicar:
instagram_business_content_publish; usadas 2 de 100), `<media>/comments` (instagram_business_manage_comments), `me/conversations`
(instagram_business_manage_messages) y `me/insights` (reach). Una escritura de comentarios no se probó.

Acceso estándar alcanza para todo lo "Sí": la doc dice que sirve si uno es dueño o administra la cuenta y la agregó a la app; Advanced Access
(App Review y verificación de empresa) es para cuentas ajenas
(<https://developers.facebook.com/docs/instagram-platform/overview>,
<https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/comment-moderation>).

| Qué | Estado hoy | Permiso o razón | Fuente |
|---|---|---|---|
| Publicar Reel, carrusel, imagen e historia (`media_type`: `REELS`, `CAROUSEL`, `STORIES`) | Sí. Ya en uso | `instagram_business_content_publish` (+ `instagram_business_basic`) | <https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/content-publishing> |
| Historia: imagen JPEG hasta 8 MB, 9:16 recomendado; video de 3 a 60 s, hasta 100 MB | Sí, con el permiso de publicar | Sin permiso extra | <https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media> |
| Historia: `caption` | No existe para historias (no figura; los ejemplos no lo llevan) | No es cuestión de permiso | <https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media> |
| Historia: `alt_text`, `collaborators`, stickers de enlace, encuesta y ubicación | No existe ("not supported" para alt_text y collaborators; stickers "cannot be published") | No es cuestión de permiso | <https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media> |
| Historia: mencionar usuarios con `user_tags` (x/y opcionales, desde el 9-jul-2025) | Sí, con el permiso de publicar. No usado en `ig.py` (ver arriba) | Sin permiso extra | <https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media> |
| Leer comentarios, responder (`POST <comentario>/replies`), comentar (`POST <media>/comments`), ocultar y borrar | Sí. La lectura de `<media>/comments` respondió 200 con este token; la escritura no se probó | `instagram_business_manage_comments`; acceso estándar en cuenta propia. Límites: solo se responde a comentarios de primer nivel, no a ocultos, y no a comentarios de Live | <https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/comment-moderation>, <https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-media/comments>, <https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-comment/replies> |
| `collaborators` en Reels, carruseles e imágenes (hasta 3 usuarios) | No hoy. La función está rotulada "Facebook Login for Business only"; la guía de publicación con Instagram Login no la menciona | Pide pasar a Facebook Login para Business (Página vinculada, `instagram_basic`, `instagram_content_publish`, `pages_read_engagement`): es otra integración, no un permiso suelto. No probado con graph.instagram.com | <https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login/collaboration>, <https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media> |
| `location_id` (imagen, video, Reel; no en hijos de carrusel) | No hoy en la práctica. El parámetro es del contenedor, pero pide el ID de una Página con ubicación y se busca con Pages Search | Pages Search pide la función Page Public Metadata Access (token de app o de usuario de Facebook). No hay Página ni Facebook Login en nuestra integración. App Review: la doc de Pages Search no lo dice | <https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media>, <https://developers.facebook.com/docs/pages-api/search-pages> |
| `user_tags` en imágenes, videos y Reels (imágenes exigen x/y entre 0.0 y 1.0) | Sí, documentado con el permiso de publicar. No probado ni usado | Sin permiso extra | <https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media> |
| `cover_url` y `thumb_offset` en Reels | Sí. Ya en `ig.py` (`--portada-url`, `--portada-ms`) | Sin permiso extra. `cover_url`: JPEG hasta 8 MB, sRGB, 9:16 recomendado; si van los dos, gana `cover_url` | <https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media> |
| `audio_name` en Reels | Sí, con el permiso de publicar. No usado en `ig.py` | Sin permiso extra. Se puede renombrar una sola vez (al crear o desde la página del audio) | <https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media> |
| `alt_text` en imagen única o imagen de carrusel (hasta 1.000 caracteres) | Sí, con el permiso de publicar. No usado en `ig.py` | Sin permiso extra. No vale en Reels ni historias | <https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media> |
| Etiquetas de producto, hashtag search, Partnership Ads (`is_paid_partnership`) | No existe con Instagram Login | Solo Facebook Login | <https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/overview>, <https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media> |

Dudas que la doc deja abiertas: (1) la referencia de comentarios por Instagram Login nombra `instagram_business_manage_comments`, pero las
páginas de `replies` y de `media` enumeran solo los permisos de Facebook Login; (2) la página de permisos
(<https://developers.facebook.com/docs/permissions>) pide caso de uso y screencast para `instagram_business_*`, lo que apunta a App Review,
aunque la guía de moderación dice que el acceso estándar basta en cuenta propia; (3) `me/insights` y `me/conversations` respondieron 200 aunque la
página de resumen no lista insights entre los permisos de Instagram Login. La prueba real (un `POST <comentario>/replies` sobre una
publicación propia) la hace N cuando quiera, porque escribe en la cuenta.

Pruebas con Meta de mentira (sin red): `python3 ../aprobar/prueba_aprobar.py` y `python3 prueba_ig.py` (token, errores, salud,
refrescar y los pasos de `accion_reel.py`).
