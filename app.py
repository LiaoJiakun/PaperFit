"""PaperFit: a small, guided research-to-reading-list workflow."""
import copy
from datetime import datetime
import streamlit as st
import ui
import history
from product_rules import suggest_conditions, validate, apply_policy

from criteria import configured_key
from demo import CRITERIA, QUESTION, load_demo_results
from errors import friendly_error
from literature_search import find_papers, review_candidate, source_label
from paperfit import PRIORITIES, evidence_location, markdown_report, screen_batch
from screen_paper import active_criteria
from setup_deepseek import save_key

st.set_page_config(page_title="PaperFit · 决定先读哪篇论文", page_icon="📄", layout="wide")
MAX_PAPERS = 20
ui.install()

ss = st.session_state
ss.setdefault("view", "home")
ss.setdefault("draft", {"question": "", "source": "自动找论文", "conditions": [], "files": []})
ss.setdefault("uploads", [])
ss.setdefault("editor_rev", 0)


def persist():
    draft = ss["draft"]
    if draft["question"].strip() or draft["conditions"] or draft["files"]:
        ss["task_id"] = history.save_task(ss.get("task_id"), draft)


def navigate(view):
    if view == "setup" and ss.get("report", {}).get("demo"):
        ss.pop("report", None)
        if ss.get("last_real_report"):
            ss["report"] = ss["last_real_report"]
    ss["view"] = view
    ss["scroll_top"] = True


def reset_widgets():
    for name in list(ss):
        if name in ("question_widget", "source_widget", "upload_widget", "result_filter") or name.startswith("conditions_"):
            del ss[name]
    ss["editor_rev"] = ss.get("editor_rev", 0) + 1


def new_task():
    persist()
    for name in ("task_id", "report", "last_real_report", "suggested_for", "delete_id"):
        ss.pop(name, None)
    reset_widgets()
    ss["draft"] = {"question": "", "source": "自动找论文", "conditions": [], "files": []}
    ss["uploads"] = []
    navigate("setup")


def save_draft(widget, name):
    ss["draft"][name] = ss[widget]
    persist()


def remember_files():
    ss["uploads"] = [(f.name, f.getvalue()) for f in ss.get("upload_widget", [])]
    ss["draft"]["files"] = history.store_files(ss["uploads"])
    persist()


def edit_condition(index, field, widget):
    ss["draft"]["conditions"][index][field] = ss[widget]
    persist()


def add_condition():
    ss["draft"]["conditions"].append({"条件":"", "要求":"", "重要性":"优先考虑"})
    ss["editor_rev"] += 1
    persist()


def remove_condition(index):
    ss["draft"]["conditions"].pop(index)
    ss["editor_rev"] += 1
    persist()


def choose_source(source):
    ss["draft"]["source"] = source
    persist()


def example():
    ss["question_widget"] = QUESTION
    ss["draft"]["question"] = QUESTION
    ss["draft"]["conditions"] = [{"条件": k, "要求": v, "重要性": "优先考虑"} for k, v in CRITERIA.items() if v]
    ss["editor_rev"] += 1
    ss["suggested_for"] = QUESTION
    persist()


def experience():
    if ss.get("report") and not ss["report"].get("demo"):
        ss["last_real_report"] = ss["report"]
    ss.pop("result_filter", None)
    conditions = [{"条件": k, "要求": v, "重要性": "优先考虑"} for k,v in CRITERIA.items() if v]
    ss["report"] = {"question": QUESTION, "criteria": dict(CRITERIA), "conditions": conditions,
                    "results": [apply_policy(r, conditions) for r in load_demo_results()], "demo": True,
                    "searches": [], "candidates": [], "events": [], "source": "体验", "status": "体验"}
    navigate("results")


