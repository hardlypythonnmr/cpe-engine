"""Saca el refresh token de YouTube para NAOS. Se corre UNA vez, en el computador de N (no en la nube).

Pasos:
  1. pip install google-auth-oauthlib==1.5.0
  2. Bajá el JSON del cliente (Google Cloud > Credenciales > el ID de cliente "App de escritorio" > Descargar JSON)
     y guardalo al lado de este archivo como client_secret.json (no lo subas al repo).
  3. python token_oauth.py
  4. Se abre el navegador: entrá con la cuenta dueña del canal NAOS, "Avanzado > ir a NAOS" si Google avisa que
     la app no está verificada, y aceptá los permisos.
  5. Los tres valores se escriben en un archivo con permiso 0600 FUERA del repo (por defecto ~/naos-youtube-oauth.txt, o la
     ruta que pases con --salida) y la terminal solo muestra los 4 últimos caracteres de cada uno. Del archivo, ponelos en el
     entorno de Claude Code, sección Network secrets: GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET y
     GOOGLE_OAUTH_REFRESH_TOKEN. No los pegués en el chat, y borrá el archivo cuando los hayas guardado.

Permisos: subir videos y miniaturas, administrar el canal (programar, títulos) y leer YouTube Analytics.
"""
import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

PERMISOS = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    # responder comentarios como Cella (comments.insert solo acepta force-ssl; sesión 6, motor/comentarios/)
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

cliente = Path(__file__).with_name("client_secret.json")
if not cliente.exists():
    raise SystemExit(f"Falta {cliente.name} al lado de este archivo (paso 2).")

import os, sys

salida = Path(sys.argv[sys.argv.index("--salida") + 1] if "--salida" in sys.argv else "~/naos-youtube-oauth.txt").expanduser().resolve()
repo = Path(__file__).resolve().parents[4]
if repo in (salida, *salida.parents):
    raise SystemExit(f"{salida} está dentro del repo: elegí una ruta fuera con --salida.")

if "--manual" in sys.argv:
    # Sin navegador local (Google Cloud Shell, shell.cloud.google.com): abrís el enlace en el celular o el PC,
    # aceptás, y el navegador termina en una página de localhost que no carga. Copiás esa dirección entera y la pegás aquí.
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"  # solo para leer el ?code= de la dirección de localhost
    flujo = InstalledAppFlow.from_client_secrets_file(str(cliente), PERMISOS, redirect_uri="http://localhost:1")
    enlace, _ = flujo.authorization_url(access_type="offline", prompt="consent")
    print("\n1. Abrí este enlace, entrá con la cuenta del canal NAOS y aceptá todo:\n\n" + enlace)
    pegado = input("\n2. Pegá aquí la dirección completa de la página que no cargó (empieza con http://localhost:1/?): ").strip()
    flujo.fetch_token(authorization_response=pegado)
    cred = flujo.credentials
else:
    flujo = InstalledAppFlow.from_client_secrets_file(str(cliente), PERMISOS)
    cred = flujo.run_local_server(port=0, access_type="offline", prompt="consent")
if not cred.refresh_token:
    raise SystemExit("Google no devolvió refresh token: borrá el permiso de NAOS en myaccount.google.com/permissions y corré otra vez.")

datos = json.loads(cliente.read_text())
datos = datos.get("installed") or datos.get("web") or datos
valores = {"GOOGLE_OAUTH_CLIENT_ID": datos["client_id"], "GOOGLE_OAUTH_CLIENT_SECRET": datos["client_secret"],
           "GOOGLE_OAUTH_REFRESH_TOKEN": cred.refresh_token}
fd = os.open(salida, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f:
    f.write("".join(f"{k}={v}\n" for k, v in valores.items()))
os.chmod(salida, 0o600)  # si el archivo ya existía con otro permiso
print(f"\nGuardé los tres valores en {salida} (permiso 0600). Pasalos a Network secrets y borrá el archivo:\n")
for k, v in valores.items():
    print(f"{k:28} = ...{v[-4:]}")
