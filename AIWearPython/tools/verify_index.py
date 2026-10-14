"""校验：Redis 索引是否与 MySQL 对得上，且记录 id 是否等于 md5(userId:ossUrl)。

只读。用来确认「确定性 id」这套约定真的成立（同一张图不会产生两条记录），
以及索引里没有残留的旧记录。

用法：
    python tools/verify_index.py

退出码：0 = 全部正确；1 = 存在问题
"""
import hashlib
import json
import sys

from _common import (IMAGE_KEY, USER_INDEX_KEY, VECTOR_DIM, db_rows, mysql_conn,
                     redis_client, short)


def expected_id(user_id, oss_url):
    return hashlib.md5(f"{user_id}:{oss_url}".encode("utf-8")).hexdigest()


def main():
    rd = redis_client()
    conn = mysql_conn()
    cur = conn.cursor()
    rows = db_rows(cur)

    ok = 0
    problems = []
    print("MySQL 图片 -> Redis 记录 校验：")
    for user_id, oss_url, status, _ in rows:
        exp = expected_id(user_id, oss_url)
        raw = rd.get(IMAGE_KEY.format(exp))
        in_index = bool(rd.sismember(USER_INDEX_KEY.format(user_id), exp))
        if not raw:
            problems.append(f"user={user_id} 记录不存在: {short(oss_url)}")
            print(f"  [缺失] user={user_id} id={exp[:12]}.. {short(oss_url)}")
            continue
        rec = json.loads(raw)
        dim = len(rec.get("vector") or [])
        if not in_index:
            problems.append(f"user={user_id} 未被索引引用: {short(oss_url)}")
            print(f"  [未引用] user={user_id} id={exp[:12]}.. {short(oss_url)}")
        elif dim != VECTOR_DIM:
            problems.append(f"user={user_id} 向量维度 {dim}: {short(oss_url)}")
            print(f"  [维度异常] user={user_id} dim={dim} {short(oss_url)}")
        else:
            ok += 1

    # 反向检查：Redis 里有没有和 MySQL 对不上的残留记录
    db_ids = {expected_id(u, o) for u, o, _, _ in rows}
    leftovers = [k for k in rd.keys(IMAGE_KEY.format("*")) if k.split(":")[-1] not in db_ids]

    print(f"\n{ok}/{len(rows)} 张图片的记录 id 正确、已在索引中、向量维度为 {VECTOR_DIM}")
    if leftovers:
        print(f"Redis 里有 {len(leftovers)} 条记录在 MySQL 中找不到对应图片（多为改造前遗留）：")
        for key in leftovers[:10]:
            print(f"  {key}")
        print("  这些记录不被索引引用时不会出现在检索结果里，可安全清理")
    if problems:
        print("\n存在问题：")
        for p in problems:
            print("  " + p)
        print("\n修复方式：重启 Java 应用（启动时自动对账），或运行 python tools/reconcile_index.py")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
