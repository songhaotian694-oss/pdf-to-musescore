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
cases=[('normal','validated',0,'passed'),
       ('missing-final-measure','validated',3,'failed_content_validation'),
       ('missing-layout-report','validated',5,'failed_layout_validation'),
       ('wrong-layout-mode','validated',5,'failed_layout_validation'),
       ('missing-final-measure-draft','draft',0,'draft_with_validation_issues'),
       ('missing-layout-report-draft','draft',0,'draft_with_validation_issues'),
       ('corrected-score','validated',0,'passed')]
for case,mode,expected,expected_status in cases:
    d=out/case;d.mkdir()
    for name in ['run.json','score-proof.pdf','score.mid','playback-assignment.json','selection.json']:
        shutil.copy2(source/name,d/name)
    manifest=json.loads((d/'run.json').read_text(encoding='utf-8-sig'));manifest['layoutMode']='reflow';manifest['selection']=str((d/'selection.json').resolve())
    (d/'run.json').write_text(json.dumps(manifest),encoding='utf-8')
    assignment=layout.apply(source/'score.mscz',d/'score.mscz','reflow')
    if case=='wrong-layout-mode':assignment['mode']='source'
    if case not in ['missing-layout-report','missing-layout-report-draft']:(d/'layout-assignment.json').write_text(json.dumps(assignment),encoding='utf-8')
    if case in ['missing-final-measure','missing-final-measure-draft']:
        with zipfile.ZipFile(d/'score.mscz') as z:entries=[(e,z.read(e.filename)) for e in z.infolist()]
        with zipfile.ZipFile(d/'score.mscz','w') as z:
            for e,data in entries:
                if e.filename.endswith('.mscx') and '/' not in e.filename:
                    root=ET.fromstring(data)
                    for staff in root.findall('./Score/Staff'):staff.remove(staff.findall('Measure')[-1])
                    data=ET.tostring(root,encoding='utf-8',xml_declaration=True)
                z.writestr(e,data)
    command=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(Path(__file__).parents[1]/'scripts/verify-output.ps1'),'-RunDirectory',str(d),'-OutputMode',mode]
    corrected=None
    if case=='corrected-score':
        corrected=d/'score-correction-01.mscz';shutil.copy2(d/'score.mscz',corrected)
        command.extend(['-ScorePath',str(corrected)])
    proc=subprocess.run(command,capture_output=True,encoding='utf-8',timeout=1200)
    (d/'verification.json').write_text(proc.stdout,encoding='utf-8')
    (d/'stderr.log').write_text(proc.stderr,encoding='utf-8')
    result=json.loads(proc.stdout.lstrip('\ufeff'))
    passed=proc.returncode==expected and result['status']==expected_status
    if mode=='draft':
        passed=passed and result['technicalValidation']=='passed' and not result['acceptancePassed']
        passed=passed and len(result['errors'])==len(set(result['errors']))
    if corrected:
        passed=passed and Path(result['verifiedScore'])==corrected and Path(result['proofPdf']).name.startswith('correction-proof-')
    records.append({'case':case,'mode':mode,'expectedExit':expected,'exitCode':proc.returncode,'passed':passed,'status':result['status'],'errors':result['errors']})
(out/'results.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
print(json.dumps(records,indent=2))
raise SystemExit(0 if all(r['passed'] for r in records) else 1)


