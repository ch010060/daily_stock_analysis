# -*- coding: utf-8 -*-
"""
Agent API endpoints.
"""

import asyncio
import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from src.config import get_config
from src.services.agent_model_service import list_agent_model_deployments
from src.services.symbol_universe import get_default_symbol_resolver

# Tool name -> Chinese display name mapping
TOOL_DISPLAY_NAMES: Dict[str, str] = {
    "get_realtime_quote":         "獲取實時行情",
    "get_daily_history":          "獲取歷史K線",
    "get_analysis_context":       "獲取分析上下文",
    "get_stock_info":             "獲取股票基本面",
    "search_stock_news":          "搜尋股票新聞",
    "search_comprehensive_intel": "搜尋綜合情報",
    "analyze_trend":              "分析技術趨勢",
    "calculate_ma":               "計算均線系統",
    "get_volume_analysis":        "分析量能變化",
    "analyze_pattern":            "識別K線形態",
    "get_market_indices":         "獲取市場指數",
    "get_sector_rankings":        "分析行業板塊",
    "get_skill_backtest_summary": "獲取技能回測概覽",
    "get_strategy_backtest_summary": "獲取策略回測概覽",
    "get_stock_backtest_summary": "獲取個股回測資料",
}

logger = logging.getLogger(__name__)

router = APIRouter()

class ChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    message: str
    session_id: Optional[str] = None
    skills: Optional[List[str]] = Field(
        default=None,
        validation_alias=AliasChoices("skills", "strategies"),
    )
    context: Optional[Dict[str, Any]] = None  # Previous analysis context for data reuse

    @property
    def effective_skills(self) -> Optional[List[str]]:
        """Return skill ids from the unified request shape."""
        return self.skills

class ChatResponse(BaseModel):
    success: bool
    content: str
    session_id: str
    error: Optional[str] = None


def _route_b_context_from_message(message: str) -> Dict[str, Any]:
    """Resolve TW/US chat targets locally before invoking the Agent LLM."""
    text = (message or "").strip()
    if not text:
        return {}

    resolver = get_default_symbol_resolver()
    cache = resolver.cache
    candidates: list[str] = []

    for token in re.findall(r"[A-Za-z]{1,32}|\d{4,6}[A-Za-z]?", text):
        candidates.append(token)

    normalized_text = text.casefold()
    for record in cache.records:
        values = [record.name, *(record.aliases or [])]
        if any(value and value.casefold() in normalized_text for value in values):
            candidates.append(record.raw_symbol)

    seen: set[str] = set()
    for candidate in candidates:
        key = candidate.casefold()
        if key in seen:
            continue
        seen.add(key)
        result = resolver.resolve(candidate)
        if result.status == "resolved" and result.selected is not None:
            selected = result.selected
            return {
                "stock_code": selected.raw_symbol,
                "stock_name": selected.name,
                "market": selected.market,
                "selection_source": "local_symbol_universe",
                "resolved_canonical_symbol": selected.canonical_symbol,
            }
    return {}

class SkillInfo(BaseModel):
    id: str
    name: str
    description: str

class SkillsResponse(BaseModel):
    skills: List[SkillInfo]
    default_skill_id: str = ""


class StrategiesResponse(BaseModel):
    strategies: List[SkillInfo]
    default_strategy_id: str = ""


class AgentModelDeployment(BaseModel):
    deployment_id: str
    model: str
    provider: str
    source: str
    api_base: Optional[str] = None
    deployment_name: Optional[str] = None
    is_primary: bool = False
    is_fallback: bool = False


class AgentModelsResponse(BaseModel):
    models: List[AgentModelDeployment]


@router.get("/models", response_model=AgentModelsResponse)
async def get_agent_models():
    """Get configured Agent model deployments for frontend selection."""
    config = get_config()
    return AgentModelsResponse(
        models=[AgentModelDeployment(**item) for item in list_agent_model_deployments(config)]
    )


