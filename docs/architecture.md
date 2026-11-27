# 架构说明

## 概述

本实践提供一个 **OpenAI 兼容的模型访问网关**：以 OpenAI SDK / cURL 为标准接口，统一接入华为云 MaaS 预置模型服务（对话与文本向量化），并附带统一的 API Key 鉴权、模型白名单与 SSE 流式输出能力。

适用于：已有基于 OpenAI API 开发的应用（LangChain、AutoGen、自研 Agent 等），希望不改代码切换到华为云大模型服务的场景。

## 架构图

```
┌───────────────────────┐        ┌────────────────────────────────────────────┐
│  OpenAI SDK / cURL    │        │              网关（CCE 容器）                │
│  (LangChain/AutoGen)  │──HTTP──▶  FastAPI + uvicorn                          │
└───────────────────────┘  Bearer │  ├─ /api/v1/models        模型清单          │
                                  │  ├─ /api/v1/chat/completions  对话 + SSE    │
                                  │  └─ /api/v1/embeddings       文本向量化     │
                                  └───────────┬────────────────────────────────┘
                                              │ MaaS OpenAI 兼容端点（公网）
                                              ▼
                          ┌─────────────────────────────────────┐
                          │  MaaS 预置模型服务                     │
                          │  chat:  /v2/chat/completions         │
                          │  embed: /v1/embeddings               │
                          │  （DeepSeek-V4-Flash / BGE-M3 等）    │
                          └─────────────────────────────────────┘
```

## 组件说明

| 组件 | 说明 |
|---|---|
| 网关（CCE Deployment） | FastAPI 应用，无状态、可水平扩展；健康检查 `/health` |
| 公网入口（独享型 ELB + EIP） | 由 CCE Service 注解自动创建，HTTP:80 → 容器 8000 |
| 模型服务（MaaS） | 对话与嵌入两个 OpenAI 兼容端点，API Key 鉴权 |
| 凭据（K8s Secret） | 网关 API Key 与 MaaS API Key，经环境变量注入容器 |

## 关键设计

1. **OpenAI 兼容协议**：请求/响应均为 OpenAI 格式，客户端无需任何改造。
2. **双端点客户端**：对话（`/v2`）与嵌入（`/v1`）是两个独立 base_url，各持一个 OpenAI client（版本可能不同，不能共用）。
3. **SSE 流式**：`stream=true` 时以 `text/event-stream` 逐块返回，支持 `stream_options.include_usage`。
4. **模型白名单**：通过 `MODEL_LIST` 环境变量配置（`模型ID:模态` 逗号分隔），`/api/v1/models` 返回清单并校验请求模型。
5. **统一鉴权**：所有 `/api/v1/*` 请求需携带 `Authorization: Bearer <API_KEY>`（网关自己的 API Key，与 MaaS API Key 相互独立）。

## 配置项（环境变量）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `API_KEY` | 无（必填） | 网关对外 API Key |
| `MAAS_API_KEY` | 无（必填） | MaaS 模型服务 API Key |
| `MAAS_CHAT_BASE_URL` | `https://api.modelarts-maas.com/v2` | 对话端点 base_url |
| `MAAS_EMBED_BASE_URL` | `https://api.modelarts-maas.com/v1` | 嵌入端点 base_url |
| `DEFAULT_MODEL` | `DeepSeek-V4-Flash` | 默认对话模型（请求缺省 model 或 gpt-* 时兜底） |
| `DEFAULT_EMBEDDING_MODEL` | `BGE-M3` | 默认嵌入模型 |
| `MODEL_LIST` | 内置默认清单 | 模型白名单（逗号分隔 `ID:模态`） |
| `VISION_ENABLED` | `false` | 是否透传图片输入（预置对话模型为纯文本时保持 false） |
| `API_ROUTE_PREFIX` | `/api/v1` | API 路由前缀 |
| `ALLOWED_ORIGINS` | `*` | CORS 允许来源 |
| `DEBUG` | `false` | 请求/响应调试日志 |
