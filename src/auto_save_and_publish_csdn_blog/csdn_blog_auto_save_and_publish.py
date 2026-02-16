#!/usr/bin/env python
# -*- encoding: utf-8 -*-
'''
@File    :   csdn_auto_publish.py
@Time    :   2026-02-16 17:31:44
@Author  :   sven
@Version :   1.0
@Desc    :   auto save and publish blog on csdn

pyperclip==1.9.0
selenium==4.26.1

'''

import os
import process
import time
import sys
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pyperclip

# ===== 配置区 =====
MD_FOLDER = "your fold"
PROCESSED_LOG = "processed_files.txt"

login_url = 'https://passport.csdn.net/login'
pub_url = 'https://editor.csdn.net/md/'
csdn_manage_url = 'https://mp.csdn.net/mp_blog/creation/editor/new'
options = webdriver.chrome.options.Options()
options.page_load_strategy = 'normal'
driver = webdriver.Chrome(options=options)


def csdn_blog_config(browser_driver, csdn_blog_file):
    wait = WebDriverWait(browser_driver, 15)

    # === 0. 点击发布文章按钮 ===
    print("点击发布文章按钮")
    save_button = wait.until(
        EC.element_to_be_clickable(
            (By.XPATH, '//button[contains(@class, "btn-publish") and contains(text(), "发布文章")]'))
    )
    save_button.click()

    # === 1. 添加文章标签 ===
    print("🏷️ 添加文章标签...")
    add_tag_button = wait.until(
        EC.element_to_be_clickable((By.XPATH, '//button[contains(@class, "tag__btn-tag") and contains(text(), "添加文章标签")]'))
    )
    add_tag_button.click()

    tag_input = wait.until(
        EC.presence_of_element_located((By.XPATH, '//input[@placeholder="请输入文字搜索，Enter键入可添加自定义标签"]'))
    )

    # 循环添加标签
    for tag in csdn_blog_file.tags:
        print(f"正在添加标签: {tag}")
        # 输入标签
        tag_input.send_keys(tag)
        # 按 Enter 键确认添加
        tag_input.send_keys(Keys.ENTER)

        # 可选：等待 UI 反馈（如标签 chip 出现），或短暂停顿
        time.sleep(2)
    print("✅ 所有标签已成功添加！")

    # 关闭添加标签页
    label_close = wait.until(
        EC.element_to_be_clickable((By.XPATH, '//div[@class="mark_selection_box_body"]//button[@title="关闭"]'))
    )
    label_close.click()
    print("✅ 已关闭添加标签页！")

    # === 2. 设置封面 ===
    print("✅ 设置封面！")
    file_input = browser_driver.find_element(By.CSS_SELECTOR, 'input.el-upload__input[type="file"]') # 定位隐藏的 file input（关键！）
    file_input.send_keys(csdn_blog_file.cover_img_path)
    time.sleep(1) # 确认文件上传
    upload_img = wait.until(
        EC.element_to_be_clickable((By.XPATH, '//div[@class="vicp-operate-btn"]'))
    )
    upload_img.click()
    time.sleep(1) # 等待文件上传成功
    print(f"✅ 已上传文件: {csdn_blog_file.cover_img_path}")
    print("✅ 已设置封面！")

    # === 3. AI提取摘要 ===
    print("🤖 点击【AI提取摘要】...")
    ai_summary_btn = wait.until(
         EC.element_to_be_clickable((By.XPATH, '//button[.//span[text()="AI提取摘要"]]'))
    )
    ai_summary_btn.click()

    time.sleep(5)  # 等待摘要生成
    print("✅ 摘要已提取")
    print("点击关闭AI摘要")
    ai_btn_close = wait.until(
        EC.element_to_be_clickable(
            (By.XPATH, '//div[@class="side-title flex flex--row is-assistant"]//button[@title="关闭" and contains(@class, "side-title__button")]'))
    )
    ai_btn_close.click()

    # === 4. 选择分类专栏 ===
    print("📂 选择新建分类专栏")
    # 点击“新建分类专栏”触发下拉菜单
    category_trigger = wait.until(
        EC.element_to_be_clickable((By.XPATH, '//div[@id="tagList"]//button[contains(text(), "新建分类专栏")]'))
    )
    category_trigger.click()
    # 循环添加分类
    for categorie in csdn_blog_file.categories:
        print(f"正在添加分类: {categorie}")
        # 添加分类
        add_categories = browser_driver.find_elements(By.XPATH, '//div[@class="tag__item-box"]//span[@contenteditable="true"]')
        if add_categories:
            category_input = add_categories[0]  # 取第一个
            category_input.click()  # 获取焦点
            category_input.send_keys(categorie)
            category_input.send_keys(Keys.ENTER)
            print("✅ 已输入标签并按回车")
        else:
            print("⚠️ 未找到可编辑的空标签输入区域")
        time.sleep(0.5)
    print("✅ 分类专栏已选择")

    # 关闭下拉菜单（点击添加标签，使得下拉菜单失去焦点）
    add_tag_button.click()
    label_close = wait.until(
        EC.element_to_be_clickable((By.XPATH, '//div[@class="mark_selection_box_body"]//button[@title="关闭"]'))
    )
    label_close.click()
    print("✅ 分类专栏页面已关闭 ")

    # === 5. 选择文章类型：原创 ===
    print("✍️ 选择文章类型：原创...")
    original_radio = wait.until(
        EC.element_to_be_clickable((By.XPATH, '//label[@for="original" and @class="lab-switch"]'))
    )
    original_radio.click()
    print("✅ 文章类型已设为原创")

    # === 6. 可见范围：全部可见 ===
    print("👁️ 设置可见范围：全部可见...")
    public_radio = wait.until(
        EC.element_to_be_clickable(
            (By.XPATH, '//div[@class="el-tooltip item"]//label[@for="public" and @class="lab-switch"]')
        )
    )
    public_radio.click()
    print("✅ 可见范围已设为全部可见")
    return True

