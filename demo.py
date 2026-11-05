"""无需 API 密钥的合成演示，用固定响应驱动真实的解析、校验和排序。"""

import json

import pymupdf


QUESTION = "个性化 mRNA 疫苗能否在胰腺癌患者中诱导 T 细胞免疫反应？"
CRITERIA = {
    "研究对象": "胰腺癌患者",
    "干预方式": "个性化 mRNA 疫苗",
    "关注结果": "T 细胞免疫反应",
    "研究类型": "",
}
SAMPLES = {
    "A": (
        "Participants had pancreatic cancer.",
        "Each participant received a personalized mRNA vaccine.",
        "The study observed vaccine-specific T cell responses.",
    ),
    "B": (
        "Participants had melanoma and no pancreatic cancer cohort was enrolled.",
        "Each participant received a personalized mRNA vaccine.",
        "The study observed vaccine-specific T cell responses.",
    ),
    "C": (
        "Participants had pancreatic cancer.",
        "Each participant received a personalized mRNA vaccine.",
        "The study measured manufacturing time as its only endpoint.",
    ),
}


def demo_papers():
    for letter, sentences in SAMPLES.items():
        with pymupdf.open() as doc:
            page = doc.new_page()
            page.insert_text((72, 72), f"PaperFit synthetic sample {letter}\n" + "\n".join(sentences))
            yield f"样例 {letter}.pdf", doc.tobytes()
    yield "样例 D（损坏文件）.pdf", b"invalid PDF"


def demo_response(system, prompt, key):
    letter = next(letter for letter in SAMPLES if f"synthetic sample {letter}" in prompt)
    standard = json.loads(prompt.split("筛选标准：", 1)[1].split("\n\n", 1)[0])
    findings = []
    for index, label in enumerate(tuple(CRITERIA)[:3]):
        if label not in standard:
            continue
        status = "不匹配" if (letter, index) == ("B", 0) else "匹配"
        quote = SAMPLES[letter][index]
        page = 1
        if (letter, index) == ("A", 2) and "前次引文核对未通过" not in prompt:
            page = 2
        if (letter, index) == ("C", 2):
            quote, page = "This fabricated sentence cannot be found.", 1
        findings.append({
            "criterion": label, "status": status,
            "reason": f"合成样例中的{label}判断。", "page": page, "quote": quote,
        })
    return {"findings": findings}
