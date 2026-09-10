import importlib.util
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

spec=importlib.util.spec_from_file_location('layout',Path(__file__).parents[1]/'scripts/score-layout.py')
layout=importlib.util.module_from_spec(spec);spec.loader.exec_module(layout)

class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.d=Path(self.tmp.name);self.source=self.d/'source.mscz';self.out=self.d/'out.mscz'
        root=ET.Element('museScore');score=ET.SubElement(root,'Score');staff=ET.SubElement(score,'Staff',id='1')
        for subtype in ['line','page','section','nobreak','unknown']:
            measure=ET.SubElement(staff,'Measure');ET.SubElement(measure,'Note').text='original note'
            br=ET.SubElement(measure,'LayoutBreak');ET.SubElement(br,'subtype').text=subtype
        with zipfile.ZipFile(self.source,'w') as z:
            z.writestr('score.mscx',ET.tostring(root));z.writestr('audiosettings.json','{"keep":"original"}')
        self.before=self.source.read_bytes()
    def test_reflow_preserves_semantic_breaks_and_music(self):
        result=layout.apply(self.source,self.out,'reflow')
        self.assertEqual(result['removed'],{'line':1,'page':1})
        self.assertEqual(result['after'],{'section':1,'nobreak':1,'unknown':1})
        self.assertTrue(result['nonLayoutDataPreserved'])
        self.assertEqual(len(layout.load(self.out)[1].findall('.//Note')),5)
        self.assertEqual(self.before,self.source.read_bytes())
        with zipfile.ZipFile(self.out) as z:self.assertEqual(z.read('audiosettings.json'),b'{"keep":"original"}')
        self.assertEqual(layout.verify(self.out,result)['status'],'passed')
    def test_source_keeps_breaks(self):
        result=layout.apply(self.source,self.out,'source')
        self.assertEqual(result['before'],result['after'])
        self.assertEqual(result['removed'],{})
    def test_reintroduced_breaks_block_acceptance(self):
        result=layout.apply(self.source,self.out,'reflow')
        self.assertEqual(layout.verify(self.source,result)['status'],'failed_layout_validation')
    def test_no_overwrite(self):
        with self.assertRaises(ValueError):layout.apply(self.source,self.source,'reflow')
        self.assertEqual(self.source.read_bytes(),self.before)
    def test_moved_break_with_same_count_is_rejected(self):
        result=layout.apply(self.source,self.out,'source')
        name,root=layout.load(self.out)
        measures=root.findall('.//Measure')
        br=measures[0].find('LayoutBreak');measures[0].remove(br);measures[1].append(br)
        moved=self.d/'moved.mscz'
        with zipfile.ZipFile(moved,'w') as z:z.writestr(name,ET.tostring(root))
        self.assertEqual(layout.breaks(root),result['after'])
        self.assertEqual(layout.verify(moved,result)['status'],'failed_layout_validation')

if __name__=='__main__':unittest.main(verbosity=2)
