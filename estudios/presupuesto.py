"""Lectura del presupuesto del sitio (Excel de la CRO) para dar de alta un protocolo.

Reconoce la plantilla de presupuesto por visita: encabezado con Sponsor /
Protocol # / Overhead / Investigator / Site ID, una tabla "Per Subject Costs"
con una columna por visita, otra de costos condicionales y los costos fijos
del sitio. El precio de cada visita se recalcula acá (cantidad × costo ×
overhead), sin depender de las fórmulas guardadas en el archivo."""
import re
from decimal import ROUND_HALF_UP, Decimal


class PresupuestoIlegible(Exception):
    pass


# Renglón del presupuesto → procedimientos internos que se esperan en esa visita.
MAPA = [
    (r"informed consent", ["Consentimiento"]),
    (r"\bPI\b|investigator.*visit", ["SI (médico)"]),
    (r"\bBCVA\b", ["AV"]),
    (r"\bLLVA\b", ["LLA"]),
    (r"VFQ|questionnaire", ["Cuestionario"]),
    (r"SD-?OCT", ["OCT"]),
    (r"OCT-?A\b", ["OCTA"]),
    (r"\bCFP\b|fundus photo", ["FP"]),
    (r"\bFAF\b|autofluorescence", ["FAF"]),
    (r"\bFA\b|fluorescein angio", ["FA", "INY fluoresceína"]),
    (r"IVT of study drug", ["Inyección"]),
    (r"blood samples? for safety", ["Extracción", "Laboratorio"]),
    (r"blood samples?", ["Extracción"]),
    (r"fellow eye(?!.*avastin)", ["Contralateral"]),
]


def _dec(valor):
    try:
        return Decimal(str(valor))
    except Exception:
        return Decimal("0")


def _internos(descripcion):
    for patron, nombres in MAPA:
        if re.search(patron, descripcion, re.I):
            return nombres
    return []


def _semana(nombre):
    if re.search(r"day\s*1\b", nombre, re.I):
        return 0
    m = re.search(r"week\s*(\d+)", nombre, re.I)
    return int(m.group(1)) if m else None


def _nombre_visita(nombre):
    m = re.search(r"week\s*(\d+)", nombre, re.I)
    if m:
        return f"Week {m.group(1)}"
    return " ".join(str(nombre).split())


def leer(archivo):
    """Devuelve un diccionario (apto para guardar en la sesión) con lo leído."""
    from openpyxl import load_workbook
    try:
        hoja = load_workbook(archivo, data_only=True).worksheets[0]
    except Exception as error:
        raise PresupuestoIlegible("El archivo no es un Excel (.xlsx) que se pueda abrir.") from error
    filas = [[c.value for c in f] for f in hoja.iter_rows(max_row=400, max_col=60)]

    def dato(etiqueta):
        for f in filas[:12]:
            for i, v in enumerate(f[:-1]):
                if isinstance(v, str) and v.strip().rstrip(":").strip().lower() == etiqueta:
                    return f[i + 1]
        return None

    overhead = _dec(dato("overhead percentage") or 0)
    encabezados = [n for n, f in enumerate(filas) if isinstance(f[0], str) and f[0].strip() == "Cost Description"]
    if not encabezados:
        raise PresupuestoIlegible("No encontré la tabla de costos por visita (“Cost Description”). "
                                  "¿Es el presupuesto del sitio en el formato de la CRO?")
    cabeza = filas[encabezados[0]]
    columnas = []
    for i in range(6, len(cabeza)):
        v = cabeza[i]
        if v is None or str(v).strip().lower().startswith("total"):
            break
        columnas.append((i, _nombre_visita(v), _semana(str(v))))
    if not columnas:
        raise PresupuestoIlegible("No encontré las columnas de visitas en el presupuesto.")

    def seccion(inicio):
        salida = []
        for f in filas[inicio + 1:]:
            if not f[0] or str(f[0]).startswith("Total Costs"):
                break
            factor = 1 + overhead if str(f[1]).strip().upper() == "Y" else Decimal("1")
            salida.append({"descripcion": " ".join(str(f[0]).split()), "unitario": _dec(f[4]) * factor,
                           "cantidades": {i: _dec(f[i] or 0) for i, _, _ in columnas}, "maximo": f[3]})
        return salida

    por_sujeto = seccion(encabezados[0])
    condicionales = seccion(encabezados[1]) if len(encabezados) > 1 else []
    fijos = []
    if len(encabezados) > 2:
        for f in filas[encabezados[2] + 1:]:
            if f[0] and _dec(f[4]):
                fijos.append({"descripcion": " ".join(str(f[0]).split()), "monto": str(_dec(f[4]).quantize(Decimal("0.01")))})

    centavo = Decimal("0.01")
    visitas = []
    for i, nombre, semana in columnas:
        precio = sum((r["unitario"] * r["cantidades"][i] for r in por_sujeto), Decimal("0"))
        esperados = []
        for r in por_sujeto + condicionales:
            if r["cantidades"][i] > 0:
                esperados += [n for n in _internos(r["descripcion"]) if n not in esperados and n != "Contralateral"]
        visitas.append({"nombre": nombre, "semana": semana, "esperados": esperados,
                        "precio": str(precio.quantize(centavo, rounding=ROUND_HALF_UP))})

    viatico, precios_condicionales, sin_cargar = Decimal("0"), {}, []
    for r in condicionales:
        monto = r["unitario"].quantize(centavo, rounding=ROUND_HALF_UP)
        if re.search(r"travel", r["descripcion"], re.I):
            viatico = monto
            continue
        internos = _internos(r["descripcion"])
        if internos:
            precios_condicionales.setdefault(internos[0], str(monto))
        else:
            sin_cargar.append({"descripcion": r["descripcion"][:110], "monto": str(monto)})
    return {
        "codigo": str(dato("protocol #") or "").strip(), "sponsor": str(dato("sponsor") or "").strip(),
        "investigador": str(dato("investigator") or "").strip(), "sitio": str(dato("site id") or "").strip(),
        "nombre_sitio": str(dato("site name") or "").strip(), "overhead": str(overhead),
        "viatico": str(viatico), "visitas": visitas, "condicionales": precios_condicionales,
        "sin_cargar": sin_cargar, "fijos": fijos,
    }
