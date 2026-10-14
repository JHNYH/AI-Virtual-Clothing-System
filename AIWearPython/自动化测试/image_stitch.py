# -*- coding: utf-8 -*-
"""
图片合并页面自动化代码（对应 img/图片合并页面.png）

只覆盖思维导图中「功能测试」分支：
    打开编辑图片弹框
        · 没有上传过图片 → 弹框标题「选择图片」，网格中没有图片可选
        · 上传过至少 1 张图片 → 弹框标题「选择图片」，网格展示「我的图片」全部素材
        · 未选图片时点击确认按钮 → 弹出黄色提示「请选择图片」
        · 选择图片后点击确认按钮 → 所选槽位显示所选缩略图，左下角序号角标为对应槽位号
    提交按钮
        · 未选图片时点击提交 → 按钮禁用，点击不了
        · 选择了一张图片，没有选择另一张 → 按钮禁用，点击不了
        · 选好了图片，但没有输入指令 → 按钮禁用，点击不了
        · 选好了两张相同的图片并输入了指令 → 提示「两张图片不能相同」，不发起请求
        · 选好了两张不同的图片并输入了指令 → 提交中…、加载态、合成图与「重置」按钮，
          「历史记录」页新增一条「图片合并」记录
    删除图片：删除其中一张图片，另一张保留
    重置按钮：用户完成一次合并后，点击重置 → 两张图、指令、结果图全部清空，可重新提交

说明：元素与文案取自 fronted/src/views/MergeView.vue 与 components/ImageSelectModal.vue。

运行示例：
    pytest 自动化测试/image_stitch.py -v
"""

from __future__ import annotations

import pytest
from selenium.webdriver.common.by import By

from utils import AI_TIMEOUT, Utils


