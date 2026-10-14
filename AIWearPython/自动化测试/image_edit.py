# -*- coding: utf-8 -*-
"""
图片编辑页面自动化代码（对应 img/图片编辑页面.png）

只覆盖思维导图中「功能测试」分支：
    打开编辑图片弹框
        · 没有上传过图片 → 弹框标题「选择图片」，网格中没有图片可选
        · 上传过至少 1 张图片 → 弹框标题「选择图片」，网格展示「我的图片」全部素材
        · 未选图片时点击确认按钮 → 弹出黄色提示「请选择图片」
        · 选择图片后点击确认按钮 → 选中的图片出现在图片的位置
    提交按钮
        · 未选图片时点击提交 → 按钮禁用，点击不了
        · 选好了图片，但没有输入指令 → 按钮禁用，点击不了
        · 选好了图片，并且输入了指令 → 提交按钮变为「提交中…」并展示加载态，
          随后展示结果图与「重置」按钮，「历史记录」页新增一条「图片编辑」记录
    删除图片：点击缩略图右上角删除按钮 → 缩略图消失，恢复为「+ 图片」占位按钮
    重置按钮：用户完成一次编辑后，点击重置 → 结果图、指令、已选图片全部清空，可重新提交

说明：元素与文案取自 fronted/src/views/EditView.vue 与 components/ImageSelectModal.vue。

运行示例：
    pytest 自动化测试/image_edit.py -v
"""

from __future__ import annotations

import pytest
from selenium.webdriver.common.by import By

from utils import AI_TIMEOUT, Utils


class ImageSelectModal:
    """「选择图片」弹框页面对象（编辑页与合并页共用）。"""

    DIALOG = (By.CSS_SELECTOR, ".el-dialog.image-select-dialog")
    TITLE = (By.CSS_SELECTOR, ".image-select-title")
    GRID = (By.CSS_SELECTOR, ".image-select-grid")
    ITEMS = (By.CSS_SELECTOR, ".image-select-item")
    ITEM_SELECTED = (By.CSS_SELECTOR, ".image-select-item.is-selected")
    CONFIRM_BTN = (By.CSS_SELECTOR, ".image-select-confirm-btn")

    MSG_EMPTY_SELECTION = "请选择图片"

    def __init__(self, utils: Utils):
        self.u = utils

    def wait_open(self):
        """等待弹框已打开（已点过触发按钮时用）。"""
        self.u.wait_visible(self.DIALOG)
        self.u.wait_visible(self.TITLE)
        return self

    def open_with(self, trigger_locator):
        """点击触发按钮并等待弹框打开（首次点击可能被吞掉，内部会重试）。"""
        self.u.click_until(trigger_locator, self.DIALOG)
        self.u.wait_visible(self.TITLE)
        return self

    def title(self) -> str:
        return self.u.text_of(self.TITLE)

    def item_count(self) -> int:
        """网格中可选素材数量（对应"网格展示我的图片全部素材"）。"""
        return self.u.count(self.ITEMS)

    def select_by_index(self, index: int = 0):
        """选择第 index 张图片（0 开始）。"""
        self.u.click((By.CSS_SELECTOR, f".image-select-item:nth-child({index + 1})"))
        return self

    def selected_count(self) -> int:
        return self.u.count(self.ITEM_SELECTED)

    def confirm(self):
        """点击「确认」。"""
        self.u.clear_messages()
        self.u.click(self.CONFIRM_BTN)
        return self

    def confirm_and_wait_close(self):
        self.confirm()
        self.u.wait_invisible(self.DIALOG)
        return self

    def ensure_has_images(self, count: int = 1):
        """弹框内至少有 count 张素材，否则 skip（前置条件不满足）。"""
        if self.item_count() < count:
            pytest.skip(f"「我的图片」中素材不足 {count} 张，请先上传图片后再跑本用例")


