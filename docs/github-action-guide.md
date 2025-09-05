# GitHub Action 自动阅读配置指南

## 📋 概述

使用 GitHub Action 可以让你的微信读书自动阅读程序在云端自动运行，无需本地电脑24小时开机。本指南将详细介绍如何配置和使用 GitHub Action 进行自动阅读。

## 🚀 快速开始

### 步骤 1: Fork 项目

1. 访问 [WeRead Bot 项目主页](https://github.com/your-username/weread-bot)
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

**代理配置（可选）**
| Secret 名称 | 说明 |
|------------|------|
| `HTTP_PROXY` | HTTP 代理地址 |
| `HTTPS_PROXY` | HTTPS 代理地址 |

### 步骤 3: 启用 GitHub Actions

1. 在你的仓库中点击 **Actions** 选项卡
2. 如果看到"Actions are disabled"提示，点击 **I understand my workflows, go ahead and enable them**
3. 找到 **Auto Reading Bot** workflow

### 步骤 4: 运行 Action

#### 手动触发

1. 在 **Actions** 页面，选择 **Auto Reading Bot** workflow
2. 点击 **Run workflow** 按钮
3. 配置运行参数：
   - **阅读时长**: 格式为 `60-90`，表示随机 60-90 分钟
   - **阅读模式**: 选择阅读策略
   - **启用通知**: 是否发送完成通知

#### 定时触发（可选）

如需启用定时运行，修改 `.github/workflows/auto-reading.yml` 文件：

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
| `target_duration` | `45-90` | 阅读时长范围（分钟） |
| `reading_mode` | `smart_random` | 阅读模式 |
| `notify_enabled` | `true` | 是否启用通知 |

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
```

## 📊 运行监控

### 查看运行日志

1. 在 **Actions** 页面选择具体的运行记录
2. 点击 **auto-reading** job
3. 展开 **Run WeRead Bot** 步骤查看详细日志

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

A: 取消 workflow 文件中 schedule 部分的注释，并根据需要调整 cron 表达式。注意时间为 UTC 时间。

## 🔒 安全提示

1. **不要在公开仓库中暴露** cURL 字符串或其他敏感信息
2. **定期更新** cURL 字符串以保持有效性
3. **合理设置**运行频率，避免被检测为异常行为
4. **及时关注**账户状态，如有异常立即停止使用

---

如有问题或建议，欢迎在 [Issues](../../issues) 中反馈。