class ImageStitchPage:
    """图片合并页面对象（页面上叫「图片合并」）。"""

    PATH = "/merge"

    # ---------- 元素定位 ----------
    DEFAULT_IMG = (By.CSS_SELECTOR, ".merge-default-img")
    PAGE_TITLE = (By.CSS_SELECTOR, ".page-title")
    RESULT_TITLE = (By.CSS_SELECTOR, ".page-title-result")
    SLOTS = (By.CSS_SELECTOR, ".merge-slots .merge-image-slot")
    SELECT_BTN_1 = (By.CSS_SELECTOR, ".merge-slots .merge-image-slot:nth-child(1) .merge-select-btn")
    SELECT_BTN_2 = (By.CSS_SELECTOR, ".merge-slots .merge-image-slot:nth-child(2) .merge-select-btn")
    SELECTED_IMG_1 = (By.CSS_SELECTOR, ".merge-slots .merge-image-slot:nth-child(1) .merge-selected-img img")
    SELECTED_IMG_2 = (By.CSS_SELECTOR, ".merge-slots .merge-image-slot:nth-child(2) .merge-selected-img img")
    SLOT_NUM_1 = (By.CSS_SELECTOR, ".merge-slots .merge-image-slot:nth-child(1) .merge-slot-num")
    SLOT_NUM_2 = (By.CSS_SELECTOR, ".merge-slots .merge-image-slot:nth-child(2) .merge-slot-num")
    DELETE_BTN_1 = (By.CSS_SELECTOR, "[aria-label='删除图片1']")
    DELETE_BTN_2 = (By.CSS_SELECTOR, "[aria-label='删除图片2']")
    TEXTAREA = (By.CSS_SELECTOR, ".merge-textarea")
    SUBMIT_BTN = (By.CSS_SELECTOR, ".merge-submit-btn")
    LOADING_MSG = (By.CSS_SELECTOR, ".loading-message")
    RESULT_IMG = (By.CSS_SELECTOR, ".merge-result-img img, .merge-result-img .el-image__inner")

    LOADING_TEXT = "AI计算中..."
    MSG_SAME_IMAGE = "两张图片不能相同"

    def __init__(self, utils: Utils):
        self.u = utils

    # ---------- 打开 ----------
    def open(self):
        """打开图片合并页（需已登录）。"""
        self.u.open(self.PATH)
        self.u.wait_visible(self.SELECT_BTN_1)
        return self

    def title(self) -> str:
        if self.u.is_displayed(self.PAGE_TITLE):
            return self.u.text_of(self.PAGE_TITLE)
        return self.u.text_of(self.RESULT_TITLE)

    # ---------- 选图 ----------
    def open_selector_for_slot(self, slot: int):
        """打开指定槽位（1 或 2）的选图弹框，返回弹框对象。"""
        from image_edit import ImageSelectModal

        btn = self.SELECT_BTN_1 if slot == 1 else self.SELECT_BTN_2
        return ImageSelectModal(self.u).open_with(btn)

    def select_for_slot(self, slot: int, index: int = 0):
        """为指定槽位选择第 index 张素材并确认（弹框为单选，仅影响该槽位）。"""
        modal = self.open_selector_for_slot(slot)
        modal.ensure_has_images(count=index + 1)
        modal.select_by_index(index)
        modal.confirm_and_wait_close()
        return self

    def use_same_image_for_both_slots(self, index: int = 0):
        """两个槽位选同一张图片（用于校验「两张图片不能相同」）。"""
        self.select_for_slot(1, index)
        self.select_for_slot(2, index)
        return self

    # ---------- 操作 ----------
    def input_instruction(self, text: str):
        self.u.input_text(self.TEXTAREA, text)
        return self

    def click_submit(self):
        self.u.clear_messages()
        self.u.click(self.SUBMIT_BTN)
        return self

    def click_reset(self):
        self.u.click((By.XPATH, "//button[contains(@class,'merge-submit-btn')][normalize-space()='重置']"))
        return self

    def delete_slot(self, slot: int):
        """删除指定槽位的已选图片。"""
        self.u.js_click(self.DELETE_BTN_1 if slot == 1 else self.DELETE_BTN_2)
        return self

    def merge(self, slot1_index: int, slot2_index: int, instruction: str):
        """完整流程：选两张不同的图 → 输入指令 → 提交。"""
        self.select_for_slot(1, slot1_index)
        self.select_for_slot(2, slot2_index)
        self.input_instruction(instruction)
        self.click_submit()
        return self

    # ---------- 状态查询 ----------
    def slot_has_image(self, slot: int) -> bool:
        """槽位是否已选图片（占位按钮消失即视为已选）。"""
        btn = self.SELECT_BTN_1 if slot == 1 else self.SELECT_BTN_2
        return not self.u.is_displayed(btn)

    def slot_number(self, slot: int) -> str:
        """槽位左下角序号角标文本（1 / 2）。"""
        return self.u.text_of(self.SLOT_NUM_1 if slot == 1 else self.SLOT_NUM_2)

    def submit_enabled(self) -> bool:
        return self.u.is_enabled(self.SUBMIT_BTN)

    def submit_text(self) -> str:
        return self.u.text_of(self.SUBMIT_BTN)

    def has_result(self) -> bool:
        return self.u.is_displayed(self.RESULT_IMG)

    def wait_result(self, timeout: float = None):
        """等待合并完成：先出现加载态，再出现结果图。"""
        self.u.wait_visible(self.LOADING_MSG, timeout=30)
        self.u.wait_visible(self.RESULT_IMG, timeout=timeout or AI_TIMEOUT)
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
    """已登录的图片合并页。"""
    return ImageStitchPage(logged_utils).open()


