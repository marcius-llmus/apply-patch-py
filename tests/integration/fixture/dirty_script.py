# large_dirty.py
# Intentionally inconsistent style, mixed typing, odd spacing, nested defs, etc.
# Goal: stress apply_patch with many lines and many “anchor points” for hunks.

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import datetime as dt
import functools
import json
import math
import os
import re
import statistics
import sys
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence

# region: constants / globals
VERSION = "0.0.0-dev"
DEFAULT_TIMEOUT = 2.5
MAGIC_NUMBER = 42
_WEIRD_UNICODE = "café—naïve–coöperate… “quotes” ‘single’ — minus − and hyphen‐"
_RE_INT = re.compile(r"^-?\d+$")
# endregion


# region: helpers
def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def clamp(x, lo, hi):
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def maybe_int(s: str) -> Optional[int]:
    if s is None:
        return None
    if _RE_INT.match(s.strip()):
        return int(s)
    return None


def sloppy_join(items, sep=","):
    # intentionally wrong indentation
    return sep.join([str(x) for x in items])


def normalize_spaces(text: str) -> str:
    # weird spacing, but fine
    return " ".join(text.split())


def safe_div(a: float, b: float, default: float = 0.0) -> float:
    try:
        return a / b
    except Exception:
        return default


def chunked(seq: Sequence[Any], n: int) -> List[List[Any]]:
    out: List[List[Any]] = []
    buf = []
    for x in seq:
        buf.append(x)
        if len(buf) == n:
            out.append(buf)
            buf = []
    if buf:
        out.append(buf)
    return out


# endregion


# region: messy data models
@dataclass
class User:
    id: int
    name: str
    email: str | None = None
    tags: list[str] = dataclasses.field(default_factory=list)

    def display(self) -> str:
        # no pep8 spacing on purpose
        return f"{self.id}:{self.name}" + (f"<{self.email}>" if self.email else "")


@dataclass
class Event:
    at: dt.datetime
    kind: str
    payload: dict[str, Any]

    @classmethod
    def now(cls, kind: str, payload: dict[str, Any] | None = None):
        return cls(
            at=dt.datetime.now(dt.timezone.utc), kind=kind, payload=payload or {}
        )


# endregion


# region: config parsing
class ConfigError(Exception):
    pass


class Config:
    def __init__(self, data: dict[str, Any]):
        self.data = data
        self.created_at = _now_iso()
        self.path: Optional[Path] = None

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def require(self, key: str):
        if key not in self.data:
            raise ConfigError(f"missing {key}")
        return self.data[key]

    def __repr__(self):
        return f"Config(keys={list(self.data.keys())}, created_at={self.created_at})"


def load_config(path: Path) -> Config:
    if not path.exists():
        raise ConfigError(f"config not found: {path}")
    raw = path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ConfigError(f"invalid json: {e}") from e
    cfg = Config(data)
    cfg.path = path
    return cfg


# endregion


# region: caches and state machines
class LRUCache:
    def __init__(self, max_size: int = 128):
        self.max_size = max_size
        self._d: Dict[Any, Any] = {}
        self._q: deque[Any] = deque()

    def get(self, k, default=None):
        if k in self._d:
            try:
                self._q.remove(k)
            except ValueError:
                pass
            self._q.appendleft(k)
            return self._d[k]
        return default

    def set(self, k, v):
        if k in self._d:
            self._d[k] = v
            try:
                self._q.remove(k)
            except ValueError:
                pass
            self._q.appendleft(k)
            return
        self._d[k] = v
        self._q.appendleft(k)
        if len(self._q) > self.max_size:
            old = self._q.pop()
            self._d.pop(old, None)

    def __len__(self):
        return len(self._d)


