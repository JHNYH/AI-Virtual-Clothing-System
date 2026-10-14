"""迁移：把 Redis 里已有的向量倒灌回 MySQL。

改造前向量只存在 Redis，MySQL 里没有。必须先把它们抢救进库，
否则 Redis 一丢，这些向量就永远拿不回来了（只能重新调大模型算一遍）。

幂等：只更新 `vector` 为空的行，重复执行不会覆盖库中已有向量。

默认只预览；确认无误后加 --apply 才真正执行。

用法：
    python tools/backfill_vectors_to_mysql.py            # 预览
    python tools/backfill_vectors_to_mysql.py --apply    # 执行
"""
import argparse
import json
import sys

from _common import IMAGE_KEY, VECTOR_DIM, mysql_conn, redis_client, short


def main():
    parser = argparse.ArgumentParser(description="把 Redis 里的向量回填到 MySQL")
    parser.add_argument("--apply", action="store_true", help="真正执行（默认只预览）")
    args = parser.parse_args()

    rd = redis_client()
    conn = mysql_conn()
    cur = conn.cursor()

    records = []
    for key in rd.keys(IMAGE_KEY.format("*")):
        raw = rd.get(key)
        if raw:
            records.append(json.loads(raw))
    print(f"Redis 中共 {len(records)} 条向量记录")

    plan, skipped_no_row, already = [], 0, 0
    for rec in records:
        user_id, url = int(rec.get("userId")), rec.get("ossUrl")
        vector = rec.get("vector") or []
        if len(vector) != VECTOR_DIM:
            print(f"  跳过维度异常的记录：user={user_id} {short(url or '', 40)}")
            continue
        cur.execute("SELECT id, `vector` FROM files WHERE user_id=%s AND oss_url=%s", (user_id, url))
        rows = cur.fetchall()
        if not rows:
            skipped_no_row += 1
            print(f"  跳过：MySQL 里没有这张图 user={user_id} {short(url or '', 40)}")
            continue
        for row_id, existing in rows:
            if existing:
                already += 1
                continue
            plan.append((row_id, user_id, url, rec))

    print(f"\n需要回填 {len(plan)} 行；库里已有向量跳过 {already} 行；MySQL 无对应行 {skipped_no_row} 条")
    for row_id, user_id, url, _ in plan[:10]:
        print(f"  id={row_id} user={user_id} {short(url)}")

    if not args.apply:
        print("\n（预览模式，未做任何修改。确认后加 --apply 执行）")
        return 0

    for row_id, _, _, rec in plan:
        cur.execute(
            "UPDATE files SET description=%s, category=%s, `vector`=%s, vector_status='READY', "
            "vector_updated_at=NOW() WHERE id=%s",
            (rec.get("description") or "", rec.get("category") or "",
             json.dumps(rec.get("vector"), separators=(",", ":")), row_id))
    conn.commit()
    print(f"\n已回填 {len(plan)} 行")

    cur.execute("SELECT vector_status, COUNT(*) FROM files GROUP BY vector_status")
    print("各状态计数:", cur.fetchall())
    return 0


if __name__ == "__main__":
    sys.exit(main())