def open_task(task_id, run_id=None):
    reset_widgets()
    draft = history.get_task(task_id)
    if not draft:
        navigate("history")
        return
    ss["task_id"] = task_id
    ss.pop("report", None)
    ss.pop("last_real_report", None)
    if run_id:
        report, status = history.get_run(run_id)
        if report:
            report.update(demo=False, run_id=run_id, status=status)
            ss["report"] = report
            ss["last_real_report"] = report
            draft = {k: copy.deepcopy(report.get(k) or ([] if k in ("conditions", "files") else ""))
                     for k in ("question", "source", "conditions", "files")}
    ss["draft"] = draft
    try:
        ss["uploads"] = history.read_files(draft.get("files") or [])
        ss.pop("file_warning", None)
    except (OSError, ValueError):
        ss["uploads"] = []
        ss["file_warning"] = "本机保存的部分 PDF 无法读取，请重新上传后运行；已有结果仍可查看。"
    navigate("results" if ss.get("report") else "setup")


def checkpoint(report, status):
    report["status"] = status
    report["run_id"] = history.save_run(ss["task_id"], report, status, report.get("run_id"))
    ss["report"] = report
    ss["last_real_report"] = report


def local_time(value):
    return datetime.fromisoformat(value).astimezone().strftime("%m-%d %H:%M:%S")


def show_tasks(limit=None):
    tasks = history.list_tasks()
    if not tasks:
        with ui.card('empty'):
            st.subheader('你的研究，会保存在这里')
            ui.text('草稿、上传文件和每次运行结果都可以回看。', 'muted')
            with ui.actions():
                st.button('新建研究', key='empty_new', type='primary', on_click=new_task)
                st.button('体验', key='empty_demo', on_click=experience)
        return
    for task_id, title, updated in tasks[:limit]:
        runs = history.list_runs(task_id)
        draft = history.get_task(task_id)
        with ui.card(f'task_{task_id}'):
            ui.text(title, 'title')
            ui.text(f"{draft['source']} · {len(runs)} 个结果版本 · 更新于 {local_time(updated)}" if runs else
                    f"草稿 · {len(draft.get('conditions') or [])} 项条件 · 尚未运行", 'meta')
            with ui.actions():
                if runs:
                    ui.badges([(f'版本 {len(runs)} · {runs[0][2]}', 'positive' if runs[0][2]=='已完成' else 'warning')])
                    st.button('打开结果', key=f'open_{task_id}', type='primary', on_click=open_task, args=(task_id,runs[0][0]))
                st.button('继续编辑', key=f'edit_{task_id}', on_click=open_task, args=(task_id,))
                if limit is None:
                    st.button('删除任务', key=f'delete_{task_id}', type='tertiary', on_click=ask_delete, args=(task_id,))
            if limit is None and len(runs)>1:
                with st.expander(f'过去的 {len(runs)-1} 个版本', expanded=len(runs)==2):
                    for i,(run_id,created,status) in enumerate(runs[1:],1):
                        with st.container(key=f'old_version_{run_id}'):
                            ui.text(f'版本 {len(runs)-i} · {status}', 'body')
                            ui.text(f'{local_time(created)} · 保留当时的条件、已完成结果与失败原因。', 'meta')
                            st.button('打开旧版本', key=f'old_{run_id}', type='tertiary', on_click=open_task, args=(task_id,run_id))


def ask_delete(task_id):
    ss['delete_id'] = task_id
    navigate('delete')


def delete_current():
    target = ss.pop('delete_id', None)
    if target:
        history.delete_task(target)
        if target == ss.get('task_id'):
            for name in ('task_id','report','last_real_report'):
                ss.pop(name,None)
            ss['draft'] = {'question':'','source':'自动找论文','conditions':[],'files':[]}
            ss['uploads'] = []
            reset_widgets()
    navigate('history')


def explanation(result):
    if result.get('error'):
        return result['error']
    if result.get('source_note'):
        return result['source_note']
    findings = result.get('findings', [])
    differences = [r['reason'] for r in findings if r['status'] != '匹配']
    if differences:
        return differences[0]
    if findings:
        return '；'.join(r['reason'].rstrip('。') for r in findings)
    return result.get('triage_reason') or '需要人工核查原文。'


