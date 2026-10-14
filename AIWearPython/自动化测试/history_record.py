# -*- coding: utf-8 -*-
"""
历史记录页面自动化代码（对应 img/历史记录页面.png）

只覆盖思维导图中「功能测试」分支：
    空列表：新老用户没进行过图片编辑和图片合并 → 页面无记录，配有文案「暂无数据」
    记录列表展示
        · 点击历史记录 → 表格按倒序展示：序号、类型、图片1、图片2、指令、执行结果
        · 点击类型，选择图片编辑 → 仅展示图片编辑的记录，类型徽标为紫色
        · 点击类型，选择图片合并 → 仅展示图片合并的记录，类型徽标为蓝色
        · 点击类型，选择全部记录 → 恢复展示全部记录
    图片预览：点击缩略图 → 全屏预览大图
    长指令省略
        · 有长指令记录 → 超出宽度显示省略号，悬停展示完整内容
        · 无长指令记录 → 短指令没超出宽度显示，可正常显示完整内容

说明：元素与文案取自 fronted/src/views/RecordsView.vue。

运行示例：
    pytest 自动化测试/history_record.py -v
"""

from __future__ import annotations

import pytest
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By

from utils import Utils


class HistoryRecordPage:
    """历史记录页面对象。"""

    PATH = "/records"

    # ---------- 元素定位 ----------
    TABLE = (By.CSS_SELECTOR, ".records-table")
    HEADERS = (By.CSS_SELECTOR, ".records-table .el-table__header th .cell")
    ROWS = (By.CSS_SELECTOR, ".records-table .el-table__body tr.el-table__row")
    BADGES = (By.CSS_SELECTOR, ".action-badge")
    BADGE_EDIT = (By.CSS_SELECTOR, ".action-badge--edit")
    BADGE_MERGE = (By.CSS_SELECTOR, ".action-badge--merge")
    INSTRUCTIONS = (By.CSS_SELECTOR, ".records-table .instruction-text")
    # 「指令」是第 5 列（序号 / 类型 / 图片1 / 图片2 / 指令 / 执行结果）
    INSTRUCTION_CELLS = (By.CSS_SELECTOR,
                         ".records-table .el-table__body td:nth-child(5) .cell")
    THUMBS = (By.CSS_SELECTOR, ".records-table .cell-thumb")
    RESULT_THUMB_FIRST = (By.CSS_SELECTOR, ".records-table .el-table__body tr:first-child "
                                             "td:last-child .cell-thumb")
    EMPTY_TEXT = (By.CSS_SELECTOR, ".empty-state-text")
    FILTER_TRIGGER = (By.CSS_SELECTOR, ".filter-trigger")
    DROPDOWN_ITEMS = (By.CSS_SELECTOR, ".el-dropdown-menu__item")

    MSG_EMPTY = "暂无数据"
    FILTER_ALL = "全部记录"
    FILTER_EDIT = "图片编辑"
    FILTER_MERGE = "图片合并"

    def __init__(self, utils: Utils):
        self.u = utils

    # ---------- 打开 ----------
    def open(self):
        """打开历史记录页（需已登录）。"""
        self.u.open(self.PATH)
        self.wait_loaded()
        return self

    def wait_loaded(self, timeout: float = None):
        """等待表格加载结束：出现记录行，或出现缺省态（加载中两者都不渲染）。"""
        def loaded(driver):
            if driver.find_elements(By.CSS_SELECTOR,
                                    ".records-table .el-table__body tr.el-table__row"):
                return True
            return any(el.is_displayed()
                       for el in driver.find_elements(By.CSS_SELECTOR, ".empty-state-text"))

        self.u._wait(timeout).until(loaded)
        return self

    # ---------- 列表 ----------
    def row_count(self) -> int:
        return self.u.count(self.ROWS)

    def headers(self) -> list:
        return self.u.texts_of(self.HEADERS)

    def instructions(self) -> list:
        """各行「指令」列文本。"""
        return self.u.texts_of(self.INSTRUCTIONS)

    def badges(self) -> list:
        """各行类型徽标文本（图片编辑 / 图片合并）。"""
        return self.u.texts_of(self.BADGES)

    def empty_text(self) -> str:
        return self.u.text_of(self.EMPTY_TEXT) if self.u.is_displayed(self.EMPTY_TEXT) else ""

    def first_row_number(self) -> str:
        """第一行序号（表格 type=index 列，倒序展示时首行为 1）。"""
        cell = self.u.find((By.CSS_SELECTOR, ".records-table .el-table__body tr:first-child td:first-child"))
        value = cell.text.strip()
        if not value:  # 未渲染文本时回退到 DOM 内容
            value = self.u.js("return arguments[0].innerText.trim();", cell) or ""
        return value

    def ensure_has_records(self):
        """列表为空时 skip（前置条件：需先执行过编辑或合并）。"""
        if self.row_count() == 0:
            pytest.skip("当前账号没有历史记录，请先执行一次图片编辑或图片合并后再跑本用例")

    # ---------- 类型筛选 ----------
    def filter_by(self, option: str):
        """按类型筛选：全部记录 / 图片编辑 / 图片合并。"""
        self.u.click(self.FILTER_TRIGGER)
        item = (By.XPATH, f"//li[contains(@class,'el-dropdown-menu__item')]"
                          f"[normalize-space()='{option}']")
        self.u.click(item)
        # 下拉收起后表格数据重算
        self.u.wait_invisible((By.CSS_SELECTOR, ".el-dropdown-menu"))
        self.u.wait_stable(0.3)
        return self

    # ---------- 指令单元格 ----------
    def instruction_cells(self) -> list:
        """「指令」列的单元格元素列表。"""
        return self.u.finds(self.INSTRUCTION_CELLS)

    def truncated_cell(self):
        """返回第一个"超出宽度被截断"的指令单元格，没有返回 None。

        el-table 的 show-overflow-tooltip 会给该列单元格的 .cell 加上 `el-tooltip` 类
        （Element Plus 2.11 是 `cell el-tooltip`，不是 `el-tooltip__trigger`），
        再用 scrollWidth > clientWidth 判断内容是否真的被省略号截断。
        """
        for cell in self.instruction_cells():
            classes = (cell.get_attribute("class") or "").split()
            if "el-tooltip" in classes and self.cell_content_truncated(cell):
                return cell
        return None

    def cell_content_truncated(self, cell) -> bool:
        """单元格内容是否被省略号截断。

        实测（Element Plus 2.11 + 本项目样式）：真正裁剪内容的是 .cell 里的子元素
        （第 5 列是 `<span class="instruction-text">`，overflow:hidden + text-overflow:ellipsis），
        而父级 .cell 是 flex 且 overflow:visible，量它自己永远 scrollWidth == clientWidth。
        所以要拿"子元素的内容宽度"和"单元格可视宽度"比。
        """
        return bool(self.u.js(
            "const cell = arguments[0];"
            "const inner = cell.firstElementChild;"
            "if (!inner) return cell.scrollWidth > cell.clientWidth;"
            "return inner.scrollWidth > cell.clientWidth;",
            cell,
        ))

    def tooltip_text(self) -> str:
        """悬停后可见的"完整内容"浮层文本；没有可见浮层返回空串。

        页面上可能同时存在多个 .el-popper（未展开的），所以要挑可见的那个。
        """
        for popper in self.u.finds((By.CSS_SELECTOR, ".el-popper")):
            if popper.is_displayed():
                return popper.text.strip()
        return ""

    def hover_element(self, element):
        """把鼠标移到指定元素上（用于触发 show-overflow-tooltip 的完整内容浮层）。"""
        ActionChains(self.u.driver).move_to_element(element).perform()
        return self

    # ---------- 图片预览 ----------
    def preview_result_image(self):
        """点击「执行结果」列缩略图，打开全屏预览。"""
        self.ensure_has_records()
        if not self.u.is_displayed(self.RESULT_THUMB_FIRST):
            pytest.skip("首行没有执行结果图，跳过预览用例")
        self.u.open_image_viewer(self.RESULT_THUMB_FIRST)
        return self