def _build_skills_response(config) -> SkillsResponse:
    from src.agent.factory import get_skill_manager
    from src.agent.skills.defaults import get_primary_default_skill_id

    skill_manager = get_skill_manager(config)
    available_skills = sorted(
        [
            skill
            for skill in skill_manager.list_skills()
            if getattr(skill, "user_invocable", True)
        ],
        key=lambda skill: (
            int(getattr(skill, "default_priority", 100)),
            skill.display_name,
            skill.name,
        ),
    )
    skills = [
        SkillInfo(id=skill.name, name=skill.display_name, description=skill.description)
        for skill in available_skills
    ]
    return SkillsResponse(
        skills=skills,
        default_skill_id=get_primary_default_skill_id(available_skills),
    )


@router.get("/skills", response_model=SkillsResponse)
async def get_skills():
    """
    Get available agent strategy skills.
    """
    return _build_skills_response(get_config())


@router.get("/strategies", response_model=StrategiesResponse, include_in_schema=False)
async def get_strategies():
    """Compatibility alias for legacy clients."""
    payload = _build_skills_response(get_config())
    return StrategiesResponse(
        strategies=payload.skills,
        default_strategy_id=payload.default_skill_id,
    )

@router.post("/chat", response_model=ChatResponse)
async def agent_chat(request: ChatRequest):
    """
    Chat with the AI Agent.
    """
    config = get_config()
    
    if not config.is_agent_available():
        raise HTTPException(status_code=400, detail="Agent mode is not enabled")
        
    session_id = request.session_id or str(uuid.uuid4())
    
    try:
        skills = request.effective_skills
        executor = _build_executor(config, skills or None)

        # Pass explicit skills into context for the orchestrator.
        # Direct assignment so caller-provided skills always take precedence
        # over any stale value carried in the context dict.
        ctx = dict(request.context or {})
        if "stock_code" not in ctx:
            ctx.update(_route_b_context_from_message(request.message))
        if skills is not None:
            ctx["skills"] = skills

        # Offload the blocking call to a thread to avoid blocking the event loop.
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: executor.chat(message=request.message, session_id=session_id,
                                  context=ctx),
        )

        return ChatResponse(
            success=result.success,
            content=result.content,
            session_id=session_id,
            error=result.error
        )
            
    except Exception as e:
        logger.error(f"Agent chat API failed: {e}")
        logger.exception("Agent chat error details:")
        raise HTTPException(status_code=500, detail=str(e))


class SessionItem(BaseModel):
    session_id: str
    title: str
    message_count: int
    created_at: Optional[str] = None
    last_active: Optional[str] = None

class SessionsResponse(BaseModel):
    sessions: List[SessionItem]

class SessionMessagesResponse(BaseModel):
    session_id: str
    messages: List[Dict[str, Any]]


@router.get("/chat/sessions", response_model=SessionsResponse)
async def list_chat_sessions(limit: int = 50, user_id: Optional[str] = None):
    """獲取聊天會話列表

    Args:
        limit: Maximum number of sessions to return.
        user_id: Optional platform-prefixed user identifier for session
            isolation.  When provided, only sessions whose session_id
            starts with this prefix are returned.  The value must
            include the platform prefix, e.g. ``telegram_12345``,
            ``feishu_ou_abc``.
    """
    from src.storage import get_db
    sessions = get_db().get_chat_sessions(
        limit=limit,
        session_prefix=user_id,
        extra_session_ids=[user_id] if user_id else None,
    )
    return SessionsResponse(sessions=sessions)


@router.get("/chat/sessions/{session_id}", response_model=SessionMessagesResponse)
async def get_chat_session_messages(session_id: str, limit: int = 100):
    """獲取單個會話的完整訊息"""
    from src.storage import get_db
    messages = get_db().get_conversation_messages(session_id, limit=limit)
    return SessionMessagesResponse(session_id=session_id, messages=messages)


@router.delete("/chat/sessions/{session_id}")
async def delete_chat_session(session_id: str):
    """刪除指定會話"""
    from src.storage import get_db
    count = get_db().delete_conversation_session(session_id)
    return {"deleted": count}


class SendChatRequest(BaseModel):
    """Request body for sending chat content to notification channels."""

    content: str = Field(..., min_length=1, max_length=50000)
    title: Optional[str] = None


