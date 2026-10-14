# -*- coding: utf-8 -*-
"""
自动化测试通用方法（Utils 类）

集中存放所有页面自动化代码都会用到的通用能力，页面对象（login_register / image_edit /
image_stitch / my_image / history_record）只负责"某个页面有什么元素、能做什么操作"，
其余如驱动初始化、显式等待、点击输入、Toast 文案采集、截图、登录态处理等一律走本类。

设计要点：
1. 等待一律使用显式等待（WebDriverWait），不用 sleep，避免用例慢且不稳定；
2. Element Plus 的 Toast（ElMessage）会自动消失，因此用 MutationObserver 在页面里
   "录屏式"记录所有出现过的提示文案，避免竞态丢文案（见 start_message_recorder）；
3. 登录态优先复用已有 token，其次读环境变量注入 token，最后才走 UI 密码登录；
   三者都没有时用例直接 skip，而不是失败。

可用环境变量（均带默认值，见下方常量）：
    AIWEAR_BASE_URL    被测系统地址，默认 http://127.0.0.1:5173（Vite 开发服务）
    AIWEAR_BROWSER     chrome | edge，默认 chrome
    AIWEAR_HEADLESS    1 表示无头运行，默认 0
    AIWEAR_WINDOW      浏览器窗口尺寸，默认 1920,1080
    AIWEAR_TIMEOUT     常规等待秒数，默认 20
    AIWEAR_AI_TIMEOUT  AI 生成类接口等待秒数，默认 300
    AIWEAR_TOKEN       已登录用户的 JWT，用于免登录进入业务页面
    AIWEAR_ACCOUNT     用户名密码登录用的用户名（默认 zhangsan，不存在时后端会自动注册）
    AIWEAR_PASSWORD    用户名密码登录用的密码（默认 123456）
    AIWEAR_EMAIL       验证码登录用的邮箱
    AIWEAR_CODE        邮箱收到的验证码
    AIWEAR_UPLOAD_DIR  上传/选择用的素材图片目录，默认自动查找项目里的 img 目录
    AIWEAR_REJECT_IMAGE   非业务图片（汽车/风景）路径，不设时按文件名关键字在素材目录里找
    AIWEAR_LANDSCAPE_IMAGE 同上，用于图搜图无结果用例
"""

from __future__ import annotations

import json
import os
import random
import time
from datetime import datetime
from pathlib import Path

import pytest
from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver import ChromeOptions, EdgeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# ---------------------------------------------------------------------------
# 环境配置
# ---------------------------------------------------------------------------
#: 自动化测试目录（本文件所在目录）
TEST_DIR = Path(__file__).resolve().parent
#: 自动化测试目录的上一级（测试目录可能放在项目根，也可能放在 AIWearPython 这类子工程里）
PROJECT_ROOT = TEST_DIR.parent
#: 截图输出目录
SCREENSHOT_DIR = TEST_DIR / "screenshots"


def _resolve_upload_dir() -> Path:
    """挑选真实存在的素材目录，避免测试目录被移动后上传类用例整体跳过。

    优先级：环境变量 AIWEAR_UPLOAD_DIR > 本级/上级目录下的 img。
    """
    env_dir = os.getenv("AIWEAR_UPLOAD_DIR", "").strip()
    if env_dir:
        return Path(env_dir)
    candidates = [
        PROJECT_ROOT / "img",          # 自动化测试/ 与 img/ 同级（放在项目根时）
        PROJECT_ROOT.parent / "img",   # 自动化测试/ 在子工程里，img/ 在项目根
        TEST_DIR / "img",
    ]
    for path in candidates:
        if path.is_dir():
            return path
    return candidates[0]


