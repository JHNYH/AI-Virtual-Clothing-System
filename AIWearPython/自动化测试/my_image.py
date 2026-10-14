# -*- coding: utf-8 -*-
"""
我的图片页面自动化代码（对应 img/我的图片页面.png）

只覆盖思维导图中「功能测试」分支：
    上传图片
        · 上传人物/人像 → 「上传中…」，成功后列表刷新出现该图片，文件名不含后缀
        · 上传衣物/服装图 → 同上
        · 上传其它图片 → 提示「图片审核不通过！」，列表不新增
        · 上传超过 50MB 的图片 → 提示「图片大小超过限制」，列表不新增
        · 上传非图片文件 → 提示「仅支持图片上传」，列表不新增
    空列表：新老用户没上传图片 → 我的图片页面无图片素材，配有文案「暂无图片，快去上传吧~」
    列表至少有一张图片 → 图片预览：点击图片缩略图全屏预览大图
    文搜图
        · 点击文搜图 → 无素材时配有文案「找找看，这里有你的素材~」
        · 文搜空输入 → 搜索按钮置灰，点击不了
        · 文搜无结果 → 提示「暂无相关数据」，列表不刷新出新图片
        · 文搜有结果 → 返回同类衣物素材（仅当前用户自己的素材）
    图搜图
        · 点击图搜图 → 无素材时配有文案「找找看，这里有你的素材~」
        · 图搜空输入 → 搜索按钮置灰，点击不了
        · 图搜无结果 → 提示「暂无相关数据」
        · 图搜有结果 → 展示「已选图片」缩略图 + 横条 + 「相似图片」网格
    我的图片中无素材时，文搜图/图搜图点击搜索 → 提示「暂无相关数据」

说明：元素与文案取自 fronted/src/views/ImagesView.vue。

运行示例：
    pytest 自动化测试/my_image.py -v
    set AIWEAR_SEARCH_QUERY=红色连衣裙 && pytest 自动化测试/my_image.py -k search
"""

from __future__ import annotations

import os
import re

import pytest
from selenium.webdriver.common.by import By

from utils import Utils

#: 图片后缀正则，用于校验"列表文件名不含后缀"
IMAGE_EXT_RE = re.compile(r"\.(png|jpg|jpeg|gif|webp|svg|bmp|ico)$", re.I)


