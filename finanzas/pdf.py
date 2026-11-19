"""Factura a la CRO en PDF, con el formato que pide la carta de pago: datos
fiscales del sitio, fechas, número, banco, sujeto por renglón, contacto y
entidad a facturar."""
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import ItemFactura

LOGO = Path(__file__).resolve().parent.parent / "static" / "marca" / "logo-loria.png"
AZUL = colors.HexColor("#334862")
GRIS = colors.HexColor("#667487")
BORDE = colors.HexColor("#d9e0e8")
MESES = ["", "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def _fecha(f):
    return f"{f.day:02d} {MESES[f.month]} {f.year}"


def _usd(x):
    return f"USD {x:,.2f}"


def _bloque(texto, estilo):
    return Paragraph("<br/>".join(escape(r) for r in texto.strip().splitlines()) or "—", estilo)


def renglones(factura):
    """[(secuencia, sujeto, visita, descripción, importe)] en el orden de la factura."""
    C = ItemFactura.Concepto
    filas = []
    for i in factura.items.select_related("visita__paciente", "visita__tipo", "realizacion__procedimiento"):
        if i.concepto == C.AJUSTE:
            sujeto, _, detalle = i.descripcion.partition(" · ")
            filas.append(("-", sujeto, detalle.split(": ", 1)[-1], "Reconciliation per payment letter", i.monto_usd))
            continue
        if i.visita is None:
            filas.append(("-", "-", i.descripcion, i.descripcion, i.monto_usd))
            continue
        v = i.visita
        falla = v.paciente.estado == "falla"
        nombre = "Screen failure" if falla else v.tipo.nombre
        if i.concepto == C.VISITA:
            descripcion = "Completed all screening procedures" if falla else "Completed all procedures"
        elif i.concepto == C.VIATICO:
            descripcion = "Travel"
        else:
            descripcion = f"{i.realizacion.procedimiento.nombre} (if performed)" if i.realizacion else i.descripcion
        filas.append((str(v.tipo.orden + 1), v.paciente.codigo, nombre, descripcion, i.monto_usd))
    return filas


def factura_pdf(factura):
    p = factura.protocolo
    normal = ParagraphStyle("n", fontName="Helvetica", fontSize=9.5, leading=13, textColor=colors.black)
    rotulo = ParagraphStyle("r", fontName="Helvetica-Bold", fontSize=8.5, leading=12, textColor=GRIS)
    derecha = ParagraphStyle("d", parent=normal, alignment=2)
    salida = BytesIO()
    doc = SimpleDocTemplate(salida, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=14 * mm,
                            bottomMargin=16 * mm, title=f"Invoice {factura.numero} · {p.codigo}")
    ancho = A4[0] - 36 * mm
    codigos = " / ".join(c for c in [p.codigo, p.codigo_cro] if c)
    encabezado = Table([[
        Image(str(LOGO), width=52 * mm, height=52 * mm * 220 / 624),
        Paragraph(f"<font size='20' color='#334862'><b>INVOICE</b></font><br/><br/>"
                  f"<b>INVOICE # {escape(factura.numero)}</b><br/>INVOICE DATE: {_fecha(factura.fecha)}<br/>"
                  f"DUE DATE: {_fecha(factura.vencimiento)}", derecha),
    ]], colWidths=[ancho * 0.5, ancho * 0.5])
    encabezado.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    partes = Table([
        [Paragraph("SITE INFORMATION", rotulo), Paragraph("BILL TO", rotulo)],
        [_bloque(p.datos_sitio, normal), _bloque(p.facturar_a, normal)],
    ], colWidths=[ancho * 0.5, ancho * 0.5])
    partes.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, 0), 0.8, AZUL),
                                ("TOPPADDING", (0, 1), (-1, 1), 5), ("RIGHTPADDING", (0, 0), (0, -1), 12)]))
    datos = [["Visit\nSequence", "Subject", "Name (Visit)", "Description", "Amount"]]
    for secuencia, sujeto, nombre, descripcion, importe in renglones(factura):
        datos.append([secuencia, sujeto, Paragraph(escape(nombre), normal), Paragraph(escape(descripcion), normal), _usd(importe)])
    datos.append(["", "", "", "TOTAL", _usd(factura.total)])
    tabla = Table(datos, colWidths=[18 * mm, 27 * mm, 34 * mm, ancho - 109 * mm, 30 * mm], repeatRows=1)
    tabla.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),
        ("LINEBELOW", (0, 1), (-1, -2), 0.4, BORDE), ("LINEABOVE", (0, -1), (-1, -1), 1.2, AZUL),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    banco = Table([[Paragraph("SUBMIT PAYMENT TO", rotulo)], [_bloque(p.datos_bancarios, normal)]], colWidths=[ancho])
    banco.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 0.8, AZUL), ("TOPPADDING", (0, 1), (-1, 1), 5)]))
    historia = [encabezado, Spacer(1, 5 * mm), Paragraph(f"<b>Protocol:</b> {escape(codigos)}", normal), Spacer(1, 5 * mm),
                partes, Spacer(1, 6 * mm)]
    if factura.request_id:
        historia += [Paragraph(f"<b>Request ID:</b> {escape(factura.request_id)}", normal), Spacer(1, 3 * mm)]
    historia += [tabla, Spacer(1, 9 * mm), banco]
    doc.build(historia)
    return salida.getvalue()
