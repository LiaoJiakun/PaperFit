import json
from getpass import getpass

from openai import OpenAI


MODEL = "deepseek-flash"
BASE_URL = "https://api.deepseek.com"


def suggest_criteria(question, key):
    client = OpenAI(
        base_url=BASE_URL,
        api_key=key,
        timeout=180,
    )

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "你是生物医学文献筛选助手。"
                    "根据用户的研究问题提取筛选标准。"
                    "只输出一个 JSON 对象，不要输出其他内容。"
                    "对象必须有四个字符串字段："
                    "population、intervention、outcome、study_type。"
                    "用简洁中文填写。用户没有指定的条件填空字符串。"
                ),
            },
            {"role": "user", "content": question},
        ],
        reasoning_effort="low",
        extra_body={"thinking": {"type": "enabled"}},
        response_format={"type": "json_object"},
    )

    content = response.choices[0].message.content
    if not content:
        raise ValueError("模型没有返回文本。")

    content = content.strip()

    # 兼容模型将结果放进 Markdown 代码块的情况
    if content.startswith("```"):
        content = "\n".join(content.splitlines()[1:])
        if content.rstrip().endswith("```"):
            content = content.rstrip()[:-3].strip()

    result = json.loads(content)
    if not isinstance(result, dict):
        raise ValueError("模型返回的内容不是 JSON 对象。")

    return result


def edit_field(label, suggested):
    hint = suggested if suggested else "未指定"
    value = input(f"{label}（建议：{hint}）：").strip()
    return value if value else suggested


def main():
    question = input("请输入你的研究问题：").strip()
    if not question:
        print("研究问题不能为空。")
        return

    key = getpass("请输入 DeepSeek API 密钥：")
    if not key:
        print("密钥不能为空。")
        return

    print("\n正在使用 DeepSeek分析，请稍候……")

    try:
        suggested = suggest_criteria(question, key)
    except Exception as error:
        print(f"\n生成筛选标准失败：{error}")
        return

    print("\n请检查并逐项修改。直接按回车可保留建议。\n")

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

    print("\n========== 最终筛选标准 ==========")
    print(f"研究问题：{question}")
    for label, value in criteria.items():
        print(f"{label}：{value if value else '不限'}")


if __name__ == "__main__":
    main()
