"""Datos de partida del protocolo MALBEC (MK-8748-002), tomados del presupuesto
del sitio (05/05/2026), la tabla de costos por procedimiento y las planillas de
carga hasta el 18/11/2026. Se cargan una sola vez, con la base vacía."""
from datetime import date
from decimal import Decimal as D

PROTOCOLO = dict(codigo="MK-8748-002", nombre="MALBEC", codigo_cro="EYEB1014", sponsor="Eyebio (MSD)",
                 cro="TFS HealthScience", sitio="312", investigador="Agustina C. Palacio", viatico_usd=D("100"),
                 derivacion_usd=D("1000"))

# nombre, tarifa al médico, precio condicional al sponsor (con overhead)
PROCEDIMIENTOS = [
    ("Consentimiento", "50", "0"), ("SI (médico)", "150", "0"), ("AV", "25", "0"), ("LLA", "25", "0"),
    ("Cuestionario", "0", "0"), ("OCT", "30", "0"), ("OCTA", "40", "520"), ("FP", "50", "0"),
    ("FA", "150", "0"), ("FAF", "40", "260"), ("INY fluoresceína", "15", "0"), ("Extracción", "15", "0"),
    ("Extracción sola", "20", "0"), ("Laboratorio", "15", "0"), ("Inyección", "150", "0"),
    ("Contralateral", "50", "0"), ("Rescate", "50", "0"),
]

BASE = ["SI (médico)", "AV", "OCT", "OCTA"]
SEMANAS_CON_INYECCION = {4, 8, 16, 24, 32, 40, 48, 56, 60, 64, 68, 72, 76, 80, 84, 88, 92}
EXTRA = {
    24: ["Cuestionario", "FAF", "Extracción", "Laboratorio"],
    48: ["Cuestionario", "LLA", "FP", "FA", "FAF", "INY fluoresceína", "Extracción", "Laboratorio"],
    72: ["Cuestionario", "FAF", "Extracción", "Laboratorio"],
    92: ["Extracción", "Laboratorio"],
    96: ["Cuestionario", "LLA", "FP", "FA", "FAF", "INY fluoresceína", "Extracción", "Laboratorio"],
}
PRECIOS = {1: "1898.00", 4: "2535.00", 8: "2535.00", 12: "1898.00", 16: "2535.00", 20: "1898.00",
           24: "2844.40", 28: "1898.00", 32: "2535.00", 36: "1898.00", 40: "2535.00", 44: "1898.00",
           48: "3808.93", 52: "1898.00", 56: "2535.00", 60: "2535.00", 64: "2535.00", 68: "2535.00",
           72: "2717.00", 76: "2535.00", 80: "2535.00", 84: "2535.00", 88: "2535.00", 92: "2691.00",
           96: "2937.93"}


def tipos_visita():
    """[(nombre, semana, precio, [procedimientos esperados])] en orden de cronograma."""
    tipos = [
        ("Screening", None, "2896.40", ["Consentimiento", "SI (médico)", "AV", "OCT", "FP", "FA",
                                        "INY fluoresceína", "Extracción", "Laboratorio"]),
        ("Day 1", 0, "3195.41", ["SI (médico)", "AV", "LLA", "Cuestionario", "OCT", "OCTA", "FAF",
                                 "Extracción sola", "Laboratorio", "Inyección"]),
    ]
    for semana in sorted(PRECIOS):
        procs = list(BASE) + (["Inyección"] if semana in SEMANAS_CON_INYECCION else []) + EXTRA.get(semana, [])
        tipos.append((f"Week {semana}", semana, PRECIOS[semana], procs))
    tipos.append(("No programada", None, "0", ["SI (médico)", "AV", "OCT"]))
    return tipos


MEDICOS = {"PAL": "Palacio", "GRU": "Grundy", "SIL": "Silveyra", "BAR": "Baraja", "OLI": "Olivera Plata",
           "SANP": "San Pelegrini", "ORIA": "Oria", "COL": "Coloschi (laboratorio)"}
