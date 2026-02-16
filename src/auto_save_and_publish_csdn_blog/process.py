import os
import re
import time
from _ctypes_test import func
import csdn_blog_auto_save_and_publish


def extract_number(filename: str) -> int:
    """从文件名如 '1. 两数之和.md' 中提取题号"""
    match = re.match(r"(\d+)", filename)
    return int(match.group(1)) if match else 9999

def get_all_md_files(folder: str):
    """获取所有 .md 文件，并按题号排序"""
    files = [f for f in os.listdir(folder) if f.endswith('.md')]
    files.sort(key=extract_number)
    return files

def load_processed_files(log_file: str):
    """从日志文件加载已处理的文件列表（去重、保持顺序）"""
    if not os.path.exists(log_file):
        return set()
    with open(log_file, 'r', encoding='utf-8') as f:
        return {line.strip() for line in f if line.strip()}

def mark_as_processed(log_file: str, filename: str):
    """将文件名追加到已处理日志"""
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(filename + '\n')

def batch_process_files(fold_dir: str, filelog: str, nums: int, csdn_blog: csdn_blog_auto_save_and_publish.Blog, process_file: func):
    # 确保文件夹存在
    if not os.path.exists(fold_dir):
        print(f"错误: 文件夹 '{fold_dir}' 不存在")
        return

    # 获取所有待处理文件（按题号排序）
    all_files = get_all_md_files(fold_dir)
    if not all_files:
        print("没有找到 .md 文件")
        return

    # 加载已处理的文件
    processed = load_processed_files(filelog)
    print(f"已处理文件数: {len(processed)}")

    # 过滤出未处理的文件
    pending_files = [f for f in all_files if f not in processed]
    print(f"待处理文件数: {len(pending_files)}")

    if not pending_files:
        print("✅ 所有文件均已处理完毕！")
        return

    # 依次处理未处理的文件
    for filename in pending_files:
        filepath = os.path.join(fold_dir, filename)
        try:
            if nums <= 0:
                break
            else:
                csdn_blog.file_path = filepath
                csdn_blog.file_name = filename
                csdn_blog.title = 'your title'
                csdn_blog.content = open(filepath).read().strip()
                ret = process_file(csdn_blog, "save")
                if not ret:
                    print("文件处理失败")
                    return
                # 记录已处理文件到日志文件
                mark_as_processed(filelog, filename)
                time.sleep(30) # 冷却30s
        except Exception as e:
            print(f"❌ 处理失败 {filename}: {e}")
            # 可选择继续或退出
            # raise  # 如果希望中断
        nums -= 1

    print("🎉 所有文件处理完成！")

if __name__ == "__main__":
    print("hello world")
