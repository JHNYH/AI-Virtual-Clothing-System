# 衣览无余 · AI 虚拟服装搭配平台

一个「上传衣物／人像照片 → 用自然语言指令编辑或合并 → 按文字或图片检索」的图片处理平台。
前后端分离：Java 负责业务与鉴权，Python 负责大模型推理与向量检索。

> 学生演示项目，用于串联 Spring Boot、Flask、Vue 3 与 Docker 的完整工程实践。

---

## 功能

| 功能 | 说明 |
|---|---|
| 注册 / 登录 | 邮箱验证码 或 用户名密码，签发 JWT |
| 我的图片 | 上传图片（内容审核 + 向量化），列表与预览 |
| 图片编辑 | 选一张图 + 自然语言指令 → 生成新图 |
| 图片合并 | 选两张图 + 指令 → 合成新图 |
| 文搜图 / 图搜图 | 在「我的图片」内按描述或按相似图检索 |
| 历史记录 | 编辑 / 合并记录，支持按类型筛选 |

---

## 架构

```
浏览器 (Vue 3 + Element Plus)              :5173
      │  /api/**
      ▼
Java 后端 (Spring Boot 3)                 :8081   ← 鉴权 / 文件 / 记录 / OSS
      │                    │
      │ JDBC               │ HTTP
      ▼                    ▼
  MySQL :3307        Python 服务 (Flask)   :5000
  Redis :6379 ←────── 通义万相 · CLIP 向量检索
```

- **MySQL** 是唯一事实来源（用户、文件元数据、向量文本）
- **Redis** 只存检索索引，可随时按 MySQL 重建
- **阿里云 OSS** 存原图与生成图

---

## 目录结构

```
.
├── AIWear/              Java 后端（Spring Boot 3.2 / Java 17）
│   ├── src/main/java/com/aiwear/
│   │   ├── controller/  接口层
│   │   ├── service/     业务层（User / File / Record / PythonImage / ImageIndex）
│   │   ├── mapper/      MyBatis-Plus
│   │   ├── entity/      实体
│   │   └── util/        JwtUtil / EmailService / OssService / VerificationCodeService
│   ├── src/main/resources/application.yml
│   ├── init.sql         建表脚本
│   └── sql/             增量迁移脚本
├── AIWearPython/        Python 服务（Flask + 通义万相 + CLIP）
│   ├── server.py        对外接口（8 个，均 POST）
│   ├── tools/           Redis 向量索引运维工具
│   ├── skills/          技能链定义
│   └── 自动化测试/       Selenium + pytest
├── fronted/             前端（Vue 3 + Vite）
│   └── src/views/       5 个页面
├── deploy/              Docker Compose 编排 + Nginx / Redis / MySQL 配置
├── 接口测试/            JMeter 测试计划
└── img/                 文档配图与测试素材
```

---

## 技术栈

| 模块 | 技术 |
|---|---|
| `AIWear/` | Java 17 · Spring Boot 3.2 · MyBatis-Plus 3.5 · MySQL · Redis · JWT · 阿里云 OSS |
| `AIWearPython/` | Python · Flask · DashScope(通义万相) · LangChain/LangGraph · CLIP (transformers + torch) |
| `fronted/` | Vue 3 · Vite 7 · Vue Router 4 · Pinia · Element Plus · Axios |
| `deploy/` | Docker Compose · MySQL 8.4 · Redis 7 · Nginx 1.24 |
| `接口测试/` | JMeter 5.6.3 |
| `AIWearPython/自动化测试/` | Selenium 4.25 · pytest |

---

## 快速开始

### 0. 准备配置（必读）

仓库中**不含任何真实凭据**，密码与密钥一律通过环境变量或本地配置文件注入。
首次使用请复制模板并填入自己的值：

```powershell
Copy-Item AIWearPython/.env.example AIWearPython/.env   # Python 服务
Copy-Item deploy/.env.example deploy/.env               # 容器编排
```

Java 侧的凭据读取自以下环境变量，也可在同目录新建
`AIWear/src/main/resources/application-local.yml` 覆盖（该文件已被 `.gitignore` 忽略，
`application.yml` 通过 `spring.config.import` 自动加载它）：

| 变量 | 用途 |
|---|---|
| `MYSQL_PASSWORD` | 数据库密码 |
| `MAIL_PASSWORD` | SMTP 授权码（登录验证码用） |
| `JWT_SECRET` | JWT 签名密钥，**至少 32 字节** |
| `ALIYUN_OSS_ACCESS_KEY_ID` / `ALIYUN_OSS_ACCESS_KEY_SECRET` | 阿里云 OSS 密钥 |

### 1. 启动中间件

```powershell
cd deploy
docker compose -p bite_wear -f docker-compose-mid.yml up -d
```

### 2. 初始化数据库

```bash
mysql -u root -p < AIWear/init.sql
```

> 已有数据的环境不要执行 `init.sql`（它开头是 `drop table`），改用
> `AIWear/sql/migrate_vector_columns.sql`。

### 3. 启动 Python 服务

```powershell
cd AIWearPython
pip install -r requirements.txt
python server.py          # 监听 :5000
```

### 4. 启动 Java 后端

```powershell
cd AIWear
mvn spring-boot:run       # 监听 :8081
```

### 5. 启动前端

```powershell
cd fronted
npm install
npm run dev               # 监听 :5173
```

浏览器打开 <http://localhost:5173>。

---

## 相关文档

- [前端说明](fronted/README.md)
- [检索索引运维工具](AIWearPython/tools/README.md)
- [UI 自动化测试](AIWearPython/自动化测试/README.md)
- [JMeter 接口测试](接口测试/README.md)

---

## 注意事项

- 图片编辑 / 合并会**真实调用大模型**并消耗额度，AI 链路接口请勿高并发压测。
- `deploy/redis/conf/redis.conf` 为**无密码**配置（`bind 0.0.0.0` + `protected-mode no`），
  仅适合本机或内网；对外部署请务必设置 `requirepass` 并限制端口暴露。
- 自动化测试与 JMeter 计划中的默认账号（`zhangsan / 123456`）仅为演示数据。