#: 被测系统地址
BASE_URL = os.getenv("AIWEAR_BASE_URL", "http://127.0.0.1:5173").rstrip("/")
#: 浏览器类型：chrome | edge
BROWSER = os.getenv("AIWEAR_BROWSER", "chrome").strip().lower()
#: 是否无头运行
HEADLESS = os.getenv("AIWEAR_HEADLESS", "0").strip() == "1"
#: 浏览器窗口尺寸
WINDOW_SIZE = tuple(int(v) for v in os.getenv("AIWEAR_WINDOW", "1920,1080").split(","))
#: 常规等待超时（秒）
DEFAULT_TIMEOUT = float(os.getenv("AIWEAR_TIMEOUT", "20"))
#: AI 生成类接口（编辑/合并）等待超时（秒），大模型出图较慢
AI_TIMEOUT = float(os.getenv("AIWEAR_AI_TIMEOUT", "300"))
#: 上传/选择素材时的默认素材目录（未设置环境变量时自动在项目里查找 img 目录）
UPLOAD_DIR = _resolve_upload_dir()

#: 演示账号（可用环境变量覆盖）。留默认值是为了让用例开箱即跑；
#: 后端 UserServiceImpl.auth() 对不存在的用户名会直接注册，所以这个账号不存在也能自动创建。
DEFAULT_ACCOUNT = os.getenv("AIWEAR_ACCOUNT", "zhangsan").strip()
DEFAULT_PASSWORD = os.getenv("AIWEAR_PASSWORD", "123456").strip()

#: 自动注册临时账号时使用的用户名前缀与密码（用完即弃，仅用于空态类用例的数据准备）
TEMP_ACCOUNT_PREFIX = "autotest_"
TEMP_ACCOUNT_PASSWORD = "auto@123456"

#: 素材文件名关键字：用于在素材目录里区分"人物图"和"服装图"
PERSON_IMAGE_KEYWORDS = ("人物", "人像", "模特", "男", "女", "person", "model")
CLOTHING_IMAGE_KEYWORDS = ("服装", "衣服", "衣", "裤", "裙", "袖", "衬衫", "T恤", "clothing")
#: 非业务图片关键字：AI 审核应判定为不通过（汽车、风景等），用于上传拦截用例
NON_BUSINESS_IMAGE_KEYWORDS = ("汽车", "车", "风景", "景", "建筑", "landscape", "car", "scene")


#: 前端 localStorage 中保存登录态的 key（见 fronted/src/store/auth.js）
TOKEN_KEY = "mengtu_token"
USER_KEY = "mengtu_user"

#: 记录页面所有 Toast 文案的脚本：用 MutationObserver 持续采集，避免 Toast 自动消失
_MESSAGE_RECORDER_JS = """
if (!window.__aiwearMsgHooked) {
  window.__aiwearMsgHooked = true;
  window.__aiwearMessages = [];
  const collect = () => {
    document.querySelectorAll('.el-message').forEach((el) => {
      const node = el.querySelector('.el-message__content') || el;
      const text = (node.textContent || '').trim();
      if (text && !window.__aiwearMessages.includes(text)) window.__aiwearMessages.push(text);
    });
  };
  new MutationObserver(collect).observe(document.documentElement, { childList: true, subtree: true });
}
window.__aiwearMessages = window.__aiwearMessages || [];
"""