EXTERNOS = {"COL"}
SOLO_DERIVAN = ["Stortini", "Cenoz", "Troncoso"]

# código: (estado, derivado por, nota)
PACIENTES = {
    "312-21165": ("activo", "Palacio", ""), "312-21185": ("activo", "Palacio", ""),
    "312-21197": ("activo", "Stortini", ""), "312-21198": ("falla", "", ""),
    "312-21787": ("activo", "Palacio", "El Day 1 del 01/10 figura en la planilla como 312-21878: verificar el código."),
    "312-21850": ("activo", "Cenoz", ""), "312-22255": ("screening", "Troncoso", ""),
    "312-22273": ("screening", "", ""), "312-22288": ("screening", "", ""),
}

_SCR = ["Consentimiento", "SI (médico)", "AV", "OCT", "FP", "FA", "INY fluoresceína", "Extracción", "Laboratorio"]
_D1 = ["SI (médico)", "AV", "LLA", "Cuestionario", "OCT", "OCTA", "FAF", "Extracción sola", "Laboratorio", "Inyección"]


def _v(tipo, fecha, paciente, columnas, quienes, completa=True):
    return (tipo, date.fromisoformat(fecha), paciente,
            {p: q for p, q in zip(columnas, quienes.split()) if q != "-"}, completa)


_W1 = ["SI (médico)", "AV", "OCT", "OCTA"]
_W4 = ["SI (médico)", "AV", "OCT", "OCTA", "Inyección"]
VISITAS = [
    _v("Screening", "2026-06-09", "312-21165", _SCR, "PAL PAL GRU GRU PAL PAL BAR BAR COL"),
    _v("Screening", "2026-06-12", "312-21185", _SCR, "SIL SIL GRU GRU SIL SIL BAR BAR COL"),
    _v("Screening", "2026-06-16", "312-21197", _SCR, "PAL PAL GRU GRU PAL PAL BAR BAR COL"),
    _v("Screening", "2026-06-16", "312-21198", _SCR, "PAL PAL GRU GRU PAL PAL BAR BAR COL"),
    _v("Screening", "2026-06-16", "312-21185", ["Extracción sola", "Laboratorio"], "BAR COL", completa=False),
    _v("Screening", "2026-09-22", "312-21787", _SCR, "PAL PAL GRU GRU OLI OLI BAR BAR BAR"),
    _v("Screening", "2026-09-28", "312-21850", _SCR, "SIL SIL SANP GRU SIL SIL BAR BAR BAR"),
    _v("Screening", "2026-11-12", "312-22255", _SCR, "PAL PAL GRU GRU PAL PAL BAR BAR BAR"),
    _v("Screening", "2026-11-16", "312-22273", _SCR, "OLI OLI GRU GRU OLI OLI BAR BAR BAR"),
    _v("Screening", "2026-11-17", "312-22288", _SCR, "OLI OLI GRU GRU OLI OLI BAR BAR BAR"),
    _v("Day 1", "2026-06-23", "312-21165", _D1, "SIL GRU GRU SIL GRU - - BAR COL SIL"),
    _v("Day 1", "2026-06-24", "312-21185", _D1, "PAL GRU GRU PAL GRU - - BAR COL PAL"),
    _v("Day 1", "2026-06-24", "312-21197", _D1, "PAL GRU GRU PAL GRU - - BAR COL PAL"),
    _v("Day 1", "2026-10-01", "312-21787", _D1, "SIL SANP SANP SIL SANP SIL SIL BAR BAR SIL"),
    _v("Day 1", "2026-10-09", "312-21850", _D1, "SIL GRU GRU SIL GRU GRU SIL BAR BAR SIL"),
    _v("Week 1", "2026-06-30", "312-21165", _W1, "PAL GRU GRU -"),
    _v("Week 1", "2026-06-30", "312-21185", _W1, "PAL PAL PAL -"),
    _v("Week 1", "2026-06-30", "312-21197", _W1, "PAL PAL PAL -"),
    _v("Week 1", "2026-10-09", "312-21787", _W1, "SIL GRU GRU GRU"),
    _v("Week 1", "2026-10-16", "312-21850", _W1, "SIL GRU GRU GRU"),
    _v("Week 4", "2026-07-21", "312-21165", _W4, "PAL GRU GRU - PAL"),
    _v("Week 4", "2026-07-21", "312-21185", _W4, "PAL GRU GRU - PAL"),
    _v("Week 4", "2026-07-21", "312-21197", _W4, "PAL GRU GRU - PAL"),
    _v("Week 4", "2026-11-02", "312-21787", _W4, "OLI GRU GRU GRU ORIA"),
    _v("Week 4", "2026-11-02", "312-21850", _W4, "OLI GRU GRU GRU ORIA"),
    _v("Week 8", "2026-08-25", "312-21165", _W4, "PAL GRU GRU - PAL"),
    _v("Week 8", "2026-08-25", "312-21185", _W4, "PAL GRU GRU - PAL"),
    _v("Week 8", "2026-08-25", "312-21197", _W4, "PAL GRU GRU - PAL"),
    _v("Week 12", "2026-09-15", "312-21165", _W1, "PAL GRU GRU -"),
    _v("Week 12", "2026-09-15", "312-21185", _W1, "PAL GRU GRU -"),
    _v("Week 12", "2026-09-15", "312-21197", _W1, "PAL GRU GRU -"),
]

