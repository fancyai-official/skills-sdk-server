# Claude Agent SDK Server

这是一个轻量的 Bun/TypeScript 服务，将 `@anthropic-ai/claude-agent-sdk` 封装为 HTTP + Server-Sent Events 接口。仓库内包含一个已脱敏的示例应用 **Icon Designer**，用于展示项目级 Claude skills、静态介绍、交互式问题，以及可选的图片生成 provider。

本目录已整理为适合公开发布到 GitHub 的项目：不包含私有部署文件、不包含真实 API key，并且只保留一个示例 app。

## 选择使用路径

建议先从最低成本的路径开始，只有需要时再接入付费服务。

| 路径 | 你会得到什么 | 需要什么 | 成本 |
|---|---|---|---|
| **Mock demo** | 启动服务、运行示例 app、生成本地占位图 | Bun + Anthropic 兼容 API key | 仅模型 token |
| **Claude chat** | 基于 `/agent-sdk/stream` 和 `/agent-sdk/answer` 构建自己的 UI 或集成 | 上述内容 + 客户端代码 | 模型 token |
| **真实图片生成** | 用 Tencent Cloud 或 DMXAPI 替换占位图，并可选接入 R2 发布 | provider 凭据和存储配置 | 模型 token + 图片 API/存储费用 |

如果你第一次使用本项目，先看 [`QUICKSTART.zh.md`](QUICKSTART.zh.md)，然后试用 [`examples/client.zh.html`](examples/client.zh.html)。

## 功能

- `POST /agent-sdk/stream`：通过 SSE 流式返回 Claude Agent SDK 事件。
- `POST /agent-sdk/answer`：接收前端对 `AskUserQuestion` 的回答。
- 本地历史接口：读取 Claude 对话 JSONL 文件。
- 静态介绍配置：无需调用上游模型即可返回 app 自我介绍。
- `app-icon-designer`：包含本地 `mock` 图片 provider，不需要云端图片生成凭据即可运行。

## 项目结构

```text
.
├── src/                         # Bun 服务和 SDK wrapper
├── .claude/
│   ├── CLAUDE.md                # 全局交互规则
│   └── apps/app-icon-designer/  # 唯一开源示例 app
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

## 快速开始

```bash
bun install
cp .env.example .env
# 编辑 .env 并设置 ANTHROPIC_AUTH_TOKEN。
bun run dev
```

服务默认监听：

```text
http://127.0.0.1:20001
```

如果想按 5 分钟步骤操作，请看 [`QUICKSTART.zh.md`](QUICKSTART.zh.md)。启动服务后，也可以直接打开 [`examples/client.zh.html`](examples/client.zh.html) 试用浏览器客户端。

## 最小请求示例

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

如果设置了 `AGENT_SDK_API_KEY`，请求时需要加：

```bash
Authorization: Bearer <token>
```

## 示例 App

`app-icon-designer` 展示了项目级 `CLAUDE.md`、skill 级 `SKILL.md`、静态介绍配置、交互式问题，以及三步式图片生成脚本约定。

默认配置为：

```bash
ICON_DESIGNER_PROVIDER=mock
```

`mock` provider 会在本地生成占位 PNG，因此不需要付费图片 API 也能跑通流程。若要接入真实 provider，可以设置：

- `ICON_DESIGNER_PROVIDER=tencent`，并配置 Tencent Cloud 相关变量；
- `ICON_DESIGNER_PROVIDER=dmxapi`，并配置 `DMX_API_KEY`；
- `ICON_DESIGNER_PROVIDER=auto`，先尝试 Tencent，失败后回退到 DMXAPI。

本示例仅将知名时装设计师作为历史和美学灵感引用，不代表与任何设计师、时装屋或商标权利人存在关联、授权、赞助或背书关系。

## 环境变量

完整列表见 `.env.example`。重要变量包括：

- `ANTHROPIC_AUTH_TOKEN`：上游 API key。
- `ANTHROPIC_BASE_URL`：可选的 Anthropic 兼容 API 地址。
- `ANTHROPIC_MODEL`：默认模型。
- `AGENT_SDK_API_KEY`：可选的本服务访问鉴权 token。
- `ICON_DESIGNER_PROVIDER`：`mock`、`tencent`、`dmxapi` 或 `auto`。
- `UPLOAD_PROVIDER`：生成资源的发布方式，支持 `local` 或 `r2`。

## Docker

```bash
cp .env.example .env
docker compose up --build
```

本地运行时，mock 图片默认写入 `.generated/`；Docker Compose 运行时，生成文件映射到 `generated-output/`。对话数据持久化到 `claude-data/`。

## 开发

```bash
bun run typecheck
bun run build
```

示例 app 的 Python 辅助脚本依赖见 `requirements.txt`。

## 安全说明

- 不要提交本地环境文件、密钥文件、对话日志或生成媒体。
- 如果要在 localhost 之外暴露服务，建议设置 `AGENT_SDK_API_KEY`。
- provider 凭据是可选项，应通过环境变量注入。

## 许可证

Apache-2.0。见 `LICENSE`。
