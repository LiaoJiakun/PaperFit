import copy
import unittest
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

from demo import QUESTION, CRITERIA, load_demo_results
from literature_search import find_papers, review_candidate
from paperfit import markdown_report


def button(app, label):
    return next(b for b in app.button if b.label == label)


class DiscoveryTests(unittest.TestCase):
    def test_confirmed_criteria_drive_queries_without_regeneration(self):
        with patch('literature_search.suggest_criteria') as suggest, \
             patch('literature_search.plan_queries', return_value=('query', '')) as plan, \
             patch('literature_search.search', return_value=(0, [])), \
             patch('literature_search.rank_candidates'):
            result = find_papers('old question', 'test', criteria={'研究对象':'edited population'})
        suggest.assert_not_called()
        self.assertIn('edited population', plan.call_args.args[0])
        self.assertNotIn('old question', plan.call_args.args[0])
        self.assertEqual(result[1], [])

    def test_retry_discards_stale_failure_fields(self):
        item = {'name':'paper','title':'paper','abstract':'text', 'pdfs':[], 'pmcid':'',
                'error':'old failure', 'source_note':'old missing full text'}
        with patch('literature_search.full_text', return_value=('PDF 全文', [{'page':1,'text':'x'*60}])), \
             patch('literature_search.screen_paper', return_value={'priority':'优先读', 'findings':[]}):
            result = review_candidate('q', CRITERIA, item, 'test')
        self.assertNotIn('error', result)
        self.assertNotIn('source_note', result)
        self.assertEqual(result['priority'], '优先读')

    def test_report_experience_label_and_links(self):
        report = markdown_report(QUESTION, CRITERIA, load_demo_results(), demo=True)
        self.assertNotIn('三篇', report)
        self.assertIn('历史实测结果', report)
        self.assertIn('https://', report)


if __name__ == '__main__':
    unittest.main()
