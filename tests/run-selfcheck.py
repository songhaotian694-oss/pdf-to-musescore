"""Integration regressions using copies of an accepted real conversion."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile

p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--out',required=True)
args=p.parse_args();source=Path(args.run);out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
spec=importlib.util.spec_from_file_location('layout',Path(__file__).parents[1]/'scripts/score-layout.py')
layout=importlib.util.module_from_spec(spec);spec.loader.exec_module(layout)
records=[]
for case,expected in [('normal',0),('missing-final-measure',3),('missing-layout-report',5),('wrong-layout-mode',5)]:
    d=out/case;d.mkdir()
    for name in ['run.json','score-proof.pdf','score.mid','playback-assignment.json']:
        shutil.copy2(source/name,d/name)
    manifest=json.loads((d/'run.json').read_text(encoding='utf-8-sig'));manifest['layoutMode']='reflow'
    (d/'run.json').write_text(json.dumps(manifest),encoding='utf-8')
    assignment=layout.apply(source/'score.mscz',d/'score.mscz','reflow')
    if case=='wrong-layout-mode':assignment['mode']='source'
    if case!='missing-layout-report':(d/'layout-assignment.json').write_text(json.dumps(assignment),encoding='utf-8')
    if case=='missing-final-measure':
        with zipfile.ZipFile(d/'score.mscz') as z:entries=[(e,z.read(e.filename)) for e in z.infolist()]
        with zipfile.ZipFile(d/'score.mscz','w') as z:
            for e,data in entries:
                if e.filename.endswith('.mscx') and '/' not in e.filename:
                    root=ET.fromstring(data)
                    for staff in root.findall('./Score/Staff'):staff.remove(staff.findall('Measure')[-1])
                    data=ET.tostring(root,encoding='utf-8',xml_declaration=True)
                z.writestr(e,data)
    proc=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(Path(__file__).parents[1]/'scripts/verify-output.ps1'),'-RunDirectory',str(d)],capture_output=True,encoding='utf-8',timeout=1200)
    (d/'verification.json').write_text(proc.stdout,encoding='utf-8')
    (d/'stderr.log').write_text(proc.stderr,encoding='utf-8')
    result=json.loads(proc.stdout.lstrip('\ufeff'))
    records.append({'case':case,'expectedExit':expected,'exitCode':proc.returncode,'passed':proc.returncode==expected,'status':result['status'],'errors':result['errors']})
(out/'results.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
print(json.dumps(records,indent=2))
raise SystemExit(0 if all(r['passed'] for r in records) else 1)