@router.post("/chat/send")
async def send_chat_to_notification(request: SendChatRequest):
    """
    Send chat session content to configured notification channels.
    Uses run_in_executor to avoid blocking the event loop.
    """
    from src.notification import NotificationService

    loop = asyncio.get_running_loop()
    success = await loop.run_in_executor(
        None,
        lambda: NotificationService().send(request.content),
    )
    if not success:
        return {
            "success": False,
            "error": "no_channels",
            "message": "未配置通知通道，請先在設定中配置",
        }
    return {"success": True}


def _build_executor(config, skills: Optional[List[str]] = None):
    """Build and return a configured AgentExecutor (sync helper)."""
    from src.agent.factory import build_agent_executor
    return build_agent_executor(config, skills=skills)


async def _run_research_in_background(
    agent,
    question: str,
    context: Optional[Dict[str, Any]],
    *,
    timeout: int,
):
    """Run deep research off the event loop with an internal overall timeout."""
    return await asyncio.to_thread(
        agent.research,
        question,
        context,
        timeout_seconds=timeout,
    )


# ============================================================
# Deep research endpoint
# ============================================================

class ResearchRequest(BaseModel):
    question: str
    stock_code: Optional[str] = None

class ResearchResponse(BaseModel):
    success: bool
    content: str
    sources: List[str] = Field(default_factory=list)
    token_usage: int = 0
    error: Optional[str] = None


@router.post("/research", response_model=ResearchResponse)
async def agent_research(request: ResearchRequest):
    """Run a deep-research query via the ResearchAgent.

    Similar to the ``/research`` bot command but exposed as a REST endpoint.
    """
    config = get_config()
    if not config.is_agent_available():
        raise HTTPException(status_code=400, detail="Agent mode is not enabled")

    question = request.question
    context: Optional[Dict[str, Any]] = None
    if request.stock_code:
        question = f"[Stock: {request.stock_code}] {question}"
        context = {"stock_code": request.stock_code}

    try:
        from src.agent.research import ResearchAgent
        from src.agent.factory import get_tool_registry
        from src.agent.llm_adapter import LLMToolAdapter

        registry = get_tool_registry()
        llm_adapter = LLMToolAdapter(config)
        budget = getattr(config, "agent_deep_research_budget", 30000)

        agent = ResearchAgent(
            tool_registry=registry,
            llm_adapter=llm_adapter,
            token_budget=budget,
        )

        research_timeout = getattr(config, "agent_deep_research_timeout", 180)

        result = await _run_research_in_background(
            agent,
            question,
            context,
            timeout=research_timeout,
        )
        if getattr(result, "timed_out", False):
            logger.warning("Agent research API timed out after %ss", research_timeout)
            return ResearchResponse(
                success=False,
                content="",
                sources=[],
                token_usage=0,
                error=f"Deep research timed out after {research_timeout}s",
            )

        return ResearchResponse(
            success=result.success,
            content=result.report,
            sources=[f"Sub-question {i+1}: {q}" for i, q in enumerate(result.sub_questions)],
            token_usage=result.total_tokens,
            error=result.error if not result.success else None,
        )
    except Exception as e:
        logger.error("Agent research API failed: %s", e)
        logger.exception("Agent research error details:")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
