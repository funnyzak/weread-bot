# WeRead Bot 开发指导

## 项目概述

WeRead Bot 是一个功能完善的微信读书自动阅读机器人，使用 Python 开发，支持多用户、多种运行模式和丰富的配置选项。本文件旨在为持续开发提供全面的指导。

## 技术栈

- **Python 3.9+**: 主要开发语言
- **异步编程**: 使用 `asyncio` 进行异步操作
- **配置管理**: YAML 配置文件 + 环境变量
- **HTTP 请求**: `requests` 库 + 自定义重试机制
- **定时任务**: `schedule` 库
- **通知系统**: 支持多种通知渠道
- **日志系统**: 支持轮转日志和多格式输出
- **配置生成器**: 基于HTML + Tailwind CSS的可视化配置工具

## 项目结构

```
weread-bot/
├── weread-bot.py          # 主程序文件（单一文件设计）
├── config-generator.html  # 配置生成器（可视化界面）
├── config.yaml.example    # 配置文件模板
├── requirements.txt       # 依赖包列表
├── README.md             # 项目说明文档
├── LICENSE              # MIT 许可证
├── CLAUDE.md            # 开发指导文档（本文件）
└── logs/                # 日志文件目录（运行时创建）
```

## 核心架构

### 设计原则

1. **单一文件设计**: 为了方便部署和使用，所有代码集中在一个文件中
2. **模块化组织**: 使用类和函数进行逻辑分离，保持代码清晰
3. **配置驱动**: 通过 YAML 配置文件和环境变量控制行为
4. **异步优先**: 使用 async/await 处理 I/O 密集型操作
5. **防御性编程**: 全面的错误处理和日志记录

### 主要类结构

```python
# 配置管理
WeReadConfig              # 主配置类
ConfigManager            # 配置管理器

# 核心业务逻辑
WeReadApplication        # 应用程序管理器
WeReadSessionManager     # 会话管理器
SmartReadingManager      # 智能阅读管理器

# 辅助功能
HttpClient              # HTTP 客户端
NotificationService     # 通知服务
HumanBehaviorSimulator   # 人类行为模拟器

# 工具类
CurlParser             # CURL 命令解析器
RandomHelper           # 随机数助手
UserAgentRotator       # User-Agent 轮换器
```

## 开发指南

### 1. 环境设置

#### 开发环境要求
- Python 3.9+
- 推荐使用虚拟环境

#### 安装依赖
```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 安装开发依赖（可选）
pip install black flake8 mypy
```

### 2. 代码规范

#### 命名约定
- 类名：`PascalCase` (如 `WeReadBot`)
- 函数名：`snake_case` (如 `parse_curl_command`)
- 变量名：`snake_case` (如 `reading_config`)
- 常量：`UPPER_SNAKE_CASE` (如 `READ_URL`)

#### 代码风格
- 使用 4 个空格缩进
- 最大行长度：120 字符
- 使用类型注解
- 编写完整的文档字符串

#### 文档字符串格式
```python
def parse_curl_command(curl_command: str) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, Any]]:
    """解析 CURL 命令，提取 headers、cookies 和请求数据。

    Args:
        curl_command: 完整的 CURL 命令字符串

    Returns:
        包含三个元素的元组：(headers, cookies, request_data)

    Raises:
        ValueError: 当 CURL 命令格式无效时

    Example:
        >>> headers, cookies, data = parse_curl_command("curl 'https://example.com' -H 'Content-Type: application/json'")
    """
```

### 3. 错误处理

#### 基本原则
1. **不要静默失败**: 所有异常都应该被记录
2. **提供有意义的错误信息**: 帮助用户和开发者理解问题
3. **优雅降级**: 当次要功能失败时，主要功能应继续工作
4. **资源清理**: 使用 `try/finally` 或 `with` 语句

#### 异常处理模式
```python
# 好的实践
try:
    response = await self.http_client.post_json(url, data, headers, cookies)
    return response
except requests.Timeout:
    logging.error(f"请求超时: {url}")
    raise  # 重新抛出异常，让调用者处理
except Exception as e:
    logging.error(f"请求失败: {e}")
    return None  # 返回默认值
```

