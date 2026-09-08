#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""WeRead Bot (微信读书阅读机器人)

项目信息:
    名称: WeRead Bot
    版本: 0.3.9
    作者: funnyzak
    仓库: https://github.com/funnyzak/weread-bot
    许可: MIT License

项目说明:
    WeRead Bot 是一个智能的微信读书自动阅读机器人，通过模拟真实用户的阅读行为
    来积累阅读时长。支持多用户、多种运行模式，适用于需要提升微信读书等级或完成
    阅读任务的用户场景。

主要功能:
    - 多用户支持：可同时管理多个用户的阅读任务
    - 多种运行模式：支持立即执行、定时任务、守护进程
    - 智能阅读：模拟真实用户阅读行为，支持多种阅读策略
    - 灵活配置：支持 YAML 配置文件和环境变量配置
    - 多通知渠道：支持多种通知方式（PushPlus、Telegram等）

使用示例:
    1. 基础使用：
       python weread-bot.py
    
    2. 指定配置文件：
       python weread-bot.py --config custom_config.yaml
    
    3. 守护进程模式：
       python weread-bot.py --daemon

参考致谢:
    - 感谢 https://github.com/findmover/wxread 提供思路和部分代码支持

更多详细说明请访问项目仓库：https://github.com/funnyzak/weread-bot
"""

import os
import re
import json
import math
import time
import random
import hashlib
import logging
import asyncio
import urllib.parse
import signal
import argparse
import tempfile
import traceback
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple, Set, Union, Callable
from dataclasses import dataclass, field
from enum import Enum
from logging.handlers import RotatingFileHandler

try:
    import yaml
except ImportError:
    yaml = None

try:
    import requests
except ImportError:
    requests = None

try:
    import httpx
except ImportError:
    httpx = None

try:
    from croniter import croniter
except ImportError:
    croniter = None
from zoneinfo import ZoneInfo

VERSION = "0.3.9"
REPO = "https://github.com/funnyzak/weread-bot"

CURRENT_USER = ContextVar("weread_user", default="system")
CURRENT_SESSION_ID = ContextVar("weread_session_id", default="-")


class LogContextFilter(logging.Filter):
    """向日志记录注入并发安全的会话上下文。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.user = CURRENT_USER.get()
        record.session_id = CURRENT_SESSION_ID.get()
        return True


class JsonLogFormatter(logging.Formatter):
    """输出可逐行解析的 JSON 日志。"""

    def format(self, record: logging.LogRecord) -> str:
        record = _redacted_log_record(record)
        payload = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "event": getattr(record, "event", record.name),
            "message": redact_for_log(record.getMessage()),
            "user": getattr(record, "user", CURRENT_USER.get()),
            "session_id": getattr(
                record, "session_id", CURRENT_SESSION_ID.get()
            ),
        }
        for name in (
            "error_category", "attempt", "max_attempts", "delay", "elapsed_ms"
        ):
            value = getattr(record, name, None)
            if value is not None:
                payload[name] = value
        if record.exc_info:
            payload["exception_type"] = record.exc_info[0].__name__
            payload["exception"] = redact_for_log(str(record.exc_info[1]))
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                payload["traceback"] = redact_for_log(
                    "".join(traceback.format_exception(*record.exc_info))
                )
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class RedactingLogFormatter(logging.Formatter):
    """在记录副本上脱敏，避免修改 handler 共享的 LogRecord。"""

    def format(self, record: logging.LogRecord) -> str:
        return super().format(_redacted_log_record(record))

    def formatException(self, exc_info: Any) -> str:
        return redact_for_log(super().formatException(exc_info))


@contextmanager
def log_context(user: str, session_id: Optional[str] = None):
    """在当前异步上下文中关联用户和会话。"""
    resolved_session_id = session_id or uuid.uuid4().hex[:10]
    user_token = CURRENT_USER.set(user or "default")
    session_token = CURRENT_SESSION_ID.set(resolved_session_id)
    try:
        yield resolved_session_id
    finally:
        CURRENT_SESSION_ID.reset(session_token)
        CURRENT_USER.reset(user_token)


SENSITIVE_LOG_KEYS = {
    "authorization", "cookie", "cookies", "wr_skey", "token", "bot_token",
    "webhook_url", "secret", "ps", "pc", "sendkey", "pushkey", "device_key",
}
SENSITIVE_LOG_KEY_PATTERN = "|".join(
    sorted((re.escape(key) for key in SENSITIVE_LOG_KEYS), key=len, reverse=True)
)


def _secret_marker(value: Any) -> str:
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()[-8:]
    return f"[REDACTED:{digest}]"


