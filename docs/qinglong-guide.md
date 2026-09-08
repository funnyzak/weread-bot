# 青龙面板部署

青龙负责定时触发，WeRead Bot 使用 `immediate` 模式，每次完成阅读后退出。以下按青龙当前官方 [Docker 部署说明](https://qinglong.online/guide/getting-started/installation-guide/docker) 和 [内置命令说明](https://qinglong.online/guide/user-guide/basic-explanation) 编写；已有面板可从安装依赖开始。

## 准备青龙面板

在已安装 Docker 的服务器执行：

```bash
mkdir -p "$PWD/ql/data"
docker run -dit \
  --name qinglong \
  --hostname qinglong \
  --restart unless-stopped \
  -p 5700:5700 \
  -e TZ=Asia/Shanghai \
  -v "$PWD/ql/data:/ql/data" \
  whyour/qinglong:latest
```

访问 `http://服务器IP:5700`，完成初始化并设置管理员账号。当前镜像使用 `/ql/data` 保存数据；下文路径均为容器内路径，对应宿主机的 `ql/data/`。例如容器内 `/ql/data/config/weread.yaml` 对应宿主机 `ql/data/config/weread.yaml`。

官方 `latest` 镜像基于 Alpine；如遇 Python 依赖兼容问题，可在新建面板时改用 `whyour/qinglong:debian`。镜像选择见 [青龙官方仓库](https://github.com/whyour/qinglong#版本)。

## 安装依赖与订阅脚本

进入 **依赖管理 → Python3 → 创建依赖**，将 **自动拆分** 设为 **是**，在“名称”中一次粘贴以下六行，保存后等待全部安装成功。已安装的旧依赖需更新到满足本仓库 [`requirements.txt`](../requirements.txt) 的版本：

```text
requests
httpx
PyYAML
urllib3
croniter
apprise
```

进入 **订阅管理 → 创建订阅**，填写：

| 字段 | 填写内容 |
|------|----------|
| 名称 | 微信读书 |
| 类型 | 公开仓库 |
| 链接 | `https://github.com/funnyzak/weread-bot.git` |
| 分支 | `main` |
| 定时类型 | `crontab` |
| 定时规则 | `0 4 * * *`，每天 04:00 更新脚本 |
| 白名单 | `weread-bot.py` |
| 黑名单 | 留空 |
| 依赖文件 | `requirements.txt` |
| 文件后缀 | `py` |
| 自动添加任务 / 自动删除任务 | 均关闭，阅读任务按下文手动创建 |

保存后运行一次订阅，在 **脚本管理** 确认 `weread-bot.py` 已拉取。以下以 `funnyzak_weread-bot_main/weread-bot.py` 为脚本相对路径；请以面板实际显示的目录为准，并替换后续命令中的路径。订阅只更新文件，`requirements.txt` 更新后仍需检查并更新面板里的 Python 依赖。

## 单用户：使用环境变量

进入 **环境变量 → 创建变量**，将 **自动拆分** 设为 **否**，逐项添加并启用以下变量。变量值直接填写内容，不写 `export`，不在整个值外额外包裹引号。保存 cURL 时必须关闭自动拆分，否则青龙会按 `&` 或换行拆成多条变量，破坏请求内容。

| 名称 | 值 | 用途 |
|------|----|------|
| `WEREAD_CURL_STRING` | 当前账号完整的 cURL (bash) 请求 | 必填，获取方式见 [抓包配置详解](../README.md#抓包配置详解) |
| `TARGET_DURATION` | `30-50` | 每次目标阅读时长，单位分钟 |
| `READING_MODE` | `smart_random` | 阅读模式 |
| `STARTUP_DELAY` | `60-300` | 启动随机延迟，单位秒 |
| `MAX_CONCURRENT_USERS` | `1` | 同时执行的账号数 |
| `LOG_FILE` | `/ql/data/log/weread-bot/weread.log` | 程序日志 |
| `HISTORY_FILE` | `/ql/data/log/weread-bot/run-history.json` | 执行历史 |

保留 cURL 内部原有的引号、请求头和请求体。也可把完整请求保存为 `/ql/data/config/weread-user1.txt`，改用 `WEREAD_CURL_BASH_FILE_PATH` 指向该绝对路径，并禁用 `WEREAD_CURL_STRING`。这两种账号来源选一种即可。

需要通知时，再添加本项目支持的通知变量，例如 `PUSHPLUS_TOKEN`；实际值只保存在面板中。通道字段见 [通知配置](../README.md#通知配置)。本项目使用自己的通知配置，不能仅凭青龙系统通知已配置就认为阅读结果也会推送。

## 多用户：共用阅读参数

只创建 **一条** `WEREAD_CURL_STRING` 变量，**自动拆分选择否**。把多个账号的完整 cURL 依次粘贴到值中，每段之间至少留出 **两个空行**：

```text
账号一的完整 cURL 请求


账号二的完整 cURL 请求


账号三的完整 cURL 请求
```

上面仅展示分隔方式，实际填写时将每段说明替换为对应账号的完整请求。不要在同一条 cURL 内插入空白段落，也不要用字面量 `\n`、`&` 或 `@` 分隔账号。

程序会生成 `env_user_1`、`env_user_2` 等用户名称，并共用 `TARGET_DURATION`、`READING_MODE` 等全局参数。`MAX_CONCURRENT_USERS=1` 表示依次执行，改成 `2` 表示最多同时执行两个账号。本指南由脚本内部管理多个账号，不依赖青龙同名变量拼接或 `task conc` 分发。

## 多用户：每个账号独立配置

需要自定义账号名称、阅读时长、阅读模式时，在面板环境变量中分别添加 `WEREAD_USER1_CURL`、`WEREAD_USER2_CURL`，每条均将 **自动拆分设为否**，值各自为一份完整 cURL。禁用前面配置的 `WEREAD_CURL_STRING` / `WEREAD_CURL_BASH_FILE_PATH`，方便维护。

在宿主机持久化目录 `ql/data/config/` 下新建 `weread.yaml`，内容如下。这份配置通过 `${变量名}` 引用面板中的账号数据，不需要把 Cookie 写入 YAML：

```yaml
app:
  startup_mode: "immediate"
  startup_delay: "60-300"
  max_concurrent_users: 1

curl_config:
  users:
    - name: "账号一"
      content: "${WEREAD_USER1_CURL}"
      reading_overrides:
        target_duration: "30-50"
        mode: "smart_random"
    - name: "账号二"
      content: "${WEREAD_USER2_CURL}"
      reading_overrides:
        target_duration: "60-90"
        mode: "sequential"
        reading_interval: "30-48"

reading:
  target_duration: "30-50"
  mode: "smart_random"
  reading_interval: "25-35"

logging:
  file: "/ql/data/log/weread-bot/weread.log"
history:
  file: "/ql/data/log/weread-bot/run-history.json"
```

`WEREAD_USER1_CURL` 等名称由你自定义，必须与 YAML 引用一致；脚本不会自动扫描这些变量。只保留一个 `users` 条目，也可以用于单用户自定义配置。如偏好文件，将该用户的 `content` 替换为 `file_path: "/ql/data/config/weread-user1.txt"`，再把该账号的完整 cURL 保存到对应文件。

配置生效规则：

- YAML 中有 `curl_config.users` 时，优先使用该用户列表，不再从 `WEREAD_CURL_STRING` 生成用户。
- 全局参数按“环境变量 → YAML → 默认值”取值；用户的 `reading_overrides` 再覆盖全局阅读参数。例如账号二明确配置了 `60-90`，全局 `TARGET_DURATION` 不会改变它。
- 用户可覆盖的阅读字段见 [多用户配置](../README.md#多用户配置)。可在用户条目下添加 `cookie_refresh_ql: true` 或 `false`；它控制微信读书 Cookie 刷新请求的字段，与是否部署在青龙面板无关。
- 账号文件、YAML、日志和历史使用绝对路径，避免工作目录变化。个人配置放在 `/ql/data/config/`，不要放进订阅更新的仓库目录。

## 校验配置与创建定时任务

在 **定时任务 → 创建任务** 中创建“微信读书”，**定时类型选择手动运行**，**实例模式选择单实例**。先完成配置校验和真实试跑，再设置常规定时。

环境变量方案先填写以下命令，保存后手动运行：

```bash
task funnyzak_weread-bot_main/weread-bot.py -- --validate-config
```

YAML 方案使用：

```bash
task funnyzak_weread-bot_main/weread-bot.py -- --validate-config --config /ql/data/config/weread.yaml
```

确认日志中的账号数量和来源正确，再将 `--validate-config` 换成 `--dry-run` 检查通知配置。这两个命令不会发起阅读请求，也不能证明 Cookie 当前仍然有效；之后需要手动真实运行一次。

校验通过后，将任务命令改成对应的正式命令。环境变量方案：

```bash
task -m 14400 funnyzak_weread-bot_main/weread-bot.py -- --mode immediate
```

YAML 方案：

```bash
task -m 14400 funnyzak_weread-bot_main/weread-bot.py -- --mode immediate --config /ql/data/config/weread.yaml
```

手动运行并检查日志后，编辑任务，将 **定时类型改为常规定时**，填写 `0 8 * * *`（每天 08:00，按面板时区），保存并确认任务处于启用状态。`--` 前是青龙参数，后面才是脚本参数；`--mode immediate` 确保每次执行后退出，不在青龙任务里再启动 `scheduled` 或 `daemon`。

`-m 14400` 将该任务超时设为 14400 秒（4 小时），只是示例。顺序执行时要按所有账号的目标时长上限之和，加上启动延迟、休息和网络重试时间预留余量；账号较多时提高超时，并拉开两次定时触发的间隔。超时参数的处理见 [青龙 task 实现](https://github.com/whyour/qinglong/blob/develop/shell/task.sh)。

单实例模式在下一次定时触发时会停止尚未结束的旧任务，因此调度间隔应大于整批账号的运行时间。多实例模式允许同一任务重叠运行，本指南建议保持单实例。面板实例数与脚本的 `MAX_CONCURRENT_USERS` 不同：后者控制一次任务内部同时执行的账号数。

如需不同账号在不同时段执行，分别创建只含一个用户的 YAML 和定时任务，用各自的 `--config` 指定。每份配置应使用不同的日志与历史文件路径，并移除或按任务覆盖共享的 `LOG_FILE` / `HISTORY_FILE` 环境变量，避免相互覆盖。

## 查看结果与排错

在 **定时任务 → 日志** 查看本次执行输出；程序日志和历史按上面的路径保存在持久化目录。把校验命令中的 `--validate-config` 换成 `--show-last-run`，可只读查看最近一次真实执行结果，YAML 方案保留相同的 `--config` 参数。

| 现象 | 检查方式 |
|------|----------|
| `ModuleNotFoundError` | 在青龙 Python3 依赖管理中补装缺失依赖；宿主机安装的包不等于容器内已安装 |
| 找不到脚本或账号文件 | 以脚本管理显示的目录替换示例脚本路径；账号文件使用容器内绝对路径 |
| 提示环境变量未设置 | 检查变量是否启用、名称是否与 YAML 引用完全一致；保存后重新运行任务 |
| 账号数量不对 | 检查多段 cURL 间的空行，以及是否有 YAML 用户列表优先生效；未传 `--config` 时也会尝试读取工作目录下的 `config.yaml` |
| YAML 修改后看似没生效 | 检查同名全局环境变量及用户 `reading_overrides` 的覆盖关系 |
| 任务长期运行或提前终止 | 确认使用 `immediate`，并按账号数检查超时和调度间隔 |
| Cookie 刷新或认证失败 | 重新抓取对应账号完整请求，更新其环境变量或本地文件后重跑；分享日志前先脱敏 |
