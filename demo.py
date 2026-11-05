"""Saved results from screening three publisher PDFs with DeepSeek."""

import json
from pathlib import Path


QUESTION = "个性化 mRNA 疫苗能否在胰腺癌患者中诱导 T 细胞免疫反应？"
CRITERIA = {
    "研究对象": "胰腺癌患者",
    "干预方式": "个性化 mRNA 疫苗",
    "关注结果": "T 细胞免疫反应",
    "研究类型": "",
}


def load_demo_results():
    path = Path(__file__).with_name("demo_results.json")
    return json.loads(path.read_text(encoding="utf-8"))
