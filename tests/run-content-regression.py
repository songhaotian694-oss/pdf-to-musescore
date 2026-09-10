"""Inject isolated structural faults into copies of a real successful test run."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pypdf import PdfReader, PdfWriter

ap=argparse.ArgumentParser(); ap.add_argument('--run',required=True); ap.add_argument('--out',required=True); ap.add_argument('--powershell',required=True)
args=ap.parse_args(); run=Path(args.run); out=Path(args.out); out.mkdir(parents=True,exist_ok=False)
scripts=Path(__file__).resolve().parents[1]/'scripts'
selection=json.loads((run/'selection.json').read_text(encoding='utf-8-sig'))
report=json.loads((run/'report.json').read_text(encoding='utf-8-sig'))
source=Path(report['candidates'][0]['path'])
with zipfile.ZipFile(source) as z:
    meta=ET.fromstring(z.read('META-INF/container.xml'))
    root=next(e for e in meta.iter() if e.tag.split('}')[-1]=='rootfile')
    xml=z.read(root.attrib['full-path'])
records=[]

def execute(name, command, expected, predicate):
    p=subprocess.run(command,capture_output=True,encoding='utf-8-sig',timeout=400)
    (out/(name+'.stdout.log')).write_text(p.stdout,encoding='utf-8')
    (out/(name+'.stderr.log')).write_text(p.stderr,encoding='utf-8')
    result=json.loads(p.stdout)
    passed=p.returncode==expected and predicate(result)
    records.append({'test':name,'passed':bool(passed),'exitCode':p.returncode,'command':list(map(str,command)),'result':result})
    (out/'results.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    print(name,passed,flush=True)

for name in ['extra-bars','footer-lyrics','wrong-cello-clef']:
    root=ET.fromstring(xml)
    if name=='extra-bars':
        part=root.findall('./part')[-1]
        for i in range(29,145): ET.SubElement(part,'measure',number=str(i))
    elif name=='footer-lyrics':
        lyric=ET.SubElement(root.find('.//note'),'lyric'); ET.SubElement(lyric,'text').text='Publisher footer'
    else:
        root.findall('./part')[-1].find('.//clef/sign').text='G'
    folder=out/name;folder.mkdir();path=folder/'fault.musicxml';ET.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
    execute(name,[sys.executable,'-X','utf8',scripts/'score-structure.py','check','--xml',path,'--selection',run/'selection.json','--out',folder],3,lambda r: r['status']=='failed_content_validation')

# Valid containers and score, but an extra near-empty page: technical pass,
# content fail. The source run stays untouched.
folder=out/'blank-proof';folder.mkdir()
for name in ['score.mscz','score.mid']:
    if (run/name).exists(): shutil.copyfile(run/name,folder/name)
copy_xml=folder/'source.mxl';shutil.copyfile(source,copy_xml)
shutil.copyfile(run/'selection.json',folder/'selection.json')
writer=PdfWriter();writer.append(run/'score-proof.pdf');writer.add_blank_page(width=595,height=842)
writer.write(folder/'score-proof.pdf')
manifest=json.loads((run/'run.json').read_text(encoding='utf-8-sig'))
manifest.update(musicXml=str(copy_xml),selection=str(folder/'selection.json'))
(folder/'run.json').write_text(json.dumps(manifest),encoding='utf-8')
execute('blank-proof',[args.powershell,'-NoProfile','-ExecutionPolicy','Bypass','-File',scripts/'verify-output.ps1','-RunDirectory',folder],3,
        lambda r:r['technicalValidation']=='passed' and r['status']=='failed_content_validation' and any('nearly blank' in e for e in r['contentValidation']['errors']))

sys.exit(0 if all(r['passed'] for r in records) else 1)
