"""Conservative page preflight and structure gates, never a note-accuracy test.

Requires pypdf, pypdfium2, numpy and Pillow. Page grouping is a draft for
visual review, not an automatic assertion of musical boundaries.
"""
import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import pypdfium2 as pdfium
from pypdf import PdfReader, PdfWriter


def absolute(value):
    p = Path(value)
    if not p.is_absolute():
        raise ValueError(f'Absolute path required: {value}')
    return p.resolve()


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, data):
    with open(path, 'x', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def staff_features(gray):
    # Long horizontal rows, then five approximately equally spaced lines.
    dark = np.asarray(gray) < 155
    rows = np.flatnonzero(dark[:, int(dark.shape[1]*.05):int(dark.shape[1]*.95)].mean(axis=1) > .40)
    runs = np.split(rows, np.where(np.diff(rows) > 1)[0] + 1)
    centers = [float(r.mean()) for r in runs if len(r)]
    staves, i = [], 0
    while i + 4 < len(centers):
        gaps = np.diff(centers[i:i+5])
        if min(gaps) >= 2 and max(gaps) <= 18 and max(gaps)/min(gaps) < 1.45:
            staves.append([centers[i], centers[i+4]])
            i += 5
        else:
            i += 1
    groups = []
    for staff in staves:
        # Only a heuristic. Wide inter-staff spacing can make this uncertain.
        if not groups or staff[0] - groups[-1][-1][1] > 3.0*(staff[1]-staff[0]):
            groups.append([staff])
        else:
            groups[-1].append(staff)
    return {'staffCount': len(staves), 'systemStaffCounts': [len(g) for g in groups],
            'inkCoverage': round(float(dark.mean()), 6)}


def analyze(pdf_path, out):
    out.mkdir(parents=True, exist_ok=False)
    document = pdfium.PdfDocument(str(pdf_path))
    pages = []
    try:
        for i in range(len(document)):
            page = document[i]
            try:
                bitmap = page.render(scale=1200 / page.get_width())
                try:
                    image = bitmap.to_pil().convert('L')
                    features = staff_features(image)
                    thumbnail = out / f'page-{i+1:03}.png'
                    image.save(thumbnail)
                finally:
                    bitmap.close()
                text_page = page.get_textpage()
                try:
                    text = text_page.get_text_range()
                finally:
                    text_page.close()
                labels = list(dict.fromkeys(re.findall(r'(?i)\b(?:violin\s*(?:ii|i|2|1)?|viola|violoncello|cello|piano|flute|clarinet|full\s+score)\b', text)))
                features.update(page=i+1, thumbnail=str(thumbnail), labels=labels,
                                textPreview=text[:1800], textAvailable=bool(text.strip()))
                features['nearBlank'] = features['staffCount'] == 0 and features['inkCoverage'] < .003
                pages.append(features)
            finally:
                page.close()
    finally:
        document.close()
    return pages


def draft_groups(pages):
    groups, previous = [], None
    for page in pages:
        signature = tuple(sorted(set(page['systemStaffCounts'])))
        labels = tuple(label.lower().strip() for label in page['labels'])
        # Different single-instrument labels are strong hints, not proof.
        single_label_change = previous and len(labels) == 1 and len(previous[1]) == 1 and labels != previous[1]
        structure_change = previous and signature and previous[0] and signature != previous[0]
        if not groups or structure_change or single_label_change:
            groups.append({'id': f'group-{len(groups)+1}', 'pages': [], 'labels': page['labels'],
                           'boundaryReason': 'first page' if not previous else 'staff layout or instrument label changed'})
        groups[-1]['pages'].append(page['page'])
        previous = signature, labels
    return groups


def preflight(source, out):
    pages = analyze(source, out / 'source-thumbnails')
    groups = draft_groups(pages)
    result = {'schemaVersion': 2, 'status': 'needs_selection', 'sourcePdf': str(source),
              'sourceSha256': digest(source), 'pageCount': len(pages), 'pages': pages,
              'suggestedGroups': groups, 'reviewRequired': True,
              'warnings': ['Grouping is heuristic. Inspect EVERY source thumbnail, including repeated titles, clefs and restarted bar numbers.',
                           'One MusicXML output does not prove that the PDF is one continuous score.']}
    write_json(out / 'preflight.json', result)
    return result


def validate_plan(plan, pre, requested):
    if plan.get('sourceSha256') != pre['sourceSha256'] or plan.get('reviewed') is not True:
        raise ValueError('Selection plan is unreviewed or belongs to a different PDF (SHA256 mismatch).')
    if plan.get('reviewedPages') != list(range(1, pre['pageCount']+1)):
        raise ValueError('Selection plan must document review of every source page in reviewedPages.')
    groups = plan.get('groups', [])
    ids, covered = set(), []
    for group in groups:
        name, pages = group.get('id', ''), group.get('pages', [])
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', name) or name in ids:
            raise ValueError('Group IDs must be unique lowercase names.')
        ids.add(name)
        if not pages or any(type(p) is not int for p in pages) or pages != sorted(set(pages)):
            raise ValueError('Each group needs nonempty, ascending unique integer page numbers.')
        covered += pages
        if type(group.get('expectedParts')) is not int or group['expectedParts'] < 1:
            raise ValueError('Each group must record visually reviewed expectedParts (MusicXML parts, not staff count).')
        if type(group.get('lyricsExpected')) is not bool:
            raise ValueError('Each group must specify lyricsExpected as true or false.')
        measures = group.get('expectedMeasuresPerPart')
        if measures is not None and (not isinstance(measures, list) or len(measures) != group['expectedParts'] or any(type(n) is not int or n < 1 for n in measures)):
            raise ValueError('expectedMeasuresPerPart must contain one positive count per expected part, or null.')
        clefs = group.get('allowedClefsPerPart')
        if clefs is not None and (not isinstance(clefs, list) or len(clefs) != group['expectedParts'] or any(not isinstance(c, list) or not c or any(s not in ['G','F','C','percussion','TAB','none'] for s in c) for c in clefs)):
            raise ValueError('allowedClefsPerPart must list reviewed clef signs for each part, or null.')
    if sorted(covered) != list(range(1, pre['pageCount']+1)):
        raise ValueError('Groups must partition all source pages exactly once; do not omit or duplicate pages.')
    if len(groups) > 1 and plan.get('selectionBasis') != 'user':
        raise ValueError('Multiple reviewed page groups require a user selection (selectionBasis=user).')
    # Merging a heuristic boundary may be legitimate (e.g. a reduced orchestration),
    # but must have a concrete visual explanation; -Force never bypasses this.
    boundaries = {g['pages'][0] for g in pre['suggestedGroups'][1:]}
    for group in groups:
        if any(p in boundaries for p in group['pages'][1:]) and not group.get('continuityReason', '').strip():
            raise ValueError('Group crosses a detected layout boundary. Split it, or document visually verified continuityReason.')
    if not requested and len(groups) == 1:
        requested = groups[0]['id']
    selected = next((g for g in groups if g['id'] == requested), None)
    if selected is None:
        raise ValueError('Select exactly one existing group using -GroupId. Run groups separately for multiple outputs.')
    if plan.get('selectionBasis') not in ['user', 'unambiguous_visual_review']:
        raise ValueError('Record selectionBasis=user or unambiguous_visual_review.')
    return selected


def select(source, pre, plan_path, requested, out):
    plan = json.loads(plan_path.read_text(encoding='utf-8-sig'))
    group = validate_plan(plan, pre, requested)
    destination = out / (group['id'] + '-source.pdf')
    reader, writer = PdfReader(source), PdfWriter()
    for number in group['pages']:
        writer.add_page(reader.pages[number-1])
    with open(destination, 'xb') as f:
        writer.write(f)
    selection = {'schemaVersion': 2, 'sourcePdf': str(source), 'sourceSha256': pre['sourceSha256'],
                 'sourcePages': group['pages'], 'group': group, 'selectionBasis': plan['selectionBasis'],
                 'selectedPdf': str(destination), 'selectedPdfSha256': digest(destination)}
    write_json(out / 'selection.json', selection)
    write_json(out / 'selection-plan.json', plan)
    return selection


def music_details(path):
    if path.suffix.lower() == '.mxl':
        with zipfile.ZipFile(path) as z:
            container = ET.fromstring(z.read('META-INF/container.xml'))
            rootfile = next(e for e in container.iter() if e.tag.split('}')[-1] == 'rootfile')
            entry = z.getinfo(rootfile.attrib['full-path'])
            if entry.file_size > 50_000_000:
                raise ValueError('Oversized MusicXML')
            data = z.read(entry)
    else:
        data = path.read_bytes()
    if len(data) > 50_000_000 or b'<!ENTITY' in data.upper():
        raise ValueError('Oversized XML or entity declarations are not supported')
    root = ET.fromstring(data)
    for e in root.iter():
        e.tag = e.tag.split('}')[-1]
    if root.tag != 'score-partwise':
        raise ValueError('Structure check currently requires score-partwise MusicXML; review/convert timewise XML explicitly.')
    names = {p.attrib.get('id'): p.findtext('part-name') for p in root.findall('./part-list/score-part')}
    parts = []
    for p in root.findall('./part'):
        parts.append({'id': p.attrib.get('id'), 'name': names.get(p.attrib.get('id')),
                      'measures': len(p.findall('./measure')),
                      'measureNumbers': [m.attrib.get('number') for m in p.findall('./measure')],
                      'clefs': list(dict.fromkeys(c.text for c in p.findall('.//clef/sign'))),
                      'lyrics': len(p.findall('.//lyric')), 'notes': len(p.findall('.//note'))})
    return {'parts': parts, 'lyrics': sum(p['lyrics'] for p in parts), 'notes': sum(p['notes'] for p in parts)}


def check_music(details, group):
    errors, warnings = [], []
    parts = details['parts']
    if len(parts) != group['expectedParts']:
        errors.append(f"Expected {group['expectedParts']} parts, found {len(parts)}.")
    if not details['notes']:
        errors.append('No notes/rests in MusicXML.')
    if not group['lyricsExpected'] and details['lyrics']:
        errors.append(f"Instrumental source produced {details['lyrics']} lyric objects; inspect header/footer misrecognition. Original XML retained.")
    if group['lyricsExpected'] and not details['lyrics']:
        errors.append('Source has lyrics but no lyric objects were recognized.')
    expected = group.get('expectedMeasuresPerPart')
    if expected is None:
        warnings.append('Source measure counts are unknown; measure-count consistency was NOT checked. Manual comparison required.')
    elif [p['measures'] for p in parts] != expected:
        errors.append(f"Per-part measure counts {[p['measures'] for p in parts]} differ from reviewed source {expected}. Check concatenation, missing bars or pickup counting.")
    clefs = group.get('allowedClefsPerPart')
    if clefs is None:
        warnings.append('Source clef expectations are unknown; clef consistency was NOT checked.')
    elif len(parts) == len(clefs):
        for part, allowed in zip(parts, clefs):
            if set(part['clefs']) - set(allowed):
                errors.append(f"Part {part['id']} has unexpected clefs {part['clefs']}; reviewed source allows {allowed}.")
    return errors, warnings


def validate_content(xml, selection, proof=None, out=None):
    data = music_details(xml)
    errors, warnings = check_music(data, selection['group'])
    pages = []
    if proof is not None:
        pages = analyze(proof, out / 'proof-thumbnails')
        for page in pages:
            if page['nearBlank']:
                errors.append(f"Proof page {page['page']} is nearly blank (ink={page['inkCoverage']}, staves=0).")
            elif page['staffCount'] == 0:
                errors.append(f"Proof page {page['page']} has no detected five-line staves; inspect manually before accepting.")
    return {'schemaVersion': 2, 'status': 'failed_content_validation' if errors else 'passed_checked_structure',
            'errors': errors, 'warnings': warnings, 'musicXml': data, 'proofPages': pages,
            'scope': 'Reviewed part/measure/clef/lyric expectations and all-page blank/staff heuristics; not musical accuracy or text-overlap validation.'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['prepare','check'])
    ap.add_argument('--input'); ap.add_argument('--out', required=True)
    ap.add_argument('--plan'); ap.add_argument('--group')
    ap.add_argument('--xml'); ap.add_argument('--selection'); ap.add_argument('--proof')
    args = ap.parse_args()
    out = absolute(args.out)
    try:
        if args.mode == 'prepare':
            source = absolute(args.input)
            pre = preflight(source, out)
            if not args.plan:
                result, code = pre, 2
            else:
                result, code = select(source, pre, absolute(args.plan), args.group, out), 0
        else:
            selection = json.loads(absolute(args.selection).read_text(encoding='utf-8-sig'))
            result = validate_content(absolute(args.xml), selection, absolute(args.proof) if args.proof else None, out)
            write_json(out / ('content-proof.json' if args.proof else 'content-musicxml.json'), result)
            code = 3 if result['errors'] else 0
    except Exception as e:
        result, code = {'status': 'failed', 'error': str(e)}, 1
    print(json.dumps(result, ensure_ascii=False))
    return code


if __name__ == '__main__':
    sys.exit(main())