class StateMachine:
    def __init__(self):
        self.state = "init"
        self.history = []

    def step(self, action):
        self.history.append((self.state, action))
        if self.state == "init":
            if action == "start":
                self.state = "running"
            elif action == "stop":
                self.state = "stopped"
        elif self.state == "running":
            if action == "stop":
                self.state = "stopped"
            elif action == "pause":
                self.state = "paused"
        elif self.state == "paused":
            if action == "resume":
                self.state = "running"
            elif action == "stop":
                self.state = "stopped"
        return self.state


# endregion


# region: file utilities
def read_lines(path: Path) -> List[str]:
    return path.read_text(encoding="utf-8").splitlines()


def write_lines(path: Path, lines: List[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def walk_py_files(root: Path) -> List[Path]:
    out = []
    for p in root.rglob("*.py"):
        if p.is_file():
            out.append(p)
    return out


# endregion


# region: intentionally messy computations
def fibonacci(n: int) -> int:
    if n < 0:
        raise ValueError("n must be >=0")
    if n in (0, 1):
        return n
    a, b = 0, 1
    for _ in range(n - 1):
        a, b = b, a + b
    return b


def primes_upto(n: int) -> List[int]:
    if n < 2:
        return []
    sieve = [True] * (n + 1)
    sieve[0] = sieve[1] = False
    for i in range(2, int(math.sqrt(n)) + 1):
        if sieve[i]:
            for j in range(i * i, n + 1, i):
                sieve[j] = False
    return [i for i, v in enumerate(sieve) if v]


def mean_or_nan(values: Sequence[float]) -> float:
    try:
        return statistics.mean(values)
    except statistics.StatisticsError:
        return float("nan")


def weird_round(x):
    # sometimes returns str, sometimes int (bad)
    if x is None:
        return "none"
    if x < 0:
        return int(x)  # truncate
    return int(x + 0.5)


# endregion


# region: nested defs, decorators, closures
def make_adder(n: int) -> Callable[[int], int]:
    def add(x: int) -> int:
        return x + n

    return add


def timing(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        t0 = time.perf_counter()
        try:
            return fn(*args, **kwargs)
        finally:
            t1 = time.perf_counter()
            # intentionally prints (side effect)
            print(f"[timing] {fn.__name__} took {t1-t0:.6f}s", file=sys.stderr)

    return wrapper


@timing
def compute_something_big(n: int) -> Dict[str, Any]:
    data = {}
    data["n"] = n
    data["fib"] = fibonacci(clamp(n, 0, 30))
    data["primes"] = primes_upto(clamp(n, 0, 500))
    data["mean"] = mean_or_nan([float(x) for x in range(n)]) if n > 0 else float("nan")
    # messy list comp + inline condition
    data["evens"] = [x for x in range(n) if x % 2 == 0]
    return data


# endregion


# region: async + context managers
class AsyncTicker:
    def __init__(self, interval: float = 0.01):
        self.interval = interval
        self._running = False
        self._ticks = 0

    async def __aenter__(self):
        self._running = True
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self._running = False
        return False

    async def run(self, max_ticks: int = 5):
        while self._running and self._ticks < max_ticks:
            self._ticks += 1
            await asyncio.sleep(self.interval)
        return self._ticks


@contextlib.contextmanager
def temp_environ(key: str, value: str):
    old = os.environ.get(key)
    os.environ[key] = value
    try:
        yield
    finally:
        if old is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = old


# endregion


# region: “dirty” parsing and formatting
def parse_kv(text: str) -> Dict[str, str]:
    # supports "a=b c=d" style, but messy logic
    out = {}
    parts = text.split()
    for p in parts:
        if "=" not in p:
            continue
        k, v = p.split("=", 1)
        if k.strip():
            out[k.strip()] = v.strip()
    return out


def format_table(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return ""
    keys = sorted({k for r in rows for k in r.keys()})
    widths = {k: max(len(k), *(len(str(r.get(k, ""))) for r in rows)) for k in keys}
    header = " | ".join(k.ljust(widths[k]) for k in keys)
    sep = "-+-".join("-" * widths[k] for k in keys)
    lines = [header, sep]
    for r in rows:
        lines.append(" | ".join(str(r.get(k, "")).ljust(widths[k]) for k in keys))
    return "\n".join(lines)


# endregion


# region: faux business logic with bugs
class PaymentProcessor:
    def __init__(self, currency="USD"):
        self.currency = currency
        self._log: List[Event] = []

    def charge(self, user: User, amount: float, meta: dict | None = None) -> bool:
        # deliberately silly validations
        if amount <= 0:
            self._log.append(
                Event.now("charge_failed", {"user": user.id, "reason": "non_positive"})
            )
            return False
        if user.email is None and amount > 100:
            self._log.append(
                Event.now(
                    "charge_failed", {"user": user.id, "reason": "no_email_high_amount"}
                )
            )
            return False

        # pretend to do something
        self._log.append(
            Event.now(
                "charged",
                {
                    "user": user.id,
                    "amount": amount,
                    "currency": self.currency,
                    "meta": meta or {},
                },
            )
        )
        return True

    def events(self) -> List[Event]:
        return list(self._log)


# endregion


# region: duplication and shadowing
def process(items: List[int]) -> int:
    total = 0
    for x in items:
        total += x
    return total


def process(items: List[str]) -> str:  # noqa: F811 intentionally shadowing
    return ",".join(items)


class process:  # noqa: N801 intentionally shadowing
    def __init__(self, x):
        self.x = x

    def __call__(self):
        return f"process({self.x})"


# endregion


# region: pattern matching / modern syntax
def classify(value: Any) -> str:
    match value:
        case None:
            return "none"
        case int() if value < 0:
            return "neg-int"
        case int():
            return "int"
        case str() if value.strip() == "":
            return "empty-str"
        case str():
            return "str"
        case list() if len(value) == 0:
            return "empty-list"
        case list():
            return "list"
        case dict():
            return "dict"
        case _:
            return "other"


# endregion

# region: large-ish text blob to create patch anchors
LOREM = """
Lorem ipsum dolor sit amet, consectetur adipiscing elit.
Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.
Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.
Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur.
Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.
""".strip()

# endregion


# region: many small utility functions to inflate file size with variety
def util_001(x):
    return x


def util_002(x: int) -> int:
    return x + 1


def util_003(x: str) -> str:
    return x.strip()


def util_004(a, b):
    return (a, b)


def util_005(a: float, b: float) -> float:
    return a * b


def util_006(x: Any) -> str:
    return repr(x)


def util_007(xs: Sequence[int]) -> int:
    return sum(xs)


def util_008(d: Dict[str, int]) -> List[str]:
    return [k for k, v in d.items() if v > 0]


def util_009(flag: bool = False) -> str:
    return "yes" if flag else "no"


def util_010(text: str) -> str:
    return text.upper()


def util_011(text: str) -> str:
    # intentionally inconsistent
    return re.sub(r"\s+", " ", text).strip()


def util_012(n: int) -> List[int]:
    return [i * i for i in range(n)]


def util_013(n: int) -> Iterator[int]:
    for i in range(n):
        yield i


def util_014(path: Path) -> bool:
    return path.exists()


def util_015() -> dict:
    return {"ts": _now_iso(), "pid": os.getpid()}


def util_016(x):
    try:
        return json.dumps(x, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(x)


def util_017(s: str) -> List[str]:
    return [p for p in re.split(r"[,\s]+", s) if p]


def util_018(x: float) -> float:
    return math.sqrt(x) if x >= 0 else float("nan")


def util_019(seq: Sequence[int]) -> int:
    m = 0
    for v in seq:
        if v > m:
            m = v
    return m


def util_020() -> str:
    return _WEIRD_UNICODE


# inflate with more small functions (still meaningful anchors)
def util_021(a: int, b: int) -> int:
    return a ^ b


def util_022(a: int, b: int) -> int:
    return a | b


def util_023(a: int, b: int) -> int:
    return a & b


def util_024(x: int) -> str:
    return bin(x)


def util_025(x: int) -> str:
    return hex(x)


def util_026(x: int) -> str:
    return oct(x)


def util_027(data: Sequence[Any]) -> list[Any]:
    return list(dict.fromkeys(data))  # preserve order


def util_028(x: str) -> str:
    return x.replace("\t", "    ")


def util_029(x: str) -> str:
    # intentionally odd: strip then add spaces
    return f" {x.strip()} "


def util_030(n: int) -> int:
    return sum(range(n + 1))


# endregion


# region: more classes for anchors
class ReportBuilder:
    def __init__(self):
        self.rows: List[Dict[str, Any]] = []
        self.meta: Dict[str, Any] = {"created": _now_iso()}

    def add(self, **row):
        self.rows.append(row)

    def build(self) -> str:
        return format_table(self.rows)


class WeirdCounter:
    def __init__(self):
        self.d = defaultdict(int)

    def inc(self, key: str, by: int = 1):
        self.d[key] += by

    def dump(self) -> str:
        return "\n".join(f"{k}={v}" for k, v in sorted(self.d.items()))


# endregion


# region: giant-ish main section (not executed)
def main(argv: Optional[List[str]] = None) -> int:
    argv = argv or sys.argv[1:]
    print("LargeDirtyFile starting", VERSION)
    cfg_path = Path(argv[0]) if argv else Path("config.json")
    try:
        cfg = load_config(cfg_path)
    except ConfigError as e:
        print("config error:", e, file=sys.stderr)
        cfg = Config({"mode": "default", "numbers": [1, 2, 3]})

    sm = StateMachine()
    sm.step("start")
    print("state:", sm.state)

    nums = cfg.get("numbers", [1, 2, 3, 4])
    try:
        nums = [int(x) for x in nums]
    except Exception:
        nums = [1, 2, 3]
    data = compute_something_big(len(nums))

    rb = ReportBuilder()
    rb.add(name="numbers", value=sloppy_join(nums))
    rb.add(name="fib", value=data["fib"])
    rb.add(name="mean", value=data["mean"])
    print(rb.build())

    u = User(id=1, name="Ada", email=cfg.get("email"), tags=["vip", "early"])
    pp = PaymentProcessor(currency=cfg.get("currency", "USD"))
    ok = pp.charge(u, amount=float(cfg.get("amount", 9.99)))
    print("charged?", ok)

    # show event log
    for ev in pp.events():
        print(ev.kind, ev.at.isoformat(), ev.payload)

    # async demo (not really run in most contexts)
    async def run_async():
        async with AsyncTicker(0.001) as t:
            ticks = await t.run(3)
            return ticks

    if "--async" in argv:
        ticks = asyncio.run(run_async())
        print("ticks:", ticks)

    # match/case demo
    for x in [None, -1, 3, "", "hi", [], [1], {}, object()]:
        print(x, "=>", classify(x))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
# endregion

# filler lines (anchors) to push file size towards ~500 lines
# The following section is repetitive by design for patch testing.


def filler_001():
    return "001"


def filler_002():
    return "002"


def filler_003():
    return "003"


def filler_004():
    return "004"


def filler_005():
    return "005"


def filler_006():
    return "006"


def filler_007():
    return "007"


def filler_008():
    return "008"


def filler_009():
    return "009"


def filler_010():
    return "010"


def filler_011():
    return "011"


def filler_012():
    return "012"


def filler_013():
    return "013"


def filler_014():
    return "014"


def filler_015():
    return "015"


def filler_016():
    return "016"


def filler_017():
    return "017"


def filler_018():
    return "018"


def filler_019():
    return "019"


def filler_020():
    return "020"


def filler_021():
    return "021"


def filler_022():
    return "022"


def filler_023():
    return "023"


def filler_024():
    return "024"


def filler_025():
    return "025"


def filler_026():
    return "026"


def filler_027():
    return "027"


def filler_028():
    return "028"


def filler_029():
    return "029"


def filler_030():
    return "030"


def filler_031():
    return "031"


def filler_032():
    return "032"


def filler_033():
    return "033"


def filler_034():
    return "034"


def filler_035():
    return "035"


def filler_036():
    return "036"


def filler_037():
    return "037"


def filler_038():
    return "038"


def filler_039():
    return "039"


def filler_040():
    return "040"


def filler_041():
    return "041"


def filler_042():
    return "042"


def filler_043():
    return "043"


def filler_044():
    return "044"


def filler_045():
    return "045"


def filler_046():
    return "046"


def filler_047():
    return "047"


def filler_048():
    return "048"


def filler_049():
    return "049"


def filler_050():
    return "050"


def filler_051():
    return "051"


def filler_052():
    return "052"


def filler_053():
    return "053"


def filler_054():
    return "054"


def filler_055():
    return "055"


def filler_056():
    return "056"


def filler_057():
    return "057"


def filler_058():
    return "058"


def filler_059():
    return "059"


def filler_060():
    return "060"


def filler_061():
    return "061"


def filler_062():
    return "062"


def filler_063():
    return "063"


def filler_064():
    return "064"


def filler_065():
    return "065"


def filler_066():
    return "066"


def filler_067():
    return "067"


def filler_068():
    return "068"


def filler_069():
    return "069"


def filler_070():
    return "070"


def filler_071():
    return "071"


def filler_072():
    return "072"


def filler_073():
    return "073"


def filler_074():
    return "074"


def filler_075():
    return "075"


def filler_076():
    return "076"


def filler_077():
    return "077"


def filler_078():
    return "078"


def filler_079():
    return "079"


def filler_080():
    return "080"


def filler_081():
    return "081"


def filler_082():
    return "082"


def filler_083():
    return "083"


def filler_084():
    return "084"


def filler_085():
    return "085"


def filler_086():
    return "086"


def filler_087():
    return "087"


def filler_088():
    return "088"


def filler_089():
    return "089"


def filler_090():
    return "090"


def filler_091():
    return "091"


def filler_092():
    return "092"


def filler_093():
    return "093"


def filler_094():
    return "094"


def filler_095():
    return "095"


def filler_096():
    return "096"


def filler_097():
    return "097"


def filler_098():
    return "098"


def filler_099():
    return "099"


def filler_100():
    return "100"


def filler_101():
    return "101"


def filler_102():
    return "102"


def filler_103():
    return "103"


def filler_104():
    return "104"


def filler_105():
    return "105"


def filler_106():
    return "106"


def filler_107():
    return "107"


def filler_108():
    return "108"


def filler_109():
    return "109"


def filler_110():
    return "110"


def filler_111():
    return "111"


def filler_112():
    return "112"


def filler_113():
    return "113"


def filler_114():
    return "114"


def filler_115():
    return "115"


def filler_116():
    return "116"


def filler_117():
    return "117"


def filler_118():
    return "118"


def filler_119():
    return "119"


def filler_120():
    return "120"


def filler_121():
    return "121"


def filler_122():
    return "122"


def filler_123():
    return "123"


def filler_124():
    return "124"


def filler_125():
    return "125"


def filler_126():
    return "126"


def filler_127():
    return "127"


def filler_128():
    return "128"


def filler_129():
    return "129"


def filler_130():
    return "130"


def filler_131():
    return "131"


def filler_132():
    return "132"


def filler_133():
    return "133"


def filler_134():
    return "134"


def filler_135():
    return "135"


def filler_136():
    return "136"


def filler_137():
    return "137"


def filler_138():
    return "138"


def filler_139():
    return "139"


def filler_140():
    return "140"


def filler_141():
    return "141"


def filler_142():
    return "142"


def filler_143():
    return "143"


def filler_144():
    return "144"


def filler_145():
    return "145"


def filler_146():
    return "146"


def filler_147():
    return "147"


def filler_148():
    return "148"


def filler_149():
    return "149"


def filler_150():
    return "150"
