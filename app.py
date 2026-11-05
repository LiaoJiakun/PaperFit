import streamlit as st

from criteria import FIELDS, configured_key, suggest_criteria
from demo import CRITERIA, QUESTION, load_demo_results
from literature_search import find_papers, source_label
from paperfit import PRIORITIES, evidence_location, markdown_report, screen_batch
from screen_paper import active_criteria


st.set_page_config(page_title="PaperFit", page_icon="📄", layout="wide")
MAX_PAPERS = 20


def reset_screening():
    for key in ("report", "show_demo", "question", "papers", "manual_key",
                "discovery", "search_question", "search_key"):
        st.session_state.pop(key, None)
    for field in FIELDS.values():
        st.session_state.pop(f"criterion_{field}", None)
    st.session_state["mode"] = "离线演示"


st.markdown("##### PAPERFIT  /  文献筛选")
st.title("决定先读哪篇论文")
st.write("确认研究问题和筛选标准，再按阅读优先级查看每篇论文的判断与页码依据。")
mode = st.radio("运行方式", ["离线演示", "我的论文", "帮我找论文"], horizontal=True, key="mode")
demo = mode == "离线演示"
searches = []


def api_key(widget_key):
    key = configured_key()
    if key:
        st.caption("已读取本地 DeepSeek API 密钥。")
        return key
    return st.text_input("DeepSeek API 密钥", type="password", key=widget_key).strip()


def run(question, criteria, papers, key):
    progress = st.progress(0, text="正在准备筛选")
    results = []
    for result in screen_batch(question, criteria, papers, key):
        results.append(result)
        progress.progress(
            len(results) / len(papers),
            text=f"已处理 {len(results)} / {len(papers)} 篇 · {result['name']}",
        )
    st.session_state["report"] = (question, criteria, results)


if demo:
    st.info("离线演示使用三篇公开论文的 DeepSeek 实测结果。")
    if st.button("查看三篇论文演示", type="primary"):
        st.session_state["show_demo"] = True
    report = (QUESTION, CRITERIA, load_demo_results()) if st.session_state.get("show_demo") else None
elif mode == "帮我找论文":
    st.subheader("从研究问题找论文")
    question = st.text_area("研究问题", placeholder=QUESTION, key="search_question").strip()
    key = api_key("search_key")
    st.caption("搜索 Europe PMC，涵盖预印本等记录。初筛最多 30 条候选，为最多 5 篇尝试获取全文。"
               "研究问题和候选文献文字将发送给 DeepSeek。")
    if st.button("搜索并筛选", type="primary", disabled=not (question and key)):
        st.session_state.pop("discovery", None)
        status = st.empty()
        try:
            criteria, results, searches, candidates = find_papers(question, key, status.info)
        except ValueError as error:
            status.error(str(error))
        except Exception:
            status.error("搜索未完成。请检查网络、Europe PMC 和 DeepSeek 服务后重试。")
        else:
            status.empty()
            st.session_state["discovery"] = (question, criteria, results, searches, candidates)
    discovery = st.session_state.get("discovery")
    report = None
    if discovery:
        search_question, criteria, results, searches, candidates = discovery
        report = (search_question, criteria, results)
        with st.expander(f"检索记录 · {len(searches)} 次搜索 · {len(candidates)} 条去重候选"):
            for entry in searches:
                hits = "请求失败" if entry["hits"] is None else f"数据库命中 {entry['hits']} 条"
                st.text(hits)
                st.code(entry["query"], language=None, wrap_lines=True)
        with st.expander("查看全部候选及摘要初筛理由"):
            labels = {"direct": "直接匹配", "background": "背景相关", "unclear": "待核查", "low": "低相关"}
            for item in candidates:
                st.text(f"{labels[item['rank']]} · {item['title']}")
                if source_label(item):
                    st.caption(source_label(item))
                st.text(item["triage_reason"])
                st.link_button("查看论文记录", item["url"])
        if not results:
            st.info("本次没有进入全文筛选的候选。可查看检索记录或调整研究问题。")