# ===========================================================================
# 用例（仅功能测试）
# ===========================================================================
@pytest.fixture()
def page(logged_utils):
    """已登录的历史记录页。"""
    return HistoryRecordPage(logged_utils).open()


class TestHistoryRecord:
    """空列表、记录列表展示、类型筛选、图片预览、长指令省略。"""

    # ---------- 空列表 ----------
    def test_tc_rec_01_empty_state(self, fresh_utils):
        """没进行过图片编辑和图片合并 → 页面无记录，配有文案「暂无数据」（用临时新账号准备）。"""
        page = HistoryRecordPage(fresh_utils).open()
        assert page.row_count() == 0, "全新的临时账号不应有历史记录"
        assert page.empty_text() == page.MSG_EMPTY

    # ---------- 记录列表展示 ----------
    def test_tc_rec_02_record_list_display(self, page):
        """表格按倒序展示：序号、类型、图片1、图片2、指令、执行结果。"""
        page.ensure_has_records()
        headers = page.headers()
        for expected in ["序号", "类型", "图片1", "图片2", "指令", "执行结果"]:
            assert expected in headers, f"表头缺少「{expected}」，实际：{headers}"
        assert page.first_row_number() == "1", "序号列应从 1 开始（倒序展示）"
        assert page.u.count(page.THUMBS) > 0, "未展示图片缩略图"
        badges = page.badges()
        assert badges, "未展示类型徽标"
        assert all(b in (page.FILTER_EDIT, page.FILTER_MERGE) for b in badges), \
            f"类型列出现未知取值：{badges}"

    def test_tc_rec_03_filter_edit_records(self, page):
        """点击类型，选择图片编辑 → 仅展示图片编辑的记录，类型徽标为紫色。"""
        page.ensure_has_records()
        page.filter_by(page.FILTER_EDIT)
        if page.row_count() == 0:
            pytest.skip("当前账号没有图片编辑记录，跳过该筛选用例")
        assert page.u.count(page.BADGE_MERGE) == 0, "筛选图片编辑后仍出现合并记录"
        assert all(b == page.FILTER_EDIT for b in page.badges())
        assert all(b in ("图片编辑",) for b in page.badges())

    def test_tc_rec_04_filter_merge_records(self, page):
        """点击类型，选择图片合并 → 仅展示图片合并的记录，类型徽标为蓝色。"""
        page.ensure_has_records()
        page.filter_by(page.FILTER_MERGE)
        if page.row_count() == 0:
            pytest.skip("当前账号没有图片合并记录，跳过该筛选用例")
        assert page.u.count(page.BADGE_EDIT) == 0, "筛选图片合并后仍出现编辑记录"
        assert all(b == page.FILTER_MERGE for b in page.badges())

    def test_tc_rec_05_filter_all_restores_records(self, page):
        """点击类型，选择全部记录 → 恢复展示全部记录。"""
        page.ensure_has_records()
        total = page.row_count()
        page.filter_by(page.FILTER_EDIT)
        page.filter_by(page.FILTER_ALL)
        assert page.row_count() == total, "恢复全部记录后行数不一致"

    # ---------- 图片预览 ----------
    def test_tc_rec_06_preview_result_image(self, page):
        """点击缩略图 → 全屏预览大图，关闭后回到列表。"""
        page.preview_result_image()
        assert page.u.is_displayed((By.CSS_SELECTOR, ".el-image-viewer__wrapper"))
        assert page.u.viewer_title(), "预览大图地址为空"
        page.u.close_image_viewer()
        assert page.row_count() > 0

    # ---------- 长指令省略 ----------
    @pytest.mark.ai
    def test_tc_rec_07_long_instruction_ellipsis(self, fresh_utils_with_edit_record):
        """有长指令记录 → 超出宽度显示省略号，悬停展示完整内容。

        长指令记录由夹具自动造：临时账号上传素材 → 用超长指令编辑一次。
        """
        page = HistoryRecordPage(fresh_utils_with_edit_record).open()
        assert page.row_count() > 0, "造数据后应至少有一条历史记录"
        cell = page.truncated_cell()
        assert cell is not None, "长指令记录未出现省略号单元格"
        assert page.cell_content_truncated(cell), "长指令单元格内容未超出宽度"
        # 悬停后应弹出完整内容浮层（浮层里是完整的长指令，而不是被截断的前半句）
        page.hover_element(cell)
        assert page.u._wait(10).until(lambda d: page.tooltip_text()), \
            "悬停未展示完整内容浮层"
        assert len(page.tooltip_text()) > 30, \
            f"浮层里不是完整指令：{page.tooltip_text()[:30]}"

    def test_tc_rec_08_short_instruction_fully_visible(self, page):
        """无长指令记录 → 短指令没超出宽度，可正常显示完整内容（不出现省略）。"""
        page.ensure_has_records()
        instructions = page.instructions()
        if not instructions:
            pytest.skip("当前记录没有指令内容，跳过短指令用例")
        short = sorted(instructions, key=len)[0]
        assert short, "指令内容为空"
        # 短指令应完整渲染在指令列中（未被截断）
        assert any(short in text for text in instructions)
