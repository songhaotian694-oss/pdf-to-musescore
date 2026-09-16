"""Behavioral regression tests independent of OMR success; synthetic XML only."""
import copy
import importlib.util
import unittest
from pathlib import Path
import tempfile
import zipfile

spec=importlib.util.spec_from_file_location('structure',Path(__file__).resolve().parents[1]/'scripts/score-structure.py')
s=importlib.util.module_from_spec(spec); spec.loader.exec_module(s)
preprocess_spec=importlib.util.spec_from_file_location('preprocess',Path(__file__).resolve().parents[1]/'scripts/prepare-omr-input.py')
preprocess=importlib.util.module_from_spec(preprocess_spec); preprocess_spec.loader.exec_module(preprocess)


def make_mscz(path, staff_content):
    xml=f'<museScore><Score><Staff id="1"><Measure>{staff_content}</Measure></Staff></Score></museScore>'
    with zipfile.ZipFile(path,'w') as archive:
        archive.writestr('score.mscx',xml)

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
    def test_quality_penalty_prefers_closer_measure_count(self):
        close=copy.deepcopy(self.music); close['parts'][0]['measures']=27
        far=copy.deepcopy(self.music); far['parts'][0]['measures']=10
        close_errors=s.check_music(close,self.group)[0]
        far_errors=s.check_music(far,self.group)[0]
        self.assertLess(s.quality_penalty(close,self.group,close_errors)[0],
                        s.quality_penalty(far,self.group,far_errors)[0])
    def test_grayscale_fallback_preserves_page_count(self):
        from PIL import Image
        from pypdf import PdfReader
        with tempfile.TemporaryDirectory() as directory:
            directory=Path(directory); source=directory/'source.pdf'; output=directory/'output.pdf'
            pages=[Image.new('RGB',(160,220),'white'),Image.new('RGB',(160,220),'white')]
            pages[0].save(source,'PDF',save_all=True,append_images=pages[1:],resolution=72)
            report=preprocess.convert(source,output,300)
            self.assertEqual(report['profile'],'grayscale-300')
            self.assertEqual(len(PdfReader(output).pages),2)
            with self.assertRaises(FileExistsError): preprocess.convert(source,output,300)
    def test_reference_timeline_matches(self):
        bars=[{'index':1,'number':'0','durationQuarters':'1','meterQuarters':'4','restOnly':False,'systemStart':True},
              {'index':2,'number':'1','durationQuarters':'4','meterQuarters':'4','restOnly':True,'systemStart':False}]
        details={'parts':[{'measureDetails':copy.deepcopy(bars)}]}
        baseline={'parts':[{'measures':copy.deepcopy(bars)}],'referenceScore':'reference.mscz',
                  'referenceScoreSha256':'abc','scope':'timeline'}
        self.assertEqual(s.compare_reference(details,baseline)['status'],'passed')
    def test_reference_timeline_detects_structure_before_numbering(self):
        reference=[{'index':1,'number':'0','durationQuarters':'1','meterQuarters':'4','restOnly':False,'systemStart':True},
                   {'index':2,'number':'1','durationQuarters':'4','meterQuarters':'4','restOnly':True,'systemStart':True}]
        candidate=copy.deepcopy(reference); candidate[0]['durationQuarters']='4'; candidate[1]['restOnly']=False; candidate[1]['number']='2'
        result=s.compare_reference({'parts':[{'measureDetails':candidate}]},
                                   {'parts':[{'measures':reference}],'referenceScore':'reference.mscz',
                                    'referenceScoreSha256':'abc','scope':'timeline'})
        self.assertEqual(result['status'],'failed_measure_number_validation')
        self.assertTrue(any('durations' in error for error in result['errors']))
        self.assertTrue(any('rest timeline' in error for error in result['errors']))
        self.assertTrue(any('numbers' in error for error in result['errors']))
    def test_zero_number_offset_is_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            score=Path(directory)/'zero.mscz';make_mscz(score,'<noOffset>0</noOffset>')
            self.assertEqual(s.inspect_numbering_compensation(score)['status'],'passed_no_compensation')
    def test_nonzero_number_offset_is_forbidden(self):
        with tempfile.TemporaryDirectory() as directory:
            score=Path(directory)/'offset.mscz';make_mscz(score,'<noOffset>-2</noOffset>')
            result=s.inspect_numbering_compensation(score)
            self.assertEqual(result['status'],'numbering_compensation_detected')
            self.assertEqual(result['compensations'][0]['mechanism'],'noOffset')
    def test_manual_measure_number_is_forbidden(self):
        with tempfile.TemporaryDirectory() as directory:
            score=Path(directory)/'manual.mscz';make_mscz(score,'<MeasureNumber><text>24</text></MeasureNumber>')
            self.assertEqual(s.inspect_numbering_compensation(score)['status'],'numbering_compensation_detected')
    def test_measure_number_mode_override_is_forbidden(self):
        with tempfile.TemporaryDirectory() as directory:
            score=Path(directory)/'mode.mscz';make_mscz(score,'<measureNumberMode>0</measureNumberMode>')
            self.assertEqual(s.inspect_numbering_compensation(score)['status'],'numbering_compensation_detected')

if __name__=='__main__': unittest.main(verbosity=2)


