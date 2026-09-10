"""Behavioral regression tests independent of OMR success; synthetic XML only."""
import copy
import importlib.util
import unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location('structure',Path(__file__).resolve().parents[1]/'scripts/score-structure.py')
s=importlib.util.module_from_spec(spec); spec.loader.exec_module(s)

class Gates(unittest.TestCase):
    def setUp(self):
        self.group={'id':'full-score','pages':[1,2,3,4], 'expectedParts':4,'lyricsExpected':False,
                    'expectedMeasuresPerPart':[28]*4,'allowedClefsPerPart':[['G'],['G'],['C'],['F']]}
        self.music={'parts':[{'id':f'P{i}', 'measures':28, 'clefs':[c], 'lyrics':0,'notes':112}
                             for i,c in enumerate(['G','G','C','F'],1)],'lyrics':0,'notes':448}
    def test_valid_quartet(self):
        self.assertEqual(s.check_music(self.music,self.group)[0],[])
    def test_concatenated_bars_blocked(self):
        self.music['parts'][3]['measures']=144
        self.assertTrue(any('measure' in e for e in s.check_music(self.music,self.group)[0]))
    def test_footer_as_lyrics_blocked(self):
        self.music['lyrics']=219
        self.assertTrue(any('lyric' in e for e in s.check_music(self.music,self.group)[0]))
    def test_cello_wrong_clef_blocked(self):
        self.music['parts'][3]['clefs']=['G','C','F']
        self.assertTrue(any('clef' in e for e in s.check_music(self.music,self.group)[0]))
    def test_valid_clef_change_allowed(self):
        self.music['parts'][3]['clefs']=['G','F']; self.group['allowedClefsPerPart'][3]=['F','G']
        self.assertEqual(s.check_music(self.music,self.group)[0],[])
    def test_unknown_counts_reported_not_invented(self):
        self.group['expectedMeasuresPerPart']=None
        self.assertTrue(any('NOT checked' in w for w in s.check_music(self.music,self.group)[1]))
    def test_single_candidate_wrong_parts_blocked(self):
        self.music['parts']=self.music['parts'][:1]
        self.assertTrue(s.check_music(self.music,self.group)[0])
    def test_grouping_four_plus_four(self):
        pages=[{'page':i,'systemStaffCounts':[4,4],'labels':['Violin I','Violin II','Viola','Violoncello']} for i in range(1,5)]
        pages += [{'page':i,'systemStaffCounts':[1]*4,'labels':[name]} for i,name in enumerate(['Violin I','Violin II','Viola','Violoncello'],5)]
        self.assertEqual([g['pages'] for g in s.draft_groups(pages)],[[1,2,3,4],[5],[6],[7],[8]])
    def test_unreviewed_and_wrong_hash_blocked(self):
        pre={'sourceSha256':'abc','pageCount':4,'suggestedGroups':[{'pages':[1,2,3,4]}]}
        plan={'sourceSha256':'wrong','reviewed':True,'reviewedPages':[1,2,3,4],'selectionBasis':'user','groups':[self.group]}
        with self.assertRaises(ValueError): s.validate_plan(plan,pre,'full-score')
        plan['sourceSha256']='abc'; plan['reviewed']=False
        with self.assertRaises(ValueError): s.validate_plan(plan,pre,'full-score')
    def test_duplicate_pages_blocked(self):
        pre={'sourceSha256':'abc','pageCount':4,'suggestedGroups':[{'pages':[1,2,3,4]}]}
        group=copy.deepcopy(self.group); group['pages']=[1,2,2,4]
        plan={'sourceSha256':'abc','reviewed':True,'reviewedPages':[1,2,3,4],'selectionBasis':'user','groups':[group]}
        with self.assertRaises(ValueError): s.validate_plan(plan,pre,'full-score')
    def test_blank_raster(self):
        import numpy as np
        from PIL import Image
        f=s.staff_features(Image.fromarray(np.full((1600,1200),255,dtype=np.uint8)))
        self.assertEqual(f['staffCount'],0); self.assertEqual(f['inkCoverage'],0)

if __name__=='__main__': unittest.main(verbosity=2)
