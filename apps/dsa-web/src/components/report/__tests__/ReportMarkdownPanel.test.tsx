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

});
