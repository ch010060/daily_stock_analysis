import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ReportOverview } from '../ReportOverview';

const baseMeta = {
  queryId: 'q-1',
  stockCode: '2330',
  stockName: '台積電',
  reportType: 'detailed' as const,
  reportLanguage: 'zh' as const,
  createdAt: '2026-03-21T08:00:00Z',
};

const baseSummary = {
  analysisSummary: '趨勢維持強勢',
  operationAdvice: '繼續觀察買點',
  trendPrediction: '短線震盪偏強',
  sentimentScore: 78,
};

describe('ReportOverview', () => {
  it('renders final market phase and partial-bar labels from report metadata', () => {
    render(
      <ReportOverview
        meta={{
          ...baseMeta,
          marketPhaseSummary: {
            market: 'cn',
            phase: 'intraday',
            marketLocalTime: '2026-03-21T10:30:00+08:00',
            sessionDate: '2026-03-21',
            effectiveDailyBarDate: '2026-03-20',
            isTradingDay: true,
            isMarketOpenNow: true,
            isPartialBar: true,
            minutesToOpen: null,
            minutesToClose: 150,
            triggerSource: 'api',
            analysisIntent: 'auto',
            warnings: [],
          },
        }}
        summary={baseSummary}
      />,
    );

    expect(screen.getByLabelText('市場階段: CN · 盤中')).toBeInTheDocument();
    expect(screen.getByText('市場階段: CN · 盤中')).toBeVisible();
    expect(screen.getByLabelText('日線未完成')).toBeInTheDocument();
  });

  it('renders English final market phase and partial-bar labels', () => {
    render(
      <ReportOverview
        meta={{
          ...baseMeta,
          reportLanguage: 'en',
          marketPhaseSummary: {
            market: 'us',
            phase: 'postmarket',
            marketLocalTime: '2026-03-21T16:30:00-04:00',
            sessionDate: '2026-03-21',
            effectiveDailyBarDate: '2026-03-21',
            isTradingDay: true,
            isMarketOpenNow: false,
            isPartialBar: true,
            minutesToOpen: null,
            minutesToClose: null,
            triggerSource: 'api',
            analysisIntent: 'auto',
            warnings: [],
          },
        }}
        summary={baseSummary}
      />,
    );

    expect(screen.getByLabelText('Market phase: US · Post-market')).toBeInTheDocument();
    expect(screen.getByLabelText('Partial bar')).toBeInTheDocument();
  });

  it('renders unknown final phase without partial-bar label', () => {
    render(
      <ReportOverview
        meta={{
          ...baseMeta,
          marketPhaseSummary: {
            market: null,
            phase: 'unknown',
            marketLocalTime: null,
            sessionDate: null,
            effectiveDailyBarDate: null,
            isTradingDay: null,
            isMarketOpenNow: null,
            isPartialBar: false,
            minutesToOpen: null,
            minutesToClose: null,
            triggerSource: 'api',
            analysisIntent: 'auto',
            warnings: ['calendar_unavailable'],
          },
        }}
        summary={baseSummary}
      />,
    );

    expect(screen.getByText('市場階段: 階段未知')).toBeVisible();
    expect(screen.queryByText('日線未完成')).not.toBeInTheDocument();
  });

  it('does not render a market phase placeholder for legacy reports', () => {
    render(<ReportOverview meta={baseMeta} summary={baseSummary} />);

    expect(screen.queryByText(/市場階段/)).not.toBeInTheDocument();
    expect(screen.queryByText('日線未完成')).not.toBeInTheDocument();
  });

  it('labels the internal score as system score with provenance', () => {
    render(<ReportOverview meta={baseMeta} summary={baseSummary} />);

    const label = screen.getByText('系統評分');
    expect(label).toBeInTheDocument();
    expect(label).toHaveAttribute('aria-label', expect.stringContaining('非市場官方指數'));
    expect(label).toHaveAttribute('aria-label', expect.stringContaining('非 VIX'));
    expect(label).toHaveAttribute('aria-label', expect.stringContaining('非 VIXTWN'));
    expect(label).toHaveAttribute('aria-label', expect.stringContaining('沒有固定公開公式'));
    expect(screen.queryByText(['恐慌', '貪婪', '指數'].join(''))).not.toBeInTheDocument();
  });

  it('renders market fear index and system score in one dashboard card when snapshot exists', () => {
    render(
      <ReportOverview
        meta={{ ...baseMeta, reportLanguage: 'zh_TW' }}
        summary={{ ...baseSummary, sentimentScore: 42 }}
        details={{
          rawResult: {
            instrumentType: 'etf',
            marketFearIndexSnapshot: {
              market: 'tw',
              kind: 'vixtwn',
              label: '台灣恐慌指數 VIXTWN',
              value: 44.27,
              asOf: '2026-06-26',
              source: 'taifex',
              sourceUrlKey: 'taifex_vixtwn_daily_txt',
              status: 'unknown',
              dataGapReason: null,
            },
          },
        }}
      />,
    );

    const gauge = screen.getByTestId('market-risk-gauge');
    expect(gauge.textContent).toContain('台灣恐慌指數 VIXTWN');
    expect(gauge.textContent).toContain('VIXTWN 44.27');
    expect(gauge.textContent).toContain('日期：2026-06-26');
    expect(gauge.textContent).toContain('系統評分');
    expect(gauge.textContent).toContain('恐慌');
    expect(gauge.textContent).toContain('中性');
    expect(screen.getByTestId('market-fear-meter')).toBeInTheDocument();
    expect(screen.getByTestId('market-fear-meter').querySelectorAll('path')).toHaveLength(4);
    expect(screen.getByTestId('market-fear-pointer')).toBeInTheDocument();
    expect(screen.getByTestId('system-score-pointer')).toBeInTheDocument();
    expect(screen.queryByTestId('market-fear-scale')).not.toBeInTheDocument();
    expect(screen.queryByText('市場情緒')).not.toBeInTheDocument();
  });

  it('renders related boards with leading and lagging markers', () => {
    render(
      <ReportOverview
        meta={baseMeta}
        summary={baseSummary}
        details={{
          belongBoards: [
            { name: ' 白酒 ', type: '行業' },
            { name: '消費', type: '概念' },
            { name: '新能源' },
          ],
          sectorRankings: {
            top: [{ name: '白酒', changePct: 2.31 }],
            bottom: [{ name: '消費', changePct: -1.2 }],
          },
        }}
      />,
    );

    expect(screen.getByText('關聯板塊')).toBeInTheDocument();
    expect(screen.getByText('白酒')).toBeInTheDocument();
    expect(screen.getByText('行業')).toBeInTheDocument();
    expect(screen.getByText('領漲')).toBeInTheDocument();
    expect(screen.getByText('+2.31%')).toBeInTheDocument();
    expect(screen.getByText('領跌')).toBeInTheDocument();
    expect(screen.getByText('-1.20%')).toBeInTheDocument();
    expect(screen.queryByText('中性')).not.toBeInTheDocument();
  });

  it('places related boards below action advice and renders more than three on one row', () => {
    const { container } = render(
      <ReportOverview
        meta={baseMeta}
        summary={baseSummary}
        details={{
          belongBoards: [
            { name: '白酒', type: '行業' },
            { name: '消費', type: '概念' },
            { name: '高階製造' },
            { name: '滬股通' },
          ],
        }}
      />,
    );

    const actionAdviceTitle = screen.getByText('操作建議');
    const relatedBoardsRegion = screen.getByRole('region', { name: '關聯板塊' });
    const boardList = container.querySelector('.home-related-board-list');

    expect(actionAdviceTitle.compareDocumentPosition(relatedBoardsRegion) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByText('滬股通')).toBeInTheDocument();
    expect(boardList).toHaveClass('flex-nowrap', 'overflow-x-auto');
  });

  it('shows board list when rankings are unavailable', () => {
    render(
      <ReportOverview
        meta={baseMeta}
        summary={baseSummary}
        details={{
          belongBoards: [{ name: '半導體', type: '行業' }],
        }}
      />,
    );

    expect(screen.getByText('關聯板塊')).toBeInTheDocument();
    expect(screen.getByText('半導體')).toBeInTheDocument();
    expect(screen.queryByText('中性')).not.toBeInTheDocument();
    expect(screen.queryByText('領漲')).not.toBeInTheDocument();
    expect(screen.queryByText('領跌')).not.toBeInTheDocument();
  });

  it('hides related boards section when no boards are available', () => {
    render(<ReportOverview meta={baseMeta} summary={baseSummary} details={{ belongBoards: [] }} />);

    expect(screen.queryByText('關聯板塊')).not.toBeInTheDocument();
  });

  it('fails open on malformed ranking payloads', () => {
    render(
      <ReportOverview
        meta={baseMeta}
        summary={baseSummary}
        details={{
          belongBoards: [{ name: ' 白酒 ' }],
          sectorRankings: {
            top: {} as unknown as never[],
            bottom: [{ name: '白酒', changePct: '-2.5%' as unknown as number }],
          },
        }}
      />,
    );

    expect(screen.getByText('關聯板塊')).toBeInTheDocument();
    expect(screen.getByText('白酒')).toBeInTheDocument();
    expect(screen.getByText('領跌')).toBeInTheDocument();
    expect(screen.getByText('-2.50%')).toBeInTheDocument();
  });
});
