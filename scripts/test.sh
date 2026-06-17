#!/bin/bash
# ===================================
# A股/港股/美股 智慧分析系統 - 測試指令碼
# ===================================
#
# 使用方法：
#   ./scripts/test.sh [測試場景]
#
# 測試場景：
#   market      - 僅大盤覆盤
#   a-stock     - A股個股分析（茅臺、平安銀行）
#   etf         - etf分析(衛星etf 563230)
#   hk-stock    - 港股分析（騰訊、阿里）
#   us-stock    - 美股分析（蘋果、特斯拉）
#   mixed       - 混合市場分析
#   single      - 單股模式測試
#   dry-run     - 僅獲取資料不分析
#   full        - 完整流程測試
#   quick       - 快速測試（單隻股票）
#   all         - 執行所有測試
#
# 示例：
#   ./scripts/test.sh market      # 測試大盤覆盤
#   ./scripts/test.sh us-stock    # 測試美股分析
#   ./scripts/test.sh quick       # 快速測試
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$REPO_ROOT"

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 列印帶顏色的資訊
info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

header() {
    echo ""
    echo "=============================================="
    echo -e "${GREEN}$1${NC}"
    echo "=============================================="
    echo ""
}

# 檢查Python環境
check_python() {
    if ! command -v python3 &> /dev/null; then
        error "Python3 未安裝"
        exit 1
    fi
    info "Python版本: $(python3 --version)"
}

# 檢查依賴
check_deps() {
    info "檢查依賴..."
    python3 -c "import yfinance" 2>/dev/null || { warn "yfinance 未安裝，美股測試可能失敗"; }
    python3 -c "import akshare" 2>/dev/null || { warn "akshare 未安裝，A股/港股測試可能失敗"; }
    success "依賴檢查完成"
}

# ==================== 測試場景 ====================

# 測試1: 大盤覆盤
test_market() {
    header "測試場景: 大盤覆盤"
    info "執行大盤覆盤分析..."
    python3 main.py --market-review "$@"
    success "大盤覆盤測試完成"
}

# 測試2: A股分析
test_a_stock() {
    header "測試場景: A股分析"
    info "分析A股: 600519(茅臺), 000001(平安銀行)"
    python3 main.py --stocks 600519,000001  --no-market-review "$@"
    success "A股分析測試完成"
}

# 測試2.5: ETF分析
test_etf() {
    header "測試場景: ETF分析"
    info "分析ETF: 563230(衛星ETF)"
    python3 main.py --stocks 563230,512400 --no-market-review "$@"
    success "ETF分析測試完成"
}

# 測試3: 港股分析
test_hk_stock() {
    header "測試場景: 港股分析"
    info "分析港股: hk00700(騰訊), hk09988(阿里)"
    python3 main.py --stocks hk00700,hk09988 --no-market-review "$@"
    success "港股分析測試完成"
}

# 測試4: 美股分析
test_us_stock() {
    header "測試場景: 美股分析"
    info "分析美股: AAPL(蘋果), TSLA(特斯拉)"
    # 允許透傳引數，預設不帶 --no-notify
    python3 main.py --stocks AAPL --no-market-review "$@"
    success "美股分析測試完成"
}

# 測試5: 混合市場
test_mixed() {
    header "測試場景: 混合市場分析"
    info "分析混合市場: 600519(A股), hk00700(港股), AAPL(美股)"
    python3 main.py --stocks 600519,hk00700,AAPL --no-market-review
    success "混合市場測試完成"
}

# 測試6: 單股推送模式
test_single() {
    header "測試場景: 單股推送模式"
    info "測試單股推送模式..."
    python3 main.py --stocks 600519 --single-notify --no-market-review
    success "單股推送模式測試完成"
}

# 測試7: dry-run模式
test_dry_run() {
    header "測試場景: Dry-Run 模式"
    info "僅獲取資料，不進行AI分析..."
    python3 main.py --stocks 600519,AAPL --dry-run --no-notify
    success "Dry-Run 測試完成"
}

# 測試8: 完整流程
test_full() {
    header "測試場景: 完整流程"
    info "執行完整分析流程（個股+大盤）..."
    python3 main.py --stocks 600519 --no-notify
    success "完整流程測試完成"
}

# 測試9: 快速測試
test_quick() {
    header "測試場景: 快速測試"
    info "單隻股票快速測試..."
    python3 main.py --stocks 600519 --no-market-review --no-notify "$@"
    success "快速測試完成"
}

# 測試10: 程式碼識別測試
test_code_recognition() {
    header "測試場景: 程式碼識別"
    info "測試股票程式碼識別邏輯..."

    python3 << 'PYTEST'
import sys
sys.path.insert(0, '.')
from data_provider.akshare_fetcher import _is_hk_code, _is_us_code

test_cases = [
    # (程式碼, 預期HK, 預期US, 描述)
    ("AAPL", False, True, "美股-蘋果"),
    ("TSLA", False, True, "美股-特斯拉"),
    ("BRK.B", False, True, "美股-伯克希爾B"),
    ("hk00700", True, False, "港股-騰訊"),
    ("HK09988", True, False, "港股-阿里"),
    ("600519", False, False, "A股-茅臺"),
    ("000001", False, False, "A股-平安"),
]

print("\n股票程式碼識別測試:")
print("-" * 60)
all_pass = True
for code, exp_hk, exp_us, desc in test_cases:
    is_hk = _is_hk_code(code)
    is_us = _is_us_code(code)
    hk_ok = is_hk == exp_hk
    us_ok = is_us == exp_us
    status = "✅" if (hk_ok and us_ok) else "❌"
    all_pass = all_pass and hk_ok and us_ok
    print(f"{status} {code:10} | HK:{is_hk:5} US:{is_us:5} | {desc}")

print("-" * 60)
print(f"{'✅ 所有測試透過!' if all_pass else '❌ 有測試失敗!'}")
sys.exit(0 if all_pass else 1)
PYTEST

    success "程式碼識別測試完成"
}