def csdn_blog_config_and_save(browser_driver, csdn_blog_file):
    ret = csdn_blog_config(browser_driver, csdn_blog_file)
    if not ret:
        print("===配置博客失败===")
        return False

    # === 7. 点击“保存为草稿” ===
    print("🚀 点击【保存为草稿】...")
    wait = WebDriverWait(browser_driver, 15)
    publish_btn = wait.until(
        EC.element_to_be_clickable(
            (By.XPATH, '//div[@class="modal__button-bar"]//button[contains(text(), "保存为草稿")]'))
    )
    publish_btn.click()
    time.sleep(1) # 等待1s
    print("✅ 已保存为草稿")
    open_csdn_manager_page(browser_driver)
    return True

def csdn_blog_config_and_publish(browser_driver, csdn_blog_file):
    ret = csdn_blog_config(browser_driver, csdn_blog_file)
    if not ret:
        print("===配置博客失败===")
        return False

    # === 点击“发布文章” ===
    print("🚀 点击【发布文章】...")
    wait = WebDriverWait(browser_driver, 15)
    publish_btn = wait.until(
        EC.element_to_be_clickable(
            (By.XPATH, '//div[@class="modal__button-bar"]//button[contains(text(), "发布文章")]'))
    )
    publish_btn.click()
    time.sleep(1) # 等待1s
    print("✅ 发布请求已提交")
    open_csdn_manager_page(browser_driver)
    return True

def open_csdn_manager_page(browser_driver, csdn_manage_page_url="https://mp.csdn.net/mp_blog/manage/article"):
    # 打开博客管理页面
    browser_driver.switch_to.new_window('tab')
    browser_driver.get(csdn_manage_page_url)
    print("✅ 已打开博客管理页面")

def csdn_save_and_publish(csdn_blog_file, editor_csdn_blog_url="https://mp.csdn.net/mp_blog/creation/editor/new", typ="save"):
    # print("📝 启动 CSDN 草稿发布...")
    ret = csdn_blog_save(driver, csdn_blog_file, editor_csdn_blog_url)
    if not ret:
        print("===保存失败===")
        return False
    if typ == "save":
        return csdn_blog_config_and_save(driver, csdn_blog_file)

    return csdn_blog_config_and_publish(driver, csdn_blog_file)

