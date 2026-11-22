"""contador.py · créditos de ElevenLabs por bolsa contra el plan (D-322).

    python3 contador.py              -> semana y ciclo contra el plan, avisos y la línea para el VP del sábado
    python3 contador.py --linea      -> solo la línea para el VP
    python3 contador.py --sin-red    -> sin leer /v1/user/subscription (solo el registro)

Lee medicion/creditos-elevenlabs.csv (lo escribe el.py) y medicion/creditos-plan.json. Con la clave en el entorno también lee
el contador de la cuenta (gratis) para ver gasto que no pasó por el.py. Avisa por debajo del 70 % y por encima del 115 % de lo
que el plan espera a esta altura del ciclo (plan, sección 1.6), cuando una bolsa pasa del 115 % de su parte del ciclo, cuando hay
gasto sin bolsa y cuando el ciclo se acerca al tope de 120.000.
"""
import datetime, json, os, sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import el  # noqa: E402

MESES = "ene feb mar abr may jun jul ago sep oct nov dic".split()


def n(x):
    return f"{round(x):,}".replace(",", ".")


def dia(t):
    return f"{t.day}-{MESES[t.month - 1]}"


def fecha(s):
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))


def plan_del_ciclo(plan, ini, fin):
    """Partes por bolsa (y margen), lo fijo y desde cuándo corre el plan en este ciclo."""
    cp = plan.get("ciclos", {}).get(str(ini.date()))
    if cp:
        desde = fecha(cp["desde"]) if cp.get("desde") else ini
        partes = {b: float(cp.get(b, 0)) for b in plan["bolsas"] + ["margen"]}
        return partes, {b: float(v) for b, v in cp.get("fijo", {}).items()}, max(desde, ini)
    return {b: float(plan["ciclo_tipo"].get(b, 0)) for b in plan["bolsas"] + ["margen"]}, {}, ini


def esperado(t, partes, fijo, desde, fin):
    """Lo que el plan espera gastado entre `desde` y t, por bolsa: lo fijo de una vez y el resto parejo."""
    if t < desde:
        return {b: 0.0 for b in partes}
    frac = min(1.0, (t - desde) / (fin - desde))
    return {b: fijo.get(b, 0) + (v - fijo.get(b, 0)) * frac for b, v in partes.items()}


