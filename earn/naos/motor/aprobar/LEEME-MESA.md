# Aprobación `via = mesa`

Qué es: la orden `aprobar.py mesa`, con la que la mesa registra en la compuerta lo que N aprobó en el artefacto de la mesa.
Qué te toca: si eres la mesa, correrla solo tras la aprobación explícita de N a esa pieza y con sus palabras literales. Si revisas la compuerta, lee "Qué se niega" y "Qué no hace".

Origen: N escogió la opción A de `empresa/mesa/ARTEFACTO-APROBACION.md` (24-nov-2026). La fila la firma la mesa con su propio nombre. Nunca escribe como N ni pone su 👍 (D-301, D-461, D-520).

## Antes: la pieza en `por-aprobar` (org v3, 25-nov-2026)

`mesa` solo aprueba lo que está `por-aprobar`. Sin issue: `python3 earn/naos/motor/aprobar/aprobar.py preparar <slug> [--seco]`
escribe `estado.json` (`por-aprobar`, versión, `hash_contenido`, huellas por canal) desde `pieza.json`. No abre issue ni
toca git: Lauren hace commit de la carpeta y push del LFS. `abrir` (el issue) es el camino retirado. Ver `PUBLICAR.md` sección 2.

## Cómo se corre

```
python3 earn/naos/motor/aprobar/aprobar.py mesa <slug> --decision aprobar|aprobar_con_nota --version <n> \
    --hash <hash_contenido> --decidido-utc <ISO UTC> --cita "<palabras literales de N>" [--seco] [--sin-git]
```

Desde Python: `aprobar.aprobar_mesa(slug, decision, hash_contenido, cita, decidido_utc, version, cola=None, seco=False)`.

| Argumento | Qué lleva (sale de la fila de `decisiones` del artefacto) |
|---|---|
| `slug` | la pieza de `cola/aprobar/<slug>/` |
| `--decision` | `aprobar` o `aprobar_con_nota`; cualquier otra se niega |
| `--version` | la versión de la pieza que N decidió |
| `--hash` | el `hash_contenido` de la decisión; tiene que ser el de la pieza en la cola |
| `--decidido-utc` | la fecha UTC en que N decidió, por ejemplo `2026-11-24T15:30:00Z` |
| `--cita` | el comentario de N, literal; en `aprobar_con_nota` es la nota |
| `--seco` | dice qué registraría y no escribe nada |
| `--sin-git` | solo escribe en la copia local; sin él, y sin `--cola`, hace commit y push a main como `retirar` |

## Qué escribe

- `motor/instagram/publicados.csv`: una fila por canal con `aprobado_por = via = mesa`, `aprobado_utc` = la fecha de la decisión de N, la versión, la huella del canal y la leyenda `aprobado por N en la mesa, <fecha UTC>: <texto literal>` en `cita`. Vence a la hora de salida más la gracia de siempre.
- `cola/aprobar/<slug>/estado.json`: `estado = aprobado`, `aprobacion = mesa` y el bloque `mesa` con la decisión, la cita, la fecha, la versión, el `hash_contenido` y la leyenda.
- `medicion/decisiones-sistema.csv`: una fila `Aprobación de N en la mesa (via mesa)` con la cita y la huella.

La compuerta (`registro.verificar`) acepta la fila solo si la firma es de la mesa, la leyenda coincide con la de `estado.json` y la huella es la de lo que sale. Una fila de `via mesa` con el usuario de N, o con la vía de su 👍, no vale.

## Qué se niega, con la razón y sin escribir nada

- el `hash_contenido` de la decisión no es el de la pieza en la cola, o la carpeta cambió después de esa versión;
- falta la cita literal;
- la decisión no es `aprobar` ni `aprobar_con_nota`;
- la pieza ya está registrada (fila de N o de la mesa de esa versión);
- el estado no admite aprobación: solo `por-aprobar`; tampoco con revisiones en Fix, pasada la hora de salida o con cifras de más de 12 h cuando N decidió;
- la versión de la decisión no es la de la pieza, la fecha no es ISO UTC o está en el futuro, o falta `decisiones-sistema.csv`.

## Qué no hace

- No llama a GitHub: no comenta, no etiqueta, no reacciona.
- No cambia `via = reaccion` ni `via = comentario`.
- Si lo aprobado por la mesa no salió, hace falta otra decisión de N: el reprogramador no la cubre (D-512).
- Un comentario de N en el issue después de la decisión frena y anula la aprobación, como con su 👍.
- Antes de registrar, la mesa corre `--seco` si tiene dudas; tras registrar, marca `registrado = true` en el artefacto.

Pruebas: `python3 earn/naos/motor/aprobar/prueba_aprobar.py TestViaMesa`.