def csdn_blog_save(browser_driver, csdn_blog_file, editor_csdn_blog_url="https://mp.csdn.net/mp_blog/creation/editor/new"):
    print("📝 启动 CSDN 草稿发布...")
    browser_driver.switch_to.new_window('tab')
    browser_driver.get(csdn_manage_url)
    wait = WebDriverWait(browser_driver, 15)

    # === 1. 填写文章标题 ===
    print("输入文章标题")
    title_input = wait.until(
        EC.presence_of_element_located((By.XPATH, '//input[@placeholder="请输入文章标题（5~100个字）"]'))
    )
    title_input.clear()
    if len(csdn_blog_file.title) < 5:
        print("标题过短")
        return False

    title_input.send_keys(csdn_blog_file.title)
    print(f"✅ 标题: {csdn_blog_file.title}")

    # === 2. 清空并粘贴文章内容 ===
    editor = wait.until(
        EC.element_to_be_clickable((By.XPATH, '//pre[@contenteditable="true"]'))
    )
    editor.click()
    time.sleep(1)

    # 全选 + 删除
    cmd = Keys.COMMAND if sys.platform == 'darwin' else Keys.CONTROL
    actions = webdriver.ActionChains(browser_driver)
    actions.key_down(cmd).send_keys('a').key_up(cmd).perform()
    actions.send_keys(Keys.BACKSPACE).perform()
    time.sleep(1)

    # 粘贴内容
    pyperclip.copy(csdn_blog_file.content)
    actions.key_down(cmd).send_keys('v').key_up(cmd).perform()
    print("✅ 内容已粘贴")

    # === 3. 保存草稿（关键修复：直接点击“保存草稿”按钮）===
    print("💾 点击【保存草稿】")
    save_button = wait.until(
        EC.element_to_be_clickable(
            (By.XPATH, '//button[contains(@class, "btn-save") and contains(text(), "保存草稿")]'))
    )
    save_button.click()
    # 等待保存完成（CSDN 通常会弹出提示或 URL 变化）
    time.sleep(2)
    print("✅ 草稿保存成功！")
    return True



def login_in(browser_driver, login_url="https://passport.csdn.net/login", timeout=60, login_method ="WeChatScanCode"):
    print("🚀 启动登录 CSDN...")
    browser_driver.get(login_url)
    wait = WebDriverWait(browser_driver, timeout)
    try:
        if login_method == "WeChatScanCode":
            """
            半自动微信扫码登录 CSDN
            :param driver: WebDriver 实例
            :param login_url: CSDN 登录页 URL
            :param timeout: 最大等待扫码时间（秒）
            """
            wechat_tab = wait.until(
                EC.presence_of_element_located((By.XPATH, '//span[@class="tabs-active" and text()="微信登录"]'))
            )
            print("✅ 当前为微信登录模式")
        elif login_method == "VerificationCode":
            print("点击切换登录方式按钮")
            save_button = wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, '//div[@class="login-box-tabs-items"]//span[contains(text(), "验证码登录")]'))
            )
            save_button.click()
            print("✅ 当前为验证码模式")
        elif login_method == "AppScanCode":
            save_button = wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, '//div[@class="login-box-tabs-items"]//span[contains(text(), "APP登录")]'))
            )
            save_button.click()

            print("✅ 当前为App扫码模式")
        elif login_method == "LoginThirdItem":
            wechat_tab = wait.until(
                EC.presence_of_element_located((By.XPATH, '//div[@class="login-third-items"]//span[@class="login-third-item login-third-xxx"]'))
            )
            print("✅ 当前为第三方登录模式")

    except:
        print("⚠️ 未检测到登录方式，请继续尝试...")

    # 等待登录成功（页面跳转到 csdn.net 主站）
    try:
        # 等待 URL 变为首页（说明登录成功）
        wait.until(lambda d: "csdn.net" in d.current_url and d.current_url != login_url)
        print("✅ 登录成功！")
        return True
    except:
        print("❌ 超时：未检测到登录成功。请确保已完成登录。")
        return False


class Blog(object):
    def __init__(self, file_path, title) -> None:
        self.file_path = file_path
        self.title = title
        self.content = ''
        self.summary = ''
        self.tags = []
        self.cover_img_path = ''
        self.categories = []


def save_and_publish_csdn_blog(csdn_blog_s: Blog, typ: str):
    print('-- title : ', csdn_blog_s.title)
    ret = csdn_save_and_publish(csdn_blog_s, typ)
    if ret:
        print("====执行成功！=====")
    else:
        print("====执行失败====")
        return False
    return True

if __name__ == "__main__":
    retry_time = 3
    success = False
    while retry_time >= 0 and success == False:
        success = login_in(driver, login_method="WeChatScanCode")
        if success:
            print("\n🎉 登录成功！现在可以进行后续操作")
        else:
            print("\n⚠️ 登录失败，重试 {} 次", retry_time)
            retry_time -= 1
    # 设置默认参数
    title = 'your blog titile ' #
    csdn_blog = Blog(MD_FOLDER, title)

    csdn_blog.tags = 'your tags'
    csdn_blog.categories = 'your categories'
    csdn_blog.cover_img_path = os.path.abspath("your csdn_profile.png")
    max_files = 2
    process.batch_process_files(MD_FOLDER, PROCESSED_LOG, max_files, csdn_blog, save_and_publish_csdn_blog)

    time.sleep(30)
