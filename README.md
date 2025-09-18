# WeRead Bot: 微信读书阅读机器人

[![Auto Reading Bot](https://img.shields.io/github/actions/workflow/status/funnyzak/weread-bot/auto-reading.yml?style=flat-square&label=Auto%20Reading)](https://github.com/funnyzak/weread-bot/actions/workflows/auto-reading.yml)
[![Docker Tags](https://img.shields.io/docker/v/funnyzak/weread-bot?sort=semver&style=flat-square&label=docker%20image)](https://hub.docker.com/r/funnyzak/weread-bot/)
[![Commit activity](https://img.shields.io/github/commit-activity/m/funnyzak/weread-bot?style=flat-square)](https://hub.docker.com/r/funnyzak/weread-bot/)
[![Python](https://img.shields.io/badge/python-3.9+-blue?style=flat-square)](https://www.python.org/)
[![GitHub license](https://img.shields.io/github/license/funnyzak/weread-bot?style=flat-square)](https://github.com/funnyzak/weread-bot/blob/main/LICENSE)

WeRead Bot 是一个易用的微信读书自动阅读机器人，通过模拟真实用户阅读行为来积累阅读时长，支持多用户多种运行模式（立即执行、定时任务、守护进程），适用于需要提升微信读书等级或完成阅读任务的用户场景。

💗 感谢 [findmover/wxread](https://github.com/findmover/wxread) 提供思路和部分代码支持。

## 核心功能

- ⏰ **智能延迟**：支持启动随机延迟，有效防止固定启动时间特征识别
- 📚 **灵活阅读**：支持时长区间配置（如 30-90 分钟随机），模拟真实阅读习惯
- 👥 **多用户支持**：支持多个微信读书账号顺序执行，每用户可独立配置阅读策略
- 🎲 **多种阅读模式**：智能随机、顺序阅读、纯随机三种模式，满足不同使用场景
- 🤖 **高级行为模拟**：模拟真实用户阅读行为，包括阅读速度变化、中途休息等
- ⚙️ **多样化配置**：支持配置文件、环境变量、命令行参数三种设置方式，灵活适配各种部署环境
- 📊 **详细统计报告**：提供完整的阅读数据、成功率统计和多维度分析
- 📱 **多平台消息推送**：支持 PushPlus、Telegram、WxPusher、Apprise、Bark、Ntfy、飞书、企业微信、钉钉 等通知服务
- 🔧 **智能配置解析**：自动从 CURL 命令提取请求数据、headers 和 cookies，无需手动配置
- 🎯 **精准请求模拟**：使用真实抓包数据，动态生成签名和校验，大幅提高成功率
- 🕐 **灵活定时任务**：支持 cron 表达式定时执行，可自定义执行频率和时间
- 🔄 **守护进程模式**：支持长期运行，自动管理会话间隔，每日会话数量可控
- 🐳 **容器化部署**：提供 Docker 镜像，支持 Docker Compose 一键部署
- ⚡ **云端自动化**：完美支持 GitHub Actions，实现免服务器自动阅读任务

## 运行预览

<img src="https://raw.githubusercontent.com/funnyzak/weread-bot/refs/heads/main/.github/assets/preview.png" alt="运行预览" style="filter: drop-shadow(0 4px 8px rgba(0, 0, 0, 0.2)); border-radius: 8px;"/>

## 快速开始

### 方式一：直接运行（推荐）

```bash
# 1. 下载文件
wget https://raw.githubusercontent.com/funnyzak/weread-bot/refs/heads/main/weread-bot.py
wget https://raw.githubusercontent.com/funnyzak/weread-bot/refs/heads/main/requirements.txt

# 2. 安装依赖
pip install -r requirements.txt

# 3. 设置环境变量
# 设置CURL命令文件路径（推荐）
export WEREAD_CURL_BASH_FILE_PATH="curl_command.txt"
# 或 设置 CURL命令字符串
export WEREAD_CURL_STRING="curl 'https://weread.qq.com/web/book/read' -H 'cookie: wr_skey=user1_key; ...' --data-raw '{...}'"

# 4. 可选配置
export TARGET_DURATION="30-50"        # 目标阅读时长（分钟），此为 30 到 50 分钟随机
export READING_MODE="smart_random"    # 阅读模式
export PUSHPLUS_TOKEN="your_token"    # PushPlus通知token（如需通知）

# 5. 运行程序
python weread-bot.py
```

> 请将第 3 步中的 `curl_command.txt` 替换为实际保存CURL命令的文件路径。获取CURL命令详见[抓包配置详解](#🔧-抓包配置详解)

### 方式二：配置文件运行

```bash
# 1. 下载配置模板
wget https://raw.githubusercontent.com/funnyzak/weread-bot/refs/heads/main/config.yaml.example

# 2. 创建配置文件
cp config.yaml.example config.yaml

# 3. 编辑配置文件
vim config.yaml

# 4. 运行程序
python weread-bot.py --config config.yaml
```

### 方式三：多用户运行

```bash
# 1. 下载配置模板
wget https://raw.githubusercontent.com/funnyzak/weread-bot/refs/heads/main/config.yaml.example

# 2. 创建多用户配置文件进行配置
cp config.yaml.example multiuser-config.yaml

# 3. 为每个用户准备CURL文件
echo "curl 'https://weread.qq.com/web/book/read' -H 'cookie: wr_skey=user1_key; ...' --data-raw '{...}'" > user1_curl.txt
echo "curl 'https://weread.qq.com/web/book/read' -H 'cookie: wr_skey=user2_key; ...' --data-raw '{...}'" > user2_curl.txt

# 5. 编辑配置文件
vim multiuser-config.yaml

# 6. 运行多用户会话
python weread-bot.py --config multiuser-config.yaml
```

### 方式四：GitHub Actions 云端运行

```bash
# 1. Fork 本项目到你的 GitHub 账户
# 2. 在仓库 Settings → Secrets 中配置必要的环境变量
# 3. 在 Actions 页面手动触发或设置定时运行
```

> **详细配置指南**: [GitHub Actions 自动阅读配置指南](https://github.com/funnyzak/weread-bot/blob/main/docs/github-action-autoread-guide.md)

### 方式五：不同运行模式

```bash
# 立即执行（默认）
python weread-bot.py

# 定时执行
python weread-bot.py --mode scheduled

# 守护进程模式
python weread-bot.py --mode daemon

# 详细日志输出
python weread-bot.py --verbose
```

### Docker 方式运行

使用一行命令单次运行：

```bash
docker run -d --name weread-bot \
  --rm \
  -v /path/to/curl_command.txt:/app/curl_command.txt:ro \
  -e TZ="Asia/Shanghai" \
  -e WEREAD_CURL_BASH_FILE_PATH="/app/curl_command.txt" \
  -e TARGET_DURATION="30-50" \
  -e READING_MODE="smart_random" \
  -e PUSHPLUS_TOKEN="your_token" \
  funnyzak/weread-bot:latest
```

> 更多 Docker 方式运行方式，详见 [Docker部署](#docker部署)。

## 配置说明

配置项可通过环境变量或配置文件设置，优先级为：环境变量 > 配置文件 > 程序默认值。 配置文件模板见 [`config.yaml.example`](https://raw.githubusercontent.com/funnyzak/weread-bot/refs/heads/main/config.yaml.example)。

### 必需配置

如果 **未使用配置文件配置**，必须通过环境变量参数提供以下配置：

| 配置项 | 环境变量 | 说明 |
|--------|----------|------|
| CURL配置 | `WEREAD_CURL_STRING` 或 `WEREAD_CURL_BASH_FILE_PATH` | 从微信读书抓包得到的curl命令或命令文件路径 |

- `WEREAD_CURL_STRING`：此环境变量适合在 青龙等面板、GitHub Actions 中直接创建环境变量，内容为完整的CURL命令字符串
- `WEREAD_CURL_BASH_FILE_PATH`：此环境变量适合在本地或Docker中使用，内容为保存CURL命令的文件路径

> 获取CURL命令详见[抓包配置详解](#抓包配置详解)

### 多用户配置

支持通过配置文件配置多个用户的CURL命令和个性化参数，适合需要同时管理多个微信读书账号的场景。

| 配置项 | 配置文件路径 | 说明 |
|--------|-------------|------|
| 多用户模式 | `curl_config.users` | 配置多个用户的CURL文件和个性化参数 |
| 用户名称 | `curl_config.users[].name` | 用户标识名称 |
| CURL文件 | `curl_config.users[].file_path` | 用户专属的CURL文件路径 |
| 个性化配置 | `curl_config.users[].reading_overrides` | 用户特定的阅读参数覆盖 |


### 应用配置

| 配置项 | 环境变量 | 默认值 | 说明 |
|--------|----------|--------|------|
| 启动模式 | `STARTUP_MODE` | `immediate` | immediate/scheduled/daemon |
| 启动延迟 | `STARTUP_DELAY` | `60-120` | 启动随机延迟（秒） |

### 阅读配置

| 配置项 | 环境变量 | 默认值 | 说明 |
|--------|----------|--------|------|
| 阅读模式 | `READING_MODE` | `smart_random` | smart_random/sequential/pure_random |
| 目标时长 | `TARGET_DURATION` | `60-70` | 目标阅读时长（分钟） |
| 阅读间隔 | `READING_INTERVAL` | `25-35` | 每次请求间隔（秒） |
| 书籍连续性 | `BOOK_CONTINUITY` | `0.8` | 继续当前书籍的概率（0-1） |
| 章节连续性 | `CHAPTER_CONTINUITY` | `0.7` | 顺序阅读章节的概率（0-1） |

### 人类行为模拟配置

| 配置项 | 环境变量 | 默认值 | 说明 |
|--------|----------|--------|------|
| 行为模拟 | `HUMAN_SIMULATION_ENABLED` | `true` | 是否启用人类行为模拟 |
| 阅读速度变化 | `READING_SPEED_VARIATION` | `true` | 是否变化阅读速度 |
| 休息概率 | `BREAK_PROBABILITY` | `0.15` | 中途休息概率（0-1） |
| 休息时长 | `BREAK_DURATION` | `30-180` | 休息时长（秒） |
| User-Agent轮换 | `ROTATE_USER_AGENT` | `true` | 是否轮换User-Agent |

### 网络配置

| 配置项 | 环境变量 | 默认值 | 说明 |
|--------|----------|--------|------|
| 超时时间 | `NETWORK_TIMEOUT` | `30` | 网络请求超时（秒） |
| 重试次数 | `RETRY_TIMES` | `3` | 失败重试次数 |
| 重试延迟 | `RETRY_DELAY` | `5-15` | 重试间隔（秒） |
| 频率限制 | `RATE_LIMIT` | `10` | 请求频率（次/分钟） |

### 通知配置

| 配置项 | 环境变量 | 默认值 | 说明 |
|--------|----------|--------|------|
| 通知开关 | `NOTIFICATION_ENABLED` | `true` | 是否启用通知 |
| 包含统计 | `INCLUDE_STATISTICS` | `true` | 是否包含详细统计 |

**注意：通知配置采用多通道模式，支持同时启用多个通知服务**

| 通知服务 | 配置参数 | 环境变量 | 说明 |
|---------|---------|----------|------|
| PushPlus | `token` | `PUSHPLUS_TOKEN` | PushPlus推送token |
| Telegram | `bot_token` | `TELEGRAM_BOT_TOKEN` | Telegram机器人token |
| | `chat_id` | `TELEGRAM_CHAT_ID` | Telegram聊天ID |
| | `proxy.http` | `HTTP_PROXY` | HTTP代理地址 |
| | `proxy.https` | `HTTPS_PROXY` | HTTPS代理地址 |
| WxPusher | `spt` | `WXPUSHER_SPT` | WxPusher SPT |
| Apprise | `url` | `APPRISE_URL` | Apprise通知URL |
| Bark | `server` | `BARK_SERVER` | Bark推送服务器地址 |
| | `device_key` | `BARK_DEVICE_KEY` | Bark设备密钥 |
| | `sound` | `BARK_SOUND` | Bark通知音效 |
| Ntfy | `server` | `NTFY_SERVER` | Ntfy服务器地址 |
| | `topic` | `NTFY_TOPIC` | Ntfy推送主题 |
| | `token` | `NTFY_TOKEN` | Ntfy访问令牌（可选） |
| 飞书 | `webhook_url` | `FEISHU_WEBHOOK_URL` | 飞书机器人Webhook URL |
| | `msg_type` | `FEISHU_MSG_TYPE` | 消息类型：text/rich_text |
| 企业微信 | `webhook_url` | `WEWORK_WEBHOOK_URL` | 企业微信机器人Webhook URL |
| | `msg_type` | `WEWORK_MSG_TYPE` | 消息类型：text/markdown/news |
| 钉钉 | `webhook_url` | `DINGTALK_WEBHOOK_URL` | 钉钉机器人Webhook URL |
| | `msg_type` | `DINGTALK_MSG_TYPE` | 消息类型：text/markdown/link |

### 通知方式详细说明

#### PushPlus
- 获取方式：访问 [pushplus.plus](https://www.pushplus.plus/) 注册获取token
- 配置：设置 `PUSHPLUS_TOKEN` 环境变量

#### Telegram
- 获取方式：
  1. 与 @BotFather 对话创建机器人获取 bot_token
  2. 与 @userinfobot 对话获取 chat_id
- 配置：设置 `TELEGRAM_BOT_TOKEN` 和 `TELEGRAM_CHAT_ID`
- 代理：支持HTTP/HTTPS代理

#### WxPusher
- 获取方式：访问 [wxpusher.zjiecode.com](https://wxpusher.zjiecode.com/) 获取SPT
- 配置：设置 `WXPUSHER_SPT` 环境变量

#### Apprise（支持多种服务）
- 支持：Discord、Slack、Email、企业微信等数十种服务
- 配置：设置 `APPRISE_URL`，格式如：
  - Discord: `discord://webhook_id/webhook_token`
  - Email: `mailto://user:pass@domain.com`
  - 更多格式见：[Apprise文档](https://github.com/caronc/apprise)

#### Bark（iOS推送）
- 获取方式：iOS App Store下载Bark应用，获取设备Key
- 配置：设置 `BARK_SERVER`（默认：https://api.day.app）和 `BARK_DEVICE_KEY`
- 音效：可选设置 `BARK_SOUND`

#### Ntfy（开源推送）
- 获取方式：使用公共服务 [ntfy.sh](https://ntfy.sh) 或自建服务
- 配置：设置 `NTFY_SERVER` 和 `NTFY_TOPIC`
- 私有主题：可选设置 `NTFY_TOKEN`

#### 飞书（Lark）
- 获取方式：
  1. 在飞书群聊中添加机器人
  2. 选择"自定义机器人"
  3. 获取Webhook URL
- 配置：设置 `FEISHU_WEBHOOK_URL`
- 消息格式：支持 `text`（纯文本）和 `rich_text`（富文本）
- 示例：`https://open.feishu.cn/open-apis/bot/v2/hook/your_webhook_token`

#### 企业微信
- 获取方式：
  1. 在企业微信群聊中添加机器人
  2. 选择"自定义机器人"
  3. 获取Webhook URL
- 配置：设置 `WEWORK_WEBHOOK_URL`
- 消息格式：支持 `text`（纯文本）、`markdown`（Markdown格式）、`news`（图文消息）
- 示例：`https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=your_webhook_key`

#### 钉钉
- 获取方式：
  1. 在钉钉群聊中添加机器人
  2. 选择"自定义机器人"
  3. 获取Webhook URL
- 配置：设置 `DINGTALK_WEBHOOK_URL`
- 消息格式：支持 `text`（纯文本）、`markdown`（Markdown格式）、`link`（链接消息）
- 示例：`https://oapi.dingtalk.com/robot/send?access_token=your_access_token`

### 定时任务配置（scheduled模式）
| 配置项 | 环境变量 | 默认值 | 说明 |
|--------|----------|--------|------|
| 定时开关 | `SCHEDULE_ENABLED` | `false` | 是否启用定时任务 |
| Cron表达式 | `CRON_EXPRESSION` | `0 */2 * * *` | 定时执行表达式 |
| 时区 | `TIMEZONE` | `Asia/Shanghai` | 时区设置 |

### 守护进程配置（daemon模式）
| 配置项 | 环境变量 | 默认值 | 说明 |
|--------|----------|--------|------|
| 守护进程开关 | `DAEMON_ENABLED` | `false` | 是否启用守护进程 |
| 会话间隔 | `SESSION_INTERVAL` | `120-180` | 会话间隔时间（分钟） |
| 每日最大会话数 | `MAX_DAILY_SESSIONS` | `12` | 每日最大执行次数 |

## 运行模式详解

### 1. 立即执行模式 (immediate)
```bash
python weread-bot.py
# 或
python weread-bot.py --mode immediate
```
- 程序启动后立即开始一次阅读会话
- 完成目标时长后自动退出
- 适合单次使用或手动控制

### 2. 定时执行模式 (scheduled)
```bash
python weread-bot.py --mode scheduled
```
配置定时任务：
```yaml
schedule:
  enabled: true
  cron_expression: "0 */2 * * *"    # 每2小时执行一次
  timezone: "Asia/Shanghai"
```
支持的cron表达式示例：
- `"0 */2 * * *"` - 每2小时执行一次
- `"30 9 * * *"` - 每天9:30执行
- `"0 * * * *"` - 每小时执行
- `"0 9,18 * * *"` - 每天9点和18点执行

### 3. 守护进程模式 (daemon)

```bash
python weread-bot.py --mode daemon
```

配置守护进程：
```yaml
daemon:
  enabled: true
  session_interval: "120-180"       # 会话间隔2-3小时随机
  max_daily_sessions: 12            # 每天最多12次会话
```

- 程序持续运行，自动管理会话间隔
- 支持每日会话次数限制
- 自动处理跨天重置
- 支持优雅关闭（Ctrl+C）

## 阅读模式详解

### 1. 智能随机模式 (smart_random)

```yaml
reading:
  mode: "smart_random"
  smart_random:
    book_continuity: 0.8          # 80%概率继续当前书籍
    chapter_continuity: 0.7       # 70%概率顺序阅读章节
    book_switch_cooldown: 300     # 换书冷却5分钟
```

- 模拟真实用户的阅读习惯
- 倾向于连续阅读同一本书的连续章节
- 偶尔随机跳转到其他书籍或章节
- 有换书冷却机制，避免频繁切换

### 2. 顺序阅读模式 (sequential)

```yaml
reading:
  mode: "sequential"
```

- 按配置的书籍和章节顺序依次阅读
- 读完一本书后自动切换到下一本
- 最符合正常阅读逻辑

### 3. 纯随机模式 (pure_random)

```yaml
reading:
  mode: "pure_random"
```

- 完全随机选择书籍和章节
- 每次请求都可能跳转到不同位置
- 最大化随机性，但可能不够自然

## 统计报告示例

### 单用户统计报告

```
📊 微信读书自动阅读统计报告

👤 用户: 用户1
⏰ 开始时间: 2024-01-15 09:30:15
⏱️ 实际阅读: 65分32秒
🎯 目标时长: 65分钟
✅ 成功请求: 328次
❌ 失败请求: 5次
📈 成功率: 98.5%
📚 阅读书籍: 3本
📄 阅读章节: 28个
☕ 休息次数: 12次 (共1256秒)
🚀 平均响应: 1.23秒

🎉 本次阅读任务完成！
```

### 多用户统计报告

```
🎭 多用户阅读会话总结

👥 用户统计:
  📊 总用户数: 3
  ✅ 成功用户: 2 (用户1, 用户3)
  ❌ 失败用户: 1 (用户2)

📖 阅读统计:
  ⏱️ 总阅读时长: 128分45秒
  ✅ 总成功请求: 652次
  ❌ 总失败请求: 12次
  📈 整体成功率: 98.2%

🎉 多用户阅读任务完成！
```

## 抓包配置详解

### 获取CURL命令步骤

1. **打开微信读书网页版**：https://weread.qq.com/
2. **登录账号**：确保已登录微信读书账号
3. **开始阅读**：找一本书开始阅读
4. **打开开发者工具**：按F12或右或者浏览器菜单选择“开发者工具”
5. **翻页**：在阅读页面翻页，模拟正常阅读行为
6. **查找请求**：
   - 切换到 Network（网络）标签
   - 在过滤器中输入 `read`
   - 继续翻页，找到 `https://weread.qq.com/web/book/read` 请求
7. **复制CURL**：
   - 右键该请求
   - 选择 `Copy` → `Copy as cURL (bash)`
8. **保存配置**：将复制的内容保存为环境变量或文件

### 智能数据提取

程序会自动从CURL命令中提取：
- **Headers**：包括 User-Agent、Content-Type、Referer 等
- **Cookies**：包括认证相关的 wr_skey、wr_vid 等
- **请求数据**：包括 appId、书籍ID、章节ID 等真实参数

**示例CURL命令结构**：

```bash
curl 'https://weread.qq.com/web/book/read' \
  -H 'accept: application/json, text/plain, */*' \
  -H 'accept-language: zh-CN,zh;q=0.9,en;q=0.8' \
  -H 'content-type: application/json;charset=UTF-8' \
  -H 'cookie: wr_skey=s_abc123; wr_vid=12345678; ...' \
  -H 'origin: https://weread.qq.com' \
  -H 'referer: https://weread.qq.com/web/reader/...' \
  -H 'user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) ...' \
  --data-raw '{"appId":"wb987654321098h765432109","b":"a1b2c3d4e5f6g7h8i9j0k1l","c":"m2n3o4p5q6r7s8t9u0v1w2x","ci":60,"co":123,"sm":"[插图]示例阅读内容","pr":65,"rt":88,"ts":1234567890123,"rn":114,"sg":"abc123def456ghi789jkl012mno345pqr678stu901vwx234yz567890abcdef12","ct":1234567890,"ps":"xxxxxxxxxxxxxxxxxxxxxxxx","pc":"xxxxxxxxxxxxxxxxxxxxxxxx","s":"abc12345"}'
```

### 配置方式选择

**方式1：环境变量（推荐）**

```bash
export WEREAD_CURL_STRING="curl 'https://weread.qq.com/web/book/read' ..."
```

**方式2：文件存储**

```bash
# 保存CURL命令到文件
echo "curl 'https://weread.qq.com/web/book/read' ..." > curl_command.txt
export WEREAD_CURL_BASH_FILE_PATH="curl_command.txt"
```

**方式3：配置文件**

```yaml
curl_config:
  file_path: "curl_command.txt"
```

### 数据提取验证

程序启动时会显示提取结果：

```text
✅ 已从环境变量加载CURL配置
✅ 已使用CURL中的请求数据，包含字段: ['appId', 'b', 'c', 'ci', 'co', 'sm', 'pr', 'rt', 'ts', 'rn', 'sg', 'ct', 'ps', 'pc', 's']
✅ 使用CURL数据作为阅读起点: 书籍 ce032b305a9bc1ce0b0dd2a, 章节 2a3327002582a38a4a932bf
```

## Docker部署

### 运行

```bash
# 运行容器（环境变量方式）
docker run -d \
  -e TZ="Asia/Shanghai" \
  -e WEREAD_CURL_STRING="your_curl_here" \
  -e TARGET_DURATION="60-70" \
  -e PUSHPLUS_TOKEN="your_token" \
  --name weread-bot \
  funnyzak/weread-bot

# 运行容器（配置文件方式）
docker run -d \
  -e TZ="Asia/Shanghai" \
  -v $(pwd)/config.yaml:/app/config.yaml \
  -v $(pwd)/curl_command.txt:/app/curl_command.txt \
  -v $(pwd)/logs:/app/logs \
  --name weread-bot \
  funnyzak/weread-bot

# 守护进程模式
docker run -d \
  -e TZ="Asia/Shanghai" \
  -e WEREAD_CURL_STRING="your_curl_here" \
  -e STARTUP_MODE="daemon" \
  --name weread-daemon \
  funnyzak/weread-bot

# 查看日志
docker logs -f weread-bot
```

### Docker Compose

```yaml
version: '3.8'
services:
  weread-bot:
    image: funnyzak/weread-bot:latest
    container_name: weread-bot
    environment:
      - TZ=Asia/Shanghai
    volumes:
      - ./logs:/app/logs
      - ./config.yaml:/app/config.yaml:ro
      - ./curl_command.txt:/app/curl_command.txt:ro
    restart: unless-stopped
```

运行：

```bash

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f
```

## 高级功能

### 1. 多用户会话管理

```yaml
# 多用户配置结构
curl_config:
  users:
    - name: "用户1"                    # 用户标识名称
      file_path: "user1_curl.txt"      # 用户专属的CURL文件路径
      reading_overrides:               # 用户特定的阅读参数覆盖（可选）
        target_duration: "45-90"       # 阅读时长
        mode: "smart_random"           # 阅读模式
        reading_interval: "30-48"      # 阅读间隔
        use_curl_data_first: true      # 是否优先使用CURL数据
        fallback_to_config: true       # 是否回退到配置数据
    
    - name: "用户2"
      file_path: "user2_curl.txt"
      reading_overrides:
        target_duration: "30-60"
        mode: "sequential"
        reading_interval: "25-35"
```

**多用户执行特性：**

- **顺序执行**：用户按配置顺序依次执行，避免同时请求
- **用户间隔**：每个用户完成后有30-60秒的间隔延迟
- **独立配置**：每个用户可以有不同的阅读策略和时长
- **错误隔离**：单个用户失败不影响其他用户执行
- **统计汇总**：提供单用户和多用户的详细统计报告

**配置覆盖优先级：**

1. **用户特定配置** (`reading_overrides`) - 最高优先级
2. **全局配置** (`reading`) - 默认配置  
3. **程序默认值** - 最低优先级

### 2. 智能书籍管理

```yaml
reading:
  # 书籍配置列表
  # 章节索引优先级：配置的索引值 > 自动计算的索引 > CURL提取的值
  books:
    - name: "深度工作"                    # 书籍名称
      book_id: "book_id_1"               # 书籍ID
      chapters:                          # 章节配置，支持新旧两种格式
        # 新格式：包含章节ID和可选的章节索引（推荐）
        - chapter_id: "chapter_1"
          chapter_index: 60              # 可选：微信读书官方章节索引ID
        - chapter_id: "chapter_2"
          chapter_index: 61              # 可选：微信读书官方章节索引ID
        # 旧格式：只有章节ID（向后兼容）
        - "chapter_3"                    # 兼容旧格式，章节索引将自动计算或从CURL提取
    
    - name: "原则"
      book_id: "book_id_2"
      chapters:
        # 也可以使用简化的字段名
        - id: "chapter_a"
          index: 25                      # 使用简化字段名
        # 混合使用新旧格式
        - "chapter_b"                    # 旧格式
  
  # 智能随机策略
  smart_random:
    book_continuity: 0.8          # 书籍连续性
    chapter_continuity: 0.7       # 章节连续性
    book_switch_cooldown: 300     # 换书冷却
```

#### 章节索引配置说明

**什么是章节索引（ci）？**
- 章节索引是微信读书为每个章节分配的专有数字标识符
- 与章节ID（c）不同，章节索引通常是连续的数字（如：60, 61, 62...）

**配置格式：**
1. **新格式（推荐）**：包含章节ID和可选的章节索引
   ```yaml
   - chapter_id: "9bf32f301f9bf31c7ff0a60"
     chapter_index: 60
   ```
   或使用简化字段名：
   ```yaml
   - id: "9bf32f301f9bf31c7ff0a60"
     index: 60
   ```

2. **旧格式（兼容）**：只有章节ID字符串
   ```yaml
   - "9bf32f301f9bf31c7ff0a60"
   ```

**章节索引优先级：**
1. **配置的索引值**：在配置文件中明确指定的 `chapter_index` 或 `index`
2. **自动计算的索引**：章节在配置列表中的位置（从0开始）
3. **CURL提取的值**：从抓取的CURL命令中提取的 `ci` 值

**如何获取章节索引？**
1. 在微信读书网页版翻页时，查看Network请求中的 `ci` 字段值
2. 不同章节的 `ci` 值通常是连续递增的数字

### 3. 高级网络配置

```yaml
network:
  timeout: 30                     # 请求超时
  retry_times: 3                  # 重试次数
  retry_delay: "5-15"            # 重试延迟
  rate_limit: 10                 # 频率限制（请求/分钟）
```

### 4. 多平台通知支持

```yaml
notification:
  enabled: true
  include_statistics: true       # 包含详细统计
  
  # 通知通道配置（支持多个通道同时使用）
  channels:
    # 通道1：PushPlus
    - name: "pushplus"
      enabled: true
      config:
        token: "${PUSHPLUS_TOKEN}"
    
    # 通道2：Telegram
    - name: "telegram"
      enabled: true
      config:
        bot_token: "${TELEGRAM_BOT_TOKEN}"
        chat_id: "${TELEGRAM_CHAT_ID}"
        proxy:
          http: "${HTTP_PROXY}"
          https: "${HTTPS_PROXY}"
    
    # 通道3：WxPusher
    - name: "wxpusher"
      enabled: false
      config:
        spt: "${WXPUSHER_SPT}"
    
    # 通道4：Apprise
    - name: "apprise"
      enabled: false
      config:
        # Apprise通知URL，支持多种服务（如Discord、Slack、Email等）
        # 示例：discord://webhook_id/webhook_token
        # 示例：mailto://user:pass@domain.com
        # 详见：https://github.com/caronc/apprise
        url: "${APPRISE_URL}"
    
    # 通道5：Bark
    - name: "bark"
      enabled: false
      config:
        # Bark服务器地址
        server: "${BARK_SERVER}"     # 如：https://api.day.app
        # 设备Key
        device_key: "${BARK_DEVICE_KEY}"
        # 通知音效（可选）
        sound: "${BARK_SOUND}"
    
    # 通道6：Ntfy
    - name: "ntfy"
      enabled: false
      config:
        # Ntfy服务器地址（默认：https://ntfy.sh）
        server: "${NTFY_SERVER}"     # 如：https://ntfy.sh
        # 主题名称
        topic: "${NTFY_TOPIC}"
        # 访问令牌（可选，用于私有主题）
        token: "${NTFY_TOKEN}"
    
    # 通道7：飞书
    - name: "feishu"
      enabled: false
      config:
        # 飞书机器人Webhook URL
        webhook_url: "${FEISHU_WEBHOOK_URL}"
        # 消息类型：text(纯文本), rich_text(富文本)
        msg_type: "text"
    
    # 通道8：企业微信
    - name: "wework"
      enabled: false
      config:
        # 企业微信机器人Webhook URL
        webhook_url: "${WEWORK_WEBHOOK_URL}"
        # 消息类型：text(纯文本), markdown(Markdown), news(图文)
        msg_type: "text"
    
    # 通道9：钉钉
    - name: "dingtalk"
      enabled: false
      config:
        # 钉钉机器人Webhook URL
        webhook_url: "${DINGTALK_WEBHOOK_URL}"
        # 消息类型：text(纯文本), markdown(Markdown), link(链接)
        msg_type: "text"
```

## 微信读书API字段说明

程序会自动从CURL命令中提取并处理这些字段，无需手动配置：

| 字段 | 示例值 | 说明 | 处理方式 |
|------|--------|------|----------|
| `appId` | `"wb115321887466h953405538"` | 应用唯一标识符 | 从CURL提取，保持不变 |
| `b` | `"241325c071f385dd2417ff2"` | 书籍ID | 智能管理，支持多书籍切换 |
| `c` | `"02e32f0021b02e74f10ece8"` | 章节ID | 智能管理，支持章节跳转 |
| `ci` | `60` | 章节索引 | 智能管理，支持配置和自动计算 |
| `co` | `336` | 内容位置/页码 | 从CURL提取，保持不变 |
| `sm` | `"2　开启你的专注之路有一篇名为《算术"` | 当前阅读内容摘要 | 从CURL提取，保持不变 |
| `pr` | `65` | 页码/段落索引 | 从CURL提取，保持不变 |
| `rt` | `88` | 阅读时长（秒） | 动态计算，模拟真实阅读时间 |
| `ts` | `1727580815581` | 时间戳（毫秒） | 动态生成，包含随机偏移 |
| `rn` | `114` | 随机数/请求编号 | 动态生成随机数 |
| `sg` | `"bfdf7de...e22e724"` | 安全签名 | 动态计算SHA256签名 |
| `ct` | `1727580815` | 时间戳（秒） | 动态生成当前时间 |
| `ps` | `"xxxxxxxx"` | 用户标识符 | 从CURL提取，保持不变 |
| `pc` | `"xxxxxxxx"` | 设备标识符 | 从CURL提取，保持不变 |
| `s` | `"fadcb9de"` | 数据校验和 | 动态计算哈希值 |

### 安全机制
- **签名算法**：使用时间戳、随机数和密钥生成SHA256签名
- **数据校验**：通过特定算法计算请求数据的校验和
- **时间同步**：动态生成符合服务器要求的时间戳
- **Cookie管理**：自动刷新和维护认证Cookie

## 常见问题

### Q: 如何防止被微信识别为机器人？

**A: 内置多层防检测机制：**
- **启动延迟**：60-120秒随机延迟，避免批量启动特征
- **阅读速度变化**：每30秒调整阅读速度（0.8-1.3倍）
- **中途休息**：15%概率随机休息30-180秒
- **智能换书**：基于概率的书籍和章节切换
- **时间戳随机化**：请求时间包含随机偏移
- **Cookie自动刷新**：维护有效的认证状态

### Q: 程序运行多长时间？

**A: 灵活的时长控制：**
- **默认时长**：60-70分钟随机选择
- **自定义区间**：支持如`"60-120"`的区间配置
- **智能完成**：达到目标时长后自动停止
- **守护模式**：可设置每日最大会话数和间隔时间

### Q: 如何查看运行状态？
**A: 多种监控方式：**
- **实时日志**：详细的运行过程日志
- **进度显示**：当前阅读进度和剩余时间
- **统计报告**：完成后的详细统计信息
- **推送通知**：支持多平台消息推送
- **日志文件**：保存在`logs/weread.log`


### Q: 程序报错"Cookie刷新失败"？
**A: Cookie问题解决：**
- 重新获取最新的CURL命令
- 确保微信读书账号未过期
- 检查网络连接是否正常
- 尝试重启程序让Cookie自动刷新

### Q: 支持多账号同时运行吗？

**A: 支持多用户模式，顺序执行多个账号：**
```yaml
# 多用户配置方式
curl_config:
  users:
    - name: "账号1"
      file_path: "account1_curl.txt"
      reading_overrides:
        target_duration: "45-90"
    - name: "账号2"  
      file_path: "account2_curl.txt"
      reading_overrides:
        target_duration: "30-60"
```

**执行特点：**
- 按配置顺序依次执行，避免同时请求
- 每个账号完成后有30-60秒间隔延迟
- 单个账号失败不影响其他账号
- 提供详细的多用户统计报告

**传统方式（并行运行）：**
```bash
# 方法1：多个配置文件
python weread-bot.py --config account1.yaml
python weread-bot.py --config account2.yaml
```

### Q: 多用户模式总执行时间是多少？
**A: 执行时间计算：**
- **总时间** = 所有用户阅读时长之和 + 用户间隔延迟
- **示例**：3个用户，每个60分钟，间隔45秒
  - 总时间 ≈ 180分钟 + 1.5分钟 = 181.5分钟
- **优化建议**：合理设置每个用户的阅读时长，避免总时间过长
- **说明**：总体是依次执行，不是并行执行，避免单次大量请求被识别异常

### Q: 某个用户失败了怎么办？
**A: 错误处理机制：**
- **错误隔离**：单个用户失败不影响其他用户执行
- **详细日志**：记录每个用户的执行状态和错误信息
- **继续执行**：失败用户跳过，继续执行下一个用户
- **统计报告**：最终报告中显示成功和失败的用户列表

### Q: 如何调整阅读策略更自然？
**A: 策略优化建议：**
```yaml
# 更保守的策略
human_simulation:
  break_probability: 0.2        # 增加休息频率
  break_duration: "60-300"      # 延长休息时间
reading:
  target_duration: "45-90"      # 缩短单次时长
  smart_random:
    book_continuity: 0.9        # 提高书籍连续性
    chapter_continuity: 0.8     # 提高章节连续性
```

## 性能优化建议

### 1. 网络优化
```yaml
network:
  timeout: 30              # 根据网络情况调整
  retry_times: 3           # 网络不稳定时增加重试
  retry_delay: "5-15"      # 重试间隔
  rate_limit: 8            # 降低请求频率更安全
```

### 2. 行为优化
```yaml
human_simulation:
  break_probability: 0.2   # 提高休息频率
  break_duration: "60-300" # 延长休息时间
  reading_speed_variation: true
```

### 3. 时长策略
```yaml
reading:
  target_duration: "60-90"   # 较短时长更安全
  reading_interval: "30-45"  # 增加请求间隔
```

## 安全建议

1. **不要分享CURL命令**：包含个人认证信息
2. **定期更新**：Cookie会过期，需要重新获取
3. **适度使用**：避免过度频繁的阅读行为
4. **监控日志**：关注异常和错误信息
5. **备份配置**：保存有效的配置文件

## 鸣谢

特别感谢以下项目提供的实现参考：

- https://github.com/findmover/wxread

## 免责声明

本项目仅供学习和研究目的，不得用于任何商业活动。用户在使用本项目时应遵守所在地区的法律法规，对于违法使用所导致的后果，本项目及作者不承担任何责任。 本项目可能存在未知的缺陷和风险（包括但不限于账号封禁等），使用者应自行承担使用本项目所产生的所有风险及责任。 作者不保证本项目的准确性、完整性、及时性、可靠性，也不承担任何因使用本项目而产生的任何损失或损害责任。 使用本项目即表示您已阅读并同意本免责声明的全部内容。

## 许可证

MIT License
