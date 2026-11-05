import sys
from pathlib import Path

import pymupdf


def read_pdf_pages(file_path):
    """提取 PDF 每一页的文字，返回页码和文字的列表。"""
    pages = []

    source = {"stream": file_path, "filetype": "pdf"} if isinstance(file_path, bytes) else {"filename": file_path}
    with pymupdf.open(**source) as document:
        if not document.is_pdf or document.needs_pass:
            raise ValueError("文件不是可读取的 PDF，或需要密码。")
        for index, page in enumerate(document):
            pages.append({
                "page": index + 1,
                "text": page.get_text().strip(),
            })

    return pages


def main():
    if len(sys.argv) != 2:
        print("用法：python read_pdf.py 论文路径.pdf")
        return

    file_path = Path(sys.argv[1])

    if not file_path.is_file():
        print(f"找不到文件：{file_path}")
        return

    try:
        pages = read_pdf_pages(file_path)
    except Exception as error:
        print(f"无法读取 PDF：{error}")
        return

    print(f"共读取 {len(pages)} 页。\n")

    for page in pages:
        print(f"========== 第 {page['page']} 页 ==========")
        if page["text"]:
            # 先显示每页前 500 个字符，方便检查
            print(page["text"][:500])
        else:
            print("本页没有提取到文字。")
        print()


if __name__ == "__main__":
    main()