def edit_report():
    if ss['report'].get('demo'):
        # Start from the example without replacing any real task or result version.
        new_task()
        example()
    navigate('setup')


def open_evidence(index):
    ss['paper_index'] = index
    navigate('evidence')


def render_conditions(rows):
    for row in rows:
        ui.text(f"{row['条件']}：{row['要求']} · {row['重要性']}")


def render_process(report):
    if report.get('demo'):
        ui.text('这里展示已保存的筛选结果；历史记录未保存的搜索步骤不会补造。', 'muted')
    for event in report.get('events',[]):
        ui.text(event)
    for entry in report.get('searches',[]):
        st.caption('请求失败' if entry['hits'] is None else f"数据库命中 {entry['hits']} 条")
        st.code(entry['query'], language=None, wrap_lines=True)
    if report.get('candidates'):
        labels={'direct':'直接匹配','background':'背景相关','unclear':'待核查','low':'低相关'}
        with st.expander(f"查看 {len(report['candidates'])} 条摘要初筛记录"):
            for item in report['candidates']:
                ui.text(f"{labels[item['rank']]} · {item['title']}", 'title')
                ui.text(source_label(item), 'meta')
                ui.text(item['triage_reason'])
                st.link_button('打开论文记录',item['url'])


def retry_paper(index, key):
    report = ss['report']
    result = report['results'][index]
    updated = copy.deepcopy(report)
    updated['parent_run'] = updated.pop('run_id',None)
    checkpoint(updated,'正在执行')
    try:
        with st.spinner('正在重试；结果将保存为新版本…'):
            if report['source']=='上传 PDF':
                papers = history.read_files([report['files'][index]])
                fresh = next(screen_batch(report['question'],report['criteria'],papers,key))
                fresh['source_kind']='上传的 PDF'
            else:
                fresh=review_candidate(report['question'],report['criteria'],result,key)
            updated['results'][index]=apply_policy(fresh,report['conditions'])
            updated['events'].append(f"单篇重试 · {result.get('title',result['name'])} · {fresh['priority']}")
        checkpoint(updated,'部分失败' if any(r.get('error') for r in updated['results']) else '已完成')
    except Exception as error:
        updated['events'].append(friendly_error(error))
        checkpoint(updated,'未完成')
    st.rerun()


# Keep the credential in a non-widget state key when the settings page unmounts.
def remember_session_key():
    ss['session_key'] = ss.get('api_input','').strip()


key = ss.get('session_key','') or configured_key()
view = ss['view']
with st.sidebar:
    ui.text('PaperFit','brand')
    ui.text('文献研究工作台','brand-sub')
    with st.container(key='sidebar_nav'):
        st.button('首页', key='nav_home', type='primary' if view=='home' else 'tertiary', on_click=navigate,args=('home',),width='stretch')
        st.button('新建研究',key='nav_new',type='primary' if view=='setup' else 'tertiary',on_click=new_task,width='stretch')
        st.button('历史记录',key='nav_history',type='primary' if view in ('history','delete') else 'tertiary',on_click=navigate,args=('history',),width='stretch')
    with st.container(key='sidebar_footer'):
        ui.text('本机工作区','meta')
        ui.text('草稿与结果自动保存','meta')
        st.button('模型设置',key='nav_settings',type='primary' if view=='settings' else 'tertiary',on_click=navigate,args=('settings',),width='stretch')

if ss.pop('scroll_top',False):
    st.html("<script>document.querySelector('[data-testid=stMain]')?.scrollTo({top:0,behavior:'instant'});</script>",unsafe_allow_javascript=True)

