import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { StockBarItemComponent } from '../StockBarItem';
import type { StockBarItem } from '../../../types/analysis';

const issue1600Item: StockBarItem = {
  id: 1,
  stockCode: '2330',
  stockName: '台積電股份有限公司',
  sentimentScore: 62,
  operationAdvice: '觀望',
  analysisCount: 2,
  lastAnalysisTime: '2026-05-31T04:52:00Z',
  marketPhaseSummary: {
    market: 'CN',
    phase: 'non_trading',
    warnings: [],
  },
};

const legacyMarketReviewItem: StockBarItem = {
  id: 2,
  stockCode: 'MARKET',
  stockName: '大盤覆盤',
  sentimentScore: 50,
  operationAdvice: '檢視覆盤',
  analysisCount: 1,
  lastAnalysisTime: '2026-06-23T08:00:00Z',
};

describe('StockBarItemComponent', () => {
  it('shows the 台股日報 title for the MARKET pseudo-record even when the persisted name is the legacy 大盤覆盤 wording', () => {
    render(
      <StockBarItemComponent
        item={legacyMarketReviewItem}
        isViewing={false}
        onClick={vi.fn()}
        onDelete={vi.fn()}
        isMarketReview
      />,
    );

    expect(screen.getByText('台股日報')).toBeInTheDocument();
    expect(screen.queryByText('大盤覆盤')).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /^台股日報 MARKET 歷史記錄$/ }),
    ).toBeInTheDocument();
  });

  it('keeps market phase in the meta row instead of the action row', () => {
    render(
      <StockBarItemComponent
        item={issue1600Item}
        isViewing={false}
        onClick={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    const actions = screen.getByTestId('history-card-actions');
    const meta = screen.getByTestId('history-card-meta');

    expect(within(actions).getByText('觀望 62')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /刪除 台積電股份有限公司 歷史記錄/ })).toBeInTheDocument();
    expect(within(actions).queryByRole('button', { name: /刪除 台積電股份有限公司 歷史記錄/ })).not.toBeInTheDocument();
    expect(within(actions).queryByText('CN · 非交易日')).not.toBeInTheDocument();
    expect(within(meta).getByText('CN · 非交易日')).toBeVisible();

    expect(screen.getByText('台積電股份有限公.')).toBeVisible();
    expect(
      screen.getByRole('button', {
        name: /^台積電股份有限公司 2330 歷史記錄$/,
      }),
    ).toBeInTheDocument();
  });

  it('does not nest the delete button inside the row activation control', () => {
    render(
      <StockBarItemComponent
        item={issue1600Item}
        isViewing={false}
        onClick={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    const row = screen.getByRole('button', {
      name: /^台積電股份有限公司 2330 歷史記錄$/,
    });

    expect(row.querySelector('button')).toBeNull();
  });

  it('keeps row activation and delete action separate for mouse and keyboard users', () => {
    const onClick = vi.fn();
    const onDelete = vi.fn();
    render(
      <StockBarItemComponent
        item={issue1600Item}
        isViewing={false}
        onClick={onClick}
        onDelete={onDelete}
      />,
    );

    const row = screen.getByRole('button', {
      name: /^台積電股份有限公司 2330 歷史記錄$/,
    });
    const deleteButton = screen.getByRole('button', {
      name: /刪除 台積電股份有限公司 歷史記錄/,
    });

    fireEvent.click(row);
    expect(onClick).toHaveBeenCalledWith(issue1600Item.id);

    fireEvent.click(deleteButton);
    expect(onDelete).toHaveBeenCalledWith(issue1600Item.stockCode);
    expect(onClick).toHaveBeenCalledTimes(1);

    fireEvent.keyDown(row, { key: 'Enter' });
    fireEvent.keyDown(row, { key: ' ' });
    expect(onClick).toHaveBeenCalledTimes(3);
  });
});
