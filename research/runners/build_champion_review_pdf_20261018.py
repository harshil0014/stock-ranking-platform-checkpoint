"""Typeset the audited champion literature/factor memo as a readable PDF."""
from pathlib import Path
import html
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, KeepTogether, PageTemplate, Paragraph,
    Spacer, Table, TableStyle,
)

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'research/reports/champion_models_papers_factors_20261018.md'
DEST = ROOT / 'output/pdf/sector_champion_research_and_factors_20261018.pdf'
FONT = Path('C:/Windows/Fonts/arial.ttf')
BOLD = Path('C:/Windows/Fonts/arialbd.ttf')
pdfmetrics.registerFont(TTFont('ArialCustom', str(FONT)))
pdfmetrics.registerFont(TTFont('ArialCustom-Bold', str(BOLD)))
pdfmetrics.registerFontFamily('ArialCustom', normal='ArialCustom', bold='ArialCustom-Bold')

NAVY = colors.HexColor('#123047')
TEAL = colors.HexColor('#067B82')
LIGHT = colors.HexColor('#E9F3F4')
GREY = colors.HexColor('#4F606C')
PALE = colors.HexColor('#F3F7F8')
PAGE_W, PAGE_H = A4


def rich(s):
    s = html.escape(s.strip())
    s = re.sub(r'\[([^]]+)\]\((https?://[^)]+)\)',
               lambda m: f'<link href="{m.group(2)}" color="#067B82"><u>{m.group(1)}</u></link>', s)
    s = re.sub(r'\[([^]]+)\]\((?!https?://)[^)]+\)', r'\1', s)
    s = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', s)
    s = re.sub(r'`([^`]+)`', r'<font color="#1D6073">\1</font>', s)
    s = s.replace('±', '+/-').replace('×', 'x').replace('²', '2')
    return s


styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='TitleCustom', fontName='ArialCustom-Bold', fontSize=23,
                          leading=27, textColor=NAVY, spaceAfter=12))
styles.add(ParagraphStyle(name='DeckCustom', fontName='ArialCustom', fontSize=10.2,
                          leading=15, textColor=GREY, spaceAfter=18))
styles.add(ParagraphStyle(name='H1Custom', fontName='ArialCustom-Bold', fontSize=14,
                          leading=18, textColor=NAVY, spaceBefore=19, spaceAfter=8,
                          keepWithNext=True))
styles.add(ParagraphStyle(name='H2Custom', fontName='ArialCustom-Bold', fontSize=10.5,
                          leading=14, textColor=TEAL, spaceBefore=14, spaceAfter=6,
                          keepWithNext=True))
styles.add(ParagraphStyle(name='BodyCustom', fontName='ArialCustom', fontSize=8.8,
                          leading=13.4, textColor=NAVY, spaceAfter=8))
styles.add(ParagraphStyle(name='BulletCustom', parent=styles['BodyCustom'], leftIndent=13,
                          firstLineIndent=-8, spaceAfter=5))
styles.add(ParagraphStyle(name='CellCustom', fontName='ArialCustom', fontSize=7.5,
                          leading=10.5, textColor=NAVY, alignment=TA_LEFT))
styles.add(ParagraphStyle(name='HeadCellCustom', parent=styles['CellCustom'],
                          fontName='ArialCustom-Bold', textColor=colors.white))


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor('#CBDADD'))
    canvas.line(20*mm, 19*mm, PAGE_W-20*mm, 19*mm)
    canvas.setFont('ArialCustom', 7.2)
    canvas.setFillColor(GREY)
    canvas.drawString(20*mm, 13.6*mm, 'Sector Champion | Research and factor review | 18 Oct 2026')
    canvas.drawRightString(PAGE_W-20*mm, 13.6*mm, str(doc.page))
    canvas.restoreState()


def table_flow(lines):
    rows = []
    for line in lines:
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if all(re.fullmatch(r':?-{3,}:?', c) for c in cells):
            continue
        rows.append(cells)
    n = len(rows[0])
    width = PAGE_W - 40*mm
    if n == 3:
        widths = [width*.24, width*.34, width*.42]
    elif n == 4:
        widths = [width*.22, width*.25, width*.28, width*.25]
    else:
        widths = [width/n]*n
    data = [[Paragraph(rich(cell), styles['HeadCellCustom' if i == 0 else 'CellCustom'])
             for cell in row] for i, row in enumerate(rows)]
    table = Table(data, colWidths=widths, repeatRows=1, hAlign='LEFT')
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), NAVY),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, PALE]),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 7),
        ('RIGHTPADDING', (0,0), (-1,-1), 7),
        ('TOPPADDING', (0,0), (-1,-1), 7),
        ('BOTTOMPADDING', (0,0), (-1,-1), 7),
        ('LINEBELOW', (0,0), (-1,0), .6, TEAL),
        ('LINEBELOW', (0,1), (-1,-1), .22, colors.HexColor('#DCE7E9')),
    ]))
    return table


def main():
    DEST.parent.mkdir(parents=True, exist_ok=True)
    lines = SOURCE.read_text(encoding='utf-8').splitlines()
    story = [Spacer(1, 4*mm), Paragraph('SECTOR RANKING / RESEARCH NOTE',
             ParagraphStyle(name='Eyebrow', fontName='ArialCustom-Bold', fontSize=8,
                            leading=11, textColor=TEAL, spaceAfter=9)),
             Paragraph('Inside the Sector Champion', styles['TitleCustom']),
             Paragraph('Every active factor, exact score weight, and the open-source models and papers behind the research.', styles['DeckCustom'])]
    i = 1  # Title is deliberately redesigned above.
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.startswith('|'):
            block = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                block.append(lines[i]); i += 1
            story.append(table_flow(block))
            story.append(Spacer(1, 5*mm))
            continue
        if line.startswith('## '):
            story.append(Paragraph(rich(line[3:]), styles['H1Custom']))
        elif line.startswith('### '):
            story.append(Paragraph(rich(line[4:]), styles['H2Custom']))
        elif line.startswith('* '):
            story.append(Paragraph('• ' + rich(line[2:]), styles['BulletCustom']))
        else:
            story.append(Paragraph(rich(line), styles['BodyCustom']))
        i += 1
    doc = BaseDocTemplate(str(DEST), pagesize=A4, leftMargin=20*mm,
                          rightMargin=20*mm, topMargin=18*mm, bottomMargin=25*mm,
                          title='Sector Champion: models, papers, factors and weights',
                          author='Codex research audit')
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates(PageTemplate(id='review', frames=[frame], onPage=footer))
    doc.build(story)
    print(DEST)


if __name__ == '__main__':
    main()
