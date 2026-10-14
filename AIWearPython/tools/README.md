# 检索索引运维工具

## 背景：为什么需要这些工具

图片的元数据存在 MySQL（`files` 表），而**检索用的向量存在 Redis 里**。两者的关系是：

> **MySQL 是唯一事实来源，Redis 只是可随时重建的索引。**

这个前提决定了所有设计：向量必须能在 MySQL 里找到，所以"索引丢了"只需要把库里的向量
重新搬回 Redis —— 毫秒级完成，不需要重新下载图片、也不需要再调一次大模型。

历史上这套系统踩过的坑：Redis 曾在空数据集状态下启动，zhangsan 的 6 张图片向量整体丢失，
表现是「我的图片」看得见 6 张图、但文搜图/图搜图任何查询都返回空，界面只提示"暂无相关数据"，
完全看不出真实原因。现在这类不一致由 **Java 侧自动对账**兜底（上传后、每次检索前、应用启动时），
下面的工具用于**手工体检、手工修复和一次性迁移**。

## 工具清单

| 脚本 | 用途 | 需要 Python 服务在跑？ | 会改数据吗 |
|---|---|---|---|
| `check_index.py` | 体检：对比「我的图片」与「检索索引」，列出缺失/孤儿/悬空/维度异常 | 否 | 否，纯只读 |
| `reconcile_index.py` | 手工对账：把索引补齐到与 MySQL 一致（`--dry-run` 只预览） | **是** | 会（补写索引、清理孤儿） |
| `verify_index.py` | 校验记录 id 是否等于 `md5(userId:ossUrl)`、维度是否为 512 | 否 | 否，纯只读 |
| `migrate_add_vector_columns.py` | 迁移：给 `files` 表加向量相关列（先自动备份） | 否 | 会（改表结构） |
| `backfill_vectors_to_mysql.py` | 迁移：把 Redis 里已有的向量倒灌回 MySQL | 否 | 会（只填 `vector` 为空的行） |

## 日常怎么用

**怀疑"搜不到图片"时，先跑体检：**

```bash
python tools/check_index.py
```

- 输出「一致」→ 检索侧没问题，去查查询词/阈值/图片本身；
- 输出「索引缺失」→ 跑 `python tools/reconcile_index.py`（或重启 Java 应用）即可修好；
- 输出「库里没有向量的图片」→ 这些图**永远搜不到**，需要重算向量（重启应用会限额重算，
  默认最多 20 张，见 `application.yml` 的 `aiwear.vector.startup-recompute-limit`）。

**想立刻修复又不想重启应用：**

```bash
python tools/reconcile_index.py --dry-run    # 先看会改什么
python tools/reconcile_index.py              # 执行
```

## 迁移一个全新/历史环境时的执行顺序

```bash
# 1. 备份 + 加列（预览后再执行）
python tools/migrate_add_vector_columns.py
python tools/migrate_add_vector_columns.py --apply

# 2. 把 Redis 里已有的向量抢救回 MySQL（必须在动 Redis 之前做）
python tools/backfill_vectors_to_mysql.py
python tools/backfill_vectors_to_mysql.py --apply

# 3. 部署新版本 Python 服务，再部署新版本 Java 服务
#    （Java 启动时会自动对账，把索引按确定性 id 重建）

# 4. 校验
python tools/verify_index.py
python tools/check_index.py
```

若历史环境里的记录还是旧版 `uuid` id，需要清空该用户的索引让它按
`md5(userId:ossUrl)` 重建 —— 前提是第 2 步已经成功，库里有向量可搬。
清理只允许**按用户逐个删**：

```
DEL aiwear:user:{userId}:images     # 以及它指向的各条 aiwear:image:{imageId}
```

**绝对不要用 `FLUSHDB`**：本地开发与线上站点共用同一个 Redis 实例（同一个 db 0），
`FLUSHDB` 会把线上所有用户的索引一起清掉。

## 注意事项

- **连接配置**：默认值与两端应用保持一致（MySQL `118.190.217.49:3307`、Redis `118.190.217.49:6379/0`）。
  可用环境变量覆盖：`MYSQL_HOST/PORT/USER/PASSWORD/DATABASE`、`REDIS_HOST/PORT/DB`、
  `PYTHON_SERVICE_URL`。生产环境请用环境变量，不要把真实账号密码提交进仓库。
- **依赖**：需要 `pymysql` 和 `redis`（见 `../requirements.txt`）；`reconcile_index.py` 需要
  Python 服务在运行，其余脚本不需要。
- **Redis 读写归属**：这些脚本只**读** Redis 的 key 结构，所有写入都通过 Python 服务的接口完成，
  避免同一份 record 格式在两处漂移。
- **`aiwear.vector.startup-reconcile`**：控制 Java 启动时是否自动对账。本地开发与线上共用同一套
  数据时可以保持 `true`；如果哪天要拿本地实例做隔离实验，记得改成 `false`。
