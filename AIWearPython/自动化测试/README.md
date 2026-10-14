# 自动化测试（Selenium + pytest）

对应被测系统 **AI 虚拟服装搭配平台「衣览无余」**，按页面拆分用例文件。
用例只覆盖五张页面思维导图中 **「功能测试」** 分支的功能点（界面/易用性/安全/兼容性/性能测试不在本套自动化代码范围内）。

## 一、目录结构

| 文件 | 作用 |
| --- | --- |
| `utils.py` | **Utils 通用方法类**：驱动初始化、显式等待、点击/输入/上传、Toast 与表单校验文案采集、图片预览、截图、登录态处理 |
| `login_register.py` | **AI 登录/注册页面**功能测试（对应 `img/AI登录 注册页面.png`） |
| `image_edit.py` | **图片编辑页面**功能测试（对应 `img/图片编辑页面.png`） |
| `image_stitch.py` | **图片合并页面**功能测试（对应 `img/图片合并页面.png`） |
| `my_image.py` | **我的图片页面**功能测试（对应 `img/我的图片页面.png`） |
| `history_record.py` | **历史记录页面**功能测试（对应 `img/历史记录页面.png`） |
| `conftest.py` | pytest 公共夹具：浏览器创建/销毁、已登录夹具、失败自动截图 |
| `pytest.ini` | 用例收集规则与运行参数 |
| `requirements.txt` | 依赖清单（Selenium 4.25.0、pytest） |
| `screenshots/` | 用例失败时自动截图输出目录（运行后生成） |
| `tmp/` | 用例构造的临时文件（超大文件、非图片文件） |

每个页面文件的结构一致：

```python
class XxxPage:      # 页面对象：元素定位 + 操作方法 + 状态查询
    ...
class TestXxx:      # 用例：只覆盖「功能测试」分支
    ...
```

## 二、环境准备

```powershell
pip install -r 自动化测试/requirements.txt
```

- Chrome / Edge 需已安装；Selenium 4.6+ 自带 Selenium Manager，会自动匹配驱动版本，无需手动下载 chromedriver。
- 被测系统需已启动：
  - 本地开发：`cd fronted; npm run dev`（默认 `http://127.0.0.1:5173`）
  - 部署环境：Nginx 地址（如 `http://118.190.217.49`），用 `AIWEAR_BASE_URL` 指定。

## 三、环境变量

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `AIWEAR_BASE_URL` | 被测系统地址 | `http://127.0.0.1:5173` |
| `AIWEAR_BROWSER` | `chrome` / `edge` | `chrome` |
| `AIWEAR_HEADLESS` | `1` 无头运行 | `0` |
| `AIWEAR_TIMEOUT` | 常规等待秒数 | `20` |
| `AIWEAR_AI_TIMEOUT` | AI 出图等待秒数 | `300` |
| `AIWEAR_TOKEN` | 已登录用户的 JWT（免登录，设置后优先使用） | 空 |
| `AIWEAR_ACCOUNT` / `AIWEAR_PASSWORD` | 密码登录账号 | `zhangsan` / `123456` |
| `AIWEAR_EMAIL` / `AIWEAR_CODE` | 验证码登录邮箱与验证码 | 空（需人工取码） |
| `AIWEAR_UPLOAD_DIR` | 上传/选图素材目录（**需放真实衣物/人像照片**） | 自动查找项目里的 `img` 目录 |
| `AIWEAR_REJECT_IMAGE` | 非业务图片（汽车/风景）路径 | 空（会按文件名关键字在素材目录里自动找） |
| `AIWEAR_LANDSCAPE_IMAGE` | 风景/其它类图片路径 | 同上 |
| `AIWEAR_SEARCH_QUERY` | 文搜图关键词 | `衣服` |

> 「需要登录」的用例会用 `AIWEAR_ACCOUNT / AIWEAR_PASSWORD`（默认 `zhangsan / 123456`）登录；
> 登录不上才会 skip。拿到 token 的最快方式：浏览器登录后在控制台执行 `localStorage.getItem('mengtu_token')`。

### 临时账号：空态类用例自动准备数据

「没有素材」「没有历史记录」这类用例以前需要手工准备一个干净账号，现在改为**自动注册临时账号**：

- 后端 `UserServiceImpl.auth()` 对「不含 `@` 且库里不存在」的用户名会直接 `insert` 一个新用户，
  所以走一次「密码登录」就等于注册，**不需要邮箱验证码**；
- 用例里用 `fresh_utils` 夹具即可拿到一个全新的空账号，`fresh_utils_with_edit_record` 会在此基础上
  再上传一张素材、用超长指令编辑一次，造出「长指令」记录；
- 临时账号用户名为 `autotest_月日时分秒+随机数`，每次运行会新增 1 个（后端没有注销接口），
  介意的话可以定期到数据库里清理 `username like 'autotest_%'` 的记录。

## 四、运行

在**本目录下**运行（`pytest.ini` 与用例同级，直接 `pytest` 即可）：