def redact_for_log(value: Any) -> Any:
    """递归脱敏日志数据，不保留密钥原始前缀。"""
    if isinstance(value, dict):
        return {
            key: (
                _secret_marker(item)
                if str(key).lower() in SENSITIVE_LOG_KEYS
                else redact_for_log(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_for_log(item) for item in value]
    if isinstance(value, str):
        redacted = re.sub(
            (
                rf"(?i)(?P<prefix>[\"']?(?:{SENSITIVE_LOG_KEY_PATTERN})"
                r"[\"']?\s*[:=]\s*)"
                r"(?P<quote>[\"']?)(?P<secret>.*?)(?P=quote)"
                r"(?=\s*[,;}\]]|\s*$)"
            ),
            lambda match: (
                match.group("prefix")
                + match.group("quote")
                + "[REDACTED]"
                + match.group("quote")
            ),
            value,
        )
        return redacted
    return value


def _redacted_log_record(record: logging.LogRecord) -> logging.LogRecord:
    """复制日志记录并脱敏最终消息，保留原记录供其他 handler 使用。"""
    redacted_record = logging.makeLogRecord(record.__dict__.copy())
    redacted_record.msg = redact_for_log(record.getMessage())
    redacted_record.args = ()
    redacted_record.exc_text = None
    return redacted_record


def safe_url_for_log(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


# =========================
# 常量与数据模型
# =========================


class NotificationEvent(str, Enum):
    """通知触发事件类型"""
    SESSION_SUCCESS = "session_success"
    SESSION_FAILURE = "session_failure"
    MULTI_USER_SUMMARY = "multi_user_summary"
    RUNTIME_ERROR = "runtime_error"
    GENERAL = "general"


def default_notification_triggers() -> Dict[NotificationEvent, bool]:
    """通知触发默认配置"""
    return {event: True for event in NotificationEvent}


class ReadingMode(Enum):
    """阅读模式枚举"""
    SEQUENTIAL = "sequential"
    SMART_RANDOM = "smart_random"
    PURE_RANDOM = "pure_random"


class StartupMode(Enum):
    """启动模式枚举"""
    IMMEDIATE = "immediate"
    SCHEDULED = "scheduled"
    DAEMON = "daemon"


class RuntimeErrorCategory(str, Enum):
    """运行时错误分类"""
    CONFIG = "config"
    AUTH = "auth"
    NETWORK = "network"
    PROTOCOL = "protocol"
    NOTIFICATION = "notification"
    UNKNOWN = "unknown"


class SessionStatus(str, Enum):
    """单个用户会话状态。"""
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


USER_READING_OVERRIDE_FIELDS = {
    "mode": "reading.mode",
    "target_duration": "reading.target_duration",
    "reading_interval": "reading.reading_interval",
    "use_curl_data_first": "reading.use_curl_data_first",
    "fallback_to_config": "reading.fallback_to_config",
}
USER_TIME_STRATEGY_FIELDS = {"target_duration", "reading_interval"}
NOTIFICATION_CHANNEL_REQUIRED_FIELDS = {
    "pushplus": ["token"],
    "telegram": ["bot_token", "chat_id"],
    "wxpusher": ["spt"],
    "apprise": ["url"],
    "bark": ["server", "device_key"],
    "ntfy": ["server", "topic"],
    "feishu": ["webhook_url"],
    "wework": ["webhook_url"],
    "dingtalk": ["webhook_url"],
    "gotify": ["server", "token"],
    "serverchan3": ["uid", "sendkey"],
    "pushdeer": ["pushkey"],
}
NOTIFICATION_CHANNEL_ENV_FIELDS = {
    "pushplus": {"token": "PUSHPLUS_TOKEN"},
    "telegram": {
        "bot_token": "TELEGRAM_BOT_TOKEN",
        "chat_id": "TELEGRAM_CHAT_ID",
    },
    "wxpusher": {"spt": "WXPUSHER_SPT"},
    "apprise": {"url": "APPRISE_URL"},
    "bark": {
        "server": "BARK_SERVER",
        "device_key": "BARK_DEVICE_KEY",
        "sound": "BARK_SOUND",
    },
    "ntfy": {
        "server": "NTFY_SERVER",
        "topic": "NTFY_TOPIC",
        "token": "NTFY_TOKEN",
    },
    "feishu": {
        "webhook_url": "FEISHU_WEBHOOK_URL",
        "msg_type": "FEISHU_MSG_TYPE",
    },
    "wework": {
        "webhook_url": "WEWORK_WEBHOOK_URL",
        "msg_type": "WEWORK_MSG_TYPE",
    },
    "dingtalk": {
        "webhook_url": "DINGTALK_WEBHOOK_URL",
        "msg_type": "DINGTALK_MSG_TYPE",
    },
    "gotify": {
        "server": "GOTIFY_SERVER",
        "token": "GOTIFY_TOKEN",
        "priority": "GOTIFY_PRIORITY",
        "title": "GOTIFY_TITLE",
    },
    "serverchan3": {
        "uid": "SERVERCHAN3_UID",
        "sendkey": "SERVERCHAN3_SENDKEY",
        "tags": "SERVERCHAN3_TAGS",
        "short": "SERVERCHAN3_SHORT",
    },
    "pushdeer": {
        "pushkey": "PUSHDEER_PUSHKEY",
        "type": "PUSHDEER_TYPE",
    },
}


@dataclass
class NetworkConfig:
    """网络配置"""
    timeout: int = 30
    retry_times: int = 3
    retry_delay: str = "5-15"
    rate_limit: int = 10


@dataclass
class ChapterInfo:
    """章节信息"""
    chapter_id: str
    chapter_index: Optional[int] = None


@dataclass
class BookInfo:
    """书籍信息"""
    name: str
    book_id: str
    chapters: List[str] = field(default_factory=list)  # 章节字符串列表
    chapter_infos: List[ChapterInfo] = field(default_factory=list)  # 新的章节信息格式


@dataclass
class SmartRandomConfig:
    """智能随机配置"""
    book_continuity: float = 0.8
    chapter_continuity: float = 0.7
    book_switch_cooldown: int = 300


@dataclass
class ScheduleConfig:
    """定时任务配置"""
    enabled: bool = False
    cron_expression: str = "0 */2 * * *"  # 每2小时执行一次
    timezone: str = "Asia/Shanghai"


@dataclass
class DaemonConfig:
    """守护进程配置"""
    enabled: bool = False
    session_interval: str = "120-180"  # 会话间隔（分钟）
    max_daily_sessions: int = 12  # 每日最大会话数


@dataclass
class LoggingConfig:
    """日志配置"""
    level: str = "INFO"
    format: str = "detailed"  # simple, detailed, json
    file: str = "logs/weread.log"
    max_size: str = "10MB"
    backup_count: int = 5
    console: bool = True


@dataclass
class HistoryConfig:
    """执行历史配置"""
    enabled: bool = True
    file: str = "logs/run-history.json"
    max_entries: int = 50
    persist_runtime_error: bool = True


@dataclass
class ReadingConfig:
    """阅读配置"""
    mode: str = "smart_random"
    target_duration: str = "60-70"
    reading_interval: str = "25-35"
    use_curl_data_first: bool = True
    fallback_to_config: bool = True
    max_consecutive_failures: int = 5
    books: List[BookInfo] = field(default_factory=list)
    smart_random: SmartRandomConfig = field(default_factory=SmartRandomConfig)


@dataclass
class HumanSimulationConfig:
    """人类行为模拟配置"""
    enabled: bool = True
    reading_speed_variation: bool = True
    break_probability: float = 0.15
    break_duration: str = "30-180"
    rotate_user_agent: bool = True


@dataclass
class UserConfig:
    """用户配置"""
    name: str
    file_path: str = ""
    content: str = ""
    cookie_refresh_ql: Optional[bool] = None
    reading_overrides: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NotificationChannel:
    """通知通道配置"""
    name: str
    enabled: bool = True
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NotificationConfig:
    """通知配置"""
    enabled: bool = True
    include_statistics: bool = True
    channels: List[NotificationChannel] = field(default_factory=list)
    triggers: Dict[NotificationEvent, bool] = field(
        default_factory=default_notification_triggers
    )
    only_on_failure: Optional[bool] = None


@dataclass
class HackConfig:
    """Hack 配置"""
    # Cookie刷新时ql属性设置
    # 根据不同用户的环境，可能需要设置为True或False来确保cookie刷新正常工作
    cookie_refresh_ql: bool = False


@dataclass
class WeReadConfig:
    """微信读书配置主类"""
    # App 基本配置
    name: str = "WeReadBot"
    version: str = VERSION
    startup_mode: str = "immediate"
    startup_delay: str = "1-10"
    max_concurrent_users: int = 1

    # CURL 配置（单用户模式）
    curl_file_path: str = ""
    curl_content: str = ""

    # 多用户配置
    users: List[UserConfig] = field(default_factory=list)

    # 各模块配置
    reading: ReadingConfig = field(default_factory=ReadingConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    human_simulation: HumanSimulationConfig = field(
        default_factory=HumanSimulationConfig
    )
    notification: NotificationConfig = field(
        default_factory=NotificationConfig
    )
    hack: HackConfig = field(default_factory=HackConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    daemon: DaemonConfig = field(default_factory=DaemonConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    history: HistoryConfig = field(default_factory=HistoryConfig)

    def get_startup_info(self) -> str:
        """获取启动信息摘要"""
        # 获取系统信息
        import platform

        # 构建启动信息
        startup_info = f"""
📚 微信读书阅读机器人

应用信息:
  📱 应用名称: {self.name}
  🔢 版本: {self.version}
  📦 仓库: {REPO}
  🐍 Python版本: {platform.python_version()}
  🖥️  系统: {platform.system()} {platform.release()}
  📁 工作目录: {Path.cwd()}

运行配置:
  🚀 启动模式: {self._get_startup_mode_desc()}
  ⏰ 启动延迟: {self.startup_delay} 秒
  📖 阅读模式: {self._get_reading_mode_desc()}
  📊 目标时长: {self.reading.target_duration} 分钟
  🔄 阅读间隔: {self.reading.reading_interval} 秒
  🎭 人类模拟: {'启用' if self.human_simulation.enabled else '禁用'}
  👥 最大并发用户: {self.max_concurrent_users}

网络配置:
  ⏱️  超时时间: {self.network.timeout} 秒
  🔄 重试次数: {self.network.retry_times} 次
  📈 请求限制: {self.network.rate_limit} 请求/分钟
  🕐 重试延迟: {self.network.retry_delay} 秒

通知配置:
  📢 通知状态: {'启用' if self.notification.enabled else '禁用'}
  📨 通知通道: {len([c for c in self.notification.channels if c.enabled])} 个启用
  📊 统计信息: {'包含' if self.notification.include_statistics else '不包含'}

数据源配置:
  📄 CURL文件: {self._get_curl_source_desc()}
  👥 用户配置: {len(self.users)} 个用户 {'(多用户模式)' if self.users else '(单用户模式)'}
  📚 配置书籍: {len(self.reading.books)} 本
  🎯 优先策略: {'CURL数据优先' if self.reading.use_curl_data_first else '配置数据优先'}
  🔄 回退策略: {'启用' if self.reading.fallback_to_config else '禁用'}

日志配置:
  📝 日志级别: {self.logging.level}
  📋 日志格式: {self.logging.format}
  💾 日志文件: {self.logging.file}
  📏 文件大小: {self.logging.max_size}
  🗂️  备份数量: {self.logging.backup_count} 个
  🖥️  控制台: {'启用' if self.logging.console else '禁用'}
"""

        # 如果是定时或守护进程模式，添加额外信息
        if self.startup_mode.lower() == "scheduled" and self.schedule.enabled:
            startup_info += (
                f"\n⏰ 定时任务: {self.schedule.cron_expression} "
                f"({self.schedule.timezone})"
            )

        if self.startup_mode.lower() == "daemon" and self.daemon.enabled:
            startup_info += (
                f"\n🔄 守护进程: 会话间隔 {self.daemon.session_interval} 分钟，"
                f"每日最大 {self.daemon.max_daily_sessions} 次会话"
            )

        return startup_info

    def _get_startup_mode_desc(self) -> str:
        """获取启动模式描述"""
        mode_map = {
            "immediate": "立即执行",
            "scheduled": "定时执行",
            "daemon": "守护进程"
        }
        return mode_map.get(self.startup_mode.lower(), self.startup_mode)

    def _get_reading_mode_desc(self) -> str:
        """获取阅读模式描述"""
        mode_map = {
            "smart_random": "智能随机",
            "sequential": "顺序阅读",
            "pure_random": "纯随机"
        }
        return mode_map.get(self.reading.mode.lower(), self.reading.mode)

    def _get_curl_source_desc(self) -> str:
        """获取CURL数据源描述"""
        if self.curl_file_path:
            return f"文件: {self.curl_file_path}"
        elif self.curl_content:
            return "环境变量 (WEREAD_CURL_STRING)"
        else:
            return "未配置"


@dataclass
class ReadingSession:
    """阅读会话统计"""
    user_name: str = "默认用户"
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    target_duration_minutes: float = 0.0
    actual_duration_seconds: int = 0
    successful_reads: int = 0
    failed_reads: int = 0
    books_read: List[str] = field(default_factory=list)  # 存储书籍ID
    books_read_names: List[str] = field(default_factory=list)  # 存储书名
    chapters_read: List[str] = field(default_factory=list)
    breaks_taken: int = 0
    total_break_time: int = 0
    response_times: List[float] = field(default_factory=list)

    @property
    def average_response_time(self) -> float:
        """计算平均响应时间"""
        if self.response_times:
            return sum(self.response_times) / len(self.response_times)
        return 0.0

    @property
    def success_rate(self) -> float:
        """计算成功率"""
        total = self.successful_reads + self.failed_reads
        return (self.successful_reads / total * 100) if total > 0 else 0.0

    @property
    def actual_duration_formatted(self) -> str:
        """格式化实际时长"""
        minutes = self.actual_duration_seconds // 60
        seconds = self.actual_duration_seconds % 60
        return f"{minutes}分{seconds}秒"

    def get_statistics_summary(self) -> str:
        """获取统计摘要"""
        books_info = (
            ', '.join(set(self.books_read_names))
            if self.books_read_names else '无书名信息'
        )
        return f"""📊 微信读书自动阅读统计报告
👤 用户名称: {self.user_name}
⏰ 开始时间: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}
⏱️ 实际阅读: {self.actual_duration_formatted}
🎯 目标时长: {self.target_duration_minutes:g}分钟
✅ 成功请求: {self.successful_reads}次
❌ 失败请求: {self.failed_reads}次
📈 成功率: {self.success_rate:.1f}%
📚 阅读书籍: {len(set(self.books_read))}本 ({books_info})
📄 阅读章节: {len(set(self.chapters_read))}个
☕ 休息次数: {self.breaks_taken}次 (共{self.total_break_time}秒)
🚀 平均响应: {self.average_response_time:.2f}秒

        🎉 本次阅读任务完成！"""


@dataclass
class SessionResult:
    """单个用户会话的明确结果。"""
    status: SessionStatus
    stats: ReadingSession
    error_category: Optional[RuntimeErrorCategory] = None
    message: str = ""


@dataclass
class RunResult:
    """一次应用运行的聚合结果。"""
    final_status: str
    user_count: int
    successful_users: int = 0
    failed_users: int = 0
    cancelled_users: int = 0
    skipped_users: int = 0
    total_duration_seconds: int = 0
    total_reads: int = 0
    total_failed_reads: int = 0
    failure_categories: Dict[str, int] = field(default_factory=dict)
    continue_on_failure: bool = False

    @property
    def exit_code(self) -> int:
        return 0 if self.final_status == "success" else 1

    def to_summary_dict(self) -> Dict[str, Any]:
        return {
            "final_status": self.final_status,
            "user_count": self.user_count,
            "successful_users": self.successful_users,
            "failed_users": self.failed_users,
            "cancelled_users": self.cancelled_users,
            "skipped_users": self.skipped_users,
            "total_duration_seconds": self.total_duration_seconds,
            "total_reads": self.total_reads,
            "total_failed_reads": self.total_failed_reads,
            "failure_categories": self.failure_categories.copy(),
            "continue_on_failure": self.continue_on_failure,
        }

    @classmethod
    def from_session_results(
        cls,
        results: List[SessionResult],
        skipped_users: int = 0,
        continue_on_failure: bool = False,
    ) -> "RunResult":
        successful = sum(
            result.status == SessionStatus.SUCCESS for result in results
        )
        failed = sum(
            result.status == SessionStatus.FAILED for result in results
        )
        cancelled = sum(
            result.status == SessionStatus.CANCELLED for result in results
        )
        failure_categories: Dict[str, int] = {}
        for result in results:
            if result.error_category is not None:
                key = result.error_category.value
                failure_categories[key] = failure_categories.get(key, 0) + 1

        if results and cancelled == len(results):
            final_status = "cancelled"
        elif successful == len(results) and not skipped_users:
            final_status = "success"
        elif successful:
            final_status = "partial_success"
        elif failed:
            final_status = "failed"
        elif cancelled:
            final_status = "cancelled"
        else:
            final_status = "failed"

        return cls(
            final_status=final_status,
            user_count=len(results) + skipped_users,
            successful_users=successful,
            failed_users=failed,
            cancelled_users=cancelled,
            skipped_users=skipped_users,
            total_duration_seconds=sum(
                result.stats.actual_duration_seconds for result in results
            ),
            total_reads=sum(
                result.stats.successful_reads for result in results
            ),
            total_failed_reads=sum(
                result.stats.failed_reads for result in results
            ),
            failure_categories=failure_categories,
            continue_on_failure=continue_on_failure,
        )


# ==================
# 配置与解析
# ==================


class ConfigError(ValueError):
    """带配置路径的解析或语义错误。"""


def _config_error(path: str, reason: str, value: Any) -> ConfigError:
    safe_value = repr(value)
    if any(key in path.lower() for key in ("token", "cookie", "secret", "content")):
        safe_value = "已提供" if value else "未提供"
    return ConfigError(f"{path}: {reason}，当前值={safe_value}")


def parse_bool(value: Any, path: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    raise _config_error(path, "必须是布尔值", value)


def parse_int(
    value: Any, path: str, minimum: Optional[int] = None
) -> int:
    if isinstance(value, bool):
        raise _config_error(path, "必须是整数", value)
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise _config_error(path, "必须是整数", value) from exc
    if minimum is not None and parsed < minimum:
        raise _config_error(path, f"必须大于或等于 {minimum}", value)
    return parsed


def parse_float(
    value: Any,
    path: str,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> float:
    if isinstance(value, bool):
        raise _config_error(path, "必须是数字", value)
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise _config_error(path, "必须是数字", value) from exc
    if not math.isfinite(parsed):
        raise _config_error(path, "必须是有限数字", value)
    if minimum is not None and parsed < minimum:
        raise _config_error(path, f"必须大于或等于 {minimum}", value)
    if maximum is not None and parsed > maximum:
        raise _config_error(path, f"必须小于或等于 {maximum}", value)
    return parsed


def parse_range(
    value: Any,
    path: str,
    minimum: Optional[float] = None,
    allow_zero: bool = True,
) -> Tuple[float, float]:
    match = re.fullmatch(
        r"\s*([+]?(?:\d+(?:\.\d*)?|\.\d+))"
        r"(?:\s*-\s*([+]?(?:\d+(?:\.\d*)?|\.\d+)))?\s*",
        str(value),
    )
    if not match:
        raise _config_error(path, "必须是数字或 min-max 范围", value)
    lower = float(match.group(1))
    upper = float(match.group(2)) if match.group(2) is not None else lower
    if not math.isfinite(lower) or not math.isfinite(upper):
        raise _config_error(path, "必须是有限范围", value)
    effective_minimum = minimum
    if not allow_zero:
        effective_minimum = max(minimum or 0.0, 0.000000001)
    if effective_minimum is not None and lower < effective_minimum:
        raise _config_error(
            path, f"下限必须大于或等于 {effective_minimum}", value
        )
    if upper < lower:
        raise _config_error(path, "上限不能小于下限", value)
    return lower, upper


def parse_choice(value: Any, path: str, choices: Set[str]) -> str:
    normalized = str(value).strip().lower()
    if normalized not in choices:
        raise _config_error(
            path, f"必须是 {', '.join(sorted(choices))} 之一", value
        )
    return normalized


def validate_config_semantics(config: WeReadConfig) -> None:
    """集中校验加载后的全局配置和用户覆盖。"""
    config.startup_mode = parse_choice(
        config.startup_mode,
        "app.startup_mode",
        {mode.value for mode in StartupMode},
    )
    parse_range(config.startup_delay, "app.startup_delay", minimum=0)
    parse_int(config.max_concurrent_users, "app.max_concurrent_users", 1)

    config.reading.mode = parse_choice(
        config.reading.mode,
        "reading.mode",
        {mode.value for mode in ReadingMode},
    )
    parse_range(
        config.reading.target_duration,
        "reading.target_duration",
        minimum=0.000000001,
        allow_zero=False,
    )
    parse_range(
        config.reading.reading_interval,
        "reading.reading_interval",
        minimum=0,
    )
    parse_int(
        config.reading.max_consecutive_failures,
        "reading.max_consecutive_failures",
        1,
    )
    parse_float(
        config.reading.smart_random.book_continuity,
        "reading.smart_random.book_continuity",
        0,
        1,
    )
    parse_float(
        config.reading.smart_random.chapter_continuity,
        "reading.smart_random.chapter_continuity",
        0,
        1,
    )
    parse_int(
        config.reading.smart_random.book_switch_cooldown,
        "reading.smart_random.book_switch_cooldown",
        0,
    )
    parse_int(config.network.timeout, "network.timeout", 1)
    parse_int(config.network.retry_times, "network.retry_times", 1)
    parse_range(config.network.retry_delay, "network.retry_delay", 0)
    parse_int(config.network.rate_limit, "network.rate_limit", 0)
    parse_float(
        config.human_simulation.break_probability,
        "human_simulation.break_probability",
        0,
        1,
    )
    parse_range(
        config.human_simulation.break_duration,
        "human_simulation.break_duration",
        0,
    )
    parse_range(config.daemon.session_interval, "daemon.session_interval", 0)
    parse_int(config.daemon.max_daily_sessions, "daemon.max_daily_sessions", 1)
    config.logging.level = parse_choice(
        config.logging.level,
        "logging.level",
        {"debug", "info", "warning", "error", "critical"},
    ).upper()
    config.logging.format = parse_choice(
        config.logging.format,
        "logging.format",
        {"simple", "detailed", "json"},
    )
    parse_int(config.logging.backup_count, "logging.backup_count", 0)
    parse_int(config.history.max_entries, "history.max_entries", 1)

    for index, user in enumerate(config.users):
        base = f"curl_config.users[{index}].reading_overrides"
        overrides = user.reading_overrides
        if "mode" in overrides:
            overrides["mode"] = parse_choice(
                overrides["mode"],
                f"{base}.mode",
                {mode.value for mode in ReadingMode},
            )
        if "target_duration" in overrides:
            parse_range(
                overrides["target_duration"],
                f"{base}.target_duration",
                minimum=0.000000001,
                allow_zero=False,
            )
        if "reading_interval" in overrides:
            parse_range(
                overrides["reading_interval"],
                f"{base}.reading_interval",
                minimum=0,
            )
        for bool_key in ("use_curl_data_first", "fallback_to_config"):
            if bool_key in overrides:
                overrides[bool_key] = parse_bool(
                    overrides[bool_key], f"{base}.{bool_key}"
                )


class ConfigManager:
    """配置管理器"""

    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.config = self._load_config()

    def _load_config(self) -> WeReadConfig:
        """加载配置文件"""
        config_data = {}

        # 尝试加载YAML配置文件
        if Path(self.config_path).exists():
            try:
                if yaml is None:
                    raise ConfigError("config: 缺少 PyYAML，无法读取配置文件")
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config_data = yaml.safe_load(f) or {}
                if not isinstance(config_data, dict):
                    raise _config_error("config", "根节点必须是对象映射", config_data)
                config_data = self._resolve_config_tree(config_data)
                logging.info(f"✅ 已加载配置文件: {self.config_path}")
            except ConfigError:
                raise
            except yaml.YAMLError as exc:
                mark = getattr(exc, "problem_mark", None)
                location = "未知位置"
                if mark is not None:
                    location = f"第 {mark.line + 1} 行，第 {mark.column + 1} 列"
                raise ConfigError(
                    "config: YAML 解析失败，"
                    f"错误类型={type(exc).__name__}，位置={location}"
                ) from exc
            except OSError as exc:
                raise ConfigError(
                    "config: 配置文件无法读取，"
                    f"错误类型={type(exc).__name__}"
                ) from exc
            except Exception as e:
                raise ConfigError(
                    "config: 配置文件读取或 YAML 解析失败，"
                    f"错误类型={type(e).__name__}"
                ) from e

        # 从环境变量获取配置（优先级最高）
        config = WeReadConfig(
            startup_mode=self._get_config_value(
                config_data, "app.startup_mode", "STARTUP_MODE", "immediate"
            ),
            startup_delay=self._get_config_value(
                config_data, "app.startup_delay", "STARTUP_DELAY", "1-10"
            ),
            max_concurrent_users=parse_int(self._get_config_value(
                config_data, "app.max_concurrent_users",
                "MAX_CONCURRENT_USERS", "1"
            ), "app.max_concurrent_users", 1),
            curl_file_path=self._get_config_value(
                config_data, "curl_config.file_path",
                "WEREAD_CURL_BASH_FILE_PATH", ""
            ),
            curl_content=self._get_config_value(
                config_data, "curl_config.content", "WEREAD_CURL_STRING", ""
            ),
            users=self._load_user_configs(config_data),
        )

        # 加载阅读配置
        config.reading = ReadingConfig(
            mode=self._get_config_value(
                config_data, "reading.mode", "READING_MODE", "smart_random"
            ),
            target_duration=self._get_config_value(
                config_data, "reading.target_duration",
                "TARGET_DURATION", "60-70"
            ),
            reading_interval=self._get_config_value(
                config_data, "reading.reading_interval",
                "READING_INTERVAL", "25-35"
            ),
            use_curl_data_first=self._get_bool_config(
                config_data, "reading.use_curl_data_first",
                "USE_CURL_DATA_FIRST", True
            ),
            fallback_to_config=self._get_bool_config(
                config_data, "reading.fallback_to_config",
                "FALLBACK_TO_CONFIG", True
            ),
            max_consecutive_failures=parse_int(self._get_config_value(
                config_data, "reading.max_consecutive_failures",
                "MAX_CONSECUTIVE_FAILURES", "5"
            ), "reading.max_consecutive_failures", 1),
            books=self._load_books(config_data),
            smart_random=SmartRandomConfig(
                book_continuity=parse_float(self._get_config_value(
                    config_data, "reading.smart_random.book_continuity",
                    "BOOK_CONTINUITY", "0.8"
                ), "reading.smart_random.book_continuity", 0, 1),
                chapter_continuity=parse_float(self._get_config_value(
                    config_data, "reading.smart_random.chapter_continuity",
                    "CHAPTER_CONTINUITY", "0.7"
                ), "reading.smart_random.chapter_continuity", 0, 1),
                book_switch_cooldown=parse_int(self._get_config_value(
                    config_data, "reading.smart_random.book_switch_cooldown",
                    "BOOK_SWITCH_COOLDOWN", "300"
                ), "reading.smart_random.book_switch_cooldown", 0),
            ),
        )

        # 加载网络配置
        config.network = NetworkConfig(
            timeout=parse_int(self._get_config_value(
                config_data, "network.timeout", "NETWORK_TIMEOUT", "30"
            ), "network.timeout", 1),
            retry_times=parse_int(self._get_config_value(
                config_data, "network.retry_times", "RETRY_TIMES", "3"
            ), "network.retry_times", 1),
            retry_delay=self._get_config_value(
                config_data, "network.retry_delay", "RETRY_DELAY", "5-15"
            ),
            rate_limit=parse_int(self._get_config_value(
                config_data, "network.rate_limit", "RATE_LIMIT", "10"
            ), "network.rate_limit", 0),
        )

        # 加载人类行为模拟配置
        config.human_simulation = HumanSimulationConfig(
            enabled=self._get_bool_config(
                config_data, "human_simulation.enabled",
                "HUMAN_SIMULATION_ENABLED", False
            ),
            reading_speed_variation=self._get_bool_config(
                config_data, "human_simulation.reading_speed_variation",
                "READING_SPEED_VARIATION", True
            ),
            break_probability=parse_float(self._get_config_value(
                config_data, "human_simulation.break_probability",
                "BREAK_PROBABILITY", "0.1"
            ), "human_simulation.break_probability", 0, 1),
            break_duration=self._get_config_value(
                config_data, "human_simulation.break_duration",
                "BREAK_DURATION", "10-20"
            ),
            rotate_user_agent=self._get_bool_config(
                config_data, "human_simulation.rotate_user_agent",
                "ROTATE_USER_AGENT", False
            ),
        )

        # 加载通知配置
        notification_triggers = self._load_notification_triggers(config_data)
        only_on_failure = self._get_bool_or_none(
            config_data, "notification.only_on_failure",
            "NOTIFICATION_ONLY_ON_FAILURE"
        )

        if only_on_failure is True:
            notification_triggers[NotificationEvent.SESSION_SUCCESS] = False
            notification_triggers[NotificationEvent.MULTI_USER_SUMMARY] = False

        config.notification = NotificationConfig(
            enabled=self._get_bool_config(
                config_data, "notification.enabled",
                "NOTIFICATION_ENABLED", True
            ),
            include_statistics=self._get_bool_config(
                config_data, "notification.include_statistics",
                "INCLUDE_STATISTICS", True
            ),
            channels=self._load_notification_channels(config_data),
            triggers=notification_triggers,
            only_on_failure=only_on_failure,
        )

        # 加载hack配置
        config.hack = HackConfig(
            cookie_refresh_ql=self._get_bool_config(
                config_data, "hack.cookie_refresh_ql",
                "HACK_COOKIE_REFRESH_QL", False
            ),
        )

        # 加载调度配置
        config.schedule = ScheduleConfig(
            enabled=self._get_bool_config(
                config_data, "schedule.enabled", "SCHEDULE_ENABLED", False
            ),
            cron_expression=self._get_config_value(
                config_data, "schedule.cron_expression",
                "CRON_EXPRESSION", "0 */2 * * *"
            ),
            timezone=self._get_config_value(
                config_data, "schedule.timezone", "TIMEZONE", "Asia/Shanghai"
            ),
        )

        # 加载守护进程配置
        config.daemon = DaemonConfig(
            enabled=self._get_bool_config(
                config_data, "daemon.enabled", "DAEMON_ENABLED", False
            ),
            session_interval=self._get_config_value(
                config_data, "daemon.session_interval",
                "SESSION_INTERVAL", "120-180"
            ),
            max_daily_sessions=parse_int(self._get_config_value(
                config_data, "daemon.max_daily_sessions",
                "MAX_DAILY_SESSIONS", "12"
            ), "daemon.max_daily_sessions", 1),
        )

        # 加载日志配置
        config.logging = LoggingConfig(
            level=self._get_config_value(
                config_data, "logging.level", "LOG_LEVEL", "INFO"
            ),
            format=self._get_config_value(
                config_data, "logging.format", "LOG_FORMAT", "detailed"
            ),
            file=self._get_config_value(
                config_data, "logging.file", "LOG_FILE", "logs/weread.log"
            ),
            max_size=self._get_config_value(
                config_data, "logging.max_size", "LOG_MAX_SIZE", "10MB"
            ),
            backup_count=parse_int(self._get_config_value(
                config_data, "logging.backup_count", "LOG_BACKUP_COUNT", "5"
            ), "logging.backup_count", 0),
            console=self._get_bool_config(
                config_data, "logging.console", "LOG_CONSOLE", True
            ),
        )

        config.history = HistoryConfig(
            enabled=self._get_bool_config(
                config_data, "history.enabled", "HISTORY_ENABLED", True
            ),
            file=self._get_config_value(
                config_data, "history.file", "HISTORY_FILE",
                "logs/run-history.json"
            ),
            max_entries=parse_int(self._get_config_value(
                config_data, "history.max_entries", "HISTORY_MAX_ENTRIES",
                "50"
            ), "history.max_entries", 1),
            persist_runtime_error=self._get_bool_config(
                config_data,
                "history.persist_runtime_error",
                "HISTORY_PERSIST_RUNTIME_ERROR",
                True,
            ),
        )

        validate_config_semantics(config)
        return config

    def _load_books(self, config_data: dict) -> List[BookInfo]:
        """加载书籍配置"""
        books = []

        # 从YAML配置加载
        books_config = self._get_nested_dict_value(
            config_data, "reading.books"
        )
        if books_config and isinstance(books_config, list):
            for book_data in books_config:
                if isinstance(book_data, dict):
                    name = book_data.get("name", "")
                    book_id = book_data.get("book_id", "")
                    chapters_config = book_data.get("chapters", [])
                    
                    if name and book_id and isinstance(chapters_config, list):
                        # 处理章节配置，支持两种格式
                        chapters = []
                        chapter_infos = []
                        
                        for chapter_item in chapters_config:
                            if isinstance(chapter_item, str):
                                # 格式：只有章节ID字符串
                                chapters.append(chapter_item)
                                chapter_infos.append(ChapterInfo(chapter_id=chapter_item))
                            elif isinstance(chapter_item, dict):
                                # 格式：包含章节ID和可选的索引
                                chapter_id = chapter_item.get("chapter_id") or chapter_item.get("id")
                                chapter_index = chapter_item.get("chapter_index")
                                if chapter_index is None:
                                    chapter_index = chapter_item.get("index")
                                
                                if chapter_id:
                                    chapters.append(chapter_id)  # 保持向后兼容
                                    chapter_infos.append(ChapterInfo(
                                        chapter_id=chapter_id,
                                        chapter_index=chapter_index
                                    ))
                        
                        if chapters:
                            books.append(BookInfo(
                                name=name,
                                book_id=book_id,
                                chapters=chapters,
                                chapter_infos=chapter_infos
                            ))
                        logging.info(
                            f"✅ 已加载书籍配置: {name} ({book_id}), "
                            f"章节数: {len(chapters)}"
                        )
                    else:
                        logging.warning(f"⚠️ 跳过无效的书籍配置: {book_data}")

        # 如果没有配置，则返回空列表
        if not books:
            logging.info("ℹ️ 未配置书籍信息，将使用CURL数据或运行时动态添加")
            return []

        return books

    def _load_notification_triggers(self, config_data: dict) -> Dict[
        NotificationEvent, bool
    ]:
        """加载通知触发配置"""
        raw_triggers = self._get_nested_dict_value(
            config_data, "notification.triggers"
        )
        triggers = default_notification_triggers()

        if isinstance(raw_triggers, dict):
            for key, value in raw_triggers.items():
                try:
                    event = NotificationEvent(key)
                except ValueError:
                    logging.warning(f"⚠️ 未知通知事件: {key}")
                    continue

                triggers[event] = parse_bool(
                    value, f"notification.triggers.{key}"
                )

        return triggers

    def _get_bool_or_none(self, config_data: dict, yaml_path: str,
                           env_key: str) -> Optional[bool]:
        """获取布尔配置，可返回None"""
        env_value = self._get_env_override(env_key)
        yaml_value = self._get_nested_dict_value(config_data, yaml_path)

        value = env_value if env_value is not None else yaml_value
        if value is None:
            return None

        return parse_bool(value, yaml_path)

    def _get_env_override(self, env_key: str) -> Optional[str]:
        """读取环境变量；空字符串和纯空白不参与配置覆盖。"""
        value = os.getenv(env_key)
        if value is None or not value.strip():
            return None
        return value

    def _get_config_value(self, config_data: dict, yaml_path: str,
                          env_key: str, default: Any) -> Any:
        """获取配置值，优先级：环境变量 > YAML > 默认值"""
        # 先检查环境变量
        env_value = self._get_env_override(env_key)
        if env_value is not None:
            # 处理环境变量中的占位符
            env_value = self._resolve_env_placeholders(env_value, yaml_path)
            return self._parse_config_value(env_value, type(default))

        # 再检查YAML配置
        yaml_value = self._get_nested_dict_value(config_data, yaml_path)
        if yaml_value is not None:
            yaml_value = self._resolve_env_placeholders(yaml_value, yaml_path)
            return self._parse_config_value(yaml_value, type(default))

        return default

    def _get_bool_config(self, config_data: dict, yaml_path: str,
                         env_key: str, default: bool) -> bool:
        """获取布尔类型配置值"""
        value = self._get_config_value(
            config_data, yaml_path, env_key, default
        )
        return parse_bool(value, yaml_path)

    def _get_nested_dict_value(self, data: dict, path: str) -> Any:
        """从嵌套字典中获取值"""
        keys = path.split('.')
        current = data
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current

    def _resolve_env_placeholders(self, value: Any, path: str) -> Any:
        """解析环境变量占位符"""
        if not isinstance(value, str):
            return value
        import re
        pattern = r'\$\{([^}]+)\}'

        def replace_match(match):
            env_var = match.group(1)
            resolved = os.getenv(env_var)
            if resolved is None:
                raise _config_error(path, f"环境变量 {env_var} 未设置", value)
            return resolved

        return re.sub(pattern, replace_match, value)

    def _resolve_config_tree(self, value: Any, path: str = "") -> Any:
        """递归解析 YAML 中任意位置的环境变量占位符。"""
        if isinstance(value, dict):
            return {
                key: self._resolve_config_tree(
                    item, f"{path}.{key}" if path else str(key)
                )
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [
                self._resolve_config_tree(item, f"{path}[{index}]")
                for index, item in enumerate(value)
            ]
        return self._resolve_env_placeholders(value, path or "config")

    def _parse_config_value(self, value: str, target_type: type) -> Any:
        """解析配置值为指定类型"""
        if target_type == list:
            if (isinstance(value, str) and
                    value.startswith('[') and value.endswith(']')):
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return []
            return []
        return value

    def _load_notification_channels(
        self, config_data: dict
    ) -> List[NotificationChannel]:
        """加载通知通道配置"""
        channels = []

        # 从YAML配置加载
        channels_config = self._get_nested_dict_value(
            config_data, "notification.channels"
        )
        if channels_config and isinstance(channels_config, list):
            for channel_data in channels_config:
                if isinstance(channel_data, dict):
                    # 应用环境变量覆盖到通道配置
                    channel_config = self._apply_env_overrides_to_channel(
                        channel_data.get("name"), 
                        channel_data.get("config", {})
                    )
                    
                    channel = NotificationChannel(
                        name=channel_data.get("name"),
                        enabled=self._get_bool_config(
                            channel_data, "enabled", "ENABLED", True
                        ),
                        config=channel_config
                    )
                    channels.append(channel)

        # 如果没有YAML配置，但有环境变量，自动创建通道
        if not channels:
            channels = self._create_channels_from_env_vars()

        return channels

    def _apply_env_overrides_to_channel(
        self, channel_name: str, base_config: dict
    ) -> dict:
        """按通道字段表应用环境变量覆盖。"""
        config = dict(base_config or {})
        field_mapping = NOTIFICATION_CHANNEL_ENV_FIELDS.get(
            channel_name, {}
        )
        for field_name, env_name in field_mapping.items():
            env_value = self._get_env_override(env_name)
            if env_value is None:
                continue
            if channel_name == "gotify" and field_name == "priority":
                config[field_name] = parse_int(
                    env_value,
                    "notification.channels.gotify.config.priority",
                )
            else:
                config[field_name] = env_value

        if channel_name == "telegram":
            proxy_config = dict(config.get("proxy") or {})
            http_proxy = self._get_env_override("HTTP_PROXY")
            https_proxy = self._get_env_override("HTTPS_PROXY")
            if http_proxy is not None:
                proxy_config["http"] = http_proxy
            if https_proxy is not None:
                proxy_config["https"] = https_proxy
            if proxy_config:
                config["proxy"] = proxy_config

        return config

    def _create_channels_from_env_vars(self) -> List[NotificationChannel]:
        """从字段表创建环境变量配置完整的通知通道。"""
        channels = []
        for channel_name in NOTIFICATION_CHANNEL_ENV_FIELDS:
            channel_config = self._apply_env_overrides_to_channel(
                channel_name, {}
            )
            required_fields = NOTIFICATION_CHANNEL_REQUIRED_FIELDS.get(
                channel_name, []
            )
            if required_fields and all(
                channel_config.get(field_name)
                for field_name in required_fields
            ):
                channels.append(
                    NotificationChannel(
                        name=channel_name,
                        enabled=True,
                        config=channel_config,
                    )
                )

        if channels:
            logging.info(
                "✅ 从环境变量自动创建了 %s 个通知通道", len(channels)
            )
        return channels
    def _load_user_configs(self, config_data: dict) -> List[UserConfig]:
        """加载用户配置"""
        users = []
        # 1) YAML 配置（优先）
        users_config = self._get_nested_dict_value(
            config_data, "curl_config.users"
        )
        if users_config and isinstance(users_config, list):
            for index, user_data in enumerate(users_config):
                if isinstance(user_data, dict) and user_data.get("name"):
                    cookie_refresh_ql = user_data.get("cookie_refresh_ql")
                    if cookie_refresh_ql is not None:
                        cookie_refresh_ql = parse_bool(
                            cookie_refresh_ql,
                            f"curl_config.users[{index}].cookie_refresh_ql",
                        )
                    user = UserConfig(
                        name=user_data.get("name"),
                        file_path=user_data.get("file_path", ""),
                        content=user_data.get("content", ""),
                        cookie_refresh_ql=cookie_refresh_ql,
                        reading_overrides=user_data.get(
                            "reading_overrides", {}
                        )
                    )
                    users.append(user)
                    logging.info(f"✅ 已加载用户配置: {user.name}")

        # 2) 回退：WEREAD_CURL_STRING 按“至少两个空行”拆分为多用户
        if not users:
            curl_env = self._get_env_override("WEREAD_CURL_STRING")
            if curl_env:
                import re
                segments = [seg.strip() for seg in re.split(r'(?:\r?\n\s*){2,}', curl_env) if seg.strip()]
                if len(segments) > 1:
                    for idx, seg in enumerate(segments, start=1):
                        users.append(UserConfig(
                            name=f"env_user_{idx}",
                            content=seg
                        ))
                    logging.info(
                        f"✅ 已从 WEREAD_CURL_STRING 拆分出 {len(users)} 个用户配置（需至少两行空行分隔）"
                    )
                elif segments:
                    # 只有一个片段，仍然按单用户处理
                    users.append(UserConfig(
                        name="env_user_1",
                        content=segments[0]
                    ))

        return users


# ==========================
# 协议与 HTTP 处理
# ==========================


class RandomHelper:
    """随机数助手类"""

    @staticmethod
    def parse_range(range_str: str) -> Tuple[float, float]:
        """解析范围字符串，如 "60-120" 或 "30" """
        normalized_range = str(range_str).strip()
        if not normalized_range:
            raise ValueError("范围不能为空")

        if '-' in normalized_range:
            parts = [part.strip() for part in normalized_range.split('-', 1)]
            if not parts[0] or not parts[1]:
                raise ValueError(f"无效范围格式: {range_str}")
            min_value = float(parts[0])
            max_value = float(parts[1])
            if max_value < min_value:
                raise ValueError(f"范围上限不能小于下限: {range_str}")
            return min_value, max_value

        value = float(normalized_range)
        return value, value

    @staticmethod
    def get_random_from_range(range_str: str) -> float:
        """从范围字符串获取随机数"""
        min_val, max_val = RandomHelper.parse_range(range_str)
        return random.uniform(min_val, max_val)

    @staticmethod
    def get_random_int_from_range(range_str: str) -> int:
        """从范围字符串获取随机整数"""
        return int(RandomHelper.get_random_from_range(range_str))


async def interruptible_sleep(
    seconds: float, is_cancelled: Callable[[], bool]
) -> bool:
    """分段休眠；取消时返回 False，完整休眠返回 True。"""
    remaining = max(0.0, float(seconds))
    while remaining > 0:
        if is_cancelled():
            return False
        step = min(remaining, 1.0)
        await asyncio.sleep(step)
        remaining -= step
    return not is_cancelled()


def is_successful_read_response(response_data: Dict[str, Any]) -> bool:
    """仅接受同时包含真值 succ 和非空 synckey 的响应。"""
    return bool(response_data.get("succ")) and bool(
        response_data.get("synckey")
    )


def load_curl_source(
    file_path: str, inline_content: str, path: str
) -> str:
    """按文件优先、内嵌内容回退的规则读取 CURL。"""
    if file_path and Path(file_path).exists():
        try:
            return Path(file_path).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ConfigError(
                f"{path}.file_path: CURL 文件无法读取，"
                f"当前值={file_path!r}"
            ) from exc
    return str(inline_content or "").strip()


class RateLimiter:
    """简单的异步速率限制器，按请求/分钟限制"""

    def __init__(self, rate_limit: int):
        self.rate_limit = max(0, rate_limit)
        self._interval = (60.0 / self.rate_limit) if self.rate_limit > 0 else 0
        self._lock = asyncio.Lock()
        self._last_acquire = 0.0

    async def acquire(self):
        """按需等待确保不超过速率"""
        if self.rate_limit <= 0:
            return

        async with self._lock:
            now = time.monotonic()
            wait_time = self._interval - (now - self._last_acquire)
            if wait_time > 0:
                await asyncio.sleep(wait_time)
                now = time.monotonic()
            self._last_acquire = now


class CurlParser:
    """CURL命令解析器"""

    @staticmethod
    def _get_header_case_insensitive(
        headers: Dict[str, str], header_name: str
    ) -> str:
        """不区分大小写获取header值"""
        target_name = header_name.lower()
        for key, value in headers.items():
            if key.lower() == target_name:
                return value
        return ""

    @staticmethod
    def _extract_request_data(curl_command: str) -> Dict[str, Any]:
        """提取请求数据，兼容单引号和双引号"""
        patterns = [
            r"--data-raw\s+'([^']*)'",
            r'--data-raw\s+"([^"]*)"',
            r"--data-binary\s+'([^']*)'",
            r'--data-binary\s+"([^"]*)"',
        ]

        for pattern in patterns:
            data_match = re.search(pattern, curl_command, re.DOTALL)
            if not data_match:
                continue

            raw_payload = data_match.group(1).strip()
            if not raw_payload:
                return {}

            try:
                request_data = json.loads(raw_payload)
                logging.debug(
                    "从 CURL 提取请求字段: %s",
                    ", ".join(sorted(request_data.keys())),
                )
                return request_data
            except json.JSONDecodeError as e:
                logging.warning(f"⚠️ 解析请求数据JSON失败: {e}")
                return {}

        return {}

    @staticmethod
    def parse_curl_command(curl_command: str) -> Tuple[
        Dict[str, str], Dict[str, str], Dict[str, Any]
    ]:
        """
        提取bash接口中的headers、cookies和请求数据
        支持 -H 'Cookie: xxx' 和 -b 'xxx' 两种方式的cookie提取
        支持 --data-raw 'json' 方式的请求数据提取
        """
        headers_temp = {}

        # 提取 headers
        for match in re.findall(r"-H '([^:]+): ([^']+)'", curl_command):
            headers_temp[match[0]] = match[1]

        # 提取 cookies
        cookies = {}

        # 从 -H 'Cookie: xxx' 提取
        cookie_header = next((v for k, v in headers_temp.items()
                             if k.lower() == 'cookie'), '')

        # 从 -b 'xxx' 提取
        cookie_b = re.search(r"-b '([^']+)'", curl_command)
        cookie_string = cookie_b.group(1) if cookie_b else cookie_header

        # 解析 cookie 字符串
        if cookie_string:
            for cookie in cookie_string.split(';'):
                cookie = cookie.strip()
                if not cookie:
                    continue
                if '=' in cookie:
                    key, value = cookie.split('=', 1)
                    cookies[key.strip()] = value.strip()

        # 移除 headers 中的 Cookie
        headers = {
            k: v for k, v in headers_temp.items()
            if k.lower() != 'cookie'
        }

        # 提取请求数据
        request_data = CurlParser._extract_request_data(curl_command)

        return headers, cookies, request_data

    @staticmethod
    def validate_curl_headers(headers: Dict[str, str],
                             cookies: Dict[str, str],
                             request_data: Dict[str, Any],
                             user_name: str = "default") -> Tuple[bool, List[str]]:
        """
        验证 CURL headers 和 cookies 的合法性

        Args:
            headers: 解析出的 headers
            cookies: 解析出的 cookies
            request_data: 解析出的请求数据
            user_name: 用户名称（用于日志）

        Returns:
            Tuple[bool, List[str]]: (是否有效, 错误信息列表)
        """
        errors = []
        warnings = []

        # 1. 验证必需的 cookies
        required_cookies = ['wr_skey']
        missing_cookies = [cookie for cookie in required_cookies if cookie not in cookies]
        if missing_cookies:
            errors.append(f"缺少必需的认证 cookies: {', '.join(missing_cookies)}")

        # 2. 验证 wr_skey 的格式（应该是一个较长的字符串）
        if 'wr_skey' in cookies:
            skey_value = cookies['wr_skey']
            if len(skey_value) < 8:
                errors.append(f"wr_skey 长度异常: {len(skey_value)} 字符，可能无效")
            else:
                warnings.append(
                    f"wr_skey 验证通过: {_secret_marker(skey_value)}"
                )

        # 3. 验证 User-Agent
        user_agent = CurlParser._get_header_case_insensitive(
            headers, 'user-agent'
        )
        if not user_agent:
            errors.append("缺少 User-Agent header")
        elif 'mozilla' not in user_agent.lower():
            warnings.append(f"User-Agent 可能异常: {user_agent[:50]}...")
        else:
            warnings.append(f"User-Agent 验证通过: {user_agent.split(' ')[0]}...")

        # 4. 验证请求数据中的必需字段
        required_data_fields = ['appId', 'ps', 'pc']
        missing_fields = [field for field in required_data_fields if field not in request_data]
        if missing_fields:
            errors.append(f"请求数据中缺少必需字段: {', '.join(missing_fields)}")

        # 5. 验证请求数据字段格式
        for field in required_data_fields:
            if field in request_data:
                value = str(request_data[field])
                if len(value) < 4:
                    errors.append(
                        f"字段 {field} 长度异常: {len(value)} 字符"
                    )
                else:
                    warnings.append(
                        f"字段 {field} 验证通过: {_secret_marker(value)}"
                    )

        # 6. 验证书籍和章节字段（如果存在）
        if 'b' in request_data and 'c' in request_data:
            book_id = str(request_data['b'])
            chapter_id = str(request_data['c'])
            if len(book_id) < 10 or len(chapter_id) < 10:
                warnings.append(f"书籍或章节ID可能异常: book={book_id[:10]}..., chapter={chapter_id[:10]}...")
            else:
                warnings.append(f"书籍和章节ID验证通过: book={book_id[:10]}..., chapter={chapter_id[:10]}...")

        # 记录验证结果
        # if warnings:
        #     for warning in warnings:
        #         logging.info(f"🔍 用户 {user_name} 验证提示: {warning}")

        if errors:
            for error in errors:
                logging.error(f"❌ 用户 {user_name} 验证错误: {error}")
            return False, errors

        logging.info(f"✅ 用户 {user_name} CURL 配置验证通过")
        return True, []


def classify_runtime_error(exc: Exception) -> RuntimeErrorCategory:
    """对运行时错误进行统一分类"""
    network_error_types: List[type] = [TimeoutError, ConnectionError]
    if requests is not None:
        network_error_types.append(requests.RequestException)
    if httpx is not None:
        network_error_types.append(httpx.HTTPError)

    if isinstance(exc, tuple(network_error_types)):
        return RuntimeErrorCategory.NETWORK

    message = str(exc).lower()
    config_keywords = [
        "config",
        "配置",
        "yaml",
        "未配置curl",
        "未找到有效的curl配置",
        "配置文件",
        "reading_overrides",
        "curl_config.users",
        "范围不能为空",
        "无效范围格式",
    ]
    auth_keywords = [
        "wr_skey",
        "cookie",
        "认证",
        "user-agent",
        "appid",
        "ps",
        "pc",
        "curl配置验证失败",
    ]
    protocol_keywords = [
        "synckey",
        "协议",
        "chapter",
        "book",
        "响应",
        "hash",
    ]
    notification_keywords = [
        "通知",
        "pushplus",
        "telegram",
        "wxpusher",
        "bark",
        "ntfy",
        "feishu",
        "wework",
        "dingtalk",
        "gotify",
        "serverchan3",
        "pushdeer",
    ]

    if any(keyword in message for keyword in auth_keywords):
        return RuntimeErrorCategory.AUTH
    if any(keyword in message for keyword in config_keywords):
        return RuntimeErrorCategory.CONFIG
    if any(keyword in message for keyword in protocol_keywords):
        return RuntimeErrorCategory.PROTOCOL
    if any(keyword in message for keyword in notification_keywords):
        return RuntimeErrorCategory.NOTIFICATION
    return RuntimeErrorCategory.UNKNOWN


def format_error_message(message: str, exc: Exception) -> str:
    """生成带分类前缀的错误消息"""
    category = classify_runtime_error(exc)
    return f"[{category.value}] {message}: {exc}"


class HttpClient:
    """异步HTTP客户端封装，内置重试与速率限制"""

    def __init__(self, config: NetworkConfig):
        if httpx is None:
            raise ImportError("缺少依赖 httpx，请先安装 requirements.txt")
        self.config = config
        self.request_times: List[float] = []
        self._rate_limiter = RateLimiter(config.rate_limit)
        self._client = httpx.AsyncClient(
            timeout=config.timeout,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=20)
        )

    async def close(self):
        await self._client.aclose()

    async def post_json(
        self, url: str, data: dict, headers: dict, cookies: dict
    ) -> Tuple[dict, float]:
        response, elapsed = await self._request_with_retries(
            url, headers=headers, cookies=cookies, json_data=data
        )
        return response.json(), elapsed

    async def post_raw(
        self, url: str, headers: dict = None, cookies: dict = None,
        json_data: dict = None, data: Any = None
    ) -> Tuple[httpx.Response, float]:
        return await self._request_with_retries(
            url, headers=headers, cookies=cookies,
            json_data=json_data, data=data
        )

    async def _request_with_retries(
        self, url: str, headers: dict = None, cookies: dict = None,
        json_data: dict = None, data: Any = None
    ) -> Tuple[httpx.Response, float]:
        attempts = max(1, self.config.retry_times)
        last_error = None

        for attempt in range(attempts):
            start_time = time.monotonic()
            try:
                await self._rate_limiter.acquire()
                response = await self._client.post(
                    url,
                    headers=headers,
                    cookies=cookies,
                    json=json_data,
                    data=data
                )
                response.raise_for_status()
                elapsed = time.monotonic() - start_time
                self.request_times.append(elapsed)
                return response, elapsed
            except Exception as exc:
                elapsed = time.monotonic() - start_time
                self.request_times.append(elapsed)
                last_error = exc
                delay = 0.0
                if attempt < attempts - 1:
                    delay = RandomHelper.get_random_from_range(
                        self.config.retry_delay
                    )
                category = classify_runtime_error(exc).value
                logging.warning(
                    "HTTP 请求失败: url=%s attempt=%s/%s next_delay=%.2fs",
                    safe_url_for_log(url),
                    attempt + 1,
                    attempts,
                    delay,
                    extra={
                        "event": "http_retry",
                        "attempt": attempt + 1,
                        "max_attempts": attempts,
                        "delay": delay,
                        "error_category": category,
                        "elapsed_ms": int(elapsed * 1000),
                    },
                )
                if attempt < attempts - 1:
                    await interruptible_sleep(delay, lambda: False)

        raise last_error if last_error else RuntimeError("请求失败")

class UserAgentRotator:
    """User-Agent轮换器"""

    USER_AGENTS = [
        ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
         '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'),
        ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
         '(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'),
        ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
         'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 '
         'Safari/537.36'),
        ('Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) '
         'Gecko/20100101 Firefox/132.0'),
        ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
         'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1.1 '
         'Safari/605.1.15')
    ]

    @classmethod
    def get_random_user_agent(cls) -> str:
        """获取随机User-Agent"""
        return random.choice(cls.USER_AGENTS)


# =========================
# 阅读策略与流程
# =========================


class SmartReadingManager:
    """智能阅读管理器"""

    def __init__(self, reading_config: ReadingConfig):
        self.config = reading_config
        self.current_book_id = ""
        self.current_book_name = ""
        self.current_chapter_id = ""
        self.current_chapter_ci = None  # 当前章节的索引ID
        self.current_book_chapters = []
        self.current_chapter_index = 0
        self.last_book_switch_time = 0
        
        # 创建书籍ID到章节的映射（保持向后兼容）
        self.book_chapters_map = {
            book.book_id: book.chapters for book in reading_config.books
        }
        # 创建书籍ID到书名的映射
        self.book_names_map = {
            book.book_id: book.name for book in reading_config.books
        }
        # 创建书籍ID到章节信息的映射
        self.book_chapter_infos_map = {
            book.book_id: book.chapter_infos for book in reading_config.books
        }
        # 创建章节ID到章节索引的映射
        self.chapter_index_map = {}
        for book in reading_config.books:
            for chapter_info in book.chapter_infos:
                if chapter_info.chapter_index is not None:
                    self.chapter_index_map[chapter_info.chapter_id] = chapter_info.chapter_index

    def _set_current_position(
        self,
        book_id: str,
        chapter_id: str,
        chapter_list: List[str],
        chapter_index: Optional[int] = None,
        curl_ci: Optional[int] = None,
    ):
        """统一设置当前阅读位置，集中处理章节索引兼容逻辑"""
        self.current_book_id = book_id
        self.current_book_name = self.book_names_map.get(book_id, "未知书籍")
        self.current_chapter_id = chapter_id
        self.current_book_chapters = chapter_list
        if chapter_index is None and chapter_id in chapter_list:
            chapter_index = chapter_list.index(chapter_id)
        self.current_chapter_index = (
            chapter_index if chapter_index is not None else 0
        )
        self.current_chapter_ci = self.get_chapter_index(chapter_id, curl_ci)

    def get_chapter_index(self, chapter_id: str, curl_ci: Optional[int] = None) -> Optional[int]:
        """
        获取章节索引，按照优先级：配置的索引值 > 自动计算的索引 > CURL提取的值
        
        Args:
            chapter_id: 章节ID
            curl_ci: 从CURL提取的章节索引
        
        Returns:
            章节索引，如果都没有则返回None
        """
        # 优先级1：配置的索引值
        if chapter_id in self.chapter_index_map:
            return self.chapter_index_map[chapter_id]
        
        # 优先级2：CURL提取的值
        if curl_ci is not None:
            return curl_ci
        
        # 优先级3：自动计算的索引（当前章节在列表中的位置）
        if self.current_book_chapters and chapter_id in self.current_book_chapters:
            return self.current_book_chapters.index(chapter_id)
        
        return None

    def set_curl_data(self, book_id: str, chapter_id: str):
        """设置从CURL提取的数据作为起点"""
        book_name = self.book_names_map.get(
            book_id, f"未知书籍({book_id[:10]}...)"
        )
        logging.info(f"🔍 尝试设置CURL数据: 书籍={book_name}, 章节={chapter_id}")
        
        # 显示已配置的书籍信息
        if self.book_names_map:
            book_list = [
                f"{name}({book_id[:10]}...)" 
                for book_id, name in self.book_names_map.items()
            ]
            logging.info(f"🔍 当前配置的书籍: {', '.join(book_list)}")

        if not book_id or not chapter_id:
            logging.warning("⚠️ CURL数据为空，使用配置数据")
            return self._fallback_to_config()

        if self.config.use_curl_data_first:
            # 验证CURL数据的有效性
            if book_id in self.book_chapters_map:
                chapters = self.book_chapters_map[book_id]
                if chapter_id in chapters:
                    self._set_current_position(
                        book_id,
                        chapter_id,
                        chapters,
                        chapter_index=chapters.index(chapter_id),
                    )
                    logging.info(
                        f"✅ 使用CURL数据作为阅读起点: "
                        f"书籍《{self.current_book_name}》, 章节 {chapter_id}, "
                        f"索引 {self.current_chapter_ci if self.current_chapter_ci is not None else 'N/A'}"
                    )
                    return True
                else:
                    logging.warning(
                        f"⚠️ CURL章节 {chapter_id} 不在书籍《{book_name}》中"
                    )
                    # 尝试将章节添加到现有书籍
                    if self._add_chapter_to_book(book_id, chapter_id):
                        return True
            else:
                logging.warning(f"⚠️ CURL书籍《{book_name}》不在配置中")
                # 尝试添加新的书籍-章节组合
                if self._add_new_book_chapter(book_id, chapter_id):
                    return True

        # 回退到配置数据
        return self._fallback_to_config()

    def _add_chapter_to_book(self, book_id: str, chapter_id: str) -> bool:
        """将章节添加到现有书籍中"""
        if book_id in self.book_chapters_map:
            self.book_chapters_map[book_id].append(chapter_id)
            self._set_current_position(
                book_id,
                chapter_id,
                self.book_chapters_map[book_id],
                chapter_index=len(self.book_chapters_map[book_id]) - 1,
            )
            logging.info(
                f"✅ 已将章节 {chapter_id} 添加到书籍《{self.current_book_name}》, "
                f"索引 {self.current_chapter_ci if self.current_chapter_ci is not None else 'N/A'}"
            )
            return True
        return False

    def _add_new_book_chapter(self, book_id: str, chapter_id: str) -> bool:
        """添加新的书籍-章节组合"""
        book_name = f"动态书籍({book_id[:10]}...)"
        self.book_chapters_map[book_id] = [chapter_id]
        self.book_names_map[book_id] = book_name
        self._set_current_position(book_id, chapter_id, [chapter_id], 0)
        logging.info(
            f"✅ 已添加新的书籍-章节组合: 《{book_name}》 -> {chapter_id}, "
            f"索引 {self.current_chapter_ci if self.current_chapter_ci is not None else 'N/A'}"
        )
        return True

    def _fallback_to_config(self) -> bool:
        """回退到配置数据"""
        if self.config.fallback_to_config and self.book_chapters_map:
            first_book = list(self.book_chapters_map.keys())[0]
            first_book_name = self.book_names_map.get(first_book, "未知书籍")
            self._switch_to_book(first_book)
            logging.info(f"✅ 回退到配置数据: 书籍《{first_book_name}》")
            return True

        logging.error("❌ 无法初始化阅读数据：既没有有效的CURL数据，也没有配置数据")
        return False

    def get_next_reading_position(self) -> Tuple[str, str]:
        """获取下一个阅读位置"""
        mode = ReadingMode(self.config.mode)

        if mode == ReadingMode.SMART_RANDOM:
            return self._smart_random_position()
        elif mode == ReadingMode.SEQUENTIAL:
            return self._sequential_position()
        else:  # PURE_RANDOM
            return self._pure_random_position()

    def _smart_random_position(self) -> Tuple[str, str]:
        """智能随机选择位置"""
        logging.debug(
            f"🔍 智能随机模式 - 当前书籍: "
            f"《{self.current_book_name}》({self.current_book_id[:10]}...), "
            f"当前章节: {self.current_chapter_id}"
        )

        # 确保有有效的当前状态
        if not self.current_book_id or not self.current_book_chapters:
            logging.warning("⚠️ 智能随机模式缺少有效状态，回退到配置数据")
            if not self._fallback_to_config():
                # 如果回退也失败，使用纯随机模式
                return self._pure_random_position()

        current_time = time.time()

        # 检查是否应该换书（考虑冷却时间）
        should_switch_book = (
            current_time - self.last_book_switch_time >
            self.config.smart_random.book_switch_cooldown and
            random.random() > self.config.smart_random.book_continuity
        )

        if should_switch_book and len(self.book_chapters_map) > 1:
            # 随机选择其他书籍
            other_books = [
                bid for bid in self.book_chapters_map.keys()
                if bid != self.current_book_id
            ]
            new_book_id = random.choice(other_books)
            self._switch_to_book(new_book_id)
            self.last_book_switch_time = current_time
            new_book_name = self.book_names_map.get(new_book_id, "未知书籍")
            logging.info(f"📚 智能换书: 《{new_book_name}》")

        # 检查是否应该跳章节
        should_skip_chapter = (
            random.random() > self.config.smart_random.chapter_continuity
        )

        if should_skip_chapter:
            # 随机选择当前书籍的其他章节
            if len(self.current_book_chapters) > 1:
                next_index = random.randint(
                    0, len(self.current_book_chapters) - 1
                )
                next_chapter = self.current_book_chapters[next_index]
                self._set_current_position(
                    self.current_book_id,
                    next_chapter,
                    self.current_book_chapters,
                    chapter_index=next_index,
                )
                logging.info(f"📄 智能跳章节: {self.current_chapter_id}, "
                           f"索引 {self.current_chapter_ci if self.current_chapter_ci is not None else 'N/A'}")
            else:
                logging.debug("📄 当前书籍只有一个章节，无法跳章节")
        else:
            # 顺序阅读下一章节
            self._next_chapter()

        result = (self.current_book_id, self.current_chapter_id)
        logging.debug(
            f"🔍 智能随机选择结果: 书籍=《{self.current_book_name}》"
            f"({result[0][:10]}...), 章节={result[1]}"
        )
        return result

    def _sequential_position(self) -> Tuple[str, str]:
        """顺序阅读位置"""
        self._next_chapter()
        return self.current_book_id, self.current_chapter_id

    def _pure_random_position(self) -> Tuple[str, str]:
        """纯随机位置"""
        # 随机选择书籍
        book_id = random.choice(list(self.book_chapters_map.keys()))
        # 随机选择章节
        chapters = self.book_chapters_map[book_id]
        chapter_id = random.choice(chapters)

        self._set_current_position(
            book_id,
            chapter_id,
            chapters,
            chapter_index=chapters.index(chapter_id),
        )

        return book_id, chapter_id

    def _switch_to_book(self, book_id: str):
        """切换到指定书籍"""
        if book_id in self.book_chapters_map:
            chapter_list = self.book_chapters_map[book_id]
            self._set_current_position(
                book_id,
                chapter_list[0],
                chapter_list,
                chapter_index=0,
            )

    def _next_chapter(self):
        """移动到下一章节"""
        if not self.current_book_chapters:
            return

        self.current_chapter_index += 1

        # 如果超出当前书籍章节范围，切换到下一本书
        if self.current_chapter_index >= len(self.current_book_chapters):
            book_ids = list(self.book_chapters_map.keys())
            current_book_index = book_ids.index(self.current_book_id)

            # 切换到下一本书，如果是最后一本则回到第一本
            next_book_index = (current_book_index + 1) % len(book_ids)
            next_book_id = book_ids[next_book_index]

            self._switch_to_book(next_book_id)
            next_book_name = self.book_names_map.get(next_book_id, "未知书籍")
            logging.info(f"📚 顺序换书: 《{next_book_name}》")
        else:
            next_chapter = self.current_book_chapters[
                self.current_chapter_index
            ]
            self._set_current_position(
                self.current_book_id,
                next_chapter,
                self.current_book_chapters,
                chapter_index=self.current_chapter_index,
            )


class HumanBehaviorSimulator:
    """人类行为模拟器"""

    def __init__(self, config: HumanSimulationConfig):
        self.config = config
        self.last_speed_change = 0
        self.current_speed_factor = 1.0

    def should_take_break(self) -> bool:
        """判断是否应该休息"""
        if not self.config.enabled:
            return False
        return random.random() < self.config.break_probability

    def get_break_duration(self) -> int:
        """获取休息时长"""
        return RandomHelper.get_random_int_from_range(
            self.config.break_duration
        )

    def get_reading_interval(self, base_interval: str) -> float:
        """获取阅读间隔（考虑速度变化）"""
        base_time = RandomHelper.get_random_from_range(base_interval)

        if self.config.enabled and self.config.reading_speed_variation:
            # 每30秒左右改变一次阅读速度
            current_time = time.time()
            if current_time - self.last_speed_change > 30:
                self.current_speed_factor = random.uniform(0.8, 1.3)
                self.last_speed_change = current_time

            return base_time * self.current_speed_factor

        return base_time


# ==========================
# 调度与应用编排
# ==========================


class NotificationService:
    """通知服务"""

    def __init__(self, config: NotificationConfig):
        self.config = config

    def send_notification(
        self, message: str,
        event: NotificationEvent = NotificationEvent.GENERAL
    ) -> bool:
        """发送通知"""
        if not self.config.enabled:
            return True

        if not self._is_event_enabled(event):
            logging.info(
                f"🔕 通知事件 {event.value} 未启用，跳过发送"
            )
            return True

        success_count = 0
        total_channels = len([c for c in self.config.channels if c.enabled])

        if total_channels == 0:
            logging.warning("⚠️ 没有启用的通知通道")
            return True

        for channel in self.config.channels:
            channel_status, channel_reason, _ = inspect_notification_channel(
                channel
            )
            if channel_status == "disabled":
                continue
            if channel_status != "ready":
                logging.warning(
                    self._format_channel_result(
                        channel.name,
                        "跳过",
                        RuntimeErrorCategory.NOTIFICATION,
                        channel_reason,
                    )
                )
                continue

            try:
                if self._send_notification_to_channel(message, channel):
                    success_count += 1
                    logging.info(f"✅ 通道 {channel.name} 通知发送成功")
                else:
                    logging.warning(
                        self._format_channel_result(
                            channel.name,
                            "失败",
                            RuntimeErrorCategory.NOTIFICATION,
                            "请求发送失败，详见该通道日志",
                        )
                    )
            except Exception as e:
                logging.error(
                    self._format_channel_result(
                        channel.name,
                        "失败",
                        classify_runtime_error(e),
                        type(e).__name__,
                    )
                )

        logging.info(
            f"📊 通知发送完成: {success_count}/{total_channels} 个通道成功"
        )
        return success_count > 0

    async def send_notification_async(
        self, message: str,
        event: NotificationEvent = NotificationEvent.GENERAL
    ) -> bool:
        """在线程池中异步发送通知，避免阻塞事件循环"""
        return await asyncio.to_thread(self.send_notification, message, event)

    def _is_event_enabled(self, event: NotificationEvent) -> bool:
        """判断事件是否允许通知"""
        triggers = self.config.triggers or default_notification_triggers()
        return triggers.get(event, True)

    def _format_channel_result(
        self,
        channel_name: str,
        action: str,
        category: RuntimeErrorCategory,
        reason: str,
        affects_main_flow: bool = False,
    ) -> str:
        """格式化通知通道执行结果"""
        return (
            f"[{category.value}] 通道 {channel_name} {action}: {reason} "
            f"(影响主流程: {'是' if affects_main_flow else '否'})"
        )

    def _send_notification_to_channel(
        self, message: str, channel: NotificationChannel
    ) -> bool:
        """发送通知到特定通道"""
        try:
            if channel.name == "pushplus":
                return self._send_pushplus(message, channel.config)
            elif channel.name == "telegram":
                return self._send_telegram(message, channel.config)
            elif channel.name == "wxpusher":
                return self._send_wxpusher(message, channel.config)
            elif channel.name == "apprise":
                return self._send_apprise(message, channel.config)
            elif channel.name == "bark":
                return self._send_bark(message, channel.config)
            elif channel.name == "ntfy":
                return self._send_ntfy(message, channel.config)
            elif channel.name == "feishu":
                return self._send_feishu(message, channel.config)
            elif channel.name == "wework":
                return self._send_wework(message, channel.config)
            elif channel.name == "dingtalk":
                return self._send_dingtalk(message, channel.config)
            elif channel.name == "gotify":
                return self._send_gotify(message, channel.config)
            elif channel.name == "serverchan3":
                return self._send_serverchan3(message, channel.config)
            elif channel.name == "pushdeer":
                return self._send_pushdeer(message, channel.config)
            else:
                logging.warning(f"⚠️ 未知的通知通道: {channel.name}")
                return False
        except Exception as e:
            logging.error(
                "❌ 通道 %s 通知发送失败: %s",
                channel.name,
                type(e).__name__,
            )
            return False

    def _send_pushplus(self, message: str, config: Dict[str, Any]) -> bool:
        """发送PushPlus通知"""
        if not config.get("token"):
            logging.error("❌ PushPlus token未配置")
            return False

        url = "https://www.pushplus.plus/send"
        data = {
            "token": config["token"],
            "title": "微信读书自动阅读报告",
            "content": message
        }

        return self._send_http_notification(url, data, "PushPlus")

    def _send_telegram(self, message: str, config: Dict[str, Any]) -> bool:
        """发送Telegram通知"""
        if (not config.get("bot_token") or not config.get("chat_id")):
            logging.error("❌ Telegram配置不完整")
            return False

        url = (f"https://api.telegram.org/bot"
               f"{config['bot_token']}/sendMessage")
        data = {
            "chat_id": config["chat_id"],
            "text": message
        }

        # 设置代理
        proxies = {}
        proxy_config = config.get("proxy", {})
        if proxy_config.get("http"):
            proxies['http'] = proxy_config["http"]
        if proxy_config.get("https"):
            proxies['https'] = proxy_config["https"]

        return self._send_http_notification(url, data, "Telegram", proxies)

    def _send_wxpusher(self, message: str, config: Dict[str, Any]) -> bool:
        """发送WxPusher通知"""
        if not config.get("spt"):
            logging.error("❌ WxPusher SPT未配置")
            return False

        # 使用极简方式
        url = (f"https://wxpusher.zjiecode.com/api/send/message/"
               f"{config['spt']}/"
               f"{urllib.parse.quote(message)}")

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            logging.info("✅ WxPusher通知发送成功")
            return True
        except Exception as e:
            logging.error("❌ WxPusher通知发送失败: %s", type(e).__name__)
            return False

    def _post_json_notification(
        self,
        url: str,
        data: dict,
        service_name: str,
        proxies: dict = None,
        headers: dict = None,
        timeout: int = 10,
        use_json_body: bool = False,
    ) -> bool:
        """发送 JSON 类型通知请求"""
        max_retries = 3

        for attempt in range(max_retries):
            try:
                request_headers = headers.copy() if headers else {}
                request_kwargs = {"timeout": timeout}
                if proxies:
                    request_kwargs["proxies"] = proxies

                if use_json_body:
                    if request_headers:
                        request_kwargs["headers"] = request_headers
                    request_kwargs["json"] = data
                else:
                    request_headers.setdefault(
                        "Content-Type", "application/json"
                    )
                    request_kwargs["headers"] = request_headers
                    request_kwargs["data"] = json.dumps(
                        data, ensure_ascii=False
                    ).encode("utf-8")

                response = requests.post(url, **request_kwargs)

                response.raise_for_status()
                logging.info(f"✅ {service_name}通知发送成功")
                return True

            except Exception as e:
                logging.error(
                    f"❌ {service_name}通知发送失败 "
                    f"(尝试 {attempt + 1}/{max_retries}): {type(e).__name__}"
                )
                if attempt < max_retries - 1:
                    time.sleep(random.randint(5, 15))

        return False

    def _send_http_notification(self, url: str, data: dict,
                                service_name: str,
                                proxies: dict = None, headers: dict = None) -> bool:
        """兼容旧接口的HTTP通知发送封装"""
        return self._post_json_notification(
            url,
            data,
            service_name,
            proxies=proxies,
            headers=headers,
            timeout=30 if service_name == "Telegram" else 10,
            use_json_body=(service_name == "Telegram"),
        )

    def _send_apprise(self, message: str, config: Dict[str, Any]) -> bool:
        """发送Apprise通知"""
        if not config.get("url"):
            logging.error("❌ Apprise URL未配置")
            return False

        try:
            # 尝试导入apprise库
            try:
                import apprise
            except ImportError:
                logging.error("❌ Apprise库未安装，请执行: pip install apprise")
                return False

            # 创建Apprise对象
            apobj = apprise.Apprise()

            # 添加通知服务
            if not apobj.add(config["url"]):
                logging.error("❌ Apprise URL格式无效")
                return False

            # 发送通知
            if apobj.notify(
                title="微信读书自动阅读报告",
                body=message
            ):
                logging.info("✅ Apprise通知发送成功")
                return True
            else:
                logging.error("❌ Apprise通知发送失败")
                return False

        except Exception as e:
            logging.error("❌ Apprise通知发送失败: %s", type(e).__name__)
            return False

    def _send_bark(self, message: str, config: Dict[str, Any]) -> bool:
        """发送Bark通知"""
        if not config.get("server") or not config.get("device_key"):
            logging.error("❌ Bark配置不完整（需要server和device_key）")
            return False

        # 构建Bark URL
        bark_url = (f"{config['server'].rstrip('/')}/"
                    f"{config['device_key']}")

        # 准备数据
        data = {
            "title": "微信读书自动阅读报告",
            "body": message
        }

        # 添加音效（如果配置了）
        if config.get("sound"):
            data["sound"] = config["sound"]

        return self._send_http_notification(bark_url, data, "Bark")

    def _send_ntfy(self, message: str, config: Dict[str, Any]) -> bool:
        """发送Ntfy通知"""
        if not config.get("server") or not config.get("topic"):
            logging.error("❌ Ntfy配置不完整（需要server和topic）")
            return False

        # 使用 JSON 发布，避免中文标题放入 HTTP 头时触发 Latin-1 编码错误
        ntfy_url = config["server"].rstrip("/")

        try:
            headers = {}
            payload = {
                "topic": config["topic"],
                "message": message,
                "title": "微信读书自动阅读报告",
            }

            # 添加认证token（如果配置了）
            if config.get("token"):
                headers["Authorization"] = f"Bearer {config['token']}"

            # 发送POST请求
            response = requests.post(
                ntfy_url,
                json=payload,
                headers=headers,
                timeout=10
            )

            response.raise_for_status()
            logging.info("✅ Ntfy通知发送成功")
            return True

        except Exception as e:
            logging.error("❌ Ntfy通知发送失败: %s", type(e).__name__)
            return False

    def _send_feishu(self, message: str, config: Dict[str, Any]) -> bool:
        """发送飞书通知"""
        if not config.get("webhook_url"):
            logging.error("❌ 飞书Webhook URL未配置")
            return False

        # 飞书支持两种消息格式：text和rich_text
        msg_type = config.get("msg_type", "text")
        
        if msg_type == "rich_text":
            # 富文本格式
            data = {
                "msg_type": "post",
                "content": {
                    "post": {
                        "zh_cn": {
                            "title": "微信读书自动阅读报告",
                            "content": [
                                [
                                    {
                                        "tag": "text",
                                        "text": message
                                    }
                                ]
                            ]
                        }
                    }
                }
            }
        else:
            # 纯文本格式
            data = {
                "msg_type": "text",
                "content": {
                    "text": f"微信读书自动阅读报告\n\n{message}"
                }
            }

        return self._send_http_notification(config["webhook_url"], data, "飞书")

    def _send_wework(self, message: str, config: Dict[str, Any]) -> bool:
        """发送企业微信通知"""
        if not config.get("webhook_url"):
            logging.error("❌ 企业微信Webhook URL未配置")
            return False

        # 企业微信支持text、markdown、news等格式
        msg_type = config.get("msg_type", "text")
        
        if msg_type == "markdown":
            # Markdown格式
            data = {
                "msgtype": "markdown",
                "markdown": {
                    "content": f"## 微信读书自动阅读报告\n\n{message}"
                }
            }
        elif msg_type == "news":
            # 图文消息格式
            data = {
                "msgtype": "news",
                "news": {
                    "articles": [
                        {
                            "title": "微信读书自动阅读报告",
                            "description": message[:200] + "..." if len(message) > 200 else message,
                            "url": "https://weread.qq.com"
                        }
                    ]
                }
            }
        else:
            # 纯文本格式
            data = {
                "msgtype": "text",
                "text": {
                    "content": f"微信读书自动阅读报告\n\n{message}"
                }
            }

        return self._send_http_notification(config["webhook_url"], data, "企业微信")

    def _send_dingtalk(self, message: str, config: Dict[str, Any]) -> bool:
        """发送钉钉通知"""
        if not config.get("webhook_url"):
            logging.error("❌ 钉钉Webhook URL未配置")
            return False

        # 钉钉支持text、markdown、link等格式
        msg_type = config.get("msg_type", "text")
        
        if msg_type == "markdown":
            # Markdown格式
            data = {
                "msgtype": "markdown",
                "markdown": {
                    "title": "微信读书自动阅读报告",
                    "text": f"## 微信读书自动阅读报告\n\n{message}"
                }
            }
        elif msg_type == "link":
            # 链接消息格式
            data = {
                "msgtype": "link",
                "link": {
                    "text": message[:200] + "..." if len(message) > 200 else message,
                    "title": "微信读书自动阅读报告",
                    "messageUrl": "https://weread.qq.com"
                }
            }
        else:
            # 纯文本格式
            data = {
                "msgtype": "text",
                "text": {
                    "content": f"微信读书自动阅读报告\n\n{message}"
                }
            }

        return self._send_http_notification(config["webhook_url"], data, "钉钉")

    def _send_gotify(self, message: str, config: Dict[str, Any]) -> bool:
        """发送Gotify通知"""
        if not config.get("server") or not config.get("token"):
            logging.error("❌ Gotify服务器地址或令牌未配置")
            return False

        # 构建Gotify API URL
        server = config["server"].rstrip("/")
        url = f"{server}/message"
        
        # 准备请求数据
        data = {
            "message": message,
            "priority": config.get("priority", 5),  # 默认优先级为5
            "title": config.get("title", "WeRead Bot 通知")
        }

        # 准备请求头
        headers = {
            "Content-Type": "application/json",
            "X-Gotify-Key": config["token"]
        }

        return self._send_http_notification(url, data, "Gotify", headers=headers)

    def _send_serverchan3(self, message: str, config: Dict[str, Any]) -> bool:
        """发送Server酱³通知"""
        if not config.get("uid") or not config.get("sendkey"):
            logging.error("❌ Server酱³ UID或SendKey未配置")
            return False

        # 构建Server酱³ API URL
        uid = config["uid"]
        sendkey = config["sendkey"]
        url = f"https://{uid}.push.ft07.com/send/{sendkey}.send"

        # 准备请求数据
        data = {
            "text": "WeRead Bot 通知",
            "desp": message
        }

        # 添加可选参数
        if config.get("tags"):
            data["tags"] = config["tags"]
        if config.get("short"):
            data["short"] = config["short"]

        return self._send_http_notification(url, data, "Server酱³")

    def _send_pushdeer(self, message: str, config: Dict[str, Any]) -> bool:
        """发送PushDeer通知"""
        if not config.get("pushkey"):
            logging.error("❌ PushDeer PushKey未配置")
            return False

        url = "https://api2.pushdeer.com/message/push"

        # 准备请求数据
        data = {
            "pushkey": config["pushkey"],
            "text": "WeRead Bot 通知",
            "desp": message,
            "type": config.get("type", "markdown")
        }

        return self._send_http_notification(url, data, "PushDeer")


class WeReadApplication:
    """微信读书应用程序管理器"""

    _instance = None
    _current_session_managers: Set["WeReadSessionManager"] = set()
    _daily_session_count = 0
    _last_session_date = None
    _last_run_summary: Dict[str, Any] = {}

    def __init__(self, config: WeReadConfig, execution_type: str = "normal"):
        self.config = config
        self.execution_type = execution_type
        self.shutdown_signal = None
        self._shutdown_event = asyncio.Event()
        WeReadApplication._instance = self

        # 设置信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    @classmethod
    def get_instance(cls):
        """获取应用程序实例"""
        return cls._instance

    @classmethod
    def reset_run_summary(cls):
        """重置最近一次运行摘要"""
        cls._last_run_summary = {}

    @classmethod
    def set_run_summary(cls, summary: Dict[str, Any]):
        """记录最近一次运行摘要"""
        cls._last_run_summary = summary

    @classmethod
    def get_run_summary(cls) -> Dict[str, Any]:
        """获取最近一次运行摘要"""
        return cls._last_run_summary.copy()

    def _signal_handler(self, signum, frame):
        """信号处理器"""
        logging.info(f"📡 收到信号 {signum}，准备优雅关闭...")
        self.shutdown_signal = signum
        self._shutdown_event.set()

    def is_shutdown_requested(self) -> bool:
        """返回当前应用实例是否收到关闭请求。"""
        return self._shutdown_event.is_set()

    async def run(self) -> RunResult:
        """根据配置的启动模式运行应用程序"""
        startup_mode = StartupMode(self.config.startup_mode.lower())

        if startup_mode == StartupMode.IMMEDIATE:
            return await self._run_immediate_mode()
        elif startup_mode == StartupMode.SCHEDULED:
            return await self._run_scheduled_mode()
        elif startup_mode == StartupMode.DAEMON:
            return await self._run_daemon_mode()
        else:
            raise ValueError(f"未知的启动模式: {self.config.startup_mode}")

    async def _run_immediate_mode(self) -> RunResult:
        """立即执行模式"""
        logging.info("🚀 启动模式: 立即执行")
        return await self.run_single_session()

    async def _run_scheduled_mode(self) -> RunResult:
        """定时执行模式"""
        logging.info("🚀 启动模式: 定时执行")

        if croniter is None:
            raise RuntimeError("缺少依赖 croniter，无法执行定时模式")

        if not self.config.schedule.enabled:
            raise ConfigError("schedule.enabled: scheduled 模式下必须为 true")

        timezone_name = self.config.schedule.timezone or "Asia/Shanghai"
        try:
            tz = ZoneInfo(timezone_name)
        except Exception:
            raise ConfigError(
                f"schedule.timezone: 无效时区，当前值={timezone_name!r}"
            )

        try:
            cron_iter = croniter(
                self.config.schedule.cron_expression,
                datetime.now(tz)
            )
        except Exception as e:
            raise ConfigError(
                "schedule.cron_expression: 无效 cron 表达式，"
                f"当前值={self.config.schedule.cron_expression!r}"
            ) from e

        logging.info(
            f"⏰ 定时任务已启动 (时区 {timezone_name})，表达式: {self.config.schedule.cron_expression}"
        )

        last_result = RunResult(
            final_status="cancelled", user_count=0, cancelled_users=0
        )
        while not self.is_shutdown_requested():
            next_run = cron_iter.get_next(datetime)
            if next_run.tzinfo is None:
                next_run = next_run.replace(tzinfo=tz)
            now = datetime.now(tz)
            wait_seconds = (next_run - now).total_seconds()

            if wait_seconds <= 0:
                continue

            logging.info(
                f"🗓️ 下一次执行时间: {next_run.astimezone(tz).strftime('%Y-%m-%d %H:%M:%S %Z')}"
            )

            while wait_seconds > 0 and not self.is_shutdown_requested():
                await interruptible_sleep(
                    min(wait_seconds, 1),
                    self.is_shutdown_requested,
                )
                now = datetime.now(tz)
                wait_seconds = (next_run - now).total_seconds()

            if self.is_shutdown_requested():
                break

            try:
                last_result = await self.run_single_session()
            except Exception as exc:
                last_result = self._record_persistent_runtime_failure(exc)
            if last_result.final_status != "success":
                logging.warning("本次失败，常驻进程继续等待下一次执行")

        logging.info("👋 定时任务已停止")
        return last_result

    async def _run_daemon_mode(self) -> RunResult:
        """守护进程模式"""
        logging.info("🚀 启动模式: 守护进程")

        if not self.config.daemon.enabled:
            raise ConfigError("daemon.enabled: daemon 模式下必须为 true")

        last_result = RunResult(
            final_status="cancelled", user_count=0, cancelled_users=0
        )
        while not self.is_shutdown_requested():
            # 检查每日会话限制
            current_date = datetime.now().date()
            if WeReadApplication._last_session_date != current_date:
                WeReadApplication._daily_session_count = 0
                WeReadApplication._last_session_date = current_date

            if (WeReadApplication._daily_session_count >=
                    self.config.daemon.max_daily_sessions):
                logging.info(
                    f"📊 已达到每日最大会话数限制: "
                    f"{self.config.daemon.max_daily_sessions}"
                )
                # 等待到第二天
                await self._wait_until_next_day()
                continue

            try:
                last_result = await self.run_single_session()
            except Exception as exc:
                last_result = self._record_persistent_runtime_failure(exc)
            finally:
                WeReadApplication._daily_session_count += 1

            if last_result.final_status == "cancelled":
                break
            if last_result.final_status != "success":
                logging.warning("本次失败，常驻进程继续")

            if not self.is_shutdown_requested():
                interval_minutes = RandomHelper.get_random_from_range(
                    self.config.daemon.session_interval
                )
                logging.info(
                    f"😴 守护进程等待 {interval_minutes:g} "
                    "分钟后执行下一次会话..."
                )
                await interruptible_sleep(
                    interval_minutes * 60,
                    self.is_shutdown_requested,
                )

        logging.info("👋 守护进程已停止")
        return last_result

    def _record_persistent_runtime_failure(
        self, exc: Exception
    ) -> RunResult:
        """记录常驻模式中未转换为 RunResult 的异常。"""
        category = classify_runtime_error(exc)
        user_count = len(self.config.users) if self.config.users else 1
        result = RunResult(
            final_status="failed",
            user_count=user_count,
            failed_users=0,
            failure_categories={category.value: 1},
            continue_on_failure=True,
        )
        logging.error(format_error_message("❌ 常驻会话执行失败", exc))
        persist_run_history(
            self.config,
            self.execution_type,
            run_summary=result.to_summary_dict(),
            runtime_error=exc,
            error_category=category,
        )
        return result

    async def _wait_until_next_day(self):
        """等待到第二天"""
        now = datetime.now()
        tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow += timedelta(days=1)
        wait_seconds = (tomorrow - now).total_seconds()

        logging.info(f"⏰ 等待到明天 00:00，剩余 {wait_seconds/3600:.1f} 小时")

        await interruptible_sleep(
            wait_seconds,
            self.is_shutdown_requested,
        )

    @classmethod
    async def run_single_session(cls) -> RunResult:
        """执行单次阅读会话"""
        instance = cls.get_instance()
        if not instance:
            raise RuntimeError("应用程序实例未初始化")

        cls.reset_run_summary()

        # 检查是否配置了多用户模式
        if instance.config.users:
            result = await cls._run_multi_user_sessions(instance)
        else:
            result = await cls._run_single_user_session(instance)
        cls.set_run_summary(result.to_summary_dict())
        persist_run_history(
            instance.config,
            instance.execution_type,
            run_summary=result.to_summary_dict(),
        )
        return result

    @classmethod
    async def _run_single_user_session(cls, instance) -> RunResult:
        """执行单用户会话"""
        session_manager = None
        user_token = CURRENT_USER.set("default")
        session_token = CURRENT_SESSION_ID.set(uuid.uuid4().hex[:10])
        try:
            # 创建会话管理器
            session_manager = WeReadSessionManager(
                instance.config,
                is_cancelled=instance.is_shutdown_requested,
            )
            WeReadApplication._current_session_managers.add(session_manager)

            # 执行阅读会话
            session_result = await session_manager.start_reading_session()

            logging.info("📊 会话统计:")
            logging.info(session_result.stats.get_statistics_summary())
            return RunResult.from_session_results([session_result])

        except Exception as e:
            error_msg = f"❌ 阅读会话执行失败: {e}"
            logging.error(error_msg)
            result = SessionResult(
                SessionStatus.FAILED,
                ReadingSession(user_name="default"),
                classify_runtime_error(e),
                str(e),
            )

            # 发送错误通知
            try:
                notification_service = NotificationService(
                    instance.config.notification
                )
                await notification_service.send_notification_async(
                    error_msg,
                    event=NotificationEvent.SESSION_FAILURE
                )
            except Exception:
                pass
            return RunResult.from_session_results([result])
        finally:
            if session_manager is not None:
                WeReadApplication._current_session_managers.discard(
                    session_manager
                )
            CURRENT_SESSION_ID.reset(session_token)
            CURRENT_USER.reset(user_token)

    @classmethod
    async def _run_multi_user_sessions(cls, instance) -> RunResult:
        """执行多用户会话"""
        user_count = len(instance.config.users)
        logging.info(f"🎭 检测到多用户配置，共 {user_count} 个用户")

        concurrency = max(1, instance.config.max_concurrent_users)
        if concurrency > user_count:
            concurrency = user_count
        logging.info(f"⚙️  最大并发用户数: {concurrency}")

        semaphore = asyncio.Semaphore(concurrency)
        tasks = []

        async def run_for_user(user_config: UserConfig):
            if instance.is_shutdown_requested():
                logging.info("📡 收到关闭信号，跳过后续用户")
                return user_config.name, SessionResult(
                    SessionStatus.CANCELLED,
                    ReadingSession(user_name=user_config.name),
                    message="收到关闭信号，未启动用户会话",
                )

            async with semaphore:
                if instance.is_shutdown_requested():
                    return user_config.name, SessionResult(
                        SessionStatus.CANCELLED,
                        ReadingSession(user_name=user_config.name),
                        message="收到关闭信号，取消用户会话",
                    )

                user_token = CURRENT_USER.set(user_config.name)
                session_token = CURRENT_SESSION_ID.set(uuid.uuid4().hex[:10])
                session_manager = None

                try:
                    logging.info(f"👤 开始执行用户 {user_config.name} 的阅读会话")
                    session_manager = WeReadSessionManager(
                        instance.config,
                        user_config,
                        is_cancelled=instance.is_shutdown_requested,
                    )
                    WeReadApplication._current_session_managers.add(session_manager)
                    session_result = await session_manager.start_reading_session()
                    logging.info(f"📊 用户 {user_config.name} 会话统计:")
                    logging.info(session_result.stats.get_statistics_summary())
                    return user_config.name, session_result
                except Exception as e:
                    error_msg = (
                        f"❌ 用户 {user_config.name} 阅读会话执行失败: {e}"
                    )
                    logging.error(error_msg)
                    try:
                        notification_service = NotificationService(
                            instance.config.notification
                        )
                        await notification_service.send_notification_async(
                            error_msg,
                            event=NotificationEvent.SESSION_FAILURE
                        )
                    except Exception:
                        pass
                    return user_config.name, SessionResult(
                        SessionStatus.FAILED,
                        ReadingSession(user_name=user_config.name),
                        classify_runtime_error(e),
                        str(e),
                    )
                finally:
                    if session_manager is not None:
                        WeReadApplication._current_session_managers.discard(
                            session_manager
                        )
                    CURRENT_SESSION_ID.reset(session_token)
                    CURRENT_USER.reset(user_token)

        for user_config in instance.config.users:
            tasks.append(asyncio.create_task(run_for_user(user_config)))

        session_results: List[SessionResult] = []
        skipped_users = 0

        for task in asyncio.as_completed(tasks):
            user_name, session_result = await task
            if session_result is None:
                skipped_users += 1
                logging.info(f"⏭️ 用户 {user_name} 已跳过: 收到关闭信号")
            else:
                session_results.append(session_result)

        run_result = RunResult.from_session_results(
            session_results,
            skipped_users=skipped_users,
            continue_on_failure=True,
        )
        await cls._generate_multi_user_summary(instance, run_result)
        return run_result

    @classmethod
    async def _generate_multi_user_summary(
        cls,
        instance,
        run_result: RunResult,
    ):
        """生成多用户会话总结"""
        summary = f"""🎭 多用户阅读会话总结

👥 用户统计:
  📊 总用户数: {run_result.user_count}
  ✅ 成功用户: {run_result.successful_users}
  ❌ 失败用户: {run_result.failed_users}
  📡 取消用户: {run_result.cancelled_users}
  ⏭️ 跳过用户: {run_result.skipped_users}
  🧭 失败后继续: 是

📖 阅读统计:
  ⏱️ 总阅读时长: {run_result.total_duration_seconds // 60}分{run_result.total_duration_seconds % 60}秒
  ✅ 成功请求: {run_result.total_reads}次
  ❌ 失败请求: {run_result.total_failed_reads}次
  🧩 失败分类: {', '.join(f'{category}={count}' for category, count in run_result.failure_categories.items())
                   if run_result.failure_categories else '无'}

最终状态: {run_result.final_status}"""

        logging.info("📊 多用户会话总结:")
        logging.info(summary)
        # 发送总结通知
        if (instance.config.notification.enabled and
                instance.config.notification.include_statistics):
            try:
                notification_service = NotificationService(
                    instance.config.notification
                )
                await notification_service.send_notification_async(
                    summary,
                    event=NotificationEvent.MULTI_USER_SUMMARY
                )
            except Exception as e:
                logging.error(f"❌ 多用户总结通知发送失败: {e}")


class WeReadSessionManager:
    """微信读书会话管理器"""

    # 微信读书API常量
    KEY = "3c5c8717f3daf09iop3423zafeqoi"
    READ_URL = "https://weread.qq.com/web/book/read"
    RENEW_URL = "https://weread.qq.com/web/login/renewal"
    FIX_SYNCKEY_URL = "https://weread.qq.com/web/book/chapterInfos"

    # 默认请求数据
    DEFAULT_DATA = {
        "appId": "app_id",  # 应用的唯一标识符
        "b": "book_id",  # 书籍或章节的唯一标识符
        "c": "chapter_id",  # 内容的唯一标识符，可能是页面或具体段落
        "ci": "chapter_index",  # 章节或部分的索引
        "co": "page_number",  # 内容的具体位置或页码
        "sm": "content",  # 当前阅读的内容描述或摘要
        "pr": "page_number",  # 页码或段落索引
        "rt": "reading_time",  # 阅读时长或阅读进度
        "ts": time.time() * 1000,  # 时间戳，毫秒级
        "rn": "random_number",  # 随机数或请求编号
        "sg": "sha256_hash",  # 安全签名
        "ct": time.time(),  # 时间戳，秒级
        "ps": "user_id",  # 用户标识符或会话标识符
        "pc": "device_id",  # 设备标识符或客户端标识符
        "s": "36cc0815"  # 校验和或哈希值
    }

    def __init__(
        self,
        config: WeReadConfig,
        user_config: UserConfig = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ):
        self.config = config
        self.user_config = user_config
        self.user_name = user_config.name if user_config else "default"
        self._is_cancelled = is_cancelled or (lambda: False)

        # 应用用户特定的阅读配置覆盖
        self.effective_reading_config = self._apply_reading_overrides(
            config.reading, user_config
        )

        self.http_client = HttpClient(config.network)
        self.notification_service = NotificationService(config.notification)
        self.behavior_simulator = HumanBehaviorSimulator(
            config.human_simulation
        )
        self.reading_manager = SmartReadingManager(
            self.effective_reading_config
        )
        self.session_stats = ReadingSession(user_name=self.user_name)

        # 动态创建 cookie 数据，优先使用用户级 ql 配置
        self.cookie_data = {
            "rq": "%2Fweb%2Fbook%2Fread",
            "ql": self._resolve_cookie_refresh_ql(),
        }

        self.headers = {}
        self.cookies = {}
        self.data = self.DEFAULT_DATA.copy()
        self.session_user_agent = None  # 会话级别的User-Agent
        self._last_read_error_category = None

        self._load_curl_config()
        self._initialize_session_user_agent()

    def _resolve_cookie_refresh_ql(self) -> bool:
        """解析当前用户会话的 Cookie 刷新 ql 配置"""
        if (self.user_config
                and isinstance(self.user_config.cookie_refresh_ql, bool)):
            return self.user_config.cookie_refresh_ql
        return self.config.hack.cookie_refresh_ql

    def _apply_reading_overrides(
        self, base_config: ReadingConfig, user_config: UserConfig
    ) -> ReadingConfig:
        """应用用户特定的阅读配置覆盖"""
        if not user_config or not user_config.reading_overrides:
            return base_config

        # 创建基础配置的副本
        from dataclasses import replace
        effective_config = replace(base_config)

        # 应用覆盖配置
        overrides = user_config.reading_overrides
        if "mode" in overrides:
            effective_config.mode = overrides["mode"]
        if "target_duration" in overrides:
            effective_config.target_duration = overrides["target_duration"]
        if "reading_interval" in overrides:
            effective_config.reading_interval = overrides["reading_interval"]
        if "use_curl_data_first" in overrides:
            effective_config.use_curl_data_first = overrides[
                "use_curl_data_first"
            ]
        if "fallback_to_config" in overrides:
            effective_config.fallback_to_config = overrides[
                "fallback_to_config"
            ]

        logging.info(
            f"📋 用户 {user_config.name} 应用配置覆盖: "
            f"模式={effective_config.mode}, "
            f"时长={effective_config.target_duration}, "
            f"间隔={effective_config.reading_interval}"
        )

        return effective_config

    def _load_curl_config(self):
        """加载CURL配置"""
        curl_content = ""

        if self.user_config:
            curl_content = load_curl_source(
                self.user_config.file_path,
                self.user_config.content,
                f"curl_config.users.{self.user_name}",
            )
            if curl_content:
                logging.info(
                    "✅ 用户 %s 已加载独立 CURL 配置", self.user_name
                )

        if not curl_content:
            curl_content = load_curl_source(
                self.config.curl_file_path,
                self.config.curl_content,
                "curl_config",
            )
            if curl_content:
                logging.info("✅ 已加载全局 CURL 配置")

        # 解析CURL配置
        if curl_content:
            try:
                self.headers, self.cookies, curl_data = (
                    CurlParser.parse_curl_command(curl_content)
                )

                # 验证CURL配置的合法性
                is_valid, validation_errors = CurlParser.validate_curl_headers(
                    self.headers, self.cookies, curl_data, self.user_name
                )

                if not is_valid:
                    error_msg = (
                        f"❌ 用户 {self.user_name} CURL 配置验证失败:\n"
                        + "\n".join(f"  • {error}" for error in validation_errors)
                        + f"\n请检查您的CURL配置是否正确，并确保包含所有必需的认证信息。"
                    )
                    logging.error(error_msg)
                    raise ValueError(error_msg)

                # 如果从CURL中提取到请求数据，则使用它替换默认数据
                if curl_data:
                    self._apply_curl_payload(curl_data)
                else:
                    logging.info(
                        f"ℹ️ 用户 {self.user_name} CURL命令中未找到请求数据，"
                        f"使用默认数据"
                    )
                    self.reading_manager.set_curl_data("", "")

                logging.info(f"✅ 用户 {self.user_name} CURL配置解析成功")
            except Exception as e:
                logging.error(
                    format_error_message(
                        f"❌ 用户 {self.user_name} CURL配置解析失败", e
                    )
                )
                raise
        else:
            error_msg = f"❌ 用户 {self.user_name} 未找到有效的CURL配置"
            logging.error(error_msg)
            raise ValueError(
                f"用户 {self.user_name} 未找到有效的CURL配置，"
                f"请检查 WEREAD_CURL_BASH_FILE_PATH 或 WEREAD_CURL_STRING"
            )

    def _validate_and_log_user_identity(self):
        """验证并记录用户身份标识符"""
        ps_value = self.data.get('ps', 'N/A')
        pc_value = self.data.get('pc', 'N/A')
        app_id = self.data.get('appId', 'N/A')
        
        # 记录用户身份信息（用于调试）
        logging.info(
            f"🔍 用户 {self.user_name} 身份验证: "
            f"ps={_secret_marker(ps_value)}, pc={_secret_marker(pc_value)}, "
            f"appId={_secret_marker(app_id)}"
        )
        
        # 验证关键身份字段是否存在
        if ps_value == 'N/A' or pc_value == 'N/A':
            logging.warning(
                f"⚠️ 用户 {self.user_name} 缺少关键身份标识符: "
                f"ps={_secret_marker(ps_value)}, "
                f"pc={_secret_marker(pc_value)}"
            )
        
        # 保存用户特定的身份标识符，确保在整个会话期间保持不变
        self.user_ps = ps_value
        self.user_pc = pc_value
        self.user_app_id = app_id

    def _initialize_session_user_agent(self):
        """初始化会话级别的User-Agent"""
        if (self.config.human_simulation.enabled and
                self.config.human_simulation.rotate_user_agent):
            self.session_user_agent = UserAgentRotator.get_random_user_agent()
            logging.info(
                f"🔄 用户 {self.user_name} 会话User-Agent已设置: "
                f"{self.session_user_agent[:50]}..."
            )
        else:
            # 如果没有启用轮换，使用CURL中的User-Agent或保持空
            self.session_user_agent = self.headers.get('user-agent')

    def _build_protocol_warning(self, reason: str,
                                detail: str = "") -> str:
        """生成统一的协议兼容提示"""
        message = f"⚠️ 协议兼容提示 ({self.user_name}): {reason}"
        if detail:
            message += f" | {detail}"
        return message

    def _build_protocol_error(self, reason: str,
                              detail: str = "") -> str:
        """生成统一的协议兼容错误"""
        message = f"协议兼容失败 ({self.user_name}): {reason}"
        if detail:
            message += f" | {detail}"
        return message

    def _apply_protocol_reading_position(
        self,
        book_id: Optional[str],
        chapter_id: Optional[str],
        chapter_ci: Optional[int] = None,
    ):
        """集中处理阅读起点与章节索引兼容逻辑"""
        initialized = self.reading_manager.set_curl_data(
            book_id or "", chapter_id or ""
        )
        if not initialized:
            raise ValueError(
                self._build_protocol_error(
                    "阅读位置初始化失败",
                    "CURL 位置不可用且配置回退失败",
                )
            )
        if (self.reading_manager.current_chapter_ci is None
                and chapter_ci is not None):
            self.reading_manager.current_chapter_ci = chapter_ci
            logging.info(f"📋 使用协议中的章节索引: ci={chapter_ci}")

    def _apply_curl_payload(self, curl_data: Dict[str, Any]):
        """应用CURL提取出的协议载荷"""
        reusable_fields = {
            "appId", "ps", "pc", "b", "c", "ci", "co", "sm", "pr", "rt"
        }
        self.data.update({
            key: value for key, value in curl_data.items()
            if key in reusable_fields
        })
        self._validate_and_log_user_identity()

        missing_fields = [field for field in ("b", "c") if not curl_data.get(field)]

        if missing_fields:
            logging.warning(
                self._build_protocol_warning(
                    "CURL请求数据缺少必需字段",
                    f"缺失字段: {', '.join(missing_fields)}，将回退到配置阅读位置",
                )
            )
            if not self.reading_manager.set_curl_data("", ""):
                raise ValueError(
                    self._build_protocol_error(
                        "CURL 缺少阅读位置且配置回退失败",
                        f"缺失字段: {', '.join(missing_fields)}",
                    )
                )
            return

        logging.info(
            f"✅ 用户 {self.user_name} 已使用CURL中的请求数据，"
            f"包含字段: {list(curl_data.keys())}"
        )
        self._apply_protocol_reading_position(
            curl_data.get('b'),
            curl_data.get('c'),
            curl_data.get('ci'),
        )

    def _extract_wr_skey_from_response(
        self, response: httpx.Response
    ) -> Optional[str]:
        """从刷新响应中提取 wr_skey，集中处理兼容分支"""
        new_skey = response.cookies.get("wr_skey")
        if new_skey:
            return new_skey

        set_cookie = response.headers.get("set-cookie", "")
        for cookie in set_cookie.split(','):
            if "wr_skey" not in cookie:
                continue
            parts = cookie.split(';')[0]
            if '=' in parts:
                return parts.split('=', 1)[1].strip()
        return None

    async def _handle_protocol_response(
        self, response_data: Dict[str, Any], response_time: float
    ) -> Tuple[bool, float]:
        """集中处理阅读接口响应中的协议兼容分支"""
        if is_successful_read_response(response_data):
            logging.debug(
                "阅读请求成功，响应字段: %s",
                ", ".join(sorted(response_data.keys())),
            )
            return True, response_time

        if response_data.get('succ'):
            logging.warning(
                self._build_protocol_warning(
                    "阅读响应缺少 synckey",
                    f"book={self.data.get('b')}, chapter={self.data.get('c')}",
                )
            )
            await self._fix_no_synckey()
            return False, response_time

        logging.warning(
            self._build_protocol_warning(
                "阅读响应未返回 succ，可能是 Cookie 失效或响应结构变更",
                f"响应字段: {', '.join(sorted(response_data.keys())) or '无'}",
            )
        )
        logging.info(
            f"🔍 失败的请求数据: book_id={self.data.get('b')}, "
            f"chapter_id={self.data.get('c')}"
        )
        await self._refresh_cookie()
        return False, response_time

    async def start_reading_session(self) -> SessionResult:
        """运行会话并返回不会与统计对象混淆的状态结果。"""
        user_info = f" (用户: {self.user_name})" if self.user_config else ""
        is_cancelled = self._is_cancelled
        monotonic = getattr(self, "_monotonic", time.monotonic)
        result: Optional[SessionResult] = None
        started_monotonic: Optional[float] = None

        def refresh_duration() -> None:
            if started_monotonic is None:
                return
            elapsed = max(0.0, monotonic() - started_monotonic)
            self.session_stats.actual_duration_seconds = int(elapsed)

        try:
            logging.info(f"🚀 微信读书阅读机器人启动{user_info}")
            logging.info(
                f"📋 配置信息: 阅读模式 {self.effective_reading_config.mode}, "
                f"目标时长 {self.effective_reading_config.target_duration} 分钟"
            )

            startup_delay = RandomHelper.get_random_int_from_range(
                self.config.startup_delay
            )
            logging.info(f"⏳ 启动延迟 {startup_delay} 秒...")
            if not await interruptible_sleep(startup_delay, is_cancelled):
                result = SessionResult(
                    SessionStatus.CANCELLED, self.session_stats,
                    message="启动延迟期间收到关闭信号",
                )
                return result

            target_minutes = RandomHelper.get_random_from_range(
                self.effective_reading_config.target_duration
            )
            self.session_stats.start_time = datetime.now()
            self.session_stats.target_duration_minutes = target_minutes
            started_monotonic = monotonic()
            deadline = started_monotonic + target_minutes * 60

            logging.info(f"🎯 本次目标阅读时长: {target_minutes} 分钟")

            if is_cancelled():
                result = SessionResult(
                    SessionStatus.CANCELLED, self.session_stats,
                    message="收到关闭信号",
                )
                return result

            cookie_refreshed = await self._refresh_cookie()
            refresh_duration()
            if is_cancelled():
                result = SessionResult(
                    SessionStatus.CANCELLED,
                    self.session_stats,
                    message="Cookie 刷新期间收到关闭信号",
                )
                return result
            if not cookie_refreshed:
                result = SessionResult(
                    SessionStatus.FAILED,
                    self.session_stats,
                    RuntimeErrorCategory.AUTH,
                    "Cookie 刷新失败",
                )
                await self._notify_session_result(result)
                return result

            last_time = int(time.time()) - 30
            consecutive_failures = 0
            last_failure_category: Optional[RuntimeErrorCategory] = None
            max_failures = self.effective_reading_config.max_consecutive_failures

            while monotonic() < deadline:
                refresh_duration()
                if is_cancelled():
                    result = SessionResult(
                        SessionStatus.CANCELLED,
                        self.session_stats,
                        message="收到关闭信号",
                    )
                    break

                if self.behavior_simulator.should_take_break():
                    break_duration = self.behavior_simulator.get_break_duration()
                    logging.info(f"☕ 休息一下... {break_duration} 秒")
                    completed = await interruptible_sleep(
                        break_duration, is_cancelled
                    )
                    refresh_duration()
                    if not completed:
                        result = SessionResult(
                            SessionStatus.CANCELLED,
                            self.session_stats,
                            message="休息期间收到关闭信号",
                        )
                        break
                    self.session_stats.breaks_taken += 1
                    self.session_stats.total_break_time += break_duration
                    continue

                try:
                    success, response_time = await self._simulate_reading_request(
                        last_time
                    )
                    refresh_duration()
                    self.session_stats.response_times.append(response_time)
                    if success:
                        self.session_stats.successful_reads += 1
                        consecutive_failures = 0
                        last_failure_category = None
                        last_time = int(time.time())
                        logging.info(
                            "✅ 阅读成功，进度: %s分钟 / %.2f分钟",
                            self.session_stats.actual_duration_seconds // 60,
                            target_minutes,
                        )
                    else:
                        self.session_stats.failed_reads += 1
                        consecutive_failures += 1
                        last_failure_category = getattr(
                            self,
                            "_last_read_error_category",
                            None,
                        ) or RuntimeErrorCategory.PROTOCOL
                except Exception as exc:
                    logging.error("❌ 阅读请求异常: %s", exc)
                    self.session_stats.failed_reads += 1
                    consecutive_failures += 1
                    last_failure_category = classify_runtime_error(exc)

                if is_cancelled():
                    result = SessionResult(
                        SessionStatus.CANCELLED,
                        self.session_stats,
                        message="阅读请求期间收到关闭信号",
                    )
                    break

                if consecutive_failures >= max_failures:
                    result = SessionResult(
                        SessionStatus.FAILED,
                        self.session_stats,
                        last_failure_category or RuntimeErrorCategory.PROTOCOL,
                        f"连续阅读失败达到上限 {max_failures} 次",
                    )
                    break

                if monotonic() >= deadline:
                    break

                interval = self.behavior_simulator.get_reading_interval(
                    self.effective_reading_config.reading_interval
                )
                if not await interruptible_sleep(interval, is_cancelled):
                    result = SessionResult(
                        SessionStatus.CANCELLED,
                        self.session_stats,
                        message="等待期间收到关闭信号",
                    )
                    break
                refresh_duration()

            refresh_duration()
            self.session_stats.end_time = datetime.now()
            if result is None:
                if self.session_stats.successful_reads > 0:
                    result = SessionResult(
                        SessionStatus.SUCCESS, self.session_stats
                    )
                else:
                    result = SessionResult(
                        SessionStatus.FAILED,
                        self.session_stats,
                        RuntimeErrorCategory.PROTOCOL,
                        "会话结束但没有成功阅读请求",
                    )

            await self._notify_session_result(result)

            return result
        except Exception as exc:
            refresh_duration()
            self.session_stats.end_time = datetime.now()
            result = SessionResult(
                SessionStatus.FAILED,
                self.session_stats,
                classify_runtime_error(exc),
                str(exc),
            )
            await self._notify_session_result(result)
            return result
        finally:
            refresh_duration()
            if self.session_stats.end_time is None:
                self.session_stats.end_time = datetime.now()
            await self.http_client.close()

    async def _notify_session_result(self, result: SessionResult) -> None:
        """按最终状态发送会话通知，通知失败不改变会话结果。"""
        if not (self.config.notification.enabled and
                self.config.notification.include_statistics):
            return
        try:
            if result.status == SessionStatus.SUCCESS:
                await self.notification_service.send_notification_async(
                    self.session_stats.get_statistics_summary(),
                    event=NotificationEvent.SESSION_SUCCESS,
                )
            elif result.status == SessionStatus.FAILED:
                await self.notification_service.send_notification_async(
                    result.message or "阅读会话失败",
                    event=NotificationEvent.SESSION_FAILURE,
                )
        except Exception as exc:
            logging.warning("会话通知发送失败: %s", exc)

    def _prepare_read_payload(self, last_time: int) -> Tuple[str, str]:
        """准备单次阅读请求的协议载荷"""
        self.data.pop('s', None)

        book_id, chapter_id = self.reading_manager.get_next_reading_position()
        self.data['b'] = book_id
        self.data['c'] = chapter_id

        chapter_ci = self.reading_manager.current_chapter_ci
        if chapter_ci is not None:
            self.data['ci'] = chapter_ci
            logging.debug(
                f"🔢 设置章节索引: ci={chapter_ci} (章节: {chapter_id})"
            )
        else:
            self.data.pop('ci', None)

        self._apply_user_identity_to_payload(book_id, chapter_id)

        current_time = int(time.time())
        self.data['ct'] = current_time
        self.data['rt'] = current_time - last_time
        self.data['ts'] = int(current_time * 1000) + random.randint(0, 1000)
        self.data['rn'] = random.randint(0, 1000)
        signature_string = (
            f"{self.data['ts']}{self.data['rn']}{self.KEY}"
        )
        self.data['sg'] = hashlib.sha256(
            signature_string.encode()
        ).hexdigest()
        self.data['s'] = self._calculate_hash(self._encode_data(self.data))
        return book_id, chapter_id

    def _record_reading_target(self, book_id: str, chapter_id: str):
        """记录本次阅读目标到会话统计"""
        if book_id not in self.session_stats.books_read:
            self.session_stats.books_read.append(book_id)
            book_name = self.reading_manager.book_names_map.get(
                book_id, f"未知书籍({book_id[:10]}...)"
            )
            if book_name not in self.session_stats.books_read_names:
                self.session_stats.books_read_names.append(book_name)
        if chapter_id not in self.session_stats.chapters_read:
            self.session_stats.chapters_read.append(chapter_id)

    def _apply_user_identity_to_payload(self, book_id: str, chapter_id: str):
        """将会话内固定的身份字段写回请求载荷"""
        if hasattr(self, 'user_ps') and hasattr(self, 'user_pc'):
            self.data['ps'] = self.user_ps
            self.data['pc'] = self.user_pc
            if hasattr(self, 'user_app_id'):
                self.data['appId'] = self.user_app_id

            logging.debug(
                f"🔒 用户 {self.user_name} 身份确认: ps={_secret_marker(self.user_ps)}, "
                f"pc={_secret_marker(self.user_pc)}, book={book_id[:10]}..., "
                f"chapter={chapter_id[:10]}..."
            )

    async def _simulate_reading_request(self,
                                        last_time: int) -> Tuple[bool, float]:
        """模拟阅读请求"""
        book_id, chapter_id = self._prepare_read_payload(last_time)
        self._record_reading_target(book_id, chapter_id)

        # 使用会话级别的User-Agent（如果启用轮换）
        if (self.config.human_simulation.enabled and
                self.config.human_simulation.rotate_user_agent and
                self.session_user_agent):
            self.headers['user-agent'] = self.session_user_agent

        try:
            # 发送请求
            response_data, response_time = await self.http_client.post_json(
                self.READ_URL, self.data, self.headers, self.cookies
            )

            logging.debug(
                "阅读响应字段: %s",
                ", ".join(sorted(response_data.keys())),
            )
            result = await self._handle_protocol_response(
                response_data, response_time
            )
            self._last_read_error_category = (
                None if result[0] else RuntimeErrorCategory.PROTOCOL
            )
            return result

        except Exception as e:
            self._last_read_error_category = classify_runtime_error(e)
            logging.error(
                format_error_message(
                    self._build_protocol_error(
                        "阅读请求发送失败",
                        f"book={self.data.get('b')}, chapter={self.data.get('c')}",
                    ),
                    e,
                )
            )
            return False, 0.0

    async def _refresh_cookie(self) -> bool:
        """刷新cookie"""
        logging.info("🍪 刷新cookie...")

        try:
            response, _ = await self.http_client.post_raw(
                self.RENEW_URL,
                headers=self.headers,
                cookies=self.cookies,
                json_data=self.cookie_data
            )

            new_skey = self._extract_wr_skey_from_response(response)

            if not new_skey:
                logging.error(
                    self._build_protocol_error(
                        "Cookie 刷新失败",
                        "响应中未找到 wr_skey，可能是 Cookie 已失效或接口返回结构变更",
                    )
                )
                return False

            self.cookies['wr_skey'] = new_skey
            logging.info(
                "✅ Cookie刷新成功，新密钥: %s", _secret_marker(new_skey)
            )
            return True

        except Exception as e:
            logging.error(
                format_error_message(
                    self._build_protocol_error(
                        "Cookie 刷新请求失败",
                        "请检查网络状态、认证信息或 renewal 接口兼容性",
                    ),
                    e,
                )
            )

        return False

    async def _fix_no_synckey(self):
        """修复synckey问题

        代码引用: https://github.com/findmover/wxread
        """
        try:
            await self.http_client.post_raw(
                self.FIX_SYNCKEY_URL,
                headers=self.headers,
                cookies=self.cookies,
                json_data={"bookIds": [self.data.get("b")]}
            )
        except Exception as e:
            logging.error(
                format_error_message(
                    self._build_protocol_error(
                        "synckey 修复失败",
                        "请检查 chapterInfos 接口、Cookie 和章节信息是否仍然可用",
                    ),
                    e,
                )
            )

    @staticmethod
    def _encode_data(data: dict) -> str:
        """数据编码

        代码引用: https://github.com/findmover/wxread
        """
        encoded_pairs = [
            f"{k}={urllib.parse.quote(str(data[k]), safe='')}"
            for k in sorted(data.keys())
        ]
        return '&'.join(encoded_pairs)

    @staticmethod
    def _calculate_hash(input_string: str) -> str:
        """计算哈希值
        
        代码引用: https://github.com/findmover/wxread
        """
        _7032f5 = 0x15051505
        _cc1055 = _7032f5
        length = len(input_string)
        _19094e = length - 1

        while _19094e > 0:
            char_code = ord(input_string[_19094e])
            shift_amount = (length - _19094e) % 30
            _7032f5 = 0x7fffffff & (_7032f5 ^ char_code << shift_amount)

            prev_char_code = ord(input_string[_19094e - 1])
            prev_shift_amount = _19094e % 30
            _cc1055 = 0x7fffffff & (
                _cc1055 ^ prev_char_code << prev_shift_amount
            )
            _19094e -= 2

        return hex(_7032f5 + _cc1055)[2:].lower()


# ======================
# 执行历史持久化
# ======================


def load_run_history(history_file: Union[str, Path]) -> List[dict]:
    """加载执行历史，缺失或损坏时回退为空列表"""
    history_path = Path(history_file)
    if not history_path.exists():
        return []

    try:
        with open(history_path, "r", encoding="utf-8") as history_fp:
            history = json.load(history_fp)
    except json.JSONDecodeError as exc:
        logging.warning(f"⚠️ 执行历史文件已损坏，已回退为空历史: {exc}")
        return []
    except Exception as exc:
        logging.warning(f"⚠️ 执行历史文件读取失败，已回退为空历史: {exc}")
        return []

    if not isinstance(history, list):
        logging.warning("⚠️ 执行历史文件格式无效，已回退为空历史")
        return []

    return [entry for entry in history if isinstance(entry, dict)]


def build_run_history_record(
    config: WeReadConfig,
    execution_type: str,
    run_summary: Optional[Dict[str, Any]] = None,
    runtime_error: Exception = None,
    error_category: Optional[RuntimeErrorCategory] = None,
) -> Dict[str, Any]:
    """基于运行摘要构建标准化执行历史记录"""
    run_summary = run_summary or {}
    failure_categories = dict(run_summary.get("failure_categories") or {})
    effective_user_count = run_summary.get("user_count")
    if effective_user_count is None:
        effective_user_count = len(config.users) if config.users else 1

    record = {
        "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "execution_type": execution_type,
        "startup_mode": config.startup_mode,
        "final_status": run_summary.get(
            "final_status",
            "failed" if runtime_error else "unknown",
        ),
        "user_count": effective_user_count,
        "successful_users": run_summary.get("successful_users", 0),
        "failed_users": run_summary.get("failed_users", 0),
        "cancelled_users": run_summary.get("cancelled_users", 0),
        "skipped_users": run_summary.get("skipped_users", 0),
        "total_duration_seconds": run_summary.get("total_duration_seconds", 0),
        "total_reads": run_summary.get("total_reads", 0),
        "total_failed_reads": run_summary.get("total_failed_reads", 0),
        "failure_categories": failure_categories,
        "continue_on_failure": run_summary.get("continue_on_failure", False),
    }

    if runtime_error is not None:
        normalized_category = (
            error_category.value if isinstance(error_category, Enum)
            else (
                str(error_category) if error_category
                else classify_runtime_error(runtime_error).value
            )
        )
        record["error_category"] = normalized_category
        record["error_message"] = redact_for_log(str(runtime_error))[:200]
        if not record["failure_categories"]:
            record["failure_categories"] = {normalized_category: 1}

    return record


def append_run_history_record(
    history_file: Union[str, Path],
    record: Dict[str, Any],
    max_entries: int = 50,
):
    """追加执行历史并裁剪，使用临时文件替换降低损坏概率"""
    history_path = Path(history_file)
    temp_path = None

    try:
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history = load_run_history(history_path)
        history.append(record)
        if max_entries > 0:
            history = history[-max_entries:]

        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=history_path.parent,
            prefix=f".{history_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_fp:
            temp_path = Path(temp_fp.name)
            json.dump(history, temp_fp, ensure_ascii=False, indent=2)
            temp_fp.write("\n")

        os.replace(temp_path, history_path)
    except Exception as exc:
        logging.warning(f"⚠️ 执行历史写入失败，已跳过持久化: {exc}")
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def persist_run_history(
    config: Optional[WeReadConfig],
    execution_type: str,
    run_summary: Optional[Dict[str, Any]] = None,
    runtime_error: Exception = None,
    error_category: Optional[RuntimeErrorCategory] = None,
):
    """统一处理真实执行历史的写入策略"""
    if config is None or execution_type != "normal":
        return

    if not config.history.enabled:
        return

    if runtime_error is not None and not config.history.persist_runtime_error:
        return

    if run_summary is None and runtime_error is None:
        return

    record = build_run_history_record(
        config=config,
        execution_type=execution_type,
        run_summary=run_summary,
        runtime_error=runtime_error,
        error_category=error_category,
    )
    append_run_history_record(
        config.history.file,
        record,
        max_entries=config.history.max_entries,
    )


def format_last_run_summary(last_record: Optional[Dict[str, Any]]) -> str:
    """将最近一次执行历史格式化为 CLI 可读摘要"""
    if not last_record:
        return "最近执行记录\n  暂无真实执行历史"

    status_label_map = {
        "success": "成功",
        "failed": "失败",
        "partial_success": "部分成功",
        "cancelled": "已取消",
        "skipped": "已跳过",
    }
    failure_categories = last_record.get("failure_categories") or {}
    failure_text = (
        ", ".join(
            f"{category}={count}"
            for category, count in failure_categories.items()
        )
        if failure_categories else "无"
    )

    return "\n".join([
        "最近执行记录",
        f"  记录时间: {last_record.get('recorded_at', '未知')}",
        f"  执行类型: {last_record.get('execution_type', 'unknown')}",
        f"  启动模式: {last_record.get('startup_mode', 'unknown')}",
        (
            "  最终状态: "
            + status_label_map.get(
                last_record.get("final_status", "unknown"),
                last_record.get("final_status", "unknown"),
            )
        ),
        f"  用户数量: {last_record.get('user_count', 0)}",
        f"  成功用户: {last_record.get('successful_users', 0)}",
        f"  失败用户: {last_record.get('failed_users', 0)}",
        f"  取消用户: {last_record.get('cancelled_users', 0)}",
        f"  跳过用户: {last_record.get('skipped_users', 0)}",
        f"  总阅读时长: {last_record.get('total_duration_seconds', 0)} 秒",
        f"  成功请求: {last_record.get('total_reads', 0)}",
        f"  失败请求: {last_record.get('total_failed_reads', 0)}",
        f"  失败分类: {failure_text}",
        (
            "  失败后继续: 是"
            if last_record.get("continue_on_failure", False)
            else "  失败后继续: 否"
        ),
    ])


# ======================
# CLI 与程序入口
# ======================


def build_runtime_summary(
    config: WeReadConfig,
    execution_mode: str,
    curl_validated: bool,
    run_summary: Dict[str, Any] = None,
    include_notification_details: bool = False,
    include_user_details: bool = False,
) -> str:
    """构建运行摘要"""
    status_label_map = {
        "success": "成功",
        "failed": "失败",
        "partial_success": "部分成功",
        "cancelled": "已取消",
        "skipped": "已跳过",
    }
    effective_user_count = len(config.users) if config.users else 1
    enabled_channels = [
        channel.name for channel in config.notification.channels if channel.enabled
    ]
    summary_lines = [
        "📋 运行摘要",
        f"  执行类型: {execution_mode}",
        f"  启动模式: {config.startup_mode}",
        f"  用户数量: {effective_user_count}",
        f"  CURL校验: {'通过' if curl_validated else '未执行'}",
        (
            f"  通知通道: {', '.join(enabled_channels)}"
            if enabled_channels else "  通知通道: 无"
        ),
    ]

    if include_user_details:
        summary_lines.extend(_build_user_config_summary_lines(config))

    if include_notification_details:
        trigger_lines = ", ".join(
            f"{event.value}={'on' if enabled else 'off'}"
            for event, enabled in config.notification.triggers.items()
        )
        summary_lines.append(f"  通知触发: {trigger_lines}")
        summary_lines.extend(
            _build_notification_diagnostic_lines(config.notification)
        )

    if run_summary:
        summary_lines.extend([
            "📊 执行结果",
            (
                "  最终状态: "
                + status_label_map.get(
                    run_summary.get("final_status", "unknown"),
                    run_summary.get("final_status", "unknown"),
                )
            ),
            f"  成功用户: {run_summary.get('successful_users', 0)}",
            f"  失败用户: {run_summary.get('failed_users', 0)}",
            f"  取消用户: {run_summary.get('cancelled_users', 0)}",
            f"  跳过用户: {run_summary.get('skipped_users', 0)}",
            f"  总阅读时长: {run_summary.get('total_duration_seconds', 0)} 秒",
            f"  成功请求: {run_summary.get('total_reads', 0)}",
            f"  失败请求: {run_summary.get('total_failed_reads', 0)}",
            (
                "  失败分类: "
                + ", ".join(
                    f"{category}={count}"
                    for category, count in run_summary.get(
                        "failure_categories", {}
                    ).items()
                )
                if run_summary.get("failure_categories")
                else "  失败分类: 无"
            ),
            (
                "  失败后继续: 是"
                if run_summary.get("continue_on_failure", False)
                else "  失败后继续: 否"
            ),
        ])

    return "\n".join(summary_lines)


def _format_config_value(value: Any) -> str:
    """格式化配置值，便于摘要输出"""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _describe_user_curl_source(user_config: UserConfig) -> str:
    """描述用户CURL来源"""
    if user_config.file_path and user_config.content:
        return f"文件优先 ({user_config.file_path})，并提供内嵌CURL"
    if user_config.file_path:
        return f"文件: {user_config.file_path}"
    if user_config.content:
        return "内嵌CURL内容"
    return "未配置"


def _build_user_override_diff(user_config: UserConfig,
                              base_config: ReadingConfig) -> str:
    """构建用户阅读覆盖差异摘要"""
    if not user_config.reading_overrides:
        return "无（沿用全局 reading 配置）"

    diff_items = []
    for key in USER_READING_OVERRIDE_FIELDS:
        if key not in user_config.reading_overrides:
            continue

        base_value = getattr(base_config, key)
        override_value = user_config.reading_overrides[key]
        if override_value == base_value:
            continue
        diff_items.append(
            f"{key}: {_format_config_value(base_value)} -> "
            f"{_format_config_value(override_value)}"
        )

    if not diff_items:
        return "无（用户覆盖值与全局 reading 配置一致）"

    return "; ".join(diff_items)


def _build_user_config_summary_lines(config: WeReadConfig) -> List[str]:
    """构建用户级配置诊断摘要"""
    summary_lines = ["👥 用户配置诊断"]

    if not config.users:
        summary_lines.extend([
            "  模式: 单用户",
            f"  全局CURL: {config._get_curl_source_desc()}",
            "  用户覆盖: 无",
        ])
        return summary_lines

    summary_lines.append(f"  模式: 多用户 ({len(config.users)} 个用户)")
    for user_config in config.users:
        time_override_keys = [
            key for key in USER_READING_OVERRIDE_FIELDS
            if key in user_config.reading_overrides
            and key in USER_TIME_STRATEGY_FIELDS
        ]
        if user_config.cookie_refresh_ql is None:
            cookie_refresh_ql_desc = (
                "沿用全局 hack.cookie_refresh_ql "
                f"({_format_config_value(config.hack.cookie_refresh_ql)})"
            )
        else:
            cookie_refresh_ql_desc = (
                "用户级覆盖 "
                f"({_format_config_value(user_config.cookie_refresh_ql)})"
            )
        summary_lines.extend([
            f"  - 用户: {user_config.name}",
            (
                f"    独立CURL: 是 ({_describe_user_curl_source(user_config)})"
                if user_config.file_path or user_config.content
                else "    独立CURL: 否（沿用全局 curl_config）"
            ),
            "    独立通知: 否（当前配置模型未提供用户级通知覆盖）",
            (
                "    独立时间策略: 是 ("
                + ", ".join(time_override_keys)
                + ")"
                if time_override_keys else
                "    独立时间策略: 否（沿用全局 reading.target_duration / "
                "reading.reading_interval）"
            ),
            f"    Cookie刷新QL: {cookie_refresh_ql_desc}",
            f"    覆盖差异: {_build_user_override_diff(user_config, config.reading)}",
        ])

    return summary_lines


def inspect_notification_channel(
    channel: NotificationChannel,
) -> Tuple[str, str, List[str]]:
    """检查通知通道配置状态"""
    if not channel.enabled:
        return "disabled", "通道已禁用", []

    required_fields = NOTIFICATION_CHANNEL_REQUIRED_FIELDS.get(channel.name)
    if required_fields is None:
        return "unsupported", "未知通知通道", []

    missing_fields = [
        field_name for field_name in required_fields
        if not channel.config.get(field_name)
    ]
    if missing_fields:
        return (
            "incomplete",
            f"缺少字段: {', '.join(missing_fields)}",
            missing_fields,
        )

    return "ready", "配置完整", []


def _build_notification_diagnostic_lines(
    notification_config: NotificationConfig,
) -> List[str]:
    """构建通知链路诊断摘要"""
    summary_lines = ["🔔 通知链路诊断"]

    if not notification_config.enabled:
        summary_lines.extend([
            "  通知开关: 禁用",
            "  通道状态: 已整体跳过",
        ])
        return summary_lines

    if not notification_config.channels:
        summary_lines.extend([
            "  通知开关: 启用",
            "  通道状态: 未配置任何通知通道",
        ])
        return summary_lines

    status_counter = {
        "ready": 0,
        "incomplete": 0,
        "disabled": 0,
        "unsupported": 0,
    }
    summary_lines.append("  通知开关: 启用")

    for channel in notification_config.channels:
        status, reason, _ = inspect_notification_channel(channel)
        status_counter[status] += 1
        status_label_map = {
            "ready": "就绪",
            "incomplete": "配置不完整",
            "disabled": "禁用",
            "unsupported": "未知通道",
        }
        summary_lines.append(
            f"  - {channel.name}: {status_label_map[status]} ({reason})"
        )

    summary_lines.append(
        "  通道汇总: "
        f"就绪 {status_counter['ready']} / "
        f"配置不完整 {status_counter['incomplete']} / "
        f"禁用 {status_counter['disabled']} / "
        f"未知 {status_counter['unsupported']}"
    )
    return summary_lines


def _validate_runtime_config(config: WeReadConfig):
    """校验运行前的配置语义并给出更精确的路径提示"""
    validate_config_semantics(config)
    if (config.startup_mode == StartupMode.SCHEDULED.value
            and not config.schedule.enabled):
        raise _config_error(
            "schedule.enabled", "scheduled 模式下必须为 true", False
        )
    if (config.startup_mode == StartupMode.DAEMON.value
            and not config.daemon.enabled):
        raise _config_error(
            "daemon.enabled", "daemon 模式下必须为 true", False
        )
    validation_errors = []
    allowed_override_keys = ", ".join(USER_READING_OVERRIDE_FIELDS.keys())

    if config.users:
        seen_names = {}
        for index, user_config in enumerate(config.users):
            user_path = f"curl_config.users[{index}]"
            user_name = str(user_config.name or "").strip()

            if not user_name:
                validation_errors.append(f"{user_path}.name 不能为空")
            elif user_name in seen_names:
                validation_errors.append(
                    f"{user_path}.name 与 {seen_names[user_name]} 重复: "
                    f"{user_name}"
                )
            else:
                seen_names[user_name] = f"{user_path}.name"

            if not isinstance(user_config.reading_overrides, dict):
                validation_errors.append(
                    f"{user_path}.reading_overrides 必须是对象映射"
                )
            else:
                invalid_keys = sorted(
                    set(user_config.reading_overrides.keys())
                    - set(USER_READING_OVERRIDE_FIELDS.keys())
                )
                for invalid_key in invalid_keys:
                    validation_errors.append(
                        f"{user_path}.reading_overrides.{invalid_key} 不支持，"
                        f"允许项: {allowed_override_keys}"
                    )

            if (user_config.cookie_refresh_ql is not None
                    and not isinstance(user_config.cookie_refresh_ql, bool)):
                validation_errors.append(
                    f"{user_path}.cookie_refresh_ql 必须是布尔值"
                )

            if not user_config.file_path and not user_config.content:
                validation_errors.append(
                    f"{user_path} 未配置 file_path 或 content"
                )
            elif (user_config.file_path
                  and not Path(user_config.file_path).exists()
                  and not user_config.content):
                validation_errors.append(
                    f"{user_path}.file_path 指向的文件不存在: "
                    f"{user_config.file_path}"
                )
    else:
        if not config.curl_file_path and not config.curl_content:
            validation_errors.append(
                "curl_config.file_path 或 curl_config.content 至少需要配置一项"
            )
        elif (config.curl_file_path
              and not Path(config.curl_file_path).exists()
              and not config.curl_content):
            validation_errors.append(
                f"curl_config.file_path 指向的文件不存在: "
                f"{config.curl_file_path}"
            )

    if validation_errors:
        raise ConfigError(
            "配置校验失败:\n"
            + "\n".join(f"  • {error}" for error in validation_errors)
        )


def setup_logging(logging_config: LoggingConfig = None, verbose: bool = False):
    """设置日志"""
    if logging_config is None:
        logging_config = LoggingConfig()

    # 创建日志目录
    log_file_path = Path(logging_config.file)
    log_file_path.parent.mkdir(parents=True, exist_ok=True)

    # 设置日志级别
    if verbose:
        log_level = logging.DEBUG
    else:
        level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL
        }
        log_level = level_map.get(logging_config.level.upper(), logging.INFO)

    # 设置日志格式
    format_map = {
        'simple': '%(levelname)s - [user=%(user)s session=%(session_id)s] - %(message)s',
        'detailed': (
            '%(asctime)s - %(levelname)-8s - '
            '[user=%(user)s session=%(session_id)s] - %(message)s'
        ),
    }
    if logging_config.format == "json":
        formatter = JsonLogFormatter()
    else:
        formatter = RedactingLogFormatter(
            format_map.get(logging_config.format, format_map['detailed'])
        )
    context_filter = LogContextFilter()

    # 解析日志文件大小
    def parse_size(size_str: str) -> int:
        """解析大小字符串，如 '10MB' -> 10485760 bytes"""
        size_str = size_str.upper()
        if size_str.endswith('KB'):
            return int(size_str[:-2]) * 1024
        elif size_str.endswith('MB'):
            return int(size_str[:-2]) * 1024 * 1024
        elif size_str.endswith('GB'):
            return int(size_str[:-2]) * 1024 * 1024 * 1024
        else:
            return int(size_str)

    # 设置处理器
    handlers = []

    # 控制台处理器
    if logging_config.console:
        console_handler = logging.StreamHandler()
        console_handler.addFilter(context_filter)
        console_handler.setFormatter(formatter)
        handlers.append(console_handler)

    # 文件处理器（支持轮转）
    try:
        max_bytes = parse_size(logging_config.max_size)
        file_handler = RotatingFileHandler(
            logging_config.file,
            maxBytes=max_bytes,
            backupCount=logging_config.backup_count,
            encoding='utf-8'
        )
        file_handler.addFilter(context_filter)
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
    except Exception as e:
        # 如果轮转处理器失败，使用普通文件处理器
        file_handler = logging.FileHandler(
            logging_config.file, encoding='utf-8'
        )
        file_handler.addFilter(context_filter)
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
        print(f"警告: 日志轮转设置失败，使用普通文件处理器: {e}")

    # 配置根日志记录器
    logging.basicConfig(
        level=log_level,
        handlers=handlers,
        force=True  # 强制重新配置
    )


def parse_arguments(argv: Optional[List[str]] = None):
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="微信读书智能阅读机器人",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
启动模式说明:
  immediate  - 立即执行一次阅读会话后退出（默认）
  scheduled  - 根据cron表达式定时执行
  daemon     - 守护进程模式，持续运行并定期执行会话

示例:
  python weread-bot.py                    # 立即执行
  python weread-bot.py --mode scheduled   # 定时执行
  python weread-bot.py --mode daemon      # 守护进程模式
        """
    )

    parser.add_argument(
        "--mode", "-m",
        choices=["immediate", "scheduled", "daemon"],
        help="启动模式"
    )

    parser.add_argument(
        "--config", "-c",
        default="config.yaml",
        help="配置文件路径 (默认: config.yaml)"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="启用详细日志输出"
    )

    parser.add_argument(
        "--validate-config",
        action="store_true",
        help="仅校验配置与CURL，不启动阅读会话"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="输出启动摘要与诊断信息，不发起网络阅读请求"
    )

    parser.add_argument(
        "--show-last-run",
        action="store_true",
        help="显示最近一次真实执行结果并退出"
    )

    return parser.parse_args(argv)


async def _validate_curl_configs(config: WeReadConfig) -> None:
    """验证全部 CURL 来源，不发起网络请求。"""
    if config.users:
        logging.info("🔍 验证多用户CURL配置，共 %s 个用户", len(config.users))
        sources = [
            (
                user.name,
                user.file_path,
                user.content,
                f"curl_config.users[{index}]",
                user,
            )
            for index, user in enumerate(config.users)
        ]
    else:
        sources = [
            (
                "default",
                config.curl_file_path,
                config.curl_content,
                "curl_config",
                None,
            )
        ]

    for user_name, file_path, inline_content, source_path, user_config in sources:
        curl_content = load_curl_source(
            file_path, inline_content, source_path
        )
        if not curl_content:
            raise ConfigError(
                f"{source_path}: 未配置可用的 CURL 文件或内容"
            )

        try:
            headers, cookies, curl_data = CurlParser.parse_curl_command(
                curl_content
            )
            is_valid, validation_errors = CurlParser.validate_curl_headers(
                headers, cookies, curl_data, user_name
            )
        except Exception as exc:
            if isinstance(exc, ConfigError):
                raise
            raise ConfigError(
                f"{source_path}: CURL 解析失败，"
                f"当前值={type(exc).__name__}"
            ) from exc

        if not is_valid:
            error_details = "\n".join(
                f"  • {error}" for error in validation_errors
            )
            raise ConfigError(
                f"{source_path}: CURL 校验失败\n{error_details}"
            )

        overrides = user_config.reading_overrides if user_config else {}
        use_curl_position = overrides.get(
            "use_curl_data_first", config.reading.use_curl_data_first
        )
        fallback_to_books = overrides.get(
            "fallback_to_config", config.reading.fallback_to_config
        )
        has_curl_position = bool(curl_data.get("b") and curl_data.get("c"))
        has_book_position = any(
            book.book_id and book.chapters for book in config.reading.books
        )
        if not (
            (use_curl_position and has_curl_position)
            or (fallback_to_books and has_book_position)
        ):
            raise ConfigError(
                f"{source_path}: 没有可用阅读位置；"
                "请在 CURL 中提供 b/c，或配置可回退的 books"
            )

    logging.info("✅ 所有CURL配置验证通过")


async def main() -> int:
    """主函数"""
    # 解析命令行参数
    args = parse_arguments()
    execution_mode = "normal"
    config = None
    run_started = False
    if args.dry_run:
        execution_mode = "dry-run"
    elif args.validate_config:
        execution_mode = "validate-config"
    elif args.show_last_run:
        execution_mode = "show-last-run"

    required_deps = []
    if Path(args.config).exists() and yaml is None:
        required_deps.append("PyYAML")
    if execution_mode == "normal":
        if requests is None:
            required_deps.append("requests")
        if httpx is None:
            required_deps.append("httpx")
        if args.mode == "scheduled" and croniter is None:
            required_deps.append("croniter")

    if required_deps:
        print(f"❌ 缺少依赖: {', '.join(required_deps)}")
        print("请安装: pip install -r requirements.txt")
        return 1

    curl_validated = False

    try:
        # 加载配置
        config_manager = ConfigManager(args.config)
        config = config_manager.config

        if args.show_last_run:
            last_record = None
            history = load_run_history(config.history.file)
            if history:
                last_record = history[-1]
            print(format_last_run_summary(last_record))
            return 0

        # 使用配置设置日志
        setup_logging(config.logging, verbose=args.verbose)

        # 命令行参数覆盖配置文件
        if args.mode:
            config.startup_mode = args.mode
            logging.info(f"🔧 命令行参数覆盖启动模式: {args.mode}")

        _validate_runtime_config(config)

        # 验证CURL配置（早期验证）
        await _validate_curl_configs(config)
        curl_validated = True

        # 打印启动信息
        logging.info("\n" + config.get_startup_info())
        logging.info(
            "\n" + build_runtime_summary(
                config,
                execution_mode,
                curl_validated,
                include_notification_details=args.dry_run,
                include_user_details=args.dry_run or args.validate_config,
            )
        )

        if args.validate_config or args.dry_run:
            logging.info("🧪 诊断模式结束，未启动阅读会话")
            return 0

        # 创建并运行应用程序
        run_started = True
        app = WeReadApplication(config, execution_type=execution_mode)
        run_result = await app.run()
        run_summary = run_result.to_summary_dict()
        logging.info(
            "\n" + build_runtime_summary(
                config,
                execution_mode,
                curl_validated,
                run_summary=run_summary,
            )
        )
        if isinstance(getattr(app, "shutdown_signal", None), int):
            return 130
        return run_result.exit_code

    except KeyboardInterrupt:
        logging.info("👋 用户中断，程序退出")
        return 130
    except Exception as e:
        error_msg = format_error_message("❌ 程序运行错误", e)
        logging.error(error_msg)

        if run_started:
            persist_run_history(
                config,
                execution_mode,
                runtime_error=e,
                error_category=classify_runtime_error(e),
            )

        if execution_mode == "normal" and run_started:
            try:
                notification_service = NotificationService(
                    config.notification
                )
                await notification_service.send_notification_async(
                    error_msg,
                    event=NotificationEvent.RUNTIME_ERROR
                )
            except Exception:
                pass
        return 1

if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
