import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { JsonViewer } from '../JsonViewer';

describe('JsonViewer', () => {
  it('escapes JSON string values before syntax highlighting', () => {
    const { container } = render(
      <JsonViewer
        data={{
          analysis_summary: '<img src=x onerror=alert(1)>',
          risk_warning: '<script>alert(1)</script>',
          safe_link: 'https://example.com/news',
          zh_tw: '繁體中文內容應保留',
        }}
      />
    );

    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('script')).toBeNull();
    expect(container.innerHTML).not.toContain('onerror=');
    expect(screen.getByText(/繁體中文內容應保留/)).toBeInTheDocument();
    expect(screen.getByText(/https:\/\/example\.com\/news/)).toBeInTheDocument();
  });
});
