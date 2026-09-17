import importlib.util
import sys
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_weread_bot():
    """重新加载 weread-bot.py，隔离类变量和模块级状态。"""
    module_name = f"weread_bot_test_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(
        module_name, ROOT / "weread-bot.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


class FakeClock:
    def __init__(self, current=0.0):
        self.current = float(current)

    def monotonic(self) -> float:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += float(seconds)


class FakeHttpClient:
    def __init__(self, json_responses=None, raw_responses=None):
        self.json_responses = list(json_responses or [])
        self.raw_responses = list(raw_responses or [])
        self.json_calls = []
        self.raw_calls = []
        self.close_calls = 0

    async def post_json(self, url, data, headers, cookies):
        self.json_calls.append((url, data.copy(), headers.copy(), cookies.copy()))
        response = self.json_responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    async def post_raw(
        self, url, headers=None, cookies=None, json_data=None, data=None
    ):
        self.raw_calls.append(
            {
                "url": url,
                "headers": headers,
                "cookies": cookies,
                "json_data": json_data,
                "data": data,
            }
        )
        response = self.raw_responses.pop(0) if self.raw_responses else None
        if isinstance(response, Exception):
            raise response
        return response

    async def close(self):
        self.close_calls += 1
