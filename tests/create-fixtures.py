"""Original deterministic notation fixtures; no third-party score content."""
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

root = Path(sys.argv[1])
root.mkdir(parents=True, exist_ok=True)

def make(name, piano=False, lyrics=False):
    score = ET.Element('score-partwise', version='4.0')
    work = ET.SubElement(score, 'work')
    ET.SubElement(work, 'work-title').text = name
    parts = ET.SubElement(score, 'part-list')
    sp = ET.SubElement(parts, 'score-part', id='P1')
    ET.SubElement(sp, 'part-name').text = 'Piano' if piano else 'Melody'
    part = ET.SubElement(score, 'part', id='P1')
    for i in range(1, 17 if piano else 9):
        m = ET.SubElement(part, 'measure', number=str(i))
        if i == 1 or (piano and i == 9):
            pr = ET.SubElement(m, 'print', **({'new-page': 'yes'} if i == 9 else {}))
            if i == 1:
                layout = ET.SubElement(pr, 'system-layout')
                ET.SubElement(layout, 'top-system-distance').text = '170'
        elif i % 4 == 1:
            ET.SubElement(m, 'print', **{'new-system': 'yes'})
        if i == 1:
            a = ET.SubElement(m, 'attributes')
            ET.SubElement(a, 'divisions').text = '1'
            key = ET.SubElement(a, 'key'); ET.SubElement(key, 'fifths').text = '0'
            time = ET.SubElement(a, 'time'); ET.SubElement(time, 'beats').text = '4'; ET.SubElement(time, 'beat-type').text = '4'
            if piano: ET.SubElement(a, 'staves').text = '2'
            for staff in range(1, 3 if piano else 2):
                clef = ET.SubElement(a, 'clef', number=str(staff))
                ET.SubElement(clef, 'sign').text = 'G' if staff == 1 else 'F'
                ET.SubElement(clef, 'line').text = '2' if staff == 1 else '4'
        for staff in range(1, 3 if piano else 2):
            if staff == 2:
                backup = ET.SubElement(m, 'backup'); ET.SubElement(backup, 'duration').text = '4'
            for beat in range(4):
                note = ET.SubElement(m, 'note'); pitch = ET.SubElement(note, 'pitch')
                ET.SubElement(pitch, 'step').text = ['C','D','E','G'][(i + beat - 1) % 4]
                ET.SubElement(pitch, 'octave').text = '4' if staff == 1 else '3'
                ET.SubElement(note, 'duration').text = '1'
                ET.SubElement(note, 'voice').text = str(staff)
                ET.SubElement(note, 'type').text = 'quarter'
                if piano: ET.SubElement(note, 'staff').text = str(staff)
                if lyrics:
                    lyric = ET.SubElement(note, 'lyric', number='1')
                    ET.SubElement(lyric, 'syllabic').text = 'single'
                    ET.SubElement(lyric, 'text').text = 'la'
    ET.indent(score)
    ET.ElementTree(score).write(root / (name + '.musicxml'), encoding='utf-8', xml_declaration=True)

make('single-melody')
make('two-page-piano', piano=True)
make('lyrics-melody', lyrics=True)
(root / 'invalid.pdf').write_text('this is not a PDF', encoding='utf-8')
from reportlab.pdfgen.canvas import Canvas
c = Canvas(str(root / 'text-only.pdf')); c.drawString(72, 720, 'This document contains ordinary text and no music staves.'); c.save()
print(root)
