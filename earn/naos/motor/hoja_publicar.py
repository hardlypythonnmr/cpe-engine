"""hoja_publicar.py · arma naos-publicar.xlsx (pestañas Publicar, Ideas y Cómo usar) desde los publicar.md, para subirlo a Drive como Google Sheets (D-139).

    python3 motor/hoja_publicar.py   (desde earn/naos; escribe /tmp/claude-0/hoja/naos-publicar.xlsx; agregar piezas en P)
"""
import re, openpyxl
from openpyxl.styles import Font, Alignment, PatternFill
R = "https://github.com/hardlypythonnmr/n-system/blob/main/earn/naos/"
def bloques(p):
    s = open(p, encoding="utf-8").read()
    sec, out = None, {}
    lab = None
    lines = s.split("\n"); i = 0
    while i < len(lines):
        l = lines[i]
        if l.startswith("## "): sec = l[3:].strip(); lab = None
        elif l.startswith("```"):
            j = i + 1; buf = []
            while not lines[j].startswith("```"): buf.append(lines[j]); j += 1
            out.setdefault(sec, []).append((lab, "\n".join(buf).strip())); i = j
        elif l.strip():
            lab = re.sub(r"[*:]|\(.*?\)", "", l).strip().lower()
        i += 1
    return out
def get(b, sec, lab):
    for k, v in b.items():
        if k and sec.lower() in k.lower():
            for l, t in v:
                if l and l.startswith(lab): return t
    return ""
P = [
 ("M01 neblina", "inglés", "micros/m01-neblina/v7b-final/"),
 ("M02 compañía", "inglés", "cola/ciclos/2026-10-10-consciencia/micro/"),
 ("E37 The Tenth One", "inglés", "cola/ciclos/2026-10-10-consciencia/short/"),
 ("C01 Te pillás", "español", "cola/ciclos/2026-10-10-consciencia/short-te-pillas/"),
 ("P01 neblina (voz paisa)", "español", "micros/m01-neblina/v7b-es-paisa/"),
 ("L04 tráiler", "inglés", "cola/ciclos/2026-10-10-consciencia/largo/v4/trailer/"),
]
rows = []
for nombre, idioma, d in P:
    b = bloques(d + "publicar.md")
    fij_global = get(b, "Comentario fijado", "") or ""
    ig_sec = "Instagram"; tt_sec = "TikTok"
    ig_cap = get(b, ig_sec, "caption"); alt = get(b, ig_sec, "alt text")
    fij = get(b, ig_sec, "comentario fijado") or (b.get("Comentario fijado", [(None, "")])[0][1])
    tt_cap = get(b, tt_sec, "caption") or ig_cap
    tt_fij = get(b, tt_sec, "comentario fijado") or fij
    yt_t = get(b, "YouTube", "título"); yt_d = get(b, "YouTube", "descripción"); yt_f = get(b, "YouTube", "comentario fijado") or fij
    vid = R + d + "naos.mp4"; por = R + d + "portada.png"
    rows += [[nombre, "TikTok", idioma, "listo", vid, por, "", tt_cap, tt_fij, ""],
             [nombre, "Instagram", idioma, "listo", vid, por, "", ig_cap, fij, alt],
             [nombre, "YouTube Shorts", idioma, "listo", vid, por, yt_t, yt_d, yt_f, ""]]
b = bloques("cola/ciclos/2026-10-10-consciencia/largo/v4/publicar.md")
d = "cola/ciclos/2026-10-10-consciencia/largo/v4/"
rows.append(["L04 Have it, or do it? (largo)", "YouTube", "inglés", "listo; falta revisión advaita y cristiana", R + d + "master.mp4", R + d + "miniatura/ (A, B y C)",
             get(b, "YouTube", "título"), get(b, "YouTube", "descripción"), get(b, "YouTube", "comentario fijado"), ""])
for r in rows:
    if not r[7]: print("FALTA", r[0], r[1])
wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Publicar"
H = ["Pieza", "Red", "Idioma", "Estado", "Video", "Portada", "Título", "Caption o descripción", "Comentario fijado", "Alt text"]
ws.append(H)
for r in rows: ws.append(r)
for c in ws[1]: c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="2E7D4F")
for col, w in zip("ABCDEFGHIJ", [24, 14, 9, 14, 30, 30, 40, 70, 40, 50]): ws.column_dimensions[col].width = w
for row in ws.iter_rows(min_row=2):
    for c in row: c.alignment = Alignment(wrap_text=True, vertical="top")
ws.freeze_panes = "C2"
wi = wb.create_sheet("Ideas")
wi.append(["Fecha", "Idea (tus palabras, tal cual)", "Estado", "Lo que hizo la sesión"])
wi.append(["2026-10-11", "(ejemplo) ¿por qué la gente se siente más sola con más contactos?", "nueva", ""])
for c in wi[1]: c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="2E7D4F")
for col, w in zip("ABCD", [12, 70, 12, 50]): wi.column_dimensions[col].width = w
wu = wb.create_sheet("Cómo usar")
for l in ["Publicar: una fila por pieza y red. Tocá una celda y copiá. Cuando publiques, cambiá Estado a 'publicado AAAA-MM-DD'.",
          "Ideas: escribí una línea en la primera fila libre, con la fecha y tus palabras tal cual. Estado 'nueva'. La sesión lee las nuevas al arrancar, primero las manda al equipo de investigación y te hace sus preguntas.",
          "Video y portada abren en GitHub (pide tu sesión de GitHub). La carpeta de Drive para los videos queda pendiente (ver el chat)."]:
    wu.append([l])
wu.column_dimensions["A"].width = 120
for row in wu.iter_rows():
    for c in row: c.alignment = Alignment(wrap_text=True, vertical="top")
wb.save("/tmp/claude-0/hoja/naos-publicar.xlsx")
print(len(rows), "filas")
