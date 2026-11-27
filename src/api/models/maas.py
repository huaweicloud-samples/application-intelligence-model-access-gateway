"""
统一模型访问层：OpenAI 兼容接口 → MaaS 预置模型服务
=========================================================

对外接口：
    MaaSModel.list_models() / validate() / chat() / chat_stream()
    get_embeddings_model(model_id).embed()

底层走华为云 MaaS（ModelArts Studio）OpenAI 兼容端点：
    - 对话（chat）：base_url 取 MAAS_CHAT_BASE_URL（如 https://api.modelarts-maas.com/v2）
    - 嵌入（embed）：base_url 取 MAAS_EMBED_BASE_URL（如 https://api.modelarts-maas.com/v1）
    两个端点版本可能不同，各持一个 client，不能共用。

依赖：pip install openai
凭据：从环境变量读取（部署时由 K8s Secret 注入），不硬编码。
"""

import base64
import json
import logging
import re
import time
from typing import AsyncIterable, Iterable, Literal

import numpy as np
import requests
from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

from api.models.base import BaseChatModel, BaseEmbeddingsModel
from api.schema import (
    AssistantMessage,
    ChatRequest,
    ChatResponse,
    ChatResponseMessage,
    ChatStreamResponse,
    Choice,
    ChoiceDelta,
    CompletionTokensDetails,
    Embedding,
    EmbeddingsRequest,
    EmbeddingsResponse,
    EmbeddingsUsage,
    Error,
    ErrorMessage,
    ImageContent,
    PromptTokensDetails,
    ResponseFunction,
    TextContent,
    ToolCall,
    ToolMessage,
    Usage,
    UserMessage,
)
from api.setting import (
    DEFAULT_MODEL,
    DEFAULT_EMBEDDING_MODEL,
    DEBUG,
    MAAS_API_KEY,
    MAAS_CHAT_BASE_URL,
    MAAS_EMBED_BASE_URL,
    MODEL_LIST_CONFIG,
    DEFAULT_MODEL_LIST,
    VISION_ENABLED,
)

logger = logging.getLogger(__name__)


# ============================================================================
# 模型清单
# ============================================================================

def load_model_list() -> dict[str, dict]:
    """从环境变量加载模型清单，返回 {model_id: {"modalities": [...]}}。"""
    result = {}
    raw = MODEL_LIST_CONFIG or ",".join(DEFAULT_MODEL_LIST)
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if ":" in entry:
            model_id, modality = entry.rsplit(":", 1)
        else:
            model_id, modality = entry, "TEXT"
        result[model_id.strip()] = {"modalities": [m.strip().upper() for m in modality.split("|")]}
    if not result:
        result[DEFAULT_MODEL] = {"modalities": ["TEXT"]}
    return result


# 模块级缓存：首次启动加载；models API 可触发刷新
model_list = load_model_list()


def refresh_model_list() -> dict[str, dict]:
    """刷新模型清单（供 models API 调用）。"""
    global model_list
    model_list = load_model_list()
    return model_list


# ============================================================================
# 对话模型
# ============================================================================