else:
    st.subheader("1. 研究问题和论文")
    question = st.text_area("研究问题", placeholder=QUESTION, key="question").strip()
    files = st.file_uploader(
        f"上传 1–{MAX_PAPERS} 篇 PDF", type="pdf", accept_multiple_files=True,
        help=f"每次最多处理 {MAX_PAPERS} 篇论文。",
        key="papers",
    )
    key = api_key("manual_key")
    st.caption("点击生成建议会将研究问题发送给 DeepSeek。开始筛选会发送 PDF 中提取的文字。")
    if st.button("生成筛选标准建议", disabled=not (question and key)):
        try:
            with st.spinner("正在提取筛选标准"):
                suggested = suggest_criteria(question, key)
        except Exception:
            st.error("生成建议失败。请检查 DeepSeek 密钥、余额和网络，或直接填写标准。")
        else:
            for label, field in FIELDS.items():
                value = suggested.get(field)
                st.session_state[f"criterion_{field}"] = value if isinstance(value, str) else ""

    st.subheader("2. 确认筛选标准")
    st.caption("留空表示未限定。你也可以直接填写，无需先生成建议。")
    criteria = {}
    columns = st.columns(2)
    for index, (label, field) in enumerate(FIELDS.items()):
        with columns[index % 2]:
            criteria[label] = st.text_input(label, key=f"criterion_{field}").strip()
    if len(files) > MAX_PAPERS:
        st.warning(f"已选 {len(files)} 篇，每批最多处理 {MAX_PAPERS} 篇。请移除多余文件。")
    if st.button(
        "开始筛选", type="primary",
        disabled=not (question and key and 1 <= len(files) <= MAX_PAPERS and active_criteria(criteria)),
    ):
        run(question, criteria, [(file.name, file.getvalue()) for file in files], key)
    report = st.session_state.get("report")


if report:
    report_question, report_criteria, results = report
    st.divider()
    st.subheader("阅读清单")
    st.text(report_question)
    st.caption("本次使用的标准 · " + " / ".join(
        f"{label}：{value}" for label, value in active_criteria(report_criteria).items()
    ))
    columns = st.columns(len(PRIORITIES))
    for column, priority in zip(columns, PRIORITIES):
        column.metric(priority, sum(result["priority"] == priority for result in results))
    st.caption("引文核对检查文字是否出现在所报页码或章节。请复核引文是否支持判断。")
    for priority in PRIORITIES:
        for result in results:
            if result["priority"] != priority:
                continue
            title = result.get("title", result["name"])
            with st.expander(f"{priority} · {title}", expanded=not demo and priority == "优先读"):
                if source_label(result):
                    st.caption(source_label(result))
                if result.get("url"):
                    st.link_button("查看论文原文", result["url"])
                if result.get("source_kind"):
                    st.caption(result["source_kind"])
                if result.get("source_note"):
                    st.info(result["source_note"])
                    st.text(result["triage_reason"])
                    if result.get("abstract"):
                        st.write(result["abstract"])
                if result.get("error"):
                    st.warning(result["error"])
                if result["short_pages"]:
                    st.caption("文字较少的 PDF 页 · " + "、".join(map(str, result["short_pages"])))
                if result.get("repair_attempted"):
                    note = "引文修正请求失败" if result.get("repair_failed") else "已尝试修正引文一次"
                    st.caption(note)
                for finding in result["findings"]:
                    st.text(f"{finding['criterion']} · {finding['status']}")
                    st.text(finding["reason"])
                    if finding["verified"]:
                        st.text(f"{evidence_location(finding)} · {finding['quote']}")
    st.download_button(
        "下载 Markdown 报告",
        markdown_report(report_question, report_criteria, results, demo=demo, searches=searches),
        file_name="paperfit-report.md",
        mime="text/markdown",
    )
    st.button("返回起始页", on_click=reset_screening)
