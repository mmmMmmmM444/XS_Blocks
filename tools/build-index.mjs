#!/usr/bin/env node
/**
 * 掃描 選股腳本 / 警示腳本 / 函數腳本 底下所有 .xs，
 * 產生 chrome-extension/data/scripts.json 供擴充功能 popup 搜尋與複製。
 *
 * 用法：node tools/build-index.mjs
 */
import { readdir, readFile, writeFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SOURCE_DIRS = ["選股腳本", "警示腳本", "函數腳本"];
const OUT = path.join(ROOT, "chrome-extension", "data", "scripts.json");

async function walk(dir) {
  const out = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...(await walk(full)));
    else if (entry.isFile() && entry.name.endsWith(".xs")) out.push(full);
  }
  return out;
}

function header(code, key) {
  const m = code.match(new RegExp(`^//\\s*${key}:\\s*(.*)$`, "m"));
  return m ? m[1].trim() : "";
}

function parse(relPath, code) {
  const parts = relPath.split(path.sep);
  const file = parts[parts.length - 1].replace(/\.xs$/, "");
  const idMatch = file.match(/^\[([^\]]+)\]\s*(.*)$/);
  const typeMatch = code.match(/^\{@type:(\w+)\}/);
  return {
    id: idMatch ? idMatch[1] : "",
    name: idMatch ? idMatch[2] : file,
    cat: parts[0] || "",
    sub: parts[1] || "",
    group: parts.length > 3 ? parts[2] : "",
    display: header(code, "顯示名稱"),
    freq: header(code, "執行頻率"),
    type: typeMatch ? typeMatch[1] : "",
    path: relPath.split(path.sep).join("/"),
    code,
  };
}

const items = [];
for (const dir of SOURCE_DIRS) {
  const files = await walk(path.join(ROOT, dir));
  for (const f of files.sort()) {
    const code = (await readFile(f, "utf8")).replace(/^﻿/, "");
    items.push(parse(path.relative(ROOT, f), code));
  }
}
items.sort((a, b) => a.path.localeCompare(b.path, "zh-Hant"));

const cats = {};
for (const it of items) cats[it.cat] = (cats[it.cat] || 0) + 1;

await mkdir(path.dirname(OUT), { recursive: true });
await writeFile(OUT, JSON.stringify({ generated: new Date().toISOString().slice(0, 10), count: items.length, cats, items }));
console.log(`wrote ${path.relative(ROOT, OUT)}: ${items.length} scripts`, cats);
