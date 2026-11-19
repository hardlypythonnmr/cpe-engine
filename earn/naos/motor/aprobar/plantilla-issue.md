# Plantilla de los issues de aprobación (OPS-06.1)

aprobar.py lee este archivo por secciones (`<!-- seccion: x -->`) y reemplaza `{{campo}}`. Los textos van en inglés
(los lee N en el celular); las notas van en español. Sin rayas largas, sin consejo financiero. La vista previa no suma
color ni fuente: es Markdown de GitHub. Cada comentario de Claude lleva un marcador `<!-- naos:... -->` para que
aprobar.py nunca lo confunda con una palabra de N.

<!-- seccion: titulo -->
Approve: {{titulo}} · {{canales}} · {{sale_corta}}

<!-- seccion: cuerpo -->
@{{aprobador}} one piece is waiting for you. Preview below.

{{estado_linea}}

<!-- naos:cuerpo -->

<!-- seccion: toque -->
**Tap 👍 on this post or under the preview, or reply ok, to approve. Any other comment stops this version until I post a new one. No answer = not published.**

<!-- seccion: primera_vez -->
> First time here. 👍 on this post or under the preview, or the word `ok` in a comment, is your approval.
> After it, the piece uploads to YouTube (private, scheduled) and the Reel follows the Short.
> To stop it, comment what to change or tap 👎: that version stays stopped until I post a new one. Nothing goes out without your approval.

<!-- seccion: fix -->
**Not ready: {{n_fix}} item(s) marked Fix below. Approval is not requested until they are fixed.**

<!-- seccion: vista_previa -->
## Preview v{{version}}

![Cover]({{portada_url}})

[Watch the video (9:16)]({{video_url}})

**Title:** {{titulo}}

**Goes out:** {{sale_larga}}

### Caption (Instagram Reel)
{{caption}}

### Description (YouTube Short)
{{descripcion}}

### Declarations
{{declaraciones}}

### Checks
| Check | Result | Note |
|---|---|---|
{{revisiones}}

{{linea_toque}}

<!-- naos:preview v={{version}} hash={{hash}} -->

<!-- seccion: vista_previa_carrusel -->
## Preview v{{version}}

Carousel of {{n}} slides, in order. They are meant to join into one wide image when you swipe.

{{laminas}}

**Title:** {{titulo}}

**Goes out:** {{sale_larga}}

### Caption (Instagram carousel)
{{caption}}

### Declarations
{{declaraciones}}

### Checks
| Check | Result | Note |
|---|---|---|
{{revisiones}}

{{linea_toque}}

<!-- naos:preview v={{version}} hash={{hash}} -->

<!-- seccion: vista_previa_imagen -->
## Preview v{{version}}

Single image post for the Instagram feed (4:5).

{{imagen}}

**Title (internal, not published):** {{titulo}}

**Goes out:** {{sale_larga}}

### Caption (Instagram image)
{{caption}}

### Declarations
{{declaraciones}}

### Checks
| Check | Result | Note |
|---|---|---|
{{revisiones}}

{{linea_toque}}

<!-- naos:preview v={{version}} hash={{hash}} -->

<!-- seccion: vista_previa_historia -->
## Preview v{{version}}

Instagram Story (9:16). It stays up 24 hours. Stories carry no caption through the API.

{{medio}}

**Title (internal, not published):** {{titulo}}

**Goes out:** {{sale_larga}}

### Declarations
{{declaraciones}}

### Checks
| Check | Result | Note |
|---|---|---|
{{revisiones}}

{{linea_toque}}

<!-- naos:preview v={{version}} hash={{hash}} -->

<!-- seccion: aprobado -->
Approved {{hora}} UTC. Uploading to YouTube and Instagram.

<!-- naos:aprobado -->

<!-- seccion: cambio -->
Got it. New version below. Your 👍 on v{{anterior}} no longer counts.

<!-- naos:cambio -->

<!-- seccion: publicado -->
Live. Short: {{url_short}} · Reel: {{url_reel}}

