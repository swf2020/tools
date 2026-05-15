import sys
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium import webdriver
import pyperclip

from .models import Blog


class CsdnEditor:
    def __init__(self, driver):
        self.driver = driver
        self.wait = WebDriverWait(driver, 15)

    # ── navigation ──────────────────────────────────

    def open_new_article(self, editor_url: str):
        print("📝 打开新文章编辑页...")
        self.driver.switch_to.new_window("tab")
        self.driver.get(editor_url)

    def open_manage_page(self, manage_url: str):
        self.driver.switch_to.new_window("tab")
        self.driver.get(manage_url)
        print("✅ 已打开博客管理页面")

    # ── content ──────────────────────────────────────

    def fill_title(self, title: str) -> bool:
        print("输入文章标题")
        title_input = self.wait.until(
            EC.presence_of_element_located(
                (By.XPATH, '//input[@placeholder="请输入文章标题（5~100个字）"]')
            )
        )
        title_input.clear()
        if len(title) < 5:
            print("标题过短")
            return False
        title_input.send_keys(title)
        print(f"✅ 标题: {title}")
        return True

    def fill_content(self, content: str):
        editor = self.wait.until(
            EC.element_to_be_clickable((By.XPATH, '//pre[@contenteditable="true"]'))
        )
        editor.click()
        time.sleep(1)

        cmd = Keys.COMMAND if sys.platform == "darwin" else Keys.CONTROL
        actions = webdriver.ActionChains(self.driver)
        actions.key_down(cmd).send_keys("a").key_up(cmd).perform()
        actions.send_keys(Keys.BACKSPACE).perform()
        time.sleep(1)

        pyperclip.copy(content)
        actions.key_down(cmd).send_keys("v").key_up(cmd).perform()
        print("✅ 内容已粘贴")

    def save_draft(self):
        print("💾 点击【保存草稿】")
        save_button = self.wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, '//button[contains(@class, "btn-save") and contains(text(), "保存草稿")]')
            )
        )
        save_button.click()
        time.sleep(2)
        print("✅ 草稿保存成功！")

    # ── configuration ────────────────────────────────

    def configure_article(self, blog: Blog) -> bool:
        """Configure tags, cover, summary, categories, originality, visibility."""
        wait = self.wait

        # 0. click "发布文章" button to enter config modal
        print("点击发布文章按钮")
        save_button = wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, '//button[contains(@class, "btn-publish") and contains(text(), "发布文章")]')
            )
        )
        save_button.click()

        # 1. add tags
        print("🏷️ 添加文章标签...")
        add_tag_button = wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, '//button[contains(@class, "tag__btn-tag") and contains(text(), "添加文章标签")]')
            )
        )
        add_tag_button.click()

        tag_input = wait.until(
            EC.presence_of_element_located(
                (By.XPATH, '//input[@placeholder="请输入文字搜索，Enter键入可添加自定义标签"]')
            )
        )
        for tag in blog.tags:
            print(f"正在添加标签: {tag}")
            tag_input.send_keys(tag)
            tag_input.send_keys(Keys.ENTER)
            time.sleep(2)
        print("✅ 所有标签已成功添加！")

        label_close = wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, '//div[@class="mark_selection_box_body"]//button[@title="关闭"]')
            )
        )
        label_close.click()
        print("✅ 已关闭添加标签页！")

        # 2. set cover image
        print("✅ 设置封面！")
        file_input = self.driver.find_element(By.CSS_SELECTOR, 'input.el-upload__input[type="file"]')
        file_input.send_keys(blog.cover_img_path)
        time.sleep(1)
        upload_img = wait.until(
            EC.element_to_be_clickable((By.XPATH, '//div[@class="vicp-operate-btn"]'))
        )
        upload_img.click()
        time.sleep(1)
        print(f"✅ 已上传文件: {blog.cover_img_path}")
        print("✅ 已设置封面！")

        # 3. AI extract summary
        print("🤖 点击【AI提取摘要】...")
        ai_summary_btn = wait.until(
            EC.element_to_be_clickable((By.XPATH, '//button[.//span[text()="AI提取摘要"]]'))
        )
        ai_summary_btn.click()
        time.sleep(5)
        print("✅ 摘要已提取")
        print("点击关闭AI摘要")
        ai_btn_close = wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, '//div[@class="side-title flex flex--row is-assistant"]//button[@title="关闭" and contains(@class, "side-title__button")]')
            )
        )
        ai_btn_close.click()

        # 4. select categories
        print("📂 选择新建分类专栏")
        category_trigger = wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, '//div[@id="tagList"]//button[contains(text(), "新建分类专栏")]')
            )
        )
        category_trigger.click()
        for categorie in blog.categories:
            print(f"正在添加分类: {categorie}")
            add_categories = self.driver.find_elements(
                By.XPATH, '//div[@class="tag__item-box"]//span[@contenteditable="true"]'
            )
            if add_categories:
                category_input = add_categories[0]
                category_input.click()
                category_input.send_keys(categorie)
                category_input.send_keys(Keys.ENTER)
                print("✅ 已输入标签并按回车")
            else:
                print("⚠️ 未找到可编辑的空标签输入区域")
            time.sleep(0.5)
        print("✅ 分类专栏已选择")

        # close category dropdown
        add_tag_button.click()
        label_close = wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, '//div[@class="mark_selection_box_body"]//button[@title="关闭"]')
            )
        )
        label_close.click()
        print("✅ 分类专栏页面已关闭")

        # 5. set article type: original
        print("✍️ 选择文章类型：原创...")
        original_radio = wait.until(
            EC.element_to_be_clickable((By.XPATH, '//label[@for="original" and @class="lab-switch"]'))
        )
        original_radio.click()
        print("✅ 文章类型已设为原创")

        # 6. set visibility: public
        print("👁️ 设置可见范围：全部可见...")
        public_radio = wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, '//div[@class="el-tooltip item"]//label[@for="public" and @class="lab-switch"]')
            )
        )
        public_radio.click()
        print("✅ 可见范围已设为全部可见")
        return True

    # ── final actions ────────────────────────────────

    def publish(self):
        print("🚀 点击【发布文章】...")
        publish_btn = self.wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, '//div[@class="modal__button-bar"]//button[contains(text(), "发布文章")]')
            )
        )
        publish_btn.click()
        time.sleep(1)
        print("✅ 发布请求已提交")

    def save_as_draft_final(self):
        print("🚀 点击【保存为草稿】...")
        publish_btn = self.wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, '//div[@class="modal__button-bar"]//button[contains(text(), "保存为草稿")]')
            )
        )
        publish_btn.click()
        time.sleep(1)
        print("✅ 已保存为草稿")


def process_blog(editor: CsdnEditor, blog: Blog, action: str,
                 editor_url: str, manage_url: str) -> bool:
    """
    Full pipeline: open editor → fill content → save draft → configure → publish/save.
    action: "save" or "publish"
    """
    editor.open_new_article(editor_url)

    if not editor.fill_title(blog.title):
        return False
    editor.fill_content(blog.content)
    editor.save_draft()

    if not editor.configure_article(blog):
        print("===配置博客失败===")
        return False

    if action == "save":
        editor.save_as_draft_final()
    else:
        editor.publish()

    editor.open_manage_page(manage_url)
    return True