class Utils:
    """自动化测试通用方法工具类。

    典型用法：

        u = Utils()                 # 自动按环境变量初始化浏览器
        u.open("/login")            # 打开登录页
        u.input_text((By.CSS_SELECTOR, "input[placeholder='请输入邮箱']"), "a@b.com")
        u.click((By.CSS_SELECTOR, "button.submit"))
        assert "验证码" in u.wait_message("验证码")
        u.quit()
    """

    # ------------------------------------------------------------------
    # 初始化与销毁
    # ------------------------------------------------------------------
    def __init__(self, driver=None, base_url: str = BASE_URL, timeout: float = DEFAULT_TIMEOUT):
        """初始化工具类。

        :param driver: 已有 WebDriver；不传则按环境变量自动创建
        :param base_url: 被测系统地址
        :param timeout: 常规显式等待超时（秒）
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.driver = driver or self.create_driver()

    @staticmethod
    def create_driver(browser: str = BROWSER, headless: bool = HEADLESS):
        """创建浏览器驱动，支持 Chrome / Edge 两种内核。"""
        if browser == "edge":
            options = EdgeOptions()
            if headless:
                options.add_argument("--headless=new")
            options.add_argument(f"--window-size={WINDOW_SIZE[0]},{WINDOW_SIZE[1]}")
            options.add_argument("--disable-gpu")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option("useAutomationExtension", False)
            return webdriver.Edge(options=options)

        options = ChromeOptions()
        if headless:
            options.add_argument("--headless=new")
        options.add_argument(f"--window-size={WINDOW_SIZE[0]},{WINDOW_SIZE[1]}")
        options.add_argument("--disable-gpu")
        # 关闭"Chrome 正受到自动测试软件的控制"提示，避免遮挡页面元素
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        return webdriver.Chrome(options=options)

    def quit(self):
        """关闭浏览器，用例结束后必须调用，否则会残留进程。"""
        if self.driver:
            try:
                self.driver.quit()
            finally:
                self.driver = None

    # ------------------------------------------------------------------
    # 页面导航
    # ------------------------------------------------------------------
    def open(self, path: str = "/"):
        """打开被测系统的某个路径（支持传完整 URL），并重置 Toast 采集。"""
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        self.driver.get(url)
        self.start_message_recorder()
        self.clear_messages()
        return self

    def current_url(self) -> str:
        """当前地址。"""
        return self.driver.current_url

    def current_path(self) -> str:
        """当前地址的路径部分（去掉域名与 query）。"""
        url = self.current_url()
        path = url.split("://", 1)[-1]
        path = path[path.find("/"):] if "/" in path else "/"
        return path.split("?")[0] or "/"

    def wait_url_contains(self, keyword: str, timeout: float = None) -> bool:
        """等待地址栏包含关键字（常用于断言路由跳转），超时返回 False。"""
        return self._wait(timeout).until(lambda d: keyword in d.current_url)

    def wait_url_not_contains(self, keyword: str, timeout: float = None) -> bool:
        """等待地址栏不再包含关键字，超时返回 False。"""
        return self._wait(timeout).until(lambda d: keyword not in d.current_url)

    # ------------------------------------------------------------------
    # 显式等待
    # ------------------------------------------------------------------
    def _wait(self, timeout: float = None) -> WebDriverWait:
        """构造 WebDriverWait，轮询间隔 0.2s，忽略元素失效异常。"""
        return WebDriverWait(
            self.driver,
            timeout if timeout is not None else self.timeout,
            poll_frequency=0.2,
            ignored_exceptions=(StaleElementReferenceException,),
        )

    def wait_visible(self, locator, timeout: float = None):
        """等待元素可见并返回该元素。"""
        return self._wait(timeout).until(EC.visibility_of_element_located(locator))

    def wait_present(self, locator, timeout: float = None):
        """等待元素存在于 DOM（不要求可见）并返回该元素。"""
        return self._wait(timeout).until(EC.presence_of_element_located(locator))

    def wait_clickable(self, locator, timeout: float = None):
        """等待元素可点击并返回该元素。"""
        return self._wait(timeout).until(EC.element_to_be_clickable(locator))

    def wait_invisible(self, locator, timeout: float = None) -> bool:
        """等待元素不可见 / 从 DOM 移除，成功返回 True。"""
        try:
            return self._wait(timeout).until(EC.invisibility_of_element_located(locator))
        except TimeoutException:
            return False

    def wait_text(self, locator, keyword: str, timeout: float = None) -> bool:
        """等待元素文本包含关键字，成功返回 True。"""
        try:
            return self._wait(timeout).until(lambda d: keyword in d.find_element(*locator).text)
        except TimeoutException:
            return False

    def wait_count_changed(self, locator, origin: int, timeout: float = None) -> bool:
        """等待元素个数发生变化（不再等于 origin），常用于断言列表刷新。"""
        try:
            return self._wait(timeout).until(lambda d: len(d.find_elements(*locator)) != origin)
        except TimeoutException:
            return False

    def wait_stable(self, seconds: float = 0.4):
        """等待页面渲染稳定，仅用于极少数无明确等待条件的场景（如轮播动画）。"""
        time.sleep(seconds)
        return self

    # ------------------------------------------------------------------
    # 元素查找
    # ------------------------------------------------------------------
    def find(self, locator):
        """查找单个元素，不存在抛 NoSuchElementException。"""
        return self.driver.find_element(*locator)

    def finds(self, locator) -> list:
        """查找多个元素，不存在返回空列表。"""
        return self.driver.find_elements(*locator)

    def exists(self, locator) -> bool:
        """元素是否存在于 DOM。"""
        return len(self.finds(locator)) > 0

    def is_displayed(self, locator) -> bool:
        """元素是否存在且可见。"""
        elements = self.finds(locator)
        return bool(elements) and elements[0].is_displayed()

    def is_enabled(self, locator) -> bool:
        """元素是否可交互（按钮灰置时返回 False）。"""
        return self.find(locator).is_enabled()

    def count(self, locator) -> int:
        """匹配元素个数。"""
        return len(self.finds(locator))

    def text_of(self, locator) -> str:
        """元素文本（去首尾空格）。"""
        return self.wait_present(locator).text.strip()

    def texts_of(self, locator) -> list:
        """多个元素文本列表（去空）。"""
        return [el.text.strip() for el in self.finds(locator) if el.text.strip()]

    def get_attribute(self, locator, attr: str) -> str:
        """读取元素属性，如 placeholder / class / src。"""
        return self.find(locator).get_attribute(attr) or ""

    # ------------------------------------------------------------------
    # 常用操作
    # ------------------------------------------------------------------
    def click(self, locator, timeout: float = None, scroll: bool = True):
        """点击元素（自动等待可点击，必要时滚动到视口中央）。"""
        element = self.wait_clickable(locator, timeout)
        if scroll:
            self.scroll_into_view(element)
        element.click()
        return self

    def click_until(self, click_locator, expect_locator, attempts: int = 3,
                    expect_timeout: float = None, timeout: float = None):
        """点击某元素，直到期望的元素出现。

        页面刚渲染完、或上一个操作（比如 AI 出图）还在收尾、机器很忙时，
        点击的反馈可能迟迟不出现。这里做有限次重试：每次点击前先看期望元素是不是
        已经出现了（上一次点击可能只是反馈慢），否则再点一次。适合"打开弹框"这类幂等操作。
        """
        last_error = None
        for _ in range(attempts):
            if self.is_displayed(expect_locator):
                return self.find(expect_locator)
            try:
                self.click(click_locator, timeout=timeout)
            except ElementClickInterceptedException as exc:
                # 被"已经弹出来的弹框"挡住，说明目标其实已经出现，交给下面的等待确认
                last_error = exc
            try:
                return self.wait_visible(expect_locator, timeout=expect_timeout)
            except TimeoutException as exc:
                last_error = exc
        raise last_error

    def js_click(self, locator):
        """JS 点击，用于被遮挡或原生不可点的元素。"""
        element = self.wait_present(locator)
        self.driver.execute_script("arguments[0].click();", element)
        return self

    def input_text(self, locator, text: str, clear: bool = True):
        """输入文本：Element Plus 的 el-input 需定位内部 <input>。"""
        element = self.wait_visible(locator)
        if clear:
            self.clear(element)
        element.send_keys(text)
        return self

    def clear(self, element):
        """清空输入框内容（兼容 el-input 的 clearable 与普通 input）。"""
        element.send_keys(Keys.CONTROL, "a")
        element.send_keys(Keys.DELETE)
        try:
            if element.get_attribute("value"):
                element.clear()
        except WebDriverException:
            pass
        return self

    def scroll_into_view(self, element):
        """滚动元素到视口中央，避免被顶栏/侧栏遮挡导致点击失败。"""
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', inline: 'center'});", element
        )
        return self

    def upload_file(self, input_locator, file_path):
        """向隐藏的 <input type="file"> 发送文件路径，完成上传/选图。

        :param input_locator: file input 的定位器
        :param file_path: 本地文件路径（str / Path）
        """
        path = Path(file_path)
        assert path.exists(), f"素材文件不存在：{path}"
        element = self.wait_present(input_locator)
        # file input 通常被 CSS 隐藏，Selenium 对隐藏 input 仍可 send_keys，无需点击
        element.send_keys(str(path))
        return self

    def allow_any_file(self, input_locator):
        """去掉 file input 的 accept 限制，用于构造"上传非图片文件"的异常用例。"""
        element = self.wait_present(input_locator)
        self.driver.execute_script("arguments[0].removeAttribute('accept');", element)
        return self

    def js(self, script: str, *args):
        """执行 JS。"""
        return self.driver.execute_script(script, *args)

    def material_images(self) -> list:
        """素材目录里的全部图片（按文件名排序）。"""
        return [
            p for p in sorted(UPLOAD_DIR.glob("*"))
            if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
        ]

    def find_material(self, keywords) -> Path:
        """按文件名关键字找一张素材；找不到返回 None（不 skip，交给调用方决定）。"""
        if isinstance(keywords, str):
            keywords = (keywords,)
        for path in self.material_images():
            if any(k.lower() in path.name.lower() for k in keywords):
                return path
        return None

    def sample_image(self, keyword: str = None) -> Path:
        """从素材目录里取一张图片，供上传/选图使用。

        :param keyword: 文件名关键字，如 "人物"、"服装"；不传则取目录内第一张
        """
        candidates = self.material_images()
        if not candidates:
            pytest.skip(f"素材目录 {UPLOAD_DIR} 下没有可用图片，请通过 AIWEAR_UPLOAD_DIR 指定")
        if keyword:
            keyword = keyword.lower()
            filtered = [p for p in candidates if keyword in p.name.lower()]
            if filtered:
                return filtered[0]
        return candidates[0]

    def sample_person_image(self) -> Path:
        """取一张人物/人像素材（按关键字识别，识别不到则退回第一张）。"""
        return self.find_material(PERSON_IMAGE_KEYWORDS) or self.sample_image()

    def sample_clothing_image(self) -> Path:
        """取一张服装/衣物素材（按关键字识别，识别不到则退回第一张）。"""
        return self.find_material(CLOTHING_IMAGE_KEYWORDS) or self.sample_image()

    def sample_non_business_image(self, env_name: str = "AIWEAR_REJECT_IMAGE") -> Path:
        """取一张"非业务图片"（汽车/风景），用于 AI 审核拦截与图搜图无结果用例。

        优先读环境变量，其次按文件名关键字在素材目录里找；都找不到返回 None（由调用方 skip）。
        """
        env_path = os.getenv(env_name, "").strip()
        if env_path:
            return Path(env_path)
        return self.find_material(NON_BUSINESS_IMAGE_KEYWORDS)

    def sample_non_image(self, directory: Path = None) -> Path:
        """构造一个非图片文件（.txt），用于"上传非图片文件"的异常用例。"""
        directory = directory or TEST_DIR / "tmp"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "not-an-image.txt"
        if not path.exists():
            path.write_text("自动化测试用的非图片文件", encoding="utf-8")
        return path

    def oversized_file(self, size_mb: int = 51, directory: Path = None) -> Path:
        """构造一个超过上传上限的文件（默认 51MB，前端限制为 50MB）。"""
        directory = directory or TEST_DIR / "tmp"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"too-large-{size_mb}mb.jpg"
        if not path.exists() or path.stat().st_size != size_mb * 1024 * 1024:
            with open(path, "wb") as fp:
                fp.truncate(size_mb * 1024 * 1024)
        return path

    # ------------------------------------------------------------------
    # 提示文案（ElMessage Toast / 表单校验红字）
    # ------------------------------------------------------------------
    def start_message_recorder(self):
        """注入 Toast 采集脚本。

        每次整页加载（open）都必须重新注入：导航会重置 window，之前注入的
        MutationObserver 和已采集的文案都会一起消失。脚本内部用
        window.__aiwearMsgHooked 做了幂等保护，重复执行没有副作用。
        """
        try:
            self.driver.execute_script(_MESSAGE_RECORDER_JS)
        except WebDriverException:
            pass
        return self

    def clear_messages(self):
        """清空已采集的 Toast 文案，通常在触发断言动作前调用。"""
        self.start_message_recorder()
        try:
            self.driver.execute_script("window.__aiwearMessages = [];")
        except WebDriverException:
            pass
        return self

    def messages(self) -> list:
        """返回当前页面出现过的全部 Toast 文案。"""
        self.start_message_recorder()
        return self.driver.execute_script("return window.__aiwearMessages || [];") or []

    def wait_message(self, keyword: str = "", timeout: float = None) -> str:
        """等待出现包含关键字的 Toast，返回该条文案；超时抛 TimeoutException。

        :param keyword: 关键字；留空表示等待任意一条提示
        """
        timeout = timeout if timeout is not None else self.timeout

        def matched(driver):
            msgs = driver.execute_script("return window.__aiwearMessages || [];") or []
            if not keyword:
                return msgs[0] if msgs else False
            for msg in msgs:
                if keyword in msg:
                    return msg
            return False

        return self._wait(timeout).until(matched)

    def form_errors(self, scope=None) -> list:
        """返回表单校验红字列表（el-form-item__error）。

        :param scope: 可传入某个表单/弹框的定位器，只取该范围内的校验提示
        """
        locator = (By.CSS_SELECTOR, ".el-form-item__error")
        if scope:
            container = self.find(scope)
            return [el.text.strip() for el in container.find_elements(*locator) if el.text.strip()]
        return self.texts_of(locator)

    def form_error_of(self, label: str) -> str:
        """按字段名返回该字段下方的校验红字，如 form_error_of("密码")。

        依赖 el-form-item 的 label 文本，结构：.el-form-item(labels 含字段名) .el-form-item__error
        """
        for item in self.finds((By.CSS_SELECTOR, ".el-form-item")):
            if label in (item.text or ""):
                errors = item.find_elements(By.CSS_SELECTOR, ".el-form-item__error")
                if errors:
                    return errors[0].text.strip()
        return ""

    # ------------------------------------------------------------------
    # 图片预览
    # ------------------------------------------------------------------
    def wait_image_loaded(self, locator, timeout: float = None):
        """等待图片真正下载完成（naturalWidth > 0）。

        Element Plus 的 el-image 在图片下载完成前只渲染占位图，此时点击不会打开预览，
        所以断言预览之前必须先等图片加载完（否则会偶发"点了没反应"）。
        """
        element = self.wait_present(locator)
        self._wait(timeout).until(lambda d: d.execute_script(
            "const img = arguments[0].tagName === 'IMG' ? arguments[0] "
            ": arguments[0].querySelector('img');"
            "return !!img && img.complete && img.naturalWidth > 0;",
            element,
        ))
        return self

    def open_image_viewer(self, locator):
        """点击图片缩略图打开全屏预览。"""
        self.wait_image_loaded(locator)
        self.click(locator)
        return self.wait_visible((By.CSS_SELECTOR, ".el-image-viewer__wrapper"))

    def viewer_title(self) -> str:
        """图片预览大图地址（用于断言预览的是当前图片）。"""
        return self.get_attribute((By.CSS_SELECTOR, ".el-image-viewer__img"), "src")

    def close_image_viewer(self):
        """关闭全屏图片预览。"""
        self.click((By.CSS_SELECTOR, ".el-image-viewer__close"))
        self.wait_invisible((By.CSS_SELECTOR, ".el-image-viewer__wrapper"))
        return self

    # ------------------------------------------------------------------
    # 登录态处理
    # ------------------------------------------------------------------
    def has_token(self) -> bool:
        """当前浏览器 localStorage 中是否存在登录 token。"""
        try:
            token = self.driver.execute_script(
                f"return window.localStorage.getItem('{TOKEN_KEY}');"
            )
            return bool(token)
        except WebDriverException:
            return False

    def current_username(self) -> str:
        """当前浏览器 localStorage 里记录的登录用户名；未登录/读不到返回空串。"""
        try:
            raw = self.driver.execute_script(
                f"return window.localStorage.getItem('{USER_KEY}');"
            )
            return (json.loads(raw) or {}).get("username", "") if raw else ""
        except Exception:
            return ""

    def login_with_token(self, token: str, user: dict = None):
        """注入 token 免登录（R4：绕过验证码，直接进入业务页面）。"""
        self.open("/login")  # 先打开同源页面，才能写 localStorage
        self.driver.execute_script(
            f"window.localStorage.setItem('{TOKEN_KEY}', arguments[0]);", token
        )
        if user:
            self.driver.execute_script(
                f"window.localStorage.setItem('{USER_KEY}', arguments[0]);",
                json.dumps(user, ensure_ascii=False),
            )
        self.open("/edit")
        return self

    def login_with_password(self, account: str, password: str, timeout: float = None):
        """通过 UI 完成"密码登录"（账号不存在时后端会自动注册），返回是否登录成功。"""
        login_tab = (By.CSS_SELECTOR, ".tabs .tab:nth-child(2)")
        username_input = (By.CSS_SELECTOR, "input[placeholder='请输入用户名']")
        password_input = (By.CSS_SELECTOR, "input[placeholder='请输入密码']")
        submit_btn = (By.CSS_SELECTOR, "button.submit")
        # 必须先清登录态：已登录时路由守卫会把 /login 重定向到 /edit，登录表单根本不会出现
        self.clear_auth()
        self.open("/login")
        self.click(login_tab)
        self.input_text(username_input, account)
        self.input_text(password_input, password)
        self.click(submit_btn)
        try:
            return self.wait_url_not_contains("/login", timeout)
        except TimeoutException:
            return False

    def clear_auth(self):
        """清空本地登录态（退出登录 / 构造未登录场景）。只动 localStorage，不做跳转。"""
        try:
            self.driver.execute_script(
                f"window.localStorage.removeItem('{TOKEN_KEY}');"
                f"window.localStorage.removeItem('{USER_KEY}');"
            )
            self.driver.delete_all_cookies()
        except WebDriverException:
            pass  # 浏览器还停在 about:blank 这类没有 localStorage 的页面时忽略
        return self

    def register_temp_user(self, prefix: str = TEMP_ACCOUNT_PREFIX):
        """自动注册一个临时新账号并登录，返回用户名。

        原理：后端 UserServiceImpl.auth() 对「不含 @ 且库里不存在」的用户名会直接 insert，
        所以走一次「密码登录」就等于注册，不需要邮箱验证码。
        新账号的「我的图片」和「历史记录」都是空的，适合空态类用例做数据准备。
        """
        username = f"{prefix}{datetime.now():%m%d%H%M%S}{random.randint(100, 999)}"
        if not self.login_with_password(username, TEMP_ACCOUNT_PASSWORD):
            pytest.skip(f"临时账号 {username} 注册/登录失败，页面提示：{self.messages()}")
        return username

    def ensure_logged_in(self, account: str = None, password: str = None):
        """确保以目标账号登录，供需要登录的用例在 setUp 中调用。

        优先级：AIWEAR_TOKEN（显式指定则必须用 token）> 账号密码（默认 DEMO 账号）。
        浏览器里已经登录了同一个账号时直接复用，避免每个用例都重登一次；
        账号不对（比如上一个用例注册了临时账号）时会重新登录。
        """
        token = os.getenv("AIWEAR_TOKEN", "").strip()
        if token:
            if not self.has_token():
                self.login_with_token(token)
            if "/login" not in self.current_url():
                return self

        account = (account or DEFAULT_ACCOUNT).strip()
        password = (password or DEFAULT_PASSWORD).strip()
        if account and password:
            if self.has_token() and self.current_username() == account:
                return self  # 已是目标账号，直接复用当前会话
            if self.login_with_password(account, password):
                return self

        pytest.skip(
            "未提供可用登录凭据：请设置 AIWEAR_TOKEN，或设置 AIWEAR_ACCOUNT / AIWEAR_PASSWORD"
        )

    # ------------------------------------------------------------------
    # 截图与调试
    # ------------------------------------------------------------------
    def screenshot(self, name: str = "screenshot") -> Path:
        """截图并按 时间_名称.png 保存到 screenshots 目录，返回文件路径。"""
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
        path = SCREENSHOT_DIR / f"{datetime.now():%Y%m%d_%H%M%S}_{safe_name}.png"
        self.driver.save_screenshot(str(path))
        return path

    def describe_page(self) -> str:
        """返回一段便于定位失败的页面摘要：地址 + 当前可见提示。"""
        return f"url={self.current_url()} messages={self.messages()} errors={self.form_errors()}"