# 測試11: YFinance程式碼轉換測試
test_yfinance_convert() {
    header "測試場景: YFinance 程式碼轉換"
    info "測試YFinance程式碼轉換邏輯..."

    python3 << 'PYTEST'
import sys
sys.path.insert(0, '.')
from data_provider.yfinance_fetcher import YfinanceFetcher

fetcher = YfinanceFetcher()

test_cases = [
    ("AAPL", "AAPL", "美股"),
    ("tsla", "TSLA", "美股小寫"),
    ("BRK.B", "BRK.B", "美股特殊"),
    ("hk00700", "0700.HK", "港股"),
    ("HK09988", "9988.HK", "港股大寫"),
    ("600519", "600519.SS", "A股滬市"),
    ("000001", "000001.SZ", "A股深市"),
    ("300750", "300750.SZ", "A股創業板"),
]

print("\nYFinance 程式碼轉換測試:")
print("-" * 60)
all_pass = True
for input_code, expected, desc in test_cases:
    result = fetcher._convert_stock_code(input_code)
    status = "✅" if result == expected else "❌"
    all_pass = all_pass and (result == expected)
    print(f"{status} {input_code:10} -> {result:12} (期望: {expected:12}) | {desc}")

print("-" * 60)
print(f"{'✅ 所有測試透過!' if all_pass else '❌ 有測試失敗!'}")
sys.exit(0 if all_pass else 1)
PYTEST

    success "YFinance 程式碼轉換測試完成"
}

# 測試12: 語法檢查
test_syntax() {
    header "測試場景: Python 語法檢查"
    info "檢查所有Python檔案語法..."

    python3 -m py_compile main.py src/config.py src/notification.py \
        data_provider/akshare_fetcher.py \
        data_provider/yfinance_fetcher.py \
        bot/commands/analyze.py

    success "語法檢查透過"
}

# 測試13: Flake8 靜態檢查
test_flake8() {
    header "測試場景: Flake8 靜態檢查"
    info "執行 Flake8 檢查嚴重錯誤..."

    if command -v flake8 &> /dev/null; then
        flake8 main.py src/config.py src/notification.py --select=F821,E999 --max-line-length=120
        success "Flake8 檢查透過"
    else
        warn "Flake8 未安裝，跳過檢查"
    fi
}

# 執行所有測試
test_all() {
    header "執行所有測試"

    test_syntax
    test_code_recognition
    test_yfinance_convert
    test_flake8

    echo ""
    info "以下測試需要網路和API配置，可能會失敗:"
    echo ""

    test_dry_run || warn "Dry-Run 測試失敗（可能是網路問題）"
    test_quick || warn "快速測試失敗（可能是API問題）"

    success "所有測試完成!"
}

# ==================== 主程式 ====================

main() {
    header "A股/港股/美股 智慧分析系統 - 測試"

    check_python
    check_deps

    case "${1:-help}" in
        market)
            shift
            test_market "$@"
            ;;
        a-stock|a_stock|astock)
            shift
            test_a_stock "$@"
            ;;
        etf)
            shift
            test_etf "$@"
            ;;
        hk-stock|hk_stock|hkstock|hk)
            shift
            test_hk_stock "$@"
            ;;
        us-stock|us_stock|usstock|us)
            shift
            test_us_stock "$@"
            ;;
        mixed|mix)
            shift
            test_mixed "$@"
            ;;
        single)
            shift
            test_single "$@"
            ;;
        dry-run|dryrun|dry)
            shift
            test_dry_run "$@"
            ;;
        full)
            shift
            test_full "$@"
            ;;
        quick|q)
            shift
            test_quick "$@"
            ;;
        code|recognition)
            shift
            test_code_recognition "$@"
            ;;
        yfinance|yf)
            shift
            test_yfinance_convert "$@"
            ;;
        syntax)
            shift
            test_syntax "$@"
            ;;
        flake8|lint)
            shift
            test_flake8 "$@"
            ;;
        all)
            shift
            test_all "$@"
            ;;
        help|--help|-h|*)
            echo "使用方法: $0 [測試場景]"
            echo ""
            echo "測試場景:"
            echo "  market      - 僅大盤覆盤"
            echo "  a-stock     - A股個股分析"
            echo "  etf         - ETF分析"
            echo "  hk-stock    - 港股分析"
            echo "  us-stock    - 美股分析"
            echo "  mixed       - 混合市場分析"
            echo "  single      - 單股推送模式"
            echo "  dry-run     - 僅獲取資料"
            echo "  full        - 完整流程"
            echo "  quick       - 快速測試（推薦）"
            echo "  code        - 程式碼識別測試"
            echo "  yfinance    - YFinance轉換測試"
            echo "  syntax      - 語法檢查"
            echo "  flake8      - 靜態檢查"
            echo "  all         - 執行所有測試"
            echo ""
            echo "示例:"
            echo "  $0 quick     # 快速測試"
            echo "  $0 us-stock  # 測試美股"
            echo "  $0 code      # 測試程式碼識別"
            echo "  $0 all       # 執行所有測試"
            ;;
    esac
}

main "$@"
