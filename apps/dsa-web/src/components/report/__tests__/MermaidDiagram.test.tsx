import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import mermaid from 'mermaid';
import { MermaidDiagram } from '../MermaidDiagram';

vi.mock('mermaid', () => ({
  default: {
    initialize: vi.fn(),
    render: vi.fn(),
  },
}));

describe('MermaidDiagram', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the success container when mermaid.render resolves with valid svg', async () => {
    vi.mocked(mermaid.render).mockResolvedValue({
      svg: '<svg data-testid="fake-svg"></svg>',
      diagramType: 'flowchart',
    });

    render(<MermaidDiagram code={'flowchart TB\n  A["Start"] --> B["End"]'} />);

    await waitFor(() => {
      expect(screen.getByTestId('mermaid-diagram')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('mermaid-fallback')).not.toBeInTheDocument();
  });

  it('renders the fallback container when mermaid.render rejects (invalid syntax)', async () => {
    vi.mocked(mermaid.render).mockRejectedValue(new Error('invalid mermaid syntax'));

    const code = 'flowchart TB\n  A["Start" --> B["End"]';
    render(<MermaidDiagram code={code} />);

    await waitFor(() => {
      expect(screen.getByTestId('mermaid-fallback')).toBeInTheDocument();
    });
    const fallback = screen.getByTestId('mermaid-fallback');
    expect(
      screen.getByText('價值網路圖暫時無法渲染，已保留 Mermaid 原始內容。')
    ).toBeInTheDocument();
    expect(fallback.textContent).toContain(code);
    expect(screen.queryByTestId('mermaid-diagram')).not.toBeInTheDocument();
  });

  it('goes straight to fallback without calling mermaid.render when content looks dangerous (script tag)', async () => {
    const code = 'flowchart TB\n  A["<script>alert(1)</script>"] --> B';
    const { container } = render(<MermaidDiagram code={code} />);

    await waitFor(() => {
      expect(screen.getByTestId('mermaid-fallback')).toBeInTheDocument();
    });
    expect(mermaid.render).not.toHaveBeenCalled();
    expect(container.querySelector('script')).toBeNull();
  });

  it('goes straight to fallback without calling mermaid.render when content has an event-handler attribute', async () => {
    const code = 'flowchart TB\n  A["x" onerror="alert(1)"] --> B';
    render(<MermaidDiagram code={code} />);

    await waitFor(() => {
      expect(screen.getByTestId('mermaid-fallback')).toBeInTheDocument();
    });
    expect(mermaid.render).not.toHaveBeenCalled();
  });
});
