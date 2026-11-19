# comentarios: leer, clasificar, escalar y responder (YouTube e Instagram)

Biblioteca estándar de Python 3, sin instalar nada. Lee de verdad. **Escribe solo con `--publicar`** (responder) o `--abrir` (issue de GitHub); sin esas banderas todo es simulacro. Lo que Cella dice y cómo lo dice está en `marca/v5-figura/voz-cella-comentarios.md`; las reglas de este script (`reglas.json`) siguen ese documento (§2 y §3).

## Archivos

| archivo | qué es |
|---|---|
| `comentarios.py` | el script (órdenes abajo) |
| `reglas.json` | reglas de clasificación (simple / escalar / fijo / modelo), el texto fijo de crisis (`respuesta_fija`) y el control de lo que Cella publica sola |
| `registro.csv` | registro de respuestas publicadas, en el repo: fecha, plataforma, hash del id, categoría, texto publicado, quién aprobó (`cella-sola`, la cita de N, `regla-crisis-N-2026-10-15` en crisis, `cella-silencio` o `cella-sospechoso`), `autor_hash` (HMAC-SHA256 con la sal `NAOS_SAL_AUTOR` de quien comentó, para "una respuesta por persona por día"; nunca el nombre; sin sal queda vacío, #904 C), `pieza` (slug de la pieza de la casa, por `media_id` o id del video en `motor/instagram/publicados.csv`) y `es_tercero` (1 si no es la casa ni una cuenta de `propios.txt`, 0 si lo es, vacío si no se sabe; D-323). Solo se agregan filas: una cabecera vieja de 7 columnas se respeta y nunca se reescribe lo escrito (copia.py sube por línea exacta) |
| `propios.txt` | hashes (nunca nombres) de las cuentas de N y de la casa que no cuentan como terceros en M3.2 (`metas.py`, línea `cella_terceros`). Se saca con `NAOS_SAL_AUTOR=<sal> python3 comentarios.py hash-autor instagram <usuario>`; si cambia la sal, hay que rehacerlos |
| `registro-rondas.csv` | auditoría D-287, al lado de `registro.csv`: una fila por ronda con fecha, marca de la ronda y cuentas (listadas, respondidas, silenciadas, sospechosas). Sin texto de terceros |
| `prueba_comentarios.py` | 194 pruebas con APIs simuladas (sin red ni credenciales; 63 son de las siete capas de D-287 y 15 de D-305): `python3 prueba_comentarios.py` |

Los textos de terceros **no** van a git. El estado vive en `~/.cache/naos-comentarios/estado.json` (carpeta 0700, archivo 0600; se cambia con `NAOS_COMENTARIOS_DIR`) y es **desechable**: la ronda horaria corre en una sesión nueva con el caché vacío. Lo que decide qué ya pasó está en el repo y en GitHub: `registro.csv` (`sha256("plataforma:id")[:16]` de lo respondido o silenciado), los hilos de la plataforma (si NAOS ya escribió en el hilo, no se responde otra vez) y la marca `<!-- naos:h=<hash> item=cN -->` que cada issue de `escalar` y `crisis` lleva en el cuerpo (se lee de issues abiertos y cerrados).

## Defensa contra inyección de instrucciones (D-287)

El texto de los comentarios lo escribe cualquiera y la sesión de Haiku tiene una terminal: es la superficie de ataque. Siete capas, cada una hecha cumplir por código donde se puede (prueba por capa en `prueba_comentarios.py`):

| capa | qué hace | dónde |
|---|---|---|
| 1. Filtro de entrada | Lo que parece instrucción o ataque (ignore/disregard previous, system prompt, you are now, act as, roleplay, jailbreak, repeat after me, say exactly, reply with, ES equivalentes; código, comillas invertidas, shell, URL o dominio, `@`, base64 o hex, ruido, letras invisibles o de alfabetos mezclados, más de 280 caracteres) se clasifica `sospechoso`, se silencia y nunca llega al modelo. Se anota solo el hash en `registro.csv` (`cella-sospechoso`) y se cuenta. Una ráfaga (3 o más en la ronda, o 3 de la misma persona) abre UN issue para N, sin texto de terceros en título ni cuerpo; el cuerpo enlaza los comentarios. Si la ráfaga no puede abrir el issue, no se anotan y la ronda siguiente reintenta. Crisis, abuso, menores y lo que ya escala a N no pasan por el modelo y no se tocan. Quien mandó algo sospechoso tampoco recibe respuesta a sus otros comentarios | código (`es_sospechoso`, `reglas.json` → `sospechosos`) |
| 2. Cerco de datos | La ronda imprime cada comentario limpio (sin enlaces, caracteres de control ni invisibles, sin markdown, espacios colapsados, 200 caracteres como máximo, sin `<` ni `>`) entre `<<<DATO-MARCA` y `DATO-MARCA>>>`, con una MARCA aleatoria nueva en cada ronda y un recordatorio de que es dato | código (`sanitizar_texto`) + `ronda.md` |
| 3. Control de salida | `responder` rechaza enlaces, dominios, `@`, `#`, más de 4 dígitos o 4 seguidos, código, más del tope de palabras y frases, cualquier tramo de 4 palabras copiado del comentario (eco), palabras de carga de inyección (password, token, click, dm, free, crypto, giveaway, link, prompt, y más), afirmaciones de ser humana o de no ser una IA, y exige la firma ` · Cella` | código (`control_respuesta`, `reglas.json` → `control_respuesta`) |
| 4. Lista blanca | `responder` solo acepta los id que la última `ronda` listó (archivo `ronda-lista.json` en el caché, con la marca; `--ronda MARCA` obligatoria y vence a las 3 horas), como mucho 10 respuestas por ronda y 1 por persona por día (según `registro.csv`), y en YouTube revisa en cada corrida que el token tenga `youtube.force-ssl` (lo tiene desde antes del 9-nov; si un token nuevo lo pierde, se niega con el motivo). `--otra-vez` no vale para Cella sola; `--aprobo` solo acepta la forma de la cita de N (`ok de @N en repo#12, fecha`). `silenciar` también exige que el id esté en la lista | código (`verificar_lista`) |
| 5. "¿Eres una IA?" | Pasa de escalar al subtipo `ia` de simple: Cella la contesta, con gracia, siempre diciendo que sí. El control exige "AI" o "IA" en la respuesta y rechaza negarlo o decirse humana. Seis líneas aprobadas (EN y ES, una con "written by NMR") en `reglas.json` y en la guía de voz §v2.6; la ronda las imprime. Si la pregunta toca la voz, la herramienta o quién la hizo, sigue escalando (`ia_voz`) | código + guía |
| 6. Comandos de la sesión | `ronda.md` limita la sesión a: el clon, `ronda`, `responder`, `silenciar` y los git exactos de los dos registros. Y `responder --publicar` se niega si el árbol de trabajo tiene cambios fuera de `registro.csv` y `registro-rondas.csv` (también detecta archivos nuevos y `assume-unchanged`), o si git no puede mirar | `ronda.md` (prompt) + código (`arbol_alterado`) |
| 7. Auditoría | Cada ronda con `--publicar` agrega una fila a `registro-rondas.csv`; `responder` y `silenciar` la actualizan. `ronda.md` la empuja junto con `registro.csv` | código + `ronda.md` |

Lo que sigue siendo solo prompt: que el modelo no corra otros comandos y que no fabrique una cita de N con la forma correcta (el código no puede saber si un comando salió de su terminal). Lo cubren el resto de las capas (el árbol alterado, la lista, los topes) y que la sesión solo empuja esos dos archivos a main.

## D-305: Cella responde todo menos lo que no pase las bandas

N, 29-oct: "todo menos lo que no pase por las bandas de seguridad que tenemos para evitar prompt injection o cosas que no debería responder not ragebaiting and careful but creative always, even with comebacks or roasting or tenderness not always emojis y cuando vengas a mi con cosas que venga con propuestas y en modoo interactivo".

| qué llega | quién lo responde |
|---|---|
| sospechoso (D-287) | nadie: se silencia y no llega al modelo |
| crisis | texto fijo de `respuesta_fija` y aviso urgente a N (sin cambios) |
| abuso, menores, soledad y duelo (rojo ola 2, R2) | **no responde Cella**: suben a N con 2 o 3 propuestas numeradas (soledad: tres de presencia llana, sin chiste ni consejo) |
| spam, insulto | silencio (D-290) |
| todo lo demás (simples, `general`, salud, fe, mercados, política, contacto, casa, crítica, IA o voz, emoji de pena) | **Cella**, en la ronda, de tipo `modelo` o `simple` |

- **Tono.** `reglas.json` → `tono`: careful but creative, con comebacks, roast amable o ternura, el emoji opcional y sin ragebait. Los ejemplos están en `marca/v5-figura/voz-cella-comentarios.md` (v2.7).
- **El control** (`control_respuesta`) suma: `emoji_opcional` (el emoji nunca se exige; la lista permitida suma 🫶 💛 😌), palabras que delatan consejo (doctor, meds, therapist, lawyer, buy, sell, vote...), nombres de políticos y partidos, insultos, y patrones de consejo ("you should", "deberías", "I recommend", "see a doctor"). Para `ia` y `ia_voz` exige decir que es una IA.
- **Casa.** Ya no escala: Cella responde con ternura, sin comentar a la persona nombrada ni invitar a entrar. El miedo a llegar o a una persona sigue en `abuso` y sube a N.
- **Soledad y duelo** (categoría `soledad`, no `salud`): suben a N con propuestas de presencia llana. **Fijado por N el 29-oct** (sesión 2.9, interactivo: "Que me lleguen (Recomendada)"); `reglas.json` ya lo tiene (`soledad.tipo: escalar`).
- **Cariño corto** (`gracias`, simple): "amo", "amoooo", "te amo", "amo este video" (el comentario entero, sin más palabras) y los emojis de la lista con tono de piel (🫶🏽 cuenta como 🫶). "amo a mi esposo y..." sigue yendo al modelo como `general`. Un 💔 o 😭 sigue en `emoji_cuidado`.
- **Si Cella no encuentra una respuesta que respete las reglas, silencia** (`silenciar <id>`). Los comentarios de YouTube también se ofrecen, porque el token tiene `youtube.force-ssl` (comprobado el 14-nov con `comentarios.py permisos`).

### Lo que sube a N llega con propuestas, y en modo interactivo

1. **El issue de escalado** (`escalar --abrir`) trae, por cada comentario, 2 o 3 respuestas propuestas **numeradas**. Si el modelo dejó propuestas con `proponer <id> --texto A --texto B [--texto C] --escalar` (con `--escalar` hacen falta 2 o 3), mandan esas; si no, salen las plantillas de la categoría en `reglas.json` → `propuestas` (abuso: dos de Cella más el texto fijo de crisis; menores: tres) o `propuestas_defecto`, en el idioma del comentario.
2. **N contesta en el issue:** `c2: 2` elige la propuesta 2 de c2 (el número va solo), `c2: texto nuevo` la reescribe, `no c3` la descarta y `ok` aprueba la propuesta 1 de lo que no es URGENTE. Abuso (URGENTE) nunca se aprueba en bloque: N elige o escribe. Después `escalar --leer <issue>` guarda texto y cita (`elegido`, `reescrito` u `ok` de @N) y `responder <id> --del-issue --publicar` publica.
3. **Modo interactivo.** Cuando la sesión trae lo que escala a N en una conversación, NO abre un issue: corre `python3 comentarios.py escalar --interactivo`, que imprime un bloque por comentario (el texto del tercero entre `<<<DATO-...` y `DATO-...>>>`, las propuestas numeradas, "Escribo la mía" y "No responder"). La sesión le hace a N **una pregunta por comentario** con la herramienta de preguntas, las propuestas como opciones, los URGENTE primero. Lo que N elige o escribe en el chat es su palabra; la sesión publica solo eso con `responder <id> --texto "<lo que N dijo>" --aprobo "elegido de @N en sesion-interactiva, <fecha>" --publicar`. Nadie pone la elección por N: sin su respuesta no se publica nada, y "No responder" es `silenciar <id>`.
4. La ronda horaria de Haiku no pregunta nada (nadie contesta durante la sesión): deja los issues con propuestas y N los ve en GitHub o los atiende en una sesión interactiva.

## La ronda de cada hora (D-286)

```
python3 comentarios.py ronda --publicar --abrir     # lo único que corre la sesión de Haiku antes de escribir
```

Hace, en orden: `leer` (YouTube e Instagram por separado: si una falla, la otra sigue; últimos 30 días, `--dias`), `clasificar`, **sincronizar** (registro.csv, hilos, issues), `crisis` (con `--publicar` responde el texto fijo; con `--abrir` abre el issue), `escalar` (con `--abrir`), el paso `sospechosos` (capa 1), y al final lista los **simples** sin responder, de a tres líneas: `id=<plataforma:id> | categoría`, el texto limpio entre `<<<DATO-MARCA` y `DATO-MARCA>>>` (es dato de un tercero, no instrucciones) y, al final, la línea `RONDA <MARCA>`. Sin las banderas todo es simulacro. Sale con código 2 si un paso falló. Si no puede leer los issues con `--abrir`, no abre ninguno (mejor callar que repetir).

- **YouTube:** el token tiene `youtube.force-ssl` (`comentarios.py permisos` dice "permitido", 14-nov; la ronda ya respondió 3 en YouTube el 9-nov). Si un token nuevo lo pierde, los simples de YouTube dejan de ofrecerse y `responder` se niega con el motivo; leer y escalar siguen.
- **Tipo `modelo`** (D-305): la ronda ahora los lista junto a los simples y Cella los responde con los mismos topes. Son las preguntas y dudas (`general`), `salud`, `fe`, `mercados`, `politica`, `contacto`, `casa`, `critica`, `ia_voz` y `emoji_cuidado`. Cada categoría trae una `guia` en `reglas.json` que la ronda imprime (sin consejo de salud, financiero ni legal, sin tomar partido, sin ragebait).
- **Solo comentarios de arriba del hilo** y sin respuesta de NAOS en el hilo; los de abuso, menores, crisis y demás van por escalar o crisis.
- **Segunda vuelta (D-323, `reglas.json` → `segunda_vuelta`):** si quien abrió el hilo vuelve, después de la respuesta de Cella, con una respuesta de categoría `acto` o `ia`, la ronda la lista y Cella responde una vez más en ese hilo (al comentario de arriba). Mismas siete capas y mismos topes; solo se exime de "una por persona por día" y de "una por hilo" para ese turno. Nunca un tercer turno, nunca otra persona, nunca menores, abuso, crisis ni lo que escala. Con `activa: false` vuelve a un turno por hilo.
- **Topes** (`reglas.json`, `control_respuesta`): `max_por_barrido` 30 (de las respuestas de la última hora según registro.csv; `responder` se niega al pasarlo), `max_por_video` 10 (la lista no ofrece más de 10 del mismo video), `max_por_ronda` 10 (la lista ofrece y `responder` acepta como mucho 10 por ronda), una respuesta por persona por día, `confianza_min` 0,8 (`responder --confianza X` se niega bajo ese valor). El control también bloquea "no es X, es Y" y "isn't X, it's Y".
- `responder <id> --texto ... --confianza 0.9 --ronda MARCA --publicar`: se niega si el id no está en la lista de la ronda o la MARCA no coincide, si el árbol de trabajo está tocado, si el hash ya está en registro.csv, si el hilo ya tiene respuesta (de NAOS o de esta sesión) o si no pasa el control. `silenciar <id>` anota en registro.csv (quien aprobó: `cella-silencio`) que se decidió callar, para que ninguna sesión nueva lo vuelva a ofrecer.
- La directiva de la sesión de Haiku está en `cola/cella-habla/ronda.md`. La sesión solo hace commit y push de `registro.csv` a main.
- El token de GitHub sale de `GITHUB_TOKEN`/`GH_TOKEN` o de `gh auth token`. Si es el de N, `--abrir` se niega (GitHub no le avisa de lo propio) salvo `NAOS_AVISO_GITHUB=1`.

## Paso a paso

```
cd earn/naos/motor/comentarios
python3 comentarios.py permisos --probar     # 0. qué permisos hay (ver "Permisos" abajo)
python3 comentarios.py leer                  # 1. trae comentarios nuevos (no imprime textos)
python3 comentarios.py clasificar            # 2. categoría y tipo; avisa en grande si hay URGENTE
python3 comentarios.py estado --todos        #    una línea por comentario (sin texto)
python3 comentarios.py ver instagram:17900…  #    el texto, solo en tu terminal
```

**Simples** (gracias, emojis, procedencia, lo que el modelo deje en simple). El texto lo escribe Cella (el modelo) y pasa por el control de §3 de la guía (máx. 25 palabras y 2 frases, 1 emoji de la lista, sin enlaces, `@`, `#`, raya larga, voseo ni palabras como "human" o "DM"; la firma "· Cella" no cuenta). Si no pasa, no sale sola.

```
python3 comentarios.py responder <id> --texto "Gracias por mirar. 🤍"            # simulacro: solo muestra
python3 comentarios.py responder <id> --texto "Gracias por mirar. 🤍" --publicar # responde de verdad y anota registro.csv ("cella-sola")
```

**Crisis** (decisión de N, 2026-10-15: "sale sola + aviso urgente"). Es la única categoría de tipo `fijo`: responde sola con un texto FIJO que vive en `reglas.json` (`respuesta_fija`), no lo genera el modelo ni lleva la voz de Cella: voz llana, sin emoji ni firma, en el idioma del comentario (español si el comentario lo es; con mezcla o duda, inglés). Y al mismo tiempo avisa a N con un issue URGENTE.

```
python3 comentarios.py crisis                       # simulacro: muestra qué respondería y el issue que armaría (no escribe nada)
python3 comentarios.py crisis --publicar --abrir    # responde con el texto fijo, anota registro.csv y abre el issue urgente
```

- Texto EN: "You're not alone. If you're in danger or thinking about hurting yourself, please reach out now: 988 (US), 106 or 123 (Colombia), or findahelpline.com for your country." El de ES (tú) dice lo mismo. Cambiarlo es editar `reglas.json`; el script se niega a publicarlo si pierde el 988 o findahelpline.com, o si le sale un emoji, la firma, una raya larga, un enlace, `@` o `#`.
- `--publicar` es la bandera de la respuesta; `--abrir`, la del issue (la misma que usa `escalar`). Sin ellas solo se arma y se muestra. En `registro.csv` queda como categoría `crisis` y quien aprueba es `regla-crisis-N-2026-10-15`.
- El issue es uno por comentario, con etiquetas `naos`, `resp:n` y `prioridad:p0`, @mención a N, título sin texto de terceros ("URGENTE NAOS: señal de crisis en youtube, respondida con texto fijo, fecha"), y el cuerpo dice qué se respondió y enlaza el comentario (tampoco copia el texto del tercero). N no tiene que dar ok: ya salió; el issue le pide mirarlo y, si hace falta, escribir algo más.
- Si la respuesta no puede salir (por ejemplo, un token de YouTube sin `youtube.force-ssl`), el issue sale igual y dice "NO se respondió" y por qué; cuando después se puede, el siguiente `crisis --publicar --abrir` responde y deja un comentario en el mismo issue. Un segundo mensaje de crisis en el mismo hilo no recibe el texto otra vez (solo el aviso a N).
- Si el token es el de N, `--abrir` se niega y no se publica nada (GitHub no le avisa de lo que él mismo abre). `responder` se niega en crisis: va todo por `crisis`.
- `escalar` no incluye la crisis, pero avisa "OJO, crisis sin atender" si queda alguna.

**Escalan** (D-305: solo abuso, menores y soledad y duelo, esta última confirmada por N el 29-oct; antes también salud, fe, mercados, política, voz de la IA, críticas y contacto, que ahora responde Cella):

```
python3 comentarios.py proponer <id> --texto "A" --texto "B" [--texto "C"] --escalar   # opcional: 2 o 3 propuestas
python3 comentarios.py escalar --interactivo              # lo trae a N en la sesión, con propuestas numeradas (sin issue)
python3 comentarios.py escalar                            # muestra el issue (título sin texto de terceros)
python3 comentarios.py escalar --abrir                    # lo abre en hardlypythonnmr/n-system, etiquetas naos y resp:n, @mención a N
                                                          # (se niega si el token es el de N, como aprobar.py)
```

N contesta en el issue: `c2: 2` (elige la propuesta 2), `c2: texto nuevo` (reescribe c2), `no c3` (no se responde) u `ok` (la propuesta 1 de lo que no es URGENTE). Luego:

```
python3 comentarios.py escalar --leer 41                  # lee lo que dijo N (solo cuenta su usuario) y guarda texto + cita
python3 comentarios.py responder <id> --del-issue --publicar   # publica el texto de N y anota la cita ("ok de @N en repo#41, fecha")
```

Sin cita de N, `responder` se niega en todo lo que escala (`--aprobo "ok de @N en hardlypythonnmr/n-system#41, 2026-10-15"` si N aprobó por otro lado). **Abuso nunca sale sin esa cita y nunca recibe respuesta automática**: escala YA, y la urgencia sale en `clasificar` y en el título del issue.

`--simulado fixture.json` (antes de la orden: `comentarios.py --simulado f.json leer`) cambia todas las APIs por un fixture; `prueba_comentarios.py` arma uno.

## Permisos (verificado el 2026-10-15)

**YouTube: con el token actual NO se puede responder.**

- El refresh token actual trae (leído de `oauth2.googleapis.com/tokeninfo`): `youtube`, `youtube.upload`, `yt-analytics.readonly`.
- La doc oficial de `comments.insert` lista **un solo permiso aceptado: `https://www.googleapis.com/auth/youtube.force-ssl`**, costo 50 unidades de cuota, y pide `snippet.parentId` y `snippet.textOriginal`: <https://developers.google.com/youtube/v3/docs/comments/insert>. Con los scopes de arriba no se llamó a `comments.insert` (sería una escritura); `responder --publicar` revisa los scopes antes y se niega con el motivo.
- Prueba de solo lectura hecha: `commentThreads.list` del canal (UC7Lo3rK5sEOWuDYhAaQKtNw, "Naos") con **OAuth da 403 `ACCESS_TOKEN_SCOPE_INSUFFICIENT`**; con la **clave de API (`YOUTUBE_API_KEY`) da 200** (0 hilos: el canal aún no tiene comentarios públicos). Por eso `leer` usa la clave para leer, y `channels.list mine=true` por OAuth solo para saber el id del canal (sirve con el scope `youtube`). Con la clave no se ven los comentarios retenidos para revisión (eso necesita el scope nuevo). `commentThreads.list` cuesta 1 unidad; `comments.list` de respuestas, 1.

**Instagram: sí.** `instagram_business_manage_comments` ya respondió 200 en lectura (hoy: `me/media` devuelve 1 publicación con 0 comentarios; el campo `replies{...}` se acepta). Responder es `POST /<comment-id>/replies` con `message` (doc: <https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/comment-moderation>). No se probó escribir.

## Lo que falta

1. **(Hecho: el token ya tiene `youtube.force-ssl`; `comentarios.py permisos` dice "permitido" el 14-nov. Se deja el paso por si hay que regenerarlo.) Token nuevo de YouTube con `youtube.force-ssl`.** En `motor/youtube/token_oauth.py` hay que agregar `https://www.googleapis.com/auth/youtube.force-ssl` a `PERMISOS` (no lo toqué), correrlo otra vez en el computador de N, y poner el `GOOGLE_OAUTH_REFRESH_TOKEN` nuevo en los Network secrets. Si hace falta, borrar antes el permiso de NAOS en myaccount.google.com/permissions para que Google devuelva refresh token. Sin esto YouTube se lee pero no se responde. Después correr `comentarios.py permisos`: debe decir "permitido".
2. **Primera respuesta real, con N mirando.** Ahora también hace falta que el clon de la sesión esté limpio (capa 6) y que `registro-rondas.csv` exista en main. Nada de esto se probó contra las APIs de escritura (solo con APIs simuladas, 149 pruebas). La primera respuesta por plataforma debería ser un comentario simple de verdad, elegido a mano.
3. **Instagram y respuestas a respuestas.** La doc no dice si se puede responder a una respuesta; el script siempre responde al comentario de arriba del hilo (también en YouTube, que solo tiene dos niveles). Confirmar con el primer caso real.
4. **Decisiones de N pendientes** (guía de voz, §8): la variante de tono, la firma "· Cella", y si se declara en la página que las respuestas simples las escribe una IA. Ya decidido (2026-10-15): la crisis sale sola con texto fijo y avisa urgente (sección "Crisis").
   - **Número de Colombia:** alineado el 2026-10-15: 106 (Línea Nacional de Salud Mental de Minsalud, 24/7, https://minsalud.gov.co/salud/publica/salud-mental/Paginas/linea-106.aspx) o 123 si hay peligro inmediato, igual en `motor/seguridad.md`.
5. **Del documento de voz, aún sin cablear aquí:** `lint_voz.py` y `lint_riesgo.py` (el control de `reglas.json` cubre largo, emojis, enlaces, palabras y voseo, no "no es X, es Y" ni promesa de resultado), la bandeja de bendiciones en lote, la regla de idioma, ocultar o reportar spam e insultos, y la regla 0 (ignorar comentarios que responden a otra persona). Las reglas son más estrictas que lo necesario a propósito: escalar de más no hace daño; medir en las dos primeras semanas cuántos simples terminan escalados y ajustar `reglas.json`.
6. **Quién lo corre.** La ronda de cada hora (ver arriba y `cola/cella-habla/ronda.md`); la tarea programada todavía hay que crearla. El resto de esta lista es la versión manual. Para los chequeos agénticos: `leer`, `clasificar`, `crisis --publicar --abrir`, `escalar --abrir`, `escalar --leer <issue>` y `responder ... --publicar` en ese orden; para crisis conviene un barrido de comentarios cada hora (1 unidad de cuota por página), y en ese barrido correr `crisis --publicar --abrir` (cuesta 50 unidades por respuesta en YouTube).

D-290: `critica` e `ia_voz` las responde Cella (tipo modelo); `insulto` se silencia (ignorar, sin alerta). D-305 (29-oct): también `salud`, `fe`, `mercados`, `politica`, `contacto`, `casa` y `emoji_cuidado`; solo `abuso`, `menores` y (rojo ola 2, 29-oct) `soledad` escalan, con propuestas.

7. **Rojo ola 2 (29-oct), cerrado:** R1 menores (`i'm 13`, `tengo 13`, `13 yo`, `soy un nino`...), R2 ideacion en `crisis` y categoria `soledad` (duelo y soledad fuerte suben a N; si N quiere que Cella los responda lo escribe en D-305), R3 control de salida (sagrado, consejo, insultos a terceros, ragebait), R4 guia de `mercados` sin `wallet`, R5 miedo en casa a `abuso`, R6 provocar a otros a `insulto`. La deteccion de edad es por patron y puede fallar (falso positivo aceptado: escala a N). 175 pruebas.

**Sal de `autor_hash` (#904 C).** La sal vive solo en el entorno, en la variable `NAOS_SAL_AUTOR` (mínimo 16 caracteres; en Actions, el secreto del mismo nombre; en la rutina de Cella, la variable del entorno). Nunca en git. El hash es `HMAC-SHA256(sal, "<plataforma>:autor:<usuario en minúsculas>")` recortado a 16 hex: estable mientras la sal no cambie. Sin sal (o con una corta) `hash_autor` devuelve vacío y no escribe nada débil: `autor_hash` queda vacío, `es_tercero` queda sin dato salvo para la casa, `hash-autor` falla con un mensaje claro y `ronda` imprime un AVISO. Cambiar la sal rompe la continuidad: los hashes viejos y los de `propios.txt` dejan de coincidir.

## Marca DD (Done Damages) y pedidos de tema (13-nov-2026)

`--marca dd` (después de la orden: `ronda --marca dd`, `responder <id> ... --marca dd`, `silenciar <id> --marca dd`) corre este mismo sistema para DD en YouTube (canal `mercury` de `motor/youtube/canales.json`, token `MERCURY_OAUTH_*` o su alias `DD_OAUTH_*`), Instagram (`MERCURY_INSTAGRAM_TOKEN` o `DD_INSTAGRAM_TOKEN`) y la Página de Facebook (Graph API: `GET /{page}/published_posts`, `GET /{post-id}/comments?filter=toplevel`, `POST /{comment-id}/comments` con `message`; token de Página con `pages_read_engagement` y `pages_manage_engagement`; <https://developers.facebook.com/docs/graph-api/reference/object/comments/>). Sin `--marca` todo es NAOS, igual que antes. La voz está en `empresa/evolucion/2026-11-13-paralelo/evolucion/dd-respuestas/VOZ.md`; cómo encenderlo, en `ENCENDER.md` de esa carpeta.

| | NAOS (por defecto) | `--marca dd` |
|---|---|---|
| reglas | `reglas.json` | `reglas-dd.json` (las 7 capas de D-287 y el texto fijo de crisis, iguales) |
| registros | `registro.csv`, `registro-rondas.csv` | `registro-dd.csv`, `registro-rondas-dd.csv` |
| estado | `~/.cache/naos-comentarios/` | `~/.cache/naos-comentarios/dd/` |
| firma y topes | ` · Cella`, 25 palabras, 2 frases | ` · DD`, 30 palabras, 3 frases, 5 por ronda |
| responde | casi todo (D-305) | `pregunta_hecho`, `desacuerdo`, `elogio_saludo`, `pedido_tema` e `ia`; silencia política, salud, menores, acusación, insulto, spam y lo no clasificado; abuso sube a N; crisis, texto fijo |

El control de DD además rechaza, por código: consejo de inversión (buy, sell, hold, price target, you should...), un adjetivo moral a menos de 4 palabras de un nombre propio (los nombres salen de las mayúsculas y de los hechos de la pieza) y cualquier cifra que no esté en el `pedido.json` de la pieza de ese comentario (la ronda imprime `HECHOS PERMITIDOS`; sin pieza o sin pedido, ninguna cifra).

**Pedidos de tema (las dos marcas).** La categoría `pedido_tema` existe en `reglas.json` (Cella lo agradece y dice que lo anotó) y en `reglas-dd.json`. Al responder, `--resumen "<hasta 6 palabras del modelo>"` se anota en `pedidos.csv`, un libro único de solo agregar: fecha, marca, plataforma, hash del comentario, hash del autor, pieza de origen, resumen, estado (`anotado`, `en_junta`, `hecho`) y pieza que lo cumplió; un cambio de estado es una fila nueva con el mismo hash. En git no va texto de terceros: el texto se queda en el caché desechable y el cazador recibe un resumen de 6 palabras que escribió el modelo (solo letras, sin cifras, sin copiar 4 palabras del comentario, sin parecer una instrucción), porque un hash solo no le dice qué tema es. NAOS escribe en `pedidos.csv` y `lecturas.csv` solo cuando el archivo ya existe en la copia (ENCENDER.md).

- `pedidos --resumen`: por marca, por plataforma, por 100 comentarios leídos (`lecturas.csv`, lo llena `ronda --publicar`: terceros de arriba del hilo publicados en la última hora) y cuántos llegaron a pieza. `pedidos --lista`: los que aún no son pieza, con su resumen. `pedidos --marcar <hash> --estado en_junta`.
- `avisar-pedido <hash> --pieza <slug> [--titulo T] [--publicar]`: cuando el tema sale, UNA respuesta en el hilo original ("You asked, it's up: <título>", en la voz de cada marca, sin enlace, pasa el control), y marca el pedido `hecho`. En seco salvo `--publicar`.

Pruebas: `python3 prueba_comentarios_dd.py` (35, sin red). Ambas suites escriben solo en carpetas temporales y cada una termina con una prueba (`ZZIntegridad`) que falla si `registro.csv`, `registro-rondas.csv`, `registro-dd.csv`, `registro-rondas-dd.csv`, `pedidos.csv` o `lecturas.csv` del repo cambiaron.

## fijar.py: el comentario_fijado como primer comentario en Instagram y YouTube (D-516)

Hasta el 14-nov el `comentario_fijado` de las piezas no lo publicaba ningún paso. `fijar.py` lo publica como primer comentario de una pieza de NAOS ya publicada: en IG sobre el Reel (`POST /{media_id}/comments`), en YT sobre el Short (`commentThreads.insert`, 50 unidades). Ni IG ni YT dejan fijar por API: queda como primer comentario y fijarlo es a mano. En el registro se dice "primer comentario", nunca "fijado".

- Apagado por defecto (`fijar.json`, `activo: false`); `publicar` sin `--de-verdad` es seco. `--plataforma ig|yt` (ig por defecto).
- Solo publica si la vista previa de la tanda (`estado.json` → `comentario_vista_previa_id`) muestra el texto bajo su encabezado, la versión coincide con la fila del 👍 en `publicados.csv` y la huella `contenido` de la pieza hoy es la de `estado.json`.
- Destinos según lo que N vio: `### First comment (Instagram and YouTube)` (tandas abiertas desde el 14-nov) habilita IG y YT; el viejo `### Pinned comment (Instagram)` habilita solo IG.
- Solo NAOS, nada sensible ni de los tipos excluidos de `pedir_tema.json`. Una vez por plataforma e id (`fijados.csv`). Nunca borra ni edita.
- El token de YouTube de NAOS tiene `youtube.force-ssl` (tokeninfo, 14-nov).
- Pruebas: `python3 prueba_fijar.py` (30, sin red).