<!-- naos:publicado -->

<!-- seccion: publicado_carrusel -->
Live. Carousel: {{url_carrusel}}

<!-- naos:publicado -->

<!-- seccion: publicado_imagen -->
Live. Image: {{url_imagen}}

<!-- naos:publicado -->

<!-- seccion: publicado_historia -->
Live for 24 hours. Story: {{url_historia}}

<!-- naos:publicado -->

<!-- seccion: error -->
Not published: {{causa}}. Nothing went live. Fix and I retry.

@{{aprobador}}

<!-- naos:error -->

<!-- seccion: caducado -->
This approval expired ({{motivo}}). Nothing went live. A new preview and a new 👍 are needed.

<!-- naos:caducado -->

<!-- seccion: vacio -->
Nothing waiting. Next piece: {{siguiente}}.

<!-- seccion: tanda_titulo -->
Approve batch: {{nombre}} · {{n}} pieces · {{desde}} to {{hasta}}

<!-- seccion: tanda_cuerpo -->
@{{aprobador}} a batch of {{n}} pieces is waiting for you. Each preview is in its own comment below. The approval is the last comment.

{{estado_linea}}

<!-- naos:cuerpo -->

<!-- seccion: tanda_toque -->
**Tap 👍 on this post or on the last comment, or reply ok, to approve the whole batch. To drop a piece, comment `no <slug>`; the rest still goes. Any other comment stops the whole batch until I post a new version. No answer = nothing published.**

<!-- seccion: tanda_toque_pieza -->
*Part of the batch. You approve once, in the last comment of this post.*

<!-- seccion: tanda_pieza -->
# Piece {{i}} of {{n}} · `{{slug}}`

<!-- seccion: tanda_resumen -->
## Batch {{nombre}} v{{version}}: {{n}} pieces

| # | Piece | Title | Goes out | Channels |
|---|---|---|---|---|
{{filas}}

**Tap 👍 under this comment (or on the post), or reply ok, to approve ALL the pieces above.**
**To drop one, comment `no <slug>` (for example `no {{ejemplo}}`; several slugs in one comment work); the rest still goes.**
**Any other comment, or 👎, stops the whole batch until I post a new version. No answer = nothing published.**

<!-- naos:tanda v={{version}} -->

<!-- seccion: tanda_aprobado -->
Approved {{hora}} UTC. {{n}} piece(s) registered: {{lista}}.{{extra}} Uploading to YouTube and Instagram on their own schedule.

<!-- naos:aprobado -->

<!-- seccion: tanda_vetado -->
Noted. Dropped: {{lista}}. They will not go out. {{resto}}

<!-- naos:vetado -->

<!-- seccion: tanda_cambio -->
Got it. New version of the batch below. Your 👍 on v{{anterior}} no longer counts.

<!-- naos:cambio -->

<!-- seccion: tanda_publicada -->
Live: `{{slug}}`. Short: {{url_short}} · Reel: {{url_reel}}

<!-- naos:publicado -->

<!-- seccion: tanda_titulo_vp -->
Tanda del VP (D-274): veto de N hasta {{hasta}}

<!-- seccion: tanda_cuerpo_vp -->
@{{aprobador}} el VP aprobó estas {{n}} piezas (D-274, D-322): historias, carruseles y regresos de conductas que ya salieron con tu 👍. Tu veto está abierto hasta {{hasta}}; antes de esa hora no sale nada.

| Pieza | Qué es | Origen | Por qué no cae en "Qué no cubre" |
|---|---|---|---|
{{filas}}

**Para vetar una pieza: 👎 en su vista previa, o comenta `no <slug>`; las demás siguen. Cualquier otro comentario, o 👎 en este post, frena toda la tanda. Tu 👍 la vuelve aprobación tuya. Sin respuesta, cada pieza sale a su hora cuando vence el veto.**

<!-- naos:cuerpo -->

<!-- seccion: tanda_resumen_vp -->
## Tanda del VP {{nombre}} v{{version}}: {{n}} piezas

