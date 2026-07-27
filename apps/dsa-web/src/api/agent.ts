import apiClient from './index';
import { toCamelCase } from './utils';
import { API_BASE_URL } from '../utils/constants';
import { createApiError, isApiRequestError, parseApiError } from './error';

export interface ChatStreamOptions {
  signal?: AbortSignal;
}

export interface ChatRequest {
  message: string;
  skills?: string[];
}

export interface ChatStreamRequest extends ChatRequest {
  session_id?: string;
  context?: unknown;
}

export interface ChatResponse {
  success: boolean;
  content: string;
  session_id: string;
  error?: string;
}

export interface SkillInfo {
  id: string;
  name: string;
  description: string;
}

export interface SkillsResponse {
  skills: SkillInfo[];
  default_skill_id: string;
}

export interface ChatSessionItem {
  session_id: string;
  title: string;
  message_count: number;
  created_at: string | null;
  last_active: string | null;
}

export interface ChatJobStatus {
  sessionId: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  createdAt: string;
  startedAt?: string | null;
  finishedAt?: string | null;
  error?: string | null;
  stepCount: number;
}

export interface ChatSessionMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string | null;
}

export const agentApi = {
  async chat(payload: ChatRequest): Promise<ChatResponse> {
    const response = await apiClient.post<ChatResponse>('/api/v1/agent/chat', payload, {
      timeout: 120000,
    });
    return response.data;
  },
  async getSkills(): Promise<SkillsResponse> {
    const response = await apiClient.get<SkillsResponse>('/api/v1/agent/skills');
    return response.data;
  },
  async getChatSessions(limit = 50): Promise<ChatSessionItem[]> {
    const response = await apiClient.get<{ sessions: ChatSessionItem[] }>('/api/v1/agent/chat/sessions', { params: { limit } });
    return response.data.sessions;
  },
  async getChatSessionMessages(sessionId: string): Promise<ChatSessionMessage[]> {
    const response = await apiClient.get<{ messages: ChatSessionMessage[] }>(`/api/v1/agent/chat/sessions/${sessionId}`);
    return response.data.messages;
  },
  async deleteChatSession(sessionId: string): Promise<void> {
    await apiClient.delete(`/api/v1/agent/chat/sessions/${sessionId}`);
  },

  /**
   * Get chat analysis job status for a session.
   * @param sessionId Session ID to check
   * @returns Job status info or null if no job exists
   */
  getChatJobStatus: async (sessionId: string): Promise<ChatJobStatus | null> => {
    try {
      const response = await apiClient.get<Record<string, unknown>>(
        `/api/v1/agent/chat/job/${sessionId}`,
      );
      return toCamelCase<ChatJobStatus>(response.data);
    } catch (error: unknown) {
      // 404 means no job exists — not an error for our purposes
      if (isApiRequestError(error) && error.response?.status === 404) {
        return null;
      }
      throw error;
    }
  },
  async sendChat(content: string): Promise<{ success: boolean }> {
    const response = await apiClient.post<{
      success: boolean;
      error?: string;
      message?: string;
    }>('/api/v1/agent/chat/send', { content });
    const data = response.data;
    if (data.success === false) {
      throw new Error(data.message || '傳送失敗');
    }
    return { success: true };
  },
  async chatStream(
    payload: ChatStreamRequest,
    options?: ChatStreamOptions,
  ): Promise<Response> {
    const base = API_BASE_URL || '';
    const url = `${base}/api/v1/agent/chat/stream`;
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        credentials: 'include',
        signal: options?.signal,
      });

      if (response.ok) {
        return response;
      }

      const contentType = response.headers.get('content-type') || '';
      let responseData: unknown = null;
      if (contentType.includes('application/json')) {
        responseData = await response.json().catch(() => null);
      } else {
        responseData = await response.text().catch(() => null);
      }

      const parsed = parseApiError({
        response: {
          status: response.status,
          statusText: response.statusText,
          data: responseData,
        },
      });
      throw createApiError(parsed, {
        response: {
          status: response.status,
          statusText: response.statusText,
          data: responseData,
        },
      });
    } catch (error: unknown) {
      if (isApiRequestError(error)) {
        throw error;
      }
      if (error instanceof Error && error.name === 'AbortError') {
        throw error;
      }

      const parsed = parseApiError(error);
      throw createApiError(parsed, { cause: error });
    }
  },
};
