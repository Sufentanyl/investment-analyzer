import os
import re
import json
import logging
from typing import Optional, Dict, Any, List
import aiohttp
import requests

logger = logging.getLogger(__name__)


def _clean_markdown_for_plain_push(text: str) -> str:
    """
    将 Telegram Markdown 文本清理为适合 iOS Bark 锁屏/横幅阅读的整洁纯文本（保留 Emoji 与换行分段）
    """
    if not text:
        return ""
    cleaned = text
    # 将 [文字](链接) 转为 文字 (链接)
    cleaned = re.sub(r"\[([^\]]+)\]\((https?://[^\)]+)\)", r"\1 (\2)", cleaned)
    # 去掉粗体/斜体/代码块符号
    cleaned = cleaned.replace("**", "").replace("__", "").replace("`", "")
    # 合并过多空行
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _extract_title_and_body(text: str, default_title: str = "📡 A股量化哨兵") -> tuple[str, str, Optional[str]]:
    """
    智能从消息体首行提取推送标题、正文以及首个新闻链接（用于 Bark 点击跳转）
    """
    if not text:
        return default_title, "", None

    # 提取文本中的第一个 URL（方便 Bark 点击通知直接打开原文或控制台）
    url_match = re.search(r"(https?://[^\s\)\]>]+)", text)
    first_url = url_match.group(1) if url_match else None

    cleaned = _clean_markdown_for_plain_push(text)
    lines = [line.strip() for line in cleaned.split("\n") if line.strip()]
    if not lines:
        return default_title, cleaned, first_url

    first_line = lines[0]
    # 如果第一行足够短，作为标题，其余作为正文
    if len(first_line) <= 45 and len(lines) > 1:
        title = first_line
        body = "\n".join(lines[1:]).strip()
        # 去掉开头的分割线
        body = re.sub(r"^[━─—\-=_]{3,}\s*\n?", "", body).strip()
        return title, body, first_url

    return default_title, cleaned, first_url


