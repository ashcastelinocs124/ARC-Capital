"""Shared fakes for Trade Lab tests: an OpenAI-SDK-shaped client scripted with replies, and facts."""

from __future__ import annotations

import json
import threading
from types import SimpleNamespace

from castelino.agents.update.models import Fact


def fact(fid: str, text: str, numbers: list[float], url: str = "https://example.com/a") -> Fact:
    return Fact(
        id=fid, text=text, numbers=numbers, provenance="data", source_title="Test", source_url=url
    )


class _Completions:
    def __init__(self, owner):
        self.owner = owner

    def _next(self, kind, kw):
        # pops the first scripted reply of the right kind (an exception fits either), so tests where bull
        # and bear call from two threads at once still get a chat reply for create() and a parse for parse()
        with self.owner.lock:
            self.owner.calls.append((kind, kw))
            for i, item in enumerate(self.owner.script):
                is_exc = isinstance(item, Exception)
                is_parse = not is_exc and hasattr(item.choices[0].message, "parsed")
                if is_exc or is_parse == (kind == "parse"):
                    self.owner.script.pop(i)
                    break
            else:
                raise AssertionError(f"no scripted {kind} reply left for {kw.get('model')}")
        if isinstance(item, Exception):
            raise item
        return item

    def create(self, **kw):
        return self._next("create", kw)

    def parse(self, **kw):
        return self._next("parse", kw)


class FakeClient:
    """Scripted stand-in for openai.OpenAI(): each create()/parse() pops the next reply (or raises it)."""

    def __init__(self, script=None):
        self.script = list(script or [])
        self.calls: list[tuple[str, dict]] = []
        self.lock = threading.Lock()
        self.chat = SimpleNamespace(completions=_Completions(self))


def usage(tin=100, tout=10, cost=None):
    u = SimpleNamespace(prompt_tokens=tin, completion_tokens=tout)
    if cost is not None:
        u.cost = cost
    return u


def parsed(obj, tin=100, tout=10, cost=None):
    msg = SimpleNamespace(parsed=obj, refusal=None, content=obj.model_dump_json() if obj else "")
    msg.model_dump = lambda: {"content": msg.content}
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=usage(tin, tout, cost))


def tool_call(name: str, args: dict, cid: str = "c1"):
    fn = SimpleNamespace(name=name, arguments=json.dumps(args))
    tc = SimpleNamespace(id=cid, type="function", function=fn)
    tc.model_dump = lambda: {
        "id": cid,
        "type": "function",
        "function": {"name": name, "arguments": fn.arguments},
    }
    return tc


def said(content: str = "", calls=None, tin=100, tout=10):
    msg = SimpleNamespace(content=content, tool_calls=calls or None)
    msg.model_dump = lambda: {"content": content}
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=usage(tin, tout))
