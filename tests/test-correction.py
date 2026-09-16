"""Correction worklist tests; no OMR or user score required."""
import importlib.util
import unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location('correction',Path(__file__).resolve().parents[1]/'scripts/score-correction.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)


class CorrectionTests(unittest.TestCase):
    def setUp(self):
        self.selection={'sourcePages':[2,3]}

    def test_no_errors_needs_no_correction(self):
        self.assertEqual(c.build({'errors':[]},self.selection)['status'],'no_issues')

    def test_measure_error_has_pdf_evidence_and_location(self):
        verification={'errors':['Part P2, measure index 17 (printed number 24): whole-measure rest duration is wrong.'],
                      'contentValidation':{'proofPages':[{'page':1,'thumbnail':'proof-1.png'}]}}
        issue=c.build(verification,self.selection)['issues'][0]
        self.assertEqual(issue['type'],'rhythm_structure')
        self.assertEqual(issue['parts'],['P2'])
        self.assertEqual(issue['measureIndices'],[17])
        self.assertEqual(issue['sourcePages'],[2,3])
        self.assertEqual(issue['proofPages'][0]['thumbnail'],'proof-1.png')

    def test_reference_and_playback_are_separate_tasks(self):
        verification={'savedContentValidation':{'errors':['Part 1 measure numbers differ from reference at indices [4].',
                                                          "Staff 1: numbering compensation noOffset='1' is forbidden."]},
                      'playbackValidation':[{'errors':['MIDI program mismatch.']}]}
        kinds=[issue['type'] for issue in c.build(verification,self.selection)['issues']]
        self.assertEqual(kinds,['reference_timeline','reference_timeline','playback'])

    def test_per_part_summary_is_not_mistaken_for_part_name(self):
        issue=c.build({'errors':['Per-part measure counts [7] differ from reviewed source [8].']},self.selection)['issues'][0]
        self.assertEqual(issue['parts'],[])


if __name__=='__main__': unittest.main(verbosity=2)


