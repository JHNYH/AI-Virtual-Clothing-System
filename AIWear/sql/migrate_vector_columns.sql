-- 图片向量一致性改造：files 表新增向量相关列
--
-- 背景：原先图片元数据在 MySQL、向量只存在 Redis，Redis 一旦丢数据就出现
--       「我的图片看得见、搜不到」且无法自愈。改造后 MySQL 成为唯一事实来源，
--       Redis 退化为可随时重建的索引。
--
-- 注意：
--   1. 只在已有数据的库上执行本脚本；全新环境用 init.sql 即可（已含这些列）。
--   2. 绝不要在生产库执行 init.sql —— 它开头是 drop table。
--   3. `vector` 加反引号：MySQL 8.x 下它不是保留字，但 9.x 起是，提前规避。

ALTER TABLE files
  ADD COLUMN description       VARCHAR(1000) NULL COMMENT '图片文字描述（大模型生成）'      AFTER oss_url,
  ADD COLUMN category          VARCHAR(20)   NULL COMMENT 'clothing/person/other/空串'      AFTER description,
  ADD COLUMN `vector`          TEXT          NULL COMMENT 'CLIP向量（JSON数组文本，512维）' AFTER category,
  ADD COLUMN vector_status     VARCHAR(20)   NOT NULL DEFAULT 'PENDING'
                                               COMMENT 'PENDING/READY/FAILED（仅描述MySQL里有没有可用向量，不代表Redis状态）' AFTER `vector`,
  ADD COLUMN vector_updated_at DATETIME      NULL COMMENT '向量写入MySQL的时间'             AFTER vector_status;
