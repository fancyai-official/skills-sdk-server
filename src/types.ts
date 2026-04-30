import type { Options } from "@anthropic-ai/claude-agent-sdk";

/**
 * 对话消息角色。
 */
export type Role = "user" | "assistant";

/**
 * 简化后的历史消息结构（用于历史读取/展示）。
 */
export interface HistoryMessage {
  role: Role;
  content: string;
  images?: ImageAttachment[];
}

/**
 * 请求中携带的图片附件。
 * 支持 base64 内联数据 或 URL 引用两种方式（二选一）。
 */
export interface ImageAttachment {
  /** base64 编码的图片数据（与 url 二选一） */
  data?: string;
  /** 图片的公开可访问 URL（与 data 二选一） */
  url?: string;
  /** MIME 类型，默认 image/jpeg */
  media_type?: "image/jpeg" | "image/png" | "image/gif" | "image/webp";
}

/**
 * 透传给 Claude Agent SDK 的 options。
 *
 * 注意：服务端会强制 `permissionMode=bypassPermissions` 且跳过交互权限；
 * 即使调用方传入相关字段，也不会生效。
 */
export type RequestOptions = Partial<Options>;

/**
 * `POST /agent-sdk/stream` 的请求体结构。
 */
export interface RequestBody {
  prompt?: string;
  userMessage?: string;
  /** 随消息附带的图片列表（支持 base64 或 URL） */
  images?: ImageAttachment[];
  systemPrompt?: string;
  model?: string;
  baseURL?: string;
  apiKey?: string;
  conversationId?: string;
  /** 用户标识，用于隔离不同用户的 Claude Code 项目上下文，防止会话串信息 */
  userId?: string;
  options?: RequestOptions;
}

/**
 * settingSources 的允许取值。
 */
export type SettingSource = "user" | "project" | "local";

/**
 * permissionMode 的允许取值。
 */
export type PermissionMode = "default" | "acceptEdits" | "bypassPermissions" | "plan" | "dontAsk";

// No beta flag passthrough in this server.
