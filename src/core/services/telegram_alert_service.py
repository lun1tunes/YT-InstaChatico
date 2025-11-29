"""Telegram Notification Service for Instagram comment alerts."""

import html
import logging
from typing import Any, Callable, Dict

import aiohttp

from ..config import settings

logger = logging.getLogger(__name__)


class TelegramAlertService:
    """Send alert notifications to Telegram for urgent/critical feedback."""

    def __init__(
        self,
        bot_token: str = None,
        chat_id: str = None,
        alert_type: str = "instagram_comment_alerts",
    ):
        self.bot_token = bot_token or settings.telegram.bot_token
        self.chat_id = chat_id or settings.telegram.chat_id
        if alert_type == "instagram_comment_alerts":
            self.thread_id = settings.telegram.tg_chat_alerts_thread_id
        elif alert_type == "app_logs":
            self.thread_id = settings.telegram.tg_chat_logs_thread_id
        else:
            self.thread_id = None
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    @staticmethod
    def _escape_html(text: str) -> str:
        """Escape HTML special characters for Telegram."""
        return html.escape(text or "", quote=True)

    async def _send_comment_notification(
        self,
        comment_data: Dict[str, Any],
        *,
        formatter: Callable[[Dict[str, Any]], str],
        notification_label: str,
    ) -> Dict[str, Any]:
        """Shared notification sender with consistent logging and error handling."""

        try:
            if not self.bot_token or not self.chat_id:
                logger.error("Telegram bot token or chat ID not configured")
                return {"success": False, "error": "Telegram configuration missing"}

            message = formatter(comment_data)
            response = await self._send_message(message)

            if response.get("ok"):
                logger.info(
                    f"{notification_label} notification sent successfully for comment {comment_data.get('comment_id', 'unknown')}"
                )
                return {
                    "success": True,
                    "message_id": response.get("result", {}).get("message_id"),
                    "response": response,
                }

            logger.error(f"Failed to send Telegram notification: {response}")
            return {
                "success": False,
                "error": response.get("description", "Unknown error"),
                "response": response,
            }

        except Exception as e:
            logger.exception("Error sending Telegram notification")
            return {"success": False, "error": str(e)}

    async def send_urgent_issue_notification(self, comment_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send urgent issue notification to Telegram."""
        return await self._send_comment_notification(
            comment_data,
            formatter=self._format_urgent_message,
            notification_label="Urgent issue",
        )

    async def send_critical_feedback_notification(self, comment_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send critical feedback notification to Telegram."""
        return await self._send_comment_notification(
            comment_data,
            formatter=self._format_critical_message,
            notification_label="Critical feedback",
        )

    def _prepare_message_data(self, comment_data: Dict[str, Any]) -> Dict[str, str]:
        """Extract and escape comment data for Telegram message."""
        data = {
            'comment_id': comment_data.get("comment_id", "Unknown"),
            'comment_text': comment_data.get("comment_text", "No text available"),
            'classification': comment_data.get("classification", "Unknown"),
            'confidence': comment_data.get("confidence", 0),
            'reasoning': comment_data.get("reasoning", "No reasoning provided"),
            'media_id': comment_data.get("media_id", "Unknown"),
            'username': comment_data.get("username", "Unknown user"),
            'timestamp': comment_data.get("timestamp", "Unknown time"),
        }

        # Escape HTML and truncate
        escaped = {k: self._escape_html(str(v)) for k, v in data.items()}
        if len(escaped['comment_text']) > 1000:
            escaped['comment_text'] = escaped['comment_text'][:997] + "..."
        if len(escaped['reasoning']) > 500:
            escaped['reasoning'] = escaped['reasoning'][:497] + "..."

        escaped['confidence'] = data['confidence']  # Keep original number
        return escaped

    def _format_urgent_message(self, comment_data: Dict[str, Any]) -> str:
        """Format urgent issue notification."""
        d = self._prepare_message_data(comment_data)
        return f"""🚨 <b>URGENT ISSUE DETECTED</b> 🚨

📱 <b>Instagram Comment Alert</b>

👤 <b>Instagram Username:</b> {d['username']}
⏰ <b>Time:</b> {d['timestamp']}
🆔 <b>Comment ID:</b> <code>{d['comment_id']}</code>
📸 <b>Media ID:</b> <code>{d['media_id']}</code>

💬 <b>Comment Text:</b>
<pre>{d['comment_text']}</pre>

🤖 <b>AI Analysis:</b>
• <b>Classification:</b> {d['classification']}
• <b>Confidence:</b> {d['confidence']}%

🧠 <b>AI Reasoning:</b>
{d['reasoning']}

⚠️ <b>Action Required:</b> This comment has been classified as an urgent issue or complaint that requires immediate attention.

#urgent #instagram #complaint #customer_service"""

    def _format_critical_message(self, comment_data: Dict[str, Any]) -> str:
        """Format critical feedback notification."""
        d = self._prepare_message_data(comment_data)
        return f"""⚠️ <b>CRITICAL FEEDBACK DETECTED</b> ⚠️

📱 <b>Instagram Comment Alert</b>

👤 <b>Instagram Username:</b> {d['username']}
⏰ <b>Time:</b> {d['timestamp']}
🆔 <b>Comment ID:</b> <code>{d['comment_id']}</code>
📸 <b>Media ID:</b> <code>{d['media_id']}</code>

💬 <b>Comment Text:</b>
<pre>{d['comment_text']}</pre>

🤖 <b>AI Analysis:</b>
• <b>Classification:</b> {d['classification']}
• <b>Confidence:</b> {d['confidence']}%

🧠 <b>AI Reasoning:</b>
{d['reasoning']}

📋 <b>Action Required:</b> This comment contains critical feedback that may require attention or follow-up.

#critical #instagram #feedback #customer_service"""

    def _format_partnership_message(self, comment_data: Dict[str, Any]) -> str:
        """Format partnership proposal notification."""
        d = self._prepare_message_data(comment_data)
        return f"""🤝 <b>PARTNERSHIP PROPOSAL</b> 🤝

📱 <b>Business Opportunity Alert</b>

👤 <b>Instagram Username:</b> {d['username']}
⏰ <b>Time:</b> {d['timestamp']}
🆔 <b>Comment ID:</b> <code>{d['comment_id']}</code>
📸 <b>Media ID:</b> <code>{d['media_id']}</code>

💬 <b>Proposal Text:</b>
<pre>{d['comment_text']}</pre>

🤖 <b>AI Classification Analysis:</b>
📊 <b>Classification:</b> {d['classification']}
🎯 <b>Confidence:</b> {d['confidence']}%

💭 <b>AI Reasoning:</b>
<i>{d['reasoning']}</i>

✅ <b>Action Required:</b> This comment contains a potential business partnership or collaboration proposal. Consider reviewing and responding to this opportunity.

#partnership #business #collaboration #opportunity"""

    def _format_toxic_message(self, comment_data: Dict[str, Any]) -> str:
        """Format toxic/abusive content notification."""
        d = self._prepare_message_data(comment_data)
        return f"""🚫 <b>TOXIC / ABUSIVE CONTENT</b> 🚫

📱 <b>Moderation Alert</b>

👤 <b>Instagram Username:</b> {d['username']}
⏰ <b>Time:</b> {d['timestamp']}
🆔 <b>Comment ID:</b> <code>{d['comment_id']}</code>
📸 <b>Media ID:</b> <code>{d['media_id']}</code>

💬 <b>Comment Text:</b>
<pre>{d['comment_text']}</pre>

🤖 <b>AI Classification Analysis:</b>
📊 <b>Classification:</b> {d['classification']}
🎯 <b>Confidence:</b> {d['confidence']}%

💭 <b>AI Reasoning:</b>
<i>{d['reasoning']}</i>

⛔ <b>Action Required:</b> This comment violates Instagram community guidelines and contains toxic/abusive content. Consider hiding, deleting, or reporting this comment for moderation.

#toxic #abusive #moderation #violation #instagram"""

    async def send_partnership_proposal_notification(self, comment_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send partnership proposal notification to Telegram."""
        return await self._send_comment_notification(
            comment_data,
            formatter=self._format_partnership_message,
            notification_label="Partnership proposal",
        )

    async def send_toxic_abusive_notification(self, comment_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send toxic/abusive comment notification to Telegram."""
        return await self._send_comment_notification(
            comment_data,
            formatter=self._format_toxic_message,
            notification_label="Toxic/abusive",
        )

    async def send_notification(self, comment_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send appropriate notification based on comment classification

        Args:
            comment_data: Dictionary containing comment information

        Returns:
            Dictionary with success status and response details
        """
        classification = comment_data.get("classification", "").lower()

        if classification == "urgent issue / complaint":
            return await self.send_urgent_issue_notification(comment_data)
        elif classification == "critical feedback":
            return await self.send_critical_feedback_notification(comment_data)
        elif classification == "partnership proposal":
            return await self.send_partnership_proposal_notification(comment_data)
        elif classification == "toxic / abusive":
            return await self.send_toxic_abusive_notification(comment_data)
        else:
            logger.warning(f"No notification needed for classification: {classification}")
            return {
                "success": False,
                "error": f"No notification configured for classification: {classification}",
            }

    async def send_log_alert(self, log_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send app log alerts to Telegram with HTML formatting."""
        try:
            if not self.bot_token or not self.chat_id:
                return {"success": False, "error": "Telegram configuration missing"}

            emoji_map = {"WARNING": "⚠️", "ERROR": "🔴", "CRITICAL": "🚨"}
            level = str(log_data.get("level", "WARNING"))
            emoji = emoji_map.get(level, "ℹ️")

            # Escape and truncate
            safe_msg = self._escape_html(str(log_data.get("message", "")))[:3500]
            safe_exception = self._escape_html(log_data.get("exception", ""))[:3500] if log_data.get("exception") else ""

            text_parts = [
                f"{emoji} <b>APP LOG ALERT</b>",
                f"<b>Level:</b> {self._escape_html(level)}",
                f"<b>Logger:</b> {self._escape_html(str(log_data.get('logger', '-')))}",
                f"<b>Trace:</b> <code>{self._escape_html(str(log_data.get('trace_id', '-')))}</code>",
                f"<b>Time:</b> {self._escape_html(str(log_data.get('timestamp', '')))}",
                "",
                f"<b>Message:</b>",
                f"<pre>{safe_msg}</pre>",
            ]

            if safe_exception:
                text_parts.extend(["", f"<b>Details:</b>", f"<pre>{safe_exception}</pre>"])

            text = "\n".join(text_parts)

            # Truncate if too long
            if len(text) > 3900:
                safe_msg = safe_msg[:2000] + "..."
                text_parts[7] = f"<pre>{safe_msg}</pre>"
                if safe_exception:
                    safe_exception = safe_exception[:1500] + "..."
                    text_parts[-1] = f"<pre>{safe_exception}</pre>"
                text = "\n".join(text_parts)

            return await self._send_message(text, parse_mode="HTML")
        except Exception as e:
            logger.exception("Error sending log alert to Telegram")
            return {"success": False, "error": str(e)}

    async def _send_message(self, message: str, parse_mode: str | None = "HTML") -> Dict[str, Any]:
        """Send message to Telegram chat using aiohttp"""

        url = f"{self.base_url}/sendMessage"

        payload = {
            "chat_id": self.chat_id,
            "message_thread_id": self.thread_id,
            "text": message,
            "disable_web_page_preview": True,
        }

        if parse_mode:
            payload["parse_mode"] = parse_mode

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        logger.error(f"Telegram API error {response.status}: {error_text}")
                        return {
                            "ok": False,
                            "description": f"HTTP {response.status}: {error_text}",
                        }
        except aiohttp.ClientError as e:
            logger.error(f"aiohttp request failed: {e}")
            return {"ok": False, "description": str(e)}
        except Exception as e:
            logger.exception("Unexpected error during Telegram API request")
            return {"ok": False, "description": str(e)}

    async def test_connection(self) -> Dict[str, Any]:
        """Test Telegram bot connection using aiohttp"""
        try:
            if not self.bot_token or not self.chat_id:
                return {
                    "success": False,
                    "error": "Bot token or chat ID not configured",
                }

            url = f"{self.base_url}/getMe"

            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        bot_info = await response.json()
                        if bot_info.get("ok"):
                            return {
                                "success": True,
                                "bot_info": bot_info.get("result", {}),
                                "chat_id": self.chat_id,
                            }
                        else:
                            return {
                                "success": False,
                                "error": bot_info.get("description", "Unknown error"),
                            }
                    else:
                        error_text = await response.text()
                        return {
                            "success": False,
                            "error": f"HTTP {response.status}: {error_text}",
                        }

        except Exception as e:
            logger.exception("Error testing Telegram connection")
            return {"success": False, "error": str(e)}


# Convenience function to get a pre-configured service
def get_telegram_service() -> TelegramAlertService:
    """Get a pre-configured Telegram alert service using default settings"""
    return TelegramAlertService()
