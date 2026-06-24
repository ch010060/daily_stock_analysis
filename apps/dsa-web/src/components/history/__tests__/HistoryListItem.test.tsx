import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { HistoryListItem } from '../HistoryListItem';
import type { HistoryItem } from '../../../types/analysis';

const legacyMarketReviewItem: HistoryItem = {
  id: 2,
  queryId: 'q-market-review-1',
  stockCode: 'MARKET',
  stockName: '大盤覆盤',
  sentimentScore: 50,
  operationAdvice: '檢視覆盤',
  createdAt: '2026-06-23T08:00:00Z',
};

describe('HistoryListItem', () => {
  it('shows the 市場概覽 title for the MARKET pseudo-record even when the persisted name is the legacy 大盤覆盤 wording', () => {
    render(
      <HistoryListItem
        item={legacyMarketReviewItem}
        isViewing={false}
        isChecked={false}
        isDeleting={false}
        onToggleChecked={vi.fn()}
        onClick={vi.fn()}
      />,
    );

    expect(screen.getByText('市場概覽')).toBeInTheDocument();
    expect(screen.queryByText('大盤覆盤')).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /^市場概覽 MARKET 歷史記錄$/ }),
    ).toBeInTheDocument();
  });
});
