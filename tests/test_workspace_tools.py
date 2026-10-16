import unittest
from workspace_tools import paired_history, feedback_record, filter_history


class WorkspaceTests(unittest.TestCase):
    def test_notebook_filter_preserves_indices_and_source(self):
        items = [{'problem':'Solve 2X+3=11','mode':'single','final_answer':'4'},
                 {'problem':'Probability of heads','mode':'multi','final_answer':'1/2'}]
        self.assertEqual(filter_history(items, ' 2x '), [(0, items[0])])
        self.assertEqual(filter_history(items, '1/2', 'multi'), [(1, items[1])])
        self.assertEqual(filter_history(items, '', 'single'), [(0, items[0])])
        self.assertEqual(filter_history(items, 'unknown'), [])
        self.assertEqual(len(items), 2)
    def test_comparison_never_mixes_models_or_questions(self):
        items = [{'problem':'2+2','model':'a','mode':'single'},
                 {'problem':'2+2','model':'b','mode':'multi'},
                 {'problem':'3+3','model':'a','mode':'multi'}]
        self.assertEqual(paired_history(items), [])
        items.append({'problem':'2+2','model':'a','mode':'multi'})
        self.assertEqual(len(paired_history(items)), 1)

    def test_comparison_uses_latest_result(self):
        items = [{'problem':'q','model':'a','mode':'single','final_answer':'new'},
                 {'problem':'q','model':'a','mode':'single','final_answer':'old'},
                 {'problem':'q','model':'a','mode':'multi'}]
        self.assertEqual(paired_history(items)[0][2]['single']['final_answer'], 'new')

    def test_feedback_validates_bounds_and_minimizes_data(self):
        with self.assertRaises(ValueError):
            feedback_record('Solve a question', True, 6, 3, '')
        record = feedback_record('Solve a question', True, 4, 3, 'x'*1200)
        self.assertEqual(len(record['comment']), 1000)
        self.assertNotIn('problem', record)
        self.assertNotIn('api_key', record)
