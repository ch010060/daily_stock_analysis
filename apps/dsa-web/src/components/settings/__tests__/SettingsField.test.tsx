import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { SettingsField } from '../SettingsField';

describe('SettingsField', () => {
  it('renders sensitive field metadata and validation errors', () => {
    const onChange = vi.fn();

    render(
      <SettingsField
        item={{
          key: 'OPENAI_API_KEY',
          value: 'secret',
          rawValueExists: true,
          isMasked: false,
          schema: {
            key: 'OPENAI_API_KEY',
            category: 'ai_model',
            dataType: 'string',
            uiControl: 'password',
            isSensitive: true,
            isRequired: true,
            isEditable: true,
            options: [],
            validation: {},
            displayOrder: 1,
          },
        }}
        value="secret"
        onChange={onChange}
        issues={[
          {
            key: 'OPENAI_API_KEY',
            code: 'required',
            message: 'API Key 必填',
            severity: 'error',
          },
        ]}
      />
    );

    expect(screen.getByText('敏感')).toBeInTheDocument();
    expect(screen.getByText('API Key 必填')).toBeInTheDocument();

    const input = screen.getByLabelText('OpenAI API Key');
    fireEvent.focus(input);
    fireEvent.change(input, {
      target: { value: 'updated-secret' },
    });

    expect(onChange).toHaveBeenCalledWith('OPENAI_API_KEY', 'updated-secret');
  });

  it('renders multi-value sensitive fields with external delete actions', () => {
    const onChange = vi.fn();

    render(
      <SettingsField
        item={{
          key: 'OPENAI_API_KEYS',
          value: 'secret-a,secret-b',
          rawValueExists: true,
          isMasked: false,
          schema: {
            key: 'OPENAI_API_KEYS',
            category: 'ai_model',
            dataType: 'string',
            uiControl: 'password',
            isSensitive: true,
            isRequired: false,
            isEditable: true,
            options: [],
            validation: { multiValue: true },
            displayOrder: 1,
          },
        }}
        value="secret-a,secret-b"
        onChange={onChange}
      />
    );

    expect(screen.getAllByRole('button', { name: '顯示內容' })).toHaveLength(2);
    expect(screen.getAllByRole('button', { name: '刪除' })).toHaveLength(2);
  });

  it('allows optional select fields to be cleared when schema provides an empty option', () => {
    const onChange = vi.fn();

    render(
      <SettingsField
        item={{
          key: 'NOTIFICATION_MIN_SEVERITY',
          value: 'warning',
          rawValueExists: true,
          isMasked: false,
          schema: {
            key: 'NOTIFICATION_MIN_SEVERITY',
            title: 'Notification Minimum Severity',
            category: 'notification',
            dataType: 'string',
            uiControl: 'select',
            isSensitive: false,
            isRequired: false,
            isEditable: true,
            options: [
              { label: 'Not set', value: '' },
              { label: 'info', value: 'info' },
              { label: 'warning', value: 'warning' },
              { label: 'error', value: 'error' },
              { label: 'critical', value: 'critical' },
            ],
            validation: { enum: ['', 'info', 'warning', 'error', 'critical'] },
            displayOrder: 69,
          },
        }}
        value="warning"
        onChange={onChange}
      />
    );

    const select = screen.getByLabelText('最小通知級別');
    expect(screen.getByRole('option', { name: '未設定' })).not.toBeDisabled();
    expect(screen.queryByRole('option', { name: '請選擇' })).not.toBeInTheDocument();

    fireEvent.change(select, { target: { value: '' } });

    expect(onChange).toHaveBeenCalledWith('NOTIFICATION_MIN_SEVERITY', '');
  });

  it('renders localized labels for real system config select options', () => {
    const selectCases = [
      {
        key: 'NEWS_STRATEGY_PROFILE',
        category: 'data_source',
        options: ['ultra_short', 'short', 'medium', 'long'],
        expectedLabels: ['超短線（1天）', '短期（3天）', '中期（7天）', '長期（30天）'],
      },
      {
        key: 'REPORT_TYPE',
        category: 'notification',
        options: ['simple', 'full', 'brief'],
        expectedLabels: ['簡潔', '完整', '簡報'],
      },
      {
        key: 'LOG_LEVEL',
        category: 'system',
        options: ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        expectedLabels: ['除錯', '資訊', '警告', '錯誤', '嚴重'],
      },
      {
        key: 'MARKET_REVIEW_REGION',
        category: 'system',
        options: ['cn', 'hk', 'us', 'both'],
        expectedLabels: ['A 股', '港股', '美股', '全部市場'],
      },
    ] as const;

    selectCases.forEach(({ key, category, options, expectedLabels }) => {
      const { unmount } = render(
        <SettingsField
          item={{
            key,
            value: options[0],
            rawValueExists: true,
            isMasked: false,
            schema: {
              key,
              title: key,
              category,
              dataType: 'string',
              uiControl: 'select',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [...options],
              validation: {},
              displayOrder: 1,
            },
          }}
          value={options[0]}
          onChange={() => undefined}
        />
      );

      expectedLabels.forEach((label) => {
        expect(screen.getByRole('option', { name: label })).toBeInTheDocument();
      });

      options.forEach((rawOption) => {
        expect(screen.queryByRole('option', { name: rawOption })).not.toBeInTheDocument();
      });

      unmount();
    });
  });

  it('renders context compression profile options with Chinese labels', () => {
    const onChange = vi.fn();

    render(
      <SettingsField
        item={{
          key: 'AGENT_CONTEXT_COMPRESSION_PROFILE',
          value: 'balanced',
          rawValueExists: true,
          isMasked: false,
          schema: {
            key: 'AGENT_CONTEXT_COMPRESSION_PROFILE',
            category: 'agent',
            dataType: 'string',
            uiControl: 'select',
            isSensitive: false,
            isRequired: false,
            isEditable: true,
            options: [
              { label: '成本優先', value: 'cost' },
              { label: '均衡推薦', value: 'balanced' },
              { label: '長上下文原文優先', value: 'long_context_raw_first' },
            ],
            validation: {
              enum: ['cost', 'balanced', 'long_context_raw_first'],
            },
            displayOrder: 72,
          },
        }}
        value="balanced"
        onChange={onChange}
      />
    );

    expect(screen.getByLabelText('上下文壓縮策略')).toBeInTheDocument();
    expect(screen.getByRole('option', { name: '成本優先' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: '均衡推薦' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: '長上下文原文優先' })).toBeInTheDocument();
  });

  it('renders blank-value preset guidance for context compression numeric fields', () => {
    const onChange = vi.fn();

    render(
      <>
        <SettingsField
          item={{
            key: 'AGENT_CONTEXT_COMPRESSION_TRIGGER_TOKENS',
            value: '',
            rawValueExists: false,
            isMasked: false,
            schema: {
              key: 'AGENT_CONTEXT_COMPRESSION_TRIGGER_TOKENS',
              category: 'agent',
              dataType: 'integer',
              uiControl: 'number',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: { min: 1000 },
              displayOrder: 73,
            },
          }}
          value=""
          onChange={onChange}
        />
        <SettingsField
          item={{
            key: 'AGENT_CONTEXT_PROTECTED_TURNS',
            value: '',
            rawValueExists: false,
            isMasked: false,
            schema: {
              key: 'AGENT_CONTEXT_PROTECTED_TURNS',
              category: 'agent',
              dataType: 'integer',
              uiControl: 'number',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: { min: 1 },
              displayOrder: 74,
            },
          }}
          value=""
          onChange={onChange}
        />
      </>
    );

    expect(screen.getByLabelText('壓縮觸發閾值（tokens）')).toBeInTheDocument();
    expect(screen.getByLabelText('原文保護輪次')).toBeInTheDocument();
    expect(screen.getByText(/估算曆史 token 超過該值時觸發摘要/)).toHaveTextContent('留空則跟隨當前上下文壓縮策略 profile 預設值');
    expect(screen.getByText(/壓縮時最近 N 個使用者輪次及其後的回覆保持原文/)).toHaveTextContent('留空則跟隨當前上下文壓縮策略 profile 預設值');
  });

  it('renders localized custom webhook body template guidance', () => {
    const onChange = vi.fn();

    render(
      <SettingsField
        item={{
          key: 'CUSTOM_WEBHOOK_BODY_TEMPLATE',
          value: '',
          rawValueExists: false,
          isMasked: false,
          schema: {
            key: 'CUSTOM_WEBHOOK_BODY_TEMPLATE',
            category: 'notification',
            dataType: 'string',
            uiControl: 'textarea',
            isSensitive: false,
            isRequired: false,
            isEditable: true,
            options: [],
            validation: {},
            displayOrder: 52,
          },
        }}
        value=""
        onChange={onChange}
      />
    );

    expect(screen.getByLabelText('自定義 Webhook Body 模板')).toBeInTheDocument();
    expect(screen.getByText(/會先於 Bark、Slack、Discord 等自動 payload 生效/)).toBeInTheDocument();
    expect(screen.getByText(/裸 \$content \/ \$title 不做 JSON 轉義/)).toBeInTheDocument();
  });

  it('opens detailed field help when help metadata is available', () => {
    render(
      <SettingsField
        item={{
          key: 'STOCK_LIST',
          value: '600519,300750',
          rawValueExists: true,
          isMasked: false,
          schema: {
            key: 'STOCK_LIST',
            category: 'base',
            dataType: 'array',
            uiControl: 'textarea',
            isSensitive: false,
            isRequired: false,
            isEditable: true,
            options: [],
            validation: {},
            displayOrder: 1,
            helpKey: 'settings.base.STOCK_LIST',
            examples: ['STOCK_LIST=600519,300750,002594'],
            docs: [
              {
                label: '完整指南',
                href: 'https://example.com/full-guide',
              },
            ],
            warningCodes: [],
          },
        }}
        value="600519,300750"
        onChange={() => undefined}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: '檢視 自選股列表 配置說明' }));

    expect(screen.getByRole('dialog', { name: '自選股列表' })).toBeInTheDocument();
    expect(screen.getByText('STOCK_LIST=600519,300750,002594')).toBeInTheDocument();
    const docLink = screen.getByRole('link', { name: /完整指南/ });
    expect(docLink).toHaveAttribute('href', 'https://example.com/full-guide');

    const closeButtons = screen.getAllByRole('button', { name: '關閉配置說明' });
    expect(closeButtons[0].tabIndex).toBe(-1);
    const closeButton = closeButtons.find((button) => button.tabIndex !== -1);
    expect(closeButton).toBeDefined();

    closeButton?.focus();
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });
    expect(docLink).toHaveFocus();

    fireEvent.keyDown(document, { key: 'Tab' });
    expect(closeButton).toHaveFocus();

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('dialog', { name: '自選股列表' })).not.toBeInTheDocument();
  });
});
