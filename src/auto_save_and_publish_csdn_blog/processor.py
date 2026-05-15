import os
import re
import time
from .models import Blog


def extract_number(filename: str) -> int:
    """从文件名如 '1. 两数之和.md' 中提取题号"""
    match = re.match(r"(\d+)", filename)
    return int(match.group(1)) if match else 9999


class MarkdownProcessor:
    def __init__(self, folder: str, log_file: str):
        self.folder = folder
        self.log_file = log_file
        self.processed: set[str] = set()

    def _load_processed(self):
        if not os.path.exists(self.log_file):
            return
        with open(self.log_file, "r", encoding="utf-8") as f:
            self.processed = {line.strip() for line in f if line.strip()}

    def get_pending_files(self) -> list[str]:
        if not os.path.exists(self.folder):
            print(f"错误: 文件夹 '{self.folder}' 不存在")
            return []

        files = [f for f in os.listdir(self.folder) if f.endswith(".md")]
        files.sort(key=extract_number)

        if not files:
            print("没有找到 .md 文件")
            return []

        self._load_processed()
        print(f"已处理文件数: {len(self.processed)}")

        pending = [f for f in files if f not in self.processed]
        print(f"待处理文件数: {len(pending)}")
        return pending

    def read_file(self, filename: str) -> str:
        filepath = os.path.join(self.folder, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()

    def mark_processed(self, filename: str):
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(filename + "\n")
        self.processed.add(filename)