# nombre, porcentaje, cobra comisión sobre el neto
SOCIOS = [("Schlottman", "10", True), ("Palacio", "50", False), ("Rosendi", "40", False), ("Loria", "10", False)]

# médico, período, USD, cotización, quién lo pagó   (planilla "balance" al 18/11/2026)
PAGOS = [
    ("GRU", "junio 2026", "440", "1535", "Rosendi"), ("SIL", "junio 2026", "700", "1535", "Rosendi"),
    ("BAR", "junio 2026", "180", "1535", "Rosendi"), ("GRU", "julio 2026", "165", "1535", "Rosendi"),
    ("PAL", "junio a septiembre 2026", "4810", None, "Palacio"),
    ("PAL", "derivaciones (3 pacientes)", "3000", None, "Palacio"),
]
GASTOS = [("Abogado Quiendi", "3585", "Rosendi")]

CARTAS = [("Q2 2026", "2026-07-14", "PYRQ-003462", "23969.43"), ("Q3 2026", "2026-10-13", "PYRQ-004039", "20904.00")]
PRIMEROS = ["312-21165", "312-21185", "312-21197"]
# número, fecha, vencimiento, carta, request id impreso, cobrada, visitas, viáticos, fijo
FACTURAS = [
    ("001", "2026-06-12", "2026-07-12", None, "", True, [], [], ("Study Fee: Set-Up", "7500")),
    ("002", "2026-08-25", "2026-09-25", "Q2 2026", "PYRQ-003462", True,
     [(p, t) for p in PRIMEROS for t in ("Screening", "Day 1", "Week 1")], [], None),
    ("003", "2026-08-25", "2026-09-25", "Q2 2026", "PYRQ-003462", True, [("312-21198", "Screening")],
     [("312-21198", "Screening")] + [(p, t) for p in PRIMEROS for t in ("Screening", "Day 1", "Week 1")], None),
    ("004", "2026-10-14", "2026-11-14", "Q3 2026", "PYRQ-003462", False,
     [(p, t) for p in PRIMEROS for t in ("Week 4", "Week 8", "Week 12")], [], None),
    ("005", "2026-10-14", "2026-11-14", "Q3 2026", "PYRQ-003462", False, [],
     [(p, t) for p in PRIMEROS for t in ("Week 4", "Week 8", "Week 12")], None),
]
