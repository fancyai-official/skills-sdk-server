# 快速开始

这份指南帮助你在大约 5 分钟内跑通开源 demo。

## 1. 安装运行环境

安装 Bun：

```bash
npm install -g bun
```

确认安装成功：

```bash
bun --version
```

## 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，至少设置：

```bash
ANTHROPIC_AUTH_TOKEN=replace-with-your-api-key
ICON_DESIGNER_PROVIDER=mock
```

首次运行建议使用 `mock`。它会生成本地占位图，不需要图片生成 provider 的凭据。

## 3. 启动服务

```bash
bun install
bun run dev
```

服务默认启动在：

```text
http://127.0.0.1:20001
```

## 4. 试用浏览器 Demo

在浏览器中打开：

```text
examples/client.zh.html
```

点击 **发送介绍请求**。页面会：

1. 调用 `POST /agent-sdk/stream`；
2. 展示流式事件；
3. 渲染 `ask_user_question` 按钮；
4. 将答案发送回 `POST /agent-sdk/answer`。

## 5. 试用直接请求

```bash
curl -N http://127.0.0.1:20001/agent-sdk/stream \
  -H "Content-Type: application/json" \
  -d '{
    "userMessage": "Explain to me what you do",
    "options": {
      "cwd": "./.claude/apps/app-icon-designer",
      "allowedTools": ["Skill", "AskUserQuestion", "Bash"]
    }
  }'
```

如果你设置了 `AGENT_SDK_API_KEY`，需要加上：

```bash
-H "Authorization: Bearer your-token"
```

## 下一步可以尝试什么

- 构建 UI 时，先保持 `ICON_DESIGNER_PROVIDER=mock`。
- 只有拿到 provider 凭据后，再切换到 `ICON_DESIGNER_PROVIDER=dmxapi` 或 `tencent`。
- 只有需要将生成文件发布到 Cloudflare R2 时，再设置 `UPLOAD_PROVIDER=r2`。

## 常见问题

- `Missing ANTHROPIC_AUTH_TOKEN`：在 `.env` 中设置该变量，或在请求体中传入 `apiKey`。
- `Unauthorized`：本地测试时可以移除 `AGENT_SDK_API_KEY`，或发送匹配的 bearer token。
- 浏览器出现 CORS 或连接错误：确认服务正在 `http://127.0.0.1:20001` 运行。
- 没有真实图片输出：使用 `ICON_DESIGNER_PROVIDER=mock` 时这是预期行为，它会返回本地占位图。
