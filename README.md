# AstrBot PrometheusAlert 插件

接收 [PrometheusAlert](https://github.com/feiyu563/PrometheusAlert) 通过 Webhook 发出的告警文本，再使用 AstrBot 的统一消息接口推送到指定会话。

支持 QQ 官方机器人（WebSocket 和 Webhook 适配器）、OneBot v11（`aiocqhttp`）及 KOOK 的群聊和私聊。PrometheusAlert 仍负责接收原始告警、模板渲染和告警路由，本插件不修改其源码。

## 配置 AstrBot

1. 将本插件目录放到 `data/plugins/astrbot_plugin_prometheusalert`，在 AstrBot WebUI 重载插件。
2. 在插件配置中设置访问令牌，并在“告警接收会话”中选择目标会话。目标机器人需要先与目标群或用户产生过会话，才能出现在会话选择器中。
3. 默认监听 `0.0.0.0:8089`。修改监听地址或端口后需重载插件。
4. Docker 部署时，需在 AstrBot 服务的 `ports` 中映射相同端口，例如 `"8089:8089"`，然后重建 AstrBot 容器。不要占用 OneBot v11 默认使用的 `6199` 端口。

健康检查地址为 `http://AstrBot地址:8089/prometheusalert/health`，无需令牌。

## 配置 PrometheusAlert

在 PrometheusAlert Dashboard 新建自定义模板：

- 模板名称：例如 `astrbot-prometheus`。
- 模板类型：`WebHook`。
- 模板用途：按告警来源选择，例如 `Prometheus`。
- Webhook Content-Type：`text/plain`。

Prometheus 告警模板示例：

```gotemplate
{{ range .alerts }}[{{ .status }}] {{ .labels.alertname }}
实例：{{ .labels.instance }}
详情：{{ .annotations.description }}
开始时间：{{ .startsAt }}
结束时间：{{ .endsAt }}
{{ end }}
```

将 PrometheusAlert 的 WebHook 地址设置为：

```text
http://AstrBot地址:8089/prometheusalert?token=你的访问令牌
```

然后在 Alertmanager 或其他告警来源中调用 PrometheusAlert 的自定义模板接口。例如：

```text
http://PrometheusAlert地址:8080/prometheusalert?type=webhook&tpl=astrbot-prometheus&webhookContentType=text/plain&webhookurl=http%3A%2F%2FAstrBot%E5%9C%B0%E5%9D%80%3A8089%2Fprometheusalert%3Ftoken%3D%E4%BD%A0%E7%9A%84%E8%AE%BF%E9%97%AE%E4%BB%A4%E7%89%8C
```

其中 `webhookurl` 是经过 URL 编码的插件地址；也可以在模板中预设 WebHook 地址以省略此参数。若 PrometheusAlert 运行在另一容器，`AstrBot地址` 不能写成 `127.0.0.1`，应使用 AstrBot 容器名或宿主机地址。

插件也接受 `application/json` 请求，格式为 `{"message":"告警文本"}`；纯文本模式无需处理 JSON 转义，推荐使用。

## 限制

- QQ 官方机器人的主动消息受腾讯接口权限、频控和额度限制；AstrBot 重启后，请先让目标群或用户给机器人发送一条消息，以刷新发送所需的会话缓存。插件调用失败时会返回失败数量并记录 AstrBot 日志。
- 请仅向可信网络开放监听端口，并妥善保管令牌。HTTP 会明文传输令牌；跨不可信网络部署时应由反向代理提供 HTTPS。
