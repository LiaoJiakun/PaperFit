import json
import sys
from getpass import getpass

from openai import OpenAI

from criteria import BASE_URL, MODEL, suggest_criteria, edit_field
from read_pdf import read_pdf_pages


def screen_paper(question, criteria, pages, key):
    client = OpenAI(
        base_url=BASE_URL,
        api_key=key,
        timeout=300,
    )

    # 把每一页单独标记，方便模型标明证据所在的 PDF 页码
    document = "\n\n".join(
        f"【PDF 第 {page['page']} 页】\n{page['text']}"
        for page in pages
        if page["text"]
    )

    prompt = (
        "请根据用户确认的筛选标准，判断论文是否相关。\n"
        "只使用提供的论文文字，不要凭知识补充。\n"
        "如果无法判断，标记为“证据不足”。\n"
        "请只返回 JSON 对象，格式如下：\n"
        '{"summary":"简要判断",'
        '"findings":[{"criterion":"筛选维度",'
        '"status":"匹配、部分匹配、不匹配或证据不足",'
        '"reason":"判断理由",'
        '"page":1,'
        '"quote":"该页的一段简短英文原文"}]}\n'
        "没有原文依据时，page 填 0，quote 填空字符串。"
        "page 必须是 PDF 页码，不是期刊印刷页码。\n\n"
        f"研究问题：{question}\n"
        f"筛选标准：{json.dumps(criteria, ensure_ascii=False)}\n\n"
        f"论文文字：\n{document}"
    )

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "你是严谨的文献筛选助手。"},
            {"role": "user", "content": prompt},
        ],
        reasoning_effort="low",
        extra_body={"thinking": {"type": "enabled"}},
        response_format={"type": "json_object"},
    )

    content = response.choices[0].message.content
    if not content:
        raise ValueError("模型没有返回文本。")

    content = content.strip()
    if content.startswith("```"):
        content = "\n".join(content.splitlines()[1:])
        if content.rstrip().endswith("```"):
            content = content.rstrip()[:-3].strip()

    return json.loads(content)


def main():
    if len(sys.argv) != 2:
        print('用法：python screen_paper.py "论文路径.pdf"')
        return

    question = input("请输入研究问题：").strip()
    if not question:
        print("研究问题不能为空。")
        return

    key = getpass("请输入 DeepSeek API 密钥：")
    if not key:
        print("密钥不能为空。")
        return

    try:
        print("\n正在提取筛选标准……")
        suggested = suggest_criteria(question, key)

        print("\n请确认或修改标准；直接回车保留建议。\n")
        fields = [
            ("研究对象", "population"),
            ("干预方式", "intervention"),
            ("关注结果", "outcome"),
            ("研究类型", "study_type"),
        ]
        criteria = {}
        for label, field in fields:
            value = suggested.get(field, "")
            if not isinstance(value, str):
                value = ""
            criteria[label] = edit_field(label, value)

        print("\n正在读取论文……")
        pages = read_pdf_pages(sys.argv[1])

        if not pages or not any(page["text"] for page in pages):
            print("无法从这篇论文中提取文字。")
            return

        short_pages = [
            page["page"] for page in pages
            if len(page["text"]) < 50
        ]

        if short_pages:
            print(
                "提醒：这些 PDF 页面提取的文字较少，"
                f"请人工检查：{short_pages}"
            )

        print("\n正在筛选论文，DeepSeek 可能需要一些时间……")
        result = screen_paper(question, criteria, pages, key)

        print("\n========== 筛选结果 ==========")
        print(result.get("summary", "未提供总结"))

        for finding in result.get("findings", []):
            print(f"\n{finding.get('criterion', '筛选维度')}")
            print(f"判断：{finding.get('status', '未提供')}")
            print(f"理由：{finding.get('reason', '未提供')}")

            page_number = finding.get("page", 0)
            quote = finding.get("quote", "")

            if page_number and quote:
                print(f"模型给出的依据：PDF 第 {page_number} 页")
                print(f"原文：{quote}")
                print("请在原 PDF 中核对这段原文和页码。")
            else:
                print("未提供可核对的原文依据。")

    except Exception as error:
        print(f"\n处理失败：{error}")


if __name__ == "__main__":
    main()