class MaaSModel(BaseChatModel):
    """OpenAI 兼容对话模型（MaaS 预置模型服务）。

    请求/响应均为 OpenAI 格式；MaaS 端点天然兼容，直接透传即可。
    当前端点的能力边界：
      - 不支持 prompt caching（客户端 extra_body.prompt_caching 被忽略）
      - 不支持 top_k（OpenAI 标准无此参数）
      - reasoning_effort 由服务端模型自行决定（透传为 thinking 参数，见 _build_args）
    """

    def __init__(self):
        from openai import OpenAI
        self._client = OpenAI(base_url=MAAS_CHAT_BASE_URL, api_key=MAAS_API_KEY)
        self.think_emitted = False

    # ------------------------------------------------------------------ #
    # 模型清单
    # ------------------------------------------------------------------ #
    def list_models(self) -> list[str]:
        refresh_model_list()
        return list(model_list.keys())

    def validate(self, chat_request: ChatRequest):
        if chat_request.model not in model_list.keys():
            error = (
                f"Unsupported model {chat_request.model}, "
                f"please use models API to get a list of supported models"
            )
            logger.error("Unsupported model: %s", chat_request.model)
            raise HTTPException(status_code=400, detail=error)

    # ------------------------------------------------------------------ #
    # 请求构造
    # ------------------------------------------------------------------ #
    def _build_args(self, chat_request: ChatRequest, stream: bool = False) -> dict:
        effective_max_tokens = (
            chat_request.max_completion_tokens
            if chat_request.max_completion_tokens is not None
            else chat_request.max_tokens
        )

        args: dict = {
            "model": chat_request.model,
            "messages": self._to_openai_messages(chat_request),
            "stream": stream,
        }
        if effective_max_tokens is not None:
            args["max_tokens"] = effective_max_tokens
        if chat_request.temperature is not None:
            args["temperature"] = chat_request.temperature
        if chat_request.top_p is not None:
            args["top_p"] = chat_request.top_p
        if chat_request.stop is not None:
            args["stop"] = chat_request.stop
        if chat_request.tools:
            args["tools"] = [self._convert_tool_spec(t.function) for t in chat_request.tools]
            if isinstance(chat_request.tool_choice, str):
                # auto / required / none 为 OpenAI 标准取值，直接透传
                args["tool_choice"] = chat_request.tool_choice
            elif isinstance(chat_request.tool_choice, dict) and "function" in chat_request.tool_choice:
                args["tool_choice"] = {
                    "type": "function",
                    "function": {"name": chat_request.tool_choice["function"].get("name", "")},
                }
        if stream:
            args["stream_options"] = {"include_usage": True}
        return args

    def _to_openai_messages(self, chat_request: ChatRequest) -> list[dict]:
        """OpenAI 请求消息已是 OpenAI 格式，逐条归一化即可。"""
        messages = []
        for message in chat_request.messages:
            if isinstance(message, (UserMessage, AssistantMessage)):
                messages.append(
                    {"role": message.role, "content": self._parse_content_parts(message)}
                )
                if isinstance(message, AssistantMessage) and message.tool_calls:
                    for tool_call in message.tool_calls:
                        messages.append(
                            {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": tool_call.id,
                                        "type": "function",
                                        "function": {
                                            "name": tool_call.function.name,
                                            "arguments": tool_call.function.arguments,
                                        },
                                    }
                                ],
                            }
                        )
            elif isinstance(message, ToolMessage):
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": message.tool_call_id,
                        "content": self._extract_tool_content(message.content),
                    }
                )
            else:
                # system / developer 直接保留
                content = message.content if isinstance(message.content, str) else str(message.content)
                messages.append({"role": message.role, "content": content})
        return messages

    def _extract_tool_content(self, content) -> str:
        """把各种 OpenAI 工具消息内容格式归一化为字符串。"""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    parts.append(str(item["text"]))
                elif hasattr(item, "text"):
                    parts.append(item.text)
                else:
                    parts.append(str(item))
            return "\n".join(parts)
        return str(content) if content is not None else ""

    def _parse_content_parts(self, message: UserMessage | AssistantMessage):
        """OpenAI content 已是目标格式；图片块按 VISION_ENABLED 处理。"""
        if isinstance(message.content, str):
            return message.content
        parts = []
        for part in message.content:
            if isinstance(part, TextContent):
                parts.append({"type": "text", "text": part.text})
            elif isinstance(part, ImageContent):
                if not VISION_ENABLED:
                    logger.warning(
                        "Image content ignored: the configured model is text-only. "
                        "Set VISION_ENABLED=true if the model supports image input."
                    )
                    continue
                image_data, content_type = self._parse_image(part.image_url.url)
                parts.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{content_type};base64,{base64.b64encode(image_data).decode()}"
                        },
                    }
                )
            else:
                continue
        return parts if parts else ""

    def _parse_image(self, image_url: str) -> tuple[bytes, str]:
        """从 data URI 或远程 URL 获取图片原始数据。"""
        pattern = r"^data:(image/[a-z]*);base64,\s*"
        content_type = re.search(pattern, image_url)
        if content_type:
            image_data = re.sub(pattern, "", image_url)
            return base64.b64decode(image_data), content_type.group(1)

        response = requests.get(image_url, timeout=30)
        if response.status_code == 200:
            content_type = response.headers.get("Content-Type", "image/jpeg")
            if not content_type.startswith("image"):
                content_type = "image/jpeg"
            return response.content, content_type
        raise HTTPException(status_code=500, detail="Unable to access the image url")

    def _convert_tool_spec(self, func) -> dict:
        return {
            "type": "function",
            "function": {
                "name": func.name,
                "description": func.description,
                "parameters": func.parameters,
            },
        }

    # ------------------------------------------------------------------ #
    # 同步对话
    # ------------------------------------------------------------------ #
    async def chat(self, chat_request: ChatRequest) -> ChatResponse:
        message_id = self.generate_message_id()
        args = self._build_args(chat_request)
        if DEBUG:
            logger.info("MaaS request: %s", json.dumps(args, default=str))
        try:
            response = await run_in_threadpool(
                self._client.chat.completions.create, **args
            )
        except Exception as e:
            logger.error("Model invocation failed for model %s: %s", chat_request.model, str(e))
            raise HTTPException(status_code=500, detail=str(e))

        choice = response.choices[0]
        message = choice.message
        usage = response.usage

        chat_response = self._create_response(
            model=chat_request.model,
            message_id=message_id,
            content=message.content,
            tool_calls=message.tool_calls,
            finish_reason=choice.finish_reason,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            total_tokens=getattr(usage, "total_tokens", 0) or 0,
            reasoning_tokens=getattr(getattr(usage, "completion_tokens_details", None), "reasoning_tokens", 0) or 0,
        )
        if DEBUG:
            logger.info("Proxy response :" + chat_response.model_dump_json())
        return chat_response

    # ------------------------------------------------------------------ #
    # 流式对话（SSE）
    # ------------------------------------------------------------------ #
    async def _async_iterate(self, stream):
        for chunk in stream:
            await run_in_threadpool(lambda: chunk)
            yield chunk

    async def chat_stream(self, chat_request: ChatRequest) -> AsyncIterable[bytes]:
        message_id = self.generate_message_id()
        args = self._build_args(chat_request, stream=True)
        try:
            stream = await run_in_threadpool(
                self._client.chat.completions.create, **args
            )
            reasoning_tokens = 0
            async for chunk in self._async_iterate(stream):
                stream_response = self._create_response_stream(
                    model_id=chat_request.model,
                    message_id=message_id,
                    chunk=chunk,
                )
                if not stream_response:
                    continue
                if stream_response.usage and reasoning_tokens > 0:
                    stream_response.usage.completion_tokens_details = CompletionTokensDetails(
                        reasoning_tokens=reasoning_tokens,
                        audio_tokens=0,
                    )
                if DEBUG:
                    logger.info("Proxy response :" + stream_response.model_dump_json())
                if stream_response.choices:
                    yield self.stream_response_to_bytes(stream_response)
                elif chat_request.stream_options and chat_request.stream_options.include_usage:
                    # OpenAI 约定：include_usage 时在 [DONE] 前输出 usage chunk（choices 为空）
                    yield self.stream_response_to_bytes(stream_response)
            yield self.stream_response_to_bytes()
        except Exception as e:
            logger.error("Stream error for model %s: %s", chat_request.model, str(e))
            error_event = Error(error=ErrorMessage(message=str(e)))
            yield self.stream_response_to_bytes(error_event)

    # ------------------------------------------------------------------ #
    # 响应构造
    # ------------------------------------------------------------------ #
    def _create_response(
        self,
        model: str,
        message_id: str,
        content: str | None = None,
        tool_calls: list | None = None,
        finish_reason: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
        reasoning_tokens: int = 0,
    ) -> ChatResponse:
        message = ChatResponseMessage(role="assistant")
        if tool_calls:
            message.tool_calls = [
                ToolCall(
                    id=tc.id,
                    type="function",
                    function=ResponseFunction(
                        name=tc.function.name,
                        arguments=tc.function.arguments,
                    ),
                )
                for tc in tool_calls
            ]
            message.content = None
        else:
            message.content = content or ""

        prompt_tokens_details = None
        completion_tokens_details = None
        if reasoning_tokens > 0:
            completion_tokens_details = CompletionTokensDetails(
                reasoning_tokens=reasoning_tokens,
                audio_tokens=0,
            )

        response = ChatResponse(
            id=message_id,
            model=model,
            choices=[
                Choice(
                    index=0,
                    message=message,
                    finish_reason=self._convert_finish_reason(finish_reason),
                    logprobs=None,
                )
            ],
            usage=Usage(
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                total_tokens=total_tokens if total_tokens > 0 else input_tokens + output_tokens,
                prompt_tokens_details=prompt_tokens_details,
                completion_tokens_details=completion_tokens_details,
            ),
        )
        response.system_fingerprint = "fp"
        response.object = "chat.completion"
        response.created = int(time.time())
        return response

    def _create_response_stream(
        self, model_id: str, message_id: str, chunk
    ) -> ChatStreamResponse | None:
        """MaaS 流式 chunk 已是 OpenAI 格式，直接映射到网关 schema。"""
        if not chunk.choices:
            # usage chunk
            if chunk.usage:
                usage = chunk.usage
                return ChatStreamResponse(
                    id=message_id,
                    model=model_id,
                    choices=[],
                    usage=Usage(
                        prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                        completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
                        total_tokens=getattr(usage, "total_tokens", 0) or 0,
                    ),
                )
            return None

        choice = chunk.choices[0]
        delta = choice.delta
        message = ChatResponseMessage()
        if delta.role:
            message.role = delta.role
        if delta.content:
            message.content = delta.content
        if delta.tool_calls:
            message.tool_calls = [
                ToolCall(
                    index=tc.index,
                    id=tc.id,
                    type="function",
                    function=ResponseFunction(
                        name=tc.function.name if tc.function else None,
                        arguments=tc.function.arguments if tc.function else "",
                    ),
                )
                for tc in delta.tool_calls
            ]

        return ChatStreamResponse(
            id=message_id,
            model=model_id,
            choices=[
                ChoiceDelta(
                    index=choice.index or 0,
                    delta=message,
                    logprobs=None,
                    finish_reason=self._convert_finish_reason(choice.finish_reason),
                )
            ],
            usage=None,
        )

    @staticmethod
    def is_supported_modality(model_id: str, modality: str = "IMAGE") -> bool:
        m = model_list.get(model_id, {})
        return modality in m.get("modalities", [])

    def _convert_finish_reason(self, finish_reason: str | None) -> str | None:
        """OpenAI finish_reason 已符合 OpenAI 语义，直接返回。"""
        if finish_reason:
            mapping = {
                "tool_calls": "tool_calls",
                "stop": "stop",
                "length": "length",
                "content_filter": "content_filter",
                "function_call": "tool_calls",
            }
            return mapping.get(finish_reason.lower(), finish_reason.lower())
        return None