def informe(filas, plan, t, api=None):
    ini, fin = el.ciclo_de(t)
    ciclo = str(ini.date())
    F = [r for r in filas if r["ciclo"] == ciclo]
    partes, fijo, desde = plan_del_ciclo(plan, ini, fin)
    bolsas = plan["bolsas"]
    semana_n = int((t - ini).days // 7) + 1
    s_ini = ini + datetime.timedelta(days=7 * (semana_n - 1))
    s_fin = min(fin, s_ini + datetime.timedelta(days=7))

    def suma(cond):
        out = {}
        for r in F:
            if cond(r):
                out[r["bolsa"]] = out.get(r["bolsa"], 0) + float(r["creditos"] or 0)
        return out

    antes = sum(float(r["creditos"] or 0) for r in F if r["bolsa"] == "antes")
    ciclo_b = suma(lambda r: r["bolsa"] != "antes")
    semana_b = suma(lambda r: r["bolsa"] != "antes" and fecha(r["fecha_utc"]) >= s_ini)
    gastado_plan = sum(ciclo_b.values())                     # lo que corre contra el plan (sin la apertura)
    registro = antes + gastado_plan
    ciclo_total = max(registro, float(api or 0))
    esp = esperado(t, partes, fijo, desde, fin)
    esp_total = sum(esp.values())
    esp_sem = esp_total - (sum(esperado(s_ini, partes, fijo, desde, fin).values()) if s_ini > desde else 0)
    plan_total = antes + sum(partes.values())
    tope = plan.get("tope_ciclo", el.TOPE)
    bajo, alto = plan["avisos"]["bajo"], plan["avisos"]["alto"]

    avisos = []
    ritmo = gastado_plan / esp_total if esp_total >= 500 else None
    if ritmo is None:
        estado = "muy temprano para medir el ritmo"
    elif ritmo < bajo:
        estado = "por debajo"
        avisos.append(f"Vas al {ritmo:.0%} de lo esperado (menos del {bajo:.0%}): gasta en el orden de 'si sobra' (plan, 1.6).")
    elif ritmo > alto:
        estado = "por encima"
        avisos.append(f"Vas al {ritmo:.0%} de lo esperado (más del {alto:.0%}): baja en el orden de 'si falta' (plan, 1.6) y anótalo en decisiones-sistema.csv.")
    else:
        estado = "en rango"
    for b in bolsas:
        if partes.get(b, 0) and ciclo_b.get(b, 0) > alto * partes[b]:
            avisos.append(f"La bolsa {b} lleva {n(ciclo_b[b])}, más del {alto:.0%} de su parte del ciclo ({n(partes[b])}).")
        if not partes.get(b) and ciclo_b.get(b, 0):
            avisos.append(f"La bolsa {b} gastó {n(ciclo_b[b])} sin tener parte en el plan de este ciclo.")
    if ciclo_b.get("sin-bolsa"):
        avisos.append(f"Hay {n(ciclo_b['sin-bolsa'])} créditos sin bolsa: pasa --bolsa o NAOS_BOLSA a el.py.")
    if api is not None and api - registro > 500:
        avisos.append(f"La cuenta marca {n(api)} y el registro {n(registro)}: {n(api - registro)} se gastaron fuera de el.py "
                      "(o el contador de la API todavía no bajó). ElevenLabs es solo para NAOS.")
    if ciclo_total >= tope:
        avisos.append(f"Tope de N alcanzado ({n(tope)}): el.py no gasta más hasta el reinicio del {dia(fin)}.")
    elif ciclo_total >= 0.95 * tope:
        avisos.append(f"El ciclo va en {n(ciclo_total)}, a {n(tope - ciclo_total)} del tope de {n(tope)}.")
    dias_rest = (fin - t).total_seconds() / 86400
    if 0 < dias_rest <= 3 and plan_total - ciclo_total > 1000:
        avisos.append(f"Faltan {dias_rest:.1f} días para el reinicio y quedan {n(plan_total - ciclo_total)} del plan: barrido de fin de ciclo (plan, 1.5 y 1.6).")

    desglose = ", ".join(f"{b} {n(v)}" for b, v in sorted(semana_b.items(), key=lambda x: -x[1])) or "nada"
    linea = (f"ElevenLabs, ciclo {dia(ini)} a {dia(fin)}: {n(ciclo_total)} de {n(tope)} (tope de N), quedan {n(max(0, tope - ciclo_total))}; "
             f"contra el plan a hoy {n(gastado_plan)} de {n(esp_total)} esperados"
             + (f" ({ritmo:.0%}, {estado})" if ritmo is not None else f" ({estado})")
             + f". Semana {semana_n} ({dia(s_ini)} a {dia(s_fin)}): {n(sum(semana_b.values()))} ({desglose})."
             + (f" Avisos: {len(avisos)}." if avisos else " Sin avisos."))
    return {"ciclo": ciclo, "inicio": ini, "fin": fin, "semana": semana_n, "semana_inicio": s_ini, "semana_fin": s_fin,
            "antes": antes, "por_bolsa_ciclo": ciclo_b, "por_bolsa_semana": semana_b, "gastado_plan": gastado_plan,
            "registro": registro, "api": api, "ciclo_total": ciclo_total, "esperado": esp, "esperado_total": esp_total,
            "esperado_semana": esp_sem, "partes": partes, "plan_total": plan_total, "tope": tope, "ritmo": ritmo,
            "estado": estado, "avisos": avisos, "linea": linea}


def texto(I):
    L = [f"# ElevenLabs · créditos del ciclo {dia(I['inicio'])} a {dia(I['fin'])}", ""]
    L.append(f"Ciclo: {n(I['ciclo_total'])} de {n(I['tope'])} (tope de N); plan del ciclo {n(I['plan_total'])}"
             + (f"; cuenta {n(I['api'])}" if I["api"] is not None else "; cuenta sin leer") + f"; registro {n(I['registro'])}"
             + (f" (con {n(I['antes'])} de antes de las bolsas)" if I["antes"] else "") + ".")
    L.append(f"Contra el plan a hoy: {n(I['gastado_plan'])} de {n(I['esperado_total'])} esperados"
             + (f" ({I['ritmo']:.0%}, {I['estado']})." if I["ritmo"] is not None else f" ({I['estado']})."))
    L.append(f"Semana {I['semana']} ({dia(I['semana_inicio'])} a {dia(I['semana_fin'])}): {n(sum(I['por_bolsa_semana'].values()))} "
             f"de {n(I['esperado_semana'])} esperados a hoy.")
    L += ["", "| bolsa | semana | ciclo | esperado a hoy | parte del ciclo |", "|---|---|---|---|---|"]
    for b in list(I["partes"]) + sorted(set(I["por_bolsa_ciclo"]) - set(I["partes"])):
        L.append(f"| {b} | {n(I['por_bolsa_semana'].get(b, 0))} | {n(I['por_bolsa_ciclo'].get(b, 0))} | "
                 f"{n(I['esperado'].get(b, 0))} | {n(I['partes'].get(b, 0))} |")
    L += ["", "Avisos:" if I["avisos"] else "Sin avisos."] + [f"- {a}" for a in I["avisos"]]
    L += ["", "Para el VP del sábado:", I["linea"]]
    return "\n".join(L)


def evitados(ini, fin):
    """D-332: lo que la pila abierta evitó en el ciclo, aparte del gasto (medicion/creditos-evitados.csv, lo escribe
    motor/sonido/fondo.py --anotar). (créditos, filas) o None si no hay registro."""
    import csv
    ruta = os.path.join(el.NAOS, "medicion", "creditos-evitados.csv")
    if not os.path.exists(ruta):
        return None
    tot = filas = 0
    with open(ruta, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if ini <= fecha(r["fecha_utc"]) < fin:
                tot += int(float(r["creditos_evitados"] or 0)); filas += 1
    return tot, filas


def main(argv):
    plan = json.load(open(el.PLAN, encoding="utf-8"))
    api = None
    if "--sin-red" not in argv and os.environ.get("ELEVENLABS_API_KEY"):
        try:
            api = el.usados()[0]
        except (SystemExit, Exception) as e:
            print(f"(no pude leer la cuenta: {e}; sigo con el registro)", file=sys.stderr)
    I = informe(el.leer_registro(), plan, el.ahora(), api)
    print(I["linea"] if "--linea" in argv else texto(I))
    ev = None if "--linea" in argv else evitados(I["inicio"], I["fin"])
    if ev:
        print(f"\nEvitado con la pila abierta (aparte, no es gasto): {n(ev[0])} créditos en {ev[1]} fuentes este ciclo.")
    return I


if __name__ == "__main__":
    main(sys.argv[1:])
