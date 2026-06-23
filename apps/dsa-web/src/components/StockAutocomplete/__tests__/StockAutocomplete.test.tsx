/**
 * StockAutocomplete component tests.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { StockAutocomplete } from '../StockAutocomplete';
import type { StockIndexItem, StockSuggestion } from '../../../types/stockIndex';

let stockIndexHookImpl: () => {
  index: StockIndexItem[];
  loading: boolean;
  fallback: boolean;
  error: Error | null;
  loaded: boolean;
};

let autocompleteHookImpl: () => {
  query: string;
  setQuery: ReturnType<typeof vi.fn>;
  suggestions: StockSuggestion[];
  isOpen: boolean;
  highlightedIndex: number;
  setHighlightedIndex: ReturnType<typeof vi.fn>;
  highlightPrevious: ReturnType<typeof vi.fn>;
  highlightNext: ReturnType<typeof vi.fn>;
  handleSelect: ReturnType<typeof vi.fn>;
  close: ReturnType<typeof vi.fn>;
  reset: ReturnType<typeof vi.fn>;
  isComposing: boolean;
  setIsComposing: ReturnType<typeof vi.fn>;
  runtimeFallback: boolean;
  error: Error | null;
};

// Mock the hooks
vi.mock('../../../hooks/useStockIndex', () => ({
  useStockIndex: () => stockIndexHookImpl(),
}));

vi.mock('../../../hooks/useAutocomplete', () => ({
  useAutocomplete: () => autocompleteHookImpl(),
}));

const mockIndex: StockIndexItem[] = [
  {
    canonicalCode: "2308",
    displayCode: "2308",
    nameZh: "台達電",
    pinyinFull: "taidadian",
    pinyinAbbr: "tdd",
    aliases: ["Delta Electronics"],
    market: "TW",
    assetType: "stock",
    active: true,
    popularity: 100,
  },
];

const mockSuggestions: StockSuggestion[] = [
  {
    canonicalCode: "2308",
    displayCode: "2308",
    nameZh: "台達電",
    market: "TW",
    matchType: "exact" as const,
    matchField: "code" as const,
    score: 100,
  },
];

const twSuggestion: StockSuggestion = {
  canonicalCode: "3008",
  displayCode: "3008",
  nameZh: "大立光",
  market: "TW" as const,
  matchType: "exact" as const,
  matchField: "name" as const,
  score: 98,
};

const phisonSuggestion: StockSuggestion = {
  canonicalCode: "8299",
  displayCode: "8299",
  nameZh: "群聯",
  market: "TW" as const,
  matchType: "exact" as const,
  matchField: "alias" as const,
  score: 97,
};

const metaSuggestion: StockSuggestion = {
  canonicalCode: "META",
  displayCode: "META",
  nameZh: "Meta Platforms",
  market: "US" as const,
  matchType: "exact" as const,
  matchField: "alias" as const,
  score: 97,
};

const ambiguousFirstFinancialSuggestions: StockSuggestion[] = [
  {
    canonicalCode: "THFF",
    displayCode: "THFF",
    nameZh: "First Financial",
    market: "US" as const,
    matchType: "exact" as const,
    matchField: "name" as const,
    score: 98,
  },
  {
    canonicalCode: "2892",
    displayCode: "2892",
    nameZh: "第一金",
    market: "TW" as const,
    matchType: "exact" as const,
    matchField: "alias" as const,
    score: 97,
  },
];

describe('StockAutocomplete', () => {
  const mockOnChange = vi.fn();
  const mockOnSubmit = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    stockIndexHookImpl = () => ({
      index: mockIndex,
      loading: false,
      fallback: false,
      error: null,
      loaded: true,
    });
    autocompleteHookImpl = () => ({
      query: '',
      setQuery: vi.fn(),
      suggestions: mockSuggestions,
      isOpen: false,
      highlightedIndex: -1,
      setHighlightedIndex: vi.fn(),
      highlightPrevious: vi.fn(),
      highlightNext: vi.fn(),
      handleSelect: vi.fn(),
      close: vi.fn(),
      reset: vi.fn(),
      isComposing: false,
      setIsComposing: vi.fn(),
      runtimeFallback: false,
      error: null,
    });
  });

  it('renders the input element', () => {
    render(
      <StockAutocomplete
        value=""
        onChange={mockOnChange}
        onSubmit={mockOnSubmit}
      />
    );

    const input = screen.getByPlaceholderText(/輸入股票代號或名稱/);
    expect(input).toBeInTheDocument();
  });

  it('renders a custom placeholder', () => {
    render(
      <StockAutocomplete
        value=""
        onChange={mockOnChange}
        onSubmit={mockOnSubmit}
        placeholder="請輸入代號"
      />
    );

    const input = screen.getByPlaceholderText(/請輸入代號/);
    expect(input).toBeInTheDocument();
  });

  it('renders the current value', () => {
    render(
      <StockAutocomplete
        value="2308"
        onChange={mockOnChange}
        onSubmit={mockOnSubmit}
      />
    );

    const input = screen.getByDisplayValue('2308');
    expect(input).toBeInTheDocument();
  });

  it('supports the disabled state', () => {
    render(
      <StockAutocomplete
        value=""
        onChange={mockOnChange}
        onSubmit={mockOnSubmit}
        disabled={true}
      />
    );

    const input = screen.getByRole('combobox');
    expect(input).toBeDisabled();
  });

  it('calls onChange when the input changes', () => {
    render(
      <StockAutocomplete
        value=""
        onChange={mockOnChange}
        onSubmit={mockOnSubmit}
      />
    );

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: '2308' } });

    expect(mockOnChange).toHaveBeenCalledWith('2308');
  });

  it('applies a custom class name', () => {
    const { container } = render(
      <StockAutocomplete
        value=""
        onChange={mockOnChange}
        onSubmit={mockOnSubmit}
        className="custom-class"
      />
    );

    const input = container.querySelector('.custom-class');
    expect(input).toBeInTheDocument();
  });

  it('exposes the expected accessibility attributes', () => {
    render(
      <StockAutocomplete
        value=""
        onChange={mockOnChange}
        onSubmit={mockOnSubmit}
      />
    );

    const input = screen.getByRole('combobox');
    expect(input).toHaveAttribute('aria-autocomplete', 'none');
    expect(input).toHaveAttribute('role', 'combobox');
  });

  describe('fallback mode', () => {
    it('renders a plain input when index loading fallback is active', () => {
      stockIndexHookImpl = () => ({
        index: [],
        loading: false,
        fallback: true,
        error: new Error('Index load failed'),
        loaded: false,
      });

      render(
        <StockAutocomplete
          value=""
          onChange={mockOnChange}
          onSubmit={mockOnSubmit}
        />
      );

      const input = screen.getByPlaceholderText(/輸入股票代號或名稱/);
      expect(input).toHaveAttribute('data-autocomplete-mode', 'fallback');
    });

    it('renders a plain input when autocomplete runtime fallback is active', () => {
      autocompleteHookImpl = () => ({
        query: '',
        setQuery: vi.fn(),
        suggestions: [],
        isOpen: false,
        highlightedIndex: -1,
        setHighlightedIndex: vi.fn(),
        highlightPrevious: vi.fn(),
        highlightNext: vi.fn(),
        handleSelect: vi.fn(),
        close: vi.fn(),
        reset: vi.fn(),
        isComposing: false,
        setIsComposing: vi.fn(),
        runtimeFallback: true,
        error: new Error('Search crashed'),
      });

      render(
        <StockAutocomplete
          value=""
          onChange={mockOnChange}
          onSubmit={mockOnSubmit}
        />
      );

      const input = screen.getByPlaceholderText(/輸入股票代號或名稱/);
      expect(input).toHaveAttribute('data-autocomplete-mode', 'fallback');
    });

    it('submits manually when fallback input receives Enter', () => {
      autocompleteHookImpl = () => ({
        query: '',
        setQuery: vi.fn(),
        suggestions: [],
        isOpen: false,
        highlightedIndex: -1,
        setHighlightedIndex: vi.fn(),
        highlightPrevious: vi.fn(),
        highlightNext: vi.fn(),
        handleSelect: vi.fn(),
        close: vi.fn(),
        reset: vi.fn(),
        isComposing: false,
        setIsComposing: vi.fn(),
        runtimeFallback: true,
          error: new Error('Search crashed'),
      });

      render(
        <StockAutocomplete
          value="2308"
          onChange={mockOnChange}
          onSubmit={mockOnSubmit}
        />
      );

      const input = screen.getByDisplayValue('2308');
      fireEvent.keyDown(input, { key: 'Enter' });

      expect(mockOnSubmit).toHaveBeenCalledWith('2308');
    });
  });

  describe('IME support', () => {
    it('handles composition start and end events', () => {
      render(
        <StockAutocomplete
          value=""
          onChange={mockOnChange}
          onSubmit={mockOnSubmit}
        />
      );

      const input = screen.getByRole('combobox');

      fireEvent.compositionStart(input);
      fireEvent.compositionEnd(input);

      // The events should be handled without throwing.
      expect(input).toBeInTheDocument();
    });
  });

  describe('keyboard submission', () => {
    it('submits the raw input when suggestions are open but nothing is highlighted', () => {
      autocompleteHookImpl = () => ({
        query: '',
        setQuery: vi.fn(),
        suggestions: mockSuggestions,
        isOpen: true,
        highlightedIndex: -1,
        setHighlightedIndex: vi.fn(),
        highlightPrevious: vi.fn(),
        highlightNext: vi.fn(),
        handleSelect: vi.fn(),
        close: vi.fn(),
        reset: vi.fn(),
        isComposing: false,
        setIsComposing: vi.fn(),
        runtimeFallback: false,
        error: null,
      });

      render(
        <StockAutocomplete
          value="230"
          onChange={mockOnChange}
          onSubmit={mockOnSubmit}
        />
      );

      const input = screen.getByDisplayValue('230');
      fireEvent.keyDown(input, { key: 'Enter' });

      expect(mockOnSubmit).toHaveBeenCalledWith('230');
    });

    it('does not auto-submit the first candidate for ambiguous cross-market exact aliases', () => {
      autocompleteHookImpl = () => ({
        query: '',
        setQuery: vi.fn(),
        suggestions: ambiguousFirstFinancialSuggestions,
        isOpen: true,
        highlightedIndex: -1,
        setHighlightedIndex: vi.fn(),
        highlightPrevious: vi.fn(),
        highlightNext: vi.fn(),
        handleSelect: vi.fn(),
        close: vi.fn(),
        reset: vi.fn(),
        isComposing: false,
        setIsComposing: vi.fn(),
        runtimeFallback: false,
        error: null,
      });

      render(
        <StockAutocomplete
          value="First Financial"
          onChange={mockOnChange}
          onSubmit={mockOnSubmit}
        />,
      );

      const input = screen.getByDisplayValue('First Financial');
      fireEvent.keyDown(input, { key: 'Enter' });

      expect(mockOnSubmit).toHaveBeenCalledWith('First Financial');
      expect(mockOnSubmit).not.toHaveBeenCalledWith('THFF', 'First Financial', 'autocomplete');
      expect(mockOnSubmit).not.toHaveBeenCalledWith('2892', '第一金', 'autocomplete');
    });

    it('submits the highlighted suggestion when one is explicitly selected', () => {
      autocompleteHookImpl = () => ({
        query: '',
        setQuery: vi.fn(),
        suggestions: mockSuggestions,
        isOpen: true,
        highlightedIndex: 0,
        setHighlightedIndex: vi.fn(),
        highlightPrevious: vi.fn(),
        highlightNext: vi.fn(),
        handleSelect: vi.fn(),
        close: vi.fn(),
        reset: vi.fn(),
        isComposing: false,
        setIsComposing: vi.fn(),
        runtimeFallback: false,
        error: null,
      });

      render(
        <StockAutocomplete
          value="2308"
          onChange={mockOnChange}
          onSubmit={mockOnSubmit}
        />
      );

      const input = screen.getByDisplayValue('2308');
      fireEvent.keyDown(input, { key: 'Enter' });

      expect(mockOnChange).toHaveBeenCalledWith('2308');
      expect(mockOnSubmit).toHaveBeenCalledWith('2308', '台達電', 'autocomplete');
    });

    it('renders and submits the highlighted TW suggestion', async () => {
      const requestAnimationFrameSpy = vi
        .spyOn(window, 'requestAnimationFrame')
        .mockImplementation((callback) => {
          callback(0);
          return 0;
        });
      const cancelAnimationFrameSpy = vi
        .spyOn(window, 'cancelAnimationFrame')
        .mockImplementation(() => undefined);
      autocompleteHookImpl = () => ({
        query: '',
        setQuery: vi.fn(),
        suggestions: [twSuggestion],
        isOpen: true,
        highlightedIndex: 0,
        setHighlightedIndex: vi.fn(),
        highlightPrevious: vi.fn(),
        highlightNext: vi.fn(),
        handleSelect: vi.fn(),
        close: vi.fn(),
        reset: vi.fn(),
        isComposing: false,
        setIsComposing: vi.fn(),
        runtimeFallback: false,
        error: null,
      });

      try {
        render(
          <StockAutocomplete
            value="大立光"
            onChange={mockOnChange}
            onSubmit={mockOnSubmit}
          />,
        );

        expect(await screen.findByText('台股')).toBeInTheDocument();
        expect(screen.getAllByText('大立光').length).toBeGreaterThan(0);

        const input = screen.getByDisplayValue('大立光');
        fireEvent.keyDown(input, { key: 'Enter' });

        expect(mockOnChange).toHaveBeenCalledWith('3008');
        expect(mockOnSubmit).toHaveBeenCalledWith('3008', '大立光', 'autocomplete');
      } finally {
        requestAnimationFrameSpy.mockRestore();
        cancelAnimationFrameSpy.mockRestore();
      }
    });

    it('submits selected Route B natural-name candidates with canonical symbols', () => {
      autocompleteHookImpl = () => ({
        query: '',
        setQuery: vi.fn(),
        suggestions: [phisonSuggestion, metaSuggestion],
        isOpen: true,
        highlightedIndex: 0,
        setHighlightedIndex: vi.fn(),
        highlightPrevious: vi.fn(),
        highlightNext: vi.fn(),
        handleSelect: vi.fn(),
        close: vi.fn(),
        reset: vi.fn(),
        isComposing: false,
        setIsComposing: vi.fn(),
        runtimeFallback: false,
        error: null,
      });

      render(
        <StockAutocomplete
          value="Phison"
          onChange={mockOnChange}
          onSubmit={mockOnSubmit}
        />,
      );

      const input = screen.getByDisplayValue('Phison');
      fireEvent.keyDown(input, { key: 'Enter' });

      expect(mockOnChange).toHaveBeenCalledWith('8299');
      expect(mockOnSubmit).toHaveBeenCalledWith('8299', '群聯', 'autocomplete');
    });
  });

  describe('runtime boundary', () => {
    it('falls back to the plain input when the autocomplete tree throws during render', () => {
      autocompleteHookImpl = () => {
        throw new Error('Autocomplete render failed');
      };

      render(
        <StockAutocomplete
          value="META"
          onChange={mockOnChange}
          onSubmit={mockOnSubmit}
        />
      );

      const input = screen.getByDisplayValue('META');
      expect(input).toHaveAttribute('data-autocomplete-mode', 'fallback');
    });

    it('falls back to the plain input when a suggestion contains an unsupported market', () => {
      const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      autocompleteHookImpl = () => ({
        query: '',
        setQuery: vi.fn(),
        suggestions: [
          {
            canonicalCode: 'TEST.OTC',
            displayCode: 'TEST',
            nameZh: '測試市場',
            market: 'OTC' as never,
            matchType: 'exact' as const,
            matchField: 'code' as const,
            score: 100,
          },
        ],
        isOpen: true,
        highlightedIndex: 0,
        setHighlightedIndex: vi.fn(),
        highlightPrevious: vi.fn(),
        highlightNext: vi.fn(),
        handleSelect: vi.fn(),
        close: vi.fn(),
        reset: vi.fn(),
        isComposing: false,
        setIsComposing: vi.fn(),
        runtimeFallback: false,
        error: null,
      });

      render(
        <StockAutocomplete
          value="TEST"
          onChange={mockOnChange}
          onSubmit={mockOnSubmit}
        />
      );

      const input = screen.getByDisplayValue('TEST');
      fireEvent.focus(input);

      const fallbackInput = screen.getByDisplayValue('TEST');
      expect(fallbackInput).toHaveAttribute('data-autocomplete-mode', 'fallback');
      expect(consoleErrorSpy).toHaveBeenCalled();
      consoleErrorSpy.mockRestore();
    });
  });
});
