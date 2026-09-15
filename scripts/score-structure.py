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
from fractions import Fraction
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
        validate_rest_expectations(group)
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


def validate_rest_expectations(group):
    spans = group.get('expectedRestSpansPerPart')
    if spans is None:
        return
    if not isinstance(spans, list) or len(spans) != group['expectedParts']:
        raise ValueError('expectedRestSpansPerPart needs one list per part, or null when unreviewed.')
    for part_index, items in enumerate(spans):
        if not isinstance(items, list):
            raise ValueError('Each reviewed part needs a list of maximal whole-bar rest spans; [] means none.')
        previous_end = -1
        for item in items:
            if not isinstance(item, dict) or set(item) != {'startMeasure', 'measureCount'}:
                raise ValueError('Rest spans require startMeasure and measureCount only.')
            start, count = item['startMeasure'], item['measureCount']
            if type(start) is not int or type(count) is not int or start < 1 or count < 1:
                raise ValueError('Rest span positions/counts must be positive integers, counted from the first actual bar.')
            if start <= previous_end + 1:
                raise ValueError('Rest spans must be ordered, disjoint and maximal; merge adjacent silent ranges.')
            previous_end = start + count - 1
            counts = group.get('expectedMeasuresPerPart')
            if counts is not None and previous_end > counts[part_index]:
                raise ValueError('Rest span extends beyond the reviewed part measure count.')


def time_quarters(time):
    if time.find('senza-misura') is not None:
        return None
    beats, types = time.findall('beats'), time.findall('beat-type')
    if not beats or len(beats) != len(types):
        return None
    return sum((sum(Fraction(n.strip()) for n in b.text.split('+')) * 4 / Fraction(t.text)
                for b, t in zip(beats, types)), Fraction(0))


def measure_details(part):
    """Inventory real XML bars; never expand a multiple-rest display twice.

    Use explicit MusicXML durations, inherited divisions/time and a cursor for
    backup/forward. This checks rest duration, not complete polyphonic rhythm.
    """
    result, divisions, meters = [], None, {}
    for index, measure in enumerate(part.findall('measure'), 1):
        errors, warnings = [], []
        cursor = Fraction(0)
        regular = [n for n in measure.findall('note') if n.find('grace') is None]
        rests = [n for n in regular if n.find('rest') is not None]
        rest_only = bool(regular) and len(regular) == len(rests)
        if not regular:
            # A forward can legitimately represent an invisible gap; it is not
            # evidence for a notated rest. Do not manufacture rests from it.
            errors.append('No timed notes/rests; unresolved empty, forward-only or grace-only measure. Compare source before accepting.')
        full_rests = []
        for node in measure:
            if node.tag == 'attributes':
                if node.find('divisions') is not None:
                    divisions = Fraction(node.findtext('divisions'))
                    if divisions <= 0:
                        raise ValueError('MusicXML divisions must be positive.')
                for time in node.findall('time'):
                    meters[time.get('number', 'all')] = time_quarters(time)
            if node.tag not in ['note', 'backup', 'forward'] or node.find('grace') is not None:
                continue
            raw = node.findtext('duration')
            if raw is None or Fraction(raw) <= 0:
                errors.append('Missing or nonpositive timed note/rest/backup/forward duration.')
                continue
            if divisions is None:
                warnings.append('Missing divisions: rest duration was NOT checked.')
                continue
            duration = Fraction(raw) / divisions
            if node.tag == 'backup':
                cursor -= duration
                if cursor < 0:
                    errors.append('Backup moves before measure start.')
                continue
            rest = node.find('rest') if node.tag == 'note' else None
            if rest is not None and rest.get('measure') == 'yes':
                meter = meters.get(node.findtext('staff', '1'), meters.get('all'))
                full_rests.append({'durationQuarters': str(duration), 'meterQuarters': str(meter) if meter is not None else None})
                if cursor != 0:
                    errors.append(f'Whole-measure rest starts at {cursor} quarter notes instead of measure start; inspect extra rests/forwards.')
                if measure.get('implicit') == 'yes':
                    warnings.append('Implicit/pickup measure: full-measure rest duration requires source review.')
                elif meter is None:
                    warnings.append('Missing/unmeasured time signature: whole-bar rest duration was NOT checked.')
                elif duration != meter:
                    errors.append(f'Whole-measure rest duration/start is {duration}/{cursor} quarter notes; expected {meter}/0.')
            if node.find('chord') is None:
                cursor += duration
        result.append({'index': index, 'number': measure.get('number'), 'restOnly': rest_only,
                       'timedNotes': len(regular)-len(rests), 'rests': len(rests),
                       'wholeMeasureRests': full_rests,
                       'hiddenRests': sum(n.get('print-object') == 'no' for n in rests),
                       'multipleRestCounts': [int(e.text) for e in measure.findall('./attributes/measure-style/multiple-rest')],
                       'errors': list(dict.fromkeys(errors)), 'warnings': list(dict.fromkeys(warnings))})
    # Display spans must be backed by individual silent MusicXML measures.
    # A compact or corrupt export needs explicit review, never blind expansion.
    for bar in result:
        for count in bar['multipleRestCounts']:
            covered = result[bar['index']-1:bar['index']-1+count]
            if count < 1 or len(covered) != count or not all(m['restOnly'] for m in covered):
                bar['errors'].append(f'Multiple-rest display spans {count} bars without matching silent XML measures; review compressed-rest expansion.')
    return result


