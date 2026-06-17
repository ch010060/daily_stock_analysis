import { describe, expect, it } from 'vitest';
import { markdownToPlainText } from '../markdown';

/**
 * Stock report specific tests for markdownToPlainText
 * Tests real-world stock analysis report scenarios
 */
describe('markdownToPlainText - Stock Report Scenarios', () => {
  it('handles typical Chinese stock report with tables and indicators', () => {
    const stockReport = `# 貴州茅臺 (600519) 分析報告

## 技術分析

| 指標 | 當前值 | 訊號 |
|------|--------|------|
| MA5 | 1680.50 | 🟢 |
| MA10 | 1675.30 | 🟢 |
| MA20 | 1665.80 | 🟢 |

**MACD**: 金叉訊號，買進參考
**RSI**: 56.8，處於中性區域

## 基本面分析

- **市盈率**: 28.5
- **市淨率**: 8.2
- **營收增長**: +15.3% YoY

> 風險提示：短期波動加大，建議控制部位

## 操作建議

\`\`\`python
# 推薦買進區間
entry_zone = [1650, 1680]
stop_loss = 1620
target = 1750
\`\`\`

[檢視詳細資料](https://example.com/stock/600519)`;

    const result = markdownToPlainText(stockReport);

    // Verify key content is preserved
    expect(result).toContain('貴州茅臺');
    expect(result).toContain('600519');
    expect(result).toContain('技術分析');
    expect(result).toContain('MACD');
    expect(result).toContain('金叉訊號');
    expect(result).toContain('市盈率');
    expect(result).toContain('風險提示');
    expect(result).toContain('entry_zone');
    expect(result).toContain('檢視詳細資料');

    // Verify markdown symbols are removed
    expect(result).not.toMatch(/^#{1,6}\s+/m);
    expect(result).not.toMatch(/\*\*[^*]+\*\*/);
    // Note: remove-markdown preserves table structure with pipe characters
    // This is a known limitation - tables remain pipe-separated
  });

  it('handles Hong Kong stock report with English and Chinese mix', () => {
    const hkReport = `# Tencent (00700.HK) Technical Analysis

## Key Indicators

* **Current Price**: HKD 368.20
* **Change**: +2.5% 📈
* **Volume**: 18.2M

## Support & Resistance

1. **Resistance 1**: HKD 375.00
2. **Resistance 2**: HKD 380.00
3. **Support 1**: HKD 365.00

> 建議在回撥至 365-368 區間關注

\`\`\`
MA5 > MA10 > MA20 (多頭排列)
RSI(14) = 58.3 (中性偏強)
\`\`\`

[Click for more details](https://finance.qq.com/q/go.php/vInvestConsult/stock/00700)`;

    const result = markdownToPlainText(hkReport);

    expect(result).toContain('Tencent');
    expect(result).toContain('00700.HK');
    expect(result).toContain('368.20');
    expect(result).toContain('Resistance 1');
    expect(result).toContain('Support 1');
    expect(result).toContain('建議在回撥');
    expect(result).toContain('MA5 > MA10');
    expect(result).toContain('Click for more details');
  });

  it('handles US stock report with financial data', () => {
    const usReport = `# Apple Inc. (AAPL) Analysis Report

## Financial Metrics

| Metric | Value | Change |
|--------|-------|--------|
| Price | $178.35 | +1.2% |
| Market Cap | $2.8T | - |
| P/E Ratio | 28.5 | - |
| EPS | $6.16 | +8.3% |

## Technical Indicators

- **MA50**: $175.20 (Above)
- **MA200**: $168.80 (Above)
- **RSI**: 62.5 (Slightly Overbought)
- **MACD**: Bullish crossover

## Recommendation

***Strong Buy*** with target price of **$195.00**

> Risk: Trade tensions may impact supply chain

\`\`\`javascript
const entryPrice = 178.35;
const stopLoss = 172.00;
const targetPrice = 195.00;
const riskReward = (targetPrice - entryPrice) / (entryPrice - stopLoss);
// Risk/Reward ratio: 2.1:1
\`\`\`

![AAPL Chart](https://example.com/charts/aapl.png)`;

    const result = markdownToPlainText(usReport);

    expect(result).toContain('Apple Inc.');
    expect(result).toContain('AAPL');
    expect(result).toContain('178.35');
    expect(result).toContain('2.8T');
    expect(result).toContain('Strong Buy');
    expect(result).toContain('195.00');
    expect(result).toContain('Risk/Reward ratio');
  });

  it('handles market review report with multiple stocks', () => {
    const marketReview = `# A股市場覆盤

## 指數表現

| 指數 | 收盤 | 漲跌幅 | 成交額 |
|------|------|--------|--------|
| 上證指數 | 3050.32 | +0.85% | 4285億 |
| 深證成指 | 9850.45 | +1.12% | 5250億 |
| 創業板指 | 1950.28 | +1.45% | 2180億 |

## 熱點板塊

1. **人工智慧** 🤖
   - 原因：大模型技術突破
   - 龍頭：科大訊飛、寒武紀

2. **新能源汽車** 🚗
   - 原因：銷量資料超預期
   - 龍頭：比亞迪、理想汽車

3. **半導體** 💾
   - 原因：國產替代加速
   - 龍頭：中芯國際、北方華創

## 資金流向

- **北向資金**: +85.5億
- **融資融券**: +32.8億
- **主力資金**: 淨流入 156.8億

## 後市展望

> 預期明日震盪區間：3040-3065

**策略**：關注科技主線，控制部位`;

    const result = markdownToPlainText(marketReview);

    expect(result).toContain('A股市場覆盤');
    expect(result).toContain('上證指數');
    expect(result).toContain('3050.32');
    expect(result).toContain('人工智慧');
    expect(result).toContain('科大訊飛');
    expect(result).toContain('北向資金');
    expect(result).toContain('85.5億');
    expect(result).toContain('3040-3065');
  });

  it('handles report with special characters and formulas', () => {
    const report = `# 技術指標計算

## MACD 計算

\`\`\`python
# MACD = EMA(12) - EMA(26)
# Signal = EMA(MACD, 9)
# Histogram = MACD - Signal

def calculate_macd(prices, fast=12, slow=26, signal=9):
    ema_fast = prices.ewm(span=fast).mean()
    ema_slow = prices.ewm(span=slow).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=signal).mean()
    return macd, signal_line
\`\`\`

## RSI 公式

$$RSI = 100 - \frac{100}{1 + RS}$$

其中：
- RS = 平均漲幅 / 平均跌幅
- 週期：預設 14 天

## 布林帶

- **中軌** = MA(20)
- **上軌** = MA(20) + 2 × STD(20)
- **下軌** = MA(20) - 2 × STD(20)

> 當前股價在上軌附近，注意回撥風險`;

    const result = markdownToPlainText(report);

    expect(result).toContain('MACD 計算');
    expect(result).toContain('EMA(12) - EMA(26)');
    expect(result).toContain('RSI');
    expect(result).toContain('布林帶');
    expect(result).toContain('MA(20)');
    expect(result).toContain('注意回撥風險');
  });

  it('handles report with code snippets in multiple languages', () => {
    const report = `# 策略回測程式碼

## Python 策略

\`\`\`python
import pandas as pd
import numpy as np

def moving_average_strategy(data, short=5, long=20):
    signals = pd.DataFrame(index=data.index)
    signals['signal'] = 0

    signals['short_ma'] = data['close'].rolling(window=short).mean()
    signals['long_ma'] = data['close'].rolling(window=long).mean()

    signals.loc[signals['short_ma'] > signals['long_ma'], 'signal'] = 1
    signals.loc[signals['short_ma'] < signals['long_ma'], 'signal'] = -1

    return signals
\`\`\`

以上程式碼可直接用於策略回測。`;

    const result = markdownToPlainText(report);

    // Verify key content is preserved
    expect(result).toContain('策略回測程式碼');
    expect(result).toContain('Python 策略');
    expect(result).toContain('以上程式碼可直接用於策略回測');

    // Verify code content is preserved
    expect(result).toContain('import pandas');
    expect(result).toContain('moving_average_strategy');
  });

  it('handles edge case: very long stock code list', () => {
    const stockList = `# 股票池列表

## 滬深300成分股（部分）

| 程式碼 | 名稱 | 現價 | 漲跌幅 |
|------|------|------|--------|
| 600519 | 貴州茅臺 | 1680.50 | +0.85% |
| 000858 | 五糧液 | 125.30 | +1.20% |
| 600036 | 招商銀行 | 32.50 | -0.25% |
| 000001 | 平安銀行 | 11.85 | +0.42% |
| 601318 | 中國平安 | 45.20 | +0.15% |
| 000333 | 美的集團 | 58.80 | +1.80% |
| 600276 | 恆瑞醫藥 | 42.50 | +2.10% |
| 300750 | 寧德時代 | 185.30 | +3.20% |
| 688981 | 中芯國際 | 52.80 | +4.50% |
| 601012 | 隆基綠能 | 25.60 | -1.20% |

## 篩選條件

- **市值**: > 500億
- **PE**: 10-50
- **ROE**: > 15%
- **負債率**: < 60%`;

    const result = markdownToPlainText(stockList);

    // Verify all stock codes are preserved
    expect(result).toContain('600519');
    expect(result).toContain('000858');
    expect(result).toContain('601012');
    expect(result).toContain('貴州茅臺');
    expect(result).toContain('寧德時代');
    expect(result).toContain('篩選條件');
    expect(result).toContain('ROE');
  });

  it('handles mixed Chinese and English punctuation correctly', () => {
    const text = `# 報告摘要

**主要觀點**：
1. 短期看漲，目標價 $195.00
2. 支撐位：$168.50-172.00
3. 壓力位：$180.50-185.00

"Risk: Trade war impact"

> 風險提示：中美貿易摩擦可能影響出口

*關注點*：AI chip business growth`;

    const result = markdownToPlainText(text);

    expect(result).toContain('主要觀點');
    expect(result).toContain('短期看漲');
    expect(result).toContain('195.00');
    expect(result).toContain('Risk: Trade war impact');
    expect(result).toContain('風險提示');
    expect(result).toContain('關注點');
    expect(result).toContain('AI chip business');
  });

  it('preserves numerical data and percentages accurately', () => {
    const report = `# 資料包告

## 關鍵指標

- 營收: 1,234.56億
- 淨利潤: +23.45%
- 市佔率: 15.67%
- ROE: 18.9%
- 負債率: 45.2%

## 價格區間

| 日期 | 開盤 | 最高 | 最低 | 收盤 |
|------|------|------|------|------|
| 2024-01-15 | 1680.50 | 1695.30 | 1675.20 | 1688.80 |
| 2024-01-16 | 1688.80 | 1702.50 | 1685.30 | 1698.20 |

漲跌幅: +1.23% (今日)`;

    const result = markdownToPlainText(report);

    expect(result).toContain('1,234.56');
    expect(result).toContain('23.45%');
    expect(result).toContain('15.67%');
    expect(result).toContain('1680.50');
    expect(result).toContain('1695.30');
    expect(result).toContain('1.23%');
  });
});