class ImageEditPage:
    """图片编辑页面对象。"""

    PATH = "/edit"

    # ---------- 元素定位 ----------
    DEFAULT_IMG = (By.CSS_SELECTOR, ".edit-default-img")
    PAGE_TITLE = (By.CSS_SELECTOR, ".page-title")
    RESULT_TITLE = (By.CSS_SELECTOR, ".page-title-result")
    SELECT_BTN = (By.CSS_SELECTOR, ".edit-select-btn")
    SELECT_LABEL = (By.CSS_SELECTOR, ".edit-select-label")
    SELECTED_IMG = (By.CSS_SELECTOR, ".edit-selected-img img, .edit-selected-img .el-image__inner")
    DELETE_BTN = (By.CSS_SELECTOR, ".edit-delete-btn")
    TEXTAREA = (By.CSS_SELECTOR, ".edit-textarea")
    SUBMIT_BTN = (By.CSS_SELECTOR, ".edit-submit-btn")
    LOADING_MSG = (By.CSS_SELECTOR, ".loading-message")
    RESULT_IMG = (By.CSS_SELECTOR, ".edit-result-img img, .edit-result-img .el-image__inner")

    LOADING_TEXT = "AI计算中..."

    def __init__(self, utils: Utils):
        self.u = utils
        self.modal = ImageSelectModal(utils)

    # ---------- 打开 ----------
    def open(self):
        """打开图片编辑页（需已登录）。"""
        self.u.open(self.PATH)
        self.u.wait_visible(self.SELECT_BTN)
        return self

    def title(self) -> str:
        """当前页面主标题（占位态为「单张图片编辑」，有结果时为「处理结果」）。"""
        if self.u.is_displayed(self.PAGE_TITLE):
            return self.u.text_of(self.PAGE_TITLE)
        return self.u.text_of(self.RESULT_TITLE)

    # ---------- 交互 ----------
    def open_selector(self, ensure_has_images: bool = True):
        """点击「+ 图片」打开选择图片弹框，返回弹框对象。"""
        self.modal.open_with(self.SELECT_BTN)
        if ensure_has_images:
            self.modal.ensure_has_images()
        return self.modal

    def select_image(self, index: int = 0):
        """选择第 index 张素材并确认，返回本页对象。"""
        modal = self.open_selector()
        modal.select_by_index(index)
        modal.confirm_and_wait_close()
        return self

    def input_instruction(self, text: str):
        """输入编辑指令。"""
        self.u.input_text(self.TEXTAREA, text)
        return self

    def click_submit(self):
        """点击「提交」。"""
        self.u.clear_messages()
        self.u.click(self.SUBMIT_BTN)
        return self

    def click_delete(self):
        """点击已选缩略图右上角的删除按钮。"""
        self.u.js_click(self.DELETE_BTN)
        return self

    def click_reset(self):
        """点击「重置」。"""
        self.u.click((By.XPATH, "//button[contains(@class,'edit-submit-btn')][normalize-space()='重置']"))
        return self

    # ---------- 状态查询 ----------
    def has_selected_image(self) -> bool:
        """图片槽中是否已选图片（占位按钮消失即视为已选）。"""
        return not self.u.is_displayed(self.SELECT_BTN)

    def submit_enabled(self) -> bool:
        """「提交」按钮是否可点击。"""
        return self.u.is_enabled(self.SUBMIT_BTN)

    def submit_text(self) -> str:
        return self.u.text_of(self.SUBMIT_BTN)

    def has_result(self) -> bool:
        """是否已生成结果图（此时按钮变为「重置」）。"""
        return self.u.is_displayed(self.RESULT_IMG)

    def wait_result(self, timeout: float = None):
        """等待 AI 出图完成（先出现加载态，再出现结果图）。"""
        self.u.wait_visible(self.LOADING_MSG, timeout=30)
        self.u.wait_visible(self.RESULT_IMG, timeout=timeout or AI_TIMEOUT)
        return self

    def edit(self, index: int, instruction: str):
        """完整流程：选图 → 输入指令 → 提交。"""
        self.select_image(index)
        self.input_instruction(instruction)
        self.click_submit()
        return self

    # ---------- 历史记录联动 ----------
    def latest_record_type(self) -> str:
        """跳到历史记录页，返回最新一条记录的类型徽标文案。"""
        self.u.open("/records")
        badges = (By.CSS_SELECTOR, ".records-table .action-badge")
        self.u.wait_visible(badges)
        return self.u.find(badges).text.strip()


# ===========================================================================
# 用例（仅功能测试）
# ===========================================================================
@pytest.fixture()
def page(logged_utils):
    """已登录的图片编辑页。"""
    return ImageEditPage(logged_utils).open()


