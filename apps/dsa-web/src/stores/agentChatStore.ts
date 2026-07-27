import { create } from 'zustand';
import { agentApi } from '../api/agent';
import type { ChatSessionItem, ChatStreamRequest } from '../api/agent';
import {
  getParsedApiError,
  isApiRequestError,
  isParsedApiError,
  type ParsedApiError,
} from '../api/error';
import { generateUUID } from '../utils/uuid';

const STORAGE_KEY_SESSION = 'dsa_chat_session_id';

export interface ProgressStep {
  type: string;
  step?: number;
  tool?: string;
  display_name?: string;
  success?: boolean;
  duration?: number;
  message?: string;
  content?: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  skills?: string[];
  skill?: string;
  skillNames?: string[];
  skillName?: string;
  thinkingSteps?: ProgressStep[];
}

export interface StreamMeta {
  skillNames?: string[];
  skillName?: string;
}

type StreamFailureEvent = {
  type: string;
  success?: boolean;
  content?: string;
  error?: unknown;
  message?: unknown;
};

function getFirstMeaningfulStreamError(...candidates: Array<unknown>): unknown {
  for (const candidate of candidates) {
    if (typeof candidate === 'string') {
      if (candidate.trim() !== '') {
        return candidate;
      }
      continue;
    }

    if (candidate != null) {
      return candidate;
    }
  }

  return undefined;
}

function getStreamFailureError(
  event: StreamFailureEvent,
  fallbackMessage: string,
): ParsedApiError {
  return getParsedApiError(
    getFirstMeaningfulStreamError(
      event.error,
      event.message,
      event.content,
      fallbackMessage,
    ),
  );
}

interface AgentChatState {
  messages: Message[];
  loading: boolean;
  progressSteps: ProgressStep[];
  sessionId: string;
  sessions: ChatSessionItem[];
  sessionsLoading: boolean;
  chatError: ParsedApiError | null;
  currentRoute: string;
  completionBadge: boolean;
  hasInitialLoad: boolean;
  abortController: AbortController | null;
  /** setTimeout handle for polling a session's job completion. */
  pendingSessionPolling: ReturnType<typeof setTimeout> | null;
  /** The session being polled for job completion. */
  pendingPollingSessionId: string | null;
}

interface AgentChatActions {
  setCurrentRoute: (path: string) => void;
  clearCompletionBadge: () => void;
  loadSessions: () => Promise<void>;
  loadInitialSession: () => Promise<void>;
  switchSession: (targetSessionId: string) => Promise<void>;
  startNewChat: () => void;
  startStream: (payload: ChatStreamRequest, meta?: StreamMeta) => Promise<void>;
  /** Poll chat job status for a session, reloading messages on completion. */
  pollChatJobCompletion: (targetSessionId: string) => Promise<void>;
}

const getInitialSessionId = (): string =>
  typeof localStorage !== 'undefined'
    ? localStorage.getItem(STORAGE_KEY_SESSION) || generateUUID()
    : generateUUID();

