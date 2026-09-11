"""Real MuseScore import/resave/MIDI checks, including a transposing brass part."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

p=argparse.ArgumentParser();p.add_argument('--musescore',required=True);p.add_argument('--out',required=True)
a=p.parse_args();out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
spec=importlib.util.spec_from_file_location('playback',Path(__file__).parents[1]/'scripts/score-playback.py')
pb=importlib.util.module_from_spec(spec);spec.loader.exec_module(pb)
records=[]
for name,kind,transpose in [('Trombone','trombone',0),('Baritone Horn','baritone-horn',0),('Euphonium','euphonium',0),('Baritone Horn','baritone-horn',-14)]:
    d=out/(kind+('-transposed' if transpose else ''));d.mkdir()
    runtime=d/'runtime';runtime.mkdir()
    env=dict(os.environ);env.update({key:str(runtime) for key in ['APPDATA','LOCALAPPDATA','TEMP','TMP']})
    root=ET.Element('score-partwise',version='4.0');pl=ET.SubElement(root,'part-list')
    sp=ET.SubElement(pl,'score-part',id='P1');ET.SubElement(sp,'part-name').text=name
    part=ET.SubElement(root,'part',id='P1');m=ET.SubElement(part,'measure',number='1');at=ET.SubElement(m,'attributes')
    ET.SubElement(at,'divisions').text='1';time=ET.SubElement(at,'time');ET.SubElement(time,'beats').text='4';ET.SubElement(time,'beat-type').text='4'
    clef=ET.SubElement(at,'clef');ET.SubElement(clef,'sign').text='G' if transpose else 'F';ET.SubElement(clef,'line').text='2' if transpose else '4'
    if transpose:
        tr=ET.SubElement(at,'transpose');ET.SubElement(tr,'diatonic').text='-1';ET.SubElement(tr,'chromatic').text='-2';ET.SubElement(tr,'octave-change').text='-1'
    for step in ['C','D','E','F']:
        note=ET.SubElement(m,'note');pitch=ET.SubElement(note,'pitch');ET.SubElement(pitch,'step').text=step;ET.SubElement(pitch,'octave').text='4'
        ET.SubElement(note,'duration').text='1';ET.SubElement(note,'type').text='quarter'
    xml=d/'source.musicxml';ET.ElementTree(root).write(xml,encoding='utf-8',xml_declaration=True)
    def export(source,target):
        r=subprocess.run([a.musescore,'-o',str(target),str(source)],capture_output=True,timeout=300,env=env)
        (d/(target.name+'.stderr.log')).write_bytes(r.stderr)
        if r.returncode or not target.exists():raise RuntimeError('MuseScore export failed: '+str(target))
    imported=d/'imported.mscz';export(xml,imported);export(imported,d/'before.mid')
    sel={'group':{'playbackInstruments':[kind]}};assignment=pb.apply(imported,d/'assigned.mscz',sel)
    export(d/'assigned.mscz',d/'score.mscz');export(d/'score.mscz',d/'score.mid')
    result=pb.verify(d/'score.mscz',d/'score.mid',sel)
    pitches=lambda file:[(n['tick'],n['pitch']) for t in pb.read_midi(file) for n in t['notes']]
    result['midiPitchAndTimingPreserved']=pitches(d/'before.mid')==pitches(d/'score.mid')
    result['expectedPitches']=[60+transpose,62+transpose,64+transpose,65+transpose]
    result['actualPitches']=[pitch for tick,pitch in pitches(d/'score.mid')]
    assert result['status']=='passed' and result['midiPitchAndTimingPreserved'] and result['actualPitches']==result['expectedPitches'],result
    records.append(result)
(out/'results.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(records,ensure_ascii=False))
