import os

API_ROUTE_PREFIX = os.environ.get("API_ROUTE_PREFIX", "/api/v1")

TITLE = "AI Model Access Gateway"
SUMMARY = "OpenAI-Compatible RESTful APIs for MaaS Models"
VERSION = "0.1.0"
DESCRIPTION = """
Use OpenAI-Compatible RESTful APIs to access unified model services.
"""

DEBUG = os.environ.get("DEBUG", "false").lower() != "false"

# ---------------------------------------------------------------------------
# 模型服务（MaaS）配置
#   - 对话（chat）与嵌入（embedding）是两个独立 OpenAI 兼容端点，
#     版本可能不同（chat=/v2, embed=/v1），因此各持一个 client，不能共用。
#   - API Key 从环境变量注入（部署时由 K8s Secret 提供），不硬编码。
# ---------------------------------------------------------------------------
MAAS_API_KEY = os.environ.get("MAAS_API_KEY", "")
MAAS_CHAT_BASE_URL = os.environ.get(
    "MAAS_CHAT_BASE_URL", "https://api.modelarts-maas.com/v2"
)
MAAS_EMBED_BASE_URL = os.environ.get(
    "MAAS_EMBED_BASE_URL", "https://api.modelarts-maas.com/v1"
)

# 默认模型（对话 / 嵌入），客户端请求未携带 model 时使用
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "DeepSeek-V4-Flash")
DEFAULT_EMBEDDING_MODEL = os.environ.get("DEFAULT_EMBEDDING_MODEL", "BGE-M3")

# 网关对外暴露的模型清单（models API 返回）。
# 格式：逗号分隔的 "模型ID:支持模态(TEXT|IMAGE)"，例如
#   DeepSeek-V4-Flash:TEXT,DeepSeek-V3.2:TEXT,Qwen3-32B:TEXT
# 未配置时使用下方默认清单。
MODEL_LIST_CONFIG = os.environ.get("MODEL_LIST", "")

DEFAULT_MODEL_LIST = [
    "DeepSeek-V4-Flash:TEXT",
    "DeepSeek-V3.2:TEXT",
    "openPangu-2.0-Flash:TEXT",
    "Qwen3-32B:TEXT",
    "BGE-M3:TEXT",
]

# 多模态支持：MaaS 预置对话模型为纯文本模型（不支持图片输入）。
# VISION_ENABLED=true 时保留 image_url 块传给模型（需服务端支持）；
# 默认 false：图片块被忽略，仅保留文本（业务侧改用文本/元数据驱动）。
VISION_ENABLED = os.environ.get("VISION_ENABLED", "false").lower() == "true"
