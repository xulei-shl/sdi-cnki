# API 使用说明 — 邮件发送服务

> 其他项目集成本邮件发送服务的接口参考文档。  
> 部署细节请参见 [`ubuntu-运维手册.md`](ubuntu-运维手册.md)。

---

## 目录

1. [快速接入](#1-快速接入)
2. [接口概览](#2-接口概览)
3. [认证方式](#3-认证方式)
4. [健康检查](#4-健康检查)
5. [发送邮件（异步 — 推荐）](#5-发送邮件异步--推荐)
6. [发送邮件（同步）](#6-发送邮件同步)
7. [请求参数说明](#7-请求参数说明)
8. [响应格式说明](#8-响应格式说明)
9. [错误处理](#9-错误处理)
10. [速率限制](#10-速率限制)
11. [调用示例](#11-调用示例)
    - [curl](#111-curl)
    - [Python (httpx)](#112-python-httpx)
    - [Python (requests)](#113-python-requests)
    - [JavaScript / Node.js](#114-javascript--nodejs)
    - [Java (OkHttp)](#115-java-okhttp)
    - [Go](#116-go)
    - [PHP (cURL)](#117-php-curl)
12. [最佳实践](#12-最佳实践)

---

## 1. 快速接入

对接只需三步：

```bash
# 1. 确认服务可用
curl http://<host>:9000/health

# 2. 发送第一封邮件（将 your-key 替换为实际 API Key）
curl -X POST http://<host>:9000/api/v1/mail/send \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "to": "user@example.com",
    "subject": "对接测试",
    "content": "邮件发送服务对接成功！"
  }'

# 3. 期待返回
# {"code":0,"message":"已提交发送","data":{"recipient":"user@example.com","subject":"对接测试"}}
```

### 前置条件

| 条件 | 说明 |
|---|---|
| 服务地址 | 部署方提供的 IP 或域名，端口默认为 `9000` |
| API Key | 部署方分配的 `X-API-Key` 鉴权字符串 |
| 网络可达 | 调用方需要能与服务端建立 TCP 连接 |

---

## 2. 接口概览

| 方法 | 路径 | 说明 | 耗时 |
|---|---|---|---|
| `GET` | `/health` | 健康检查 | 即时 |
| `POST` | `/api/v1/mail/send` | 发送邮件（**异步**） | ~10ms（请求即刻返回） |
| `POST` | `/api/v1/mail/send-sync` | 发送邮件（**同步**） | 1~5s（等待 SMTP 结果） |

> **异步优先**：日常使用请优先调用异步接口。它几乎瞬时返回，后台线程池执行真实的 SMTP 发送，不会阻塞调用方。同步接口仅适用于需要立即确认发送结果的场景（如注册验证码）。

---

## 3. 认证方式

所有邮件发送接口均需在 **HTTP 请求头** 中携带 API Key：

```http
X-API-Key: <your-api-secret-key>
```

**说明：**

- 由部署方在服务端 `.env` 文件中通过 `API_SECRET_KEY` 配置
- 请妥善保管，**不要**在客户端代码、前端页面或公开仓库中明文硬编码
- 如果 Key 泄露，请联系部署方在服务端更换并重启服务

> 注意：如果服务端未配置 `API_SECRET_KEY`（仅用于开发调试），鉴权会完全禁用。**生产环境必须设置**。

---

## 4. 健康检查

快速确认服务是否正常运行。

### 请求

```http
GET /health
```

### 响应示例

```json
{
  "status": "ok",
  "smtp_configured": true,
  "auth_configured": true,
  "rate_limit": "10次/60秒"
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| `status` | string | 服务状态，正常为 `"ok"` |
| `smtp_configured` | bool | SMTP 邮箱是否已配置 |
| `auth_configured` | bool | API 鉴权是否已开启 |
| `rate_limit` | string | 当前速率限制策略 |

### 用途

- **调用方启动时探测**：在发送邮件前先确认服务可达
- **监控系统轮询**：对接 Prometheus / 自建监控，定期检查

### curl 示例

```bash
curl -s http://localhost:9000/health | python3 -m json.tool
```

---

## 5. 发送邮件（异步 — 推荐）

请求即刻返回，后台线程池执行真实发送。适用于绝大多数场景。

### 请求

```http
POST /api/v1/mail/send
Content-Type: application/json
X-API-Key: your-key

{
  "to": "user@example.com",
  "subject": "订单通知",
  "content": "您的订单 #2024001 已发货。"
}
```

### 响应示例

```json
{
  "code": 0,
  "message": "已提交发送",
  "data": {
    "recipient": "user@example.com",
    "subject": "订单通知"
  }
}
```

### ⚠ 重要提示

- `code: 0` + `"已提交发送"` **仅表示**请求已通过校验并加入后台发送队列
- 实际发送可能因授权码过期、收件人地址错误、SMTP 超时等原因失败
- **发送结果仅在服务端日志中记录**，不会回调通知调用方
- 如需确认发送结果，请使用[同步接口](#6-发送邮件同步)或查看服务端日志

```bash
# 查看发送结果（需服务端权限）
sudo journalctl -u email-api --grep "发送成功|发送失败"
```

---

## 6. 发送邮件（同步）

等待实际的 SMTP 发送结果后再返回。适合需要确认结果的场景。

### 请求

```http
POST /api/v1/mail/send-sync
Content-Type: application/json
X-API-Key: your-key

{
  "to": "user@example.com",
  "subject": "验证码",
  "content": "您的验证码是：123456，5分钟内有效。"
}
```

### 成功响应

```json
{
  "code": 0,
  "message": "发送成功",
  "data": {
    "recipient": "user@example.com",
    "subject": "验证码"
  }
}
```

### 失败响应

```json
{
  "code": 500,
  "message": "认证失败，请检查 SMTP_USER / SMTP_PASS（授权码）: ...",
  "data": null
}
```

### 适用场景

| 推荐使用 | 不建议使用 |
|---|---|
| 注册/登录验证码 | 批量通知 |
| 密码重置邮件 | 营销邮件 |
| 重要告警通知 | 日志摘要 |
| 接收方需要确认送达 | 高并发场景 |

**超时说明**：同步接口内部默认 15 秒 SMTP 超时。如果 SMTP 服务器响应慢或网络不稳定，接口可能在 15 秒后才返回错误。

---

## 7. 请求参数说明

### 请求体

```json
{
  "to": "user@example.com",
  "subject": "邮件主题",
  "content": "邮件正文内容",
  "content_type": "plain",
  "cc": ["manager@example.com"],
  "sender_name": "客服小助手"
}
```

### 字段详解

| 参数 | 类型 | 必填 | 默认值 | 长度限制 | 说明 |
|---|---|---|---|---|---|
| `to` | string (email) | ✅ | — | — | 收件人邮箱地址 |
| `subject` | string | ✅ | — | 1~500 字符 | 邮件主题 |
| `content` | string | ✅ | — | 1~100,000 字符 | 邮件正文 |
| `content_type` | string | ❌ | `"plain"` | — | 正文格式：`"plain"`（纯文本）或 `"html"`（富文本） |
| `cc` | array[string] | ❌ | `null` | — | 抄送地址列表，每项为邮箱地址 |
| `sender_name` | string | ❌ | 服务端配置值 | — | 自定义发件人显示名称，覆盖服务端默认值 |

### content_type 说明

- **`"plain"`**：纯文本，适合简单通知、验证码等
- **`"html"`**：富文本，支持完整的 HTML 标签和样式

**HTML 邮件注意事项：**

```html
<!-- 推荐：简洁的 HTML 结构 -->
<!DOCTYPE html>
<html>
<body>
  <h2>订单通知</h2>
  <p>您的订单 <strong>#2024001</strong> 已发货。</p>
  <hr>
  <p style="color: gray; font-size: 12px;">本邮件由系统自动发送</p>
</body>
</html>
```

- 建议使用 **内联样式**（`style="..."`），部分邮件客户端不支持 `<style>` 标签
- 避免使用 JavaScript（多数邮件客户端会过滤）
- 图片请使用绝对 URL（`https://...`），并确保图片服务器允许热加载
- 控制邮件宽度在 600px 以内，兼容移动端阅读

---

## 8. 响应格式说明

### 通用响应体

所有接口使用统一的响应格式：

```json
{
  "code": 0,
  "message": "提示信息",
  "data": { }
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| `code` | int | `0` 表示操作成功；非 `0` 表示操作失败，值为 HTTP 状态码 |
| `message` | string | 成功时的提示，或失败时的错误详情 |
| `data` | object / null | 附加数据，可能包含 `recipient`、`subject` 等字段 |

**解析建议**：判断成功与否应只依赖 `code` 字段，不要依赖 `message` 的具体文本内容（`message` 可能因国际化或版本更新而变化）。

---

## 9. 错误处理

### HTTP 状态码速查

| 状态码 | 含义 | 处理建议 |
|---|---|---|
| `200` | 请求成功 | 检查 `code` 是否为 `0` |
| `400` | 请求参数错误 | 检查请求体格式、字段类型或 `content_type` 值 |
| `403` | API Key 无效 | 核对 `X-API-Key` 是否正确 |
| `429` | 请求频率超限 | 等待后重试（参见速率限制） |
| `500` | 邮件发送失败 | 检查收件人地址或联系服务方排查 SMTP 配置 |

### 常见错误详情

```json
// 400 — 参数校验失败
{
  "code": 400,
  "message": "content_type 仅支持 plain 或 html",
  "data": null
}

// 403 — 鉴权失败
{
  "code": 403,
  "message": "无效的 API Key",
  "data": null
}

// 429 — 频率限制
{
  "code": 429,
  "message": "请求过于频繁（限制: 10次/60秒）",
  "data": null
}

// 500 — 发送失败（同步接口）
{
  "code": 500,
  "message": "认证失败，请检查 SMTP_USER / SMTP_PASS（授权码）: ...",
  "data": null
}

// 500 — 收件人地址被拒绝
{
  "code": 500,
  "message": "收件人地址被拒绝: ...",
  "data": null
}

// 500 — SMTP 连接超时
{
  "code": 500,
  "message": "连接 SMTP 服务器超时（smtphz.qiye.163.com:994）",
  "data": null
}
```

### 调用方重试策略

对于可重试的错误，建议使用 **指数退避**（Exponential Backoff）：

| 错误码 | 是否重试 | 策略 |
|---|---|---|
| `400` | ❌ 不重试 | 修复请求参数 |
| `403` | ❌ 不重试 | 检查 API Key |
| `429` | ✅ 可重试 | 等待后重试，建议 5s、10s、20s 阶梯退避 |
| `500` | ✅ 可重试 | 网络或 SMTP 临时故障，建议 3 次以内重试 |

---

## 10. 速率限制

服务端使用滑动窗口算法进行限流。

### 默认限制

```
每个 API Key 每分钟最多 10 次请求
```

> 此限制可由服务方通过 `RATE_LIMIT` 和 `RATE_LIMIT_WINDOW` 环境变量调整。

### 被限流时的表现

HTTP 状态码 `429`，响应体：

```json
{
  "code": 429,
  "message": "请求过于频繁（限制: 10次/60秒）",
  "data": null
}
```

### 调用方最佳实践

- 在客户端维护一个轻量的发送计数器，本地预判是否接近限制
- 对 429 响应做重试，重试间隔至少等于限流窗口时间
- 将非紧急邮件（如日报、批量通知）合并为单封邮件发送
- 如默认限制不满足业务需求，请联系服务方调整配额

---

## 11. 调用示例

### 11.1 curl

```bash
#!/bin/bash
# 文件: send-mail.sh

HOST="http://localhost:9000"
API_KEY="your-api-secret-key"

# 健康检查
curl -s "$HOST/health" | python3 -m json.tool

# 异步发送（纯文本）
curl -s -X POST "$HOST/api/v1/mail/send" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "to": "user@example.com",
    "subject": "订单通知",
    "content": "您的订单 #2024001 已发货。"
  }' | python3 -m json.tool

# 同步发送（HTML）
curl -s -X POST "$HOST/api/v1/mail/send-sync" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "to": "user@example.com",
    "subject": "欢迎注册",
    "content": "<h1>欢迎！</h1><p>感谢您注册我们的服务。</p>",
    "content_type": "html"
  }' | python3 -m json.tool
```

### 11.2 Python (httpx)

推荐使用 `httpx` 替代 `requests`，它支持异步和更现代的 HTTP 特性。

```python
"""文件: email_client_async.py — 异步调用示例"""
import httpx


class EmailClient:
    """邮件发送服务客户端（异步版）
    
    用法:
        async with EmailClient(base_url, api_key) as client:
            result = await client.send_async(...)
    """

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Content-Type": "application/json",
            "X-API-Key": api_key,
        }
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            headers=self.headers,
            timeout=httpx.Timeout(30.0),
        )
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    async def health(self) -> dict:
        """健康检查"""
        resp = await self._client.get(f"{self.base_url}/health")
        return self._handle_response(resp)

    async def send_async(
        self,
        to: str,
        subject: str,
        content: str,
        content_type: str = "plain",
        cc: list[str] | None = None,
        sender_name: str | None = None,
    ) -> dict:
        """异步发送邮件（推荐）"""
        payload = self._build_payload(to, subject, content, content_type, cc, sender_name)
        resp = await self._client.post(
            f"{self.base_url}/api/v1/mail/send",
            json=payload,
        )
        return self._handle_response(resp)

    async def send_sync(
        self,
        to: str,
        subject: str,
        content: str,
        content_type: str = "plain",
        cc: list[str] | None = None,
        sender_name: str | None = None,
    ) -> dict:
        """同步发送邮件（等待 SMTP 结果）"""
        payload = self._build_payload(to, subject, content, content_type, cc, sender_name)
        resp = await self._client.post(
            f"{self.base_url}/api/v1/mail/send-sync",
            json=payload,
            timeout=httpx.Timeout(25.0),  # 同步接口需更长超时
        )
        return self._handle_response(resp)

    @staticmethod
    def _build_payload(to, subject, content, content_type, cc, sender_name):
        payload = {
            "to": to,
            "subject": subject,
            "content": content,
            "content_type": content_type,
        }
        if cc:
            payload["cc"] = cc
        if sender_name:
            payload["sender_name"] = sender_name
        return payload

    @staticmethod
    def _handle_response(resp: httpx.Response) -> dict:
        """处理响应，将错误 body 中的 message 透出"""
        result = resp.json()
        if resp.is_error:
            raise RuntimeError(result.get("message", f"HTTP {resp.status_code}"))
        return result


# ===== 使用示例 =====
import asyncio


async def main():
    async with EmailClient(
        base_url="http://localhost:9000",
        api_key="your-api-secret-key",
    ) as client:
        # 健康检查
        health = await client.health()
        print(f"服务状态: {health['status']}")

        # 异步发送
        result = await client.send_async(
            to="user@example.com",
            subject="订单通知",
            content="您的订单已发货。",
        )
        print(f"异步结果: {result}")
        # → {"code":0, "message":"已提交发送", ...}

        # 同步发送（适合验证码等场景）
        result = await client.send_sync(
            to="user@example.com",
            subject="验证码",
            content="您的验证码是：123456",
        )
        print(f"同步结果: {result}")
        # → {"code":0, "message":"发送成功", ...}


asyncio.run(main())
```

### 11.3 Python (requests)

```python
"""文件: email_client_sync.py — 同步调用示例"""
import requests
import time


class EmailClient:
    """邮件发送服务客户端（同步版）"""

    def __init__(self, base_url: str, api_key: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "X-API-Key": api_key,
        })

    def health(self) -> dict:
        """健康检查"""
        resp = self.session.get(
            f"{self.base_url}/health",
            timeout=self.timeout,
        )
        return self._handle_response(resp)

    def send_async(
        self,
        to: str,
        subject: str,
        content: str,
        content_type: str = "plain",
        cc: list[str] | None = None,
        sender_name: str | None = None,
    ) -> dict:
        """异步发送邮件"""
        payload = self._build_payload(to, subject, content, content_type, cc, sender_name)
        resp = self.session.post(
            f"{self.base_url}/api/v1/mail/send",
            json=payload,
            timeout=self.timeout,
        )
        return self._handle_response(resp)

    def send_sync(
        self,
        to: str,
        subject: str,
        content: str,
        content_type: str = "plain",
        cc: list[str] | None = None,
        sender_name: str | None = None,
    ) -> dict:
        """同步发送邮件（可能耗时数秒）"""
        payload = self._build_payload(to, subject, content, content_type, cc, sender_name)
        resp = self.session.post(
            f"{self.base_url}/api/v1/mail/send-sync",
            json=payload,
            timeout=20,  # 给 SMTP 发送留足时间
        )
        return self._handle_response(resp)

    @staticmethod
    def _handle_response(resp) -> dict:
        result = resp.json()
        if resp.status_code >= 400:
            raise RuntimeError(result.get("message", f"HTTP {resp.status_code}"))
        return result

    def _build_payload(self, to, subject, content, content_type, cc, sender_name):
        payload = {
            "to": to,
            "subject": subject,
            "content": content,
            "content_type": content_type,
        }
        if cc:
            payload["cc"] = cc
        if sender_name:
            payload["sender_name"] = sender_name
        return payload


# ===== 使用示例 =====
client = EmailClient(
    base_url="http://localhost:9000",
    api_key="your-api-secret-key",
)

# 健康检查
print(client.health())

# 异步发送
print(client.send_async(
    to="user@example.com",
    subject="通知",
    content="您的订单已发货。",
))

# 同步发送带抄送
print(client.send_sync(
    to="user@example.com",
    subject="重要通知",
    content="<h1>会议提醒</h1><p>下午 3 点会议室 A</p>",
    content_type="html",
    cc=["manager@example.com", "assistant@example.com"],
))
```

### 11.4 JavaScript / Node.js

```javascript
// 文件: email-client.js
// 安装依赖: npm install axios 或 npm install node-fetch

// ===== 使用 axios =====
const axios = require('axios');

class EmailClient {
  constructor(baseUrl, apiKey) {
    this.client = axios.create({
      baseURL: baseUrl,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': apiKey,
      },
    });
  }

  async health() {
    const { data } = await this.client.get('/health');
    return data;
  }

  async sendAsync({ to, subject, content, contentType = 'plain', cc, senderName }) {
    const payload = { to, subject, content, content_type: contentType };
    if (cc) payload.cc = cc;
    if (senderName) payload.sender_name = senderName;

    const { data } = await this.client.post('/api/v1/mail/send', payload);
    return data;
  }

  async sendSync({ to, subject, content, contentType = 'plain', cc, senderName }) {
    const payload = { to, subject, content, content_type: contentType };
    if (cc) payload.cc = cc;
    if (senderName) payload.sender_name = senderName;

    const { data } = await this.client.post('/api/v1/mail/send-sync', payload);
    return data;
  }
}

// ===== 使用示例 =====
async function main() {
  const client = new EmailClient('http://localhost:9000', 'your-api-secret-key');

  // 健康检查
  const health = await client.health();
  console.log('服务状态:', health.status);

  // 异步发送纯文本邮件
  const result1 = await client.sendAsync({
    to: 'user@example.com',
    subject: '订单通知',
    content: '您的订单 #2024001 已发货。',
  });
  console.log('异步结果:', result1);
  // → { code: 0, message: '已提交发送', data: { recipient: 'user@example.com', subject: '订单通知' } }

  // 同步发送 HTML 邮件（带抄送）
  const result2 = await client.sendSync({
    to: 'user@example.com',
    subject: '欢迎注册',
    content: '<h1>欢迎！</h1><p>感谢您的注册。</p>',
    contentType: 'html',
    cc: ['manager@example.com'],
  });
  console.log('同步结果:', result2);
  // → { code: 0, message: '发送成功', ... }
}

main().catch(console.error);
```

#### TypeScript 版本

```typescript
// 文件: email-client.ts
// 安装依赖: npm install axios
import axios, { AxiosInstance } from 'axios';

interface SendMailParams {
  to: string;
  subject: string;
  content: string;
  contentType?: 'plain' | 'html';
  cc?: string[];
  senderName?: string;
}

interface ApiResponse {
  code: number;
  message: string;
  data: Record<string, unknown> | null;
}

interface HealthResponse {
  status: string;
  smtp_configured: boolean;
  auth_configured: boolean;
  rate_limit: string;
}

class EmailClient {
  private client: AxiosInstance;

  constructor(baseUrl: string, apiKey: string) {
    this.client = axios.create({
      baseURL: baseUrl,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': apiKey,
      },
    });
  }

  async health(): Promise<HealthResponse> {
    const { data } = await this.client.get<HealthResponse>('/health');
    return data;
  }

  async sendAsync(params: SendMailParams): Promise<ApiResponse> {
    const payload = {
      to: params.to,
      subject: params.subject,
      content: params.content,
      content_type: params.contentType ?? 'plain',
      ...(params.cc && { cc: params.cc }),
      ...(params.senderName && { sender_name: params.senderName }),
    };
    const { data } = await this.client.post<ApiResponse>('/api/v1/mail/send', payload);
    return data;
  }

  async sendSync(params: SendMailParams): Promise<ApiResponse> {
    const payload = {
      to: params.to,
      subject: params.subject,
      content: params.content,
      content_type: params.contentType ?? 'plain',
      ...(params.cc && { cc: params.cc }),
      ...(params.senderName && { sender_name: params.senderName }),
    };
    const { data } = await this.client.post<ApiResponse>('/api/v1/mail/send-sync', payload);
    return data;
  }
}

// 使用示例
const client = new EmailClient('http://localhost:9000', 'your-api-secret-key');
client.sendAsync({
  to: 'user@example.com',
  subject: '通知',
  content: 'Hello!',
}).then(console.log);
```

### 11.5 Java (OkHttp)

```java
// 文件: EmailClient.java
// 依赖: com.squareup.okhttp3:okhttp, com.google.code.gson:gson

import okhttp3.*;
import com.google.gson.Gson;
import com.google.gson.JsonObject;
import java.io.IOException;
import java.util.List;
import java.util.Map;

public class EmailClient {
    private static final MediaType JSON = MediaType.parse("application/json");
    private final OkHttpClient client;
    private final String baseUrl;
    private final String apiKey;
    private final Gson gson = new Gson();

    public EmailClient(String baseUrl, String apiKey) {
        this.baseUrl = baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl;
        this.apiKey = apiKey;
        this.client = new OkHttpClient.Builder()
                .connectTimeout(10, java.util.concurrent.TimeUnit.SECONDS)
                .readTimeout(30, java.util.concurrent.TimeUnit.SECONDS)
                .build();
    }

    public JsonObject health() throws IOException {
        Request request = new Request.Builder()
                .url(baseUrl + "/health")
                .get()
                .build();
        try (Response response = client.newCall(request).execute()) {
            return gson.fromJson(response.body().string(), JsonObject.class);
        }
    }

    public JsonObject sendAsync(
            String to, String subject, String content,
            String contentType, List<String> cc, String senderName
    ) throws IOException {
        return send("/api/v1/mail/send", to, subject, content, contentType, cc, senderName);
    }

    public JsonObject sendSync(
            String to, String subject, String content,
            String contentType, List<String> cc, String senderName
    ) throws IOException {
        return send("/api/v1/mail/send-sync", to, subject, content, contentType, cc, senderName);
    }

    private JsonObject send(
            String path, String to, String subject, String content,
            String contentType, List<String> cc, String senderName
    ) throws IOException {
        JsonObject payload = new JsonObject();
        payload.addProperty("to", to);
        payload.addProperty("subject", subject);
        payload.addProperty("content", content);
        payload.addProperty("content_type", contentType != null ? contentType : "plain");
        if (cc != null && !cc.isEmpty()) {
            var ccArray = new com.google.gson.JsonArray();
            cc.forEach(ccArray::add);
            payload.add("cc", ccArray);
        }
        if (senderName != null) {
            payload.addProperty("sender_name", senderName);
        }

        RequestBody body = RequestBody.create(gson.toJson(payload), JSON);
        Request request = new Request.Builder()
                .url(baseUrl + path)
                .post(body)
                .header("X-API-Key", apiKey)
                .build();

        try (Response response = client.newCall(request).execute()) {
            return gson.fromJson(response.body().string(), JsonObject.class);
        }
    }
}
```

### 11.6 Go

```go
// 文件: email_client.go
package emailclient

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"time"
)

// Client 邮件发送服务客户端
type Client struct {
	baseURL    string
	apiKey     string
	httpClient *http.Client
}

// SendMailParams 发送邮件请求参数
type SendMailParams struct {
	To          string   `json:"to"`
	Subject     string   `json:"subject"`
	Content     string   `json:"content"`
	ContentType string   `json:"content_type,omitempty"` // "plain" 或 "html"
	Cc          []string `json:"cc,omitempty"`
	SenderName  string   `json:"sender_name,omitempty"`
}

// ApiResponse 通用响应
type ApiResponse struct {
	Code    int                    `json:"code"`
	Message string                 `json:"message"`
	Data    map[string]interface{} `json:"data"`
}

// HealthResponse 健康检查响应
type HealthResponse struct {
	Status          string `json:"status"`
	SmtpConfigured  bool   `json:"smtp_configured"`
	AuthConfigured  bool   `json:"auth_configured"`
	RateLimit       string `json:"rate_limit"`
}

// New 创建客户端
func New(baseURL, apiKey string) *Client {
	return &Client{
		baseURL: baseURL,
		apiKey:  apiKey,
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
	}
}

// Health 健康检查
func (c *Client) Health() (*HealthResponse, error) {
	resp, err := c.httpClient.Get(c.baseURL + "/health")
	if err != nil {
		return nil, fmt.Errorf("健康检查请求失败: %w", err)
	}
	defer resp.Body.Close()

	var result HealthResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("解析响应失败: %w", err)
	}
	return &result, nil
}

// SendAsync 异步发送邮件
func (c *Client) SendAsync(params SendMailParams) (*ApiResponse, error) {
	return c.send("/api/v1/mail/send", params)
}

// SendSync 同步发送邮件
func (c *Client) SendSync(params SendMailParams) (*ApiResponse, error) {
	return c.send("/api/v1/mail/send-sync", params)
}

func (c *Client) send(path string, params SendMailParams) (*ApiResponse, error) {
	// 设置默认值
	if params.ContentType == "" {
		params.ContentType = "plain"
	}

	body, err := json.Marshal(params)
	if err != nil {
		return nil, fmt.Errorf("序列化请求体失败: %w", err)
	}

	req, err := http.NewRequest("POST", c.baseURL+path, bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("创建请求失败: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-API-Key", c.apiKey)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("请求失败: %w", err)
	}
	defer resp.Body.Close()

	var result ApiResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("解析响应失败: %w", err)
	}
	return &result, nil
}
```

### 11.7 PHP (cURL)

```php
<?php
// 文件: email_client.php

class EmailClient {
    private string $baseUrl;
    private string $apiKey;

    public function __construct(string $baseUrl, string $apiKey) {
        $this->baseUrl = rtrim($baseUrl, '/');
        $this->apiKey = $apiKey;
    }

    public function health(): array {
        return $this->get('/health');
    }

    public function sendAsync(
        string $to,
        string $subject,
        string $content,
        string $contentType = 'plain',
        ?array $cc = null,
        ?string $senderName = null
    ): array {
        return $this->post('/api/v1/mail/send', [
            'to' => $to,
            'subject' => $subject,
            'content' => $content,
            'content_type' => $contentType,
            'cc' => $cc,
            'sender_name' => $senderName,
        ]);
    }

    public function sendSync(
        string $to,
        string $subject,
        string $content,
        string $contentType = 'plain',
        ?array $cc = null,
        ?string $senderName = null
    ): array {
        return $this->post('/api/v1/mail/send-sync', [
            'to' => $to,
            'subject' => $subject,
            'content' => $content,
            'content_type' => $contentType,
            'cc' => $cc,
            'sender_name' => $senderName,
        ]);
    }

    private function get(string $path): array {
        $ch = curl_init($this->baseUrl . $path);
        curl_setopt_array($ch, [
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT => 10,
            CURLOPT_HTTPHEADER => [
                'X-API-Key: ' . $this->apiKey,
            ],
        ]);
        $result = curl_exec($ch);
        $this->checkError($ch);
        curl_close($ch);
        return json_decode($result, true);
    }

    private function post(string $path, array $data): array {
        // 清理空字段
        $data = array_filter($data, fn($v) => $v !== null && $v !== []);
        
        $ch = curl_init($this->baseUrl . $path);
        curl_setopt_array($ch, [
            CURLOPT_POST => true,
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT => 20,
            CURLOPT_HTTPHEADER => [
                'Content-Type: application/json',
                'X-API-Key: ' . $this->apiKey,
            ],
            CURLOPT_POSTFIELDS => json_encode($data, JSON_UNESCAPED_UNICODE),
        ]);
        $result = curl_exec($ch);
        $this->checkError($ch);
        curl_close($ch);
        return json_decode($result, true);
    }

    private function checkError($ch): void {
        if (curl_errno($ch)) {
            throw new RuntimeException('cURL 错误: ' . curl_error($ch));
        }
    }
}

// ===== 使用示例 =====
$client = new EmailClient('http://localhost:9000', 'your-api-secret-key');

print_r($client->health());

print_r($client->sendAsync(
    'user@example.com',
    '订单通知',
    '您的订单已发货。'
));

print_r($client->sendSync(
    'user@example.com',
    '验证码',
    '您的验证码是：123456'
));
```

---

## 12. 最佳实践

### 12.1 选择合适的接口

```
需要确认发送结果？         → 使用同步接口（send-sync）
     │
     └─ 仅验证码/密码重置/重要告警 → 同步
     └─ 其他场景                → 异步（send）
```

### 12.2 调用方应实现

```python
# 伪代码 — 推荐的重试 + 超时模式
async def send_with_retry(client, payload, max_retries=3):
    for attempt in range(max_retries):
        try:
            result = await client.send_async(**payload)
            if result["code"] == 0:
                return result
            # 不可重试的错误
            if result["code"] in (400, 403):
                raise ValueError(result["message"])
        except (httpx.TimeoutException, httpx.NetworkError):
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)  # 指数退避
```

### 12.3 效率建议

| 建议 | 说明 |
|---|---|
| **复用连接** | 使用连接池（`requests.Session`、`httpx.AsyncClient`、`axios` 实例），避免每次请求都新建 TCP 连接 |
| **设置超时** | 异步接口 10s，同步接口 20s（SMTP 发送可能耗时数秒） |
| **批量通知合并** | 多封通知邮件合并为单封（使用 `cc` 字段），减少 SMTP 调用次数 |
| **异步优先** | 默认走异步接口，仅关键场景走同步 |
| **限流本地预判** | 在调用方维持计数器，接近限制时主动降速 |

### 12.4 监控建议

```bash
# 服务端健康检查（建议每 30 秒轮询）
curl -s http://localhost:9000/health

# 服务端手动验证发送（每日定时任务）
curl -s -X POST http://localhost:9000/api/v1/mail/send-sync \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"to":"ops@example.com","subject":"每日自检","content":"邮件服务正常"}'
```

### 12.5 常见集成问题

| 问题 | 排查步骤 |
|---|---|
| `Connection refused` | 确认服务地址和端口是否正确，防火墙是否放行 |
| `timeout` | 检查调用方与服务端之间的网络连通性 |
| `403` | 确认 `X-API-Key` 的值是否正确 |
| `500: 认证失败` | SMTP 授权码可能过期，联系部署方更新 `.env` |
| 异步返回成功但邮件未收到 | 检查垃圾邮件箱；联系部署方查看服务端日志 |

---

## 修订历史

| 日期 | 版本 | 修订内容 |
|---|---|---|
---

## 13. dc-tools 后端集成实践

> 本节描述 dc-tools 后端如何调用本邮件服务，以及通知系统的完整架构。
> 适用于在 dc-tools 中新增模块时正确接入通知。

### 13.1 通知架构总览

```
                    ┌──────────────────────────────────┐
                    │    业务逻辑层（runner.py / routers） │
                    └──────────┬───────────────────────┘
                               │ send_notification()
                               ▼
               ┌───────────────────────────────────────┐
               │  wecom_notifier.send_notification()    │
               │  (WeChat + Email 合并入口，永不抛异常)    │
               └──────────┬──────────┬─────────────────┘
                          │          │
               ┌──────────▼─┐  ┌─────▼──────────────┐
               │ WeChat      │  │ Email               │
               │ Webhook     │  │ send_email_         │
               │ (Markdown)  │  │ notification()      │
               └──────┬──────┘  └──────┬──────────────┘
                      │                │
               ┌──────▼──────┐  ┌──────▼──────────────┐
               │ 企业微信      │  │ 外部邮件 API（本服务） │
               │ 机器人消息    │  │ POST /api/v1/mail/  │
               │             │  │ send (异步)          │
               └─────────────┘  └─────────────────────┘
```

**两个通道完全独立**：各自有自己的启停开关、模块粒度和收件人配置。

### 13.2 数据模型

**`user_notification_configs` 表** — 每个用户一行（`user_id` 唯一）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `enabled` | bool | WeChat 总开关 |
| `webhook_url` | text | 企业微信机器人 Webhook URL |
| `module_flags` | text | JSON：`{"price_cleanup": true, "requirement": true}` |
| `email_enabled` | bool | 邮件总开关 |
| `email_to` | text | 自定义收件邮箱（可选） |
| `email_module_flags` | text | JSON：`{"price_cleanup": true, "requirement": true}` |

**`system_configs` 表** — 系统级邮件 API 配置：

| config_key | config_value | 说明 |
|---|---|---|
| `email_api_url` | `http://localhost:9000` | 邮件服务地址，默认 `http://localhost:9000` |
| `email_api_key` | `xxx` | 邮件服务 API Key，**未配置则跳过所有邮件发送** |

### 13.3 通知控制链路

每条通知走以下链路，每个环节均可"掐断"：

```
用户操作触发
    │
    ▼
┌─ 判断 module_key 是否匹配 ──────────────┐
│  price_cleanup / requirement 等          │
└──────────┬──────────────────────────────┘
           │
     ┌─────┴─────┐
     ▼           ▼
  WeChat       Email
     │           │
     ▼           ▼
enabled?     email_enabled?
     │           │
     ▼           ▼
webhook_url  email_to 或 user.email
  存在?        存在?
     │           │
     ▼           ▼
module_flags  email_module_flags
[module_key]  [module_key]
  为 true?      为 true?
     │           │
     ▼           ▼
  发送消息      email_api_key 已配置?
                    │
                    ▼
                 发送邮件
```

**重要**：`module_flags` / `email_module_flags` 默认值行为不同：
- 在 `send_notification()` 中，默认所有 feature 模块为 **true**（全部开启）
- 在通知配置 API 中，默认所有 feature 模块为 **false**（用户需手动勾选）
- 这是因为通知配置 API 的 `_default_flags()` 返回全 `false`，而 `send_notification()` 逻辑中的 `_parse_flags()` 在 `raw` 为 `None` 时返回全 `true`

### 13.4 收件人解析

**邮件收件人优先级**（`email_notifier.py:_load_email_recipient`）：

```
1. config.email_to（用户在通知配置中自定义的邮箱）
2. user.email（用户注册时填写的邮箱）
3. 均不存在 → 跳过发信
```

**WeChat 收件人**：直接使用 `config.webhook_url`，不存在则跳过。

### 13.5 通知模板

两个通道共享同一套模板数据，但渲染格式不同：

| 通道 | 渲染函数 | 格式 |
|---|---|---|
| WeChat | `build_markdown()` | 纯 Markdown |
| Email | `build_html()` | HTML（Markdown → HTML 转换 + 内联样式包装） |

模板数据包含字段：`stage`、`task_name`、`username`、`status`、`error_message`、`completed_at`、`stats`。

### 13.6 两种通知模式

#### 模式 A：用户触发 → 通知本人

用户执行动作，结果通知回到该用户自己。

```
用户 A 触发 price_cleanup
    │
    ▼
send_notification(user_id=A, module_key="price_cleanup")
    │
    ▼
同时检查 A 的 WeChat 和 Email 配置
```

**适用场景**：`price_cleanup`（剔旧价格整理）

#### 模式 B：双向通知（用户 ↔ 管理员）

**用户 → 管理员**：用户创建/编辑需求，通知管理员。

```
用户创建需求
    │
    ▼
_notify_admin_requirement()
    │
    ▼
查询 role=admin 的用户
    │
    ▼
send_notification(user_id=admin.id, module_key="requirement")
```

**管理员 → 用户**：管理员变更需求状态，通知提交人。

```
管理员更新需求状态
    │
    ▼
send_notification(user_id=req.user_id, module_key="requirement")
    │
    ▼
通知原提交人
```

**适用场景**：`requirement`（需求征集）

### 13.7 系统级配置管理

邮件功能需要管理员在 **系统配置页面** 设置以下两项：

| 配置项 | 必填 | 说明 |
|---|---|---|
| `email_api_url` | 否 | 邮件服务地址，默认 `http://localhost:9000` |
| `email_api_key` | **是** | 邮件服务 API Key，未配置则所有邮件通知被静默跳过 |

配置存储在 `system_configs` 表中，通过 `/api/v1/admin/system-config` 接口管理。

### 13.8 测试入口

用户可在通知配置页面测试两个通道：

| 端点 | 方法 | 说明 |
|---|---|---|
| `POST /api/v1/user/notification-config/test` | 测试 WeChat | 向指定 Webhook URL 发送测试消息 |
| `POST /api/v1/user/notification-config/test-email` | 测试邮件 | 向指定邮箱发送测试邮件（需系统已配置 `email_api_key`） |

### 13.9 新增模块接入通知

如需为新模块增加通知支持，只需三步：

1. **在 `MODULES` 列表中添加 `kind="feature"` 的模块**（`registry.py`），`feature_module_keys()` 自动返回该 key
2. **在 `SUBJECT_TEMPLATES` 中添加邮件主题模板**（`email_notifier.py`）
3. **在业务逻辑完成/失败处调用 `send_notification()`**（`wecom_notifier.py`）

```python
# 示例：新增模块通知
await send_notification(
    db,
    user_id=user_id,          # 收通知的用户 ID
    module_key="your_module", # 与 MODULES 中的 key 一致
    instance_data={
        "stage": "你的模块名称",
        "task_name": "...",
        "username": "...",
        "status": "completed",  # 或 "failed"
        "error_message": "...",  # 仅失败时
        "completed_at": "...",
        "stats": {"key": "value"},
    },
)
```

用户会自动在通知配置页面看到新模块的开关，无需修改前端。

### 13.10 设计原则

| 原则 | 说明 |
|---|---|
| **Best-effort** | 通知从不抛异常给调用方，失败仅记录日志 |
| **通道独立** | WeChat 和 Email 各自独立开关、独立 try/except |
| **模块粒度** | 每个通道可精确控制哪些模块发通知 |
| **系统 + 用户双层控制** | 系统层控制邮件服务可用性，用户层控制个人偏好 |

---

## 修订历史

| 日期 | 版本 | 修订内容 |
|---|---|---|
| 2026-07-23 | v1.0 | 初版，覆盖所有接口和 7 种语言调用示例 |
| 2026-08-02 | v1.1 | 新增第 13 节：dc-tools 后端集成实践 |