### 4. 日志记录

#### 日志级别使用
- **DEBUG**: 详细的调试信息，仅开发时使用
- **INFO**: 正常的操作信息，用户关心的状态变化
- **WARNING**: 潜在问题，不影响功能
- **ERROR**: 错误情况，影响部分功能
- **CRITICAL**: 严重错误，程序无法继续

#### 日志格式规范
```python
# 好的日志消息
logging.info("✅ 用户配置加载成功: %s", user_name)
logging.warning("⚠️ 网络请求失败，正在重试: %s", error_msg)
logging.error("❌ 用户认证失败: %s", auth_error)

# 包含上下文信息
logging.debug("🔍 请求数据: book_id=%s, chapter_id=%s", book_id, chapter_id)
```

### 5. 配置管理

#### 配置优先级
环境变量 > YAML 配置文件 > 默认值

#### 添加新配置项
1. 在相应的 dataclass 中添加字段
2. 在 `_load_config()` 方法中添加加载逻辑
3. 在环境变量处理中添加映射
4. 更新配置文件模板

```python
@dataclass
class NetworkConfig:
    timeout: int = 30
    retry_times: int = 3
    # 新配置项
    connection_pool_size: int = 10  # 新增

# 在 ConfigManager._load_config() 中
config.network = NetworkConfig(
    timeout=int(self._get_config_value(...)),
    retry_times=int(self._get_config_value(...)),
    connection_pool_size=int(self._get_config_value(  # 新增
        config_data, "network.connection_pool_size",
        "CONNECTION_POOL_SIZE", "10"
    )),
)
```

### 6. 异步编程

#### 异步函数设计
- 所有 I/O 操作都应该是异步的
- 使用 `async/await` 语法
- 避免在异步函数中调用阻塞操作

```python
# 好的实践
async def fetch_data(self, url: str) -> dict:
    try:
        response = await self.http_client.post_json(url, data, headers, cookies)
        return response
    except Exception as e:
        logging.error(f"获取数据失败: {e}")
        return {}

# 避免阻塞
async def process_data(self):
    # 不要这样做
    # time.sleep(1)  # 阻塞

    # 应该这样做
    await asyncio.sleep(1)  # 非阻塞
```

### 7. 测试策略

#### 单元测试
由于是单一文件设计，建议：
1. 提取关键函数进行独立测试
2. 使用 `unittest.mock` 模拟外部依赖
3. 测试配置解析逻辑
4. 测试工具类函数

#### 集成测试
1. 测试完整的阅读流程
2. 测试多用户场景
3. 测试通知功能
4. 测试错误恢复

### 8. 版本控制

#### Git 工作流
1. **主分支**: `main` 保持稳定可发布状态
2. **开发分支**: 在功能分支上开发
3. **提交信息**: 使用有意义的提交信息

```bash
# 好的提交信息格式
git commit -m "feat: 添加新的通知渠道支持"
git commit -m "fix: 修复章节索引计算错误"
git commit -m "docs: 更新 README 使用说明"
git commit -m "refactor: 重构配置管理模块"
```

#### 语义化版本
遵循 `MAJOR.MINOR.PATCH` 格式：
- **MAJOR**: 不兼容的 API 更改
- **MINOR**: 向后兼容的功能添加
- **PATCH**: 向后兼容的错误修复

### 9. 部署和发布

#### 发布流程
1. 更新版本号 (`weread-bot.py:64`)
2. 更新 CHANGELOG.md
3. 创建 Git 标签
4. 构建 Docker 镜像（如适用）

#### Docker 部署
```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY weread-bot.py .
CMD ["python", "weread-bot.py"]
```

## 配置生成器

### 概述

`config-generator.html` 是一个基于 HTML + Tailwind CSS + shadcn/ui 的轻量化配置文件生成器，为用户提供可视化的配置界面，简化配置文件的创建过程。

### 技术栈