# ============================================================================
# 嵌入模型
# ============================================================================

SUPPORTED_EMBEDDING_MODELS = {
    "BGE-M3": "Text Embedding",
    "text-embedding-v3": "Text Embedding",
}


class MaaSEmbeddingsModel(BaseEmbeddingsModel):
    """OpenAI 兼容文本嵌入模型（MaaS 文本向量化服务）。"""

    def __init__(self):
        from openai import OpenAI
        self._client = OpenAI(base_url=MAAS_EMBED_BASE_URL, api_key=MAAS_API_KEY)

    def embed(self, embeddings_request: EmbeddingsRequest) -> EmbeddingsResponse:
        input_texts = self._parse_input(embeddings_request)
        try:
            response = self._client.embeddings.create(
                model=embeddings_request.model,
                input=input_texts,
            )
        except Exception as e:
            logger.error("Embedding invocation failed: %s", str(e))
            raise HTTPException(status_code=500, detail=str(e))

        embeddings = [item.embedding for item in response.data]
        usage = response.usage
        return self._create_response(
            embeddings=embeddings,
            model=embeddings_request.model,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=0,
            encoding_format=embeddings_request.encoding_format,
        )

    def _parse_input(self, req: EmbeddingsRequest) -> list[str]:
        if isinstance(req.input, str):
            return [req.input]
        if isinstance(req.input, list):
            texts = []
            for item in req.input:
                if isinstance(item, str):
                    texts.append(item)
                elif isinstance(item, int):
                    texts.append(str(item))
                elif isinstance(item, Iterable):
                    texts.append(" ".join(str(x) for x in item))
                else:
                    raise HTTPException(status_code=400, detail=f"Unsupported input item type: {type(item).__name__}")
            return texts
        raise HTTPException(status_code=400, detail="Unsupported input type")

    def _create_response(
        self,
        embeddings: list[list[float]],
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        encoding_format: Literal["float", "base64"] = "float",
    ) -> EmbeddingsResponse:
        data = []
        for i, embedding in enumerate(embeddings):
            if encoding_format == "base64":
                arr = np.array(embedding, dtype=np.float32)
                data.append(Embedding(index=i, embedding=base64.b64encode(arr.tobytes())))
            else:
                data.append(Embedding(index=i, embedding=embedding))
        return EmbeddingsResponse(
            data=data,
            model=model,
            usage=EmbeddingsUsage(
                prompt_tokens=input_tokens,
                total_tokens=input_tokens + output_tokens,
            ),
        )


def get_embeddings_model(model_id: str) -> MaaSEmbeddingsModel:
    if model_id not in SUPPORTED_EMBEDDING_MODELS:
        logger.error("Unsupported embedding model id %s", model_id)
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported embedding model id {model_id}. "
                   f"Supported: {sorted(SUPPORTED_EMBEDDING_MODELS.keys())}",
        )
    return MaaSEmbeddingsModel()
