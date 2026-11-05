"""Read a DeepSeek key from the terminal and save it to the ignored local config."""

import shutil
import tempfile
import warnings
from getpass import GetPassWarning, getpass
from pathlib import Path

from dotenv import set_key

from criteria import KEY_FILE, KEY_NAME


def save_key(key, destination=KEY_FILE):
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
        temp = Path(handle.name)
    try:
        if destination.exists():
            shutil.copyfile(destination, temp)
        set_key(temp, KEY_NAME, key)
        temp.chmod(0o600)
        temp.replace(destination)
    finally:
        temp.unlink(missing_ok=True)


def main():
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", GetPassWarning)
            key = getpass("请输入 DeepSeek API 密钥（输入不会显示）：").strip()
    except (GetPassWarning, EOFError, KeyboardInterrupt):
        print("\n未保存密钥。请在终端中重新运行。")
        return 1
    if not key or any(character.isspace() for character in key):
        print("密钥为空或包含空白，未保存。")
        return 1
    save_key(key)
    print(f"DeepSeek 密钥已保存到 {KEY_FILE}。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
