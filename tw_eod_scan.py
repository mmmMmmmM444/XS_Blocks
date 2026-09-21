#!/usr/bin/env python3
"""tw_eod_scan.py — 台股盤後動能選股（量價 + 籌碼）

只用 Python 標準函式庫，不需安裝任何套件。資料來源為證交所 / 櫃買中心公開 JSON：
  上市：MI_INDEX（全部個股行情）、T86（三大法人）、MI_MARGN（融資融券）
  上櫃：afterTrading/otc（行情）、insti/dailyTrade（三大法人）、margin/balance（融資融券）

每個交易日的原始資料會快取在 --cache-dir（預設 ~/.tw_eod_cache），
隔天只需再抓最新一天，回溯 N 日不會重複下載。

預設條件（皆可用參數調整）：
  1. 成交金額 >= 1 億、收盤價 >= 10 元（流動性）
  2. 今日漲幅 >= 3%
  3. 今日量 >= 前 5 日均量 1.5 倍（攻擊量）
  4. 收盤 > MA5 > MA20（多頭排列）
  5. 收盤創 20 日新高（突破）
  6. 外資 + 投信 今日合計買超 > 0

用法：
  python3 tw_eod_scan.py                    # 以最近一個交易日掃描
  python3 tw_eod_scan.py --date 20260903    # 指定日期
  python3 tw_eod_scan.py --min-chg 5 --vol-ratio 2 --top 30
  python3 tw_eod_scan.py --market tpex      # 只看上櫃
  python3 tw_eod_scan.py --demo             # 不連網，用隨機資料跑流程
  python3 tw_eod_scan.py --list-conditions  # 列出所有條件與對應的 XS 積木代號
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Iterable

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")

# --------------------------------------------------------------------------
# 資料結構
# --------------------------------------------------------------------------

@dataclass
class Bar:
    date: str          # YYYYMMDD
    open: float
    high: float
    low: float
    close: float
    volume: int        # 股
    amount: float      # 元
    foreign: int = 0   # 外資買賣超（股）
    trust: int = 0     # 投信買賣超（股）
    dealer: int = 0    # 自營商買賣超（股）
    margin_chg: int | None = None  # 融資餘額增減（張），None = 無資料


@dataclass
class Stock:
    code: str
    name: str
    market: str        # twse / tpex
    bars: list[Bar] = field(default_factory=list)   # 由舊到新


# --------------------------------------------------------------------------
# 小工具
# --------------------------------------------------------------------------

def num(s, default=0.0) -> float:
    """把 '1,234.5'、'--'、'+3.2'、'X' 之類的字串轉成數字。"""
    if s is None:
        return default
    if isinstance(s, (int, float)):
        return float(s)
    t = str(s).replace(",", "").replace("+", "").strip()
    if t in ("", "--", "-", "X", "除權", "除息", "除權息", "N/A"):
        return default
    try:
        return float(t)
    except ValueError:
        return default


def roc_date(d: dt.date) -> str:
    return f"{d.year - 1911}/{d.month:02d}/{d.day:02d}"


def find_col(fields: list[str], *must: str, exclude: Iterable[str] = ()) -> int:
    """找出欄位名稱同時包含所有 must 關鍵字（且不含 exclude）的索引，找不到回 -1。"""
    for i, f in enumerate(fields):
        f = str(f).replace(" ", "")
        if all(k in f for k in must) and not any(x in f for x in exclude):
            return i
    return -1


def is_stock_code(code: str) -> bool:
    """只留一般股票（4 碼數字且不以 0 開頭），排除 ETF(00xx)、權證、DR、特別股等。"""
    return len(code) == 4 and code.isdigit() and code[0] != "0"


# --------------------------------------------------------------------------
# 下載與快取
# --------------------------------------------------------------------------

class Fetcher:
    def __init__(self, cache_dir: str, sleep: float = 3.0, verbose: bool = True):
        self.cache_dir = os.path.expanduser(cache_dir)
        os.makedirs(self.cache_dir, exist_ok=True)
        self.sleep = sleep
        self.verbose = verbose
        self._last_request = 0.0

    def log(self, msg: str):
        if self.verbose:
            print(msg, file=sys.stderr)

    def get_json(self, key: str, url: str) -> dict | None:
        """帶快取的 GET。回傳 JSON dict；網路或解析失敗回 None（不快取失敗）。"""
        path = os.path.join(self.cache_dir, key + ".json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        wait = self.sleep - (time.time() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            self.log(f"  [網路失敗] {url} -> {e}")
            return None
        finally:
            self._last_request = time.time()
        try:
            data = json.loads(raw.decode("utf-8-sig"))
        except ValueError:
            self.log(f"  [非 JSON 回應] {url}")
            return None
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        return data


# --------------------------------------------------------------------------
# 證交所 / 櫃買 JSON 解析
# 兩邊的 JSON 都是 {fields:[...], data:[[...]]} 或 {tables:[{fields,data}]}
# 一律用「欄位名稱關鍵字」找欄位，避免官方調整欄位順序就壞掉。
# --------------------------------------------------------------------------

def iter_tables(payload: dict | None):
    """把證交所（fields1/data1…、fields/data）與櫃買（tables[]）統一成 (fields, rows)。"""
    if not payload:
        return
    if "tables" in payload and isinstance(payload["tables"], list):
        for t in payload["tables"]:
            if t.get("fields") and t.get("data"):
                yield t["fields"], t["data"]
    if payload.get("fields") and payload.get("data"):
        yield payload["fields"], payload["data"]
    for i in range(1, 12):
        if payload.get(f"fields{i}") and payload.get(f"data{i}"):
            yield payload[f"fields{i}"], payload[f"data{i}"]


def pick_table(payload, *must_cols: str):
    for fields, rows in iter_tables(payload):
        if all(find_col(fields, c) >= 0 for c in must_cols):
            return fields, rows
    return None, None


def parse_quotes(payload, market: str, date: str) -> dict[str, tuple[str, Bar]]:
    """回傳 {code: (name, Bar)}。"""
    if market == "twse":
        fields, rows = pick_table(payload, "證券代號", "收盤價", "成交股數")
    else:
        fields, rows = pick_table(payload, "代號", "收盤", "成交股數")
    if not rows:
        return {}
    c_code = find_col(fields, "代號")
    c_name = find_col(fields, "名稱")
    c_open = find_col(fields, "開盤")
    c_high = find_col(fields, "最高")
    c_low = find_col(fields, "最低")
    c_close = find_col(fields, "收盤")
    c_vol = find_col(fields, "成交股數")
    c_amt = find_col(fields, "成交金額")
    out = {}
    for r in rows:
        code = str(r[c_code]).strip()
        if not is_stock_code(code):
            continue
        close = num(r[c_close])
        if close <= 0:
            continue
        out[code] = (str(r[c_name]).strip(), Bar(
            date=date, open=num(r[c_open]), high=num(r[c_high]), low=num(r[c_low]),
            close=close, volume=int(num(r[c_vol])), amount=num(r[c_amt])))
    return out


def parse_inst(payload, market: str) -> dict[str, tuple[int, int, int]]:
    """回傳 {code: (外資買賣超股數, 投信買賣超股數, 自營商買賣超股數)}。"""
    fields, rows = pick_table(payload, "代號", "投信")
    if not rows:
        return {}
    c_code = find_col(fields, "代號")
    # 上市 T86：外陸資買賣超股數(不含外資自營商)；上櫃：外資及陸資(不含外資自營商)-買賣超股數
    c_f = find_col(fields, "外", "買賣超", exclude=("自營商買賣超",))
    if c_f >= 0 and "自營商" in str(fields[c_f]) and "不含" not in str(fields[c_f]):
        c_f = -1
    c_t = find_col(fields, "投信", "買賣超")
    # 自營商合計：上市 T86 為「自營商買賣超股數」，上櫃為「自營商-買賣超股數」；其餘(自行買賣)/(避險)是分項
    c_d = -1
    for i, f in enumerate(fields):
        f = str(f).replace(" ", "")
        if f in ("自營商買賣超股數", "自營商-買賣超股數"):
            c_d = i
            break
    if c_d < 0:
        c_d = find_col(fields, "自營商", "買賣超", exclude=("外",))
    out = {}
    for r in rows:
        code = str(r[c_code]).strip()
        if not is_stock_code(code):
            continue
        out[code] = (
            int(num(r[c_f])) if c_f >= 0 else 0,
            int(num(r[c_t])) if c_t >= 0 else 0,
            int(num(r[c_d])) if c_d >= 0 else 0,
        )
    return out


def parse_margin(payload, market: str) -> dict[str, int]:
    """回傳 {code: 融資餘額增減（張）}；解析不到就回空 dict（融資為選配）。"""
    fields, rows = pick_table(payload, "代號")
    if not rows:
        return {}
    c_code = find_col(fields, "代號")
    if market == "twse":
        # MI_MARGN 欄位：股票代號, 股票名稱, 融資買進, 賣出, 現金償還, 前日餘額, 今日餘額, ...（融資在前）
        c_prev = find_col(fields, "前日餘額")
        c_now = find_col(fields, "今日餘額")
        unit = 1
    else:
        c_prev = find_col(fields, "前資餘額")
        c_now = find_col(fields, "資餘額", exclude=("前",))
        unit = 1
    if c_prev < 0 or c_now < 0:
        return {}
    out = {}
    for r in rows:
        code = str(r[c_code]).strip()
        if not is_stock_code(code):
            continue
        out[code] = int((num(r[c_now]) - num(r[c_prev])) * unit)
    return out


# --------------------------------------------------------------------------
# 載入 N 個交易日
# --------------------------------------------------------------------------

def twse_urls(d: dt.date) -> dict[str, str]:
    ymd = d.strftime("%Y%m%d")
    return {
        "quotes": f"https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&date={ymd}&type=ALLBUT0999",
        "inst": f"https://www.twse.com.tw/fund/T86?response=json&date={ymd}&selectType=ALLBUT0999",
        "margin": f"https://www.twse.com.tw/exchangeReport/MI_MARGN?response=json&date={ymd}&selectType=ALL",
    }


def tpex_urls(d: dt.date) -> dict[str, str]:
    q = urllib.parse.quote(d.strftime("%Y/%m/%d"), safe="")
    return {
        "quotes": f"https://www.tpex.org.tw/www/zh-tw/afterTrading/otc?date={q}&response=json",
        "inst": f"https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade?type=Daily&sect=EW&date={q}&response=json",
        "margin": f"https://www.tpex.org.tw/www/zh-tw/margin/balance?date={q}&response=json",
    }


def load_day(fetcher: Fetcher, d: dt.date, markets: list[str], want_inst: bool, want_margin: bool
             ) -> dict[str, Stock] | None:
    """抓一天。非交易日（行情表為空）回 None。"""
    ymd = d.strftime("%Y%m%d")
    stocks: dict[str, Stock] = {}
    got_any = False
    for m in markets:
        urls = twse_urls(d) if m == "twse" else tpex_urls(d)
        quotes = parse_quotes(fetcher.get_json(f"{ymd}_{m}_quotes", urls["quotes"]), m, ymd)
        if not quotes:
            continue
        got_any = True
        inst = parse_inst(fetcher.get_json(f"{ymd}_{m}_inst", urls["inst"]), m) if want_inst else {}
        margin = parse_margin(fetcher.get_json(f"{ymd}_{m}_margin", urls["margin"]), m) if want_margin else {}
        for code, (name, bar) in quotes.items():
            if code in inst:
                bar.foreign, bar.trust, bar.dealer = inst[code]
            if code in margin:
                bar.margin_chg = margin[code]
            stocks[code] = Stock(code=code, name=name, market=m, bars=[bar])
    return stocks if got_any else None


def load_history(fetcher: Fetcher, end: dt.date, sessions: int, markets: list[str],
                 want_inst: bool, want_margin: bool) -> tuple[dict[str, Stock], list[str]]:
    """從 end 往回抓，直到湊滿 sessions 個交易日。回傳 (stocks, 交易日清單由舊到新)。"""
    universe: dict[str, Stock] = {}
    days: list[str] = []
    d = end
    misses = 0
    while len(days) < sessions and misses < 15:
        if d.weekday() >= 5:
            d -= dt.timedelta(days=1)
            continue
        fetcher.log(f"讀取 {d:%Y-%m-%d} …")
        day = load_day(fetcher, d, markets, want_inst, want_margin)
        if day is None:
            misses += 1
            fetcher.log(f"  {d:%Y-%m-%d} 無資料（休市或尚未公布），略過")
        else:
            misses = 0
            days.append(d.strftime("%Y%m%d"))
            for code, s in day.items():
                universe.setdefault(code, Stock(code=code, name=s.name, market=s.market)).bars.extend(s.bars)
        d -= dt.timedelta(days=1)
    for s in universe.values():
        s.bars.sort(key=lambda b: b.date)
    return universe, sorted(days)


# --------------------------------------------------------------------------
# 選股條件與評分
# --------------------------------------------------------------------------

@dataclass
class Params:
    min_amount: float = 1e8
    min_price: float = 10.0
    min_chg: float = 3.0
    vol_ratio: float = 1.5
    vol_days: int = 5
    ma_fast: int = 5
    ma_slow: int = 20
    breakout_days: int = 20
    require_breakout: bool = True
    require_ma: bool = True
    require_inst: bool = True
    inst_days: int = 3


CONDITIONS = [
    ("成交金額 >= N 元、收盤 >= N 元", "P0040 成交值 / P0010 收盤價", "--min-amount / --min-price"),
    ("今日漲幅 >= N%", "P0020 漲跌幅 [P0020-001-A]", "--min-chg"),
    ("今日量 >= 前 N 日均量 X 倍", "P0030 成交量 [P0030-00x] 爆量", "--vol-ratio / --vol-days"),
    ("收盤 > MA5 > MA20 多頭排列", "P0070 技術指標 均線", "--ma-fast / --ma-slow / --no-ma"),
    ("收盤創 N 日新高", "P0010 收盤價 創N日新高", "--breakout-days / --no-breakout"),
    ("外資 + 投信 今日合計買超 > 0", "B0010 外資 / B0020 投信 [B0010-001-A]", "--no-inst"),
    ("法人連續買超天數（評分用）", "B0040 三大法人 連續N日買超", "--inst-days"),
    ("融資增減（僅顯示）", "B0060 融資", "--margin"),
]


@dataclass
class Hit:
    stock: Stock
    date: str
    close: float
    chg_pct: float
    vol_ratio: float
    amount: float
    ma_fast: float
    ma_slow: float
    breakout: bool
    inst_today: int      # 外資+投信 買賣超（張）
    inst_streak: int     # 外資+投信 連續買超天數
    inst_ratio: float    # 近 inst_days 日法人買超 / 同期成交量
    margin_chg: int | None
    score: float


def evaluate(s: Stock, p: Params) -> Hit | None:
    bars = s.bars
    need = max(p.ma_slow, p.breakout_days, p.vol_days + 1, 2)
    if len(bars) < need:
        return None
    today, prev = bars[-1], bars[-2]
    if today.close < p.min_price or today.amount < p.min_amount:
        return None
    chg = (today.close / prev.close - 1) * 100 if prev.close > 0 else 0.0
    if chg < p.min_chg:
        return None
    hist_vol = [b.volume for b in bars[-1 - p.vol_days:-1]]
    avg_vol = sum(hist_vol) / len(hist_vol) if hist_vol else 0
    vr = today.volume / avg_vol if avg_vol > 0 else 0.0
    if vr < p.vol_ratio:
        return None
    closes = [b.close for b in bars]
    ma_f = sum(closes[-p.ma_fast:]) / p.ma_fast
    ma_s = sum(closes[-p.ma_slow:]) / p.ma_slow
    if p.require_ma and not (today.close > ma_f > ma_s):
        return None
    prior_high = max(b.high for b in bars[-p.breakout_days:-1])
    breakout = today.close >= prior_high
    if p.require_breakout and not breakout:
        return None
    inst_today = (today.foreign + today.trust) // 1000
    if p.require_inst and inst_today <= 0:
        return None
    streak = 0
    for b in reversed(bars):
        if b.foreign + b.trust > 0:
            streak += 1
        else:
            break
    recent = bars[-p.inst_days:]
    inst_sum = sum(b.foreign + b.trust for b in recent)
    vol_sum = sum(b.volume for b in recent)
    inst_ratio = inst_sum / vol_sum * 100 if vol_sum > 0 else 0.0

    score = (
        min(chg, 10) * 2.0            # 漲幅，上限 10%
        + min(vr, 5) * 4.0            # 量能，上限 5 倍
        + (10.0 if breakout else 0)   # 突破
        + min(streak, 5) * 3.0        # 法人連買
        + max(min(inst_ratio, 20), -20) * 0.5   # 法人吃貨佔量比
    )
    return Hit(s, today.date, today.close, chg, vr, today.amount, ma_f, ma_s, breakout,
               inst_today, streak, inst_ratio, today.margin_chg, score)


# --------------------------------------------------------------------------
# 輸出
# --------------------------------------------------------------------------

def print_table(hits: list[Hit], top: int):
    hdr = f"{'#':>3} {'代號':<5} {'名稱':<8} {'市場':<4} {'收盤':>8} {'漲幅%':>6} {'量比':>5} {'成交額(億)':>9} {'突破':>4} {'法人今日(張)':>10} {'連買':>4} {'法人占量%':>8} {'融資增減':>8} {'分數':>6}"
    print(hdr)
    print("-" * len(hdr))
    for i, h in enumerate(hits[:top], 1):
        name = h.stock.name[:6]
        pad = 8 - sum(2 if ord(c) > 255 else 1 for c in name)
        mkt = "上市" if h.stock.market == "twse" else "上櫃"
        mc = "" if h.margin_chg is None else f"{h.margin_chg:+d}"
        print(f"{i:>3} {h.stock.code:<5} {name}{' ' * max(pad, 0)} {mkt:<4} {h.close:>8.2f} {h.chg_pct:>6.2f} "
              f"{h.vol_ratio:>5.1f} {h.amount / 1e8:>9.2f} {'✓' if h.breakout else '':>4} "
              f"{h.inst_today:>10d} {h.inst_streak:>4d} {h.inst_ratio:>8.1f} {mc:>8} {h.score:>6.1f}")


def write_csv(hits: list[Hit], path: str):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["日期", "代號", "名稱", "市場", "收盤", "漲幅%", "量比", "成交金額", "MA快", "MA慢",
                    "突破", "法人今日買超(張)", "法人連買天數", "法人占量%", "融資增減(張)", "分數"])
        for h in hits:
            w.writerow([h.date, h.stock.code, h.stock.name, h.stock.market, f"{h.close:.2f}",
                        f"{h.chg_pct:.2f}", f"{h.vol_ratio:.2f}", int(h.amount), f"{h.ma_fast:.2f}",
                        f"{h.ma_slow:.2f}", int(h.breakout), h.inst_today, h.inst_streak,
                        f"{h.inst_ratio:.2f}", "" if h.margin_chg is None else h.margin_chg, f"{h.score:.1f}"])


# --------------------------------------------------------------------------
# Demo：不連網的隨機資料，用來驗證流程
# --------------------------------------------------------------------------

def demo_universe(sessions: int, seed: int = 42) -> tuple[dict[str, Stock], list[str]]:
    rng = random.Random(seed)
    end = dt.date.today()
    days = []
    d = end
    while len(days) < sessions:
        if d.weekday() < 5:
            days.append(d.strftime("%Y%m%d"))
        d -= dt.timedelta(days=1)
    days.reverse()
    universe = {}
    for i in range(300):
        code = f"{2300 + i:04d}"
        market = "twse" if i % 3 else "tpex"
        px = rng.uniform(15, 300)
        base_vol = rng.randint(500, 20000) * 1000
        bars = []
        hot = rng.random() < 0.08   # 8% 的股票在最後一天做出攻擊訊號
        for j, day in enumerate(days):
            drift = rng.gauss(0.001, 0.02)
            if hot and j == len(days) - 1:
                drift = rng.uniform(0.04, 0.095)
            o = px
            c = max(px * (1 + drift), 1)
            h = max(o, c) * (1 + abs(rng.gauss(0, 0.005)))
            lo = min(o, c) * (1 - abs(rng.gauss(0, 0.005)))
            vol = int(base_vol * (rng.uniform(2, 4) if hot and j == len(days) - 1 else rng.uniform(0.6, 1.4)))
            f = int(rng.gauss(0, base_vol * 0.05))
            t = int(rng.gauss(0, base_vol * 0.02))
            if hot and j >= len(days) - 3:
                f, t = abs(f) + base_vol // 20, abs(t)
            bars.append(Bar(day, o, h, lo, c, vol, c * vol, f, t, 0, rng.randint(-300, 300)))
            px = c
        universe[code] = Stock(code, f"示範{code}", market, bars)
    return universe, days


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="台股盤後動能選股（量價 + 籌碼）", formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split("用法：")[1] if "用法：" in __doc__ else None)
    ap.add_argument("--date", help="掃描日期 YYYYMMDD，預設今天（自動退到最近交易日）")
    ap.add_argument("--lookback", type=int, default=30, help="回溯交易日數（預設 30，至少要大於 MA 慢線與突破天數）")
    ap.add_argument("--market", choices=["all", "twse", "tpex"], default="all", help="上市 / 上櫃 / 全部")
    ap.add_argument("--top", type=int, default=40, help="顯示前 N 名")
    ap.add_argument("--min-amount", type=float, default=1e8, help="今日成交金額下限（元），預設 1 億")
    ap.add_argument("--min-price", type=float, default=10, help="收盤價下限")
    ap.add_argument("--min-chg", type=float, default=3.0, help="今日漲幅下限 %%")
    ap.add_argument("--vol-ratio", type=float, default=1.5, help="今日量 / 前 N 日均量 的下限")
    ap.add_argument("--vol-days", type=int, default=5, help="均量天數")
    ap.add_argument("--ma-fast", type=int, default=5)
    ap.add_argument("--ma-slow", type=int, default=20)
    ap.add_argument("--no-ma", action="store_true", help="不要求 收盤 > MA快 > MA慢")
    ap.add_argument("--breakout-days", type=int, default=20, help="創 N 日新高")
    ap.add_argument("--no-breakout", action="store_true", help="不要求創新高")
    ap.add_argument("--no-inst", action="store_true", help="不要求外資+投信買超（也不下載法人資料）")
    ap.add_argument("--inst-days", type=int, default=3, help="法人占量比的計算天數")
    ap.add_argument("--margin", action="store_true", help="同時下載融資餘額並顯示增減")
    ap.add_argument("--cache-dir", default="~/.tw_eod_cache")
    ap.add_argument("--sleep", type=float, default=3.0, help="每次請求間隔秒數（證交所有流量限制，建議 >= 3）")
    ap.add_argument("--out", help="輸出 CSV 路徑，預設 scan_<日期>.csv；填 - 則不輸出")
    ap.add_argument("--json", action="store_true", help="改以 JSON 輸出到 stdout（給其他程式接）")
    ap.add_argument("--demo", action="store_true", help="不連網，用隨機資料跑一次流程")
    ap.add_argument("--list-conditions", action="store_true", help="列出條件與對應的 XS 積木代號後結束")
    ap.add_argument("-q", "--quiet", action="store_true")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    a = parse_args(argv)
    if a.list_conditions:
        for cond, xs, flag in CONDITIONS:
            print(f"{cond:<32} XS: {xs:<40} 參數: {flag}")
        return 0

    p = Params(min_amount=a.min_amount, min_price=a.min_price, min_chg=a.min_chg, vol_ratio=a.vol_ratio,
               vol_days=a.vol_days, ma_fast=a.ma_fast, ma_slow=a.ma_slow, breakout_days=a.breakout_days,
               require_breakout=not a.no_breakout, require_ma=not a.no_ma, require_inst=not a.no_inst,
               inst_days=a.inst_days)
    need = max(p.ma_slow, p.breakout_days, p.vol_days + 1) + 1
    sessions = max(a.lookback, need)

    if a.demo:
        universe, days = demo_universe(sessions)
    else:
        end = dt.datetime.strptime(a.date, "%Y%m%d").date() if a.date else dt.date.today()
        markets = ["twse", "tpex"] if a.market == "all" else [a.market]
        fetcher = Fetcher(a.cache_dir, sleep=a.sleep, verbose=not a.quiet)
        universe, days = load_history(fetcher, end, sessions, markets, want_inst=not a.no_inst, want_margin=a.margin)
        if not days:
            print("抓不到任何交易日資料：請確認網路可連 twse.com.tw / tpex.org.tw，或用 --date 指定已收盤的日期。", file=sys.stderr)
            return 2
        if len(days) < need:
            print(f"只取得 {len(days)} 個交易日，少於條件需要的 {need} 日；請加大 --lookback 或檢查快取。", file=sys.stderr)
            return 2

    hits = [h for s in universe.values() if (h := evaluate(s, p))]
    hits.sort(key=lambda h: h.score, reverse=True)
    scan_date = days[-1]

    if a.json:
        print(json.dumps([{"code": h.stock.code, "name": h.stock.name, "market": h.stock.market,
                           **{k: v for k, v in h.__dict__.items() if k != "stock"}} for h in hits],
                         ensure_ascii=False, indent=1))
    else:
        print(f"掃描日 {scan_date}  母體 {len(universe)} 檔  交易日 {len(days)}  命中 {len(hits)} 檔"
              f"{'  [DEMO 隨機資料]' if a.demo else ''}")
        print(f"條件：漲幅>={p.min_chg}%  量比>={p.vol_ratio}x({p.vol_days}日)  成交額>={p.min_amount / 1e8:g}億  "
              f"{'MA多頭 ' if p.require_ma else ''}{'創' + str(p.breakout_days) + '日高 ' if p.require_breakout else ''}"
              f"{'外資+投信買超 ' if p.require_inst else ''}")
        print()
        if hits:
            print_table(hits, a.top)
        else:
            print("今日沒有符合條件的股票。可放寬 --min-chg / --vol-ratio 或加 --no-breakout。")

    out = a.out or f"scan_{scan_date}.csv"
    if out != "-" and hits:
        write_csv(hits, out)
        if not a.json:
            print(f"\n已輸出 {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
