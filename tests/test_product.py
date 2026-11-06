import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import history
from product_rules import validate, apply_policy
from streamlit.testing.v1 import AppTest
from demo import QUESTION, load_demo_results


def button(app, label):
    return next(b for b in app.button if b.label == label)


class LocalHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.patch = patch('history.ROOT', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_restore_versions_and_key_whitelist(self):
        refs = history.store_files([('paper.pdf', b'pdf-content')])
        draft = dict(question='q', source='上传 PDF', conditions=[], files=refs, api_key='SECRET')
        task = history.save_task(None, draft)
        self.assertNotIn('api_key', history.get_task(task))
        self.assertEqual(history.read_files(history.get_task(task)['files']), [('paper.pdf', b'pdf-content')])
        report = dict(draft, results=[{'name':'old'}], events=[])
        old = history.save_run(task, report, '已完成')
        report['results'][0]['name'] = 'new'
        new = history.save_run(task, report, '已完成')
        self.assertNotEqual(old,new)
        self.assertEqual(history.get_run(old)[0]['results'][0]['name'], 'old')
        self.assertNotIn('SECRET', (self.root/'history.sqlite3').read_bytes().decode(errors='ignore'))
        self.assertEqual(len(history.list_runs(task)),2)

    def test_delete_preserves_shared_files(self):
        refs=history.store_files([('a.pdf',b'shared')])
        draft=dict(question='a',files=refs)
        first=history.save_task(None,draft)
        second=history.save_task(None,draft)
        history.delete_task(first)
        self.assertEqual(history.read_files(refs)[0][1],b'shared')
        history.delete_task(second)
        self.assertEqual(list((self.root/'files').iterdir()),[])

    def test_invalid_file_reference_rejected(self):
        with self.assertRaises(ValueError):
            history.read_files([{'name':'x','digest':'../../secret'}])


class PolicyTests(unittest.TestCase):
    def test_dynamic_duplicate_and_empty_validation(self):
        rows=[{'条件':'研发环节','要求':'抗体设计','重要性':'优先考虑'}]
        self.assertEqual(validate(rows),{'研发环节':'抗体设计'})
        with self.assertRaises(ValueError): validate(rows*2)
        with self.assertRaises(ValueError): validate([])

    def test_required_unknown_is_not_excluded(self):
        rows=[{'条件':'研发环节','要求':'抗体设计','重要性':'必须满足'}]
        result=dict(priority='待人工核查',findings=[dict(criterion='研发环节',status='证据不足',verified=False)])
        self.assertEqual(apply_policy(result,rows)['eligibility'],'待核查')
        result['findings'][0].update(status='不匹配',verified=True)
        self.assertEqual(apply_policy(result,rows)['eligibility'],'不符合必须条件')

    def test_preference_mismatch_kept(self):
        rows=[{'条件':'方法','要求':'生成模型','重要性':'优先考虑'}]
        result=dict(priority='背景参考',findings=[dict(criterion='方法',status='不匹配',verified=True)])
        self.assertEqual(apply_policy(result,rows)['eligibility'],'可参考')


class InterfaceTests(LocalHistoryTests):
    def setUp(self):
        super().setUp()
        self.key_patch=patch('criteria.configured_key',return_value='test-key')
        self.key_patch.start()
        self.addCleanup(self.key_patch.stop)
        self.app=self.create_app()

    def create_app(self):
        return AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'), default_timeout=15).run()

    def setup_example(self):
        self.app.button(key='home_new').click().run()
        button(self.app,'填入示例问题').click().run()
        self.assertFalse(self.app.exception)

    def test_experience_offline_and_new_keeps_history(self):
        self.setup_example()
        task=self.app.session_state['task_id']
        button(self.app,'首页').click().run()
        with patch('criteria.request_json',side_effect=AssertionError('offline')):
            button(self.app,'体验').click().run()
        self.assertFalse(self.app.exception)
        self.assertTrue(self.app.session_state['report']['demo'])
        self.app.button(key='nav_new').click().run()
        self.assertTrue(history.get_task(task))
        self.assertNotIn('report',self.app.session_state)

    def test_draft_restored_in_new_session(self):
        self.setup_example()
        self.app.text_input(key='question_widget').set_value('AI 如何辅助抗体研发？').run()
        app2=self.create_app()
        button(app2,'继续编辑').click().run()
        self.assertEqual(app2.text_input(key='question_widget').value,'AI 如何辅助抗体研发？')
        self.assertFalse(app2.exception)

    def test_conditions_passed_and_versions_retained(self):
        self.setup_example()
        value = next(x for x in self.app.text_input if x.label == '第 1 项要求')
        value.set_value('术后胰腺癌患者').run()
        self.app.selectbox[0].select('必须满足').run()
        observed={}
        def fake(q,k,p,*,criteria,on_result):
            observed.update(criteria)
            r=copy.deepcopy(load_demo_results()[0])
            on_result(r,[],[])
            return criteria,[r],[],[]
        with patch('literature_search.find_papers',side_effect=fake):
            button(self.app,'确认条件并开始').click().run()
        self.assertFalse(self.app.exception)
        self.assertEqual(observed['研究对象'],'术后胰腺癌患者')
        old=self.app.session_state['report']['run_id']
        button(self.app,'修改条件').click().run()
        with patch('literature_search.find_papers',side_effect=TimeoutError()):
            button(self.app,'确认条件并开始').click().run()
        self.assertFalse(self.app.exception)
        task=self.app.session_state['task_id']
        self.assertEqual(len(history.list_runs(task)),2)
        self.assertEqual(history.get_run(old)[1],'已完成')
        self.assertEqual(self.app.session_state['report']['status'],'未完成')

    def test_upload_retry_new_version(self):
        self.setup_example()
        button(self.app,'上传 PDF').click().run()
        papers=[('broken.pdf',b'broken'),('good.pdf',b'good')]
        self.app.session_state['uploads']=papers
        self.app.session_state['draft']['files']=history.store_files(papers)
        self.app.run()
        good=copy.deepcopy(load_demo_results()[0])
        failure=dict(name='broken.pdf',priority='待人工核查',short_pages=[],findings=[],error='无法打开 PDF')
        def batch(q,c,p,k): yield copy.deepcopy(failure if p[0][0]=='broken.pdf' else good)
        with patch('paperfit.screen_batch',side_effect=batch):
            button(self.app,'确认条件并开始').click().run()
        self.assertFalse(self.app.exception)
        original=self.app.session_state['report']['run_id']
        with patch('paperfit.screen_batch',return_value=iter([good])) as retry:
            button(self.app,'重试这篇').click().run()
        self.assertFalse(self.app.exception)
        self.assertEqual(retry.call_args.args[2],[papers[0]])
        self.assertEqual(history.get_run(original)[1],'部分失败')
        self.assertEqual(self.app.session_state['report']['status'],'已完成')
        self.assertEqual(len(history.list_runs(self.app.session_state['task_id'])),2)

    def test_missing_input_explained(self):
        self.app.button(key='home_new').click().run()
        self.assertTrue(button(self.app,'确认条件并开始').disabled)
        self.assertTrue(any('至少填写一项' in c.value for c in self.app.caption))

    def test_condition_add_remove_persist(self):
        self.setup_example()
        button(self.app,'＋ 添加条件').click().run()
        next(x for x in self.app.text_input if x.label == '第 4 项条件').set_value('验证方法').run()
        next(x for x in self.app.text_input if x.label == '第 4 项要求').set_value('临床数据').run()
        self.app.button(key='del_condition_0').click().run()
        draft=history.get_task(self.app.session_state['task_id'])
        self.assertEqual(draft['conditions'][-1]['要求'],'临床数据')
        self.assertEqual(len(draft['conditions']),3)
        self.assertFalse(self.app.exception)

    def test_evidence_return_retains_filter_and_process(self):
        self.app.button(key='home_demo').click().run()
        self.app.button(key='filter_背景参考').click().run()
        button(self.app,'查看依据').click().run()
        self.assertEqual(self.app.session_state['view'],'evidence')
        self.assertTrue(any('把判断' in x.value for x in self.app.title))
        button(self.app,'返回阅读清单').click().run()
        self.assertEqual(self.app.session_state['result_filter'],'背景参考')
        button(self.app,'查看执行过程').click().run()
        self.assertEqual(self.app.session_state['view'],'process')
        self.assertFalse(self.app.exception)

    def test_session_key_survives_settings_navigation(self):
        self.app.button(key='nav_settings').click().run()
        self.app.text_input(key='api_input').set_value('test-session-secret').run()
        self.app.button(key='nav_home').click().run()
        self.app.button(key='nav_settings').click().run()
        self.assertEqual(self.app.text_input(key='api_input').value,'test-session-secret')
        self.assertFalse(history.list_tasks())
        self.assertFalse(self.app.exception)

    def test_delete_requires_confirmation(self):
        self.setup_example()
        task=self.app.session_state['task_id']
        self.app.button(key='nav_history').click().run()
        button(self.app,'删除任务').click().run()
        self.assertIsNotNone(history.get_task(task))
        button(self.app,'取消，保留任务').click().run()
        self.assertIsNotNone(history.get_task(task))
        button(self.app,'删除任务').click().run()
        button(self.app,'确认删除').click().run()
        self.assertIsNone(history.get_task(task))
        self.assertEqual(self.app.session_state['view'],'history')
        self.assertFalse(self.app.exception)
