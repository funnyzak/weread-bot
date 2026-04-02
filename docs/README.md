# 文档总览

本文档用于帮助不同类型的用户快速找到合适的说明入口。

## 从哪里开始

如果你是第一次使用本项目，建议先按这个顺序阅读：

1. [项目首页 README](../README.md)
2. [配置模板 `config.yaml.example`](../config.yaml.example)
3. 根据你的部署方式继续阅读对应指南

## 按场景选择文档

### 本地单用户

- 入口：[README 中的三分钟快速开始](../README.md#三分钟快速开始)
- 适合：先验证 cURL、快速跑通、调试参数

### 多用户

- 入口：[README 中的多用户使用](../README.md#多用户使用)
- 适合：同时维护多个账号、需要用户级覆盖参数

### GitHub Actions

- 入口：[GitHub Action 自动阅读配置指南](./github-action-autoread-guide.md)
- 适合：不想自建常驻环境，希望云端自动运行

### Docker

- 入口：[README 中的部署方式](../README.md#部署方式)
- 适合：服务器常驻运行、容器化部署

### 排错和自检

- 入口：[README 中的自检与排错](../README.md#自检与排错)
- 关键命令：
  - `python3 weread-bot.py --validate-config --config config.yaml`
  - `python3 weread-bot.py --dry-run --config config.yaml`
  - `python3 weread-bot.py --show-last-run --config config.yaml`

## 当前文档列表

- [README](../README.md)：项目介绍、快速开始、常用命令、部署入口
- [GitHub Action 自动阅读配置指南](./github-action-autoread-guide.md)：云端运行、Secrets 配置、工作流说明
- [配置模板](../config.yaml.example)：完整配置字段示例

## 维护说明

- README 只保留入门和导航信息，避免继续膨胀成百科全书
- 进阶部署、平台差异和场景化说明优先放到 `docs/` 下的专门文档
- 新增文档时，应同时更新本文档，保持索引可用
