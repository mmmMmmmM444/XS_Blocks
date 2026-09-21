"""離線測試：把模擬證交所 / 櫃買 JSON 放進快取目錄，驗證解析與整條流程。
執行：python3 -m unittest tests.test_tw_eod_scan -v
"""
import datetime as dt
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tw_eod_scan as m  # noqa: E402

TWSE_QUOTES = {
    "stat": "OK", "date": "20260903",
    "tables": [
        {"title": "大盤統計資訊", "fields": ["指數", "收盤指數", "漲跌(+/-)"], "data": [["發行量加權股價指數", "23,000.00", "+"]]},
        {"title": "每日收盤行情(全部(不含權證、牛熊證))",
         "fields": ["證券代號", "證券名稱", "成交股數", "成交筆數", "成交金額", "開盤價", "最高價", "最低價", "收盤價",
                    "漲跌(+/-)", "漲跌價差", "最後揭示買價", "最後揭示買量", "最後揭示賣價", "最後揭示賣量", "本益比"],
         "data": [
             ["0050", "元大台灣50", "10,000,000", "5,000", "1,900,000,000", "190.00", "191.00", "189.00", "190.50", "+", "0.50", "190.45", "10", "190.50", "5", "0.00"],
             ["2330", "台積電", "30,000,000", "40,000", "30,000,000,000", "995.00", "1,010.00", "990.00", "1,005.00", "+", "10.00", "1,000.00", "100", "1,005.00", "50", "25.00"],
             ["2603", "長榮", "50,000,000", "30,000", "10,000,000,000", "195.00", "205.00", "194.00", "204.00", "+", "9.00", "203.50", "50", "204.00", "20", "5.00"],
             ["9999", "無成交", "0", "0", "0", "--", "--", "--", "--", " ", "0.00", "--", "0", "--", "0", "0.00"],
         ]},
    ],
}
TWSE_T86 = {
    "stat": "OK",
    "fields": ["證券代號", "證券名稱", "外陸資買進股數(不含外資自營商)", "外陸資賣出股數(不含外資自營商)", "外陸資買賣超股數(不含外資自營商)",
               "外資自營商買進股數", "外資自營商賣出股數", "外資自營商買賣超股數", "投信買進股數", "投信賣出股數", "投信買賣超股數",
               "自營商買賣超股數", "自營商買進股數(自行買賣)", "自營商賣出股數(自行買賣)", "自營商買賣超股數(自行買賣)",
               "自營商買進股數(避險)", "自營商賣出股數(避險)", "自營商買賣超股數(避險)", "三大法人買賣超股數"],
    "data": [
        ["2330", "台積電", "10,000,000", "8,000,000", "2,000,000", "0", "0", "0", "500,000", "100,000", "400,000", "-300,000", "0", "0", "0", "0", "0", "-300,000", "2,100,000"],
        ["2603", "長榮", "3,000,000", "5,000,000", "-2,000,000", "0", "0", "0", "0", "0", "0", "100,000", "0", "0", "0", "0", "0", "100,000", "-1,900,000"],
    ],
}
TWSE_MARGN = {
    "stat": "OK",
    "tables": [
        {"title": "融資融券彙總", "fields": ["項目", "買進", "賣出", "現金(券)償還", "前日餘額", "今日餘額"], "data": [["融資(交易單位)", "1", "2", "3", "4", "5"]]},
        {"title": "融資融券明細",
         "fields": ["股票代號", "股票名稱", "買進", "賣出", "現金償還", "前日餘額", "今日餘額", "次一營業日限額",
                    "買進", "賣出", "現券償還", "前日餘額", "今日餘額", "次一營業日限額", "資券互抵", "註記"],
         "data": [["2330", "台積電", "500", "300", "10", "20,000", "20,190", "50,000", "10", "5", "0", "100", "105", "1,000", "0", ""],
                  ["2603", "長榮", "5,000", "6,000", "100", "80,000", "78,900", "100,000", "0", "0", "0", "0", "0", "0", "0", ""]]},
    ],
}
TPEX_QUOTES = {
    "stat": "ok", "date": "115/09/03",
    "tables": [{"title": "上櫃股票每日收盤行情(不含定價)",
                "fields": ["代號", "名稱", "收盤", "漲跌", "開盤", "最高", "最低", "成交股數", "成交金額(元)", "成交筆數",
                           "最後買價", "最後買量(千股)", "最後賣價", "最後賣量(千股)", "發行股數", "次日參考價", "次日漲停價", "次日跌停價"],
                "data": [
                    ["3105", "穩懋", "150.00", "+7.00", "144.00", "151.00", "143.50", "8,000,000", "1,190,000,000", "6,000", "149.50", "10", "150.00", "5", "400,000,000", "150.00", "165.00", "135.00"],
                    ["00679B", "元大美債20年", "30.00", "0.00", "30.00", "30.10", "29.90", "1,000,000", "30,000,000", "500", "", "", "", "", "", "", "", ""],
                ]}],
}
TPEX_INST = {
    "stat": "ok",
    "tables": [{"fields": ["代號", "名稱", "外資及陸資(不含外資自營商)-買進股數", "外資及陸資(不含外資自營商)-賣出股數", "外資及陸資(不含外資自營商)-買賣超股數",
                           "外資自營商-買進股數", "外資自營商-賣出股數", "外資自營商-買賣超股數", "外資及陸資-買進股數", "外資及陸資-賣出股數", "外資及陸資-買賣超股數",
                           "投信-買進股數", "投信-賣出股數", "投信-買賣超股數", "自營商(自行買賣)-買進股數", "自營商(自行買賣)-賣出股數", "自營商(自行買賣)-買賣超股數",
                           "自營商(避險)-買進股數", "自營商(避險)-賣出股數", "自營商(避險)-買賣超股數", "自營商-買進股數", "自營商-賣出股數", "自營商-買賣超股數", "三大法人買賣超股數合計"],
                "data": [["3105", "穩懋", "2,000,000", "1,000,000", "1,000,000", "0", "0", "0", "2,000,000", "1,000,000", "1,000,000",
                          "300,000", "0", "300,000", "10,000", "0", "10,000", "0", "20,000", "-20,000", "10,000", "20,000", "-10,000", "1,290,000"]]}],
}
TPEX_MARGIN = {
    "stat": "ok",
    "tables": [{"fields": ["代號", "名稱", "前資餘額(張)", "資買", "資賣", "現償", "資餘額(張)", "資屬證金", "資使用率(%)", "資限額",
                           "前券餘額(張)", "券賣", "券買", "券償", "券餘額(張)", "券屬證金", "券使用率(%)", "券限額", "資券相抵(張)", "備註"],
                "data": [["3105", "穩懋", "10,000", "800", "300", "0", "10,500", "0", "10.5", "100,000", "100", "0", "0", "0", "100", "0", "0.1", "100,000", "50", ""]]}],
}
HOLIDAY = {"stat": "很抱歉，沒有符合條件的資料!"}


