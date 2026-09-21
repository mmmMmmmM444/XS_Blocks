# 量化積木腳本集

## 腳本結構說明

提供量化積木系統內建條件的原始碼.

程式碼分成以下幾個目錄:

- 選股腳本: 放置的是盤後條件的腳本, 可以把內容匯入XS選股腳本, 依照條件說明, 設定選股策略
- 警示腳本: 放置的是即時條件的腳本, 可以把內容匯入XS警示腳本, 依照條件說明, 設定警示雷達
- 函數腳本: 放置的是盤後選股的排行榜條件, 可以把內容匯入XS函數區, 以排行條件的方式加入選股策略

## Chrome 擴充功能

`chrome-extension/` 內有一個 Manifest V3 的 Chrome 擴充功能, 可在瀏覽器工具列直接搜尋全部腳本並複製程式碼貼進 XS 編輯器. 載入方式、重建索引與上架打包步驟見 [chrome-extension/README.md](chrome-extension/README.md).

## 盤後動能選股腳本 tw_eod_scan.py

`tw_eod_scan.py` 是獨立的 Python 3 腳本, 只用標準函式庫, 直接抓證交所與櫃買中心的公開 JSON(行情、三大法人、融資融券), 以量價加籌碼條件掃出隔日短線候選股, 條件對應本 repo 的 XS 積木代號(P0020 漲跌幅、P0030 爆量、B0010 外資、B0020 投信 等).

```bash
python3 tw_eod_scan.py                       # 最近一個交易日, 上市+上櫃
python3 tw_eod_scan.py --date 20260903 --margin --top 30
python3 tw_eod_scan.py --min-chg 5 --vol-ratio 2 --no-breakout
python3 tw_eod_scan.py --list-conditions     # 條件與對應的 XS 積木
python3 tw_eod_scan.py --demo                # 不連網, 隨機資料跑流程
python3 -m unittest tests.test_tw_eod_scan   # 離線測試
```

每日原始資料快取在 `~/.tw_eod_cache`, 隔天只補抓最新一天. 結果印在終端並輸出 `scan_<日期>.csv`, 加 `--json` 可給其他程式接.

## 如何檢視程式碼



建議安裝[VSCode](https://code.visualstudio.com/).

把repo複製到本機端之後, 使用VSCode, 開啟目錄即可檢視程式碼.

另外也建議安裝[xs程式碼的外掛](https://marketplace.visualstudio.com/items?itemName=sysjust-xq.xs), VSCode就可以依照XS語法自動調整顯示的顏色.


