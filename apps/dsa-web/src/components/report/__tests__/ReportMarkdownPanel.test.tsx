import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { historyApi } from '../../../api/history';
import { ReportMarkdownPanel } from '../ReportMarkdownPanel';

vi.mock('../../../api/history', () => ({
  historyApi: {
    getMarkdown: vi.fn(),
    getDetail: vi.fn().mockResolvedValue(null),
    getPdf: vi.fn(),
  },
}));

vi.mock('../visual/ReportVisualSummary', () => ({
  ReportVisualSummary: () => <div data-testid="visual-summary-stub" />,
}));

vi.mock('../MermaidDiagram', () => ({
  MermaidDiagram: (props: { code: string }) => (
    <div data-testid="mermaid-stub">{props.code}</div>
  ),
}));

describe('ReportMarkdownPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(historyApi.getPdf).mockResolvedValue({
      blob: new Blob(['%PDF'], { type: 'application/pdf' }),
      filename: 'report.pdf',
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders a normal fenced code block as plain code, with no MermaidDiagram stub present', async () => {
    vi.mocked(historyApi.getMarkdown).mockResolvedValue('```json\n{"a":1}\n```');

    render(
      <ReportMarkdownPanel
        recordId={1}
        stockName="Test Co"
        stockCode="TST"
        onRequestClose={() => {}}
      />
    );

    expect(await screen.findByText(/"a":1/)).toBeInTheDocument();
    expect(screen.queryByTestId('mermaid-stub')).not.toBeInTheDocument();
  });

  it('renders a mermaid fenced block via the MermaidDiagram component with trimmed inner source', async () => {
    vi.mocked(historyApi.getMarkdown).mockResolvedValue(
      '```mermaid\nflowchart TB\n  A["Start"] --> B["End"]\n```'
    );

    render(
      <ReportMarkdownPanel
        recordId={1}
        stockName="Test Co"
        stockCode="TST"
        onRequestClose={() => {}}
      />
    );

    const stub = await screen.findByTestId('mermaid-stub');
    expect(stub.textContent).toBe('flowchart TB\n  A["Start"] --> B["End"]');
    expect(stub.closest('.report-body-mermaid-figure')).not.toBeNull();
  });

  it('renders the appendix heading followed by the mermaid block, in DOM order after preceding content', async () => {
    vi.mocked(historyApi.getMarkdown).mockResolvedValue(
      '# 報告標題\n\n一些內文段落。\n\n## 附錄：價值網路圖\n\n```mermaid\nflowchart TB\n  A --> B\n```\n'
    );

    const { container } = render(
      <ReportMarkdownPanel
        recordId={1}
        stockName="Test Co"
        stockCode="TST"
        onRequestClose={() => {}}
      />
    );

    expect(await screen.findByText('附錄：價值網路圖')).toBeInTheDocument();
    const stub = await screen.findByTestId('mermaid-stub');
    expect(stub).toBeInTheDocument();

    const fullText = container.textContent ?? '';
    const titleIndex = fullText.indexOf('報告標題');
    const headingIndex = fullText.indexOf('附錄：價值網路圖');
    expect(titleIndex).toBeGreaterThanOrEqual(0);
    expect(headingIndex).toBeGreaterThan(titleIndex);
  });

  it('still renders normal markdown (headings, paragraphs) unaffected', async () => {
    vi.mocked(historyApi.getMarkdown).mockResolvedValue('# Title\n\nA paragraph.');

    render(
      <ReportMarkdownPanel
        recordId={1}
        stockName="Test Co"
        stockCode="TST"
        onRequestClose={() => {}}
      />
    );

    expect(await screen.findByRole('heading', { name: 'Title' })).toBeInTheDocument();
    expect(screen.getByText('A paragraph.')).toBeInTheDocument();
  });

  it('renders market_review markdown as the Taiwan daily structured reader when parseable', async () => {
    vi.mocked(historyApi.getMarkdown).mockResolvedValue([
      '# 台股大盤回顧',
      '',
      '> 資料日期：2026-06-26',
      '',
      '## 今日盤勢摘要',
      '',
      '今日所有必要指標資料完整，可進行完整分析。',
      '',
      '## 指數表現',
      '',
      '- 加權報酬指數（TAIEX）：23,000.00 點 🟢 +120.00（+0.52%）',
      '- 櫃買報酬指數（TPEx）：260.00 點 🔴 -1.50（-0.57%）',
      '',
      '## 法人與資金面',
      '',
      '- 外資：買 1,200.0 億，賣 1,000.0 億，淨 ▲ 200.0 億',
      '',
      '## 融資融券觀察',
      '',
      '- 融資餘額：今日 2,200.0 億，較昨日 ▼ 10.0 億',
      '',
      '## 0050 / 臺積電參考',
      '',
      '- 元大台灣50（0050）：收盤 180.20（2026-06-26）',
      '',
      '## 風險與注意事項',
      '',
      '- 市場有風險，投資需謹慎。',
    ].join('\n'));

    render(
      <ReportMarkdownPanel
        recordId={2}
        stockName="台股日報"
        stockCode="MARKET"
        initialDetail={{
          meta: {
            id: 2,
            queryId: 'market-review-q-1',
            stockCode: 'MARKET',
            stockName: '台股日報',
            reportType: 'market_review',
            createdAt: '2026-06-26T00:00:00Z',
          },
          summary: {
            analysisSummary: '台股日報摘要',
            operationAdvice: '檢視資料',
            trendPrediction: '大盤回顧',
            sentimentScore: 50,
          },
        }}
        onRequestClose={() => {}}
      />
    );

    const reader = await screen.findByTestId('tw-daily-reader');
    expect(reader).toBeInTheDocument();
    expect(screen.getAllByRole('heading', { name: '台股日報' }).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('主要指數')).toBeInTheDocument();
    expect(screen.getByText('法人與資金面')).toBeInTheDocument();
    expect(screen.queryByTestId('visual-summary-stub')).not.toBeInTheDocument();
    expect(screen.queryByTestId('report-markdown-body')).not.toBeInTheDocument();
  });

  it('prefers tw_daily_snapshot over market_review markdown when history detail exposes structured data', async () => {
    vi.mocked(historyApi.getMarkdown).mockResolvedValue([
      '# 台股大盤回顧',
      '',
      '> 資料日期：2026-06-26',
      '',
      '## 指數表現',
      '',
      '- 加權報酬指數（TAIEX）：23,000.00 點 🟢 +120.00（+0.52%）',
      '',
      '## 法人與資金面',
      '',
      '- 外資：買 1,200.0 億，賣 1,000.0 億，淨 ▲ 200.0 億',
      '',
      '## 融資融券觀察',
      '',
      '- 融資餘額：今日 2,200.0 億，較昨日 ▼ 10.0 億',
      '',
      '## 0050 / 臺積電參考',
      '',
      '- 元大台灣50（0050）：收盤 180.20（2026-06-26）',
    ].join('\n'));

    render(
      <ReportMarkdownPanel
        recordId={22}
        stockName="台股日報"
        stockCode="MARKET"
        initialDetail={{
          meta: {
            id: 22,
            queryId: 'market-review-q-structured',
            stockCode: 'MARKET',
            stockName: '台股日報',
            reportType: 'market_review',
            createdAt: '2026-06-26T00:00:00Z',
          },
          summary: {
            analysisSummary: '台股日報摘要',
            operationAdvice: '檢視資料',
            trendPrediction: '大盤回顧',
            sentimentScore: 50,
          },
          details: {
            contextSnapshot: {
              marketLightSnapshots: {
                tw: {
                  twDailySnapshot: {
                    kind: 'tw_daily_snapshot',
                    source: 'finmind',
                    dataDate: '2026-06-26',
                    indices: [{
                      symbol: 'TAIEX',
                      name: '加權報酬指數',
                      value: 23000,
                      change: -120,
                      changePct: -0.52,
                      dataDate: '2026-06-26',
                    }],
                    institutionalFlows: [],
                    marginShort: [],
                    representatives: [{
                      symbol: '006208',
                      name: '富邦台50',
                      close: 112.4,
                      previousClose: 112.8,
                      change: -0.4,
                      changePct: -0.35,
                      volume: 3400000,
                      turnover: 382160000,
                      dataDate: '2026-06-26',
                      missingFields: ['PER', 'PBR', 'dividend_yield'],
                    }],
                    twMarketAnalysisSnapshot: {
                      kind: 'tw_market_analysis_snapshot',
                      analysisReady: true,
                      dataDate: '2026-06-26',
                      marketState: 'closed',
                      narrative: {
                        title: '台股加權指數最新技術分析',
                        openingSummary: '加權指數收在 23,000 點。',
                        coreJudgement: ['反彈中但未確認翻多'],
                        movingAverageAnalysis: ['指數低於 MA20。'],
                        momentumAnalysis: ['RSI14 動能改善。'],
                        priceActionAnalysis: [],
                        volumeAnalysis: [],
                        supportResistanceAnalysis: ['支撐區 22,700–22,900 點。'],
                        confirmationConditions: [],
                        invalidationConditions: [],
                      },
                    },
                    dataStatus: { missingFields: [], staleFields: [], partialFailures: [] },
                  },
                },
              },
            },
          },
        }}
        onRequestClose={() => {}}
      />
    );

    expect(await screen.findByTestId('tw-daily-reader')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '台股加權指數最新技術分析' })).toBeInTheDocument();
    expect(screen.getByText('反彈中但未確認翻多')).toBeInTheDocument();
    expect(screen.getByText('006208')).toBeInTheDocument();
    expect(screen.queryByTestId('report-markdown-body')).not.toBeInTheDocument();
  });

  it('falls back to the safe markdown body for incomplete market_review markdown', async () => {
    vi.mocked(historyApi.getMarkdown).mockResolvedValue('# 台股大盤回顧\n\n只有舊版文字');

    render(
      <ReportMarkdownPanel
        recordId={2}
        stockName="台股日報"
        stockCode="MARKET"
        onRequestClose={() => {}}
      />
    );

    expect(await screen.findByTestId('report-markdown-body')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '台股大盤回顧' })).toBeInTheDocument();
    expect(screen.queryByTestId('tw-daily-reader')).not.toBeInTheDocument();
  });

  it('renders a US-only market_review record (no Taiwan snapshot, no Taiwan headings) as the generic body, never the Taiwan reader', async () => {
    vi.mocked(historyApi.getMarkdown).mockResolvedValue([
      '# 2026-07-18 美股大盤回顧',
      '',
      '> **今日市場狀態：** 科技主導的全面回調。',
      '',
      '## 一、盤面總覽',
      '',
      '三大指數全線下跌，納斯達克跌幅最大。',
    ].join('\n'));

    render(
      <ReportMarkdownPanel
        recordId={211}
        stockName="美股日報"
        stockCode="MARKET"
        initialDetail={{
          meta: {
            id: 211,
            queryId: 'market-review-us-only',
            stockCode: 'MARKET',
            stockName: '美股日報',
            reportType: 'market_review',
            createdAt: '2026-07-18T00:23:00Z',
          },
          summary: {
            analysisSummary: '美股日報摘要',
            operationAdvice: '查看美股日報',
            trendPrediction: '美股日報',
            sentimentScore: 50,
          },
        }}
        onRequestClose={() => {}}
      />
    );

    expect(await screen.findByRole('heading', { name: '2026-07-18 美股大盤回顧' })).toBeInTheDocument();
    expect(screen.queryByTestId('tw-daily-reader')).not.toBeInTheDocument();
    expect(screen.getByTestId('report-markdown-body')).toBeInTheDocument();
  });

  describe('copy scope', () => {
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    let originalClipboard: Navigator['clipboard'] | undefined;

    beforeEach(() => {
      writeTextMock.mockClear();
      originalClipboard = navigator.clipboard;
      Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: { writeText: writeTextMock },
      });
    });

    afterEach(() => {
      Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: originalClipboard,
      });
    });

    const COMPOSITE_MARKDOWN = [
      '# 台股大盤回顧',
      '',
      '> 資料日期：2026-07-16',
      '',
      '## 指數表現',
      '',
      '- 加權報酬指數（TAIEX）：42,671.27 點 🔴 -2,954.43（-6.48%）',
      '',
      '## 法人與資金面',
      '',
      '- 外資：買 1,200.0 億，賣 1,000.0 億，淨 ▼ 200.0 億',
      '',
      '## 融資融券觀察',
      '',
      '- 融資餘額：今日 2,200.0 億，較昨日 ▼ 10.0 億',
      '',
      '## 0050 / 臺積電參考',
      '',
      '- 元大台灣50（0050）：收盤 150.20（2026-07-16）',
      '',
      '---',
      '',
      '## 美股大盤回顧',
      '',
      '道瓊工業指數下跌 500 點，那斯達克同步走弱。',
      '',
      '### 操作建議',
      '',
      '建議觀望，等待風險釋放後再行布局。',
    ].join('\n');

    const marketReviewDetail = {
      meta: {
        id: 33,
        queryId: 'market-review-q-copy-scope',
        stockCode: 'MARKET',
        stockName: '台股日報',
        reportType: 'market_review' as const,
        createdAt: '2026-07-16T00:00:00Z',
      },
      summary: {
        analysisSummary: '台股日報摘要',
        operationAdvice: '檢視資料',
        trendPrediction: '大盤回顧',
        sentimentScore: 50,
      },
      details: {
        contextSnapshot: {
          marketLightSnapshots: {
            tw: {
              twDailySnapshot: {
                kind: 'tw_daily_snapshot',
                source: 'finmind',
                dataDate: '2026-07-16',
                indices: [],
                institutionalFlows: [],
                marginShort: [],
                representatives: [],
                twMarketAnalysisSnapshot: {
                  kind: 'tw_market_analysis_snapshot',
                  analysisReady: true,
                  dataDate: '2026-07-16',
                  marketState: 'open_incomplete',
                  analysisArticle: {
                    status: 'available',
                    headline: '台股加權指數最新技術分析',
                    marketContext: '資料時間：2026 年 7 月 17 日 03:26（台股交易中；分析僅採前一完整交易日）',
                    sessionSummary: '最新完整交易日為 2026-07-16，加權指數收在 42,671.27 點，下跌 2,954.43 點、跌幅 6.48%。',
                    coreJudgement: {
                      label: '短空中性',
                      summary: '短線持續下探，指數已進入 42,353～42,990 點支撐區並正接受測試，若跌破區間下緣，修正風險將進一步提高。',
                    },
                    trendParagraphs: ['指數收盤仍低於 MA5、MA10 與 MA20，短期均線維持偏空結構。'],
                    priceActionParagraphs: ['指數已進入 42,353～42,990 點支撐區，支撐正在接受測試；目前尚未跌破區間下緣，但收盤位於區間內，承接力仍待確認。'],
                    confirmationParagraph: '若後續收盤有效跌破 42,353 點，才代表該支撐區正式失效。',
                    supportingContext: ['外資偏賣、投信偏買，法人方向分歧且整體仍偏賣。'],
                    tpexContext: '櫃買指數當日下跌 7.02%，表現弱於加權指數。',
                  },
                },
                dataStatus: { missingFields: [], staleFields: [], partialFailures: [] },
              },
            },
          },
        },
      },
    };

    it('scopes the Taiwan daily Markdown copy action to the article only, excluding the composite US/full-market markdown', async () => {
      vi.mocked(historyApi.getMarkdown).mockResolvedValue(COMPOSITE_MARKDOWN);

      render(
        <ReportMarkdownPanel
          recordId={33}
          stockName="台股日報"
          stockCode="MARKET"
          initialDetail={marketReviewDetail}
          onRequestClose={() => {}}
        />
      );

      expect(await screen.findByTestId('tw-daily-reader')).toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: /複製台股日報.*Markdown/ }));
      await waitFor(() => expect(writeTextMock).toHaveBeenCalledTimes(1));
      const copiedMarkdown = writeTextMock.mock.calls[0][0] as string;

      expect(copiedMarkdown).toContain('台股加權指數最新技術分析');
      expect(copiedMarkdown).toContain('42,353');
      expect(copiedMarkdown).toContain('支撐正在接受測試');
      expect(copiedMarkdown).not.toContain('美股大盤回顧');
      expect(copiedMarkdown).not.toContain('操作建議');
      expect(copiedMarkdown).not.toContain('道瓊工業指數');
    });

    it('scopes the Taiwan daily plain-text copy action to the article only, excluding the composite US/full-market markdown', async () => {
      vi.mocked(historyApi.getMarkdown).mockResolvedValue(COMPOSITE_MARKDOWN);

      render(
        <ReportMarkdownPanel
          recordId={33}
          stockName="台股日報"
          stockCode="MARKET"
          initialDetail={marketReviewDetail}
          onRequestClose={() => {}}
        />
      );

      expect(await screen.findByTestId('tw-daily-reader')).toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: /複製台股日報.*純文字/ }));
      await waitFor(() => expect(writeTextMock).toHaveBeenCalledTimes(1));
      const copiedPlainText = writeTextMock.mock.calls[0][0] as string;

      expect(copiedPlainText).toContain('台股加權指數最新技術分析');
      expect(copiedPlainText).not.toContain('美股大盤回顧');
      expect(copiedPlainText).not.toContain('操作建議');
    });

    it('copies the full report unaffected when no Taiwan daily reader is active', async () => {
      vi.mocked(historyApi.getMarkdown).mockResolvedValue('# Report title\n\nA paragraph.');

      render(
        <ReportMarkdownPanel
          recordId={1}
          stockName="Test Co"
          stockCode="TST"
          onRequestClose={() => {}}
        />
      );

      expect(await screen.findByRole('heading', { name: 'Report title' })).toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: '複製 Markdown 原始碼' }));
      await waitFor(() => expect(writeTextMock).toHaveBeenCalledWith('# Report title\n\nA paragraph.'));
    });

    it('still copies a useful Taiwan-only payload for the legacy markdown fallback reader', async () => {
      vi.mocked(historyApi.getMarkdown).mockResolvedValue([
        '# 台股大盤回顧',
        '',
        '> 資料日期：2026-06-26',
        '',
        '## 今日盤勢摘要',
        '',
        '今日所有必要指標資料完整，可進行完整分析。',
        '',
        '## 指數表現',
        '',
        '- 加權報酬指數（TAIEX）：23,000.00 點 🟢 +120.00（+0.52%）',
        '',
        '## 法人與資金面',
        '',
        '- 外資：買 1,200.0 億，賣 1,000.0 億，淨 ▲ 200.0 億',
        '',
        '## 融資融券觀察',
        '',
        '- 融資餘額：今日 2,200.0 億，較昨日 ▼ 10.0 億',
        '',
        '## 0050 / 臺積電參考',
        '',
        '- 元大台灣50（0050）：收盤 180.20（2026-06-26）',
        '',
        '## 風險與注意事項',
        '',
        '- 市場有風險，投資需謹慎。',
      ].join('\n'));

      render(
        <ReportMarkdownPanel
          recordId={2}
          stockName="台股日報"
          stockCode="MARKET"
          initialDetail={{
            meta: {
              id: 2,
              queryId: 'market-review-legacy-copy',
              stockCode: 'MARKET',
              stockName: '台股日報',
              reportType: 'market_review',
              createdAt: '2026-06-26T00:00:00Z',
            },
            summary: {
              analysisSummary: '台股日報摘要',
              operationAdvice: '檢視資料',
              trendPrediction: '大盤回顧',
              sentimentScore: 50,
            },
          }}
          onRequestClose={() => {}}
        />
      );

      expect(await screen.findByTestId('tw-daily-reader')).toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: /複製台股日報.*Markdown/ }));
      await waitFor(() => expect(writeTextMock).toHaveBeenCalledTimes(1));
      const copied = writeTextMock.mock.calls[0][0] as string;

      expect(copied).toContain('加權報酬指數');
      expect(copied).toContain('外資');
    });
  });

  it('renders Markdown as editorial report sections with styled headings, tables, and callouts', async () => {
    vi.mocked(historyApi.getMarkdown).mockResolvedValue(
      '# Report title\n\n> 分析日期: **2026-06-27** | 報告生成時間: 15:49\n\n## Section A\n\n### Risk section\n\n> Important callout.\n\n| 操作點位 | 目前價格 |\n| --- | --- |\n| 理想買進點 | Wait |\n'
    );

    const { container } = render(
      <ReportMarkdownPanel
        recordId={1}
        stockName="Test Co"
        stockCode="TST"
        onRequestClose={() => {}}
      />
    );

    expect(await screen.findByRole('heading', { name: 'Report title' })).toHaveClass('report-body-title');
    expect(screen.getByRole('heading', { name: 'Section A' })).toHaveClass('report-body-heading');
    expect(screen.getByRole('heading', { name: 'Risk section' })).toHaveClass('report-body-heading-level3');
    expect(screen.getAllByTestId('report-body-section')).toHaveLength(3);
    expect(screen.getByRole('table')).toHaveClass('report-body-table', 'report-body-battle-table');
    expect(container.querySelector('blockquote.report-body-callout')).not.toBeNull();
    expect(container.querySelector('blockquote.report-body-meta-strip')).not.toBeNull();
  });

  it('suppresses duplicate headline/chip content and renders checklist rows as a compact table', async () => {
    vi.mocked(historyApi.getMarkdown).mockResolvedValue(
      [
        '# Microsoft Corporation 股票分析報告',
        '',
        '> 分析日期: **2026-06-27** | 報告生成時間: 15:49',
        '',
        '### 📌 核心結論',
        '',
        '**⚪ 觀望** | 看空',
        '',
        '### 📈 多週期趨勢快照',
        '',
        '| 週期 | 漲跌幅 |',
        '| --- | --- |',
        '| 1週 | -7% |',
        '',
        '### 📊 資料透視',
        '',
        '**籌碼**: 籌碼集中度不足',
        '',
        '| 指標 | 值 |',
        '| --- | --- |',
        '| 籌碼集中度 | 高 |',
        '',
        '**✅ 檢查清單**',
        '',
        '- ✅ 多頭排列: 成立',
        '- ⚠️ RSI: 接近超賣',
      ].join('\n')
    );

    const { container } = render(
      <ReportMarkdownPanel
        recordId={1}
        stockName="Test Co"
        stockCode="TST"
        onRequestClose={() => {}}
      />
    );

    expect(await screen.findByText(/檢查清單/)).toBeInTheDocument();
    expect(screen.queryByText(/股票分析報告/)).not.toBeInTheDocument();
    expect(container.querySelector('blockquote.report-body-meta-strip')).not.toBeNull();
    expect(screen.queryByText(/觀望/)).not.toBeInTheDocument();
    expect(screen.queryByText(/多週期趨勢快照/)).not.toBeInTheDocument();
    expect(screen.queryByText(/籌碼/)).not.toBeInTheDocument();
    expect(screen.getByText('多頭排列')).toBeInTheDocument();
    expect(screen.getByText('接近超賣')).toBeInTheDocument();
    expect(container.querySelector('table.report-body-checklist-table')).not.toBeNull();
  });

  it('renders visual summary above the light report markdown body when detail succeeds', async () => {
    vi.mocked(historyApi.getMarkdown).mockResolvedValue('# Styled report');
    vi.mocked(historyApi.getDetail).mockResolvedValue({ id: 1 } as never);

    render(
      <ReportMarkdownPanel
        recordId={1}
        stockName="Test Co"
        stockCode="TST"
        onRequestClose={() => {}}
      />
    );

    const summary = await screen.findByTestId('visual-summary-stub');
    const body = screen.getByTestId('report-markdown-body');
    expect(body.className).toContain('report-light-surface');
    expect(body.className).toContain('report-markdown-body');
    expect(body.className).toContain('report-body-paper');
    expect(summary.compareDocumentPosition(body) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('downloads the PDF from the backend endpoint without changing report content', async () => {
    vi.mocked(historyApi.getMarkdown).mockResolvedValue('# Printable report');
    const openSpy = vi.spyOn(window, 'open').mockReturnValue(null);
    const clickSpy = vi.fn();
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: vi.fn(() => 'blob:report-pdf'),
    });
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      value: vi.fn(),
    });
    const createElementSpy = vi.spyOn(document, 'createElement');
    createElementSpy.mockImplementation((tagName: string) => {
      const element = document.createElementNS('http://www.w3.org/1999/xhtml', tagName) as HTMLElement;
      if (tagName === 'a') {
        Object.defineProperty(element, 'click', { value: clickSpy });
      }
      return element;
    });

    render(
      <ReportMarkdownPanel
        recordId={74}
        stockName="富邦台50"
        stockCode="006208"
        onRequestClose={() => {}}
      />
    );

    fireEvent.click(await screen.findByRole('button', { name: '下載 PDF' }));

    await waitFor(() => {
      expect(historyApi.getPdf).toHaveBeenCalledWith(74);
    });
    expect(openSpy).not.toHaveBeenCalled();
    expect(URL.createObjectURL).toHaveBeenCalled();
    expect(clickSpy).toHaveBeenCalled();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:report-pdf');
    expect(await screen.findByRole('heading', { name: 'Printable report' })).toBeInTheDocument();
  });

  it('shows a controlled PDF error when direct download fails', async () => {
    vi.mocked(historyApi.getMarkdown).mockResolvedValue('# Printable report');
    vi.mocked(historyApi.getPdf).mockRejectedValue(new Error('pdf failed'));

    render(
      <ReportMarkdownPanel
        recordId={74}
        stockName="富邦台50"
        stockCode="006208"
        onRequestClose={() => {}}
      />
    );

    fireEvent.click(await screen.findByRole('button', { name: '下載 PDF' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('PDF 產生失敗，請稍後再試。');
  });


  it('does not show a Google Finance link inside the full report panel', async () => {
    vi.mocked(historyApi.getMarkdown).mockResolvedValue('# Google finance report');

    render(
      <ReportMarkdownPanel
        recordId={1}
        stockName="台積電"
        stockCode="2330"
        onRequestClose={() => {}}
        initialDetail={{
          meta: {
            id: 1,
            queryId: 'q-tw',
            stockCode: '2330',
            stockName: '台積電',
            reportType: 'detailed',
            createdAt: '2026-06-28T08:00:00Z',
            market: 'TW',
            instrumentType: 'stock',
            exchange: 'TWSE',
            googleFinanceExchange: 'TPE',
            exchangeSource: 'static_tpe',
          },
          summary: {},
          strategy: {},
        } as never}
      />
    );

    expect(await screen.findByRole('heading', { name: 'Google finance report' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '在 Google Finance 查看' })).not.toBeInTheDocument();
  });

  // ── Phase 25.7: four-masters commentary structured UI ──

  const fourMastersDetail = (rawResult: Record<string, unknown>) => ({
    meta: {
      id: 9,
      queryId: 'q-fm',
      stockCode: '2330',
      stockName: '台積電',
      reportType: 'detailed',
      createdAt: '2026-07-08T08:00:00Z',
    },
    summary: {
      analysisSummary: '摘要',
      operationAdvice: '觀望',
      trendPrediction: '震盪',
      sentimentScore: 59,
    },
    details: { rawResult },
  }) as never;

  const fourMastersMarkdown = [
    '# 台積電分析',
    '',
    '## 走勢分析',
    '',
    '- 均線糾結。',
    '',
    '## 四大師視角補充',
    '',
    '### 巴菲特視角：價值與安全邊際',
    '',
    'markdown 版巴菲特點評內文',
    '',
    '> 本段為投資框架模擬點評，不代表任何人物本人觀點，且不覆蓋原始操作建議。',
  ].join('\n');

  const fourMastersRaw = {
    fourMastersCommentary: {
      buffett: { summary: '結構化巴菲特點評', supportsOriginalView: 'challenge' },
      munger: { summary: '結構化蒙格點評', supportsOriginalView: 'mixed' },
      duanYongping: { summary: '結構化段永平點評', supportsOriginalView: 'support' },
      liLu: { summary: '結構化李錄點評', supportsOriginalView: 'support' },
      synthesis: { mainDisagreement: '分歧在估值', confidenceAdjustment: 'unchanged' },
    },
  };

  it('renders structured four-masters UI and suppresses the duplicate markdown section', async () => {
    vi.mocked(historyApi.getMarkdown).mockResolvedValue(fourMastersMarkdown);

    render(
      <ReportMarkdownPanel
        recordId={9}
        stockName="台積電"
        stockCode="2330"
        onRequestClose={() => {}}
        initialDetail={fourMastersDetail(fourMastersRaw)}
      />
    );

    expect(await screen.findByTestId('four-masters-commentary')).toBeInTheDocument();
    // 結構化內容出現
    expect(screen.getByText('結構化巴菲特點評')).toBeInTheDocument();
    // markdown 版四大師段被抑制（無重複）：markdown body 內不含該 heading 與內文
    expect(screen.queryByText('markdown 版巴菲特點評內文')).not.toBeInTheDocument();
    const markdownBody = screen.getByTestId('report-markdown-body');
    expect(markdownBody.textContent).not.toContain('四大師視角補充');
    // 其他 markdown 段不受影響
    expect(screen.getByRole('heading', { name: '走勢分析' })).toBeInTheDocument();
    // 全頁只有一份四大師標題（結構化 UI 自己的）
    expect(screen.getAllByText(/四大師視角補充/).length).toBe(1);
  });

  it('keeps the markdown four-masters section when detail lacks structured payload', async () => {
    vi.mocked(historyApi.getMarkdown).mockResolvedValue(fourMastersMarkdown);

    render(
      <ReportMarkdownPanel
        recordId={10}
        stockName="台積電"
        stockCode="2330"
        onRequestClose={() => {}}
        initialDetail={fourMastersDetail({})}
      />
    );

    expect(await screen.findByText('markdown 版巴菲特點評內文')).toBeInTheDocument();
    expect(screen.queryByTestId('four-masters-commentary')).not.toBeInTheDocument();
  });

  it('legacy reports without four-masters content render unchanged', async () => {
    vi.mocked(historyApi.getMarkdown).mockResolvedValue('# 舊報告\n\n## 走勢分析\n\n內文。');

    render(
      <ReportMarkdownPanel
        recordId={11}
        stockName="台積電"
        stockCode="2330"
        onRequestClose={() => {}}
        initialDetail={fourMastersDetail({})}
      />
    );

    expect(await screen.findByRole('heading', { name: '舊報告' })).toBeInTheDocument();
    expect(screen.queryByTestId('four-masters-commentary')).not.toBeInTheDocument();
    expect(screen.queryByText(/四大師/)).not.toBeInTheDocument();
  });

});