if view=='home':
    ui.page_header('首页','从一个问题，找到值得先读的论文','面向生物医药研究与行业工作。让每一条阅读建议都有可回看的依据。')
    with ui.card('home_hero'):
        st.subheader('这次，你想研究什么？')
        ui.text('AI 对抗体药物研发有哪些帮助？采用了哪些方法和工具？','muted')
        with ui.actions():
            st.button('新建研究',key='home_new',type='primary',on_click=new_task)
            st.button('体验',key='home_demo',on_click=experience)
        ui.text('体验无需密钥，也不消耗 API 额度。','meta')
    for col,number,title,description in zip(st.columns(3),('01','02','03'),('定义问题','核查文献','形成清单'),('确认与你的任务相关的条件','检索、筛选并定位原文依据','决定先读什么，随时继续研究')):
        with col:
            ui.text(number,'meta');ui.text(title,'title');ui.text(description,'muted')
    st.subheader('继续最近的研究')
    show_tasks(limit=3)
    st.stop()

if view=='settings':
    ui.page_header('模型设置','连接你的模型','真实运行使用你自己的 API 额度。体验不需要配置。',saved=bool(configured_key()))
    with ui.card('model_settings'):
        ui.text('使用你自己的 DeepSeek API 密钥','title')
        ss.setdefault('api_input',ss.get('session_key',''))
        st.text_input('API 密钥',type='password',key='api_input',on_change=remember_session_key,
                      placeholder='已配置本机密钥，输入新密钥可替换' if configured_key() else '输入 DeepSeek API 密钥')
        ui.text('密钥只保存在本机配置中，不进入历史记录或导出报告。','muted')
        if st.button('保存到本机',type='primary',disabled=not ss.get('api_input','').strip()):
            value=ss['api_input'].strip()
            if any(c.isspace() for c in value):
                st.error('密钥不能包含空白字符。')
            else:
                try:
                    save_key(value)
                    st.success('已保存到本机。')
                except OSError:
                    st.error('本机配置无法写入，当前会话仍可使用输入的密钥。')
        ui.text('DeepSeek Flash · 低档思考。真实运行会将问题、条件和论文文字发送给 DeepSeek。','meta')
    st.stop()

if view=='delete':
    target=history.get_task(ss.get('delete_id',''))
    if not target:
        navigate('history');st.rerun()
    ui.page_header('删除确认','删除这项研究？','删除前再次确认，防止误操作。')
    with ui.card('delete'):
        ui.badges([('无法撤销','warning')])
        ui.text(target['question'] or '未命名任务','title')
        ui.text('将删除这个任务的全部结果版本与不再被其他任务使用的 PDF 副本。','muted')
        with ui.actions():
            st.button('取消，保留任务',type='primary',on_click=navigate,args=('history',))
            st.button('确认删除',on_click=delete_current)
    st.stop()

if view=='history':
    empty=not history.list_tasks()
    ui.page_header('历史记录','还没有保存的研究' if empty else '每一次研究，都可以接着做',
                   '从一个具体问题开始，PaperFit 会帮你整理有依据的阅读清单。' if empty else '草稿与结果保存在本机。修改条件、重新运行与重试都会保留旧版本。')
    show_tasks()
    ui.text('关闭窗口或刷新后，可从这里恢复。删除任务前会再次确认。','meta')
    st.stop()