class UnifiedNotifier:
    """
    统一多通道消息推送器 (v2.1)
    - 主力通道: Bark (iOS 原生推送，支持分组、时效性穿透、铃声、角标、点击跳转)
    - 扩展通道: Discord Webhook / 飞书 / 企业微信 / 钉钉 / Slack / 自定义 JSON Webhook
    - 兼容通道: Telegram Bot (可选，未配置时自动跳过)
    支持从环境变量 (.env) 或 /app/data/user_config.json (Web 控制台) 动态读取配置！
    """

    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            if os.path.exists("/app/data") or os.access("/app", os.W_OK):
                config_path = "/app/data/user_config.json"
            else:
                config_path = os.path.join(os.getcwd(), "data", "user_config.json")
        self.config_path = config_path

    def _load_notify_config(self) -> Dict[str, Any]:
        """合并读取环境变量与 user_config.json 中的 notify_config（Web 控制台配置优先）"""
        file_cfg: Dict[str, Any] = {}
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    file_cfg = data.get("notify_config") or {}
        except Exception as e:
            logger.debug(f"读取 user_config.json 推送配置失败: {e}")

        bark_url = (
            file_cfg.get("bark_url")
            or os.getenv("BARK_URL", "")
            or os.getenv("BARK_KEY", "")
        ).strip()

        return {
            "bark_enabled": file_cfg.get("bark_enabled", True),
            "bark_url": bark_url,
            "bark_group": (file_cfg.get("bark_group") or os.getenv("BARK_GROUP", "A股量化哨兵")).strip(),
            "bark_sound": (file_cfg.get("bark_sound") or os.getenv("BARK_SOUND", "glass")).strip(),
            "bark_level": (file_cfg.get("bark_level") or os.getenv("BARK_LEVEL", "timeSensitive")).strip(),
            "dashboard_url": (file_cfg.get("dashboard_url") or os.getenv("DASHBOARD_URL", "")).strip(),
            "webhook_url": (file_cfg.get("webhook_url") or os.getenv("WEBHOOK_URL", "") or os.getenv("DISCORD_WEBHOOK_URL", "")).strip(),
            "telegram_enabled": file_cfg.get("telegram_enabled", bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))),
            "telegram_token": (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip(),
            "telegram_chat_id": (os.getenv("TELEGRAM_CHAT_ID") or "").strip(),
        }

    def save_notify_config(self, new_notify_cfg: Dict[str, Any]) -> bool:
        """保存推送配置到 user_config.json（供 Web Dashboard 调用）"""
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            data = {}
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            current = data.get("notify_config") or {}
            current.update(new_notify_cfg)
            data["notify_config"] = current
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"保存推送配置失败: {e}")
            return False

    def get_status_summary(self) -> Dict[str, Any]:
        """返回各推送通道状态摘要"""
        cfg = self._load_notify_config()
        bark_ok = bool(cfg["bark_enabled"] and cfg["bark_url"])
        webhook_ok = bool(cfg["webhook_url"])
        tg_ok = bool(
            cfg["telegram_enabled"]
            and cfg["telegram_token"]
            and cfg["telegram_token"] != "your_telegram_bot_token_here"
            and cfg["telegram_chat_id"]
        )
        active_channels = []
        if bark_ok:
            active_channels.append("Bark (iOS)")
        if webhook_ok:
            active_channels.append("Webhook")
        if tg_ok:
            active_channels.append("Telegram")
        return {
            "bark_configured": bark_ok,
            "webhook_configured": webhook_ok,
            "telegram_configured": tg_ok,
            "active_channels": active_channels,
            "config": cfg,
        }

    def _resolve_bark_endpoint_and_key(self, raw_bark: str) -> tuple[str, Optional[str]]:
        """
        解析用户填写的 Bark 地址或 Key：
        - 若填写 'https://api.day.app/AbCdEfG/' -> ('https://api.day.app/push', 'AbCdEfG')
        - 若填写 'https://bark.myserver.com/AbCdEfG' -> ('https://bark.myserver.com/push', 'AbCdEfG')
        - 若仅填写 'AbCdEfG' (Device Key) -> ('https://api.day.app/push', 'AbCdEfG')
        """
        raw = raw_bark.strip().rstrip("/")
        if not raw:
            return "", None

        if raw.startswith(("http://", "https://")):
            # 去掉可能附带的查询参数
            base_part = raw.split("?")[0].rstrip("/")
            parts = base_part.split("/")
            # 形如 https://api.day.app/KEY 或 https://api.day.app/KEY/标题
            if len(parts) >= 4:
                server_root = "/".join(parts[:3])
                device_key = parts[3]
                if device_key == "push":
                    return f"{server_root}/push", None
                return f"{server_root}/push", device_key
            return f"{base_part}/push", None
        else:
            return "https://api.day.app/push", raw

    async def send(
        self,
        text: str,
        title: Optional[str] = None,
        subtitle: Optional[str] = None,
        level: Optional[str] = None,
        group: Optional[str] = None,
        click_url: Optional[str] = None,
    ) -> bool:
        """
        异步发送通知到所有已启用的通道（Bark / Webhook / Telegram）
        """
        if not text:
            return False

        cfg = self._load_notify_config()
        auto_title, clean_body, extracted_url = _extract_title_and_body(text)
        final_title = title or auto_title
        final_url = click_url or cfg.get("dashboard_url") or extracted_url

        results = []

        # 1. Bark (iOS) 推送
        if cfg["bark_enabled"] and cfg["bark_url"]:
            ok = await self._send_bark(
                cfg=cfg,
                title=final_title,
                subtitle=subtitle,
                body=clean_body,
                level=level,
                group=group,
                click_url=final_url,
            )
            results.append(ok)

        # 2. 通用 / Discord / 飞书 / 企微 / 钉钉 Webhook
        if cfg["webhook_url"]:
            ok = await self._send_webhook(
                webhook_url=cfg["webhook_url"],
                title=final_title,
                body=clean_body,
                raw_markdown=text,
            )
            results.append(ok)

        # 3. 兼容可选 Telegram
        if (
            cfg["telegram_enabled"]
            and cfg["telegram_token"]
            and cfg["telegram_token"] != "your_telegram_bot_token_here"
            and cfg["telegram_chat_id"]
        ):
            ok = await self._send_telegram(
                token=cfg["telegram_token"],
                chat_id=cfg["telegram_chat_id"],
                text=text,
            )
            results.append(ok)

        return any(results) if results else False

    def send_sync(
        self,
        text: str,
        title: Optional[str] = None,
        subtitle: Optional[str] = None,
        level: Optional[str] = None,
        group: Optional[str] = None,
        click_url: Optional[str] = None,
    ) -> bool:
        """同步发送接口（供崩溃告警或同步脚本使用）"""
        cfg = self._load_notify_config()
        auto_title, clean_body, extracted_url = _extract_title_and_body(text)
        final_title = title or auto_title
        final_url = click_url or cfg.get("dashboard_url") or extracted_url
        ok_any = False

        if cfg["bark_enabled"] and cfg["bark_url"]:
            endpoint, device_key = self._resolve_bark_endpoint_and_key(cfg["bark_url"])
            if endpoint and device_key:
                payload: Dict[str, Any] = {
                    "device_key": device_key,
                    "title": final_title,
                    "body": clean_body[:3500],
                    "group": group or cfg["bark_group"] or "A股量化哨兵",
                    "sound": cfg["bark_sound"] or "glass",
                    "level": level or cfg["bark_level"] or "timeSensitive",
                }
                if subtitle:
                    payload["subtitle"] = subtitle
                if final_url:
                    payload["url"] = final_url
                try:
                    resp = requests.post(endpoint, json=payload, timeout=10)
                    if resp.status_code == 200:
                        ok_any = True
                except Exception as e:
                    logger.warning(f"Bark 同步推送失败: {e}")

        if cfg["webhook_url"]:
            try:
                payload = self._build_webhook_payload(cfg["webhook_url"], final_title, clean_body, text)
                resp = requests.post(cfg["webhook_url"], json=payload, timeout=10)
                if resp.status_code < 300:
                    ok_any = True
            except Exception as e:
                logger.warning(f"Webhook 同步推送失败: {e}")

        return ok_any

    async def _send_bark(
        self,
        cfg: Dict[str, Any],
        title: str,
        subtitle: Optional[str],
        body: str,
        level: Optional[str],
        group: Optional[str],
        click_url: Optional[str],
    ) -> bool:
        """发送 iOS Bark 推送（使用 POST JSON 接口，支持长文本与完整元数据）"""
        endpoint, device_key = self._resolve_bark_endpoint_and_key(cfg["bark_url"])
        if not endpoint:
            return False

        # 根据内容自动强化告警级别与铃声
        resolved_level = level or cfg.get("bark_level") or "timeSensitive"
        resolved_sound = cfg.get("bark_sound") or "glass"
        if "🚨" in title or "强烈" in title or "🔥[持仓]" in body:
            resolved_level = "timeSensitive"

        payload: Dict[str, Any] = {
            "title": title[:100],
            "body": body[:3500] if body else title,
            "group": group or cfg.get("bark_group") or "A股量化哨兵",
            "sound": resolved_sound,
            "level": resolved_level,
            "isArchive": 1,
        }
        if device_key:
            payload["device_key"] = device_key
        if subtitle:
            payload["subtitle"] = subtitle[:80]
        if click_url:
            payload["url"] = click_url

        try:
            timeout = aiohttp.ClientTimeout(total=12)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(endpoint, json=payload) as resp:
                    if resp.status == 200:
                        logger.info(f"📲 Bark 推送成功: {title[:30]}")
                        return True
                    else:
                        err_text = await resp.text()
                        logger.warning(f"⚠️ Bark 推送返回 HTTP {resp.status}: {err_text[:150]}")
                        # 回退尝试 GET/POST 路径式调用
                        if device_key:
                            fallback_url = endpoint.replace("/push", f"/{device_key}")
                            async with session.post(fallback_url, json=payload) as resp2:
                                return resp2.status == 200
        except Exception as e:
            logger.error(f"❌ Bark 推送异常: {e}")
        return False

    def _build_webhook_payload(self, url: str, title: str, clean_body: str, raw_markdown: str) -> Dict[str, Any]:
        """根据 Webhook URL 域名自动适配 Discord / 飞书 / 企业微信 / 钉钉 / Slack / 通用 JSON"""
        u_lower = url.lower()
        full_text = f"**{title}**\n\n{raw_markdown}" if title not in raw_markdown else raw_markdown

        if "discord.com/api/webhooks" in u_lower or "discordapp.com/api/webhooks" in u_lower:
            color = 0x10B981 if ("利好" in title or "🟢" in title or "🔥" in title) else (
                0xEF4444 if ("利空" in title or "🔴" in title or "🔻" in title) else 0x2563EB
            )
            return {
                "username": "A股量化哨兵",
                "embeds": [
                    {
                        "title": title[:250],
                        "description": raw_markdown[:4000],
                        "color": color,
                    }
                ],
            }
        elif "open.feishu.cn" in u_lower or "open.larksuite.com" in u_lower:
            return {
                "msg_type": "text",
                "content": {"text": f"{title}\n\n{clean_body}"},
            }
        elif "qyapi.weixin.qq.com" in u_lower:
            return {
                "msgtype": "markdown",
                "markdown": {"content": full_text[:4000]},
            }
        elif "oapi.dingtalk.com" in u_lower:
            return {
                "msgtype": "markdown",
                "markdown": {"title": title[:60], "text": full_text[:4000]},
            }
        elif "hooks.slack.com" in u_lower:
            return {"text": f"*{title}*\n{clean_body}"}
        else:
            return {
                "title": title,
                "body": clean_body,
                "markdown": raw_markdown,
                "text": f"{title}\n\n{clean_body}",
            }

    async def _send_webhook(self, webhook_url: str, title: str, body: str, raw_markdown: str) -> bool:
        try:
            payload = self._build_webhook_payload(webhook_url, title, body, raw_markdown)
            timeout = aiohttp.ClientTimeout(total=12)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(webhook_url, json=payload) as resp:
                    if resp.status < 300:
                        logger.info(f"🌐 Webhook 推送成功: {title[:30]}")
                        return True
                    else:
                        err = await resp.text()
                        logger.warning(f"⚠️ Webhook 推送失败 ({resp.status}): {err[:150]}")
        except Exception as e:
            logger.error(f"❌ Webhook 推送异常: {e}")
        return False

    async def _send_telegram(self, token: str, chat_id: str, text: str) -> bool:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text[:4000],
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }
        try:
            timeout = aiohttp.ClientTimeout(total=12)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        return True
                    # 如果 Markdown 解析失败，回退为纯文本发送
                    payload.pop("parse_mode", None)
                    async with session.post(url, json=payload) as resp2:
                        return resp2.status == 200
        except Exception as e:
            logger.debug(f"Telegram 推送失败: {e}")
        return False
