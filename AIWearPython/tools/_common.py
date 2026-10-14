"""工具脚本共用部分：连接配置与只读对比逻辑。

配置优先读环境变量，默认值与两端应用保持一致：
  - Java 侧：AIWear/src/main/resources/application.yml（MySQL / Redis）
  - Python 侧：AIWearPython/server.py（Redis）
生产环境请用环境变量覆盖，不要把真实账号密码提交进仓库。

这里只「读」Redis 的 key 结构，不自己实现写入——写入一律由 server.py 负责，
避免同一份 record 结构在两处漂移。
"""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import pymysql
import redis
from dotenv import load_dotenv

# 与 server.py 保持一致：从 AIWearPython/.env 读取本地连接配置（该文件不进版本库）
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ---------- 连接配置 ----------
MYSQL_HOST = os.getenv("MYSQL_HOST", "118.190.217.49")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3307"))
MYSQL_USER = os.getenv("MYSQL_USER", "bite")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "bite_wear")

REDIS_HOST = os.getenv("REDIS_HOST", "118.190.217.49")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))

PYTHON_SERVICE_URL = os.getenv("PYTHON_SERVICE_URL", "http://127.0.0.1:5000")

# ---------- Redis key 格式（与 server.py 保持一致，这里只用于读取）----------
IMAGE_KEY = "aiwear:image:{}"
USER_INDEX_KEY = "aiwear:user:{}:images"
VECTOR_DIM = 512


def mysql_conn():
    return pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER,
                           password=MYSQL_PASSWORD, database=MYSQL_DATABASE,
                           charset="utf8mb4")


def redis_client():
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB,
                       socket_timeout=5, socket_connect_timeout=5, decode_responses=True)


def post_json(path, payload, timeout=300):
    """调用 Python 服务。返回 (status, body)，body 尽量解析成 dict。"""
    req = urllib.request.Request(PYTHON_SERVICE_URL + path,
                                 data=json.dumps(payload).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status, raw = resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, raw


# ---------- 读取 ----------
def db_rows(cur, user_id=None):
    """读 files 表：返回 [(user_id, oss_url, vector_status, vector_len)]"""
    sql = "SELECT user_id, oss_url, vector_status, LENGTH(`vector`) FROM files"
    params = ()
    if user_id is not None:
        sql += " WHERE user_id=%s"
        params = (user_id,)
    sql += " ORDER BY user_id, id"
    cur.execute(sql, params)
    return cur.fetchall()


def db_vectors_by_url(cur, user_id):
    """取某用户的 ossUrl -> 向量文本（只有对账补写时才需要，向量每条约 10KB）"""
    cur.execute("SELECT oss_url, `vector` FROM files WHERE user_id=%s", (user_id,))
    return {url: vec for url, vec in cur.fetchall()}


def all_user_ids(cur):
    cur.execute("SELECT DISTINCT user_id FROM files ORDER BY user_id")
    return [r[0] for r in cur.fetchall()]


def analyze_user(rd, cur, user_id):
    """只读对比：把某用户的 MySQL 图片列表与 Redis 索引逐条比一遍。

    返回的字段含义：
      db_total           MySQL 里该用户的图片总数（「我的图片」看到的数量）
      db_without_vector  库里没有可用向量的图片数（永远搜不到，需要重算）
      indexed            索引里能对上的图片数
      missing            库里有、索引里没有的地址（对账会补写）
      orphans            索引里有、库里已经没有的地址（对账会清理）
      dangling           索引指针指向的记录不存在（对账会清理指针）
      bad_dimension      索引里向量维度不对的条数
    """
    rows = db_rows(cur, user_id)
    db_urls = [r[1] for r in rows]
    keep = set(db_urls)

    index_key = USER_INDEX_KEY.format(user_id)
    ids = list(rd.smembers(index_key))
    pipe = rd.pipeline()
    for image_id in ids:
        pipe.get(IMAGE_KEY.format(image_id))
    payloads = pipe.execute()

    indexed = set()
    orphans = []
    dangling = []
    bad_dimension = 0
    for image_id, payload in zip(ids, payloads):
        if not payload:
            dangling.append(image_id)
            continue
        rec = json.loads(payload)
        url = rec.get("ossUrl", "")
        if url not in keep:
            orphans.append(url)
            continue
        if len(rec.get("vector") or []) != VECTOR_DIM:
            bad_dimension += 1
            continue
        indexed.add(url)

    return {
        "user_id": user_id,
        "db_total": len(db_urls),
        "db_without_vector": sum(1 for r in rows if r[2] != "READY"),
        "indexed": len(indexed),
        "missing": [u for u in db_urls if u not in indexed],
        "orphans": orphans,
        "dangling": dangling,
        "bad_dimension": bad_dimension,
    }


def analyze_all(rd, cur, user_id=None):
    users = [user_id] if user_id is not None else all_user_ids(cur)
    return [analyze_user(rd, cur, u) for u in users]


def is_healthy(result):
    """该用户是否没有任何不一致"""
    return (not result["missing"] and not result["orphans"]
            and not result["dangling"] and not result["bad_dimension"])


def short(url, n=46):
    return url if len(url) <= n else "…" + url[-n:]