class ParserTests(unittest.TestCase):
    def test_twse_quotes(self):
        q = m.parse_quotes(TWSE_QUOTES, "twse", "20260903")
        self.assertEqual(set(q), {"2330", "2603"})       # ETF 0050 與無成交 9999 被排除
        name, bar = q["2330"]
        self.assertEqual(name, "台積電")
        self.assertEqual((bar.open, bar.high, bar.low, bar.close), (995.0, 1010.0, 990.0, 1005.0))
        self.assertEqual(bar.volume, 30_000_000)
        self.assertEqual(bar.amount, 30_000_000_000)

    def test_twse_inst(self):
        i = m.parse_inst(TWSE_T86, "twse")
        self.assertEqual(i["2330"], (2_000_000, 400_000, -300_000))
        self.assertEqual(i["2603"], (-2_000_000, 0, 100_000))

    def test_twse_margin(self):
        mg = m.parse_margin(TWSE_MARGN, "twse")
        self.assertEqual(mg["2330"], 190)
        self.assertEqual(mg["2603"], -1100)

    def test_tpex_quotes(self):
        q = m.parse_quotes(TPEX_QUOTES, "tpex", "20260903")
        self.assertEqual(list(q), ["3105"])
        _, bar = q["3105"]
        self.assertEqual((bar.open, bar.high, bar.low, bar.close), (144.0, 151.0, 143.5, 150.0))
        self.assertEqual(bar.amount, 1_190_000_000)

    def test_tpex_inst(self):
        i = m.parse_inst(TPEX_INST, "tpex")
        self.assertEqual(i["3105"], (1_000_000, 300_000, -10_000))   # 自營商取合計，不是(自行買賣)

    def test_tpex_margin(self):
        self.assertEqual(m.parse_margin(TPEX_MARGIN, "tpex")["3105"], 500)

    def test_holiday(self):
        self.assertEqual(m.parse_quotes(HOLIDAY, "twse", "20260906"), {})
        self.assertEqual(m.parse_inst(HOLIDAY, "twse"), {})