class MyImagePage:
    """「我的图片」页面对象（含文搜图、图搜图两个页签）。"""

    PATH = "/images"

    # ---------- 页签 ----------
    TAB_MY_IMAGES = (By.CSS_SELECTOR, ".main-tabs .main-tab:nth-child(1)")
    TAB_TEXT_SEARCH = (By.CSS_SELECTOR, ".main-tabs .main-tab:nth-child(2)")
    TAB_IMAGE_SEARCH = (By.CSS_SELECTOR, ".main-tabs .main-tab:nth-child(3)")

    # ---------- 通用 ----------
    # 三个页签的内容区都在 DOM 里（v-show 切换），查列表必须限定在当前页签的内容区，
    # 否则「我的图片」的素材会被算进文搜图/图搜图的结果里。
    CONTENT_MY_IMAGES = (By.CSS_SELECTOR, ".tab-content-images")
    CONTENT_TEXT_SEARCH = (By.XPATH, "(//div[contains(@class,'tab-content-images')])[2]")
    CONTENT_IMAGE_SEARCH = (By.XPATH, "(//div[contains(@class,'tab-content-images')])[3]")
    GRID_ITEMS = (By.CSS_SELECTOR, ".grid .item")
    ITEM_NAMES = (By.CSS_SELECTOR, ".item-name-text")
    EMPTY_TEXT = (By.CSS_SELECTOR, ".empty-state-text")
    SEARCH_RESULT_TITLE = (By.CSS_SELECTOR, ".image-search-result-title")

    # ---------- 上传 ----------
    UPLOAD_BTN = (By.CSS_SELECTOR, ".upload-top-btn")
    # 上传/图搜图共用一个隐藏 input：同一时刻只渲染其中一个（随页签切换），故用同一选择器
    UPLOAD_INPUT = (By.CSS_SELECTOR, ".main-tabs input[type='file']")

    # ---------- 文搜图 ----------
    TEXT_SEARCH_INPUT = (By.CSS_SELECTOR, ".text-search-input input")
    TEXT_SEARCH_BTN = (By.CSS_SELECTOR, ".text-search-btn")

    # ---------- 图搜图 ----------
    IMAGE_SEARCH_INPUT = (By.CSS_SELECTOR, ".main-tabs input[type='file']")
    IMAGE_SEARCH_SELECT = (By.CSS_SELECTOR, ".image-search-select-wrap")
    IMAGE_SEARCH_BTN = (By.CSS_SELECTOR, ".image-search-btn")
    IMAGE_SEARCH_DIVIDER = (By.CSS_SELECTOR, ".image-search-divider")
    IMAGE_SEARCH_SELECTED_IMG = (By.CSS_SELECTOR, ".image-search-selected-img img, "
                                                   ".image-search-selected-img .el-image__inner")

    MSG_EMPTY_LIST = "暂无图片，快去上传吧~"
    MSG_SEARCH_EMPTY = "找找看，这里有你的素材~"
    MSG_NO_RESULT = "暂无相关数据"
    MSG_TOO_LARGE = "图片大小超过限制"
    MSG_ONLY_IMAGE = "仅支持图片上传"
    MSG_REVIEW_REJECT = "图片审核不通过"

    def __init__(self, utils: Utils):
        self.u = utils
        #: 当前页签，决定列表/结果查询落在哪个内容区
        self._tab = "images"

    # ---------- 打开与切页 ----------
    def open(self):
        """打开「我的图片」页（需已登录）。"""
        self.u.open(self.PATH)
        self.u.wait_visible(self.UPLOAD_BTN)
        return self.goto_tab("images")

    def goto_tab(self, tab: str):
        """切换页签：images | text | image。"""
        locator = {
            "images": self.TAB_MY_IMAGES,
            "text": self.TAB_TEXT_SEARCH,
            "image": self.TAB_IMAGE_SEARCH,
        }[tab]
        self.u.click(locator)
        self._tab = tab
        self.wait_list_loaded()
        return self

    def content_locator(self):
        """当前页签内容区的定位器。"""
        return {
            "images": self.CONTENT_MY_IMAGES,
            "text": self.CONTENT_TEXT_SEARCH,
            "image": self.CONTENT_IMAGE_SEARCH,
        }[self._tab]

    def content(self):
        """当前页签的内容区元素。"""
        return self.u.wait_present(self.content_locator())

    # ---------- 列表 ----------
    def item_count(self) -> int:
        """当前页签内容区里的素材/结果数量。"""
        return len(self.content().find_elements(*self.GRID_ITEMS))

    def item_names(self) -> list:
        return [el.text.strip() for el in self.content().find_elements(*self.ITEM_NAMES)
                if el.text.strip()]

    def empty_text(self) -> str:
        """当前页签下可见的缺省态文案；无缺省态时返回空串。"""
        for element in self.content().find_elements(*self.EMPTY_TEXT):
            if element.is_displayed():
                return element.text.strip()
        return ""

    def wait_list_loaded(self, timeout: float = None):
        """等待列表加载结束。

        列表加载中（isMyImagesLoading）时素材和缺省态都不会渲染，
        直接断言会读到空字符串，所以必须先等"出素材"或"出缺省态"。
        """
        content = self.content()

        def loaded(driver):
            if content.find_elements(*self.GRID_ITEMS):
                return True
            return any(el.is_displayed() for el in content.find_elements(*self.EMPTY_TEXT))

        self.u._wait(timeout).until(loaded)
        return self

    def wait_count_changed(self, origin: int, timeout: float = None):
        """等待当前页签的素材数量相对 origin 发生变化（上传成功后列表刷新）。"""
        self.u._wait(timeout).until(lambda driver: self.item_count() != origin)
        return self

    def ensure_has_images(self):
        """列表至少有一张图片，否则 skip。"""
        if self.item_count() == 0:
            pytest.skip("当前账号素材为空，请先上传图片后再跑本用例")

    # ---------- 上传 ----------
    def upload(self, file_path):
        """向隐藏的 file input 发送文件路径完成上传。"""
        self.u.clear_messages()
        self.u.upload_file(self.UPLOAD_INPUT, file_path)
        return self

    def upload_image(self, keyword: str = None):
        """上传一张素材图片。

        不指定关键字时取服装/人像这类业务图片——素材目录里可能混有汽车/风景图，
        按文件名取第一张会随机踩到"审核不通过"的图。
        """
        image = self.u.sample_image(keyword) if keyword else self.u.sample_clothing_image()
        return self.upload(image)

    def allow_any_file(self):
        """去掉 accept="image/*"，用于构造「上传非图片文件」的异常用例。"""
        self.u.allow_any_file(self.UPLOAD_INPUT)
        return self

    def upload_text(self) -> str:
        """上传按钮当前文案（上传中… / 上传图片）。"""
        return self.u.text_of(self.UPLOAD_BTN)

    # ---------- 文搜图 ----------
    def input_search_query(self, query: str):
        self.u.input_text(self.TEXT_SEARCH_INPUT, query)
        return self

    def click_text_search(self):
        """点击文搜图「搜索」。"""
        self.u.clear_messages()
        self.u.click(self.TEXT_SEARCH_BTN)
        return self

    def text_search(self, query: str):
        """完整文搜图流程。"""
        self.goto_tab("text")
        self.u.wait_present(self.TEXT_SEARCH_INPUT)
        self.input_search_query(query)
        self.click_text_search()
        self.wait_search_result()
        return self

    def text_search_enabled(self) -> bool:
        return self.u.is_enabled(self.TEXT_SEARCH_BTN)

    # ---------- 图搜图 ----------
    def select_search_image(self, file_path):
        """图搜图：给隐藏 input 发送文件路径。"""
        self.goto_tab("image")
        self.u.wait_present(self.IMAGE_SEARCH_SELECT)
        self.u.upload_file(self.IMAGE_SEARCH_INPUT, file_path)
        return self

    def has_selected_search_image(self) -> bool:
        """是否已展示「已选图片」缩略图。"""
        return self.u.is_displayed(self.IMAGE_SEARCH_SELECTED_IMG)

    def click_image_search(self):
        """点击图搜图「搜索」。"""
        self.u.clear_messages()
        self.u.click(self.IMAGE_SEARCH_BTN)
        return self

    def image_search(self, file_path):
        """完整图搜图流程。"""
        self.select_search_image(file_path)
        self.click_image_search()
        self.wait_search_result()
        return self

    def image_search_enabled(self) -> bool:
        return self.u.is_enabled(self.IMAGE_SEARCH_BTN)

    # ---------- 通用等待 ----------
    def wait_search_result(self, timeout: float = 120):
        """等待检索真正结束：当前页签出现结果网格，或出现提示文案（如「暂无相关数据」）。

        不能用"按钮文案恢复为搜索"来判断——点击后 Vue 还没把文案改成"搜索中…"时，
        这个条件会立刻成立，导致在请求发出前就开始断言。
        """
        content = self.content()

        def finished(driver):
            if content.find_elements(*self.GRID_ITEMS):
                return True
            return bool(driver.execute_script("return window.__aiwearMessages || [];"))

        self.u._wait(timeout).until(finished)
        return self

    def preview_first_image(self):
        """点击第一张缩略图，打开全屏预览。"""
        self.ensure_has_images()
        self.u.open_image_viewer((By.CSS_SELECTOR, ".tab-content-images .grid .item:first-child .item-img"))
        return self


