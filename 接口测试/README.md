# 接口测试（JMeter）

被测系统：**AI 虚拟服装搭配平台「衣览无余」**
测试计划：`接口测试.jmx`（JMeter 5.6.3，只用原生元件 + JSON 断言，不依赖任何插件）

## 一、结构：两个线程组，各设并发

图片里的 10 个接口**全部保留、全部会执行、全部有断言**，只是按"能承受的并发"分成了两组：

```
测试计划
├── HTTP信息头管理器 / HTTP请求默认值 / HTTP Cookie管理器   ← 两个线程组共用
│
├── 线程组-核心接口（可高并发，默认 10 线程）
│     登录/注册接口 → 我的图片列表接口 → 历史记录接口
│
├── 线程组-AI链路（低并发，默认 1 线程）
│     登录/注册接口 → 上传图片接口 → 我的图片列表接口 → 文搜图接口 → 图搜图接口
│     → 图片编辑接口 → 图片合并接口 → 图片内容审核接口 → 退出登录接口
│
└── 察看结果树 / 聚合报告   ← 收集两个线程组的样本
```

计划里已勾选 **「独立运行每个线程组」**（`serialize_threadgroups=true`）：先把核心组跑完，再跑 AI 组，避免 AI 请求被并发的核心组挤垮。

**为什么这样分**：核心接口是纯 Java + MySQL，可以压到 50/100 并发；
AI 接口最终打到**本机 Python 推理** + **跨公网 Redis** + **大模型限流**，10 个并发必挂（实测见第五节），
但**不代表不测**——用 1~2 并发测它的功能、响应时间和稳定性，照样有数据。

## 二、跑之前要满足的条件

1. **服务已启动**：Java 后端 `8081`、Python AI 服务 `5000`。
2. **账号里至少有 2 张图片**：图片合并要从列表取前两张不同的图。
3. **素材文件存在**（上传/图搜图/审核用）：`C:/Python Project/img/男模特3.jpg`、`长袖.jpg`。

## 三、怎么跑

```powershell
cd "C:\Python Project\请求测试"
& "C:\Jmeter\apache-jmeter-5.6.3\bin\jmeter.bat" -n -t 接口测试.jmx -l 结果.jtl -j jmeter.log
```

GUI 调试：`jmeter.bat` → 打开 `接口测试.jmx` → 点绿色启动 → 看「察看结果树」。

**不用改文件就能调并发/换环境**（`-J` 覆盖属性）：

```powershell
# 核心接口压到 50 并发、循环 10 次；AI 链路仍保持 1 并发
jmeter.bat -n -t 接口测试.jmx -l 结果.jtl -JcoreThreads=50 -JcoreLoops=10

# 单独把 AI 链路加到 3 并发（找它的承受上限，见下节）
jmeter.bat -n -t 接口测试.jmx -l 结果.jtl -JcoreThreads=1 -JcoreLoops=1 -JaiThreads=3

# 换环境 / 换账号 / 换关键词
jmeter.bat -n -t 接口测试.jmx -l 结果.jtl -Jhost=118.190.217.49 -Jport=80 -Jaccount=zhangsan -JsearchQuery=连衣裙
```

| 属性 | 含义 | 默认 |
| --- | --- | --- |
| `coreThreads` / `coreLoops` / `coreRamp` | 核心接口组的线程数/循环/爬坡秒数 | 10 / 1 / 5 |
| `aiThreads` / `aiLoops` | AI 链路的线程数/循环 | 1 / 1 |
| `host` / `port` | 被测系统地址 | 127.0.0.1 / 8081 |
| `account` / `password` | 登录账号 | zhangsan / 123456 |
| `searchQuery` | 文搜图关键词 | 衣服 |
| `pyhost` / `pyport` | Python AI 服务地址 | 127.0.0.1 / 5000 |

## 四、AI 接口怎么"测"（不是禁用，是阶梯递增）

