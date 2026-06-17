#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate Stock Index from CSV File

Input:
  - Tushare format: data/stock_list_{a,hk,us}.csv
  - AkShare format: logs/stock_basic_*.csv

Output: apps/dsa-web/public/stocks.index.json

Usage:
    python3 scripts/generate_index_from_csv.py              # 預設使用 Tushare
    python3 scripts/generate_index_from_csv.py --source akshare
    python3 scripts/generate_index_from_csv.py --test       # 測試模式
"""

import argparse
import csv
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add the project root to sys.path.
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from pypinyin import lazy_pinyin, Style
    PYPINYIN_AVAILABLE = True
except ImportError:
    lazy_pinyin = None
    Style = None
    PYPINYIN_AVAILABLE = False


def require_pypinyin() -> bool:
    """Ensure pypinyin is available before generating autocomplete assets."""
    if PYPINYIN_AVAILABLE:
        return True

    print("[Error] pypinyin not available; cannot generate stock autocomplete index.")
    print("[Info] Install dependencies with: pip install -r requirements.txt")
    return False


def load_csv_data(csv_path: Path) -> List[Dict[str, Any]]:
    """
    Load stock data from AkShare format CSV file

    Args:
        csv_path: CSV file path

    Returns:
        List of stock data
    """
    stocks = []

    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)

        for row in reader:
            ts_code = row['ts_code'].strip()
            symbol = row['symbol'].strip()
            name = row['name'].strip()

            # Skip invalid rows.
            if not ts_code or not symbol or not name:
                continue

            stocks.append({
                'ts_code': ts_code,
                'symbol': symbol,
                'name': name,
                'area': row.get('area', ''),
                'industry': row.get('industry', ''),
                'list_date': row.get('list_date', ''),
            })

    return stocks


def load_tushare_data(data_dir: Path) -> List[Dict[str, Any]]:
    """
    從 Tushare CSV 檔案載入三個市場的股票資料

    Args:
        data_dir: 資料目錄路徑

    Returns:
        合併後的股票列表
    """
    all_stocks = []
    market_files = {
        'CN': data_dir / 'stock_list_a.csv',
        'HK': data_dir / 'stock_list_hk.csv',
        'US': data_dir / 'stock_list_us.csv',
    }

    for market_name, csv_file in market_files.items():
        if not csv_file.exists():
            print(f"[Warning] 未找到檔案：{csv_file}")
            continue

        print(f"  正在讀取 {market_name} 市場資料：{csv_file.name}")

        try:
            file_stocks = []
            selected_us_stocks: Dict[str, tuple[Dict[str, Any], int]] = {}
            with open(csv_file, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)

                for row in reader:
                    # 傳入市場引數以最佳化判斷（對於特殊格式如 DUMMY）
                    parsed = parse_stock_row(row, market_name)
                    if not parsed:
                        continue

                    if market_name == 'US':
                        # Tushare us_basic may include historical rows for a reused ticker.
                        # Keep one deterministic row per ts_code before generating the index.
                        delist_priority = get_us_delist_priority(row)
                        existing = selected_us_stocks.get(parsed['ts_code'])
                        if existing is None or delist_priority > existing[1]:
                            selected_us_stocks[parsed['ts_code']] = (parsed, delist_priority)
                        continue

                    if parsed:
                        all_stocks.append(parsed)
                        file_stocks.append(parsed)

            if market_name == 'US':
                file_stocks = [item for item, _priority in selected_us_stocks.values()]
                all_stocks.extend(file_stocks)

            print(f"    ✓ {market_name} 市場讀取完成：{len(file_stocks)} 只股票")

        except Exception as e:
            print(f"    [Error] 讀取 {csv_file.name} 失敗：{e}")

    return all_stocks


def get_us_delist_priority(row: Dict[str, str]) -> int:
    """
    為複用 ticker 的美股記錄生成去重優先順序。

    Tushare us_basic 匯出的 delist_date 對當前記錄並不總是穩定：
    - 空字串通常表示當前仍在使用的 ticker
    - ``NaT`` 多見於歷史記錄或日期佔位值
    - 實際日期表示明確退市

    因此前置去重時優先選擇：
    1. delist_date 為空
    2. delist_date 為 NaT
    3. delist_date 為實際日期

    同優先順序時保留 CSV 中最先出現的記錄，避免在資訊不足時隨意切換名稱。
    """
    delist_date = (row.get('delist_date') or '').strip()
    if not delist_date:
        return 2
    if delist_date.upper() == 'NAT':
        return 1
    return 0


def load_akshare_data(logs_dir: Path) -> List[Dict[str, Any]]:
    """
    從 AkShare CSV 檔案載入股票資料

    Args:
        logs_dir: 日誌目錄路徑

    Returns:
        股票列表

    說明：
        AkShare 這條輸入路徑保留其原始 name 欄位，不額外套用
        Tushare A 股那套 XD / XR / DR 狀態字首修正邏輯。這裡的目標是
        複用 AkShare 已輸出的展示名，而不是對其做二次歸一化。
    """
    csv_files = list(logs_dir.glob("stock_basic_*.csv"))

    if not csv_files:
        print("[Error] 未找到 CSV 檔案：logs/stock_basic_*.csv")
        return []

    # 使用最新的 CSV 檔案
    csv_file = sorted(csv_files)[-1]
    print(f"  正在讀取 AkShare 資料：{csv_file.name}")

    stocks = []
    with open(csv_file, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)

        for row in reader:
            ts_code = row['ts_code'].strip()
            symbol = row['symbol'].strip()
            name = row['name'].strip()

            # Skip invalid rows.
            if not ts_code or not symbol or not name:
                continue

            stocks.append({
                'ts_code': ts_code,
                'symbol': symbol,
                'name': name,
                'area': row.get('area', ''),
                'industry': row.get('industry', ''),
                'list_date': row.get('list_date', ''),
            })

    print(f"    ✓ 共讀取 {len(stocks)} 只股票")
    return stocks


def generate_pinyin(name: str) -> tuple:
    """
    Generate pinyin for stock name

    Args:
        name: Stock name

    Returns:
        Tuple of (pinyin_full, pinyin_abbr)
    """
    if not PYPINYIN_AVAILABLE:
        raise RuntimeError("pypinyin is required to generate stock autocomplete index")

    try:
        normalized_name = normalize_name_for_pinyin(name)

        # Full pinyin spelling.
        py_full = lazy_pinyin(normalized_name, style=Style.NORMAL)
        pinyin_full = ''.join(py_full)

        # Pinyin abbreviation.
        py_abbr = lazy_pinyin(normalized_name, style=Style.FIRST_LETTER)
        pinyin_abbr = ''.join(py_abbr)

        return (pinyin_full, pinyin_abbr)
    except Exception as e:
        print(f"[Warning] Failed to generate pinyin for {name}: {e}")
        return (None, None)


def normalize_name_for_pinyin(name: str) -> str:
    """
    Normalize stock name to avoid special prefixes and full-width characters polluting pinyin index

    Args:
        name: Original stock name

    Returns:
        Normalized name for pinyin generation
    """
    normalized = unicodedata.normalize('NFKC', name).strip()

    # Strip common A-share prefixes while preserving the core name.
    normalized = re.sub(r'^(?:\*?ST|N)+', '', normalized, flags=re.IGNORECASE)

    return normalized.strip() or unicodedata.normalize('NFKC', name).strip()


def normalize_stock_name_for_index(name: str, market: str) -> str:
    """
    Normalize stock names before writing the long-lived autocomplete index.

    For A-shares (including BSE), ``XD``/``XR``/``DR`` are
    ex-dividend/ex-rights trading-day prefixes. They should not be stored in
    the official static index because they can become stale almost immediately.
    New-stock prefixes such as ``N``/``C`` and risk-warning prefixes such as
    ``ST``/``*ST`` are preserved; they should be refreshed by the next
    stock-list update.
    """
    normalized = unicodedata.normalize('NFKC', str(name or '')).strip()
    if market in {'CN', 'BSE'}:
        normalized = re.sub(r'^(?:XD|XR|DR)\s*', '', normalized, flags=re.IGNORECASE)
    return normalized.strip()


def extract_symbol_from_ts_code(ts_code: str, market: str) -> Optional[str]:
    """
    從 ts_code 提取 displayCode

    - A股：000001.SZ → 000001
    - 港股：00700.HK → 00700
    - 美股：AAPL → AAPL

    Args:
        ts_code: TS程式碼
        market: 市場程式碼

    Returns:
        displayCode 或 None
    """
    if not ts_code:
        return None

    if market == 'US':
        # 美股無字尾，直接返回
        return ts_code

    if '.' in ts_code:
        # A股和港股：去除字尾
        return ts_code.split('.')[0]

    return ts_code


def get_stock_name(row: Dict[str, str], market: str) -> Optional[str]:
    """
    獲取股票名稱

    - A股/港股：使用 name 欄位
    - 美股：使用 enname 欄位（英文名稱）

    Args:
        row: CSV 行資料
        market: 市場程式碼

    Returns:
        股票名稱或 None
    """
    if market == 'US':
        # 美股使用英文名稱
        name = row.get('enname', '').strip()
        return name if name else None
    else:
        # A股和港股使用中文名稱
        name = row.get('name', '').strip()
        name = normalize_stock_name_for_index(name, market)
        return name if name else None


def parse_stock_row(row: Dict[str, str], preferred_market: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    解析單行股票資料

    - 美股 DUMMY 過濾（嚴格過濾）
    - 空值校驗
    - 自動判斷市場型別（當無法判斷時使用 preferred_market）
    - 返回統一格式的字典

    Args:
        row: CSV 行資料
        preferred_market: 當 ts_code 無法判斷市場時使用（如美股 DUMMY 記錄）

    Returns:
        解析後的股票字典，無效資料返回 None
    """
    ts_code = row.get('ts_code', '').strip()

    if not ts_code:
        return None

    # 自動判斷市場型別
    market = determine_market(ts_code)

    # 如果 ts_code 沒有字尾（無法準確判斷），且提供了 preferred_market，則使用它
    # 這主要用於處理美股的特殊格式（如 DUMMY 記錄）
    if '.' not in ts_code and preferred_market:
        market = preferred_market

    # 美股特殊處理：嚴格過濾 DUMMY 記錄
    if market == 'US':
        enname = row.get('enname', '').strip()
        if not enname or 'DUMMY' in enname.upper():
            return None

    # 獲取股票名稱
    name = get_stock_name(row, market)
    if not name:
        return None

    # 提取 displayCode
    display_code = extract_symbol_from_ts_code(ts_code, market)
    if not display_code:
        return None

    return {
        'ts_code': ts_code,
        'symbol': display_code,
        'name': name,
        'market': market,
    }