- **HTML5**: 语义化标签和现代Web特性
- **Tailwind CSS**: 实用优先的CSS框架
- **shadcn/ui**: 高质量UI组件设计
- **JavaScript ES6+**: 现代JavaScript特性
- **js-yaml**: YAML解析和生成库
- **Lucide Icons**: 现代化图标库


## 功能扩展指南

### 添加新的通知渠道

1. 在 `NotificationMethod` 枚举中添加新渠道
2. 在 `NotificationService._send_notification_to_channel()` 中添加处理逻辑
3. 在 `ConfigManager._create_channels_from_env_vars()` 中添加环境变量支持
4. 更新配置文件模板

```python
# 1. 添加枚举
class NotificationMethod(Enum):
    # ... 现有渠道
    NEW_CHANNEL = "new_channel"

# 2. 添加发送逻辑
def _send_new_channel(self, message: str, config: Dict[str, Any]) -> bool:
    """发送新渠道通知"""
    # 实现发送逻辑
    pass

# 3. 在主发送方法中添加分支
elif channel.name == "new_channel":
    return self._send_new_channel(message, channel.config)
```

### 添加新的阅读模式

1. 在 `ReadingMode` 枚举中添加新模式
2. 在 `SmartReadingManager.get_next_reading_position()` 中添加逻辑
3. 更新配置文档

```python
# 1. 添加枚举
class ReadingMode(Enum):
    # ... 现有模式
    CUSTOM_MODE = "custom"

# 2. 实现新逻辑
def _custom_position(self) -> Tuple[str, str]:
    """自定义阅读模式逻辑"""
    # 实现自定义逻辑
    pass

# 3. 在主方法中添加分支
elif mode == ReadingMode.CUSTOM_MODE:
    return self._custom_position()
```

### 添加新的运行模式

1. 在 `StartupMode` 枚举中添加新模式
2. 在 `WeReadApplication.run()` 中添加处理逻辑
3. 实现相应的运行方法

```python
# 1. 添加枚举
class StartupMode(Enum):
    # ... 现有模式
    CUSTOM = "custom"

# 2. 添加运行逻辑
async def _run_custom_mode(self):
    """自定义运行模式"""
    # 实现自定义逻辑
    pass

# 3. 在主方法中添加分支
elif startup_mode == StartupMode.CUSTOM:
    await self._run_custom_mode()
```

## 性能优化

### 网络优化
1. **连接池**: 复用 HTTP 连接
2. **超时设置**: 合理的超时时间
3. **重试机制**: 指数退避重试
4. **速率限制**: 避免过于频繁的请求

### 内存优化
1. **资源释放**: 及时关闭文件和网络连接
2. **数据结构**: 选择合适的数据结构
3. **缓存策略**: 合理使用缓存避免重复计算

### 异步优化
1. **并发控制**: 使用 `asyncio.Semaphore` 限制并发
2. **超时处理**: 使用 `asyncio.wait_for()` 设置超时
3. **错误处理**: 妥善处理异步异常

## 安全考虑

### 数据安全
1. **敏感信息**: 不要在日志中记录敏感信息
2. **配置文件**: 保护配置文件不被未授权访问
3. **网络传输**: 使用 HTTPS 和安全的认证方式

### 运行安全
1. **输入验证**: 验证所有外部输入
2. **权限控制**: 最小权限原则
3. **异常处理**: 避免异常暴露系统信息

### 隐私保护
1. **用户数据**: 妥善处理用户个人信息
2. **日志内容**: 避免记录敏感的用户数据
3. **通知内容**: 谨慎处理通知中的个人信息

## 常见问题解决

### 调试技巧
1. **启用详细日志**: 使用 `--verbose` 参数
2. **配置验证**: 检查配置文件格式和内容
3. **网络测试**: 手动测试网络连接和 API
4. **逐步调试**: 使用 Python 调试器

### 性能问题
1. **日志分析**: 检查日志中的性能指标
2. **内存使用**: 监控内存使用情况
3. **网络延迟**: 检查网络响应时间
4. **并发问题**: 检查异步操作的正确性

