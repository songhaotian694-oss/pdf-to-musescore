"""Build an evidence-linked correction worklist from verification failures."""
import argparse
import json
import re
from pathlib import Path


def absolute(value):
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f'Absolute path required: {value}')
    return path.resolve()


def unique(items):
    return list(dict.fromkeys(str(item) for item in items if item))


def issue_type(message):
    lower = message.lower()
    if ('reference mscz' in lower or 'reference-system' in lower or 'measure numbers differ' in lower
            or 'numbering compensation' in lower or 'nooffset' in lower
            or 'measurenumber' in lower or 'measurenumbermode' in lower):
        return 'reference_timeline'
    if any(word in lower for word in ['measure', 'rest', 'duration', 'pickup', 'backup', 'forward']):
        return 'rhythm_structure'
    if any(word in lower for word in ['part', 'staff', 'clef']):
        return 'staff_structure'
    if any(word in lower for word in ['lyric', 'text']):
        return 'text_recognition'
    if any(word in lower for word in ['playback', 'midi', 'program', 'bank', 'channel']):
        return 'playback'
    if any(word in lower for word in ['layout', 'break', 'page']):
        return 'layout'
    return 'notation'


ACTIONS = {
    'reference_timeline': 'Find the first drift, repair actual bars/durations/rest expansion, then remove every numbering offset or override; never compensate the displayed number.',
    'rhythm_structure': 'Compare the source PDF and proof at the named part/measure; correct bars, rests and durations in an editable copy.',
    'staff_structure': 'Compare staff grouping and clefs with the source PDF; correct the Audiveris OMR project first when possible.',
    'text_recognition': 'Compare text with the source PDF; remove only confirmed false OCR or restore confirmed lyrics.',
    'playback': 'Reapply the planned instrument mapping, export MIDI from the corrected MSCZ and verify programs/channels.',
    'layout': 'Compare every proof page; repair only explicit line/page breaks and collisions confirmed visually.',
    'notation': 'Compare the source PDF and proof visually; do not infer unclear pitches or durations.'
}


def build(verification, selection):
    messages = []
    for key in ['contentValidation', 'savedContentValidation']:
        messages.extend((verification.get(key) or {}).get('errors') or [])
    messages.extend(verification.get('errors') or [])
    for playback in verification.get('playbackValidation') or []:
        messages.extend(playback.get('errors') or [])
    messages.extend((verification.get('layoutValidation') or {}).get('errors') or [])
    messages = unique(messages)
    proof = []
    for page in (verification.get('contentValidation') or {}).get('proofPages') or []:
        proof.append({'page': page.get('page'), 'thumbnail': page.get('thumbnail')})
    issues = []
    for index, message in enumerate(messages, 1):
        measures = [int(value) for value in re.findall(r'measure(?: index)?\s+(\d+)', message, re.I)]
        parts = unique(re.findall(r'\bPart\s+([^,:]+?)(?=,|:)', message))
        kind = issue_type(message)
        issues.append({'id': f'issue-{index:03}', 'type': kind, 'message': message,
                       'parts': parts, 'measureIndices': measures,
                       'sourcePages': selection.get('sourcePages') or [],
                       'proofPages': proof, 'action': ACTIONS[kind],
                       'automaticOnlyWhenUnambiguous': True})
    return {'schemaVersion': 1, 'status': 'correction_required' if issues else 'no_issues',
            'maxIterations': 2, 'issues': issues,
            'rules': ['Work on a copy of score.mscz and preserve the original recognition output.',
                      'Inspect the linked source and proof pages before changing musical content.',
                      'Never change reviewed expectations to make an OMR result pass.',
                      'Do not guess pitches, durations, ties, accidentals or missing sounding measures when the PDF is ambiguous.',
                      'After each correction, export a new proof/MusicXML/MIDI and rerun all gates.']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--verification', required=True)
    parser.add_argument('--selection', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        verification = json.loads(absolute(args.verification).read_text(encoding='utf-8-sig'))
        selection = json.loads(absolute(args.selection).read_text(encoding='utf-8-sig'))
        result = build(verification, selection)
        output = absolute(args.output)
        if output.exists():
            raise FileExistsError(f'Refusing to overwrite: {output}')
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        code = 0
    except Exception as exc:
        result, code = {'status': 'failed', 'error': str(exc)}, 1
    print(json.dumps(result, ensure_ascii=False))
    return code


if __name__ == '__main__':
    raise SystemExit(main())


