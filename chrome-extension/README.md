# XS 量化積木腳本集 — Chrome 擴充功能

在瀏覽器工具列一鍵搜尋本 repo 內 3,431 條 XS 腳本（選股 / 警示 / 函數），點開即看原始碼，按「複製程式碼」貼進 XQ 的 XS 編輯器。

Manifest V3，無背景 service worker、無 content script、不連任何外部服務；唯一的權限是 `clipboardWrite`（複製程式碼用）。

## 目錄

```
chrome-extension/
├── manifest.json        # 名稱、版號、icon、popup 設定
├── popup.html           # 工具列圖示點開的畫面
├── popup.css
├── popup.js             # 搜尋、鍵盤操作、複製
├── icons/icon{16,32,48,128}.png   # 由 tools/make_icons.py 產生
└── data/scripts.json    # 由 tools/build-index.mjs 從 ../選股腳本 等目錄產生
```

## 本機載入（Load unpacked）

1. 網址列輸入 `chrome://extensions`。
2. 右上角打開「開發人員模式」。
3. 按「載入未封裝項目」，選擇本 repo 的 `chrome-extension/` 目錄。
4. 點工具列拼圖圖示，把「XS 量化積木腳本集」釘選到工具列。

### 操作

| 動作 | 方式 |
|---|---|
| 搜尋 | 輸入代號（如 `E0030`）、名稱或顯示名稱，多個關鍵字用空白分隔，全部命中才列出 |
| 篩選類別 | 右上下拉：全部 / 選股 / 警示 / 函數 |
| 移動與開啟 | `↑` `↓` 選取，`Enter` 開啟 |
| 複製整段程式碼 | 「複製程式碼」按鈕或 `Ctrl+Enter` |
| 返回列表 | `Esc` |
| 在 GitHub 開啟原檔 | 詳細頁的「路徑」連結 |

上次的關鍵字與類別會記住在 popup 的 `localStorage`。

## 改完程式碼後要不要重新載入？

| 改到的檔案 | 需要到 chrome://extensions 按重新整理 |
|---|---|
| `manifest.json` | 要 |
| `popup.html` / `popup.css` / `popup.js` | 不用，關掉 popup 再打開即可 |
| `data/scripts.json`（重跑索引後） | 不用，關掉 popup 再打開即可 |

## 看 log 與錯誤

- 在 popup 上按右鍵 →「檢查」→ Console，可看到 `popup.js` 一開始印的 `This is a popup!` 以及載入錯誤。
- 語法錯誤會出現在 `chrome://extensions` 該項目的「錯誤」按鈕內。

## 腳本更新後重建索引

repo 內的 `.xs` 有增減或修改時，重新產生索引：

```bash
node tools/build-index.mjs
```

會掃描 `選股腳本/`、`警示腳本/`、`函數腳本/` 底下所有 `.xs`，解析檔名的 `[代號]名稱` 與檔頭的 `顯示名稱`、`執行頻率`、`{@type:...}`，寫入 `data/scripts.json`。

## 打包上架 Chrome Web Store

```bash
bash tools/package.sh
```

流程：重建索引 → 重畫 icon → 把 `chrome-extension/` 內容壓成 `dist/xs-blocks-extension-v<版號>.zip`，`manifest.json` 位於 ZIP 根目錄。

上傳前檢查：

- `manifest.json` 的 `version` 每次上傳都必須比上一版大（目前 `0.0.0.1`）。上架後 manifest 內容無法在後台修改，只能改檔、升版號、重新打包。
- `description` 上限 132 字元（目前 47）。
- `icons` 已含 16 / 32 / 48 / 128。
- 商店頁面另需 128×128 商店圖示、至少一張 1280×800 或 640×400 截圖、簡短說明與隱私聲明；本擴充功能不蒐集任何資料。

`dist/` 已加入 `.gitignore`。
