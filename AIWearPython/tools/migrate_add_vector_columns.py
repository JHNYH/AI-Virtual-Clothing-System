"""迁移：给 files 表加上向量相关列（幂等，已存在的列会跳过）。

对应 SQL 文件：AIWear/sql/migrate_vector_columns.sql
本脚本额外做一件事：执行前先把 files 全表导出成 JSON 备份。

默认只预览；确认无误后加 --apply 才真正执行。

用法：
    python tools/migrate_add_vector_columns.py            # 预览
    python tools/migrate_add_vector_columns.py --apply    # 执行（先自动备份）
"""
import argparse
import json
import sys
import time
from pathlib import Path

from _common import mysql_conn

COLUMNS = [
    ("description", "ALTER TABLE files ADD COLUMN description VARCHAR(1000) NULL "
                    "COMMENT '图片文字描述（大模型生成）' AFTER oss_url"),
    ("category", "ALTER TABLE files ADD COLUMN category VARCHAR(20) NULL "
                 "COMMENT 'clothing/person/other/空串' AFTER description"),
    ("vector", "ALTER TABLE files ADD COLUMN `vector` TEXT NULL "
               "COMMENT 'CLIP向量（JSON数组文本，512维）' AFTER category"),
    ("vector_status", "ALTER TABLE files ADD COLUMN vector_status VARCHAR(20) NOT NULL DEFAULT 'PENDING' "
                      "COMMENT 'PENDING/READY/FAILED（仅描述MySQL里有没有可用向量，不代表Redis状态）' "
                      "AFTER `vector`"),
    ("vector_updated_at", "ALTER TABLE files ADD COLUMN vector_updated_at DATETIME NULL "
                          "COMMENT '向量写入MySQL的时间' AFTER vector_status"),
]


def main():
    parser = argparse.ArgumentParser(description="为 files 表添加向量相关列")
    parser.add_argument("--apply", action="store_true", help="真正执行（默认只预览）")
    args = parser.parse_args()

    conn = mysql_conn()
    cur = conn.cursor()
    cur.execute("SHOW COLUMNS FROM files")
    cols = [r[0] for r in cur.fetchall()]

    todo = [(name, ddl) for name, ddl in COLUMNS if name not in cols]
    if not todo:
        print("所有列都已存在，无需迁移")
        return 0

    print("将要新增的列：")
    for name, _ in todo:
        print(f"  {name}")
    print(f"已有列：{cols}")

    if not args.apply:
        print("\n（预览模式，未做任何修改。确认后加 --apply 执行）")
        return 0

    # 备份
    cur.execute(f"SELECT {', '.join('`' + c + '`' for c in cols)} FROM files")
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    backup = Path(__file__).resolve().parent / f"files_backup_{time.strftime('%Y%m%d_%H%M%S')}.json"
    backup.write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n已备份 {len(rows)} 行 -> {backup}")

    for name, ddl in todo:
        cur.execute(ddl)
        print(f"  已新增列 {name}")
    conn.commit()

    cur.execute("SHOW COLUMNS FROM files")
    print("\n迁移后的列：")
    for r in cur.fetchall():
        print(f"  {r[0]:<18} {r[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
