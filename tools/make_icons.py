#!/usr/bin/env python3
"""產生 chrome-extension/icons/icon{16,32,48,128}.png（純標準函式庫，不需 Pillow）。

圖示：深色圓角底 + 三根 K 棒（台股慣例：紅漲綠跌）。
用法：python3 tools/make_icons.py
"""
import struct
import zlib
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "chrome-extension" / "icons"
SIZES = (16, 32, 48, 128)
SS = 4  # 超取樣倍率，縮圖時做平均以得到平滑邊緣

BG = (15, 23, 42, 255)        # slate-900
RED = (239, 68, 68, 255)      # 漲
GREEN = (34, 197, 94, 255)    # 跌

# 以「相對於圖示邊長的比例」描述形狀：(x0, y0, x1, y1)
CANDLES = [
    # (顏色, 影線, 實體)
    (RED,   (0.23, 0.55, 0.27, 0.86), (0.18, 0.62, 0.32, 0.80)),
    (GREEN, (0.48, 0.30, 0.52, 0.70), (0.43, 0.36, 0.57, 0.60)),
    (RED,   (0.73, 0.12, 0.77, 0.56), (0.68, 0.18, 0.82, 0.46)),
]


def rounded_rect_mask(px, py, n, radius):
    """判斷像素 (px, py) 是否落在圓角正方形內。"""
    r = radius * n
    x = min(px, n - 1 - px)
    y = min(py, n - 1 - py)
    if x >= r or y >= r:
        return True
    dx, dy = r - x - 0.5, r - y - 0.5
    return dx * dx + dy * dy <= r * r


def render(size):
    n = size * SS
    canvas = [[(0, 0, 0, 0)] * n for _ in range(n)]
    for y in range(n):
        for x in range(n):
            if rounded_rect_mask(x, y, n, 0.22):
                canvas[y][x] = BG
    for color, wick, body in CANDLES:
        for rect in (wick, body):
            x0, y0, x1, y1 = (int(round(v * n)) for v in rect)
            for y in range(y0, y1):
                for x in range(x0, x1):
                    canvas[y][x] = color
    # 平均縮圖到目標尺寸
    rows = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            acc = [0, 0, 0, 0]
            for sy in range(SS):
                for sx in range(SS):
                    p = canvas[y * SS + sy][x * SS + sx]
                    for i in range(4):
                        acc[i] += p[i]
            row += bytes(v // (SS * SS) for v in acc)
        rows.append(bytes(row))
    return rows


def png_chunk(tag, data):
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def write_png(path, size, rows):
    raw = b"".join(b"\x00" + r for r in rows)
    png = (b"\x89PNG\r\n\x1a\n"
           + png_chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
           + png_chunk(b"IDAT", zlib.compress(raw, 9))
           + png_chunk(b"IEND", b""))
    path.write_bytes(png)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for size in SIZES:
        out = OUT_DIR / f"icon{size}.png"
        write_png(out, size, render(size))
        print(f"wrote {out.relative_to(OUT_DIR.parent.parent)} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
