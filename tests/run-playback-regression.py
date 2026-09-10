"""Inject wrong saved routing / wrong delivered MIDI into copies of a real run."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile

parser=argparse.ArgumentParser();parser.add_argument('--run',required=True);parser.add_argument('--out',required=True)
args=parser.parse_args();source=Path(args.run);out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
spec=importlib.util.spec_from_file_location('fixtures',Path(__file__).with_name('test-playback.py'))
fixtures=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixtures)
records=[]
for case in ['saved-piano-fallback','delivered-wrong-midi']:
    d=out/case;d.mkdir()
    for name in ['run.json','score.mscz','score-proof.pdf','score.mid','playback-assignment.json']:
        shutil.copy2(source/name,d/name)
    if case=='saved-piano-fallback':
        with zipfile.ZipFile(d/'score.mscz') as z: entries=[(e,z.read(e.filename)) for e in z.infolist()]
        with zipfile.ZipFile(d/'score.mscz','w') as z:
            for e,data in entries:
                if e.filename.endswith('.mscx') and '/' not in e.filename:
                    root=ET.fromstring(data)
                    for program in root.findall('./Score/Part/Instrument/Channel/program'):program.set('value','0')
                    data=ET.tostring(root,encoding='utf-8',xml_declaration=True)
                z.writestr(e,data)
    else:fixtures.midi(d/'score.mid',programs=[0,0,0,0])
    proc=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(Path(__file__).parents[1]/'scripts/verify-output.ps1'),'-RunDirectory',str(d)],capture_output=True,encoding='utf-8',timeout=1200)
    (d/'verification.json').write_text(proc.stdout,encoding='utf-8')
    (d/'stderr.log').write_text(proc.stderr,encoding='utf-8')
    result=json.loads(proc.stdout.lstrip('\ufeff'))
    records.append({'case':case,'exitCode':proc.returncode,'status':result['status'],
                    'passed':proc.returncode==4 and result['status']=='failed_playback_validation',
                    'errors':result['errors']})
(out/'results.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
print(json.dumps(records,indent=2))
raise SystemExit(0 if all(r['passed'] for r in records) else 1)
