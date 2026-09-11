"""Playback routing regressions using independent minimal SMF/MSCZ fixtures."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

spec=importlib.util.spec_from_file_location('playback',Path(__file__).parents[1]/'scripts/score-playback.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
NAMES=['Violin I','Violin II','Viola','Violoncello']

def score(path, names=NAMES, staves=1):
    root=ET.Element('museScore');s=ET.SubElement(root,'Score')
    for i,name in enumerate(names):
        part=ET.SubElement(s,'Part',id=str(i+1));ET.SubElement(part,'trackName').text=name
        for j in range(staves): ET.SubElement(part,'Staff',id=str(i*staves+j+1))
        inst=ET.SubElement(part,'Instrument',id='piano')
        ET.SubElement(inst,'instrumentId').text='keyboard.piano'
        ch=ET.SubElement(inst,'Channel');ET.SubElement(ch,'program',value='0')
        staff=ET.SubElement(s,'Staff',id=str(i+1));ET.SubElement(staff,'Measure',number='1')
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('score.mscx',ET.tostring(root))
        z.writestr('audiosettings.json',json.dumps({'activeSoundProfile':'Muse Sounds','tracks':[{'old':'piano'}]}))

def midi(path, programs=(40,40,41,42), names=NAMES, channels=None, late=None, bank=False, running=False):
    chunks=[]
    for i,(name,program) in enumerate(zip(names,programs)):
        ch=channels[i] if channels else i
        label=name.encode();data=b'\x00\xff\x03'+bytes([len(label)])+label
        if program is not None:data+=bytes([0,0xc0|ch,program])
        if bank:data+=bytes([0,0xb0|ch,32,1])
        data+=bytes([0,0x90|ch,60,80])
        if running:data+=bytes([1,61,80,1,61,0])
        if late is not None:data+=bytes([1,0xc0|ch,late,0,0x90|ch,62,80])
        data+=b'\x01\xff\x2f\x00'
        chunks.append(b'MTrk'+struct.pack('>I',len(data))+data)
    path.write_bytes(b'MThd'+struct.pack('>IHHH',6,1,len(chunks),480)+b''.join(chunks))

class PlaybackTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.d=Path(self.tmp.name);self.original=self.d/'original.mscz';score(self.original)
        self.fixed=self.d/'fixed.mscz';self.selection={'group':{'playbackInstruments':['violin','violin','viola','cello']}}
        self.before=self.original.read_bytes();p.apply(self.original,self.fixed,self.selection)
        self.mid=self.d/'score.mid'

    def verify(self,**kwargs):
        midi(self.mid,**kwargs)
        return p.verify(self.fixed,self.mid,self.selection)

    def test_correct_quartet_and_source_unchanged(self):
        self.assertEqual(self.verify()['status'],'passed')
        self.assertEqual(self.before,self.original.read_bytes())
        self.assertEqual([ET.tostring(s) for s in p.load_score(self.original)[1].findall('./Score/Staff')],
                         [ET.tostring(s) for s in p.load_score(self.fixed)[1].findall('./Score/Staff')])

    def test_piano_fallback(self): self.assertEqual(self.verify(programs=[0,0,0,0])['status'],'failed_playback_validation')
    def test_swapped_viola_cello(self): self.assertTrue(self.verify(programs=[40,40,42,41])['errors'])
    def test_missing_program(self): self.assertTrue(self.verify(programs=[None]*4)['errors'])
    def test_late_program_change(self): self.assertTrue(self.verify(late=0)['errors'])
    def test_wrong_bank(self): self.assertTrue(self.verify(bank=True)['errors'])
    def test_percussion_channel(self): self.assertTrue(self.verify(channels=[0,1,2,9])['errors'])
    def test_shared_channel(self): self.assertTrue(self.verify(channels=[0,0,2,3])['errors'])
    def test_track_order(self): self.assertTrue(self.verify(names=['Violin II','Violin I','Viola','Violoncello'])['errors'])
    def test_running_status_and_velocity_zero(self):
        result=self.verify(running=True);self.assertEqual(result['status'],'passed')
        self.assertEqual([t['noteCount'] for t in result['parts']],[2]*4)
    def test_saved_score_wrong_even_with_correct_midi(self):
        midi(self.mid);self.assertTrue(p.verify(self.original,self.mid,self.selection)['errors'])
    def test_no_inference_from_four_parts(self):
        unknown=self.d/'unknown.mscz';score(unknown,['A','B','C','D'])
        with self.assertRaises(ValueError): p.apply(unknown,self.d/'unknown-fixed.mscz',{'group':{}})
    def test_never_overwrite(self):
        with self.assertRaises(ValueError): p.apply(self.original,self.fixed,self.selection)
    def test_piano_two_staves(self):
        source=self.d/'piano.mscz';score(source,['Piano'],2)
        out=self.d/'piano-fixed.mscz';sel={'group':{'playbackInstruments':['piano']}}
        p.apply(source,out,sel);midi(self.mid,[0,0],['Piano','Piano'],[0,0])
        self.assertEqual(p.verify(out,self.mid,sel)['status'],'passed')
    def test_truncated_midi(self):
        midi(self.mid);self.mid.write_bytes(self.mid.read_bytes()[:-2])
        with self.assertRaises(ValueError):p.read_midi(self.mid)
    def test_brass_programs_and_piano_fallback(self):
        names=['Trombone','Baritone Horn','Euphonium']
        source=self.d/'brass.mscz';score(source,names)
        out=self.d/'brass-fixed.mscz';sel={'group':{'playbackInstruments':['trombone','baritone-horn','euphonium']}}
        p.apply(source,out,sel);midi(self.mid,[57,60,58],names)
        self.assertEqual(p.verify(out,self.mid,sel)['status'],'passed')
        midi(self.mid,[0,0,0],names)
        self.assertEqual(p.verify(out,self.mid,sel)['status'],'failed_playback_validation')
    def test_brass_names_are_distinct(self):
        for label,kind in [('长号 II','trombone'),('次中音号','baritone-horn'),('Baritone Horn','baritone-horn'),('Euph.','euphonium'),('上低音号','euphonium')]:
            self.assertEqual(p.infer(label),kind)
        self.assertIsNone(p.infer('Baritone Saxophone'))
        self.assertIsNone(p.infer('Baritone'))
    def test_brass_transposition_preserved(self):
        root=p.load_score(self.original)[1]
        inst=root.find('./Score/Part/Instrument')
        ET.SubElement(inst,'transposeChromatic').text='-14'
        ET.SubElement(inst,'transposeDiatonic').text='-8'
        source=self.d/'transposed.mscz'
        with zipfile.ZipFile(source,'w') as z:z.writestr('score.mscx',ET.tostring(root))
        out=self.d/'transposed-fixed.mscz'
        p.apply(source,out,{'group':{'playbackInstruments':['baritone-horn','trombone','euphonium','cello']}})
        result=p.load_score(out)[1].find('./Score/Part/Instrument')
        self.assertEqual(result.findtext('transposeChromatic'),'-14')
        self.assertEqual(result.findtext('transposeDiatonic'),'-8')

if __name__=='__main__':unittest.main(verbosity=2)
