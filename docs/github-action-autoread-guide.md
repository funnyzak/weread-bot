# GitHub Action 自动阅读配置指南

## 📋 概述

使用 GitHub Action 可以让你的微信读书自动阅读程序在云端自动运行，无需本地电脑24小时开机。本指南将详细介绍如何配置和使用 GitHub Action 进行自动阅读。

## 🚀 快速开始

### 步骤 1: Fork 项目

1. 访问 [WeRead Bot 项目主页](https://github.com/funnyzak/weread-bot)
2. 点击右上角的 **Fork** 按钮
3. 选择你的 GitHub 账户，完成 Fork

### 步骤 2: 配置 Secrets

Fork 完成后，需要在你的仓库中配置必要的环境变量：

1. 进入你 Fork 的仓库
2. 点击 **Settings** 选项卡
3. 在左侧菜单中选择 **Secrets and variables** → **Actions**
4. 点击 **New repository secret** 添加以下配置：

#### 必需配置

| Secret 名称 | 说明 | 获取方法 |
|------------|------|----------|
| `WEREAD_CURL_STRING` | 微信读书的 cURL 请求字符串 | 参考主文档的"获取 cURL 字符串"章节 |

#### 多用户

- 将多个 cURL 片段写入同一个 `WEREAD_CURL_STRING`，**片段之间至少插入两个空行**，程序会自动拆分为多个用户。
- 通过 `MAX_CONCURRENT_USERS` 控制并发执行账号数量，默认 1 表示顺序执行，建议从 1 开始再逐步提高。
- 单个片段只绑定一个账号的 cURL，确保不同用户分段清晰，避免粘连。

示例（Secret 内容，注意两空行分隔）：

```
curl 'https://weread.qq.com/web/book/read' -H 'cookie: wr_skey=user1; ...' --data-raw '{...}'


curl 'https://weread.qq.com/web/book/read' -H 'cookie: wr_skey=user2; ...' --data-raw '{...}'
```

#### 可选运行配置

| Secret 名称 | 说明 | 默认值 |
|------------|------|------|
| `TARGET_DURATION` | 默认阅读时长，格式如 `5-10`；用于定时触发或手动触发留空时的默认值 | 1-2 |
| `MAX_CONCURRENT_USERS` | 多用户并发数量（>=1） | 1 |
| `HACK_COOKIE_REFRESH_QL` | Cookie 刷新兼容开关全局默认值，遇到刷新失败可切换 true/false | false |
| `NOTIFICATION_ONLY_ON_FAILURE` | 仅失败通知开关（true/false），覆盖 workflow 运行参数 | false |
| `HISTORY_ENABLED` | 是否启用执行历史持久化 | true |
| `HISTORY_FILE` | 执行历史输出路径 | logs/run-history.json |
| `HISTORY_MAX_ENTRIES` | 最近执行记录保留条数 | 50 |
| `HISTORY_PERSIST_RUNTIME_ERROR` | 运行时异常是否写入失败历史 | true |

#### 可选通知配置

根据你使用的通知方式，添加相应的 Secret：

**PushPlus 推送加**
| Secret 名称 | 说明 |
|------------|------|
| `PUSHPLUS_TOKEN` | PushPlus 的推送令牌 |

**Telegram 通知**
| Secret 名称 | 说明 |
|------------|------|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token |
| `TELEGRAM_CHAT_ID` | Telegram Chat ID |

**WxPusher 通知**
| Secret 名称 | 说明 |
|------------|------|
| `WXPUSHER_SPT` | WxPusher 的 SPT |

**Bark 通知**
| Secret 名称 | 说明 |
|------------|------|
| `BARK_SERVER` | Bark 服务器地址 |
| `BARK_DEVICE_KEY` | Bark 设备密钥 |
| `BARK_SOUND` | Bark 推送声音（可选） |

**Ntfy 通知**
| Secret 名称 | 说明 |
|------------|------|
| `NTFY_SERVER` | Ntfy 服务器地址 |
| `NTFY_TOPIC` | Ntfy 主题 |
| `NTFY_TOKEN` | Ntfy 访问令牌（可选） |

**Apprise 通用通知**
| Secret 名称 | 说明 |
|------------|------|
| `APPRISE_URL` | Apprise 通知 URL |

> **获取方式**：支持 Discord、Slack、Email 等数十种服务，详见 [Apprise 文档](https://github.com/caronc/apprise)

**飞书通知**
| Secret 名称 | 说明 |
|------------|------|
| `FEISHU_WEBHOOK_URL` | 飞书机器人 Webhook URL |
| `FEISHU_MSG_TYPE` | 消息类型：text/rich_text（可选） |

> **获取方式**：
> 1. 在飞书桌面版群聊中添加机器人
> 2. 选择"自定义机器人"
> 3. 获取 Webhook URL
> 4. 示例：`https://open.feishu.cn/open-apis/bot/v2/hook/your_webhook_token`

**企业微信通知**
| Secret 名称 | 说明 |
|------------|------|
| `WEWORK_WEBHOOK_URL` | 企业微信机器人 Webhook URL |
| `WEWORK_MSG_TYPE` | 消息类型：text/markdown/news（可选） |

> **获取方式**：
> 1. 在企业微信群聊中添加机器人
> 2. 选择"自定义机器人"
> 3. 获取 Webhook URL
> 4. 示例：`https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=your_webhook_key`

**钉钉通知**
| Secret 名称 | 说明 |
|------------|------|
| `DINGTALK_WEBHOOK_URL` | 钉钉机器人 Webhook URL |
| `DINGTALK_MSG_TYPE` | 消息类型：text/markdown/link（可选） |

> **获取方式**：
> 1. 在钉钉群聊中添加机器人
> 2. 选择"自定义机器人"
> 3. 获取 Webhook URL
> 4. 示例：`https://oapi.dingtalk.com/robot/send?access_token=your_access_token`

**GOTify 通知**
| Secret 名称 | 说明 |
|------------|------|
| `GOTIFY_SERVER` | GOTify 服务器地址 |
| `GOTIFY_TOKEN` | GOTify 访问令牌 |
| `GOTIFY_PRIORITY` | 消息优先级（可选，默认 5） |
| `GOTIFY_TITLE` | 消息标题（可选） |

> **获取方式**：
> 1. 访问你的 GOTify 服务器，登录后进入“应用”页面，创建新应用以获取访问令牌（Token）。
> 2. GOTify 服务器地址通常为你的部署地址，如 `https://gotify.example.com`。
> 3. 优先级和标题可根据需要自定义，留空则使用默认值。


**代理配置（可选）**
| Secret 名称 | 说明 |
|------------|------|
| `HTTP_PROXY` | HTTP 代理地址 |
| `HTTPS_PROXY` | HTTPS 代理地址 |

**Hack 配置（可选）**
| Secret 名称 | 说明 | 默认值 |
|------------|------|--------|
| `HACK_COOKIE_REFRESH_QL` | Cookie刷新时ql属性值设置 | `false` |

> **Hack 配置说明：**
> - `HACK_COOKIE_REFRESH_QL`: 控制Cookie刷新请求中的`ql`参数值，作为全局默认值
>   - `false` (默认): 使用`"ql": false`
>   - `true`: 使用`"ql": true`
> - 根据不同用户的环境，可能需要设置为True或False来确保cookie刷新正常工作
> - 如果遇到cookie刷新失败的问题，可以尝试切换此配置的值
> - 建议先使用默认值，如果出现cookie相关错误再尝试修改
> - GitHub Actions Secrets 只能设置全局默认值；如果多用户需要不同取值，请改用配置文件中的 `curl_config.users[].cookie_refresh_ql`

### 步骤 3: 启用 GitHub Actions

1. 在你的仓库中点击 **Actions** 选项卡
2. 如果看到"Actions are disabled"提示，点击 **I understand my workflows, go ahead and enable them**
3. 找到 **Auto Reading Bot** workflow

### 步骤 4: 运行 Action

#### 手动触发

1. 在 **Actions** 页面，选择 **Auto Reading Bot** workflow
2. 点击 **Run workflow** 按钮
3. 配置运行参数：
   - **阅读时长**: 格式为 `60-90`，表示随机 60-90 分钟；留空时优先使用仓库 Secret `TARGET_DURATION`，否则默认 `1-2`
   - **阅读模式**: 选择阅读策略
   - **启用通知**: 是否发送完成通知
   - **启用执行历史**: 是否在运行后保存最近执行记录
   - **历史保留条数**: 最近执行记录最多保留多少条

#### 定时触发（可选）

Fork 后默认不会自动定时运行，因为仓库中的 `.github/workflows/auto-reading.yml` 仍然把 `schedule` 注释掉了。若希望自动定时运行，必须先取消该注释，再按需要调整 cron 表达式：

```yaml
on:
  # 取消注释以下行启用定时触发
  schedule:
    - cron: '0 0 * * *'    # UTC 00:00 = 北京时间 08:00
    - cron: '0 12 * * *'   # UTC 12:00 = 北京时间 20:00
```

## ⚙️ 配置参数说明

### 阅读模式

| 模式 | 说明 |
|------|------|
| `smart_random` | 智能随机模式，优先继续当前书籍和章节 |
| `sequential` | 顺序阅读模式，按书籍顺序阅读 |
| `pure_random` | 纯随机模式，完全随机选择书籍和章节 |

### 运行参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `target_duration` | 留空 | 手动触发时可直接填写；留空则优先使用 Secret `TARGET_DURATION`，否则回退到 `1-2` |
| `reading_mode` | `smart_random` | 阅读模式 |
| `notify_enabled` | `true` | 是否启用通知 |
| `notify_only_on_failure` | `false` | 仅失败时发送通知 |
| `history_enabled` | `true` | 是否启用执行历史持久化 |
| `history_max_entries` | `50` | 执行历史最多保留多少条 |

当在 GitHub Actions 中手动触发 `auto-reading.yml` 时，可以直接在界面填写 `target_duration` 覆盖本次阅读时长；若留空，则 workflow 会优先读取仓库 Secret `TARGET_DURATION`，再回退到默认值 `1-2`。这对 fork 后不想改 workflow 代码、但想给定时任务设置默认时长的场景尤其有用。

同时，你也可以直接在界面勾选以上两个通知开关：`notify_enabled` 控制是否生成阅读成功摘要，`notify_only_on_failure` 则对应 `config.yaml` 中的 `notification.only_on_failure`，会自动关闭 `session_success` 和 `multi_user_summary` 两类成功事件，仅保留失败/异常通知。

如果希望默认采用“仅失败通知”策略（无需每次触发都勾选），可以设置仓库 Secret `NOTIFICATION_ONLY_ON_FAILURE=true`。该 Secret 会通过环境变量覆盖运行参数，在 workflow 中自动传递给 `NOTIFICATION_ONLY_ON_FAILURE`。

执行历史同样支持“仓库 Secret 默认值 + 手动触发临时覆盖”的组合方式。默认情况下，workflow 会把 `logs/run-history.json` 与 `logs/weread.log` 一起上传为 artifact；如果你通过 Secret 自定义了 `HISTORY_FILE`，建议同步调整 workflow 中的 artifact 路径。

## 🎯 高级配置

### 自定义配置文件

如需更详细的配置，可以修改 workflow 文件中的 config.yaml 内容：

```yaml
human_simulation:
  enabled: true
  reading_speed_variation: true
  break_probability: 0.15        # 休息概率
  break_duration: "30-180"       # 休息时长范围
  rotate_user_agent: false       # 是否轮换 User-Agent

network:
  timeout: 30                    # 请求超时时间
  retry_times: 3                 # 重试次数
  retry_delay: "5-15"           # 重试延迟范围
  rate_limit: 10                # 速率限制（请求/秒）

history:
  enabled: true                  # 是否记录最近执行历史
  file: "logs/run-history.json"  # 历史文件路径
  max_entries: 50                # 最多保留最近 50 条
  persist_runtime_error: true    # 运行时异常也落失败记录
```

## 📊 运行监控

### 查看运行日志与历史

1. 在 **Actions** 页面选择具体的运行记录
2. 点击 **auto-reading** job
3. 展开 **Run WeRead Bot** 步骤查看详细日志
4. 在页面底部 **Artifacts** 区域下载 `weread-runtime-<run_id>`，查看 `logs/weread.log` 和 `logs/run-history.json`

### 运行状态

- ✅ **成功**: 阅读任务正常完成
- ❌ **失败**: 检查错误日志，通常是配置问题
- ⏸️ **取消**: 手动取消或超时（2小时）

## ❓ 常见问题

### Q: Action 运行失败怎么办？

A: 检查以下几点：
1. `WEREAD_CURL_STRING` 是否正确配置
2. cURL 字符串是否已过期（建议定期更新）
3. 查看运行日志中的具体错误信息

### Q: 如何更新 cURL 字符串？

A: 
1. 重新从微信读书网页版获取 cURL 字符串
2. 在仓库 Settings → Secrets 中更新 `WEREAD_CURL_STRING`

### Q: 可以同时运行多个 Action 吗？

A: 不建议同时运行多个相同账户的 Action，可能导致账户异常。如需多账户，请使用不同的配置。

### Q: GitHub Actions 有使用限制吗？

A: 是的，GitHub 免费账户每月有 2000 分钟的 Actions 使用时间。本项目单次运行通常消耗 60-120 分钟。

### Q: 如何设置定时运行？

A: 先取消 `.github/workflows/auto-reading.yml` 中 `schedule` 部分的注释，并根据需要调整 cron 表达式。注意时间为 UTC 时间。如果你 fork 后不想继续改代码，但想调整默认阅读时长，可以额外配置仓库 Secret `TARGET_DURATION`，例如 `5-10`。

### Q: GitHub Actions 里的执行历史保存在哪里？

A: 当前 workflow 会在任务结束后上传 artifact，默认包含 `logs/weread.log` 和 `logs/run-history.json`。进入单次运行详情页后，在底部 **Artifacts** 区域下载即可。

### Q: 遇到 Cookie 刷新失败怎么办？

A: 这可能是 `cookie_refresh_ql` 配置问题：
1. 在仓库 Settings → Secrets 中添加 `HACK_COOKIE_REFRESH_QL`
2. 如果当前设置为 `false`，尝试设置为 `true`
3. 如果当前设置为 `true`，尝试设置为 `false`
4. 重新运行 Action 测试
5. 如果是多用户且仅部分账号失败，请改用配置文件，为对应账号单独设置 `curl_config.users[].cookie_refresh_ql`

### Q: 如何判断是否需要调整 Hack 配置？

A: 查看运行日志中的错误信息：
- 搜索关键词：`cookie`、`refresh`、`ql`、`认证`
- 如果看到 Cookie 相关错误，尝试调整 `HACK_COOKIE_REFRESH_QL` 配置
- 如果只有某个账号失败，优先检查该账号是否需要单独设置 `curl_config.users[].cookie_refresh_ql`
- 如果看到 401/403 认证错误，也可能是此配置问题

## 🔒 安全提示

1. **不要在公开仓库中暴露** cURL 字符串或其他敏感信息
2. **定期更新** cURL 字符串以保持有效性
3. **合理设置**运行频率，避免被检测为异常行为
4. **及时关注**账户状态，如有异常立即停止使用

---

如有问题或建议，欢迎在 [Issues](../../issues) 中反馈。
