"""CSDN Blog Auto-Save-and-Publish Tool

Usage:
    python -m src.auto_save_and_publish_csdn_blog.main
    python -m src.auto_save_and_publish_csdn_blog.main --headless
    python -m src.auto_save_and_publish_csdn_blog.main --folder /path/to/md/files
"""

import argparse
import os
import sys
import time

from .browser import BrowserManager
from .config import (
    CSDN_LOGIN_METHOD, CSDN_LOGIN_URL, CSDN_EDITOR_URL, CSDN_MANAGE_URL,
    CSDN_MANAGE_LIST_URL, MD_FOLDER, PROCESSED_LOG, DEFAULT_TAGS,
    DEFAULT_CATEGORIES, DEFAULT_COVER_IMG, MAX_FILES_PER_RUN, HEADLESS,
)
from .editor import CsdnEditor, process_blog
from .login import login_csdn
from .models import Blog
from .processor import MarkdownProcessor


def main():
    parser = argparse.ArgumentParser(description="CSDN Blog Auto Save & Publish")
    parser.add_argument("--headless", action="store_true", default=HEADLESS,
                        help="Run Chrome in headless mode")
    parser.add_argument("--folder", type=str, default=MD_FOLDER,
                        help="Folder containing .md files to publish")
    parser.add_argument("--action", type=str, default="save",
                        choices=["save", "publish"],
                        help="Action: save (draft) or publish")
    args = parser.parse_args()

    if not args.folder:
        print("错误: 未设置 MD_FOLDER。请通过 --folder 参数或 .env 文件指定。")
        sys.exit(1)

    # 1. start browser
    print("🌐 启动浏览器...")
    with BrowserManager(headless=args.headless) as driver:
        # 2. login
        logged_in = False
        for attempt in range(3, 0, -1):
            logged_in = login_csdn(driver, login_url=CSDN_LOGIN_URL,
                                   login_method=CSDN_LOGIN_METHOD)
            if logged_in:
                print("\n🎉 登录成功！现在可以进行后续操作")
                break
            print(f"\n⚠️ 登录失败，重试 {attempt - 1} 次")
        if not logged_in:
            print("❌ 登录失败，退出。")
            sys.exit(1)

        editor = CsdnEditor(driver)

        # 3. scan files
        processor = MarkdownProcessor(args.folder, PROCESSED_LOG)
        pending_files = processor.get_pending_files()

        if not pending_files:
            print("✅ 所有文件均已处理完毕！")
            return

        # 4. process files
        success_count = 0
        for i, filename in enumerate(pending_files):
            if i >= MAX_FILES_PER_RUN:
                print(f"已达到单次最大处理数量 ({MAX_FILES_PER_RUN})，退出。")
                break

            print(f"\n{'='*50}")
            print(f"处理文件 [{i+1}/{min(len(pending_files), MAX_FILES_PER_RUN)}]: {filename}")
            print(f"{'='*50}")

            content = processor.read_file(filename)

            blog = Blog(
                file_path=os.path.join(args.folder, filename),
                title=os.path.splitext(filename)[0],
                content=content,
                tags=DEFAULT_TAGS,
                categories=DEFAULT_CATEGORIES,
                cover_img_path=DEFAULT_COVER_IMG,
            )

            try:
                success = process_blog(
                    editor, blog, args.action,
                    editor_url=CSDN_EDITOR_URL,
                    manage_url=CSDN_MANAGE_LIST_URL,
                )
                if success:
                    processor.mark_processed(filename)
                    success_count += 1
                    print(f"✅ {filename} 处理成功")
                else:
                    print(f"❌ {filename} 处理失败")
            except Exception as e:
                print(f"❌ 处理失败 {filename}: {e}")

            if i < min(len(pending_files), MAX_FILES_PER_RUN) - 1:
                time.sleep(30)

        print(f"\n🎉 处理完成！成功: {success_count}/{min(len(pending_files), MAX_FILES_PER_RUN)}")

    print("浏览器已关闭。")


if __name__ == "__main__":
    main()
