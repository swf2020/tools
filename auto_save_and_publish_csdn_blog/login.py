import sys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def login_csdn(driver, login_url: str = "https://passport.csdn.net/login",
               login_method: str = "WeChatScanCode", timeout: int = 120) -> bool:
    print("🚀 启动登录 CSDN...")
    driver.get(login_url)
    wait = WebDriverWait(driver, timeout)

    try:
        if login_method == "WeChatScanCode":
            wait.until(EC.presence_of_element_located(
                (By.XPATH, '//span[@class="tabs-active" and text()="微信登录"]')
            ))
            print("✅ 当前为微信登录模式")

        elif login_method == "VerificationCode":
            print("点击切换登录方式按钮")
            btn = wait.until(EC.element_to_be_clickable(
                (By.XPATH, '//div[@class="login-box-tabs-items"]//span[contains(text(), "验证码登录")]')
            ))
            btn.click()
            print("✅ 当前为验证码模式")

        elif login_method == "AppScanCode":
            btn = wait.until(EC.element_to_be_clickable(
                (By.XPATH, '//div[@class="login-box-tabs-items"]//span[contains(text(), "APP登录")]')
            ))
            btn.click()
            print("✅ 当前为App扫码模式")

        elif login_method == "LoginThirdItem":
            wait.until(EC.presence_of_element_located(
                (By.XPATH, '//div[@class="login-third-items"]//span[@class="login-third-item login-third-xxx"]')
            ))
            print("✅ 当前为第三方登录模式")

    except Exception:
        print("⚠️ 未检测到登录方式，请继续尝试...")

    try:
        wait.until(lambda d: "csdn.net" in d.current_url and d.current_url != login_url)
        print("✅ 登录成功！")
        return True
    except Exception:
        print("❌ 超时：未检测到登录成功。请确保已完成登录。")
        return False