### 配置问题
1. **格式验证**: 使用 YAML 验证工具检查配置文件
2. **环境变量**: 确认环境变量正确设置
3. **权限问题**: 检查文件访问权限
4. **依赖版本**: 确认依赖包版本兼容

## 贡献指南

### 报告问题
1. 使用 GitHub Issues 报告问题
2. 提供详细的复现步骤
3. 包含相关的日志和配置信息
4. 说明运行环境和版本信息

### 提交代码
1. Fork 项目仓库
2. 创建功能分支
3. 遵循代码规范
4. 添加必要的测试
5. 提交 Pull Request

### 代码审查
1. 确保代码符合项目风格
2. 检查错误处理和日志记录
3. 验证功能完整性
4. 测试不同场景下的行为

## 文档更新维护规范

### 文档同步更新原则

每次代码更新和功能调整后，必须检查并同步更新以下文档：

1. **README.md** - 用户面向的文档
2. **CLAUDE.md** - 开发指导文档
3. **配置文件模板** - config.yaml.example
4. **代码注释** - 重要函数和类的文档字符串

### 文档更新检查清单

#### 功能新增时
- [ ] README.md中添加新功能的说明
- [ ] CLAUDE.md中更新技术栈和项目结构
- [ ] 更新配置文件模板（如果涉及新配置项）
- [ ] 添加相关的代码注释和文档字符串
- [ ] 更新示例和说明文档

#### 配置变更时
- [ ] 更新config.yaml.example
- [ ] 在README.md中说明配置变更
- [ ] 在CLAUDE.md中更新配置管理部分
- [ ] 如果是配置生成器相关，更新config-generator.html

#### Bug修复时
- [ ] 更新相关的文档说明
- [ ] 如果影响用户使用，在README.md中添加已知问题说明
- [ ] 在CLAUDE.md中记录修复过程和原因

#### 文档结构检查
- [ ] 确保所有文档中的版本信息一致
- [ ] 检查文档中的链接是否有效
- [ ] 确保代码示例的正确性
- [ ] 验证文档中的命令和路径

### 文档质量标准

#### README.md标准
- 清晰的项目概述和特性说明
- 完整的安装和使用指南
- 准确的配置说明和示例
- 常见问题解答
- 有效的链接和引用

#### CLAUDE.md标准
- 详细的技术架构说明
- 完整的开发指南
- 代码规范和最佳实践
- 测试和部署指南
- 维护和贡献指南

#### 代码注释标准
- 公开函数和类必须有完整的文档字符串
- 复杂逻辑需要详细的注释说明
- 配置项变更需要记录变更原因
- 重要的算法和数据结构需要说明

### 文档更新流程

1. **开发阶段**：在开发过程中同步更新相关文档
2. **代码审查**：将文档更新作为代码审查的一部分
3. **提交前检查**：使用以下检查清单验证文档完整性
4. **合并后验证**：确认文档在线版本正确更新

### 文档版本管理

- 重要功能变更需要更新文档的版本信息
- 保持文档的向后兼容性说明
- 记录文档的变更历史
- 定期清理过时的文档内容

### 在线文档部署

项目配置为GitHub Pages自动部署，在线访问地址：
```
https://weread.gh.yycc.dev/
```

## 维护计划

### 定期维护
1. **依赖更新**: 定期更新依赖包版本
2. **安全补丁**: 及时应用安全更新
3. **性能优化**: 持续优化性能瓶颈
4. **文档更新**: 保持文档与代码同步

### 版本发布
1. **功能冻结**: 发布前冻结功能开发
2. **测试验证**: 全面测试新功能
3. **文档更新**: 更新用户文档和开发文档
4. **发布准备**: 准备发布说明和变更日志

### 监控和反馈
1. **问题跟踪**: 及时响应和解决问题
2. **用户反馈**: 收集和分析用户反馈
3. **使用统计**: 监控使用情况（匿名）
4. **改进规划**: 基于反馈制定改进计划

---

**注意**: 本文档应与代码保持同步更新。在进行重大更改时，请同时更新相应的文档部分。

**最后更新**: 2025-09-28