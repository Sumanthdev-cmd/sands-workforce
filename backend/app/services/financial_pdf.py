"""Printable reference copies; status never implies payment or a signature."""
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether

FONT=Path(__file__).with_name('financial_export_font.ttf')

def render_pdf(data):
    if 'SandSExport' not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(TTFont('SandSExport',str(FONT)))
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Export',fontName='SandSExport',fontSize=9,leading=13,spaceAfter=5,wordWrap='CJK'))
    styles.add(ParagraphStyle(name='ExportTitle',fontName='SandSExport',fontSize=21,leading=27,textColor=colors.HexColor('#12325c'),spaceAfter=12))
    styles.add(ParagraphStyle(name='ExportHeading',fontName='SandSExport',fontSize=12,leading=17,textColor=colors.HexColor('#12325c'),spaceBefore=13,spaceAfter=8,keepWithNext=True))
    def p(value,style='Export'):
        value=''.join(c for c in str(value) if ord(c)>=32 or c in '\n\t')
        return Paragraph(escape(value).replace('\n','<br/>'),styles[style])
    stream=BytesIO();doc=SimpleDocTemplate(stream,pagesize=A4,rightMargin=36,leftMargin=36,topMargin=36,bottomMargin=48,title=data['title'],author=data['organization'])
    story=[p(data['organization']+' · '+data['code']),p(data['title'],'ExportTitle'),p('Saved status: '+data['status']+' · Currency: '+data.get('currency','INR')),p('Reference: '+data['id']),p('Generated (UTC): '+data['generated_at']+' · Exported by: '+data['exported_by']),p('Reference copy of the saved record. Approval authorises processing; it is not proof of payment. Use the recorded payment details and supporting receipts. This export does not transfer money or add a signature.'),Spacer(1,8)]
    for title,fields in data['sections']:
        story.append(p(title,'ExportHeading'))
        if not fields:story.append(p('No details recorded.'));continue
        # Individual paragraphs can split across pages, including very long notes.
        for key,value in fields:
            story.append(p(key+': '+value))
    def footer(canvas,doc):
        canvas.saveState();canvas.setStrokeColor(colors.HexColor('#d4dce7'));canvas.line(36,36,A4[0]-36,36)
        canvas.setFont('SandSExport',8);canvas.setFillColor(colors.HexColor('#53657b'))
        canvas.drawString(36,23,'SandS Workforce · Financial record · UTC timestamps unless offset shown')
        canvas.drawRightString(A4[0]-36,23,str(doc.page));canvas.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return stream.getvalue()