class TestImageEdit:
    """打开弹框、提交按钮、删除、重置。"""

    # ---------- 打开编辑图片弹框 ----------
    def test_tc_edit_01_modal_without_images(self, fresh_utils):
        """没有上传过图片 → 弹框标题「选择图片」，网格中没有图片可选（用临时新账号准备）。"""
        page = ImageEditPage(fresh_utils).open()
        modal = page.open_selector(ensure_has_images=False)
        assert modal.title() == "选择图片"
        assert modal.item_count() == 0, "全新账号的弹框里不应有可选素材"
        assert page.u.is_displayed(modal.GRID), "无素材时应展示空网格"

    def test_tc_edit_02_modal_shows_all_my_images(self, page):
        """上传过至少 1 张图片 → 弹框标题「选择图片」，网格展示「我的图片」全部素材。"""
        modal = page.open_selector(ensure_has_images=True)
        assert modal.title() == "选择图片"
        assert modal.item_count() > 0, "弹框未展示「我的图片」素材"

    def test_tc_edit_03_confirm_without_selection(self, page):
        """未选图片时点击确认 → 弹出黄色提示「请选择图片」，弹框保持打开。"""
        modal = page.open_selector(ensure_has_images=False)
        modal.confirm()
        assert ImageSelectModal.MSG_EMPTY_SELECTION in page.u.wait_message(
            ImageSelectModal.MSG_EMPTY_SELECTION
        ), f"未出现「请选择图片」提示，实际：{page.u.messages()}"
        assert page.u.is_displayed(modal.DIALOG), "校验不通过时弹框应保持打开"

    def test_tc_edit_04_confirm_selected_image(self, page):
        """选择图片后点击确认 → 选中的图片出现在图片的位置，弹框关闭。"""
        modal = page.open_selector()
        modal.select_by_index(0)
        assert modal.selected_count() == 1, "单选模式下应只有一张被选中"
        modal.confirm_and_wait_close()
        assert page.has_selected_image(), "确认后图片槽未展示所选图片"
        assert page.u.is_displayed(page.SELECTED_IMG), "缩略图未渲染"

    # ---------- 提交按钮 ----------
    def test_tc_edit_05_submit_disabled_without_selection(self, page):
        """未选图片时点击提交 → 按钮禁用（鼠标悬停为红色禁止符号），点击不了。"""
        assert not page.submit_enabled(), "未选图时提交按钮应禁用"
        page.u.js_click(page.SUBMIT_BTN)  # 强制点击，验证不会产生任何结果
        page.u.wait_stable(1)
        assert not page.has_result(), "未选图时不应产生结果图"

    def test_tc_edit_06_submit_disabled_without_instruction(self, page):
        """选好了图片但没有输入指令 → 按钮仍禁用，点击不了。"""
        page.select_image()
        assert page.has_selected_image(), "确认后图片槽应展示缩略图"
        assert not page.submit_enabled(), "未输入指令时提交按钮应禁用"

    @pytest.mark.ai
    def test_tc_edit_07_edit_success_and_record_created(self, page):
        """选好图片并输入指令提交 → 加载态 → 结果图 + 「重置」，历史记录新增「图片编辑」记录。"""
        page.select_image()
        page.input_instruction("把人物的上衣换成粉色的")
        assert page.submit_enabled(), "选图并输入指令后提交按钮应可点击"
        page.click_submit()
        assert page.u.wait_text(page.LOADING_MSG, ImageEditPage.LOADING_TEXT, timeout=30), \
            "提交后未出现「AI计算中...」加载态"
        page.wait_result()
        assert page.title() == "处理结果"
        assert page.submit_text() == "重置", "出图后按钮应变为「重置」"
        assert page.latest_record_type() == "图片编辑", "历史记录未新增「图片编辑」记录"

    # ---------- 删除图片 ----------
    def test_tc_edit_08_delete_selected_image(self, page):
        """点击缩略图右上角删除按钮 → 缩略图消失，恢复为「+ 图片」占位按钮。"""
        page.select_image()
        assert page.has_selected_image()
        page.click_delete()
        assert page.u.wait_invisible(page.DELETE_BTN)
        assert page.u.is_displayed(page.SELECT_BTN), "删除后应恢复「+ 图片」占位按钮"

    # ---------- 重置按钮 ----------
    def test_tc_edit_09_reset_form(self, page):
        """完成一次编辑后点击重置 → 结果图、指令、已选图片全部清空，恢复初始状态可重新提交。"""
        page.edit(0, "把背景换成纯白色")
        page.wait_result()
        page.click_reset()
        assert page.u.wait_invisible(page.RESULT_IMG)
        assert page.u.get_attribute(page.TEXTAREA, "value") == "", "重置后指令未清空"
        assert page.u.is_displayed(page.SELECT_BTN), "重置后应恢复占位按钮"
        assert page.title() == "单张图片编辑"
        assert not page.submit_enabled(), "重置后提交按钮应恢复禁用态"