def rest_spans(bars):
    spans = []
    for bar in bars:
        if bar['restOnly']:
            if spans and spans[-1]['startMeasure'] + spans[-1]['measureCount'] == bar['index']:
                spans[-1]['measureCount'] += 1
            else:
                spans.append({'startMeasure': bar['index'], 'measureCount': 1})
    return spans


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
        bars = measure_details(p)
        parts.append({'id': p.attrib.get('id'), 'name': names.get(p.attrib.get('id')),
                      'measures': len(p.findall('./measure')),
                      'measureNumbers': [m.attrib.get('number') for m in p.findall('./measure')],
                      'clefs': list(dict.fromkeys(c.text for c in p.findall('.//clef/sign'))),
                      'lyrics': len(p.findall('.//lyric')), 'notes': len(p.findall('.//note')),
                      'measureDetails': bars, 'restSpans': rest_spans(bars),
                      'firstSoundingMeasure': next((b['index'] for b in bars if b['timedNotes']), None)})
    return {'parts': parts, 'lyrics': sum(p['lyrics'] for p in parts), 'notes': sum(p['notes'] for p in parts)}


def check_music(details, group):
    errors, warnings = [], []
    validate_rest_expectations(group)
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
    expected_rests = group.get('expectedRestSpansPerPart')
    if expected_rests is None:
        warnings.append('Source rest spans are unknown; rest counts and entry positions were NOT checked against the PDF.')
    for i, part in enumerate(parts):
        for bar in part.get('measureDetails', []):
            where = f"Part {part['id']}, measure index {bar['index']} (printed number {bar['number']}): "
            errors.extend(where + message for message in bar['errors'])
            warnings.extend(where + message for message in bar['warnings'])
        if expected_rests is not None and i < len(expected_rests) and part.get('restSpans') != expected_rests[i]:
            errors.append(f"Part {part['id']}: rest spans {part.get('restSpans')} differ from reviewed source {expected_rests[i]}. Check missing/duplicated rests and shifted entries; do not fix by renumbering.")
    return errors, warnings


def quality_penalty(details, group, errors):
    """Rank OMR attempts conservatively; zero never replaces formal validation."""
    parts = details['parts']
    components = {'validationErrors': len(errors) * 10000,
                  'partDifference': abs(len(parts) - group['expectedParts']) * 100000,
                  'measureDifference': 0, 'unexpectedClefs': 0,
                  'missingNotes': 100000 if not details['notes'] else 0}
    expected = group.get('expectedMeasuresPerPart')
    if expected is not None:
        components['measureDifference'] = sum(abs(part['measures'] - count)
                                              for part, count in zip(parts, expected)) * 100
        components['measureDifference'] += abs(len(parts) - len(expected)) * 10000
    clefs = group.get('allowedClefsPerPart')
    if clefs is not None:
        components['unexpectedClefs'] = sum(len(set(part['clefs']) - set(allowed))
                                             for part, allowed in zip(parts, clefs)) * 1000
    return sum(components.values()), components


def validate_content(xml, selection, proof=None, out=None):
    data = music_details(xml)
    errors, warnings = check_music(data, selection['group'])
    penalty, components = quality_penalty(data, selection['group'], errors)
    pages = []
    if proof is not None:
        pages = analyze(proof, out / 'proof-thumbnails')
        for page in pages:
            if page['nearBlank']:
                errors.append(f"Proof page {page['page']} is nearly blank (ink={page['inkCoverage']}, staves=0).")
            elif page['staffCount'] == 0:
                errors.append(f"Proof page {page['page']} has no detected five-line staves; inspect manually before accepting.")
    return {'schemaVersion': 3, 'status': 'failed_content_validation' if errors else 'passed_checked_structure',
            'errors': errors, 'warnings': warnings, 'musicXml': data, 'proofPages': pages,
            'qualityPenalty': penalty, 'qualityComponents': components,
            'scope': 'Reviewed part/measure/clef/lyric/rest-span expectations, explicit empty bars and whole-measure rest durations, all-page blank/staff heuristics; not full rhythmic/musical accuracy or text-overlap validation.'}


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
