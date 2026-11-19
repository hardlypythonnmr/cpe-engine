#!/usr/bin/env python3
"""nombres_dd.py: las credenciales de Done Damages se llaman DD_*; el código viejo las lee como MERCURY_*. Solo stdlib.

Las llaves de DD se crearon como DD_* (N, 15-nov). Mercury nunca tuvo llaves propias (se cerró por D-504 y pasó a ser DD,
D-506), pero el código y canales.json todavía piden MERCURY_*. alias() copia cada DD_X que exista sobre su MERCURY_X, así
el código que lee MERCURY_X recibe la llave de DD. DD manda: si están las dos, gana DD_X.
Las Actions ya pasan `secrets.DD_X || secrets.MERCURY_X` con el nombre MERCURY_X; ahí alias() no cambia nada.
Nunca imprime ni guarda un valor. Lo llaman ig.py, investigacion/yt.py y comentarios.py al cargarse.
prueba_nombres_dd.py falla si el código pide un MERCURY_* de credencial que no está en PARES.
"""
import os

# DD_X -> MERCURY_X. Solo credenciales e identificadores de cuenta, no ajustes de render (MERCURY_CHROME, MERCURY_GL...).
PARES = {
    "DD_OAUTH_CLIENT_ID": "MERCURY_OAUTH_CLIENT_ID",
    "DD_OAUTH_CLIENT_SECRET": "MERCURY_OAUTH_CLIENT_SECRET",
    "DD_OAUTH_REFRESH_TOKEN": "MERCURY_OAUTH_REFRESH_TOKEN",
    "DD_INSTAGRAM_TOKEN": "MERCURY_INSTAGRAM_TOKEN",
    "DD_INSTAGRAM_USER_ID": "MERCURY_INSTAGRAM_USER_ID",
    "DD_YOUTUBE_API_KEY": "MERCURY_YOUTUBE_API_KEY",
    "DD_PAGINA_TOKEN": "MERCURY_PAGINA_TOKEN",
    "DD_PAGES_BASE": "MERCURY_PAGES_BASE",
    "DD_PAGES_REPO": "MERCURY_PAGES_REPO",
}


def alias(entorno=None):
    """Copia DD_X sobre MERCURY_X. Devuelve los NOMBRES copiados (nunca valores)."""
    e = os.environ if entorno is None else entorno
    copiados = []
    for dd, merc in PARES.items():
        v = (e.get(dd) or "").strip()
        if v and e.get(merc) != v:
            e[merc] = v
            copiados.append(merc)
    return copiados


def faltan(entorno=None):
    """Pares sin ningún valor, ni DD_X ni MERCURY_X, nombrados por su nombre DD."""
    e = os.environ if entorno is None else entorno
    return [dd for dd, merc in PARES.items() if not (e.get(dd) or "").strip() and not (e.get(merc) or "").strip()]


if __name__ == "__main__":
    f = faltan()
    print("nombres de DD: todos presentes" if not f else "faltan (ni DD_ ni MERCURY_): " + ", ".join(f))