class PipelineTests(unittest.TestCase):
    """把 fixture 放進快取，Fetcher 走快取路徑就不會連網。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = self.tmp.name
        self.days = []
        d = dt.date(2026, 9, 3)
        while len(self.days) < 25:
            if d.weekday() < 5 and d != dt.date(2026, 8, 20):   # 8/20 當作休市日
                self.days.append(d)
            d -= dt.timedelta(days=1)
        # 25 個交易日：每天複製 fixture，但價量做一點變化，讓最後一天出現訊號
        for k, day in enumerate(reversed(self.days)):
            ymd = day.strftime("%Y%m%d")
            q = json.loads(json.dumps(TWSE_QUOTES))
            rows = q["tables"][1]["data"]
            last = k == len(self.days) - 1
            for r in rows:
                if r[0] == "2603":
                    px = 150 + k * 0.5 if not last else 175.0
                    r[5] = r[6] = r[7] = r[8] = f"{px:.2f}"
                    r[6] = f"{px + 1:.2f}"
                    r[2] = "150,000,000" if last else "50,000,000"
                    r[4] = f"{int(px * float(r[2].replace(',', '')))}"
                if r[0] == "2330":     # 台積電：每天小漲 0.1%，不會過濾出來
                    px = 1000 * (1.001 ** k)
                    r[5] = r[6] = r[7] = r[8] = f"{px:.2f}"
            self._put(f"{ymd}_twse_quotes", q)
            t = json.loads(json.dumps(TWSE_T86))
            if k >= len(self.days) - 3:      # 最後 3 天長榮外資轉買
                for r in t["data"]:
                    if r[0] == "2603":
                        r[4] = "5,000,000"
            self._put(f"{ymd}_twse_inst", t)
            self._put(f"{ymd}_twse_margin", TWSE_MARGN)
            self._put(f"{ymd}_tpex_quotes", TPEX_QUOTES)
            self._put(f"{ymd}_tpex_inst", TPEX_INST)
            self._put(f"{ymd}_tpex_margin", TPEX_MARGIN)
        self._put("20260820_twse_quotes", HOLIDAY)
        self._put("20260820_tpex_quotes", HOLIDAY)

    def tearDown(self):
        self.tmp.cleanup()

    def _put(self, key, payload):
        with open(os.path.join(self.cache, key + ".json"), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)

    def test_load_history_skips_holiday_and_sorts(self):
        f = m.Fetcher(self.cache, sleep=0, verbose=False)
        uni, days = m.load_history(f, dt.date(2026, 9, 3), 25, ["twse", "tpex"], True, True)
        self.assertEqual(len(days), 25)
        self.assertNotIn("20260820", days)
        self.assertEqual(days, sorted(days))
        self.assertEqual(set(uni), {"2330", "2603", "3105"})
        self.assertEqual([b.date for b in uni["2603"].bars], days)
        self.assertEqual(uni["2603"].bars[-1].foreign, 5_000_000)
        self.assertEqual(uni["2603"].bars[-1].margin_chg, -1100)
        self.assertEqual(uni["3105"].market, "tpex")

    def test_evaluate_picks_breakout(self):
        f = m.Fetcher(self.cache, sleep=0, verbose=False)
        uni, _ = m.load_history(f, dt.date(2026, 9, 3), 25, ["twse", "tpex"], True, True)
        p = m.Params()
        hits = {s.code: m.evaluate(s, p) for s in uni.values()}
        self.assertIsNotNone(hits["2603"])
        self.assertIsNone(hits["2330"])       # 漲幅不足
        self.assertIsNone(hits["3105"])       # 價格不變 → 漲幅 0
        h = hits["2603"]
        self.assertTrue(h.breakout)
        self.assertEqual(h.inst_streak, 3)
        self.assertEqual(h.inst_today, 5000)
        self.assertGreater(h.vol_ratio, 2.5)
        self.assertAlmostEqual(h.chg_pct, (175 / 161.5 - 1) * 100, places=6)   # 前一日收盤 150 + 23*0.5

    def test_main_end_to_end_csv(self):
        out = os.path.join(self.cache, "out.csv")
        rc = m.main(["--date", "20260903", "--cache-dir", self.cache, "--sleep", "0", "--margin", "-q",
                     "--lookback", "25", "--out", out])
        self.assertEqual(rc, 0)
        with open(out, encoding="utf-8-sig") as fh:
            rows = fh.read().splitlines()
        self.assertEqual(len(rows), 2)
        self.assertIn("2603", rows[1])


if __name__ == "__main__":
    unittest.main()
