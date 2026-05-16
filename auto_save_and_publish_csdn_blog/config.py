import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _get_list(key: str, default: str = "") -> list[str]:
    val = os.environ.get(key, default)
    if not val:
        return []
    return [item.strip() for item in val.split(",") if item.strip()]


CSDN_LOGIN_METHOD = os.environ.get("CSDN_LOGIN_METHOD", "WeChatScanCode")
CSDN_LOGIN_URL = os.environ.get("CSDN_LOGIN_URL", "https://passport.csdn.net/login")
CSDN_EDITOR_URL = os.environ.get("CSDN_EDITOR_URL", "https://mp.csdn.net/mp_blog/creation/editor/new")
CSDN_MANAGE_URL = os.environ.get("CSDN_MANAGE_URL", "https://mp.csdn.net/mp_blog/manage/article")
CSDN_MANAGE_LIST_URL = os.environ.get("CSDN_MANAGE_LIST_URL", "https://mp.csdn.net/mp_blog/manage/article")

MD_FOLDER = os.environ.get("MD_FOLDER", "")
PROCESSED_LOG = os.environ.get("PROCESSED_LOG", "processed_files.txt")
DEFAULT_TAGS = _get_list("DEFAULT_TAGS", "")
DEFAULT_CATEGORIES = _get_list("DEFAULT_CATEGORIES", "")
DEFAULT_COVER_IMG = os.environ.get("DEFAULT_COVER_IMG", "")
MAX_FILES_PER_RUN = int(os.environ.get("MAX_FILES_PER_RUN", "5"))
HEADLESS = os.environ.get("HEADLESS", "false").lower() == "true"
