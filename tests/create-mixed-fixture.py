"""Original 28-bar quartet + four separate parts; no third-party music."""
from pathlib import Path
import sys
import xml.etree.ElementTree as E

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
instruments = [('violin-1','Violin I','G','2',4), ('violin-2','Violin II','G','2',4),
               ('viola','Viola','C','3',4), ('violoncello','Violoncello','F','4',3)]

def make(name, chosen, full):
    root=E.Element('score-partwise',version='4.0')
    work=E.SubElement(root,'work'); E.SubElement(work,'work-title').text='Original Quartet Study'
    if not full: E.SubElement(root,'movement-title').text=chosen[0][1]
    pl=E.SubElement(root,'part-list')
    for j, (_,label,clef,line,octave) in enumerate(chosen,1):
        p=E.SubElement(pl,'score-part',id=f'P{j}'); E.SubElement(p,'part-name').text=label
    for j, (_,label,clef,line,octave) in enumerate(chosen,1):
        part=E.SubElement(root,'part',id=f'P{j}')
        for i in range(1,29):
            m=E.SubElement(part,'measure',number=str(i))
            if i==1:
                pr=E.SubElement(m,'print'); sl=E.SubElement(pr,'system-layout'); E.SubElement(sl,'top-system-distance').text='100'
                a=E.SubElement(m,'attributes'); E.SubElement(a,'divisions').text='1'
                k=E.SubElement(a,'key'); E.SubElement(k,'fifths').text='0'
                t=E.SubElement(a,'time'); E.SubElement(t,'beats').text='4'; E.SubElement(t,'beat-type').text='4'
                c=E.SubElement(a,'clef'); E.SubElement(c,'sign').text=clef; E.SubElement(c,'line').text=line
            elif full and i in (8,15,22): E.SubElement(m,'print',**{'new-page':'yes'})
            elif (full and i in (5,12,19,26)) or (not full and (i-1)%4==0):
                E.SubElement(m,'print',**{'new-system':'yes'})
            for beat in range(4):
                n=E.SubElement(m,'note'); p=E.SubElement(n,'pitch')
                E.SubElement(p,'step').text=['C','D','E','G'][(i+beat-1)%4]
                E.SubElement(p,'octave').text=str(octave)
                E.SubElement(n,'duration').text='1'; E.SubElement(n,'type').text='quarter'
    E.indent(root); E.ElementTree(root).write(out/(name+'.musicxml'),encoding='utf-8',xml_declaration=True)

make('full-score',instruments,True)
for instrument in instruments: make(instrument[0],[instrument],False)
print(out)
