import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { SidebarNav } from '../SidebarNav';

const mockLogout = vi.fn().mockResolvedValue(undefined);
const mockGetAlphaSiftStatus = vi.fn().mockResolvedValue({ enabled: false, available: false, installSpecIsDefault: false });
const mockThemeToggle = vi.fn(({ collapsed }: { collapsed?: boolean }) => (
  <button type="button">{collapsed ? '切換主題(摺疊)' : '切換主題'}</button>
));

const completionBadgeState = { value: true };

vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => ({
    authEnabled: true,
    logout: mockLogout,
  }),
}));

vi.mock('../../../stores/agentChatStore', () => ({
  useAgentChatStore: (selector: (state: { completionBadge: boolean }) => unknown) =>
    selector({ completionBadge: completionBadgeState.value }),
}));

vi.mock('../../../api/alphasift', () => ({
  ALPHASIFT_CONFIG_CHANGED_EVENT: 'alphasift-config-changed',
  SYSTEM_CONFIG_CHANGED_EVENT: 'dsa-system-config-changed',
  alphasiftApi: {
    getStatus: () => mockGetAlphaSiftStatus(),
  },
}));

vi.mock('../../theme/ThemeToggle', () => ({
  ThemeToggle: (props: { collapsed?: boolean }) => mockThemeToggle(props),
}));

describe('SidebarNav', () => {
  it('hides the screening navigation item while AlphaSift is disabled', () => {
    mockGetAlphaSiftStatus.mockResolvedValueOnce({ enabled: false, available: false, installSpecIsDefault: false });

    render(
      <MemoryRouter initialEntries={['/']}>
        <SidebarNav />
      </MemoryRouter>,
    );

    expect(screen.queryByRole('link', { name: '選股' })).not.toBeInTheDocument();
  });

  it('shows the screening navigation item when AlphaSift is enabled', async () => {
    mockGetAlphaSiftStatus.mockResolvedValueOnce({ enabled: true, available: false, installSpecIsDefault: false });

    render(
      <MemoryRouter initialEntries={['/']}>
        <SidebarNav />
      </MemoryRouter>,
    );

    expect(await screen.findByRole('link', { name: '選股' })).toHaveAttribute('href', '/screening');
  });

  it('places screening directly after chat when AlphaSift is enabled', async () => {
    mockGetAlphaSiftStatus.mockResolvedValueOnce({ enabled: true, available: false, installSpecIsDefault: false });

    render(
      <MemoryRouter initialEntries={['/']}>
        <SidebarNav />
      </MemoryRouter>,
    );

    await screen.findByRole('link', { name: '選股' });
    const hrefs = screen.getAllByRole('link').map((link) => link.getAttribute('href'));
    expect(hrefs.slice(0, 4)).toEqual(['/', '/chat', '/screening', '/portfolio']);
  });

  it('refreshes the screening navigation item after any config save event', async () => {
    mockGetAlphaSiftStatus
      .mockResolvedValueOnce({ enabled: false, available: false, installSpecIsDefault: false })
      .mockResolvedValueOnce({ enabled: true, available: false, installSpecIsDefault: false });

    render(
      <MemoryRouter initialEntries={['/']}>
        <SidebarNav />
      </MemoryRouter>,
    );

    expect(screen.queryByRole('link', { name: '選股' })).not.toBeInTheDocument();
    window.dispatchEvent(new Event('dsa-system-config-changed'));

    expect(await screen.findByRole('link', { name: '選股' })).toHaveAttribute('href', '/screening');
    await waitFor(() => expect(mockGetAlphaSiftStatus.mock.calls.length).toBeGreaterThanOrEqual(2));
  });

  it('shows the shared completion badge only when chat completion is pending', () => {
    completionBadgeState.value = true;

    const { rerender } = render(
      <MemoryRouter initialEntries={['/chat']}>
        <SidebarNav />
      </MemoryRouter>,
    );

    expect(screen.getByTestId('chat-completion-badge')).toBeInTheDocument();
    expect(screen.getByLabelText('問股有新訊息')).toBeInTheDocument();

    completionBadgeState.value = false;
    rerender(
      <MemoryRouter initialEntries={['/chat']}>
        <SidebarNav />
      </MemoryRouter>,
    );

    expect(screen.queryByTestId('chat-completion-badge')).not.toBeInTheDocument();
  });

  it('renders the collapsed theme toggle variant when the sidebar is collapsed', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <SidebarNav collapsed />
      </MemoryRouter>,
    );

    expect(mockThemeToggle).toHaveBeenCalledWith(
      expect.objectContaining({ variant: 'nav', collapsed: true }),
    );
    expect(screen.getByRole('button', { name: '切換主題(摺疊)' })).toBeInTheDocument();
  });

  it('renders the alerts navigation item and marks it active', () => {
    render(
      <MemoryRouter initialEntries={['/alerts']}>
        <SidebarNav />
      </MemoryRouter>,
    );

    const alertsLink = screen.getByRole('link', { name: '警告' });
    expect(alertsLink).toHaveAttribute('href', '/alerts');
    expect(alertsLink).toHaveClass('font-medium');
  });

  it('opens the logout confirmation and confirms logout', async () => {
    render(
      <MemoryRouter initialEntries={['/chat']}>
        <SidebarNav />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', { name: '登出' }));

    expect(await screen.findByRole('heading', { name: '退出登入' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '確認退出' }));
    expect(mockLogout).toHaveBeenCalled();
  });
});
