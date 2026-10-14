"""只读体检：对比「我的图片」(MySQL) 与「检索索引」(Redis)。

只读，不做任何修改，不需要 Python 服务在运行。

用法：
    python tools/check_index.py                # 检查所有用户
    python tools/check_index.py --user-id 10000001
    python tools/check_index.py --quiet        # 只输出有问题的用户

退出码：0 = 全部一致；1 = 存在不一致（便于挂到监控/脚本里）
"""
import argparse
import sys

from _common import analyze_all, is_healthy, mysql_conn, redis_client, short


def main():
    parser = argparse.ArgumentParser(description="对比 MySQL 图片与 Redis 检索索引（只读）")
    parser.add_argument("--user-id", type=int, help="只检查某个用户")
    parser.add_argument("--quiet", action="store_true", help="只输出存在不一致的用户")
    args = parser.parse_args()

    rd = redis_client()
    conn = mysql_conn()
    cur = conn.cursor()
    results = analyze_all(rd, cur, args.user_id)

    if not results:
        print("files 表里没有任何图片")
        return 0

    unhealthy = 0
    for r in results:
        healthy = is_healthy(r)
        if healthy and args.quiet:
            continue
        unhealthy += 0 if healthy else 1
        print(f"用户 {r['user_id']}  {'【一致】' if healthy else '【不一致】'}")
        print(f"  我的图片(MySQL)     : {r['db_total']} 张")
        print(f"  已建立索引(Redis)   : {r['indexed']} 张")
        print(f"  库里没有向量的图片  : {r['db_without_vector']} 张"
              f"{'（永远搜不到，需要重算向量）' if r['db_without_vector'] else ''}")
        if r["missing"]:
            print(f"  索引缺失            : {len(r['missing'])} 张（对账会补写）")
            for url in r["missing"][:5]:
                print(f"      {short(url)}")
        if r["orphans"]:
            print(f"  孤儿记录            : {len(r['orphans'])} 条（库里已无此图，对账会清理）")
            for url in r["orphans"][:5]:
                print(f"      {short(url)}")
        if r["dangling"]:
            print(f"  悬空索引指针        : {len(r['dangling'])} 个（对账会清理）")
        if r["bad_dimension"]:
            print(f"  向量维度异常        : {r['bad_dimension']} 条")
        print()

    print(f"共 {len(results)} 个用户，其中 {unhealthy} 个存在不一致")
    if unhealthy:
        print("修复方式：重启 Java 应用（启动时自动对账），或运行 python tools/reconcile_index.py")
    return 1 if unhealthy else 0


if __name__ == "__main__":
    sys.exit(main())
