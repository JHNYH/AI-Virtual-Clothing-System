"""手动对账：把某用户（或全部用户）的检索索引与 MySQL 里的图片拉齐。

正常运行时这件事是自动做的 —— Java 侧在上传后、每次检索前、以及应用启动时都会对账，
所以这个脚本用于「不方便重启应用」或「想立刻修好并看到报告」的场景。

对账本身是纯搬运：用 MySQL 里存的向量把索引补齐，不会重新下载图片、也不会调用大模型
（所以它是毫秒级的，不像重新向量化那样每张要几秒并消耗大模型额度）。

需要 Python 服务在运行：Redis 的写入统一由 server.py 负责，脚本不自己拼 record 结构。

用法：
    python tools/reconcile_index.py --dry-run            # 只看差异，不改任何东西
    python tools/reconcile_index.py                      # 对所有用户执行对账
    python tools/reconcile_index.py --user-id 10000001   # 只对某个用户执行
"""
import argparse
import sys

from _common import (VECTOR_DIM, analyze_user, all_user_ids, db_rows,
                     db_vectors_by_url, is_healthy, mysql_conn, post_json,
                     redis_client, short)


def dry_run(rd, cur, user_id):
    results = [analyze_user(rd, cur, user_id)] if user_id else \
        [analyze_user(rd, cur, u) for u in all_user_ids(cur)]
    for r in results:
        if is_healthy(r):
            print(f"用户 {r['user_id']}：一致，无需处理")
            continue
        print(f"用户 {r['user_id']}：")
        if r["missing"]:
            print(f"  索引缺失 {len(r['missing'])} 张，将被补写：")
            for url in r["missing"][:10]:
                print(f"    {short(url)}")
        if r["orphans"]:
            print(f"  孤儿记录 {len(r['orphans'])} 条，将被清理")
        if r["dangling"]:
            print(f"  悬空指针 {len(r['dangling'])} 个，将被清理")
        if r["bad_dimension"]:
            print(f"  向量维度异常 {r['bad_dimension']} 条，需要重新计算")
    print("\n（dry-run：以上只是预览，未做任何修改）")


def reconcile_one(cur, user_id):
    rows = db_rows(cur, user_id)
    keep_urls = [r[1] for r in rows if r[1]]
    if not keep_urls:
        print(f"用户 {user_id}：库里没有图片，跳过")
        return

    status, body = post_json("/api/reconcile-user", {"userId": user_id, "keepOssUrls": keep_urls})
    if status != 200 or not isinstance(body, dict) or not body.get("success"):
        print(f"用户 {user_id}：对账请求失败（status={status} body={body}）")
        print("  请确认 Python 服务在运行、且是包含 /api/reconcile-user 的新版本")
        return

    missing = body.get("missing") or []
    healed = 0
    without_vector = 0
    if missing:
        vectors = db_vectors_by_url(cur, user_id)
        for url in missing:
            vector = vectors.get(url)
            if not vector:
                without_vector += 1
                continue
            st, res = post_json("/api/index-image", {
                "userId": user_id, "ossUrl": url,
                "description": "", "category": "", "vector": vector,
            })
            if st == 200 and isinstance(res, dict) and res.get("success"):
                healed += 1
            else:
                print(f"  补写失败：{short(url)}（status={st} body={res}）")

    print(f"用户 {user_id}：补写 {healed} 张，库里无向量跳过 {without_vector} 张，"
          f"清理孤儿 {len(body.get('removed') or [])} 条，索引现有 {body.get('indexed')} 条")
    if without_vector:
        print("  注意：这些图片在 MySQL 里也没有向量，需要重新计算（重启应用会限额重算）")


def main():
    parser = argparse.ArgumentParser(description="手动对账检索索引")
    parser.add_argument("--user-id", type=int, help="只处理某个用户")
    parser.add_argument("--dry-run", action="store_true", help="只预览差异，不做任何修改")
    args = parser.parse_args()

    rd = redis_client()
    conn = mysql_conn()
    cur = conn.cursor()

    if args.dry_run:
        dry_run(rd, cur, args.user_id)
        return 0

    users = [args.user_id] if args.user_id else all_user_ids(cur)
    if not users:
        print("files 表里没有任何图片")
        return 0
    for user_id in users:
        reconcile_one(cur, user_id)
    print("\n完成。可用 python tools/check_index.py 复查。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
