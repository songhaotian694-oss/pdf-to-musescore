"""Remove imported physical line/page breaks on a copy; preserve section semantics."""
import argparse
import collections
import copy
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

def load(path):
    with zipfile.ZipFile(path) as z:
        names=[n for n in z.namelist() if n.endswith('.mscx') and '/' not in n]
        if len(names)!=1: raise ValueError('Expected exactly one main MSCX.')
        data=z.read(names[0])
        if b'<!ENTITY' in data.upper(): raise ValueError('Entity declarations are unsupported.')
        return names[0],ET.fromstring(data)

def breaks(root):
    return dict(collections.Counter(b.findtext('subtype','unknown') for b in root.findall('.//LayoutBreak')))

def positions(root):
    result=[]
    # Include frame/measure ordinal, staff and score (including excerpts).
    for score_index,score in enumerate(root.findall('.//Score')):
        for staff in score.findall('Staff'):
            ordinal=0
            for element in staff:
                if element.tag not in ['Measure','VBox','HBox','TBox','FBox']: continue
                ordinal+=1
                for br in element.findall('.//LayoutBreak'):
                    result.append([score_index,staff.get('id'),ordinal,element.tag,br.findtext('subtype','unknown')])
    return result

def strip_physical(root):
    removed=[]
    for parent in root.iter():
        for child in list(parent):
            if child.tag=='LayoutBreak' and child.findtext('subtype') in ['line','page']:
                removed.append(child.findtext('subtype'));parent.remove(child)
    return removed

def apply(source,output,mode):
    if output.exists(): raise ValueError('Use a new output path; never overwrite a score.')
    name,root=load(source);original=copy.deepcopy(root);before=breaks(root)
    removed=strip_physical(root) if mode=='reflow' else []
    # Compare all data after masking ONLY the two permitted layout elements.
    a=copy.deepcopy(original);b=copy.deepcopy(root);strip_physical(a);strip_physical(b)
    if ET.tostring(a)!=ET.tostring(b): raise ValueError('Unexpected non-layout mutation.')
    with zipfile.ZipFile(source) as old,zipfile.ZipFile(output,'x') as new:
        for entry in old.infolist():
            data=ET.tostring(root,encoding='utf-8',xml_declaration=True) if entry.filename==name else old.read(entry.filename)
            new.writestr(entry,data)
    return {'status':'applied','mode':mode,'before':before,'after':breaks(root),'positions':positions(root),
            'removed':dict(collections.Counter(removed)),'nonLayoutDataPreserved':True,
            'source':str(source),'output':str(output)}

def verify(score,assignment):
    _,root=load(score);actual=breaks(root)
    errors=[]
    if actual!=assignment['after']: errors.append('Saved break counts differ from the applied layout policy.')
    if 'positions' not in assignment:
        errors.append('Legacy layout report lacks break positions; reapply layout on a new copy before acceptance.')
    elif positions(root)!=assignment['positions']:
        errors.append('Break locations changed despite possibly identical counts.')
    return {'status':'failed_layout_validation' if errors else 'passed','errors':errors,
            'mode':assignment['mode'],'breaks':actual,
            'scope':'Explicit break policy only; inspect all proof pages for spacing, turns and collisions.'}

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['apply','verify'])
    p.add_argument('--score',required=True);p.add_argument('--output');p.add_argument('--report',required=True)
    p.add_argument('--mode',choices=['reflow','source'],default='reflow');p.add_argument('--assignment')
    args=p.parse_args()
    try:
        for value in [args.score,args.output,args.report,args.assignment]:
            if value and not Path(value).is_absolute(): raise ValueError('Use absolute paths.')
        result=apply(Path(args.score),Path(args.output),args.mode) if args.action=='apply' else verify(Path(args.score),json.loads(Path(args.assignment).read_text(encoding='utf-8-sig')))
    except Exception as e: result={'status':'failed_layout_validation','errors':[str(e)]}
    with open(args.report,'x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False))
    return 5 if result['status']=='failed_layout_validation' else 0

if __name__=='__main__':raise SystemExit(main())
