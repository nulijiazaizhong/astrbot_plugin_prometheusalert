import asyncio
import hmac
import json

from aiohttp import web
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import MessageChain
from astrbot.api.star import Context, Star


class PrometheusAlertPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None

    async def initialize(self):
        app = web.Application(client_max_size=1024 * 1024)
        app.add_routes(
            [
                web.get("/prometheusalert/health", self._health),
                web.post("/prometheusalert", self._receive_alert),
            ]
        )
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        port = int(self.config.get("port", 8089))
        if not 1 <= port <= 65535:
            raise ValueError("PrometheusAlert 插件端口必须在 1-65535 之间")
        self._site = web.TCPSite(
            self._runner,
            host=str(self.config.get("host", "0.0.0.0")),
            port=port,
        )
        await self._site.start()
        logger.info(f"PrometheusAlert Webhook 已监听端口 {port}")
        if not self.config.get("token"):
            logger.warning("PrometheusAlert 插件尚未配置访问令牌，Webhook 暂不可用")

    async def _health(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    async def _receive_alert(self, request: web.Request) -> web.Response:
        expected = str(self.config.get("token", ""))
        if not expected:
            return web.json_response(
                {"success": False, "message": "插件尚未配置访问令牌"}, status=503
            )
        provided = request.query.get("token", "")
        if not hmac.compare_digest(provided.encode(), expected.encode()):
            return web.json_response(
                {"success": False, "message": "访问令牌无效"}, status=401
            )

        try:
            if request.content_type == "application/json":
                payload = await request.json()
                if not isinstance(payload, dict) or not isinstance(
                    payload.get("message"), str
                ):
                    raise ValueError
                message = payload["message"].strip()
            elif request.content_type == "text/plain":
                message = (await request.text()).strip()
            else:
                return web.json_response(
                    {
                        "success": False,
                        "message": "仅支持 text/plain 或 application/json",
                    },
                    status=415,
                )
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            return web.json_response(
                {"success": False, "message": "请求体格式错误"}, status=400
            )

        if not message:
            return web.json_response(
                {"success": False, "message": "告警内容不能为空"}, status=400
            )
        targets = list(
            dict.fromkeys(
                target.strip()
                for target in self.config.get("targets", [])
                if isinstance(target, str) and target.strip()
            )
        )
        if not targets:
            return web.json_response(
                {"success": False, "message": "插件尚未配置接收会话"}, status=503
            )

        results = await asyncio.gather(
            *(self._send_alert(target, message) for target in targets)
        )
        sent = sum(results)
        failed = len(targets) - sent
        return web.json_response(
            {"success": failed == 0, "sent": sent, "failed": failed},
            status=200 if failed == 0 else 502,
        )

    async def _send_alert(self, target: str, message: str) -> bool:
        try:
            sent = await self.context.send_message(
                target, MessageChain().message(message)
            )
            if not sent:
                logger.error(f"PrometheusAlert 消息发送失败：找不到会话 {target}")
            return sent
        except Exception as exc:  # noqa: BLE001 - 单个会话失败不能阻断其他会话
            logger.error(f"PrometheusAlert 消息发送失败：{target}，{exc}")
            return False

    async def terminate(self):
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()
        self._site = None
        self._runner = None
