import streamlit as st

from criteria import FIELDS, configured_key, suggest_criteria
from demo import CRITERIA, QUESTION, demo_papers, demo_response
from paperfit import PRIORITIES, markdown_report, screen_batch
from screen_paper import active_criteria


st.set_page_config(page_title="PaperFit", page_icon="📄", layout="wide")

st.markdown("##### PAPERFIT  /  文献筛选")
st.title("决定先读哪篇论文")
st.write("确认研究问题和筛选标准，再按阅读优先级查看每篇论文的判断与页码依据。")
mode = st.radio("运行方式", ["离线演示", "我的论文"], horizontal=True)
demo = mode == "离线演示"


def run(question, criteria, papers, key, **options):
    progress = st.progress(0, text="正在准备筛选")
    results = []
    for result in screen_batch(question, criteria, papers, key, **options):
        results.append(result)
        progress.progress(
            len(results) / len(papers),
            text=f"已处理 {len(results)} / {len(papers)} 篇 · {result['name']}",
        )
    st.session_state["report"] = (demo, question, criteria, results)


if demo:
    st.info("使用四个合成样例演示正常筛选、引文修正和文件失败。")
    st.write(QUESTION)
    if st.button("运行离线演示", type="primary"):
        run(QUESTION, CRITERIA, list(demo_papers()), "", request=demo_response)
else:
    st.subheader("1. 研究问题和论文")
    question = st.text_area("研究问题", placeholder=QUESTION).strip()
    files = st.file_uploader(
        "上传 1–5 篇 PDF", type="pdf", accept_multiple_files=True,
        help="建议用 3–5 篇论文做一次比较。",
    )
    key = configured_key()
    if key:
        st.caption("已读取本地 DeepSeek API 密钥。")
    else:
        key = st.text_input("DeepSeek API 密钥", type="password").strip()
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
    if len(files) > 5:
        st.warning("每批最多处理 5 篇。请移除多余文件。")
    if st.button(
        "开始筛选", type="primary",
        disabled=not (question and key and 1 <= len(files) <= 5 and active_criteria(criteria)),
    ):
        run(question, criteria, [(file.name, file.getvalue()) for file in files], key)


report = st.session_state.get("report")
if report and report[0] == demo:
    _, report_question, report_criteria, results = report
    st.divider()
    st.subheader("阅读清单")
    st.text(report_question)
    st.caption("本次使用的标准 · " + " / ".join(
        f"{label}：{value}" for label, value in active_criteria(report_criteria).items()
    ))
    columns = st.columns(len(PRIORITIES))
    for column, priority in zip(columns, PRIORITIES):
        column.metric(priority, sum(result["priority"] == priority for result in results))
    st.caption("引文核对检查文字是否出现在所报页码。请复核引文是否支持判断。")
    for priority in PRIORITIES:
        for result in results:
            if result["priority"] != priority:
                continue
            with st.expander(f"{priority} · {result['name']}", expanded=priority == "优先读"):
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
                        st.text(f"PDF 第 {finding['page']} 页 · {finding['quote']}")
    st.download_button(
        "下载 Markdown 报告",
        markdown_report(report_question, report_criteria, results, demo=demo),
        file_name="paperfit-report.md",
        mime="text/markdown",
    )
