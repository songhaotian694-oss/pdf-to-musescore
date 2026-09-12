"""Original synthetic rest fixtures; no copyrighted user scores required."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

spec=importlib.util.spec_from_file_location('structure',Path(__file__).parents[1]/'scripts/score-structure.py')
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)

def attrs(beats='4',unit='4',divisions='4'):
    return f'<attributes><divisions>{divisions}</divisions><time><beats>{beats}</beats><beat-type>{unit}</beat-type></time></attributes>'

def rest(duration=16,hidden=False):
    return f'<note print-object="{"no" if hidden else "yes"}"><rest measure="yes"/><duration>{duration}</duration></note>'

PITCH='<note><pitch><step>C</step><octave>4</octave></pitch><duration>16</duration></note>'

class RestTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'original.musicxml'

    def inspect(self,bars,spans=None):
        text='<score-partwise><part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list><part id="P1">'
        text+=''.join(f'<measure number="{i}">{bar}</measure>' for i,bar in enumerate(bars,1))+'</part></score-partwise>'
        self.path.write_text(text,encoding='utf-8');before=self.path.read_bytes()
        details=s.music_details(self.path)
        group={'expectedParts':1,'lyricsExpected':False,'expectedMeasuresPerPart':None,'allowedClefsPerPart':None,
               'expectedRestSpansPerPart':None if spans is None else [spans]}
        errors,warnings=s.check_music(details,group)
        self.assertEqual(before,self.path.read_bytes())
        return details,errors,warnings

    def test_empty_bar_between_notes_is_blocked(self):
        _,errors,_=self.inspect([attrs()+PITCH,'',PITCH])
        self.assertTrue(any('measure index 2' in e and 'No timed notes/rests' in e for e in errors))

    def test_forward_only_is_unresolved_not_manufactured_rest(self):
        d,e,_=self.inspect([attrs()+'<forward><duration>16</duration></forward>'])
        self.assertTrue(e);self.assertEqual(d['parts'][0]['restSpans'],[])

    def test_grace_only_bar_is_unresolved(self):
        _,e,_=self.inspect([attrs()+'<note><grace/><pitch><step>C</step><octave>4</octave></pitch></note>'])
        self.assertTrue(e)

    def test_three_four_rest_uses_actual_duration_not_whole_glyph(self):
        _,e,_=self.inspect([attrs('3')+rest(12),rest(12)])
        self.assertEqual(e,[])

    def test_twelve_eight_and_inherited_divisions(self):
        _,e,_=self.inspect([attrs('12','8')+rest(24),rest(24),attrs('3','4','8')+rest(24)])
        self.assertEqual(e,[])

    def test_additive_meter(self):
        _,e,_=self.inspect([attrs('3+2','8')+rest(10)])
        self.assertEqual(e,[])

    def test_wrong_full_rest_duration_fails(self):
        _,e,_=self.inspect([attrs('3')+rest(16)])
        self.assertTrue(any('Whole-measure rest' in x for x in e))

    def test_full_rest_after_extra_eighth_is_not_a_valid_empty_bar(self):
        _,e,_=self.inspect([attrs()+'<note><rest/><duration>2</duration></note>'+rest()])
        self.assertTrue(e)

    def test_two_staff_rest_backup_is_valid(self):
        _,e,_=self.inspect([attrs()+rest()+'<backup><duration>16</duration></backup>'+rest().replace('</note>','<staff>2</staff></note>')])
        self.assertEqual(e,[])

    def test_multirest_does_not_double_count_underlying_measures(self):
        bars=[attrs()+'<attributes><measure-style><multiple-rest>8</multiple-rest></measure-style></attributes>'+rest()]+[rest()]*7+[PITCH]
        d,e,_=self.inspect(bars,[{'startMeasure':1,'measureCount':8}])
        self.assertEqual(e,[]);self.assertEqual(d['parts'][0]['measures'],9)
        self.assertEqual(d['parts'][0]['firstSoundingMeasure'],9)

    def test_extra_hidden_bar_shifts_entry_even_without_total_count_expectation(self):
        _,e,_=self.inspect([attrs()+rest(hidden=True)]+[rest()]*8+[PITCH],[{'startMeasure':1,'measureCount':8}])
        self.assertTrue(any('rest spans' in x for x in e))

    def test_collapsed_twenty_six_rests_fail(self):
        _,e,_=self.inspect([attrs()+rest()]+[rest()]*3+[PITCH],[{'startMeasure':1,'measureCount':26}])
        self.assertTrue(any('rest spans' in x for x in e))

    def test_multiple_rest_without_underlying_bars_is_blocked(self):
        _,e,_=self.inspect([attrs()+'<attributes><measure-style><multiple-rest>8</multiple-rest></measure-style></attributes>'+rest(),PITCH])
        self.assertTrue(any('Multiple-rest display' in x for x in e))

    def test_unknown_source_rest_expectations_are_disclosed(self):
        _,e,w=self.inspect([attrs()+rest()])
        self.assertEqual(e,[]);self.assertTrue(any('rest counts and entry positions were NOT checked' in x for x in w))

    def test_reviewed_no_rests_detects_omr_rest_replacing_note(self):
        _,e,_=self.inspect([attrs()+rest()],[])
        self.assertTrue(e)

    def test_invalid_plan_overlapping_spans(self):
        with self.assertRaises(ValueError):
            s.validate_rest_expectations({'expectedParts':1,'expectedRestSpansPerPart':[[{'startMeasure':1,'measureCount':8},{'startMeasure':8,'measureCount':2}]]})

if __name__=='__main__':unittest.main(verbosity=2)
