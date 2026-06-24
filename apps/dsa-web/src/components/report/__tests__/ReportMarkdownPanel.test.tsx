import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { historyApi } from '../../../api/history';
import { ReportMarkdownPanel } from '../ReportMarkdownPanel';

vi.mock('../../../api/history', () => ({
  historyApi: {
    getMarkdown: vi.fn(),
  },
}));

vi.mock('../MermaidDiagram', () => ({
  MermaidDiagram: (props: { code: string }) => (
    <div data-testid="mermaid-stub">{props.code}</div>
  ),
}));

describe('ReportMarkdownPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
});