export const useAgentChatStore = create<AgentChatState & AgentChatActions>((set, get) => ({
  messages: [],
  loading: false,
  progressSteps: [],
  sessionId: getInitialSessionId(),
  sessions: [],
  sessionsLoading: false,
  chatError: null,
  currentRoute: '',
  completionBadge: false,
  hasInitialLoad: false,
  abortController: null,
  pendingSessionPolling: null,
  pendingPollingSessionId: null,

  setCurrentRoute: (path) => set({ currentRoute: path }),

  clearCompletionBadge: () => set({ completionBadge: false }),

  loadSessions: async () => {
    set({ sessionsLoading: true });
    try {
      const sessions = await agentApi.getChatSessions();
      set({ sessions });
    } catch {
      // Ignore load errors
    } finally {
      set({ sessionsLoading: false });
    }
  },

  loadInitialSession: async () => {
    const { hasInitialLoad } = get();
    if (hasInitialLoad) return;
    set({ hasInitialLoad: true, sessionsLoading: true });

    try {
      const sessionList = await agentApi.getChatSessions();
      set({ sessions: sessionList });

      const savedId = localStorage.getItem(STORAGE_KEY_SESSION);
      if (savedId) {
        const sessionExists = sessionList.some((s) => s.session_id === savedId);
        if (sessionExists) {
          const msgs = await agentApi.getChatSessionMessages(savedId);
          if (msgs.length > 0) {
            set({
              messages: msgs.map((m) => ({
                id: m.id,
                role: m.role,
                content: m.content,
              })),
            });
            // Check for running analysis job on initial load (e.g. page refresh)
            const hasUnansweredQuery =
              msgs.length > 0 &&
              msgs[msgs.length - 1].role === 'user';
            if (hasUnansweredQuery) {
              try {
                const jobStatus = await agentApi.getChatJobStatus(savedId);
                if (get().sessionId !== savedId) return;
                if (jobStatus && jobStatus.status === 'running') {
                  set({
                    loading: true,
                    progressSteps: [{
                      type: 'thinking',
                      message: '分析仍在後台進行中...',
                    }],
                  });
                  get().pollChatJobCompletion(savedId);
                }
              } catch {
                // Ignore
              }
            }
          }
        } else {
          const newId = generateUUID();
          set({ sessionId: newId });
          localStorage.setItem(STORAGE_KEY_SESSION, newId);
        }
      } else {
        localStorage.setItem(STORAGE_KEY_SESSION, get().sessionId);
      }
    } catch {
      // Ignore
    } finally {
      set({ sessionsLoading: false });
    }
  },

  switchSession: async (targetSessionId) => {
    const { sessionId, messages, abortController, pendingSessionPolling } = get();
    if (targetSessionId === sessionId && messages.length > 0) return;

    // Cancel any ongoing polling (we're leaving the previous polling target)
    if (pendingSessionPolling !== null) {
      clearTimeout(pendingSessionPolling);
      set({ pendingSessionPolling: null, pendingPollingSessionId: null });
    }

    // Abort current SSE stream (detach observer; analysis continues on backend)
    abortController?.abort();
    set({
      messages: [],
      sessionId: targetSessionId,
      loading: false,
      progressSteps: [],
      chatError: null,
      abortController: null,
    });
    localStorage.setItem(STORAGE_KEY_SESSION, targetSessionId);

    try {
      const msgs = await agentApi.getChatSessionMessages(targetSessionId);
      if (get().sessionId !== targetSessionId) {
        return;
      }
      set({
        messages: msgs.map((m) => ({
          id: m.id,
          role: m.role,
          content: m.content,
        })),
      });

      // Check if there is a running analysis job for this session.
      // If the last message is from user without an assistant response,
      // the analysis may still be in progress on the backend.
      const hasUnansweredQuery =
        msgs.length > 0 &&
        msgs[msgs.length - 1].role === 'user';
      if (hasUnansweredQuery) {
        try {
          const jobStatus = await agentApi.getChatJobStatus(targetSessionId);
          if (get().sessionId !== targetSessionId) return;
          if (jobStatus && jobStatus.status === 'running') {
            // Analysis is still running — show loading and poll for completion.
            set({
              loading: true,
              progressSteps: [{
                type: 'thinking',
                message: '分析仍在後台進行中...',
              }],
            });
            // Start polling (async, no await)
            get().pollChatJobCompletion(targetSessionId);
          }
        } catch {
          // Ignore errors from status check (e.g. network timeout)
        }
      }
    } catch {
      // Ignore
    }
  },

  startNewChat: () => {
    // Cancel any in-flight polling first
    const st = get();
    if (st.pendingSessionPolling !== null) {
      clearTimeout(st.pendingSessionPolling);
    }
    // Abort any in-flight stream so the old request does not keep running
    st.abortController?.abort();
    const newId = generateUUID();
    set({
      sessionId: newId,
      messages: [],
      loading: false,
      progressSteps: [],
      chatError: null,
      abortController: null,
      pendingSessionPolling: null,
      pendingPollingSessionId: null,
    });
    localStorage.setItem(STORAGE_KEY_SESSION, newId);
  },

  startStream: async (payload, meta) => {
    if (get().loading) return;
    // Cancel any pending polling — we're starting fresh
    const currentState = get();
    if (currentState.pendingSessionPolling !== null) {
      clearTimeout(currentState.pendingSessionPolling);
      set({ pendingSessionPolling: null, pendingPollingSessionId: null });
    }
    const { abortController: prevAc, sessionId: storeSessionId } = currentState;
    prevAc?.abort();

    const ac = new AbortController();
    set({ abortController: ac });

    const streamSessionId = payload.session_id || storeSessionId;
    const skillNames = meta?.skillNames?.length
      ? meta.skillNames
      : [meta?.skillName ?? '通用'];
    const skillName = skillNames.join('、');

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: payload.message,
      skills: payload.skills,
      skill: payload.skills?.[0],
      skillNames,
      skillName,
    };

    set((s) => ({
      messages: [...s.messages, userMessage],
      loading: true,
      progressSteps: [],
      chatError: null,
      sessions: s.sessions.some((x) => x.session_id === streamSessionId)
        ? s.sessions
        : [
            {
              session_id: streamSessionId,
              title: payload.message.slice(0, 60),
              message_count: 1,
              created_at: new Date().toISOString(),
              last_active: new Date().toISOString(),
            },
            ...s.sessions,
          ],
    }));

    try {
      const response = await agentApi.chatStream(payload, { signal: ac.signal });
      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      let finalContent: string | null = null;
      const currentProgressSteps: ProgressStep[] = [];
        const processLine = (line: string) => {
          if (!line.startsWith('data: ')) return;

          const event = JSON.parse(line.slice(6)) as ProgressStep;
          if (event.type === 'done') {
            const doneEvent = event as unknown as StreamFailureEvent;
            if (doneEvent.success === false) {
              throw getStreamFailureError(doneEvent, '大模型呼叫出錯，請檢查 API Key 配置');
            }
            finalContent = doneEvent.content ?? '';
            return;
          }

          if (event.type === 'error') {
            throw getStreamFailureError(event as unknown as StreamFailureEvent, '分析出錯');
          }

        currentProgressSteps.push(event);
        set((s) => ({ progressSteps: [...s.progressSteps, event] }));
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop() ?? '';

        for (const line of lines) {
          try {
            processLine(line);
          } catch (parseErr: unknown) {
            if (isParsedApiError(parseErr) || isApiRequestError(parseErr)) {
              throw parseErr;
            }
          }
        }
      }

      if (buf.trim().startsWith('data: ')) {
        try {
          processLine(buf.trim());
        } catch (parseErr: unknown) {
          if (isParsedApiError(parseErr) || isApiRequestError(parseErr)) {
            throw parseErr;
          }
        }
      }

      const { sessionId: currentSessionId, currentRoute } = get();
      const shouldAppend =
        currentSessionId === streamSessionId && !ac.signal.aborted;

      if (shouldAppend) {
        set((s) => ({
          messages: [
            ...s.messages,
            {
              id: (Date.now() + 1).toString(),
              role: 'assistant',
              content: finalContent || '（無內容）',
              skills: payload.skills,
              skill: payload.skills?.[0],
              skillNames,
              skillName,
              thinkingSteps: [...currentProgressSteps],
            },
          ],
        }));
      }

      if (currentRoute !== '/chat') {
        set({ completionBadge: true });
      }
    } catch (error: unknown) {
      if (error instanceof Error && error.name === 'AbortError') {
        // User-initiated abort: silent, no badge
      } else {
        set({ chatError: getParsedApiError(error) });
        const { currentRoute } = get();
        if (currentRoute !== '/chat') {
          set({ completionBadge: true });
        }
      }
    } finally {
      const { abortController: currentAc } = get();
      if (currentAc === ac) {
        set({
          loading: false,
          progressSteps: [],
          abortController: null,
        });
      }
      await get().loadSessions();
    }
  },

  pollChatJobCompletion: async (targetSessionId) => {
    // Guard: only poll if we're still on this session
    if (get().sessionId !== targetSessionId) return;

    // Clear old polling handle
    const prev = get().pendingSessionPolling;
    if (prev !== null) clearTimeout(prev);
    set({ pendingSessionPolling: null, pendingPollingSessionId: targetSessionId });

    try {
      const jobStatus = await agentApi.getChatJobStatus(targetSessionId);
      if (get().sessionId !== targetSessionId) return;

      if (!jobStatus) {
        // No job found (TTL expired or never existed) — stop polling
        set({
          loading: false,
          progressSteps: [],
          pendingSessionPolling: null,
          pendingPollingSessionId: null,
        });
        return;
      }

      if (jobStatus.status === 'completed') {
        // Analysis completed — reload messages to get the assistant response
        const msgs = await agentApi.getChatSessionMessages(targetSessionId);
        if (get().sessionId !== targetSessionId) return;
        set({
          messages: msgs.map((m) => ({
            id: m.id,
            role: m.role,
            content: m.content,
          })),
          loading: false,
          progressSteps: [],
          pendingSessionPolling: null,
          pendingPollingSessionId: null,
        });
        return;
      }

      if (jobStatus.status === 'failed') {
        set({
          loading: false,
          progressSteps: [],
          pendingSessionPolling: null,
          pendingPollingSessionId: null,
          chatError: getParsedApiError(jobStatus.error || '分析失敗'),
        });
        return;
      }

      if (jobStatus.status === 'queued' || jobStatus.status === 'running') {
        // Still running — update progress and poll again
        set({
          loading: true,
          progressSteps: [{
            type: 'thinking',
            message: '分析仍在後台進行中...',
          }],
        });
        // Poll again after 3 seconds
        const timeoutHandle = setTimeout(() => {
          get().pollChatJobCompletion(targetSessionId);
        }, 3000);
        set({ pendingSessionPolling: timeoutHandle });
      }
    } catch {
      // Transient error — retry after 5 seconds
      if (get().sessionId === targetSessionId) {
        const timeoutHandle = setTimeout(() => {
          get().pollChatJobCompletion(targetSessionId);
        }, 5000);
        set({ pendingSessionPolling: timeoutHandle });
      }
    }
  },
}));
