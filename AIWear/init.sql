drop table if exists `users`;

CREATE TABLE users
(
    id            BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '用户ID，主键，自增长，从10000001开始',
    username      VARCHAR(50)  NOT NULL UNIQUE COMMENT '用户名，唯一标识，用于登录和显示',
    email         VARCHAR(100) UNIQUE COMMENT '邮箱地址，唯一，用于登录和通知',
    password_hash VARCHAR(255) COMMENT '密码哈希值，使用BCrypt加密存储',
    INDEX idx_email (email),
    INDEX idx_username (username)
) COMMENT '用户表' CHARSET = utf8mb4  AUTO_INCREMENT = 10000001;

drop table if exists `files`;
CREATE TABLE files
(
    id               BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '用户ID，主键，自增长，从10000001开始',
    user_id          BIGINT        NOT NULL COMMENT '上传用户ID',
    file_name        VARCHAR(255)  NOT NULL COMMENT '图片文件名',
    file_size        BIGINT        NOT NULL COMMENT '图片大小（字节）',
    oss_url          VARCHAR(500)  NOT NULL COMMENT 'OSS访问地址',
    description      VARCHAR(1000) NULL COMMENT '图片文字描述（大模型生成）',
    category         VARCHAR(20)   NULL COMMENT 'clothing/person/other/空串',
    `vector`         TEXT          NULL COMMENT 'CLIP向量（JSON数组文本，512维）',
    vector_status    VARCHAR(20)   NOT NULL DEFAULT 'PENDING'
        COMMENT 'PENDING/READY/FAILED（仅描述MySQL里有没有可用向量，不代表Redis状态）',
    vector_updated_at DATETIME     NULL COMMENT '向量写入MySQL的时间',
    INDEX idx_user_id (user_id)
) COMMENT '图片表' CHARSET = utf8mb4  AUTO_INCREMENT = 10000001;

drop table if exists `records`;
CREATE TABLE `records` (
   `id` BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '记录ID',
   `user_id` BIGINT NOT NULL COMMENT '用户ID',
   `action` VARCHAR(20) NOT NULL COMMENT '动作类型：edit/merge',
   `input_oss_url1` VARCHAR(500) NOT NULL COMMENT '输入图片1 OSS地址',
   `input_oss_url2` VARCHAR(500) COMMENT '输入图片2 OSS地址（merge用）',
   `instruction` VARCHAR(1000) COMMENT '用户提示词',
   `result_url` VARCHAR(1000) COMMENT 'Python返回的临时图片URL',
   `output_oss_url` VARCHAR(500) COMMENT '输出图片 OSS地址',
    INDEX `idx_user_id` (`user_id`)
) COMMENT '请求记录表' ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 AUTO_INCREMENT = 10000001;