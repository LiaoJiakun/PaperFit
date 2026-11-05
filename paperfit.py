from criteria import request_json
from read_pdf import read_pdf_pages
from screen_paper import screen_paper


PRIORITIES = ("优先读", "背景参考", "低相关", "待人工核查")
MAX_TEXT_CHARS = 500_000


def screen_batch(question, criteria, papers, key, *, request=request_json):
    """按上传顺序处理，单篇失败时继续处理其余论文。"""
    for name, pdf in papers:
        result = {"name": name, "priority": "待人工核查", "short_pages": [], "findings": []}
        try:
            pages = read_pdf_pages(pdf)
        except Exception:
            yield {**result, "error": "无法打开 PDF。请检查文件格式、密码和完整性。"}
            continue

        result["short_pages"] = [page["page"] for page in pages if len(page["text"]) < 50]
        text_size = sum(len(page["text"]) for page in pages)
        if not text_size:
            yield {**result, "error": "未提取到可用文字。请提供带文字层的 PDF。"}
            continue
        if text_size > MAX_TEXT_CHARS:
            yield {**result, "error": "提取的文字超过本版本上限。请拆分 PDF 后重试。"}
            continue

        try:
            assessment = screen_paper(question, criteria, pages, key, request=request)
        except Exception:
            yield {**result, "error": "筛选请求失败。请检查 DeepSeek 密钥、余额和网络后重试。"}
        else:
            yield {**result, **assessment}


def evidence_location(finding):
    return finding.get("location") or f"PDF 第 {finding['page']} 页"


def markdown_report(question, criteria, results, *, demo=False, searches=()):
    lines = ["# PaperFit 文献筛选报告", "", f"研究问题：{question}", ""]
    if demo:
        lines += ["**离线演示 · 三篇公开论文的 DeepSeek 实测结果**", ""]
    lines += ["## 筛选标准", ""]
    lines += [f"- {label}：{value or '未限定'}" for label, value in criteria.items()]
    lines += ["", "引文核对检查文字和页码或章节。请复核引文是否支持判断。"]
    if searches:
        lines += ["", "## Europe PMC 检索记录", ""]
        for entry in searches:
            hits = "请求失败" if entry["hits"] is None else f"数据库命中 {entry['hits']} 条"
            lines.append(f"- {hits}：`{entry['query']}`")
    for priority in PRIORITIES:
        group = [result for result in results if result["priority"] == priority]
        if not group:
            continue
        lines += ["", f"## {priority}（{len(group)} 篇）"]
        for result in group:
            title = result.get("title", result["name"])
            lines += ["", f"### {title}", ""]
            if result.get("url"):
                lines += [f"[论文原文]({result['url']})", ""]
            if result.get("source_kind"):
                lines += [f"证据来源：{result['source_kind']}", ""]
            if result.get("is_preprint"):
                lines += ["文献类型：预印本", ""]
            if result.get("source_note"):
                lines += [result["source_note"], result["triage_reason"], ""]
            if result.get("error"):
                lines += [f"处理失败：{result['error']}", ""]
            if result["short_pages"]:
                pages = "、".join(map(str, result["short_pages"]))
                lines += [f"文字较少的 PDF 页：{pages}", ""]
            if result.get("repair_attempted"):
                status = "请求失败" if result.get("repair_failed") else "已执行"
                lines += [f"引文修正：{status}", ""]
            for finding in result["findings"]:
                lines.append(f"- **{finding['criterion']} · {finding['status']}** — {finding['reason']}")
                if finding["verified"]:
                    quote = " ".join(finding["quote"].split())
                    lines.append(f"  - {evidence_location(finding)}：{quote}")
    return "\n".join(lines) + "\n"