def determine_market(ts_code: str) -> str:
    """
    Determine market based on code

    Args:
        ts_code: Trading code (e.g., 000001.SZ, AAPL, BRK.B, GOOG.A)

    Returns:
        Market code (CN, HK, US, BSE)
    """
    if '.' in ts_code:
        # 有字尾的情況
        suffix = ts_code.split('.')[1]
        # 檢查是否為中國市場字尾
        if suffix in ['SH', 'SZ']:
            return 'CN'
        elif suffix == 'HK':
            return 'HK'
        elif suffix == 'BJ':
            return 'BSE'
        # 有字尾但不是中國市場字尾，檢查是否為美股
        # 美股可能有點號字尾（如 BRK.B, GOOG.A, AAPL.U）
        prefix = ts_code.split('.')[0]
        if prefix.isalpha():
            return 'US'
    else:
        # 無字尾的情況
        # 純字母程式碼為美股
        if ts_code.isalpha():
            return 'US'

    # 預設為 A股
    return 'CN'


def generate_aliases(name: str, market: str) -> List[str]:
    """
    Generate stock aliases

    Args:
        name: Stock name
        market: Market code

    Returns:
        List of aliases
    """
    aliases = []

    # A股常見別名
    cn_alias_map = {
        '貴州茅臺': ['茅臺'],
        '中國平安': ['平安'],
        '平安銀行': ['平銀'],
        '招商銀行': ['招行'],
        '五糧液': ['五糧'],
        '寧德時代': ['寧德'],
        '比亞迪': ['比亞'],
        '工商銀行': ['工行'],
        '建設銀行': ['建行'],
        '農業銀行': ['農行'],
        '中國銀行': ['中行'],
        '交通銀行': ['交行'],
        '興業銀行': ['興業'],
        '浦發銀行': ['浦發'],
        '民生銀行': ['民生'],
        '中信證券': ['中信'],
        '東方財富': ['東財'],
        '海康威視': ['海康'],
        '隆基綠能': ['隆基'],
        '中國神華': ['神華'],
        '長江電力': ['長電'],
        '中國石化': ['石化'],
        '中國石油': ['石油'],
    }

    # 港股常見別名
    hk_alias_map = {
        '騰訊控股': ['騰訊', 'Tencent'],
        '阿里巴巴-SW': ['阿里', '阿里巴巴', 'Alibaba'],
        '美團-W': ['美團', 'Meituan'],
        '小米集團-W': ['小米', 'Xiaomi'],
        '京東集團-SW': ['京東', 'JD'],
        '網易-S': ['網易', 'NetEase'],
        '百度集團-SW': ['百度', 'Baidu'],
        '中芯國際': ['中芯', 'SMIC'],
        '中國移動': ['中移動', 'China Mobile'],
        '中國海洋石油': ['中海油', 'CNOOC'],
    }

    # 美股常見別名
    us_alias_map = {
        'Apple Inc.': ['Apple', 'AAPL'],
        'Microsoft Corporation': ['Microsoft', 'MSFT'],
        'Amazon.com, Inc.': ['Amazon', 'AMZN'],
        'Tesla Inc.': ['Tesla', 'TSLA'],
        'Meta Platforms, Inc.': ['Meta', 'Facebook', 'META'],
        'Alphabet Inc.': ['Google', 'Alphabet', 'GOOGL'],
        'NVIDIA Corporation': ['NVIDIA', 'NVDA'],
        'Netflix Inc.': ['Netflix', 'NFLX'],
        'Intel Corporation': ['Intel', 'INTC'],
        'Advanced Micro Devices': ['AMD', 'AMD'],
    }

    # 根據市場選擇對映表
    if market == 'CN':
        alias_map = cn_alias_map
    elif market == 'HK':
        alias_map = hk_alias_map
    elif market == 'US':
        alias_map = us_alias_map
    else:
        alias_map = {}

    if name in alias_map:
        aliases.extend(alias_map[name])

    return aliases