if view=='setup':
    draft=ss['draft']
    ui.page_header('研究设置','把研究问题变成可核查的条件','条件可以随任务变化。确认后，PaperFit 才会开始检索和筛选。',saved=bool(ss.get('task_id')))
    if ss.get('file_warning'): st.warning(ss['file_warning'])
    with ui.card('question'):
        ss.setdefault('question_widget',draft['question'])
        st.text_input('研究问题',placeholder='AI 在抗体药物研发中有哪些应用？效果如何，使用了哪些方法和工具？',key='question_widget',on_change=save_draft,args=('question_widget','question'))
        with ui.actions():
            for source in ('自动找论文','上传 PDF'):
                st.button(source,key=f'source_{source}',type='primary' if draft['source']==source else 'secondary',on_click=choose_source,args=(source,))
            st.button('填入示例问题',type='tertiary',on_click=example)
        ui.text('自动检索最多初筛 30 条候选、核查 5 篇全文；上传支持 1–20 篇 PDF。','meta')
        if draft['source']=='上传 PDF':
            st.file_uploader('选择或替换 PDF',type='pdf',accept_multiple_files=True,key='upload_widget',on_change=remember_files)
            if ss['uploads']:
                with st.expander(f"已保留 {len(ss['uploads'])} 篇论文"):
                    for name,_ in ss['uploads']: st.text(name)
                    if st.button('清空已选文件'):
                        ss['uploads']=[];draft['files']=[];persist();ss.pop('upload_widget',None);st.rerun()
    question=draft['question'].strip()
    with ui.card('conditions'):
        with ui.actions():
            st.subheader('确认筛选条件')
            suggest=st.button('让 AI 建议',disabled=not(question and key))
        if suggest:
            try:
                with st.spinner('正在理解研究问题…'):
                    draft['conditions']=suggest_conditions(question,key)
                ss['editor_rev']+=1;ss['suggested_for']=question;persist()
            except Exception as error: st.error(friendly_error(error))
        ui.text('优先考虑用于排序；明确不符合必须条件的论文会单独标明。','muted')
        if ss.get('suggested_for') and ss['suggested_for']!=question:
            st.info('研究问题已修改，请重新核对下面的筛选条件。')
        with st.container(key='condition_headers'):
            for col,label in zip(st.columns([18,60,17,5]),('条件','要求','重要性','')):
                with col: ui.text(label,'meta')
        for i,row in enumerate(draft['conditions']):
            tone='required' if row.get('重要性')=='必须满足' else 'preferred'
            with st.container(key=f'condition_row_{tone}_{i}'):
                cols=st.columns([18,60,17,5],vertical_alignment='center')
                for col,field in zip(cols[:2],('条件','要求')):
                    widget=f"conditions_{ss['editor_rev']}_{i}_{field}"
                    ss.setdefault(widget,row.get(field,''))
                    col.text_input(f'第 {i+1} 项{field}',key=widget,label_visibility='collapsed',placeholder=field,on_change=edit_condition,args=(i,field,widget))
                widget=f"conditions_{ss['editor_rev']}_{i}_importance"
                ss.setdefault(widget,row.get('重要性','优先考虑'))
                cols[2].selectbox(f'第 {i+1} 项重要性',['优先考虑','必须满足'],key=widget,label_visibility='collapsed',on_change=edit_condition,args=(i,'重要性',widget))
                cols[3].button('×',key=f'del_condition_{i}',help=f'删除第 {i+1} 项条件',type='tertiary',on_click=remove_condition,args=(i,))
        st.button('＋ 添加条件',type='tertiary',on_click=add_condition,disabled=len(draft['conditions'])>=12)
    missing=[]
    try: criteria=validate(draft['conditions'])
    except ValueError as error: criteria={};missing.append(str(error))
    if not question: missing.append('填写研究问题')
    if not key: missing.append('到模型设置填写 DeepSeek 密钥')
    if draft['source']=='上传 PDF' and not 1<=len(ss['uploads'])<=MAX_PAPERS: missing.append('上传 1–20 篇 PDF')
    with ui.actions():
        start=st.button('确认条件并开始',type='primary',disabled=bool(missing))
        ui.text('草稿已保存 · 不确定的条件可先保留为偏好' if ss.get('task_id') else '编辑后移开焦点，草稿会自动保存。','meta')
        if ss.get('report') and not ss['report'].get('demo'):
            st.button('查看上次结果',type='tertiary',on_click=navigate,args=('results',))
    if missing: st.caption('还需要：'+'、'.join(missing))
    if not key: st.button('前往模型设置',on_click=navigate,args=('settings',))
    if start:
        persist()
        report={'question':question,'criteria':dict(criteria),'conditions':copy.deepcopy(draft['conditions']),
                'results':[],'demo':False,'searches':[],'candidates':[],'events':[],'source':draft['source'],
                'files':copy.deepcopy(draft['files']) if draft['source']=='上传 PDF' else []}
        checkpoint(report,'正在执行')
        ss['pending_run']=True
        navigate('running');st.rerun()
    st.stop()

