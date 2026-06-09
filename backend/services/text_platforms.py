"""v1.4.11+: 文本引擎平台清单。

BUILTIN_TEXT_PLATFORMS 列出常见 OpenAI-compatible 平台 + 本地 ollama。
所有非 ollama 平台都走 services/llm.py 的 _stream_openai_compat 通道，
所以加新平台 = 在这里加一行，不需要改 driver。

用户自定义平台存在 settings.text_engine.custom_platforms 列表里。
"""
from __future__ import annotations

from config import TextPlatform


BUILTIN_TEXT_PLATFORMS: list[TextPlatform] = [
    # 本地
    TextPlatform(
        id="ollama", label="Ollama（本地）",
        base_url="http://localhost:11434",
        api_path="api/chat",      # ollama 自有路径
        is_ollama=True, is_builtin=True,
        model_hint="如 llama3.2 / qwen2.5:7b / deepseek-r1",
    ),
    TextPlatform(
        id="lmstudio", label="LM Studio（本地）",
        base_url="http://localhost:1234/v1",
        api_path="chat/completions",
        is_builtin=True,
        model_hint="LM Studio 控制台加载的模型名",
    ),

    # 国内云
    TextPlatform(
        id="deepseek", label="DeepSeek（深度求索）",
        base_url="https://api.deepseek.com",
        api_path="chat/completions",
        is_builtin=True,
        model_hint="deepseek-chat / deepseek-reasoner",
    ),
    TextPlatform(
        id="bailian", label="阿里云百炼（通义千问）",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_path="chat/completions",
        is_builtin=True,
        model_hint="qwen-max / qwen-plus / qwen-turbo",
    ),
    TextPlatform(
        id="volcengine", label="火山方舟（Doubao / Seed）",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        api_path="chat/completions",
        is_builtin=True,
        model_hint="如 doubao-seed-2-0-pro-260215 / doubao-seed-2-0-lite-260428；或控制台 Endpoint ID",
    ),
    TextPlatform(
        id="moonshot", label="月之暗面 Kimi（Moonshot）",
        base_url="https://api.moonshot.cn/v1",
        api_path="chat/completions",
        is_builtin=True,
        model_hint="kimi-k2-0905-preview / moonshot-v1-128k",
    ),
    TextPlatform(
        id="bigmodel_glm", label="智谱 GLM（BigModel）",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        api_path="chat/completions",
        is_builtin=True,
        model_hint="glm-4-plus / glm-4-air / glm-4-flash",
    ),
    TextPlatform(
        id="stepfun", label="阶跃星辰 Step",
        base_url="https://api.stepfun.com/v1",
        api_path="chat/completions",
        is_builtin=True,
        model_hint="step-2-16k / step-1-flash / step-2-mini",
    ),
    TextPlatform(
        id="siliconflow", label="硅基流动 SiliconFlow",
        base_url="https://api.siliconflow.cn/v1",
        api_path="chat/completions",
        is_builtin=True,
        model_hint="Qwen/Qwen2.5-72B-Instruct / deepseek-ai/DeepSeek-V3",
    ),
    TextPlatform(
        id="minimax", label="MiniMax（海螺）",
        base_url="https://api.minimaxi.com/v1",
        api_path="chat/completions",
        is_builtin=True,
        model_hint="MiniMax-M1-80k / abab6.5s-chat",
    ),
    TextPlatform(
        id="zhipu", label="智谱 Zhipu（z.ai）",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        api_path="chat/completions",
        is_builtin=True,
        model_hint="同 BigModel，等价别名",
    ),

    # 海外
    TextPlatform(
        id="openai", label="OpenAI",
        base_url="https://api.openai.com/v1",
        api_path="chat/completions",
        is_builtin=True,
        model_hint="gpt-4o / gpt-4o-mini / gpt-4.1",
    ),
    TextPlatform(
        id="anthropic_oai", label="Anthropic（OpenAI 兼容）",
        base_url="https://api.anthropic.com/v1",
        api_path="chat/completions",
        is_builtin=True,
        model_hint="claude-opus-4 / claude-sonnet-4.5",
    ),
    TextPlatform(
        id="google_gemini", label="Google Gemini（OpenAI 兼容）",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        api_path="chat/completions",
        is_builtin=True,
        model_hint="gemini-2.5-pro / gemini-2.5-flash",
    ),
    TextPlatform(
        id="openrouter", label="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        api_path="chat/completions",
        is_builtin=True,
        model_hint="如 openrouter/auto / anthropic/claude-3.5-sonnet",
    ),

    # 通用兜底
    TextPlatform(
        id="openai_compat", label="自定义 OpenAI 兼容端点",
        base_url="https://api.example.com/v1",
        api_path="chat/completions",
        is_builtin=True,
        model_hint="填你自己的端点 + 模型 ID",
    ),
]


def merge_platforms(custom: list[TextPlatform]) -> list[TextPlatform]:
    """合并 builtin + 用户自定义，自定义在后。同 id 时 builtin 优先（防覆盖）。"""
    seen = {p.id for p in BUILTIN_TEXT_PLATFORMS}
    out = list(BUILTIN_TEXT_PLATFORMS)
    for p in custom or []:
        if p.id in seen:
            continue
        out.append(p)
    return out
