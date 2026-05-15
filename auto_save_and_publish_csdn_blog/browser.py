from selenium import webdriver


class BrowserManager:
    def __init__(self, headless: bool = False):
        self.headless = headless
        self.driver = None

    def create(self):
        options = webdriver.ChromeOptions()
        options.page_load_strategy = "normal"
        if self.headless:
            options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-gpu")
        self.driver = webdriver.Chrome(options=options)
        return self.driver

    def close(self):
        if self.driver:
            self.driver.quit()
            self.driver = None

    def __enter__(self):
        return self.create()

    def __exit__(self, *args):
        self.close()