def build_stock_index(stocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Build the stock index.

    Args:
        stocks: Raw stock rows（已包含 market 欄位）

    Returns:
        Stock index entries
    """
    index = []

    for stock in stocks:
        ts_code = stock['ts_code']
        symbol = stock['symbol']
        name = stock['name']
        market = stock.get('market', 'CN')  # 優先使用已解析的市場，否則從 ts_code 判斷

        # 如果沒有 market 欄位，從 ts_code 判斷
        if market == 'CN' and '.' not in ts_code:
            market = determine_market(ts_code)

        # Generate pinyin fields.
        pinyin_full, pinyin_abbr = generate_pinyin(name)

        # Generate aliases.
        aliases = generate_aliases(name, market)

        index.append({
            "canonicalCode": ts_code,    # Example: 000001.SZ, AAPL
            "displayCode": symbol,       # Example: 000001, AAPL
            "nameZh": name,
            "pinyinFull": pinyin_full,
            "pinyinAbbr": pinyin_abbr,
            "aliases": aliases,
            "market": market,
            "assetType": "stock",
            "active": True,
            "popularity": 100,
        })

    return index


def compress_index(index: List[Dict[str, Any]]) -> List[List]:
    """
    壓縮索引為陣列格式以減少檔案大小

    Args:
        index: 原始索引

    Returns:
        壓縮後的索引
    """
    compressed = []
    for item in index:
        compressed.append([
            item["canonicalCode"],
            item["displayCode"],
            item["nameZh"],
            item.get("pinyinFull"),
            item.get("pinyinAbbr"),
            item.get("aliases", []),
            item["market"],
            item["assetType"],
            item["active"],
            item.get("popularity", 0),
        ])
    return compressed


def main():
    """主函式"""
    parser = argparse.ArgumentParser(description='從 CSV 生成股票自動補全索引')
    parser.add_argument(
        '--source',
        choices=['tushare', 'akshare'],
        default='tushare',
        help='資料來源選擇（預設: tushare）'
    )
    parser.add_argument(
        '--test', '-t',
        action='store_true',
        help='測試模式：只驗證不寫入檔案'
    )
    args = parser.parse_args()

    print("=" * 60)
    print("股票索引生成工具（從 CSV）")
    print("=" * 60)
    print(f"資料來源：{args.source}")

    if not require_pypinyin():
        return 1

    # 載入資料
    print("\n[1/5] 讀取 CSV 資料...")
    if args.source == 'tushare':
        data_dir = Path(__file__).parent.parent / 'data'
        stocks = load_tushare_data(data_dir)
    elif args.source == 'akshare':
        logs_dir = Path(__file__).parent.parent / 'logs'
        stocks = load_akshare_data(logs_dir)
    else:
        print(f"[Error] 不支援的資料來源：{args.source}")
        return 1

    if not stocks:
        print("[Error] 未載入到任何股票資料")
        return 1

    print(f"      共讀取 {len(stocks)} 只股票")

    print("\n[2/5] 生成索引資料...")
    index = build_stock_index(stocks)

    # 輸出路徑
    output_path = (
        Path(__file__).parent.parent / "apps" / "dsa-web" / "public" / "stocks.index.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print("\n[3/5] 壓縮索引資料...")
    compressed = compress_index(index)

    if args.test:
        print("\n[4/5] 測試模式：跳過寫入檔案")
        print(f"      輸出路徑：{output_path}")

        # 驗證資料
        print("\n[5/5] 驗證資料...")
        print(f"      壓縮前：{len(index)} 條記錄")
        print(f"      壓縮後：{len(compressed)} 條記錄")

        # 顯示前5條示例
        if compressed:
            print("\n      前5條示例：")
            for i, item in enumerate(compressed[:5]):
                print(f"        {i + 1}. {item}")
    else:
        print(f"\n[4/5] 寫入檔案：{output_path}")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('[\n')
            for i, item in enumerate(compressed):
                json.dump(item, f, ensure_ascii=False, separators=(',', ':'))
                if i < len(compressed) - 1:
                    f.write(',\n')
                else:
                    f.write('\n')
            f.write(']\n')

        file_size = output_path.stat().st_size
        print(f"      檔案大小：{file_size / 1024:.2f} KB")

        # 驗證檔案
        print("\n[5/5] 驗證檔案...")
        with open(output_path, 'r', encoding='utf-8') as f:
            test_data = json.load(f)
            print(f"      驗證透過：{len(test_data)} 條記錄")

    # 統計資訊
    market_stats = {}
    for item in index:
        market = item['market']
        market_stats[market] = market_stats.get(market, 0) + 1

    print(f"\n{'=' * 60}")
    print("生成完成！市場分佈：")
    for market, count in sorted(market_stats.items()):
        print(f"  - {market}: {count} 只")
    print(f"{'=' * 60}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