| # | Pieza | Título | Sale | Canales |
|---|---|---|---|---|
{{filas}}

**Veto de N hasta {{hasta}}. `no <slug>` (por ejemplo `no {{ejemplo}}`) o 👎 en la vista previa de una pieza la quita. Cualquier otro comentario, o 👎, frena toda la tanda. Tu 👍 aquí la vuelve aprobación tuya.**

<!-- naos:tanda v={{version}} -->

<!-- seccion: vp_aprobado -->
Aprobada por el VP (D-274, D-322) a las {{hora}} UTC: {{lista}}. Veto de N abierto hasta {{hasta}} ({{hasta_utc}}): nada sale antes. Cita de las filas: {{cita}}

<!-- naos:vp -->

<!-- seccion: vp_veto -->
Veto de N desde la mesa, pasado por el VP con su cita literal: «{{cita}}». Fuera: {{lista}}. No salen.

<!-- naos:vp-veto -->

<!-- seccion: tanda_titulo_agente -->
Tanda del agente (D-461): veto de N hasta {{hasta}}

<!-- seccion: tanda_cuerpo_agente -->
@{{aprobador}} el agente aprobó estas {{n}} piezas (D-461): pasaron el corte, el lector estético y el lente de cumplimiento, y no tocan duelo, soledad, salud mental ni cuerpo. Tu veto está abierto hasta {{hasta}}; antes de esa hora no sale nada.

| Pieza | Marca | Puntaje | Lector estético | Lente |
|---|---|---|---|---|
{{filas}}

**Para vetar una pieza: 👎 en su vista previa, o comenta `no <slug>`; las demás siguen. Cualquier otro comentario, o 👎 en este post, frena toda la tanda. Tu 👍 la vuelve aprobación tuya. Sin respuesta, cada pieza sale a su hora cuando vence el veto.**

<!-- naos:cuerpo -->

<!-- seccion: tanda_cuerpo_agente_d520 -->
@{{aprobador}} el agente aprobó estas {{n}} piezas de Done Damages por D-520 (tu decisión del 16-nov: "It should approve everything from dd and batch batches into just one approval from my side"; el 17-nov pediste que las firme el agente y no tu cuenta). Pasaron la revisión de ley y verdad de la línea; lo que el revisor marcó sensible no está aquí, va a tu tanda. Tu veto está abierto hasta {{hasta}}; antes de esa hora no sale nada. Los Shorts, además, se pueden vetar hasta 12 horas después de publicar.

| Pieza | Marca | Puntaje | Lector estético | Lente |
|---|---|---|---|---|
{{filas}}

**Para vetar una pieza: 👎 en su vista previa, o comenta `no <slug>`; las demás siguen. Cualquier otro comentario, o 👎 en este post, frena toda la tanda. Tu 👍 la vuelve aprobación tuya. Sin respuesta, cada pieza sale a su hora cuando vence el veto.**

<!-- naos:cuerpo -->

<!-- seccion: tanda_resumen_agente -->
## Tanda del agente {{nombre}} v{{version}}: {{n}} piezas

| # | Pieza | Título | Sale | Canales |
|---|---|---|---|---|
{{filas}}

**Veto de N hasta {{hasta}}. `no <slug>` (por ejemplo `no {{ejemplo}}`) o 👎 en la vista previa de una pieza la quita. Cualquier otro comentario, o 👎, frena toda la tanda. Tu 👍 aquí la vuelve aprobación tuya.**

<!-- naos:tanda v={{version}} -->

<!-- seccion: agente_aprobado -->
Aprobada por el agente (D-461) a las {{hora}} UTC: {{lista}}. Veto de N abierto hasta {{hasta}} ({{hasta_utc}}): nada sale antes. Cita de las filas: {{cita}}

<!-- naos:agente -->

