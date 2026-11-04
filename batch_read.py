import sys
from pathlib import Path

from read_pdf import read_pdf_pages


def inspect_pdf(file_path):
    """读取一篇 PDF，并找出提取文字较少的页面。"""
    path = Path(file_path)

    if not path.is_file():
        return {
            "name": path.name,
            "status": "失败",
            "reason": "文件不存在",
        }

    try:
        pages = read_pdf_pages(path)
    except Exception as error:
        return {
            "name": path.name,
            "status": "失败",
            "reason": str(error),
        }

    if not pages:
        return {
            "name": path.name,
            "status": "失败",
            "reason": "PDF 没有页面",
        }

    # 少于 50 个字符的页面可能没有被完整读取。
    # 这只是一个提醒，不代表其他页面一定提取完整。
    short_pages = [
        page["page"]
        for page in pages
        if len(page["text"]) < 50
    ]

    return {
        "name": path.name,
        "status": "已读取",
        "total_pages": len(pages),
        "short_pages": short_pages,
    }


def main():
    file_paths = sys.argv[1:]

    if not file_paths:
        print('用法：python batch_read.py "论文1.pdf" "论文2.pdf"')
        return

    for file_path in file_paths:
        result = inspect_pdf(file_path)

        print(f"\n论文：{result['name']}")
        print(f"状态：{result['status']}")

        if result["status"] == "失败":
            print(f"原因：{result['reason']}")
            continue

        print(f"总页数：{result['total_pages']}")

        if result["short_pages"]:
            page_numbers = "、".join(
                str(page) for page in result["short_pages"]
            )
            print(f"以下页面提取文字较少，请核对：{page_numbers}")
        else:
            print("没有发现文字少于 50 个字符的页面。")


if __name__ == "__main__":
    main()
