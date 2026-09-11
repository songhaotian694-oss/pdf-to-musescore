"""Set MuseScore playback instruments on a copy and verify actual SMF events.

Program values are zero-based: violin=40, viola=41, cello=42, piano=0.
MSCX Instrument/Channel format verified against installed MuseScore 4 templates.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import xml.etree.ElementTree as ET
import zipfile

CATALOG = {
    'violin': ('violin', 'strings.violin', 'Violin', 40),
    'viola': ('viola', 'strings.viola', 'Viola', 41),
    'cello': ('violoncello', 'strings.cello', 'Cello', 42),
    'piano': ('piano', 'keyboard.piano', 'Piano', 0),
    'trombone': ('trombone', 'brass.trombone', 'Trombone', 57),
    'baritone-horn': ('baritone-horn', 'brass.baritone-horn', 'Baritone Horn', 60),
    'euphonium': ('euphonium', 'brass.euphonium', 'Euphonium', 58),
}


def load_score(path):
    with zipfile.ZipFile(path) as archive:
        names = [n for n in archive.namelist() if n.endswith('.mscx') and '/' not in n]
        if len(names) != 1:
            raise ValueError('MSCZ must contain exactly one main MSCX score.')
        data = archive.read(names[0])
        if len(data) > 50_000_000 or b'<!ENTITY' in data.upper():
            raise ValueError('Oversized MSCX or entity declaration.')
        return names[0], ET.fromstring(data)


def infer(label):
    normalized = re.sub(r'\s+', ' ', label.strip().lower())
    if re.fullmatch(r'(violin|vln\.?|小提琴)(\s*(i{1,2}|[12一二]))?', normalized):
        return 'violin'
    if normalized in ['viola','vla.','中提琴']:
        return 'viola'
    if normalized in ['cello','violoncello','vc.','大提琴']:
        return 'cello'
    if normalized in ['piano','pno.','钢琴']:
        return 'piano'
    if re.fullmatch(r'(trombone|tenor trombone|tbn\.?|长号)(\s*(i{1,3}|[123一二三]))?', normalized):
        return 'trombone'
    if re.fullmatch(r'(baritone horn|baritone-horn|次中音号)(\s*(i{1,3}|[123一二三]))?', normalized):
        return 'baritone-horn'
    if re.fullmatch(r'(euphonium|euph\.?|上低音号)(\s*(i{1,3}|[123一二三]))?', normalized):
        return 'euphonium'
    return None


def set_text(parent, tag, value):
    el = parent.find(tag)
    if el is None:
        el = ET.SubElement(parent, tag)
    el.text = str(value)


def instruments(root, selection):
    parts = root.findall('./Score/Part')
    if root.findall('.//InstrumentChange'):
        raise ValueError('Mid-score instrument changes need an explicit change-aware mapping; refusing to flatten them.')
    requested = selection.get('group', {}).get('playbackInstruments')
    if requested is not None and (not isinstance(requested, list) or len(requested) != len(parts)):
        raise ValueError('playbackInstruments must specify one instrument per part, in source order.')
    mapped = []
    for i, part in enumerate(parts):
        label = part.findtext('trackName') or part.findtext('./Instrument/longName') or ''
        kind = requested[i].lower() if requested is not None else infer(label)
        if kind == 'violoncello': kind = 'cello'
        if kind not in CATALOG:
            raise ValueError(f'Playback instrument is unknown for part {i+1} ({label}). Set reviewed playbackInstruments from {list(CATALOG)}. Do not guess from part count/clef.')
        if len(part.findall('Instrument')) != 1:
            raise ValueError('Expected one initial instrument per part.')
        inst_id, sound_id, name, program = CATALOG[kind]
        mapped.append({'partIndex': i, 'partId': part.get('id'), 'label': label,
                       'instrument': kind, 'instrumentId': inst_id, 'soundId': sound_id,
                       'trackName': name, 'program0': program, 'program1': program+1,
                       'staves': len(part.findall('Staff'))})
    return parts, mapped


def apply(source, output, selection):
    if output.exists(): raise ValueError('Output already exists; never overwrite a score.')
    entry_name, root = load_score(source)
    parts, mapping = instruments(root, selection)
    before = [ET.tostring(s) for s in root.findall('./Score/Staff')]
    for part, item in zip(parts, mapping):
        instrument = part.find('Instrument')
        instrument.set('id', item['instrumentId'])
        set_text(instrument, 'instrumentId', item['soundId'])
        set_text(instrument, 'trackName', item['trackName'])
        # Keep display names, Staff elements, note data, dynamics and articulation.
        channels = instrument.findall('Channel')
        if not channels: channels = [ET.SubElement(instrument, 'Channel')]
        for i, channel in enumerate(channels):
            channel_name = channel.get('name', '')
            if i == 0 or channel_name in ['', 'normal', 'arco']:
                program = item['program0']
            elif item['instrument'] in ['violin','viola','cello'] and channel_name in ['pizzicato','tremolo']:
                program = {'pizzicato':45, 'tremolo':44}[channel_name]
            else:
                raise ValueError(f'Unmapped articulation channel: {channel_name}')
            for child in list(channel):
                if child.tag == 'program' or (child.tag == 'controller' and child.get('ctrl') in ['0','32']):
                    channel.remove(child)
            ET.SubElement(channel, 'controller', ctrl='0', value='0')
            ET.SubElement(channel, 'controller', ctrl='32', value='0')
            ET.SubElement(channel, 'program', value=str(program))
            set_text(channel, 'synti', 'Fluid')
    if before != [ET.tostring(s) for s in root.findall('./Score/Staff')]:
        raise ValueError('Unexpected notation mutation.')
    with zipfile.ZipFile(source) as old, zipfile.ZipFile(output, 'x') as new:
        audio = json.loads(old.read('audiosettings.json')) if 'audiosettings.json' in old.namelist() else {}
        # A known local sound profile resolves the assigned IDs/programs. Remove
        # stale piano/VST track overrides only in this newly generated copy.
        reset_count = len(audio.get('tracks', []))
        audio['activeSoundProfile'] = 'MuseScore Basic'
        audio['tracks'] = []
        for entry in old.infolist():
            data = old.read(entry.filename)
            if entry.filename == entry_name:
                data = ET.tostring(root, encoding='utf-8', xml_declaration=True)
            elif entry.filename == 'audiosettings.json':
                data = json.dumps(audio).encode('utf-8')
            new.writestr(entry, data)
        if 'audiosettings.json' not in old.namelist():
            new.writestr('audiosettings.json', json.dumps(audio))
    return {'status':'assigned', 'parts':mapping, 'profile':'MuseScore Basic',
            'resetTrackOverrides':reset_count, 'source':str(source), 'output':str(output),
            'sourceSha256':hashlib.sha256(source.read_bytes()).hexdigest(), 'notationPreserved':True}


def vlq(data, offset):
    value = 0
    for _ in range(4):
        if offset >= len(data): raise ValueError('Truncated MIDI variable-length quantity.')
        b = data[offset]; offset += 1
        value = (value << 7) | (b & 127)
        if b < 128: return value, offset
    raise ValueError('Invalid MIDI variable-length quantity.')


def read_midi(path):
    data = path.read_bytes()
    if len(data) < 14 or data[:4] != b'MThd': raise ValueError('Invalid MIDI header.')
    length = int.from_bytes(data[4:8], 'big')
    if length < 6 or 8+length > len(data): raise ValueError('Invalid MIDI header length.')
    fmt, count, _ = struct.unpack('>HHH', data[8:14])
    if fmt not in [0,1] or count < 1: raise ValueError('Only MIDI format 0/1 is supported.')
    pos, events, tracks = 8+length, [], []
    for track_index in range(count):
        if data[pos:pos+4] != b'MTrk': raise ValueError('Missing MIDI track chunk.')
        size=int.from_bytes(data[pos+4:pos+8],'big'); pos+=8
        track=data[pos:pos+size]; pos+=size
        if len(track)!=size: raise ValueError('Truncated MIDI track.')
        offset, tick, running, sequence = 0, 0, None, 0
        label = ''
        while offset < len(track):
            delta,offset=vlq(track,offset); tick+=delta
            if offset>=len(track): raise ValueError('Missing MIDI event.')
            status=track[offset]
            if status >= 128: offset+=1
            elif running is not None: status=running
            else: raise ValueError('Invalid MIDI running status.')
            if status==255:
                if offset>=len(track): raise ValueError('Truncated meta event.')
                typ=track[offset]; offset+=1; size,offset=vlq(track,offset)
                payload=track[offset:offset+size]; offset+=size
                if len(payload)!=size: raise ValueError('Truncated MIDI meta payload.')
                if typ==3: label=payload.decode('utf-8',errors='replace')
                running=None
            elif status in [240,247]:
                size,offset=vlq(track,offset); offset+=size; running=None
                if offset>len(track): raise ValueError('Truncated SysEx.')
            elif 128 <= status < 240:
                running=status; kind=status>>4; channel=status&15
                size=1 if kind in [12,13] else 2
                values=track[offset:offset+size];offset+=size
                if len(values)!=size or any(v>=128 for v in values): raise ValueError('Invalid MIDI channel event.')
                events.append((tick,track_index,sequence,kind,channel,list(values)))
            else: raise ValueError('Unsupported MIDI status.')
            sequence+=1
        tracks.append({'track':track_index,'label':label,'notes':[], 'programChanges':[]})
    if pos!=len(data): raise ValueError('Unexpected trailing MIDI bytes.')
    states={}
    for tick,tr,seq,kind,ch,values in sorted(events):
        state=states.setdefault(ch,{'program':None,'bankMSB':0,'bankLSB':0})
        if kind==12:
            state['program']=values[0]
            tracks[tr]['programChanges'].append({'tick':tick,'channel':ch,'program0':values[0]})
        elif kind==11 and values[0] in [0,32]:
            state['bankMSB' if values[0]==0 else 'bankLSB']=values[1]
        elif kind==9 and values[1]>0:
            tracks[tr]['notes'].append({'tick':tick,'pitch':values[0],'channel':ch,'program0':state['program'],
                                        'bankMSB':state['bankMSB'],'bankLSB':state['bankLSB']})
    return tracks


def verify(score, midi, selection):
    _,root=load_score(score)
    parts,mapping=instruments(root,selection)
    errors=[]
    for part,item in zip(parts,mapping):
        inst=part.find('Instrument'); channel=inst.find('Channel')
        if inst.get('id')!=item['instrumentId'] or inst.findtext('instrumentId')!=item['soundId']:
            errors.append(f"{item['label']}: wrong saved instrument ID.")
        if channel is None or channel.find('program') is None or channel.find('program').get('value')!=str(item['program0']):
            errors.append(f"{item['label']}: wrong saved main-channel program.")
    with zipfile.ZipFile(score) as z:
        audio=json.loads(z.read('audiosettings.json')) if 'audiosettings.json' in z.namelist() else {}
    if audio.get('activeSoundProfile')!='MuseScore Basic' or audio.get('tracks'):
        errors.append('Sound profile or explicit track overrides differ from the validated MuseScore Basic routing.')
    tracks=[t for t in read_midi(midi) if t['notes']]
    expected=mapping
    if len(tracks)!=len(mapping):
        expected=[item for item in mapping for _ in range(item['staves'])]
    if len(tracks)!=len(expected):
        errors.append(f'Expected {len(mapping)} part tracks or {sum(i["staves"] for i in mapping)} staff tracks with notes; found {len(tracks)}.')
    used={}
    summary=[]
    for track,item in zip(tracks,expected):
        programs=sorted({n['program0'] for n in track['notes']},key=lambda n:-1 if n is None else n)
        channels=sorted({n['channel'] for n in track['notes']})
        if track['label'] and track['label']!=item['label']:
            errors.append(f"Track order/name mismatch: {track['label']} vs {item['label']}.")
        for channel in channels:
            if channel==9: errors.append('A pitched part uses percussion channel 10.')
            if channel in used and used[channel]!=item['partIndex']:
                errors.append(f'Parts share MIDI channel {channel+1}; independent routing is not verified.')
            used[channel]=item['partIndex']
        # Conservative initial implementation: non-arco program changes need
        # articulation-aware review, never accept piano fallback as an effect.
        if programs != [item['program0']]:
            errors.append(f"{item['label']}: actual note programs {programs}, expected {item['program0']} (zero-based). Review program changes/articulations.")
        if any(n['bankMSB'] or n['bankLSB'] for n in track['notes']):
            errors.append(f"{item['label']}: non-GM bank active at a note.")
        summary.append({'part':item['label'],'instrument':item['instrument'],'track':track['track'],
                        'channels1':[c+1 for c in channels],'programs0':programs,
                        'expectedProgram0':item['program0'],'expectedProgram1':item['program1'],'noteCount':len(track['notes'])})
    return {'status':'failed_playback_validation' if errors else 'passed', 'errors':errors,
            'profile':'MuseScore Basic','parts':summary,'savedScore':str(score),'midi':str(midi),
            'scope':'Saved instrument IDs and every MIDI note-on program/bank; not a listening or installed soundfont-quality test.'}


def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['apply','verify'])
    p.add_argument('--score',required=True);p.add_argument('--selection',required=True)
    p.add_argument('--output');p.add_argument('--midi');p.add_argument('--report',required=True)
    p.add_argument('--assignment', help='Freeze expected instruments/names from the original assignment report.')
    args=p.parse_args()
    try:
        for value in [args.score,args.selection,args.report,args.output,args.midi,args.assignment]:
            if value and not Path(value).is_absolute(): raise ValueError('Use absolute paths.')
        selection=json.loads(Path(args.selection).read_text(encoding='utf-8-sig'))
        assignment = None
        if args.assignment:
            assignment=json.loads(Path(args.assignment).read_text(encoding='utf-8-sig'))
            if assignment.get('status')!='assigned': raise ValueError('Invalid playback assignment report.')
            selection.setdefault('group', {})['playbackInstruments']=[i['instrument'] for i in assignment['parts']]
        if args.mode=='apply': result=apply(Path(args.score),Path(args.output),selection)
        else:
            result=verify(Path(args.score),Path(args.midi),selection)
            if assignment:
                _,root=load_score(Path(args.score))
                _,current=instruments(root,selection)
                if [(i['partId'],i['label']) for i in current] != [(i['partId'],i['label']) for i in assignment['parts']]:
                    result['errors'].append('Saved part identities differ from the original playback assignment.')
                    result['status']='failed_playback_validation'
        code=4 if result['status']=='failed_playback_validation' else 0
    except Exception as e:
        result={'status':'failed_playback_validation','errors':[str(e)]};code=4
    with open(args.report,'x',encoding='utf-8') as f: json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False));return code

if __name__=='__main__':sys.exit(main())