<!-- seccion: agente_plantilla_despues -->
Carril de plantilla (D-503, D-505): {{lista}}. Tu veto sigue abierto después de publicar, hasta 12 horas después de la hora de salida (cerca de {{hasta}}, {{hasta_utc}}). Para vetar una sola pieza: 👎 en su vista previa, o comenta `no <slug>` (por ejemplo `no {{ejemplo}}`). Su Short se pasa a privado solo y las demás siguen arriba; el agente no se frena. Cualquier otro comentario, 👎 en el post o cerrar el issue quitan todas las de esta tanda. Pasadas las 12 horas ya no se baja solo: se baja en Studio. Esto baja el Short de YouTube y nada más: si publicaste por otro camino una pieza de Instagram del mismo tema, esa se borra a mano en la app.

<!-- naos:agente-plantilla -->

<!-- seccion: agente_d520_despues -->
D-520 (todo lo de DD, veto después como D-505): {{lista}}. Tu veto sigue abierto después de publicar, hasta 12 horas después de la hora de salida (cerca de {{hasta}}, {{hasta_utc}}). Para vetar una sola pieza: 👎 en su vista previa, o comenta `no <slug>` (por ejemplo `no {{ejemplo}}`). Su Short se pasa a privado solo y las demás siguen arriba; el agente no se frena. Cualquier otro comentario, 👎 en el post o cerrar el issue quitan todas las de esta tanda. Pasadas las 12 horas ya no se baja solo: se baja en Studio. Esto baja el Short de YouTube y nada más: una pieza de Instagram ya publicada se borra a mano en la app.

<!-- naos:agente-d520 -->

<!-- seccion: tanda_titulo_agente_viva -->
Agente (D-461), cifra viva: sale a su hora; veto de N hasta {{hasta}}

<!-- seccion: tanda_cuerpo_agente_viva -->
@{{aprobador}} el agente aprobó estas {{n}} piezas de Mercury por el carril de cifra viva (D-461; tu decisión del 11-nov): pasaron el corte, el lector estético y el lente, y no tocan lo sensible ni lo que Mercury nunca saca solo. **Salen a su hora sin esperar tu veto.** Justo antes de subir se vuelve a leer cada cifra contra su fuente: si cambió, no sale. Tu veto queda abierto hasta 12 horas después de publicar (cerca de {{hasta}}).

| Pieza | Marca | Puntaje | Lector estético | Lente |
|---|---|---|---|---|
{{filas}}

**Para vetar una pieza, antes o después de que salga: 👎 en su vista previa, o comenta `no <slug>`. Cualquier otro comentario, 👎 en este post o cerrar el issue frenan todo. Si ya es pública, el Short se pasa a privado. Tu 👍 la vuelve aprobación tuya.**

<!-- naos:cuerpo -->

<!-- seccion: tanda_resumen_agente_viva -->
## Tanda del agente, cifra viva, {{nombre}} v{{version}}: {{n}} piezas

| # | Pieza | Título | Sale | Canales |
|---|---|---|---|---|
{{filas}}

**Sale a su hora, después de releer la cifra. Veto de N hasta 12 h después de publicar (cerca de {{hasta}}). `no <slug>` (por ejemplo `no {{ejemplo}}`) o 👎 en la vista previa de una pieza la quita y, si ya es pública, se pasa a privado. Cualquier otro comentario, o 👎, frena toda la tanda. Tu 👍 aquí la vuelve aprobación tuya.**

<!-- naos:tanda v={{version}} -->

<!-- seccion: agente_viva_aprobado -->
Aprobada por el agente (D-461) por el carril de cifra viva a las {{hora}} UTC: {{lista}}. Sale a su hora si la relectura de la cifra da igual; si cambió, no sale. Veto de N abierto hasta 12 h después de publicar (cerca de {{hasta}}, {{hasta_utc}}). Cita de las filas: {{cita}}

<!-- naos:agente -->

<!-- seccion: agente_veto -->
Veto de N desde la mesa, pasado por el agente con su cita literal: «{{cita}}». Fuera: {{lista}}. No salen.

<!-- naos:agente-veto -->
