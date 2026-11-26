"""Render the report's editable Markdown subset to a paginated PDF."""
import html
import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Table, TableStyle

root, source, output = map(Path, sys.argv[1:])
fonts = Path("/System/Library/Fonts/Supplemental")
for name, file in {
    "Body": "Arial.ttf", "Body-Bold": "Arial Bold.ttf", "Body-Italic": "Arial Italic.ttf",
    "Body-BoldItalic": "Arial Bold Italic.ttf", "Display": "Georgia.ttf",
}.items():
    pdfmetrics.registerFont(TTFont(name, str(fonts / file)))
pdfmetrics.registerFontFamily("Body", normal="Body", bold="Body-Bold",
                              italic="Body-Italic", boldItalic="Body-BoldItalic")

navy, teal, ink, muted = "#152D3D", "#256569", "#263947", "#526572"
width, height = A4
margin = 50
usable = width - margin * 2 - 12
styles = {
    "title": ParagraphStyle("title", fontName="Display", fontSize=29, leading=34,
                            spaceAfter=10, textColor=navy),
    "section": ParagraphStyle("section", fontName="Display", fontSize=19, leading=23,
                              spaceBefore=5, spaceAfter=10, textColor=navy, keepWithNext=True),
    "brand": ParagraphStyle("brand", fontName="Body-Bold", fontSize=11, leading=15,
                            spaceAfter=9, textColor=teal),
    "sub": ParagraphStyle("sub", fontName="Body-Bold", fontSize=13, leading=17,
                          spaceBefore=5, spaceAfter=6, textColor=teal, keepWithNext=True),
    "normal": ParagraphStyle("normal", fontName="Body", fontSize=10.4, leading=14.1,
                             spaceAfter=9, textColor=ink),
    "meta": ParagraphStyle("meta", fontName="Body-Bold", fontSize=9.4, leading=14,
                           spaceAfter=19, textColor=muted),
    "caption": ParagraphStyle("caption", fontName="Body-Italic", fontSize=9.1, leading=12,
                              spaceAfter=9, textColor=muted),
    "cell": ParagraphStyle("cell", fontName="Body", fontSize=9.15, leading=12, textColor=ink),
    "header": ParagraphStyle("header", fontName="Body-Bold", fontSize=9, leading=12,
                             textColor=colors.white),
    "register": ParagraphStyle("register", fontName="Body", fontSize=8.5, leading=11.5,
                               textColor=ink),
}


def markup(text):
    text = html.escape(text, quote=False)
    text = text.replace("&lt;br&gt;", "<br/>")
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    return text


def table(block):
    matrix = [[cell.strip() for cell in row.strip("|").split("|")] for row in block]
    header, data = matrix[0], matrix[2:]
    is_register = header[0] == "ID" and "Repository paths" in header
    compact = header[-1] in ("Disposition", "Status")
    padding = 2.3 if compact else 4.5
    widths = {
        ("Inventory", "Specification"): [0.27, 0.73],
        ("Validation question", "Evidence and disposition"): [0.34, 0.66],
        ("Development diagnostic", "Result"): [0.32, 0.68],
        ("Review field", "Status"): [0.44, 0.56],
    }.get(tuple(header))
    if is_register:
        widths = [0.10, 0.26, 0.64]
    elif header[0] == "ID":
        widths = [0.10, 0.32, 0.25, 0.33]
    elif header[0] == "Portfolio":
        widths = [0.25] + [0.15] * 5
    rows = [
        [Paragraph(markup(value), styles["header" if i == 0 else "register" if is_register else "cell"])
         for value in row] for i, row in enumerate([header, *data])
    ]
    grid = Table(rows, colWidths=[usable * w for w in widths], repeatRows=1, hAlign="LEFT", spaceAfter=11)
    grid.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(navy)),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#EEF4F4"), colors.white]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), padding),
        ("BOTTOMPADDING", (0, 0), (-1, -1), padding),
        ("LINEBELOW", (0, -1), (-1, -1), 0.55, colors.HexColor("#BCD0D1")),
    ]))
    return grid


content = []
lines = source.read_text().splitlines()
index = 0
while index < len(lines):
    line = lines[index]
    index += 1
    if not line:
        continue
    if line.startswith("|"):
        block = [line]
        while index < len(lines) and lines[index].startswith("|"):
            block.append(lines[index])
            index += 1
        content.append(table(block))
        continue
    if line == "<!-- pagebreak -->":
        content.append(PageBreak())
        continue
    if line.startswith("!["):
        relative = line.split("](", 1)[1].rstrip(")")
        image_path = (root / "output/pdf/phase6" / relative).resolve()
        figure = Image(str(image_path))
        figure.drawWidth, figure.drawHeight = usable, usable * figure.imageHeight / figure.imageWidth
        figure.hAlign = "LEFT"
        content.append(figure)
        continue
    if line.startswith("# "):
        style, line = "title", line[2:]
    elif line.startswith("## "):
        style, line = ("brand" if line.startswith("## Noether") else "section"), line[3:]
    elif line.startswith("### "):
        style, line = "sub", line[4:]
    elif line.startswith("Internal methodology"):
        style = "meta"
    elif line.startswith("*Figure"):
        style = "caption"
    else:
        style = "normal"
    content.append(Paragraph(markup(line), styles[style]))


def chrome(canvas, document):
    canvas.setTitle("Independent Model & Strategy Validation" if source.stem == "report" else "Executive Research Summary")
    canvas.setAuthor("Noether Meridian | Internal methodology demonstration")
    canvas.setStrokeColor(colors.HexColor("#BDD0CE"))
    canvas.line(margin, height - 43, width - margin, height - 43)
    canvas.setFont("Body-Bold", 8)
    canvas.setFillColor(colors.HexColor(teal))
    canvas.drawString(margin, height - 32, "NOETHER MERIDIAN")
    canvas.drawRightString(width - margin, height - 32, "SERVICE 02  /  UNIT 1")
    canvas.line(margin, 42, width - margin, 42)
    canvas.setFont("Body", 8)
    canvas.setFillColor(colors.HexColor(muted))
    canvas.drawString(margin, 29, "INTERNAL METHODOLOGY DEMONSTRATION  •  SIGN-OFF PENDING")
    canvas.drawRightString(width - margin, 29, f"{document.page:02d}")


doc = SimpleDocTemplate(str(output), pagesize=A4, leftMargin=margin, rightMargin=margin,
                        topMargin=55, bottomMargin=53, invariant=True)
doc.build(content, onFirstPage=chrome, onLaterPages=chrome)