class TestImageStitch:
    """打开弹框、提交按钮、删除、重置。"""

    # ---------- 打开编辑图片弹框 ----------
    def test_tc_merge_11_modal_without_images(self, fresh_utils):
        """没有上传过图片 → 弹框标题「选择图片」，网格中没有图片可选（用临时新账号准备）。"""
        page = ImageStitchPage(fresh_utils).open()
        modal = page.open_selector_for_slot(1)
        assert modal.title() == "选择图片"
        assert modal.item_count() == 0, "全新账号的弹框里不应有可选素材"

    def test_tc_merge_01_modal_shows_all_my_images(self, page):
        """上传过至少 1 张图片 → 弹框标题「选择图片」，网格展示「我的图片」全部素材。"""
        from image_edit import ImageSelectModal

        modal = page.open_selector_for_slot(1)
        assert modal.title() == "选择图片"
        assert modal.item_count() > 0, "弹框未展示「我的图片」素材"
        modal.confirm()  # 确认后需要关闭，避免影响后续用例

    def test_tc_merge_02_confirm_without_selection(self, page):
        """未选图片时点击确认 → 弹出黄色提示「请选择图片」。"""
        from image_edit import ImageSelectModal

        modal = page.open_selector_for_slot(1)
        modal.confirm()
        assert ImageSelectModal.MSG_EMPTY_SELECTION in page.u.wait_message(
            ImageSelectModal.MSG_EMPTY_SELECTION
        ), f"未出现「请选择图片」提示，实际：{page.u.messages()}"

    def test_tc_merge_03_selected_image_shows_in_slot(self, page):
        """选择图片后点击确认 → 所选槽位显示所选缩略图，左下角序号角标为对应槽位号。"""
        page.select_for_slot(1, 0)
        assert page.slot_has_image(1), "槽位 1 未显示所选缩略图"
        assert page.u.is_displayed(page.SELECTED_IMG_1)
        assert page.slot_number(1) == "1"
        assert page.u.is_displayed(page.SELECT_BTN_2), "选图 1 不应影响槽位 2"

        page.select_for_slot(2, 0)
        assert page.slot_has_image(2), "槽位 2 未显示所选缩略图"
        assert page.u.is_displayed(page.SELECTED_IMG_2)
        assert page.slot_number(2) == "2"

    # ---------- 提交按钮 ----------
    def test_tc_merge_04_submit_disabled_without_selection(self, page):
        """未选图片时点击提交 → 按钮禁用，点击不了。"""
        assert not page.submit_enabled(), "未选图时提交按钮应禁用"
        page.u.js_click(page.SUBMIT_BTN)  # 强制点击，验证不发起请求
        page.u.wait_stable(1)
        assert not page.has_result(), "未选图时不应产生结果图"

    def test_tc_merge_05_submit_disabled_with_one_image(self, page):
        """选择了一张图片，没有选择另一张 → 提交按钮禁用，点击不了。"""
        page.select_for_slot(1, 0)
        page.input_instruction("给图2的人物换上图1的衣服")
        assert not page.submit_enabled(), "只选一张图时提交按钮应禁用"

    def test_tc_merge_06_submit_disabled_without_instruction(self, page):
        """选好了两张不同的图片，但没有输入指令 → 提交按钮禁用，点击不了。"""
        page.select_for_slot(1, 0)
        page.select_for_slot(2, 0)
        assert not page.submit_enabled(), "未输入指令时提交按钮应禁用"

    def test_tc_merge_07_same_image_rejected(self, page):
        """选好了两张相同的图片并输入指令 → 提示「两张图片不能相同」，不发起请求。"""
        page.use_same_image_for_both_slots(0)
        page.input_instruction("换装")
        assert page.submit_enabled(), "选齐两张图并输入指令后按钮应可点击"
        page.click_submit()
        assert page.MSG_SAME_IMAGE in page.u.wait_message(page.MSG_SAME_IMAGE), \
            f"未出现「两张图片不能相同」提示，实际：{page.u.messages()}"
        assert not page.has_result(), "被拦截时不应产生结果图"

    @pytest.mark.ai
    def test_tc_merge_08_merge_success_and_record_created(self, page):
        """选好两张不同的图片并输入指令提交 → 加载态 → 合成图 + 「重置」，历史记录新增「图片合并」记录。"""
        page.select_for_slot(1, 0)
        page.select_for_slot(2, 1)
        page.input_instruction("给图2的人物换上图1的衣服")
        assert page.submit_enabled(), "选齐两张不同的图并输入指令后提交按钮应可点击"
        page.click_submit()
        assert page.u.wait_text(page.LOADING_MSG, ImageStitchPage.LOADING_TEXT, timeout=30), \
            "提交后未出现「AI计算中...」加载态"
        page.wait_result()
        assert page.title() == "处理结果"
        assert page.submit_text() == "重置", "出图后按钮应变为「重置」"
        assert page.latest_record_type() == "图片合并", "历史记录未新增「图片合并」记录"

    # ---------- 删除图片 ----------
    def test_tc_merge_09_delete_one_slot(self, page):
        """删除其中一张图片，另一张保留。"""
        page.select_for_slot(1, 0)
        page.select_for_slot(2, 0)
        page.delete_slot(1)
        assert page.u.wait_invisible(page.DELETE_BTN_1)
        assert page.u.is_displayed(page.SELECT_BTN_1), "槽位 1 应恢复占位按钮"
        assert page.slot_has_image(2), "槽位 2 的图片不应被一起删除"

    # ---------- 重置按钮 ----------
    @pytest.mark.ai
    def test_tc_merge_10_reset_form(self, page):
        """完成一次合并后点击重置 → 两张图、指令、结果图全部清空，可重新提交。"""
        page.merge(0, 1, "给图2的人物换上图1的衣服")
        page.wait_result()
        page.click_reset()
        assert page.u.wait_invisible(page.RESULT_IMG)
        assert page.u.get_attribute(page.TEXTAREA, "value") == "", "重置后指令未清空"
        assert page.u.is_displayed(page.SELECT_BTN_1) and page.u.is_displayed(page.SELECT_BTN_2), \
            "重置后两个槽位都应恢复占位按钮"
        assert page.title() == "合并2张图片"
        assert not page.submit_enabled()