report=ss.get('report')
if not report:
    navigate('home');st.rerun()

if view=='running' and ss.pop('pending_run',False):
    ui.page_header('运行中','正在核查论文','完成一篇就保存一篇。单篇失败不会阻断其他论文。',saved=True)
    with ui.card('run_progress'):
        ui.badges([('正在执行','positive')])
        progress_view=st.empty()
        count_view=st.empty()
        def progress(message):
            report['events'].append(message)
            checkpoint(report,'正在执行')
            with progress_view.container(): ui.text(message,'title')
        def receive(result,searches,candidates):
            report['results'].append(apply_policy(result,report['conditions']))
            report.update(searches=searches,candidates=candidates)
            checkpoint(report,'正在执行')
            count_view.caption(f"已保存 {len(report['results'])} 篇结果")
        try:
            if report['source']=='自动找论文':
                _,results,searches,candidates=find_papers(report['question'],key,progress,criteria=report['criteria'],on_result=receive)
                report.update(results=[apply_policy(r,report['conditions']) for r in results],searches=searches,candidates=candidates)
            else:
                for index,paper in enumerate(ss['uploads'],1):
                    progress(f"正在处理 {index} / {len(ss['uploads'])} · {paper[0]}")
                    result=next(screen_batch(report['question'],report['criteria'],[paper],key))
                    result['source_kind']='上传的 PDF';receive(result,[],[])
            progress(f"处理结束，已整理 {len(report['results'])} 篇论文")
            checkpoint(report,'部分失败' if any(r.get('error') for r in report['results']) else '已完成')
        except Exception as error:
            report['events'].append(friendly_error(error));checkpoint(report,'未完成')
    ss.pop('result_filter',None);navigate('results');st.rerun()

if view in ('running','process'):
    ui.page_header('执行记录','本次研究的执行过程','回看已保存的检索、核查与处理记录。',saved=not report['demo'])
    st.button('返回阅读清单',type='tertiary',on_click=navigate,args=('results',))
    with ui.card('process'):
        ui.badges([(report.get('status','已保存'),'neutral')])
        render_process(report)
    st.stop()

if view=='evidence':
    index=ss.get('paper_index',0)
    result=report['results'][index]
    failed=bool(result.get('error'))
    ui.page_header('部分失败' if failed else '证据核查','部分论文需要再处理' if failed else '把判断与原文放在一起看',
        '已完成的结果已经保存。可以只重试失败的论文。' if failed else '每项条件都能回到对应的原文位置，避免只凭摘要下结论。',saved=not report['demo'])
    st.button('返回阅读清单',type='tertiary',on_click=navigate,args=('results',))
    st.subheader(result.get('title',result['name']))
    with ui.actions():
        ui.badges([(result['priority'],'positive' if result['priority']=='优先读' else 'warning' if failed else 'neutral'),(result.get('eligibility','待核查'),'neutral')])
        if result.get('url'): st.link_button('打开原文',result['url'])
        if not report['demo'] and (failed or result['priority']=='待人工核查'):
            if st.button('重试这篇',type='primary',disabled=not key): retry_paper(index,key)
    if failed:
        with ui.card('failed_paper'):
            ui.badges([('处理失败','warning')]);ui.text(result['error'])
            ui.text('扫描版 PDF 可先进行文字识别，再上传带文字层的文件。其他论文结果会保留。','muted')
            st.button('重新上传',type='primary',on_click=navigate,args=('setup',))
    if result.get('source_note'): ui.text(result['source_note'],'muted')
    if result.get('abstract') and not result.get('findings'):
        with ui.card('abstract'):
            ui.badges([('仅摘要','warning')]);ui.text(result['abstract'])
    for i,finding in enumerate(result.get('findings',[])):
        with ui.card(f'evidence_{i}'):
            ui.text(f"{finding['criterion']} · {finding['status']}",'title')
            ui.text(finding['reason'],'muted')
            if finding['verified']: ui.quote(evidence_location(finding),finding['quote'])
            else: ui.text('缺少可定位的原文依据，需要人工核查。','meta')
    if result.get('short_pages'): st.caption('部分页面文字较少，请按需核对：'+'、'.join(map(str,result['short_pages'])))
    if result.get('repair_attempted'): st.caption('已尝试修正引文一次'+('，修正请求未完成' if result.get('repair_failed') else ''))
    st.stop()

