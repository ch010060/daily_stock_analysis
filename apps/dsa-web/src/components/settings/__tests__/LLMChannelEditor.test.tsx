import { useState } from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LLMChannelEditor } from '../LLMChannelEditor';

const {
  update,
  testLLMChannel,
  discoverLLMChannelModels,
} = vi.hoisted(() => ({
  update: vi.fn(),
  testLLMChannel: vi.fn(),
  discoverLLMChannelModels: vi.fn(),
}));

vi.mock('../../../api/systemConfig', () => ({
  systemConfigApi: {
    update: (...args: unknown[]) => update(...args),
    testLLMChannel: (...args: unknown[]) => testLLMChannel(...args),
    discoverLLMChannelModels: (...args: unknown[]) => discoverLLMChannelModels(...args),
  },
}));

describe('LLMChannelEditor', () => {
  beforeEach(() => {
    update.mockReset();
    testLLMChannel.mockReset();
    discoverLLMChannelModels.mockReset();
  });

  it('renders API Key input with controlled visibility', async () => {
    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'openai' },
          { key: 'LLM_OPENAI_PROTOCOL', value: 'openai' },
          { key: 'LLM_OPENAI_BASE_URL', value: 'https://api.openai.com/v1' },
          { key: 'LLM_OPENAI_ENABLED', value: 'true' },
          { key: 'LLM_OPENAI_API_KEY', value: 'secret-key' },
          { key: 'LLM_OPENAI_MODELS', value: 'gpt-4o-mini' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /OpenAI 官方/i }));

    const input = await screen.findByLabelText('API Key');
    expect(input).toHaveAttribute('type', 'password');

    fireEvent.click(screen.getByRole('button', { name: '顯示內容' }));
    expect(input).toHaveAttribute('type', 'text');
  });

  it('shows help dialogs for channel editor fields', async () => {
    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_PROTOCOL', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_BASE_URL', value: 'https://api.deepseek.com' },
          { key: 'LLM_DEEPSEEK_ENABLED', value: 'true' },
          { key: 'LLM_DEEPSEEK_API_KEY', value: 'sk-test' },
          { key: 'LLM_DEEPSEEK_MODELS', value: 'deepseek-v4-flash' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek 官方/i }));
    fireEvent.click(await screen.findByRole('button', { name: '檢視 Base URL 配置說明' }));

    expect(screen.getByRole('dialog', { name: 'Base URL' })).toBeInTheDocument();
    expect(screen.getByText('該通道的介面根地址。')).toBeInTheDocument();
    expect(screen.getByText('LLM_DEEPSEEK_BASE_URL=https://api.deepseek.com')).toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });
    fireEvent.click(await screen.findByRole('button', { name: '檢視 Temperature 配置說明' }));

    expect(screen.getByRole('dialog', { name: 'Temperature' })).toBeInTheDocument();
    expect(screen.getByText('執行時統一取樣溫度。')).toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });
    fireEvent.click(await screen.findByRole('button', { name: '檢視 執行時能力檢測 配置說明' }));

    expect(screen.getByRole('dialog', { name: '執行時能力檢測' })).toBeInTheDocument();
    expect(screen.getByText('選擇能力後點選檢測；檢測會發起真實 LLM 請求。')).toBeInTheDocument();
  });

  it('hides LiteLLM wording when advanced YAML routing is enabled', () => {
    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'openai' },
          { key: 'LITELLM_CONFIG', value: './litellm_config.yaml' },
          { key: 'LLM_OPENAI_PROTOCOL', value: 'openai' },
          { key: 'LLM_OPENAI_BASE_URL', value: 'https://api.openai.com/v1' },
          { key: 'LLM_OPENAI_ENABLED', value: 'true' },
          { key: 'LLM_OPENAI_API_KEY', value: 'secret-key' },
          { key: 'LLM_OPENAI_MODELS', value: 'gpt-4o-mini' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    expect(screen.getByText(/檢測到已配置高階模型路由 YAML/i)).toBeInTheDocument();
    expect(screen.getByText(/執行時主模型 \/ 備選模型 \/ Vision \/ Temperature 仍由下方通用欄位決定/i)).toBeInTheDocument();
    expect(screen.queryByText(/LiteLLM/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/LITELLM_CONFIG/i)).not.toBeInTheDocument();
  });

  it('keeps minimax-prefixed models in runtime selections', () => {
    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'openai' },
          { key: 'LLM_OPENAI_PROTOCOL', value: 'openai' },
          { key: 'LLM_OPENAI_BASE_URL', value: 'https://api.example.com/v1' },
          { key: 'LLM_OPENAI_ENABLED', value: 'true' },
          { key: 'LLM_OPENAI_API_KEY', value: 'secret-key' },
          { key: 'LLM_OPENAI_MODELS', value: 'minimax/MiniMax-M1' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    const primaryModelSelect = screen.getByRole('combobox', { name: '主模型' });
    const agentModelSelect = screen.getByRole('combobox', { name: 'Agent 主模型' });
    const visionModelSelect = screen.getByRole('combobox', { name: 'Vision 模型' });

    expect(within(primaryModelSelect).getByRole('option', { name: 'minimax/MiniMax-M1' })).toBeInTheDocument();
    expect(within(agentModelSelect).getByRole('option', { name: 'minimax/MiniMax-M1' })).toBeInTheDocument();
    expect(within(visionModelSelect).getByRole('option', { name: 'minimax/MiniMax-M1' })).toBeInTheDocument();
  });

  it('uses DeepSeek V4 defaults when adding the official preset', async () => {
    render(
      <LLMChannelEditor
        items={[]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'deepseek' } });
    fireEvent.click(screen.getByRole('button', { name: '+ 新增通道' }));

    await screen.findByRole('button', { name: /DeepSeek 官方/i });
    expect(screen.getByLabelText('Base URL')).toHaveValue('https://api.deepseek.com');
    expect(screen.getByLabelText('模型（逗號分隔）')).toHaveValue('deepseek-v4-flash,deepseek-v4-pro');
  });

  it.each([
    ['minimax', /MiniMax 官方/i, 'https://api.minimax.io/v1', 'MiniMax-M3,MiniMax-M2.7,MiniMax-M2.7-highspeed'],
    ['volcengine', /火山方舟/i, 'https://ark.cn-beijing.volces.com/api/v3', 'doubao-seed-1-6-251015,doubao-seed-1-6-thinking-251015'],
  ])('uses %s OpenAI-compatible defaults when adding the official preset', async (preset, buttonName, baseUrl, models) => {
    render(
      <LLMChannelEditor
        items={[]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.change(screen.getByRole('combobox'), { target: { value: preset } });
    fireEvent.click(screen.getByRole('button', { name: '+ 新增通道' }));

    await screen.findByRole('button', { name: buttonName });
    expect(screen.getAllByRole('combobox').some((select) => (
      select instanceof HTMLSelectElement && select.value === 'openai'
    ))).toBe(true);
    expect(screen.getByLabelText('Base URL')).toHaveValue(baseUrl);
    expect(screen.getByLabelText('模型（逗號分隔）')).toHaveValue(models);
  });

  it('shows provider capability badges, official sources, and config hints', async () => {
    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'openrouter' },
          { key: 'LLM_OPENROUTER_PROTOCOL', value: 'openai' },
          { key: 'LLM_OPENROUTER_BASE_URL', value: 'https://openrouter.ai/api/v1' },
          { key: 'LLM_OPENROUTER_ENABLED', value: 'true' },
          { key: 'LLM_OPENROUTER_API_KEY', value: 'sk-or-test' },
          { key: 'LLM_OPENROUTER_MODELS', value: '~anthropic/claude-sonnet-latest' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /OpenRouter/i }));

    expect(await screen.findByText('配置參考')).toBeInTheDocument();
    expect(screen.getByText('OpenAI 相容')).toBeInTheDocument();
    expect(screen.getByText('聚合平臺')).toBeInTheDocument();
    expect(screen.getByText('可獲取模型')).toBeInTheDocument();
    expect(screen.getByText(/模型列表和模型可見性依賴賬號許可權與 API Key/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'OpenRouter Models API' })).toHaveAttribute(
      'href',
      'https://openrouter.ai/docs/api/api-reference/models/get-models',
    );
    expect(screen.getByText(/能力標籤僅用於配置參考，不代表執行時能力已驗證透過/i)).toBeInTheDocument();
  });

  it('shows model-discovery capability for SiliconFlow provider hints', async () => {
    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'siliconflow' },
          { key: 'LLM_SILICONFLOW_PROTOCOL', value: 'openai' },
          { key: 'LLM_SILICONFLOW_BASE_URL', value: 'https://api.siliconflow.cn/v1' },
          { key: 'LLM_SILICONFLOW_ENABLED', value: 'true' },
          { key: 'LLM_SILICONFLOW_API_KEY', value: 'sk-test' },
          { key: 'LLM_SILICONFLOW_MODELS', value: 'deepseek-ai/DeepSeek-V3.2' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /SiliconFlow/i }));

    expect(await screen.findByText('可獲取模型')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'SiliconFlow Models' })).toBeInTheDocument();
  });

  it('does not show provider metadata for custom or unknown channels', async () => {
    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'my_proxy' },
          { key: 'LLM_MY_PROXY_PROTOCOL', value: 'openai' },
          { key: 'LLM_MY_PROXY_BASE_URL', value: 'https://proxy.example.com/v1' },
          { key: 'LLM_MY_PROXY_ENABLED', value: 'true' },
          { key: 'LLM_MY_PROXY_API_KEY', value: 'sk-test' },
          { key: 'LLM_MY_PROXY_MODELS', value: 'custom-model' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /my_proxy/i }));

    expect(screen.queryByText('配置參考')).not.toBeInTheDocument();
    expect(screen.queryByText(/官方來源/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/能力標籤僅用於配置參考/i)).not.toBeInTheDocument();
  });

  it('preserves manually edited base URL and models when switching preset names', async () => {
    render(
      <LLMChannelEditor
        items={[]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'deepseek' } });
    fireEvent.click(screen.getByRole('button', { name: '+ 新增通道' }));

    await screen.findByRole('button', { name: /DeepSeek 官方/i });
    fireEvent.change(screen.getByLabelText('Base URL'), {
      target: { value: 'https://proxy.example.com/v1' },
    });
    fireEvent.change(screen.getByLabelText('模型（逗號分隔）'), {
      target: { value: 'custom-model-a,custom-model-b' },
    });
    fireEvent.change(screen.getByLabelText('通道名稱'), {
      target: { value: 'minimax' },
    });

    await screen.findByRole('button', { name: /MiniMax 官方/i });
    expect(screen.getByLabelText('Base URL')).toHaveValue('https://proxy.example.com/v1');
    expect(screen.getByLabelText('模型（逗號分隔）')).toHaveValue('custom-model-a,custom-model-b');
  });

  it('uses the selected preset defaults when adding a duplicate provider channel', async () => {
    render(
      <LLMChannelEditor
        items={[]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'minimax' } });
    fireEvent.click(screen.getByRole('button', { name: '+ 新增通道' }));
    await screen.findByRole('button', { name: /MiniMax 官方/i });
    fireEvent.click(screen.getByRole('button', { name: '+ 新增通道' }));

    await screen.findByRole('button', { name: /minimax2/i });
    expect(screen.getAllByLabelText('通道名稱').map((input) => (input as HTMLInputElement).value)).toEqual([
      'minimax',
      'minimax2',
    ]);
    expect(screen.getAllByLabelText('Base URL').map((input) => (input as HTMLInputElement).value)).toEqual([
      'https://api.minimax.io/v1',
      'https://api.minimax.io/v1',
    ]);
    expect(screen.getAllByLabelText('模型（逗號分隔）').map((input) => (input as HTMLInputElement).value)).toEqual([
      'MiniMax-M3,MiniMax-M2.7,MiniMax-M2.7-highspeed',
      'MiniMax-M3,MiniMax-M2.7,MiniMax-M2.7-highspeed',
    ]);
    expect(screen.getAllByRole('link', { name: 'MiniMax OpenAI API' })).toHaveLength(1);
  });

  it('saves the MiniMax preset into LLM channel env keys', async () => {
    update.mockResolvedValue({
      success: true,
      configVersion: 'v2',
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
      updatedKeys: ['LLM_CHANNELS', 'LLM_MINIMAX_PROTOCOL', 'LLM_MINIMAX_BASE_URL', 'LLM_MINIMAX_MODELS'],
      warnings: [],
    });

    render(
      <LLMChannelEditor
        items={[]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'minimax' } });
    fireEvent.click(screen.getByRole('button', { name: '+ 新增通道' }));
    await screen.findByRole('button', { name: /MiniMax 官方/i });
    fireEvent.click(screen.getByRole('button', { name: '儲存 AI 配置' }));

    await waitFor(() => {
      expect(update).toHaveBeenCalled();
    });

    const updatePayload = update.mock.calls[0][0];
    expect(updatePayload.items).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ key: 'LLM_CHANNELS', value: 'minimax' }),
        expect.objectContaining({ key: 'LLM_MINIMAX_PROTOCOL', value: 'openai' }),
        expect.objectContaining({ key: 'LLM_MINIMAX_BASE_URL', value: 'https://api.minimax.io/v1' }),
        expect.objectContaining({ key: 'LLM_MINIMAX_MODELS', value: 'MiniMax-M3,MiniMax-M2.7,MiniMax-M2.7-highspeed' }),
      ]),
    );
  });

  it('sanitizes stale runtime models before saving DeepSeek V4 channel changes', async () => {
    update.mockResolvedValue({
      success: true,
      configVersion: 'v2',
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
      updatedKeys: ['LLM_DEEPSEEK_MODELS', 'LITELLM_MODEL'],
      warnings: [],
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_PROTOCOL', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_BASE_URL', value: 'https://api.deepseek.com' },
          { key: 'LLM_DEEPSEEK_ENABLED', value: 'true' },
          { key: 'LLM_DEEPSEEK_API_KEY', value: 'sk-test' },
          { key: 'LLM_DEEPSEEK_MODELS', value: 'deepseek-chat,deepseek-reasoner' },
          { key: 'LITELLM_MODEL', value: 'deepseek/deepseek-chat' },
          { key: 'AGENT_LITELLM_MODEL', value: 'deepseek/deepseek-reasoner' },
          { key: 'LITELLM_FALLBACK_MODELS', value: 'deepseek/deepseek-v4-pro,deepseek/deepseek-chat,cohere/command-r-plus' },
          { key: 'VISION_MODEL', value: 'deepseek/deepseek-reasoner' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek 官方/i }));
    fireEvent.change(screen.getByLabelText('模型（逗號分隔）'), {
      target: { value: 'deepseek-v4-flash,deepseek-v4-pro' },
    });
    fireEvent.click(screen.getByRole('button', { name: '儲存 AI 配置' }));

    await waitFor(() => {
      expect(update).toHaveBeenCalled();
    });

    const updatePayload = update.mock.calls[0][0];
    expect(updatePayload.items).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ key: 'LITELLM_MODEL', value: '' }),
        expect.objectContaining({ key: 'AGENT_LITELLM_MODEL', value: '' }),
        expect.objectContaining({ key: 'LITELLM_FALLBACK_MODELS', value: 'deepseek/deepseek-v4-pro,cohere/command-r-plus' }),
        expect.objectContaining({ key: 'VISION_MODEL', value: '' }),
        expect.objectContaining({ key: 'LLM_DEEPSEEK_MODELS', value: 'deepseek-v4-flash,deepseek-v4-pro' }),
      ]),
    );
  });

  it('sanitizes stale runtime models when enabled channels have no available models', async () => {
    update.mockResolvedValue({
      success: true,
      configVersion: 'v2',
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
      updatedKeys: ['LLM_DEEPSEEK_BASE_URL', 'LITELLM_MODEL', 'AGENT_LITELLM_MODEL', 'LITELLM_FALLBACK_MODELS', 'VISION_MODEL'],
      warnings: [],
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_PROTOCOL', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_BASE_URL', value: 'https://api.deepseek.com' },
          { key: 'LLM_DEEPSEEK_ENABLED', value: 'false' },
          { key: 'LLM_DEEPSEEK_API_KEY', value: 'sk-test' },
          { key: 'LLM_DEEPSEEK_MODELS', value: 'deepseek-chat,deepseek-v4-pro' },
          { key: 'LITELLM_MODEL', value: 'deepseek/deepseek-chat' },
          { key: 'AGENT_LITELLM_MODEL', value: 'deepseek/deepseek-chat' },
          { key: 'LITELLM_FALLBACK_MODELS', value: 'deepseek/deepseek-v4-pro' },
          { key: 'VISION_MODEL', value: 'deepseek/deepseek-chat' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek 官方/i }));
    fireEvent.change(screen.getByLabelText('Base URL'), {
      target: { value: 'https://api.deepseek.com/v1' },
    });
    fireEvent.click(screen.getByRole('button', { name: '儲存 AI 配置' }));

    await waitFor(() => {
      expect(update).toHaveBeenCalled();
    });

    const updatePayload = update.mock.calls[0][0];
    expect(updatePayload.items).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ key: 'LITELLM_MODEL', value: '' }),
        expect.objectContaining({ key: 'AGENT_LITELLM_MODEL', value: '' }),
        expect.objectContaining({ key: 'LITELLM_FALLBACK_MODELS', value: '' }),
        expect.objectContaining({ key: 'VISION_MODEL', value: '' }),
      ]),
    );
  });

  it('keeps legacy-key-backed runtime models when enabled channels have no available models', async () => {
    update.mockResolvedValue({
      success: true,
      configVersion: 'v2',
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
      updatedKeys: ['LLM_PRIMARY_BASE_URL', 'LITELLM_MODEL', 'LITELLM_FALLBACK_MODELS'],
      warnings: [],
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'primary' },
          { key: 'LLM_PRIMARY_PROTOCOL', value: 'openai' },
          { key: 'LLM_PRIMARY_BASE_URL', value: 'https://api.example.com/v1' },
          { key: 'LLM_PRIMARY_ENABLED', value: 'false' },
          { key: 'LLM_PRIMARY_API_KEY', value: 'sk-test' },
          { key: 'LLM_PRIMARY_MODELS', value: 'gpt-4o-mini' },
          { key: 'OPENAI_API_KEY', value: 'sk-legacy-value' },
          { key: 'LITELLM_MODEL', value: 'openai/gpt-4o-mini' },
          { key: 'LITELLM_FALLBACK_MODELS', value: 'openai/gpt-4o' },
          { key: 'AGENT_LITELLM_MODEL', value: '' },
          { key: 'VISION_MODEL', value: '' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /primary/i }));
    fireEvent.change(screen.getByLabelText('Base URL'), {
      target: { value: 'https://api.example.com/compatible/v1' },
    });
    fireEvent.click(screen.getByRole('button', { name: '儲存 AI 配置' }));

    await waitFor(() => {
      expect(update).toHaveBeenCalled();
    });

    const updatePayload = update.mock.calls[0][0];
    expect(updatePayload.items).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ key: 'LITELLM_MODEL', value: 'openai/gpt-4o-mini' }),
        expect.objectContaining({ key: 'LITELLM_FALLBACK_MODELS', value: 'openai/gpt-4o' }),
      ]),
    );
  });

  it('shows cleanup warning and restore path after stale runtime models are removed on save', async () => {
    update.mockResolvedValue({
      success: true,
      configVersion: 'v2',
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
      updatedKeys: ['LLM_DEEPSEEK_MODELS', 'LITELLM_MODEL'],
      warnings: [
        '檢測到已同步清理失效的執行時模型引用：主模型 / Agent 主模型 / Vision 模型 / 備選模型中的失效項。如需恢復，請先補回對應通道模型列表後重新選擇；也可用桌面端匯出備份或手動 .env 還原之前的 LLM_* / LITELLM_MODEL / AGENT_LITELLM_MODEL / VISION_MODEL / LLM_TEMPERATURE。',
      ],
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_PROTOCOL', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_BASE_URL', value: 'https://api.deepseek.com' },
          { key: 'LLM_DEEPSEEK_ENABLED', value: 'true' },
          { key: 'LLM_DEEPSEEK_API_KEY', value: 'sk-test' },
          { key: 'LLM_DEEPSEEK_MODELS', value: 'deepseek-chat,deepseek-reasoner' },
          { key: 'LITELLM_MODEL', value: 'deepseek/deepseek-chat' },
          { key: 'AGENT_LITELLM_MODEL', value: 'deepseek/deepseek-reasoner' },
          { key: 'LITELLM_FALLBACK_MODELS', value: 'deepseek/deepseek-v4-pro,deepseek/deepseek-chat' },
          { key: 'VISION_MODEL', value: 'deepseek/deepseek-reasoner' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek 官方/i }));
    fireEvent.change(screen.getByLabelText('模型（逗號分隔）'), {
      target: { value: 'deepseek-v4-flash,deepseek-v4-pro' },
    });
    fireEvent.click(screen.getByRole('button', { name: '儲存 AI 配置' }));

    expect(await screen.findByText('儲存後提示')).toBeInTheDocument();
    expect(screen.getByText(/已同步清理失效的執行時模型引用/i)).toBeInTheDocument();
    expect(screen.getByText(/桌面端匯出備份或手動 \.env 還原/i)).toBeInTheDocument();
  });

  it('keeps save warnings visible after onSaved-driven refresh', async () => {
    const warningMessage = '檢測到已同步清理失效的執行時模型引用：主模型 / Agent 主模型 / Vision 模型 / 備選模型中的失效項。';
    const initialItems = [
      { key: 'LLM_CHANNELS', value: 'deepseek' },
      { key: 'LLM_DEEPSEEK_PROTOCOL', value: 'deepseek' },
      { key: 'LLM_DEEPSEEK_BASE_URL', value: 'https://api.deepseek.com' },
      { key: 'LLM_DEEPSEEK_ENABLED', value: 'true' },
      { key: 'LLM_DEEPSEEK_API_KEY', value: 'sk-test' },
      { key: 'LLM_DEEPSEEK_MODELS', value: 'deepseek-chat,deepseek-reasoner' },
      { key: 'LITELLM_MODEL', value: 'deepseek/deepseek-chat' },
      { key: 'AGENT_LITELLM_MODEL', value: 'deepseek/deepseek-reasoner' },
      { key: 'LITELLM_FALLBACK_MODELS', value: 'deepseek/deepseek-v4-pro,cohere/command-r-plus' },
      { key: 'VISION_MODEL', value: 'deepseek/deepseek-reasoner' },
    ];
    const Component = () => {
      const [items, setItems] = useState(initialItems);

      return (
        <LLMChannelEditor
          items={items}
          configVersion="v1"
          maskToken="******"
          onSaved={async (updatedItems) => {
            setItems(updatedItems);
          }}
        />
      );
    };

    update.mockResolvedValue({
      success: true,
      configVersion: 'v2',
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
      updatedKeys: ['LLM_DEEPSEEK_MODELS', 'LITELLM_MODEL'],
      warnings: [warningMessage],
    });

    render(<Component />);

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek 官方/i }));
    fireEvent.change(screen.getByLabelText('模型（逗號分隔）'), {
      target: { value: 'deepseek-v4-flash,deepseek-v4-pro' },
    });
    fireEvent.click(screen.getByRole('button', { name: '儲存 AI 配置' }));

    expect(await screen.findByText('儲存後提示')).toBeInTheDocument();
    expect(screen.getByText(warningMessage)).toBeInTheDocument();
  });

  it('clears failed-save feedback after saved props refresh', async () => {
    const initialItems = [
      { key: 'LLM_CHANNELS', value: 'openai' },
      { key: 'LLM_OPENAI_PROTOCOL', value: 'openai' },
      { key: 'LLM_OPENAI_BASE_URL', value: 'https://api.openai.com/v1' },
      { key: 'LLM_OPENAI_ENABLED', value: 'true' },
      { key: 'LLM_OPENAI_API_KEY', value: 'secret-key' },
      { key: 'LLM_OPENAI_MODELS', value: 'gpt-4o-mini' },
    ];
    const onSaved = vi.fn(async () => {
      throw new Error('refresh failed');
    });

    update.mockResolvedValue({
      success: true,
      configVersion: 'v2',
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
      updatedKeys: ['LLM_OPENAI_BASE_URL'],
      warnings: [],
    });

    const renderResult = render(
      <LLMChannelEditor
        items={initialItems}
        configVersion="v1"
        maskToken="******"
        onSaved={onSaved}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /OpenAI 官方/i }));
    fireEvent.change(screen.getByLabelText('Base URL'), {
      target: { value: 'https://api.openai.com/v1/test' },
    });
    fireEvent.click(screen.getByRole('button', { name: '儲存 AI 配置' }));

    expect(await screen.findByText('refresh failed')).toBeInTheDocument();

    const savedItems = update.mock.calls[0][0].items;
    renderResult.rerender(
      <LLMChannelEditor
        items={savedItems}
        configVersion="v2"
        maskToken="******"
        onSaved={onSaved}
      />,
    );

    await waitFor(() => {
      expect(screen.queryByText('refresh failed')).not.toBeInTheDocument();
    });
  });

  it('keeps stale runtime fallback model available when user restores it in channel models', async () => {
    update.mockResolvedValue({
      success: true,
      configVersion: 'v2',
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
      updatedKeys: ['LLM_DEEPSEEK_MODELS', 'LITELLM_MODEL', 'LITELLM_FALLBACK_MODELS'],
      warnings: [],
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_PROTOCOL', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_BASE_URL', value: 'https://api.deepseek.com' },
          { key: 'LLM_DEEPSEEK_ENABLED', value: 'true' },
          { key: 'LLM_DEEPSEEK_API_KEY', value: 'sk-test' },
          { key: 'LLM_DEEPSEEK_MODELS', value: 'deepseek-chat' },
          { key: 'LITELLM_MODEL', value: 'deepseek/deepseek-chat' },
          { key: 'AGENT_LITELLM_MODEL', value: '' },
          { key: 'LITELLM_FALLBACK_MODELS', value: 'deepseek/deepseek-old' },
          { key: 'VISION_MODEL', value: '' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek 官方/i }));
    fireEvent.change(screen.getByLabelText('模型（逗號分隔）'), {
      target: { value: 'deepseek-chat,deepseek-old' },
    });

    expect(await screen.findByLabelText('deepseek/deepseek-old')).toBeChecked();

    fireEvent.click(screen.getByRole('button', { name: '儲存 AI 配置' }));
    await waitFor(() => {
      expect(update).toHaveBeenCalled();
    });

    const updatePayload = update.mock.calls[0][0];
    expect(updatePayload.items).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ key: 'LITELLM_FALLBACK_MODELS', value: 'deepseek/deepseek-old' }),
      ]),
    );
  });

  it('keeps runtime selections while channel models are edited temporarily', async () => {
    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_PROTOCOL', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_BASE_URL', value: 'https://api.deepseek.com' },
          { key: 'LLM_DEEPSEEK_ENABLED', value: 'true' },
          { key: 'LLM_DEEPSEEK_API_KEY', value: 'sk-test' },
          { key: 'LLM_DEEPSEEK_MODELS', value: 'deepseek-chat,deepseek-reasoner,deepseek-v4-pro' },
          { key: 'LITELLM_MODEL', value: 'deepseek/deepseek-chat' },
          { key: 'AGENT_LITELLM_MODEL', value: 'deepseek/deepseek-reasoner' },
          { key: 'LITELLM_FALLBACK_MODELS', value: 'deepseek/deepseek-v4-pro' },
          { key: 'VISION_MODEL', value: 'deepseek/deepseek-reasoner' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    const primaryModelSelect = screen.getByRole('combobox', { name: '主模型' });
    const agentModelSelect = screen.getByRole('combobox', { name: 'Agent 主模型' });
    const visionModelSelect = screen.getByRole('combobox', { name: 'Vision 模型' });

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek 官方/i }));
    const modelInput = screen.getByLabelText('模型（逗號分隔）');
    fireEvent.change(modelInput, {
      target: { value: 'deepseek-v4-flash' },
    });

    await waitFor(() => {
      expect(primaryModelSelect).toHaveValue('deepseek/deepseek-chat');
      expect(agentModelSelect).toHaveValue('deepseek/deepseek-reasoner');
      expect(visionModelSelect).toHaveValue('deepseek/deepseek-reasoner');
    });

    fireEvent.change(modelInput, {
      target: { value: 'deepseek-chat,deepseek-reasoner,deepseek-v4-pro' },
    });

    await waitFor(() => {
      expect(primaryModelSelect).toHaveValue('deepseek/deepseek-chat');
      expect(agentModelSelect).toHaveValue('deepseek/deepseek-reasoner');
      expect(visionModelSelect).toHaveValue('deepseek/deepseek-reasoner');
      expect(screen.getByLabelText('deepseek/deepseek-v4-pro')).toBeChecked();
    });
  });

  it('keeps direct-env provider runtime models (cohere / google / xai) while saving channel changes', async () => {
    update.mockResolvedValue({
      success: true,
      configVersion: 'v2',
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
      updatedKeys: ['LLM_DEEPSEEK_BASE_URL', 'LITELLM_MODEL', 'AGENT_LITELLM_MODEL', 'LITELLM_FALLBACK_MODELS', 'VISION_MODEL'],
      warnings: [],
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_PROTOCOL', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_BASE_URL', value: 'https://api.deepseek.com/v1' },
          { key: 'LLM_DEEPSEEK_ENABLED', value: 'true' },
          { key: 'LLM_DEEPSEEK_API_KEY', value: 'sk-test' },
          { key: 'LLM_DEEPSEEK_MODELS', value: 'deepseek-v4-flash' },
          { key: 'LITELLM_MODEL', value: 'cohere/command-r-plus' },
          { key: 'AGENT_LITELLM_MODEL', value: 'google/gemini-2.5-flash' },
          { key: 'LITELLM_FALLBACK_MODELS', value: 'cohere/command-r-plus,google/gemini-2.5-flash,xai/grok-beta' },
          { key: 'VISION_MODEL', value: 'xai/grok-vision-beta' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek 官方/i }));
    fireEvent.change(screen.getByLabelText('Base URL'), {
      target: { value: 'https://api.deepseek.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: '儲存 AI 配置' }));

    await waitFor(() => {
      expect(update).toHaveBeenCalled();
    });

    const updatePayload = update.mock.calls[0][0];
    expect(updatePayload.items).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ key: 'LITELLM_MODEL', value: 'cohere/command-r-plus' }),
        expect.objectContaining({ key: 'AGENT_LITELLM_MODEL', value: 'google/gemini-2.5-flash' }),
        expect.objectContaining({ key: 'LITELLM_FALLBACK_MODELS', value: 'cohere/command-r-plus,google/gemini-2.5-flash,xai/grok-beta' }),
        expect.objectContaining({ key: 'VISION_MODEL', value: 'xai/grok-vision-beta' }),
      ]),
    );
  });

  it('checks protocol-prefixed selected model when discovery returns bare id', async () => {
    discoverLLMChannelModels.mockResolvedValue({
      success: true,
      message: 'LLM channel model discovery succeeded',
      error: null,
      resolvedProtocol: 'openai',
      models: ['MiniMax-M1'],
      latencyMs: 80,
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'dashscope' },
          { key: 'LLM_DASHSCOPE_PROTOCOL', value: 'openai' },
          { key: 'LLM_DASHSCOPE_BASE_URL', value: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
          { key: 'LLM_DASHSCOPE_ENABLED', value: 'true' },
          { key: 'LLM_DASHSCOPE_API_KEY', value: 'sk-test' },
          { key: 'LLM_DASHSCOPE_MODELS', value: 'openai/MiniMax-M1' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /通義千問/i }));
    fireEvent.click(screen.getByRole('button', { name: '獲取模型' }));

    const checkbox = await screen.findByLabelText('MiniMax-M1');
    expect(checkbox).toBeChecked();

    fireEvent.click(checkbox);
    await waitFor(() => {
      expect(screen.getByLabelText('手動模型（逗號分隔）')).toHaveValue('');
    });
  });

  it('does not treat unknown-prefixed selected model as equivalent to bare discovered id', async () => {
    discoverLLMChannelModels.mockResolvedValue({
      success: true,
      message: 'LLM channel model discovery succeeded',
      error: null,
      resolvedProtocol: 'openai',
      models: ['MiniMax-M1'],
      latencyMs: 80,
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'dashscope' },
          { key: 'LLM_DASHSCOPE_PROTOCOL', value: 'openai' },
          { key: 'LLM_DASHSCOPE_BASE_URL', value: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
          { key: 'LLM_DASHSCOPE_ENABLED', value: 'true' },
          { key: 'LLM_DASHSCOPE_API_KEY', value: 'sk-test' },
          { key: 'LLM_DASHSCOPE_MODELS', value: 'minimax/MiniMax-M1' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /通義千問/i }));
    fireEvent.click(screen.getByRole('button', { name: '獲取模型' }));

    const checkbox = await screen.findByLabelText('MiniMax-M1');
    expect(checkbox).not.toBeChecked();
    expect(screen.getByLabelText('手動模型（逗號分隔）')).toHaveValue('minimax/MiniMax-M1');
  });

  it('discovers models and writes selected values back to channel config', async () => {
    discoverLLMChannelModels.mockResolvedValue({
      success: true,
      message: 'LLM channel model discovery succeeded',
      error: null,
      resolvedProtocol: 'openai',
      models: ['qwen-plus', 'qwen-turbo'],
      latencyMs: 88,
    });
    update.mockResolvedValue({
      success: true,
      configVersion: 'v2',
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
      updatedKeys: ['LLM_DASHSCOPE_MODELS'],
      warnings: [],
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'dashscope' },
          { key: 'LLM_DASHSCOPE_PROTOCOL', value: 'openai' },
          { key: 'LLM_DASHSCOPE_BASE_URL', value: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
          { key: 'LLM_DASHSCOPE_ENABLED', value: 'true' },
          { key: 'LLM_DASHSCOPE_API_KEY', value: 'sk-test' },
          { key: 'LLM_DASHSCOPE_MODELS', value: 'qwen-old' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /Dashscope/i }));
    fireEvent.click(screen.getByRole('button', { name: '獲取模型' }));

    const qwenPlusCheckbox = await screen.findByLabelText('qwen-plus');
    fireEvent.click(qwenPlusCheckbox);

    await waitFor(() => {
      expect(screen.getByLabelText('手動模型（逗號分隔）')).toHaveValue('qwen-old,qwen-plus');
    });

    expect(discoverLLMChannelModels).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'dashscope',
        protocol: 'openai',
        baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
        apiKey: 'sk-test',
        models: ['qwen-old'],
      }),
    );

    fireEvent.click(screen.getByRole('button', { name: '儲存 AI 配置' }));

    await waitFor(() => {
      expect(update).toHaveBeenCalled();
    });

    const updatePayload = update.mock.calls[0][0];
    expect(updatePayload.items).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ key: 'LLM_DASHSCOPE_MODELS', value: 'qwen-old,qwen-plus' }),
      ]),
    );
  });

  it('shows structured troubleshooting hint when channel auth fails', async () => {
    testLLMChannel.mockResolvedValue({ success: false, message: 'LLM authentication failed', error: '401 Unauthorized · Bearer [REDACTED]', errorCode: 'auth', stage: 'chat_completion', retryable: false, details: {}, resolvedProtocol: 'openai', resolvedModel: 'openai/gpt-4o-mini', latencyMs: null });

    render(
      <LLMChannelEditor
        items={[{ key: 'LLM_CHANNELS', value: 'openai' }, { key: 'LLM_OPENAI_PROTOCOL', value: 'openai' }, { key: 'LLM_OPENAI_BASE_URL', value: 'https://api.openai.com/v1' }, { key: 'LLM_OPENAI_ENABLED', value: 'true' }, { key: 'LLM_OPENAI_API_KEY', value: 'secret-key' }, { key: 'LLM_OPENAI_MODELS', value: 'gpt-4o-mini' }]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /OpenAI 官方/i }));
    fireEvent.click(screen.getByRole('button', { name: '測試連線' }));

    expect(await screen.findByText(/聊天呼叫 · 鑑權失敗：LLM authentication failed/i)).toBeInTheDocument();
    expect(screen.getByText(/請檢查 API Key 是否正確/i)).toBeInTheDocument();
    expect(screen.queryByText(/調整模型順序或移除不可用模型/i)).not.toBeInTheDocument();
  });

  it('shows tested model and model-availability hints when a model is disabled', async () => {
    testLLMChannel.mockResolvedValue({
      success: false,
      message: 'LLM channel test failed',
      error: 'litellm.APIError: APIError: OpenAIException - Model disabled.',
      errorCode: 'model_not_found',
      stage: 'chat_completion',
      retryable: false,
      details: { reason: 'model_access_denied', model: 'openai/deepseek-ai/DeepSeek-V3' },
      resolvedProtocol: 'openai',
      resolvedModel: 'openai/deepseek-ai/DeepSeek-V3',
      latencyMs: null,
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'siliconflow' },
          { key: 'LLM_SILICONFLOW_PROTOCOL', value: 'openai' },
          { key: 'LLM_SILICONFLOW_BASE_URL', value: 'https://api.siliconflow.cn/v1' },
          { key: 'LLM_SILICONFLOW_ENABLED', value: 'true' },
          { key: 'LLM_SILICONFLOW_API_KEY', value: 'secret-key' },
          { key: 'LLM_SILICONFLOW_MODELS', value: 'deepseek-ai/DeepSeek-V3,Qwen/Qwen3-Coder' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /SiliconFlow/i }));
    fireEvent.click(screen.getByRole('button', { name: '測試連線' }));

    expect(await screen.findByText(/聊天呼叫 · 模型不可用：LLM channel test failed/i)).toBeInTheDocument();
    expect(screen.getByText(/本次測試模型：openai\/deepseek-ai\/DeepSeek-V3/i)).toBeInTheDocument();
    expect(screen.getByText(/基礎連線測試預設使用模型列表首項：deepseek-ai\/DeepSeek-V3/i)).toBeInTheDocument();
    expect(screen.getByText(/基礎連線測試預設只測試模型列表中的第一個模型/i)).toBeInTheDocument();
    expect(screen.getByText(/調整模型順序或移除不可用模型/i)).toBeInTheDocument();
    expect(screen.getByText(/模型是否已開通、賬號是否可見/i)).toBeInTheDocument();
    expect(screen.queryByText(/Base URL、代理、TLS/i)).not.toBeInTheDocument();
    expect(testLLMChannel).toHaveBeenCalledWith(expect.objectContaining({
      models: ['deepseek-ai/DeepSeek-V3', 'Qwen/Qwen3-Coder'],
    }));
  });

  it('shows provider blocked troubleshooting without network or model-list hints', async () => {
    testLLMChannel.mockResolvedValue({
      success: false,
      message: 'LLM request was blocked by provider or gateway policy',
      error: 'litellm.APIError: APIError: OpenAIException - Your request was blocked.',
      errorCode: 'request_blocked',
      stage: 'chat_completion',
      retryable: false,
      details: { reason: 'provider_blocked', model: 'openai/gpt-5.5' },
      resolvedProtocol: 'openai',
      resolvedModel: 'openai/gpt-5.5',
      latencyMs: null,
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'proxy' },
          { key: 'LLM_PROXY_PROTOCOL', value: 'openai' },
          { key: 'LLM_PROXY_BASE_URL', value: 'https://gateway.example.com/v1' },
          { key: 'LLM_PROXY_ENABLED', value: 'true' },
          { key: 'LLM_PROXY_API_KEY', value: 'secret-key' },
          { key: 'LLM_PROXY_MODELS', value: 'gpt-5.5,gpt-4o-mini' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /proxy/i }));
    fireEvent.click(screen.getByRole('button', { name: '測試連線' }));

    expect(await screen.findByText(/聊天呼叫 · 請求被攔截/i)).toBeInTheDocument();
    expect(screen.getByText(/本次測試模型：openai\/gpt-5\.5/i)).toBeInTheDocument();
    expect(screen.getByText(/賬號風控、地域限制、模型許可權/i)).toBeInTheDocument();
    expect(screen.queryByText(/Base URL、代理、TLS/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/調整模型順序或移除不可用模型/i)).not.toBeInTheDocument();
  });

  it('shows focused quota exceeded troubleshooting hints', async () => {
    testLLMChannel.mockResolvedValue({
      success: false,
      message: 'LLM request was rejected by quota or rate limiting',
      error: 'quota exceeded',
      errorCode: 'quota',
      stage: 'chat_completion',
      retryable: true,
      details: { reason: 'quota_exceeded' },
      resolvedProtocol: 'openai',
      resolvedModel: 'openai/gpt-4o-mini',
      latencyMs: null,
    });

    render(
      <LLMChannelEditor
        items={[{ key: 'LLM_CHANNELS', value: 'openai' }, { key: 'LLM_OPENAI_PROTOCOL', value: 'openai' }, { key: 'LLM_OPENAI_BASE_URL', value: 'https://api.openai.com/v1' }, { key: 'LLM_OPENAI_ENABLED', value: 'true' }, { key: 'LLM_OPENAI_API_KEY', value: 'secret-key' }, { key: 'LLM_OPENAI_MODELS', value: 'gpt-4o-mini' }]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /OpenAI 官方/i }));
    fireEvent.click(screen.getByRole('button', { name: '測試連線' }));

    expect(await screen.findByText(/服務商返回配額已耗盡/i)).toBeInTheDocument();
    expect(screen.queryByText(/調整模型順序或移除不可用模型/i)).not.toBeInTheDocument();
  });

  it('does not show model-list action hints for network failures', async () => {
    testLLMChannel.mockResolvedValue({
      success: false,
      message: 'LLM request failed before a valid response was returned',
      error: 'DNS lookup failed',
      errorCode: 'network_error',
      stage: 'chat_completion',
      retryable: true,
      details: { reason: 'dns_error' },
      resolvedProtocol: 'openai',
      resolvedModel: 'openai/gpt-4o-mini',
      latencyMs: null,
    });

    render(
      <LLMChannelEditor
        items={[{ key: 'LLM_CHANNELS', value: 'openai' }, { key: 'LLM_OPENAI_PROTOCOL', value: 'openai' }, { key: 'LLM_OPENAI_BASE_URL', value: 'https://api.openai.com/v1' }, { key: 'LLM_OPENAI_ENABLED', value: 'true' }, { key: 'LLM_OPENAI_API_KEY', value: 'secret-key' }, { key: 'LLM_OPENAI_MODELS', value: 'gpt-4o-mini' }]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /OpenAI 官方/i }));
    fireEvent.click(screen.getByRole('button', { name: '測試連線' }));

    expect(await screen.findByText(/域名解析失敗/i)).toBeInTheDocument();
    expect(screen.queryByText(/調整模型順序或移除不可用模型/i)).not.toBeInTheDocument();
  });

  it('does not request runtime capabilities during the basic connection test', async () => {
    testLLMChannel.mockResolvedValue({
      success: true,
      message: 'LLM channel test succeeded',
      error: null,
      errorCode: null,
      stage: 'chat_completion',
      retryable: false,
      details: {},
      resolvedProtocol: 'openai',
      resolvedModel: 'openai/gpt-4o-mini',
      latencyMs: 80,
      capabilityResults: {},
    });

    render(
      <LLMChannelEditor
        items={[{ key: 'LLM_CHANNELS', value: 'openai' }, { key: 'LLM_OPENAI_PROTOCOL', value: 'openai' }, { key: 'LLM_OPENAI_BASE_URL', value: 'https://api.openai.com/v1' }, { key: 'LLM_OPENAI_ENABLED', value: 'true' }, { key: 'LLM_OPENAI_API_KEY', value: 'secret-key' }, { key: 'LLM_OPENAI_MODELS', value: 'gpt-4o-mini' }]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /OpenAI 官方/i }));
    fireEvent.click(screen.getByRole('button', { name: '測試連線' }));

    await screen.findByText(/連線成功 · openai\/gpt-4o-mini/i);
    expect(testLLMChannel).toHaveBeenCalledWith(expect.not.objectContaining({ capabilityChecks: expect.anything() }));
  });

  it('runs explicit runtime capability checks and shows detailed hints', async () => {
    testLLMChannel.mockResolvedValue({
      success: true,
      message: 'LLM channel test succeeded',
      error: null,
      errorCode: null,
      stage: 'chat_completion',
      retryable: false,
      details: {},
      resolvedProtocol: 'openai',
      resolvedModel: 'openai/gpt-4o-mini',
      latencyMs: 80,
      capabilityResults: {
        json: {
          status: 'passed',
          message: 'JSON output capability check passed',
          errorCode: null,
          stage: 'capability_json',
          retryable: false,
          details: { reason: 'json_valid' },
        },
        tools: {
          status: 'failed',
          message: 'LLM channel does not support tools capability',
          errorCode: 'capability_unsupported',
          stage: 'capability_tools',
          retryable: false,
          details: { reason: 'capability_unsupported' },
        },
      },
    });

    render(
      <LLMChannelEditor
        items={[{ key: 'LLM_CHANNELS', value: 'openai' }, { key: 'LLM_OPENAI_PROTOCOL', value: 'openai' }, { key: 'LLM_OPENAI_BASE_URL', value: 'https://api.openai.com/v1' }, { key: 'LLM_OPENAI_ENABLED', value: 'true' }, { key: 'LLM_OPENAI_API_KEY', value: 'secret-key' }, { key: 'LLM_OPENAI_MODELS', value: 'gpt-4o-mini' }]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /OpenAI 官方/i }));
    fireEvent.click(screen.getByLabelText('JSON'));
    fireEvent.click(screen.getByLabelText('Tools'));
    fireEvent.click(screen.getByRole('button', { name: '檢測能力' }));

    expect(await screen.findByText(/能力檢測完成：1 透過 \/ 1 失敗 \/ 0 跳過/i)).toBeInTheDocument();
    expect(screen.getByText('JSON 透過')).toBeInTheDocument();
    expect(screen.getByText('Tools 失敗')).toBeInTheDocument();
    expect(screen.getByText(/當前模型或相容層不支援該能力/i)).toBeInTheDocument();
    expect(testLLMChannel).toHaveBeenCalledWith(expect.objectContaining({ capabilityChecks: ['json', 'tools'] }));
  });

  it('shows skipped runtime capabilities when the base test fails', async () => {
    testLLMChannel.mockResolvedValue({
      success: false,
      message: 'LLM authentication failed',
      error: '401 Unauthorized',
      errorCode: 'auth',
      stage: 'chat_completion',
      retryable: false,
      details: { reason: 'api_key_rejected' },
      resolvedProtocol: 'openai',
      resolvedModel: 'openai/gpt-4o-mini',
      latencyMs: null,
      capabilityResults: {
        json: {
          status: 'skipped',
          message: 'Skipped because the base channel test did not pass',
          errorCode: 'skipped',
          stage: 'capability_json',
          retryable: false,
          details: { reason: 'base_test_failed' },
        },
      },
    });

    render(
      <LLMChannelEditor
        items={[{ key: 'LLM_CHANNELS', value: 'openai' }, { key: 'LLM_OPENAI_PROTOCOL', value: 'openai' }, { key: 'LLM_OPENAI_BASE_URL', value: 'https://api.openai.com/v1' }, { key: 'LLM_OPENAI_ENABLED', value: 'true' }, { key: 'LLM_OPENAI_API_KEY', value: 'bad-key' }, { key: 'LLM_OPENAI_MODELS', value: 'gpt-4o-mini' }]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /OpenAI 官方/i }));
    fireEvent.click(screen.getByLabelText('JSON'));
    fireEvent.click(screen.getByRole('button', { name: '檢測能力' }));

    expect(await screen.findByText(/能力檢測完成：0 透過 \/ 0 失敗 \/ 1 跳過/i)).toBeInTheDocument();
    expect(screen.getByText('JSON 跳過')).toBeInTheDocument();
    expect(screen.getByText(/服務商拒絕了當前 API Key/i)).toBeInTheDocument();
    expect(screen.getByLabelText('模型（逗號分隔）')).toBeEnabled();
  });

  it('keeps manual model input available when discovery fails', async () => {
    discoverLLMChannelModels.mockResolvedValue({
      success: false,
      message: 'Model discovery is not supported for this protocol',
      error: 'LLM channel does not support /models discovery yet',
      errorCode: 'unsupported_protocol',
      stage: 'model_discovery',
      retryable: false,
      details: {},
      resolvedProtocol: 'gemini',
      models: [],
      latencyMs: null,
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'gemini' },
          { key: 'LLM_GEMINI_PROTOCOL', value: 'gemini' },
          { key: 'LLM_GEMINI_BASE_URL', value: '' },
          { key: 'LLM_GEMINI_ENABLED', value: 'true' },
          { key: 'LLM_GEMINI_API_KEY', value: 'sk-test' },
          { key: 'LLM_GEMINI_MODELS', value: '' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /Gemini 官方/i }));
    fireEvent.click(screen.getByRole('button', { name: '獲取模型' }));

    await screen.findByText(/模型發現 · 協議暫不支援：Model discovery is not supported for this protocol/i);
    expect(screen.getByText(/當前僅對 OpenAI Compatible \/ DeepSeek 通道提供自動模型發現/i)).toBeInTheDocument();

    const manualInput = screen.getByLabelText('模型（逗號分隔）');
    fireEvent.change(manualInput, { target: { value: 'gemini-2.5-flash' } });
    expect(manualInput).toHaveValue('gemini-2.5-flash');
  });

  it('maps discovery format errors to the /models troubleshooting hint', async () => {
    discoverLLMChannelModels.mockResolvedValue({
      success: false,
      message: 'Failed to parse /models response',
      error: 'Unexpected discovery payload',
      errorCode: 'format_error',
      stage: 'response_parse',
      retryable: false,
      details: {},
      resolvedProtocol: 'openai',
      models: [],
      latencyMs: null,
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'openai' },
          { key: 'LLM_OPENAI_PROTOCOL', value: 'openai' },
          { key: 'LLM_OPENAI_BASE_URL', value: 'https://api.openai.com/v1' },
          { key: 'LLM_OPENAI_ENABLED', value: 'true' },
          { key: 'LLM_OPENAI_API_KEY', value: 'secret-key' },
          { key: 'LLM_OPENAI_MODELS', value: '' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /OpenAI 官方/i }));
    fireEvent.click(screen.getByRole('button', { name: '獲取模型' }));

    expect(await screen.findByText(/響應解析 · 格式異常：Failed to parse \/models response/i)).toBeInTheDocument();
    expect(screen.getByText(/該通道返回的 \/models 響應格式不相容，請改為手動填寫模型列表。/i)).toBeInTheDocument();
  });

  it('maps discovery empty responses to the /models troubleshooting hint', async () => {
    discoverLLMChannelModels.mockResolvedValue({
      success: false,
      message: 'No model IDs returned from /models response',
      error: 'Empty model discovery response',
      errorCode: 'empty_response',
      stage: 'model_discovery',
      retryable: false,
      details: {},
      resolvedProtocol: 'openai',
      models: [],
      latencyMs: null,
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'openai' },
          { key: 'LLM_OPENAI_PROTOCOL', value: 'openai' },
          { key: 'LLM_OPENAI_BASE_URL', value: 'https://api.openai.com/v1' },
          { key: 'LLM_OPENAI_ENABLED', value: 'true' },
          { key: 'LLM_OPENAI_API_KEY', value: 'secret-key' },
          { key: 'LLM_OPENAI_MODELS', value: '' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /OpenAI 官方/i }));
    fireEvent.click(screen.getByRole('button', { name: '獲取模型' }));

    expect(await screen.findByText(/模型發現 · 空響應：No model IDs returned from \/models response/i)).toBeInTheDocument();
    expect(screen.getByText(/該通道的 \/models 介面未返回可用模型 ID/i)).toBeInTheDocument();
    expect(screen.queryByText(/切換相容模型、關閉額外響應模式/i)).not.toBeInTheDocument();
  });

  it('does not apply stale discovery response after channel list re-sync', async () => {
    let resolvePendingFirst!: (value: unknown) => void;
    const pendingFirst = new Promise((resolve) => {
      resolvePendingFirst = resolve;
    });

    discoverLLMChannelModels
      .mockImplementationOnce(() => pendingFirst)
      .mockResolvedValueOnce({
        success: true,
        message: 'LLM channel model discovery succeeded',
        error: null,
        resolvedProtocol: 'openai',
        models: ['dashscope-plus'],
        latencyMs: 30,
      });

    const renderResult = render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'openai' },
          { key: 'LLM_OPENAI_PROTOCOL', value: 'openai' },
          { key: 'LLM_OPENAI_BASE_URL', value: 'https://api.openai.com/v1' },
          { key: 'LLM_OPENAI_ENABLED', value: 'true' },
          { key: 'LLM_OPENAI_API_KEY', value: 'open-key' },
          { key: 'LLM_OPENAI_MODELS', value: 'gpt-old' },
          { key: 'LLM_DASHSCOPE_PROTOCOL', value: 'openai' },
          { key: 'LLM_DASHSCOPE_BASE_URL', value: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
          { key: 'LLM_DASHSCOPE_ENABLED', value: 'true' },
          { key: 'LLM_DASHSCOPE_API_KEY', value: 'dash-key' },
          { key: 'LLM_DASHSCOPE_MODELS', value: 'dash-old' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /OpenAI 官方/i }));
    fireEvent.click(screen.getByRole('button', { name: '獲取模型' }));

    renderResult.rerender(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'dashscope' },
          { key: 'LLM_DASHSCOPE_PROTOCOL', value: 'openai' },
          { key: 'LLM_DASHSCOPE_BASE_URL', value: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
          { key: 'LLM_DASHSCOPE_ENABLED', value: 'true' },
          { key: 'LLM_DASHSCOPE_API_KEY', value: 'dash-key' },
          { key: 'LLM_DASHSCOPE_MODELS', value: 'dash-old' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /通義千問/i }));
    fireEvent.click(screen.getByRole('button', { name: '獲取模型' }));

    const dashModelCheckbox = await screen.findByLabelText('dashscope-plus');
    fireEvent.click(dashModelCheckbox);

    expect(screen.getByLabelText('手動模型（逗號分隔）')).toHaveValue('dash-old,dashscope-plus');

    resolvePendingFirst({
      success: true,
      message: 'LLM channel model discovery succeeded',
      error: null,
      resolvedProtocol: 'openai',
      models: ['stale-openai'],
      latencyMs: 20,
    });

    await waitFor(() => {
      expect(screen.getByLabelText('手動模型（逗號分隔）')).toHaveValue('dash-old,dashscope-plus');
    });
    expect(screen.queryByLabelText('stale-openai')).not.toBeInTheDocument();
  });

  it('does not apply stale discovery response after inline channel edit', async () => {
    let resolvePendingFirst!: (value: unknown) => void;
    const pendingFirst = new Promise((resolve) => {
      resolvePendingFirst = resolve;
    });

    discoverLLMChannelModels.mockImplementationOnce(() => pendingFirst);

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'dashscope' },
          { key: 'LLM_DASHSCOPE_PROTOCOL', value: 'openai' },
          { key: 'LLM_DASHSCOPE_BASE_URL', value: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
          { key: 'LLM_DASHSCOPE_ENABLED', value: 'true' },
          { key: 'LLM_DASHSCOPE_API_KEY', value: 'dash-key' },
          { key: 'LLM_DASHSCOPE_MODELS', value: 'qwen-old' },
        ]}
        configVersion="v1"
        maskToken="******"
        onSaved={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Dashscope/i }));
    fireEvent.click(screen.getByRole('button', { name: '獲取模型' }));

    const baseUrlInput = screen.getByLabelText('Base URL');
    fireEvent.change(baseUrlInput, {
      target: { value: 'https://dashscope.aliyuncs.com/compatible-mode/v2' },
    });

    resolvePendingFirst({
      success: true,
      message: 'LLM channel model discovery succeeded',
      error: null,
      resolvedProtocol: 'openai',
      models: ['stale-openai'],
      latencyMs: 20,
    });

    await waitFor(() => {
      expect(screen.getByLabelText('模型（逗號分隔）')).toHaveValue('qwen-old');
      expect(screen.queryByLabelText('stale-openai')).not.toBeInTheDocument();
    });
  });
});
