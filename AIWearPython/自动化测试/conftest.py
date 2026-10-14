# -*- coding: utf-8 -*-
"""
pytest 公共配置与夹具

统一在这里创建/销毁浏览器，各页面用例文件只写业务断言：
    utils            每个用例一个干净的浏览器（加 --reuse-browser 则全程共用一个）
    logged_utils     已登录的浏览器（自动读取 AIWEAR_TOKEN 或账号密码）
    driver（兼容别名）与 utils 等价

另提供两个钩子：
- pytest_runtest_makereport：记录用例结果，供失败截图使用；
- pytest_runtest_logreport：用例失败时自动截图，存到 screenshots 目录，便于写测试报告。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# 保证自动化测试目录在 sys.path 中，页面文件可直接 `from utils import Utils`
TEST_DIR = Path(__file__).resolve().parent
if str(TEST_DIR) not in sys.path:
    sys.path.insert(0, str(TEST_DIR))

from utils import AI_TIMEOUT, BROWSER, DEFAULT_TIMEOUT, Utils  # noqa: E402

#: 造「长指令」记录时使用的指令（远超历史记录表「指令」列宽，用于验证省略号）
LONG_INSTRUCTION = (
    "把人物的上衣换成浅蓝色的宽松针织开衫，保留原本的姿势与表情，"
    "背景、光线、构图和人物比例都保持不变，衣服的材质、褶皱和垂坠感要自然，"
    "注意袖口与领口的细节要清晰，整体色调偏冷、画面干净明亮"
)


# ---------------------------------------------------------------------------
# 命令行参数
# ---------------------------------------------------------------------------
def pytest_addoption(parser):
    parser.addoption(
        "--browser",
        action="store",
        default=BROWSER,
        choices=["chrome", "edge"],
        help="运行的浏览器内核：chrome（默认）或 edge",
    )
    parser.addoption(
        "--base-url",
        action="store",
        default=None,
        help="被测系统地址，覆盖环境变量 AIWEAR_BASE_URL",
    )
    parser.addoption(
        "--keep-open",
        action="store_true",
        default=False,
        help="用例结束后不关闭浏览器，便于人工查看页面",
    )
    parser.addoption(
        "--reuse-browser",
        action="store_true",
        default=False,
        help="全部用例共用一个浏览器（启动快很多，但登录态等状态会跨用例保留）",
    )


@pytest.fixture(scope="session")
def browser_name(pytestconfig) -> str:
    return pytestconfig.getoption("--browser")


@pytest.fixture(scope="session")
def base_url(pytestconfig) -> str:
    return pytestconfig.getoption("--base-url") or None


# ---------------------------------------------------------------------------
# 浏览器夹具
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def shared_driver(browser_name):
    """整个测试会话共用的浏览器（由 --reuse-browser 触发，节省启动时间）。"""
    driver = Utils.create_driver(browser=browser_name)
    yield driver
    try:
        driver.quit()
    except Exception:
        pass


@pytest.fixture()
def utils(browser_name, base_url, pytestconfig, request):
    """浏览器夹具。

    默认每个用例独占一个浏览器，用例之间互不影响；
    加 --reuse-browser 时全部用例共用一个浏览器（快，但登录态/表单状态会保留）。
    """
    kwargs = {"timeout": DEFAULT_TIMEOUT}
    if base_url:  # 命令行 --base-url 优先于环境变量
        kwargs["base_url"] = base_url

    if pytestconfig.getoption("--reuse-browser"):
        helper = Utils(driver=request.getfixturevalue("shared_driver"), **kwargs)
        yield helper
        return

    helper = Utils(driver=Utils.create_driver(browser=browser_name), **kwargs)
    yield helper
    if not pytestconfig.getoption("--keep-open"):
        helper.quit()


@pytest.fixture()
def driver(utils):
    """兼容写法：直接拿 WebDriver 的用例可用此夹具。"""
    return utils.driver


@pytest.fixture()
def logged_utils(utils):
    """已登录的浏览器：优先复用 token，其次环境变量注入，最后走 UI 密码登录。"""
    utils.ensure_logged_in()
    return utils


@pytest.fixture()
def fresh_utils(utils):
    """全新注册的临时账号（用完即弃）。

    该账号的「我的图片」和「历史记录」都是空的，用于空态类用例：
    不用再依赖"手工准备一个没传过图的新账号"这个前置条件。
    注意：账号会留在数据库里（后端没有提供注销接口），每次运行会产生 1 个 autotest_ 前缀的账号。
    """
    username = utils.register_temp_user()
    print(f"\n[临时账号] {username}")
    return utils


@pytest.fixture()
def fresh_utils_with_edit_record(fresh_utils):
    """临时账号 + 一条「长指令」的图片编辑记录。

    造数据链路：上传一张素材 → 用超长指令编辑一次 → 历史记录里就多一条长指令记录。
    整条链路都包了异常处理：任何一步失败（Python 服务没起、机器太忙导致点击/等待超时等）
    都 skip 而不是 error，避免把环境问题算成用例失败。
    """
    from image_edit import ImageEditPage
    from my_image import MyImagePage

    fresh = fresh_utils
    try:
        upload_page = MyImagePage(fresh).open()
        upload_page.upload_image()
        upload_page.wait_count_changed(0, timeout=180)

        # 注意：必须等这次 AI 请求真正跑完（成功或失败）再决定 skip。
        # 若中途直接放弃，请求还挂在后端（Python 出图会吃满 CPU），
        # 会拖慢紧接其后的用例，表现为"点了没反应、断言超时"。
        edit_page = ImageEditPage(fresh).open()
        edit_page.select_image(0)
        edit_page.input_instruction(LONG_INSTRUCTION)
        edit_page.click_submit()
        fresh.wait_visible(ImageEditPage.LOADING_MSG, timeout=120)
        fresh.wait_visible(ImageEditPage.RESULT_IMG, timeout=AI_TIMEOUT)
    except Exception as exc:
        pytest.skip(
            f"准备数据失败（{exc.__class__.__name__}）：{exc}；页面提示：{fresh.messages()}"
        )
    return fresh


# ---------------------------------------------------------------------------
# 失败自动截图
# ---------------------------------------------------------------------------
@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    """把各阶段结果挂到 item 上，供下面的钩子判断是否失败。"""
    outcome = yield
    report = outcome.get_result()
    setattr(item, f"rep_{report.when}", report)


@pytest.fixture(autouse=True)
def _screenshot_on_failure(request):
    """用例失败时自动截图并打印页面摘要，方便定位与写测试报告。"""
    yield
    report = getattr(request.node, "rep_call", None)
    if report is None or not report.failed:
        return
    # 用例可能用 utils / logged_utils / fresh_utils 等不同夹具，取其中任意一个 Utils 实例
    helper = next(
        (value for value in request.node.funcargs.values() if isinstance(value, Utils)),
        None,
    )
    if helper is None:
        return
    try:
        path = helper.screenshot(request.node.name)
        print(f"\n[失败截图] {path}\n[页面摘要] {helper.describe_page()}")
    except Exception as exc:  # 截图失败不应覆盖原始错误
        print(f"\n[失败截图失败] {exc}")