# ===========================================================================
# 用例（仅功能测试）
# ===========================================================================
@pytest.fixture()
def page(logged_utils):
    """已登录的「我的图片」页。"""
    return MyImagePage(logged_utils).open()


class TestMyImage:
    """上传图片、空列表、图片预览、文搜图、图搜图。"""

    # ---------- 上传图片 ----------
    @pytest.mark.ai
    def test_tc_img_01_upload_person_image(self, page):
        """上传人物/人像 → 按钮显示「上传中…」，成功后列表刷新出现该图片，文件名不含后缀。"""
        before = page.item_count()
        page.upload(page.u.sample_person_image())
        assert page.wait_count_changed(before, timeout=180), \
            f"上传后列表未刷新（上传前 {before} 张），提示：{page.u.messages()}"
        names = page.item_names()
        assert names, "列表未展示文件名"
        assert not any(IMAGE_EXT_RE.search(name) for name in names), f"文件名不应带后缀：{names}"

    @pytest.mark.ai
    def test_tc_img_02_upload_clothing_image(self, page):
        """上传衣物/服装图 → 上传成功，列表刷新（列表顶部出现该图片）。"""
        before = page.item_count()
        page.upload(page.u.sample_clothing_image())
        assert page.wait_count_changed(before, timeout=180), \
            f"上传后列表未刷新（上传前 {before} 张），提示：{page.u.messages()}"

    @pytest.mark.ai
    def test_tc_img_03_upload_non_business_image_rejected(self, page):
        """上传其它图片（如汽车、风景）→ 提示「图片审核不通过！」，列表不新增。"""
        rejected = page.u.sample_non_business_image()
        if not rejected:
            pytest.skip(
                "素材目录里没有非业务图片（汽车/风景）：设置 AIWEAR_REJECT_IMAGE，"
                "或放一张文件名含「汽车/风景」的图片到素材目录"
            )
        before = page.item_count()
        page.upload(rejected)
        assert page.MSG_REVIEW_REJECT in page.u.wait_message(timeout=120), \
            f"未出现审核不通过提示，实际：{page.u.messages()}"
        assert page.item_count() == before, "审核不通过的图片不应进入列表"

    def test_tc_img_04_upload_oversized_file_rejected(self, page):
        """上传超过 50MB 的图片 → 提示「图片大小超过限制」，列表不新增。"""
        before = page.item_count()
        page.upload(page.u.oversized_file(51))
        assert page.MSG_TOO_LARGE in page.u.wait_message(page.MSG_TOO_LARGE, timeout=15), \
            f"未出现超限提示，实际：{page.u.messages()}"
        assert page.item_count() == before, "超限文件不应写入列表"

    def test_tc_img_05_upload_non_image_rejected(self, page):
        """上传非图片文件 → 提示「仅支持图片上传」，列表不新增。"""
        before = page.item_count()
        page.allow_any_file()
        page.upload(page.u.sample_non_image())
        assert page.u.wait_message("", timeout=30), "上传非图片文件后没有任何提示"
        assert page.MSG_ONLY_IMAGE in "".join(page.u.messages()), \
            f"未出现「仅支持图片上传」提示，实际：{page.u.messages()}"
        assert page.item_count() == before

    # ---------- 空列表 ----------
    def test_tc_img_06_empty_list_state(self, fresh_utils):
        """新注册用户没上传图片 → 无图片素材，配有文案「暂无图片，快去上传吧~」。

        用临时新账号自动准备"没有素材"的前置条件，不再依赖手工造新账号。
        """
        page = MyImagePage(fresh_utils).open()
        assert page.item_count() == 0, "全新的临时账号不应有素材"
        assert page.empty_text() == page.MSG_EMPTY_LIST

    # ---------- 图片预览 ----------
    def test_tc_img_07_image_preview(self, page):
        """列表至少有一张图片 → 点击图片缩略图全屏预览大图，可关闭回到列表。"""
        page.preview_first_image()
        assert page.u.is_displayed((By.CSS_SELECTOR, ".el-image-viewer__wrapper"))
        assert page.u.viewer_title(), "预览大图地址为空"
        page.u.close_image_viewer()
        assert page.item_count() > 0

    # ---------- 文搜图 ----------
    def test_tc_img_08_text_search_empty_input(self, page):
        """文搜图空输入 → 「搜索」按钮置灰，点击不了。"""
        page.goto_tab("text")
        page.u.wait_present(page.TEXT_SEARCH_INPUT)
        assert not page.text_search_enabled(), "空输入时搜索按钮应禁用"

    @pytest.mark.ai
    def test_tc_img_09_text_search_with_result(self, page):
        """文搜图有结果 → 返回同类素材并刷新列表（仅当前用户自己的素材）。"""
        page.ensure_has_images()
        query = os.getenv("AIWEAR_SEARCH_QUERY", "").strip() or "衣服"
        page.text_search(query)
        results = page.item_count()
        if results > 0:
            assert page.item_names(), "命中结果未展示素材名称"
            assert not any(IMAGE_EXT_RE.search(name) for name in page.item_names())
        else:
            assert page.MSG_NO_RESULT in "".join(page.u.messages()), \
                f"无结果时未提示「暂无相关数据」：{page.u.messages()}"
            assert page.empty_text() == page.MSG_SEARCH_EMPTY

    @pytest.mark.ai
    def test_tc_img_10_text_search_no_result(self, page):
        """文搜图无结果 → 提示「暂无相关数据」，列表不刷新出新图片。"""
        page.ensure_has_images()
        page.text_search("自动化测试绝对搜不到的词ZZZ999")
        assert page.MSG_NO_RESULT in "".join(page.u.messages()), \
            f"未提示「暂无相关数据」，实际：{page.u.messages()}"
        assert page.item_count() == 0, "无结果时不应展示任何素材"
        assert page.empty_text() == page.MSG_SEARCH_EMPTY

    @pytest.mark.ai
    def test_tc_img_11_text_search_without_material(self, fresh_utils):
        """文搜图页签下无素材 → 配有文案「找找看，这里有你的素材~」；点击搜索提示「暂无相关数据」。"""
        page = MyImagePage(fresh_utils).open()
        page.goto_tab("text")
        page.u.wait_present(page.TEXT_SEARCH_INPUT)
        assert page.item_count() == 0, "全新的临时账号不应有素材"
        assert page.empty_text() == page.MSG_SEARCH_EMPTY
        page.input_search_query("衣服")
        page.click_text_search()
        page.wait_search_result()
        assert page.MSG_NO_RESULT in "".join(page.u.messages())

    # ---------- 图搜图 ----------
    def test_tc_img_12_image_search_empty_input(self, page):
        """图搜图空输入 → 「搜索」按钮置灰，点击不了。"""
        page.goto_tab("image")
        assert not page.image_search_enabled(), "未选图时搜索按钮应禁用"

    @pytest.mark.ai
    def test_tc_img_13_image_search_with_result(self, page):
        """图搜图有结果 → 展示「已选图片」缩略图 + 横条 + 「相似图片」网格。"""
        page.ensure_has_images()
        page.image_search(page.u.sample_clothing_image())
        assert page.has_selected_search_image(), "未展示「已选图片」缩略图"
        if page.item_count() > 0:
            assert page.u.is_displayed(page.IMAGE_SEARCH_DIVIDER), "未展示结果区横条"
            assert page.u.is_displayed(page.SEARCH_RESULT_TITLE), "未展示「相似图片」标题"
            assert page.u.text_of(page.SEARCH_RESULT_TITLE) == "相似图片"
        else:
            assert page.MSG_NO_RESULT in "".join(page.u.messages())

    @pytest.mark.ai
    def test_tc_img_14_image_search_no_result(self, page):
        """图搜图无结果（传入非衣物/人物图）→ 提示「暂无相关数据」。"""
        landscape = page.u.sample_non_business_image("AIWEAR_LANDSCAPE_IMAGE")
        if not landscape:
            pytest.skip(
                "素材目录里没有非衣物/人物图片：设置 AIWEAR_LANDSCAPE_IMAGE，"
                "或放一张文件名含「风景/汽车」的图片到素材目录"
            )
        page.image_search(landscape)
        assert page.MSG_NO_RESULT in "".join(page.u.messages()), \
            f"未提示「暂无相关数据」，实际：{page.u.messages()}"
        assert page.item_count() == 0

    @pytest.mark.ai
    def test_tc_img_15_image_search_without_material(self, fresh_utils):
        """图搜图页签下无素材 → 配有文案「找找看，这里有你的素材~」；点击搜索提示「暂无相关数据」。"""
        page = MyImagePage(fresh_utils).open()
        page.goto_tab("image")
        page.u.wait_present(page.IMAGE_SEARCH_SELECT)
        assert page.item_count() == 0, "全新的临时账号不应有素材"
        assert page.empty_text() == page.MSG_SEARCH_EMPTY
        page.u.upload_file(page.IMAGE_SEARCH_INPUT, page.u.sample_image())
        page.click_image_search()
        page.wait_search_result()
        assert page.MSG_NO_RESULT in "".join(page.u.messages())
