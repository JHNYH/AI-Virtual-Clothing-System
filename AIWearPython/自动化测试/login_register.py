# -*- coding: utf-8 -*-
"""
AI 登录/注册页面自动化代码（对应 img/AI登录 注册页面.png）

只覆盖思维导图中「功能测试」分支：
    正常登录/注册
        · 邮箱验证码登录/注册（新用户：正确邮箱 + 验证码 → 提示「验证码已发送，请检查邮箱」，
          注册并登录成功后跳转图片编辑页、顶栏显示用户名；老用户：直接登录成功）
        · 用户名密码登录/注册（正确的用户名和密码 → 登录成功，跳转图片编辑页）
    异常登录/注册
        · 异常验证码：验证码为空 / 正确的邮箱 + 错误的验证码 / 5 分钟有效期内重复发送
        · 异常邮箱：邮箱为空 / 错误的邮箱格式
        · 邮箱和验证码都异常：邮箱为空 + 验证码为空
        · 异常用户名：用户名为空
        · 异常密码：密码为空 / 正确的用户名 + 错误的密码 / 密码长度不足
        · 用户名和密码都异常：用户名为空 + 密码为空

说明：页面元素与提示文案取自 fronted/src/views/LoginView.vue，改动页面时请同步更新本文件。

运行示例：
    pytest 自动化测试/login_register.py -v
    set AIWEAR_EMAIL=you@example.com && set AIWEAR_CODE=123456 && pytest 自动化测试/login_register.py -k code
"""

from __future__ import annotations

import os

import pytest
from selenium.webdriver.common.by import By

from utils import DEFAULT_ACCOUNT, DEFAULT_PASSWORD, Utils


class LoginRegisterPage:
    """登录/注册页面对象：只描述"页面上有什么、能做什么"。"""

    PATH = "/login"

    # ---------- 元素定位 ----------
    CARD = (By.CSS_SELECTOR, ".login-card")
    TAB_CODE = (By.CSS_SELECTOR, ".tabs .tab:nth-child(1)")      # 验证码登录
    TAB_PASSWORD = (By.CSS_SELECTOR, ".tabs .tab:nth-child(2)")  # 密码登录

    EMAIL_INPUT = (By.CSS_SELECTOR, "input[placeholder='请输入邮箱']")
    CODE_INPUT = (By.CSS_SELECTOR, "input[placeholder='请输入验证码']")
    SEND_CODE_BTN = (By.CSS_SELECTOR, ".send-link-suffix")
    USERNAME_INPUT = (By.CSS_SELECTOR, "input[placeholder='请输入用户名']")
    PASSWORD_INPUT = (By.CSS_SELECTOR, "input[placeholder='请输入密码']")
    SUBMIT_BTN = (By.CSS_SELECTOR, "button.submit")

    # ---------- 登录后的顶栏（校验"跳转成功 + 顶栏显示用户名"） ----------
    HEADER_USERNAME = (By.CSS_SELECTOR, ".app-header-username")

    # ---------- 期望文案（与页面实现保持一致） ----------
    MSG_EMAIL_REQUIRED = "请输入邮箱"
    MSG_EMAIL_INVALID = "请输入正确的邮箱"
    MSG_CODE_REQUIRED = "请输入验证码"
    MSG_CODE_SENT = "验证码已发送，请检查邮箱"
    MSG_CODE_RESENT = "验证码尚未过期，请勿重复发送"
    MSG_CODE_INVALID = "验证码不存在或者已经过期"
    MSG_USERNAME_REQUIRED = "请输入用户名"
    MSG_PASSWORD_REQUIRED = "请输入密码"
    MSG_PASSWORD_TOO_SHORT = "密码最少6位"
    MSG_LOGIN_FAILED = "用户名或密码错误"

    def __init__(self, utils: Utils):
        self.u = utils

    # ---------- 打开与切页 ----------
    def open(self):
        """打开登录页。

        必须先清登录态：已登录时路由守卫会把 /login 重定向到 /edit，登录表单根本不会渲染
        （`--reuse-browser` 跑全量用例时，前一个用例的登录态会让这里全部报错）。
        """
        self.u.clear_auth()
        self.u.open(self.PATH)
        self.u.wait_visible(self.CARD)
        return self

    def switch_to_code_login(self):
        """切换到「验证码登录」页签。"""
        self.u.click(self.TAB_CODE)
        self.u.wait_visible(self.EMAIL_INPUT)
        return self

    def switch_to_password_login(self):
        """切换到「密码登录」页签。"""
        self.u.click(self.TAB_PASSWORD)
        self.u.wait_visible(self.USERNAME_INPUT)
        return self

    # ---------- 输入与提交 ----------
    def input_email(self, email: str):
        self.u.input_text(self.EMAIL_INPUT, email)
        return self

    def input_code(self, code: str):
        self.u.input_text(self.CODE_INPUT, code)
        return self

    def input_username(self, username: str):
        self.u.input_text(self.USERNAME_INPUT, username)
        return self

    def input_password(self, password: str):
        self.u.input_text(self.PASSWORD_INPUT, password)
        return self

    def click_send_code(self):
        """点击「获取验证码」。"""
        self.u.clear_messages()
        self.u.click(self.SEND_CODE_BTN)
        return self

    def click_submit(self):
        """点击「登录/注册」。"""
        self.u.clear_messages()
        self.u.click(self.SUBMIT_BTN)
        return self

    def submit_code_login(self, email: str, code: str):
        """一步完成：验证码登录方式下填表并提交。"""
        self.switch_to_code_login()
        self.input_email(email)
        self.input_code(code)
        self.click_submit()
        return self

    def submit_password_login(self, username: str, password: str):
        """一步完成：密码登录方式下填表并提交。"""
        self.switch_to_password_login()
        self.input_username(username)
        self.input_password(password)
        self.click_submit()
        return self

    # ---------- 断言辅助 ----------
    def wait_error_of(self, label: str, expected: str, timeout: float = None) -> str:
        """等待指定字段下方出现期望的校验红字，返回实际文案。"""

        def matched(driver):
            text = self.u.form_error_of(label)
            return text if expected in text else False

        return self.u._wait(timeout).until(matched)

    def login_succeeded(self, timeout: float = None) -> bool:
        """等待跳出登录页（视为登录成功）。"""
        try:
            return self.u.wait_url_not_contains(self.PATH, timeout)
        except Exception:
            return False

    def header_username(self) -> str:
        """登录成功后顶栏展示的用户名。"""
        return self.u.text_of(self.HEADER_USERNAME)


