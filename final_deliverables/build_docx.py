import re
import sys
from pathlib import Path
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

root=Path(sys.argv[1]); folder=Path(sys.argv[2]) if len(sys.argv)>2 else Path(__file__).parent
def styled(p,s):
    for i,t in enumerate(re.split(r'\*\*(.*?)\*\*',s)):
        if t:
            p.add_run(t).bold=(i%2==1)
def build(name):
    d=Document()
    sec=d.sections[0];sec.top_margin=Inches(.65);sec.bottom_margin=Inches(.6)
    sec.left_margin=sec.right_margin=Inches(.65)
    normal=d.styles["Normal"];normal.font.name="Arial";normal.font.size=Pt(9.5)
    normal.paragraph_format.space_after=Pt(5);normal.paragraph_format.line_spacing=1.07
    d.styles["Title"].font.name="Georgia";d.styles["Title"].font.size=Pt(29)
    d.styles["Title"].font.color.rgb=RGBColor.from_string("000000")
    for border in d.styles["Title"].element.xpath(".//w:pBdr"):
        border.getparent().remove(border)
    for name_,size in [("Heading 1",17),("Heading 2",12)]:
        st=d.styles[name_];st.font.name="Arial";st.font.size=Pt(size);st.font.color.rgb=RGBColor.from_string("193443")
    header=sec.header.paragraphs[0];header.add_run("NOETHER MERIDIAN   /   SERVICE 02   /   UNIT 1").bold=True
    footer=sec.footer.paragraphs[0]; footer.add_run("INTERNAL METHODOLOGY DEMONSTRATION   •   SIGN-OFF PENDING")
    for p in [header,footer]:
        for run in p.runs: run.font.size=Pt(8)
    lines=iter((folder/f"{name}.md").read_text().splitlines())
    raw=list(lines);i=0
    while i<len(raw):
        line=raw[i]; i+=1
        if not line: continue
        if line.startswith("|"):
            group=[line]
            while i<len(raw) and raw[i].startswith("|"):
                group.append(raw[i]);i+=1
            cells=[[v.strip() for v in x.strip("|").split("|")] for x in [group[0],*group[2:]]]
            t=d.add_table(rows=0,cols=len(cells[0]));t.style="Light Shading Accent 1";t.autofit=False
            patterns={2:[.30,.70],3:[.10,.24,.66],4:[.10,.30,.24,.36],6:[.25,.15,.15,.15,.15,.15]}
            widths=patterns[len(cells[0])]
            for c,frac in zip(t.columns,widths): c.width=Inches(7.2*frac)
            for j,record in enumerate(cells):
                r=t.add_row()
                style=OxmlElement('w:tblHeader' if j==0 else 'w:cantSplit')
                r._tr.get_or_add_trPr().append(style)
                for c,v,frac in zip(r.cells,record,widths):
                    c.width=Inches(7.2*frac)
                    p=c.paragraphs[0];p.paragraph_format.space_after=Pt(3)
                    run=p.add_run(v.replace("<br>","\n"));run.font.size=Pt(8 if len(cells)>10 or len(record)==3 else 9)
            d.add_paragraph().paragraph_format.space_after=Pt(1)
        elif line.startswith("!["):
            path=line.split("](")[1].rstrip(")").removeprefix("../")
            d.add_picture(str(root/path),width=Inches(6.9))
        elif line=="<!-- pagebreak -->":
            d.add_page_break()
        elif line.startswith("# "): d.add_paragraph(line[2:].replace("&","and"),"Title")
        elif line.startswith("## "): d.add_paragraph(line[3:],"Heading 1")
        elif line.startswith("### "): d.add_paragraph(line[4:],"Heading 2")
        elif line.startswith("*Figure"): d.add_paragraph(line.strip("*"),"Caption")
        else: styled(d.add_paragraph(),line)
    d.core_properties.author="Noether Meridian | Internal demonstration"
    d.save(folder/(name+".docx"))
for name in ("report","executive-summary"):
    build(name)