ui.page_header('阅读清单','你的阅读清单','体验 · 真实论文的历史筛选结果；不发起新的模型请求。' if report['demo'] else '按照确认后的条件，查看阅读建议与原文依据。',saved=not report['demo'])
ui.text(report['question'],'question')
with ui.actions():
    st.button('修改条件',on_click=edit_report)
    st.download_button('导出阅读清单',markdown_report(report['question'],report['criteria'],report['results'],demo=report['demo'],searches=report['searches'],conditions=report['conditions'],status=report.get('status')),
                       file_name='PaperFit-阅读清单.md',mime='text/markdown',type='primary')
    st.button('查看执行过程',type='tertiary',on_click=navigate,args=('process',))
if not report['demo']:
    runs=history.list_runs(ss['task_id'])
    number=next((len(runs)-i for i,r in enumerate(runs) if r[0]==report.get('run_id')),'—')
    ui.text(f"版本 {number} · {report.get('status','已保存')}",'meta')
    if report.get('status') in ('未完成','部分失败','正在执行'):
        st.warning('这次任务未全部完成。已有结果已保留；可重试单篇或修改条件重新运行，原版本会保留。')
results=report['results']
ui.stats(results,PRIORITIES)
ss.setdefault('result_filter','全部')
with ui.actions(key='result_filters'):
    for label in ('全部',*PRIORITIES):
        count=len(results) if label=='全部' else sum(r['priority']==label for r in results)
        if st.button(f'{label} {count}',key=f'filter_{label}',type='primary' if ss['result_filter']==label else 'tertiary'):
            ss['result_filter']=label;st.rerun()
selected=ss['result_filter']
visible=sorted(((i,r) for i,r in enumerate(results) if selected=='全部' or r['priority']==selected),key=lambda pair:PRIORITIES.index(pair[1]['priority']))
if not visible:
    with ui.card('no_results'):
        ui.text('这个分组暂时没有论文。' if results else '本次没有进入全文核查的论文。','title')
        ui.text('可以查看检索过程，或修改条件再次搜索。','muted')
        st.button('修改研究条件',on_click=edit_report)
for index,result in visible:
    with ui.card(f'paper_{index}'):
        meta=result.get('source_kind') or ('读取未完成' if result.get('error') else 'PDF 全文')
        if result.get('year'): meta+=f" · {result['year']}"
        if result.get('is_preprint'): meta+=' · 预印本'
        ui.badges([(result['priority'],'positive' if result['priority']=='优先读' else 'warning' if result['priority']=='待人工核查' else 'neutral'),(result.get('evidence_status','证据待核对'),'neutral')],note=meta)
        ui.text(result.get('title',result['name']),'title')
        ui.text(explanation(result),'muted')
        if result.get('failed_conditions'): st.warning('不符合必须条件：'+'、'.join(result['failed_conditions']))
        with ui.actions():
            st.button('查看依据',key=f'evidence_{index}',on_click=open_evidence,args=(index,))
            if result.get('url'): st.link_button('打开原文',result['url'])
            if not report['demo'] and (result.get('error') or result['priority']=='待人工核查'):
                if st.button('重试这篇',key=f'retry_{index}',type='tertiary',disabled=not key): retry_paper(index,key)
ui.text('引文已定位只表示在原文找到这段文字，仍需结合研究设计判断证据价值。','meta')
with st.expander('本次筛选条件'): render_conditions(report['conditions'])