# ===========================================================================
# 用例（仅功能测试）
# ===========================================================================
@pytest.fixture()
def page(utils):
    """登录页页面对象。"""
    return LoginRegisterPage(utils).open()


class TestLoginRegister:
    """正常登录/注册 + 异常登录/注册。"""

    # ---------- 异常登录/注册：异常邮箱 ----------
    def test_tc_login_01_email_empty(self, page):
        """邮箱为空：点击「获取验证码」→ 红字「请输入邮箱」。"""
        page.click_send_code()
        assert page.wait_error_of("邮箱", page.MSG_EMAIL_REQUIRED) == page.MSG_EMAIL_REQUIRED

    def test_tc_login_02_email_invalid_format(self, page):
        """错误的邮箱格式：输入不含 @ 的账号 → 红字「请输入正确的邮箱」。"""
        page.input_email("abc")
        page.click_send_code()
        assert page.wait_error_of("邮箱", page.MSG_EMAIL_INVALID) == page.MSG_EMAIL_INVALID

    # ---------- 异常登录/注册：异常验证码 ----------
    def test_tc_login_03_code_empty(self, page):
        """验证码为空：邮箱已填、验证码留空提交 → 红字「请输入验证码」。"""
        page.input_email("someone@example.com")
        page.click_submit()
        assert page.wait_error_of("验证码", page.MSG_CODE_REQUIRED) == page.MSG_CODE_REQUIRED

    def test_tc_login_04_email_and_code_empty(self, page):
        """邮箱和验证码都异常：两者都留空提交 → 同时出现「请输入邮箱」「请输入验证码」。"""
        page.switch_to_code_login()
        page.click_submit()
        assert page.wait_error_of("邮箱", page.MSG_EMAIL_REQUIRED) == page.MSG_EMAIL_REQUIRED
        assert page.wait_error_of("验证码", page.MSG_CODE_REQUIRED) == page.MSG_CODE_REQUIRED

    def test_tc_login_05_wrong_verification_code(self, page):
        """正确的邮箱 + 错误的验证码 → 提示「验证码不存在或者已经过期」，停留在登录页。"""
        email = os.getenv("AIWEAR_EMAIL", "").strip()
        if not email:
            pytest.skip("未设置 AIWEAR_EMAIL，跳过需真实邮箱的验证码异常用例")
        page.input_email(email)
        page.input_code("000000")
        page.click_submit()
        msg = page.u.wait_message(page.MSG_CODE_INVALID, timeout=30)
        assert page.MSG_CODE_INVALID in msg
        assert page.u.current_path() == page.PATH, "登录失败后应停留在登录页"

    def test_tc_login_06_send_code_and_resend_too_soon(self, page):
        """发送验证码成功；5 分钟有效期内重复发送 → 提示「验证码尚未过期，请勿重复发送」。"""
        email = os.getenv("AIWEAR_EMAIL", "").strip()
        if not email:
            pytest.skip("未设置 AIWEAR_EMAIL，跳过发验证码用例")
        page.input_email(email)
        page.click_send_code()
        assert page.MSG_CODE_SENT in page.u.wait_message(page.MSG_CODE_SENT, timeout=30)
        page.u.click(page.SEND_CODE_BTN)
        assert page.MSG_CODE_RESENT in page.u.wait_message(page.MSG_CODE_RESENT, timeout=30)

    # ---------- 异常登录/注册：异常用户名 / 密码 ----------
    def test_tc_login_07_username_empty(self, page):
        """异常用户名：用户名为空（密码已填）提交 → 红字「请输入用户名」。"""
        page.switch_to_password_login()
        page.input_password("123456")
        page.click_submit()
        assert page.wait_error_of("用户名", page.MSG_USERNAME_REQUIRED) == page.MSG_USERNAME_REQUIRED

    def test_tc_login_08_password_empty(self, page):
        """异常密码：密码为空（用户名已填）提交 → 红字「请输入密码」。"""
        page.switch_to_password_login()
        page.input_username("tester")
        page.click_submit()
        assert page.wait_error_of("密码", page.MSG_PASSWORD_REQUIRED) == page.MSG_PASSWORD_REQUIRED

    def test_tc_login_09_username_and_password_empty(self, page):
        """用户名和密码都异常：两者都留空提交 → 同时出现「请输入用户名」「请输入密码」。"""
        page.switch_to_password_login()
        page.click_submit()
        assert page.wait_error_of("用户名", page.MSG_USERNAME_REQUIRED) == page.MSG_USERNAME_REQUIRED
        assert page.wait_error_of("密码", page.MSG_PASSWORD_REQUIRED) == page.MSG_PASSWORD_REQUIRED

    def test_tc_login_10_password_too_short(self, page):
        """密码长度不足（5 位）→ 红字「密码最少6位」。"""
        page.switch_to_password_login()
        page.input_username("tester")
        page.input_password("12345")
        page.click_submit()
        assert page.wait_error_of("密码", page.MSG_PASSWORD_TOO_SHORT) == page.MSG_PASSWORD_TOO_SHORT

    def test_tc_login_11_password_login_wrong_password(self, page):
        """正确的用户名 + 错误的密码 → 提示「用户名或密码错误」，停留在登录页。"""
        if not DEFAULT_ACCOUNT:
            pytest.skip("未设置 AIWEAR_ACCOUNT，跳过密码错误用例")
        page.submit_password_login(DEFAULT_ACCOUNT, "wrong-password-0001")
        assert page.MSG_LOGIN_FAILED in page.u.wait_message(timeout=30)
        assert page.u.current_path() == page.PATH

    # ---------- 正常登录/注册 ----------
    def test_tc_login_12_code_login_success(self, page):
        """邮箱验证码登录/注册：新用户注册成功 / 老用户直接登录，跳转图片编辑页且顶栏显示用户名。"""
        email = os.getenv("AIWEAR_EMAIL", "").strip()
        code = os.getenv("AIWEAR_CODE", "").strip()
        if not (email and code):
            pytest.skip("未设置 AIWEAR_EMAIL / AIWEAR_CODE，跳过验证码登录成功用例")
        page.submit_code_login(email, code)
        assert page.login_succeeded(timeout=30), f"验证码登录未跳转，页面提示：{page.u.messages()}"
        assert page.u.wait_url_contains("/edit"), "登录成功后应跳转图片编辑页"
        assert page.header_username(), "顶栏未显示用户名"

    def test_tc_login_13_password_login_success(self, page):
        """用户名密码登录/注册：正确的用户名和密码 → 登录成功，跳转图片编辑页。"""
        if not (DEFAULT_ACCOUNT and DEFAULT_PASSWORD):
            pytest.skip("未设置 AIWEAR_ACCOUNT / AIWEAR_PASSWORD，跳过密码登录成功用例")
        page.submit_password_login(DEFAULT_ACCOUNT, DEFAULT_PASSWORD)
        assert page.login_succeeded(timeout=30), f"密码登录未跳转，页面提示：{page.u.messages()}"
        assert page.u.wait_url_contains("/edit")
        assert page.header_username(), "顶栏未显示用户名"