async def agent_chat_stream(request: ChatRequest):
    """
    Chat with the AI Agent, streaming progress via SSE.
    Each SSE event is a JSON object with a 'type' field:
      - thinking: AI is deciding next action
      - tool_start: a tool call has begun
      - tool_done: a tool call finished
      - generating: final answer being generated
      - done: analysis complete, contains 'content' and 'success'
      - error: error occurred, contains 'message'

    Lifecycle semantics:
      - Analysis execution is decoupled from the SSE HTTP connection lifetime.
      - A ChatJobManager tracks running jobs by session_id.
      - If a job already exists for this session, the request attaches as an
        observer rather than starting a duplicate analysis.
      - Client disconnect (CSSE cancellation or navigation) does not cancel
        the analysis — it continues in a thread pool thread and persists
        results via conversation_manager.
      - Frontend can check GET /agent/chat/job/{session_id} for status.
    """
    from src.agent.job_manager import get_chat_job_manager

    config = get_config()
    if not config.is_agent_available():
        raise HTTPException(status_code=400, detail="Agent mode is not enabled")

    session_id = request.session_id or str(uuid.uuid4())
    loop = asyncio.get_running_loop()

    job_manager = get_chat_job_manager()
    event_queue: asyncio.Queue = asyncio.Queue()

    # Store main event loop reference for thread-safe SSE broadcasting
    job_manager.set_main_loop(loop)

    # Pass explicit skills into context for the orchestrator.
    # Direct assignment so caller-provided skills always take precedence.
    skills = request.effective_skills
    stream_ctx = dict(request.context or {})
    if "stock_code" not in stream_ctx:
        stream_ctx.update(_route_b_context_from_message(request.message))
    if skills is not None:
        stream_ctx["skills"] = skills

    # Check if there's already a running job for this session.
    # If yes, attach as observer (don't start a duplicate analysis).
    is_running = job_manager.attach_observer(session_id, event_queue)

    if not is_running:
        # No existing job — this is the primary execution request.
        # Create job and start analysis in a background thread.
        job_manager.create_job(session_id)
        job_manager.attach_observer(session_id, event_queue)

        def progress_callback(event: dict):
            # Enrich tool events with display names
            if event.get("type") in ("tool_start", "tool_done"):
                tool = event.get("tool", "")
                event["display_name"] = TOOL_DISPLAY_NAMES.get(tool, tool)
            # Broadcast to ALL observer queues via job manager
            job_manager.broadcast_event(session_id, event)

        def run_sync():
            try:
                job_manager.start_job(session_id)
                executor = _build_executor(config, skills or None)
                result = executor.chat(
                    message=request.message,
                    session_id=session_id,
                    progress_callback=progress_callback,
                    context=stream_ctx,
                )

                done_event = {
                    "type": "done",
                    "success": result.success,
                    "content": result.content,
                    "error": result.error,
                    "total_steps": result.total_steps,
                    "session_id": session_id,
                }
                job_manager.broadcast_event(session_id, done_event)

                if result.success:
                    job_manager.complete_job(session_id, step_count=result.total_steps or 0)
                else:
                    job_manager.fail_job(session_id, result.error or "Unknown error")
            except Exception as exc:
                logger.error(f"Agent stream error: {exc}")
                job_manager.broadcast_event(session_id, {"type": "error", "message": str(exc)})
                job_manager.fail_job(session_id, str(exc)[:200])

        # Run analysis in a thread pool — survives client disconnect
        loop.run_in_executor(None, run_sync)

    async def event_generator():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=300.0)
                except asyncio.TimeoutError:
                    yield "data: " + json.dumps({"type": "error", "message": "分析超時"}, ensure_ascii=False) + "\n\n"
                    break
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
                if event.get("type") in ("done", "error"):
                    break
        except asyncio.CancelledError:
            # Client disconnected — clean up observer only.
            # The analysis job continues in its thread and persists to DB.
            logger.debug("SSE observer disconnected (session=%s)", session_id)
            raise
        finally:
            job_manager.detach_observer(session_id, event_queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get(
    "/chat/job/{session_id}",
    response_model=dict,
    responses={
        200: {"description": "Job status"},
        404: {"description": "No job found for this session"},
    },
    summary="查詢對話分析 Job 狀態",
    description="根據 session_id 查詢當前或最近的分析 job 狀態。可用於前端斷線重連後判斷分析是否仍在執行。",
)
async def get_chat_job_status(session_id: str):
    """
    查詢對話分析 Job 狀態。

    Frontend 在 session 切換後返回時呼叫此端點：
    - QUEUED/RUNNING: 分析仍在執行，可以重新連線 SSE stream
    - COMPLETED: 分析已完成，結果已持久化到 DB
    - FAILED: 分析失敗
    - 404: 沒有任何 job 記錄（可能是新 session 或過期已清理）
    """
    from src.agent.job_manager import get_chat_job_manager

    job_info = get_chat_job_manager().get_job_info(session_id)
    if job_info is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "not_found",
                "message": f"Session {session_id} 沒有執行中的分析 job",
            },
        )
    return job_info.to_dict()