想知道 AI 接口到底能扛多少并发，用**阶梯递增 + 看错误率拐点**，这本身就是很有说服力的性能测试结论：

| 轮次 | 命令 | 观察 |
| --- | --- | --- |
| 基线 | `-JcoreThreads=1 -JaiThreads=1` | 各接口的单请求响应时间（无干扰基线） |
| 2 并发 | `-JaiThreads=2` | 错误率是否仍为 0，响应时间涨了多少 |
| 3 并发 | `-JaiThreads=3` | … |
| 5 并发 | `-JaiThreads=5` | 大概率开始出错，拐点就在这里 |

每轮跑完看「聚合报告」里的 **Error%** 和 **Average/90% 响应时间**，把拐点写进报告。
（记得每轮把 `-JcoreThreads=1`，否则核心组的并发会干扰 AI 组的测量。）

## 五、已知的并发问题（跑之前先知道，免得以为是自己配错了）

| 接口 | 并发下的报错 | 根因 | 性质 |
| --- | --- | --- | --- |
| 文搜图 / 图搜图 | `检索服务不可用，请稍后重试` | Python 侧检索接口抛 `Timeout reading from socket`：Redis 在 `118.190.217.49`（跨公网）、`socket_timeout=2s`、连接池只有 8；Java 侧把任何异常统一降级成这句话 | 环境/性能瓶颈（实测 6 并发仅 2 成功） |
| 图片编辑 | `'NoneType' object is not subscriptable` | 出图工具对上游（通义万相）返回没有判空，并发限流时直接抛 TypeError 并透给前端 | 应用缺陷（缺判空/重试/友好提示） |
| 图片合并 | `无法处理提供的图片路径…正斜杠 '/' 格式` | 合并走 LangGraph Agent，把**本地临时文件路径塞进 prompt 让大模型转述**给工具，路径被改坏就读不到文件 | 设计脆弱（不应让 LLM 转述本地路径） |
| 退出登录 | `退出失败，请稍后重试` | Redis 里每个用户只有一个 token；多个线程用同一账号并发退出，第一个删掉后其余都失败 | 预期行为，属测试设计问题 |

> 因此：AI 链路默认只给 1 个线程。想验证多用户场景，请给每个线程配不同账号
> （加 `CSV Data Set Config` 放 `account,password` 多行，登录 JSON 改用 `${account}`/`${password}`）。

## 六、这份文件修掉了旧文件里的 5 个配置问题

| # | 旧文件（`图片编辑接口.jmx`） | 后果 | 现在 |
| --- | --- | --- | --- |
| 1 | 登录参数填在**参数**页签 | 变成表单请求，`@RequestBody` 解析不了 → 415 | 改用消息体数据 + `Content-Type: application/json` |
| 2 | 文搜图参数名写成 `text` | 接口要 `query`，等于没传关键词 | 改为 `query` |
| 3 | 上传/图搜图/审核的**文件参数名为空** | 后端 `@RequestParam("file")` 取不到 → 400 | 统一填 `file` |
| 4 | 图片编辑只传 `image`（还是表单参数）、没有 `instruction` | 格式与字段都不对 | 改 JSON 体，图片地址用变量注入 |
| 5 | 默认端口 `5173`、没有提取 token | 前端没起就连不上；`${token}` 不替换 → `JWT strings must contain exactly 2 period characters` | 端口改 `8081`；登录后自动提取 `$.data.token` |

另外每个采样器都挂了 **JSON 断言 `$.code == 200`**：本项目**业务异常也是 HTTP 200**
（`ApiLogAspect` 把异常统一包成 `Result.serverError`），所以断言要看 `code`，不要看 HTTP 状态码。

## 七、注意事项

- **上传接口会真的往账号里加图**（后端没有删除接口），跑多了素材会变多。
- **编辑/合并会真的调用大模型出图**，每次 30~90 秒并消耗额度。
- 运行产物 `结果.jtl`、`jmeter.log` 都在本目录；用 `-e -o 报告目录` 可生成 HTML 报告。