```powershell
cd "C:\Python Project\AIWearPython\自动化测试"

# 全部用例
pytest

# 只跑非 AI 的用例（快、稳，推荐日常回归用）
pytest -m "not ai"

# 只跑 AI 链路（出图 / 上传向量化 / 检索，会吃满本机 CPU，建议单独跑）
pytest -m ai

# 单个页面
pytest login_register.py -v
pytest image_edit.py -v

# 列出每条跳过原因（排查"为什么这么多 skip"时用）
pytest -rs

# 指向部署环境
pytest --base-url http://118.190.217.49

# 免登录跑（注入 token）
$env:AIWEAR_TOKEN="eyJhbGciOi..."; pytest

# 只跑某个场景
pytest image_stitch.py -k "same_image"
pytest -k search

# 全部用例共用一个浏览器（启动快很多，但登录态等状态会跨用例保留）
pytest --reuse-browser
```

> 提示：默认每条用例独占一个浏览器，Windows 上 Chrome 冷启动较慢（实测约 30s/条），
> 全量回归建议加 `--reuse-browser`（实测可降到 3s/条左右）。
>
> **跑全量前请留意机器负载**：Python AI 服务就在本机跑，出图/上传向量化/CLIP 检索都是 CPU 密集型操作。
> CPU 被吃满时浏览器渲染会明显卡顿，表现为"点了没反应、断言超时"（实测：混跑全量偶尔 1~2 条失败；
> 用 `-m "not ai"` 单独跑则 41 条全绿）。所以推荐日常用 `-m "not ai"` 回归，AI 用例挑机器空闲时单独跑。

## 五、用例覆盖对照（均为思维导图「功能测试」分支）

| 文件 | 覆盖功能点 |
| --- | --- |
| `login_register.py` | 验证码登录/注册（新用户注册、老用户登录）、用户名密码登录/注册；异常验证码（为空、错误、5 分钟内重复发送）、异常邮箱（为空、格式错误）、邮箱和验证码都异常、异常用户名（为空）、异常密码（为空、错误、长度不足）、用户名和密码都异常 |
| `image_edit.py` | 打开弹框（无素材/有素材/未选图点确认/选图后确认）、提交按钮（未选图禁用、未输指令禁用、正常提交出图并新增历史记录）、删除图片、重置 |
| `image_stitch.py` | 打开弹框、槽位选图与序号角标、提交按钮（未选图/只选一张/未输指令禁用、两张相同拦截、两张不同正常合并并新增历史记录）、删除其中一张、重置 |
| `my_image.py` | 上传人物/服装/其它图片、超 50MB、非图片文件、空列表缺省态*、图片预览、文搜图（空输入、无结果、有结果、无素材*）、图搜图（空输入、无结果、有结果、无素材*） |
| `history_record.py` | 空列表缺省态*、列表倒序展示（序号/类型/图片1/图片2/指令/执行结果）、类型筛选（图片编辑/图片合并/全部记录）、图片预览、长指令省略*与短指令完整显示 |

> 带 `*` 的用例都由「临时账号」夹具自动准备数据，不再依赖手工前置条件；
> 只有「其它图片审核不通过」「图搜图无结果」两条还需要素材目录里有一张汽车/风景图
> （文件名含「汽车/车/风景/景/建筑」即可被自动识别，或用 `AIWEAR_REJECT_IMAGE` 指定）。

## 六、已经踩过的坑（写新用例时注意）

| 现象 | 原因 | 处理方式 |
| --- | --- | --- |
| 点击缩略图"没反应"，预览不打开 | el-image 的图**还在下载**（`naturalWidth == 0`）时只显示占位图，点击无效 | 先 `wait_image_loaded()` 再点，已内置在 `open_image_viewer()` 里 |
| 点「+ 图片」后弹框很久才出来 / 断言超时 | 紧邻的上一个用例刚发起过 AI 出图，Python 生成图片会把 CPU 吃满，浏览器渲染跟着卡；另外 `/file/my-images` 顺带做索引对账时也会连带等 Python | `click_until()` 多次点击+等待；造数据夹具会**等 AI 请求真正结束**再 skip，避免请求悬在半空影响下一个用例 |
| Toast 采集不到 | 整页导航会清掉注入的 MutationObserver | `open()` 每次都重新注入（`start_message_recorder`） |
| 列表刚加载完断言缺省态为空串 | 加载中（`isMyImagesLoading`）素材与缺省态都不渲染 | `wait_list_loaded()` |
| `--reuse-browser` 下登录页用例报错 | 已登录时路由守卫把 `/login` 重定向到 `/edit` | `LoginRegisterPage.open()` 先 `clear_auth()` |
| 上传素材时提示「图片审核不通过」 | 素材目录里混了汽车/风景图（按文件名排序时可能排在最前） | 业务用例统一用 `sample_person_image()` / `sample_clothing_image()` |
| AI 用例跑完后紧接着的用例偶发超时 | Python 出图吃满 CPU，浏览器渲染卡顿 | AI 用例已打 `ai` 标记，日常回归用 `-m "not ai"` 排除 |

## 七、维护约定

1. 页面元素与文案直接取自前端源码（`fronted/src/views/*.vue`、`fronted/src/components/*.vue`）；
   页面改版后请同步更新对应页面对象的定位常量与期望文案常量。
2. 新增通用能力（等待、上传、断言等）请加到 `utils.py` 的 `Utils` 类，不要在用例里写 `time.sleep`。
3. 需要前置数据的用例优先用 `fresh_utils` / `fresh_utils_with_edit_record` 夹具自动造数据；
   只有在真实账号上验证的用例才用 `logged_utils`，前置不满足时 `pytest.skip` 并说明原因。
