# -*- coding: utf-8 -*-
"""
飛書 傳送提醒服務

職責：
1. 透過 webhook 傳送飛書訊息
"""
import base64
import hashlib
import hmac
import logging
import time
from typing import Any, Dict, Optional

import requests

from src.config import Config
from src.formatters import (
    MIN_MAX_BYTES,
    PAGE_MARKER_SAFE_BYTES,
    chunk_content_by_max_bytes,
    format_feishu_markdown,
)


logger = logging.getLogger(__name__)


class FeishuSender:

    def __init__(self, config: Config):
        """
        初始化飛書配置

        Args:
            config: 配置物件
        """
        self._feishu_url = getattr(config, 'feishu_webhook_url', None)
        self._feishu_secret = (getattr(config, 'feishu_webhook_secret', None) or '').strip()
        self._feishu_keyword = (getattr(config, 'feishu_webhook_keyword', None) or '').strip()
        self._feishu_max_bytes = getattr(config, 'feishu_max_bytes', 20000)
        self._webhook_verify_ssl = getattr(config, 'webhook_verify_ssl', True)

    def _get_keyword_prefix(self) -> str:
        """Return the keyword prefix required by Feishu webhook security settings."""
        if not self._feishu_keyword:
            return ""
        return f"{self._feishu_keyword}\n"

    def _apply_keyword_prefix(self, content: str) -> str:
        """Prepend the optional keyword so each webhook request passes keyword checks."""
        prefix = self._get_keyword_prefix()
        if not prefix:
            return content
        return f"{prefix}{content}" if content else self._feishu_keyword

    def _build_security_fields(self) -> Dict[str, str]:
        """Build optional signing fields required by Feishu custom robot security."""
        if not self._feishu_secret:
            return {}

        timestamp = str(int(time.time()))
        string_to_sign = f"{timestamp}\n{self._feishu_secret}"
        sign = base64.b64encode(
            hmac.new(
                string_to_sign.encode('utf-8'),
                digestmod=hashlib.sha256,
            ).digest()
        ).decode('utf-8')
        return {
            "timestamp": timestamp,
            "sign": sign,
        }


    def send_to_feishu(self, content: str, *, timeout_seconds: Optional[float] = None) -> bool:
        """
        推送訊息到飛書機器人

        飛書自定義機器人 Webhook 訊息格式：
        {
            "msg_type": "interactive",
            "card": {
                "config": { "wide_screen_mode": true },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": "..."
                        }
                    }
                ],
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": "A股智慧分析報告"
                    }
                }
            }
        }

        說明：飛書文字訊息不會渲染 Markdown，需使用互動卡片（lark_md）格式

        注意：飛書文字訊息限制約 20KB，超長內容會自動分批傳送
        可透過環境變數 FEISHU_MAX_BYTES 調整限制值

        Args:
            content: 訊息內容（Markdown 會轉為純文字）

        Returns:
            是否傳送成功
        """
        if not self._feishu_url:
            logger.warning("飛書 Webhook 未配置，跳過推送")
            return False

        # 飛書 lark_md 支援有限，先做格式轉換
        formatted_content = format_feishu_markdown(content)

        max_bytes = self._feishu_max_bytes  # 從配置讀取，預設 20000 位元組
        keyword_overhead = len(self._get_keyword_prefix().encode('utf-8'))
        effective_max_bytes = max_bytes - keyword_overhead

        if effective_max_bytes <= 0:
            logger.error("飛書關鍵詞過長，超過單條訊息允許的最大位元組數，無法傳送")
            return False

        # 檢查位元組長度，超長則分批傳送
        content_bytes = len(formatted_content.encode('utf-8')) + keyword_overhead
        if content_bytes > max_bytes:
            min_chunk_bytes = MIN_MAX_BYTES + PAGE_MARKER_SAFE_BYTES
            if effective_max_bytes < min_chunk_bytes:
                logger.error(
                    "飛書關鍵詞過長，剩餘分片預算(%s位元組)不足以安全分頁傳送，至少需要 %s 位元組",
                    effective_max_bytes,
                    min_chunk_bytes,
                )
                return False
            logger.info(f"飛書訊息內容超長({content_bytes}位元組/{len(content)}字元)，將分批傳送")
            return self._send_feishu_chunked(formatted_content, effective_max_bytes)

        try:
            return self._send_feishu_message(formatted_content, timeout_seconds=timeout_seconds)
        except Exception as e:
            logger.error(f"傳送飛書訊息失敗: {e}")
            return False

    def _send_feishu_chunked(self, content: str, max_bytes: int) -> bool:
        """
        分批傳送長訊息到飛書

        按股票分析塊（以 --- 或 ### 分隔）智慧分割，確保每批不超過限制

        Args:
            content: 完整訊息內容
            max_bytes: 單條訊息最大位元組數

        Returns:
            是否全部傳送成功
        """
        try:
            chunks = chunk_content_by_max_bytes(content, max_bytes, add_page_marker=True)
        except ValueError as e:
            logger.error("飛書訊息分片失敗，單片預算不足以安全分頁（關鍵詞過長或 max_bytes 過小）: %s", e)
            return False

        # 分批傳送
        total_chunks = len(chunks)
        success_count = 0

        logger.info(f"飛書分批傳送：共 {total_chunks} 批")

        for i, chunk in enumerate(chunks):
            try:
                if self._send_feishu_message(chunk):
                    success_count += 1
                    logger.info(f"飛書第 {i+1}/{total_chunks} 批傳送成功")
                else:
                    logger.error(f"飛書第 {i+1}/{total_chunks} 批傳送失敗")
            except Exception as e:
                logger.error(f"飛書第 {i+1}/{total_chunks} 批傳送異常: {e}")

            # 批次間隔，避免觸發頻率限制
            if i < total_chunks - 1:
                time.sleep(1)

        return success_count == total_chunks

    def _send_feishu_message(self, content: str, *, timeout_seconds: Optional[float] = None) -> bool:
        """傳送單條飛書訊息（優先使用 Markdown 卡片）"""
        prepared_content = self._apply_keyword_prefix(content)
        security_fields = self._build_security_fields()

        def _post_payload(payload: Dict[str, Any]) -> bool:
            request_payload = dict(payload)
            request_payload.update(security_fields)
            logger.debug(f"飛書請求 URL: {self._feishu_url}")
            logger.debug(f"飛書請求 payload 長度: {len(prepared_content)} 字元")

            response = requests.post(
                self._feishu_url,
                json=request_payload,
                timeout=timeout_seconds or 30,
                verify=self._webhook_verify_ssl
            )

            logger.debug(f"飛書響應狀態碼: {response.status_code}")
            logger.debug(f"飛書響應內容: {response.text}")

            if response.status_code == 200:
                result = response.json()
                code = result.get('code') if 'code' in result else result.get('StatusCode')
                if code == 0:
                    logger.info("飛書訊息傳送成功")
                    return True
                else:
                    error_msg = result.get('msg') or result.get('StatusMessage', '未知錯誤')
                    error_code = result.get('code') or result.get('StatusCode', 'N/A')
                    logger.error(f"飛書返回錯誤 [code={error_code}]: {error_msg}")
                    logger.error(f"完整響應: {result}")
                    return False
            else:
                logger.error(f"飛書請求失敗: HTTP {response.status_code}")
                logger.error(f"響應內容: {response.text}")
                return False

        # 1) 優先使用互動卡片（支援 Markdown 渲染）
        card_payload = {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": "股票智慧分析報告"
                    }
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": prepared_content
                        }
                    }
                ]
            }
        }

        if _post_payload(card_payload):
            return True

        # 2) 回退為普通文字訊息
        text_payload = {
            "msg_type": "text",
            "content": {
                "text": prepared_content
            }
        }

        return _post_payload(text_payload)
