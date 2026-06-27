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
    expect(mermaid.initialize).toHaveBeenCalledWith(expect.objectContaining({
      securityLevel: 'strict',
      theme: 'base',
      themeVariables: expect.objectContaining({
        primaryTextColor: '#111827',
        clusterBkg: '#f8fafc',
      }),
      flowchart: expect.objectContaining({
        htmlLabels: false,
      }),
    }));
    expect(screen.queryByTestId('mermaid-fallback')).not.toBeInTheDocument();
  });

  it('applies inline report tuning to generated svg labels and center nodes', async () => {
    vi.mocked(mermaid.render).mockResolvedValue({
      svg: [
        '<svg data-testid="fake-svg" viewBox="0 0 100 80">',
        '<g class="node center"><rect /><text><tspan class="nodeLabel">富邦台50</tspan></text></g>',
        '</svg>',
      ].join(''),
      diagramType: 'flowchart',
    });

    render(<MermaidDiagram code={'flowchart TB\n  A["富邦台50"]'} />);

    await waitFor(() => {
      expect(screen.getByTestId('mermaid-diagram')).toBeInTheDocument();
    });
    const container = screen.getByTestId('mermaid-diagram');
    expect((container.querySelector('.nodeLabel') as HTMLElement).style.fontSize).toBe('13px');
    expect((container.querySelector('.node.center rect') as SVGElement).style.fill).toBe('#fffdfa');
    expect(container.querySelector('svg')?.getAttribute('viewBox')).toBe('-44 -44 188 168');
    expect(container.querySelector('svg')?.getAttribute('preserveAspectRatio')).toBe('xMidYMid meet');
  });

  it('replaces dark center/card class definitions with readable report classes', async () => {
    vi.mocked(mermaid.render).mockResolvedValue({
      svg: '<svg data-testid="fake-svg"></svg>',
      diagramType: 'flowchart',
    });

    render(
      <MermaidDiagram
        code={[
          'flowchart TB',
          '  C["Microsoft (MSFT.US)<br/>雲端/AI"]',
          '  classDef center fill:#111827,stroke:#111827,color:#ffffff;',
          '  classDef card fill:#0f172a,color:#ffffff;',
          '  class C center',
        ].join('\n')}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId('mermaid-diagram')).toBeInTheDocument();
    });
    expect(mermaid.render).toHaveBeenCalledWith(
      expect.any(String),
      expect.stringContaining('classDef center fill:#fffdfa,stroke:#1e3a5f,stroke-width:2px,color:#111827;')
    );
    expect(mermaid.render).toHaveBeenCalledWith(
      expect.any(String),
      expect.not.stringContaining('fill:#111827')
    );
  });

  it('strips source-level mermaid init directives so report theme controls sizing', async () => {
    vi.mocked(mermaid.render).mockResolvedValue({
      svg: '<svg data-testid="fake-svg"></svg>',
      diagramType: 'flowchart',
    });

    render(
      <MermaidDiagram
        code={[
          "%%{init: {'themeVariables': {'fontSize': '20px'}}}%%",
          'flowchart TB',
          '  C["富邦台50<br/>(006208.TW)<br/>市值型台股ETF"]',
          '  classDef center fill:#0f172a,color:#ffffff;',
          '  class C center',
        ].join('\n')}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId('mermaid-diagram')).toBeInTheDocument();
    });
    expect(mermaid.render).toHaveBeenCalledWith(
      expect.any(String),
      expect.not.stringContaining('fontSize')
    );
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

  it('allows horizontal overflow scroll instead of clipping wide A4 card layouts', async () => {
    vi.mocked(mermaid.render).mockResolvedValue({
      svg: '<svg data-testid="fake-svg"></svg>',
      diagramType: 'flowchart',
    });

    render(<MermaidDiagram code={'flowchart TB\n  A["Start"] --> B["End"]'} />);

    await waitFor(() => {
      expect(screen.getByTestId('mermaid-diagram')).toBeInTheDocument();
    });
    const container = screen.getByTestId('mermaid-diagram');
    expect(container.style.overflowX).toBe('auto');
    expect(container.style.maxWidth).toBe('100%');
  });
});
