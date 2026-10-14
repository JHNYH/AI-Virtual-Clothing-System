# 初始化模板：创建业务库 bite_wear 与 bite 用户
#
# ⚠ 本文件不应包含真实密码。
#   mysql 官方镜像的 /docker-entrypoint-initdb.d 不做环境变量替换，
#   部署前请把下面的 CHANGE_ME 改成你自己的密码，且不要把它提交回仓库。
#
# 1、初始化数据库：创建业务数据库 bite_wear
# 2、创建用户，用户名：bite，密码：CHANGE_ME
# 3、授予 bite 用户特定权限

CREATE database if NOT EXISTS `bite_wear` default character set utf8mb4 collate utf8mb4_general_ci;

CREATE USER 'bite'@'%' IDENTIFIED BY 'CHANGE_ME';
grant replication slave, replication client on *.* to 'bite'@'%';

GRANT ALL PRIVILEGES ON bite_wear.* TO  'bite'@'%';

FLUSH PRIVILEGES;
