# NAOS y la Audio API de Instagram: pasos para N

Encargo de la mesa (19-nov-2026). Aquí solo hay pasos: no se tocó la app ni los permisos.

## Por qué NAOS no tiene la Audio API hoy

`naos.v3` publica con **Instagram Login**, a través de la app de NAOS: una cuenta MEDIA_CREATOR, con acceso estándar y solo la cuenta propia.

La Audio API "is available on the Instagram API with Facebook Login and the Instagram API with Unified Login. It is not supported on the Instagram API with Instagram Login."
- Fuente: <https://developers.facebook.com/documentation/instagram-platform/content-publishing/audio-api.md>.
- Tipos de cuenta: "An Instagram Business or Instagram Creator account", así que una cuenta de creador sirve.
- Permisos: `instagram_basic` e `instagram_content_publish`.

## Lo que NO se hace

- **No le agregues Facebook Login a la app de NAOS.** "Your app can either use Facebook Login or Instagram Login but not both". Fuente: <https://developers.facebook.com/documentation/instagram-platform/app-review.md>. La app de NAOS se queda como está y sigue publicando.
- **No mezclar el sonido dentro del mp4 de NAOS.**
  - La doc solo dice que `download_url` es "A temporary URL to preview the audio file", que vence en unos 1,5 días.
  - Los Términos de la Plataforma no dan licencia para modificar el contenido ni hacer obras derivadas fuera de lo permitido. Fuente: <https://developers.facebook.com/terms/dfc_platform_terms/>.
  - El único uso documentado es adjuntarlo con `audio_configuration`. Sin certeza de licencia, no (regla de la mesa).
  - Las mezclas de la sala (n-system #1843) son solo para mirar.

## Camino A (recomendado): la app de DD con Facebook Login

La app de DD ya publica con Facebook Login. La doc no prohíbe que una app sirva a dos cuentas de Instagram, aunque tampoco lo dice explícitamente.

1. **Página de Facebook de NAOS.** Hoy no existe: `fb_pagina.py` pide `NAOS_FB_PAGE_ID` y anota "la Página de NAOS la crea N".
   - En Facebook, crea la Página de NAOS desde tu perfil (Páginas > Crear).
2. **Conectar `naos.v3` a esa Página.** En la Página: Configuración > Cuentas vinculadas > Instagram > Conectar, y entra con `naos.v3`.
   - Requisito: "your app users' Instagram professional accounts must be connected to a Facebook Page" (<https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login/overview>).
   - Quien haga el paso 4 tiene que poder hacer tareas en la Página: administrar, crear contenido, moderar o anunciar.
3. **Portafolio comercial.** En Meta Business Suite, agrega la Página de NAOS y la cuenta `naos.v3` al portafolio comercial donde vive la app de DD.
   - Es el mismo portafolio del usuario del sistema que usa DD. Así el token no vence, igual que el de DD (`instagram/LEEME.md`, sección Mercury).
4. **Token.** En el portafolio ve a Configuración del negocio > Usuarios > Usuarios del sistema, al mismo usuario del sistema de DD.
   - Agregar activos: la Página de NAOS y `naos.v3`, con control total o con las tareas de contenido.
   - Generar token: elige la app de DD y marca los permisos `instagram_basic`, `instagram_content_publish`, `pages_show_list` y `pages_read_engagement`, más `instagram_manage_comments` si quieres comentarios como DD.
   - Copia el token **solo en el formulario de secretos de GitHub**, nunca en el chat: naos-motor > Settings > Secrets and variables > Actions > New repository secret.
   - Nombre sugerido: `NAOS_FB_TOKEN`.
   - Alternativa: Graph API Explorer (<https://developers.facebook.com/tools/explorer>) con la app de DD, los mismos permisos, y canje a largo plazo con `grant_type=fb_exchange_token`.
     - El token de usuario dura unos 60 días.
     - Un token de Página sacado de él no vence.
     - Fuente: <https://developers.facebook.com/documentation/facebook-login/guides/access-tokens/get-long-lived.md>.
5. **ID de la cuenta.** `GET /me/accounts`, luego `GET /{page-id}?fields=instagram_business_account`, y ese número es el ID (<https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login/get-started>).
   - Va como variable, no secreto: Settings > Variables > `NAOS_FB_IG_USER_ID`.
   - Si prefieres no hacerlo, el motor tiene `ig.py ... cuenta`, que lo busca con el token, como hizo con DD.
6. **App Review.** No hace falta si la app es "only for a business I own or manage": basta el acceso estándar (<https://developers.facebook.com/documentation/instagram-platform/app-review.md>).
   - La doc no dice si "un negocio" cubre dos marcas en el mismo portafolio. Con los dos activos en el mismo portafolio, debería.

Después de eso, el motor necesita un cambio pequeño (lo hace una sesión, no N):
- La marca naos tendría dos credenciales: Instagram Login para publicar, como hoy, y Facebook Login para la Audio API.
- O se pasa NAOS entera a Facebook Login.
- Se decide con una prueba en seco (`dd-audio` con la marca naos).

## Camino B: Unified Login, sin Página

Meta dice que Unified Login es "the recommended setup for new integrations. New Instagram API features are released only for this setup" y que "Your clients don't need a Facebook Page" (<https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-unified-login.md>).
- Pide una app de un portafolio comercial con Facebook Login for Business.
- En el panel de la app: Casos de uso > Administrar mensajes y contenido en Instagram > Personalizar > Configuración de la API con Unified Login. Ahí creas una configuración y entras por su URL.
- Da un "Business Integration System User Access Token" (<https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-unified-login/get-started.md>).

**Duda abierta:** la página de la Audio API todavía lista "A Facebook Page connected to that account" en "Before You Start", lo que contradice lo de "sin Página". Por eso el camino A, con Página, es el que no depende de esa contradicción.

## Lo que la Audio API no permite (vale para DD también)

- `audio_configuration` solo tiene tres campos:
  - `audio_id`;
  - `audio_volume`, de 1 a 100, por defecto 100;
  - `video_volume`, de 1 a 100, por defecto 100.
- **No hay un campo de inicio ni de alineación.** No se puede pedir que el golpe del sonido caiga en el cuadro 0: Instagram decide desde dónde suena.
- "Previewing a Reel with attached audio is not supported."
- Fuente: <https://developers.facebook.com/documentation/instagram-platform/content-publishing/audio-api.md>.
