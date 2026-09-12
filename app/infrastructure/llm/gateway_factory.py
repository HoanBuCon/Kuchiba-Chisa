from __future__ import annotations

import httpx

from app.application.llm_gateway import LLMGateway, LLMGatewayPolicy, ProviderModel
from app.config.settings import Settings
from app.domain.interfaces.llm_provider import LLMCapability, LLMPurpose

_ALL_PURPOSES = frozenset(purpose for purpose in LLMPurpose if purpose is not LLMPurpose.UNKNOWN)
_TEXT_STRUCTURED_STREAM = frozenset(
    {
        LLMCapability.TEXT,
        LLMCapability.STRUCTURED_OUTPUT,
        LLMCapability.STREAMING,
    }
)


def _provider_names(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(part.strip().lower() for part in value.split(",") if part.strip()))


def _provider_purposes(value: str) -> frozenset[LLMPurpose]:
    parts = _provider_names(value)
    if parts == ("*",):
        return _ALL_PURPOSES
    return frozenset(LLMPurpose(part) for part in parts)


def validate_llm_configuration(config: Settings) -> list[str]:
    """Return sanitized config-readiness findings without contacting providers."""
    enabled = _provider_names(config.LLM_ENABLED_PROVIDERS)
    fallback = _provider_names(config.LLM_FALLBACK_PROVIDERS)
    supported = {"deepseek", "gemini", "groq"}
    findings: list[str] = []
    unknown = sorted(set(enabled) - supported)
    if unknown:
        findings.append(f"unsupported enabled LLM providers: {', '.join(unknown)}")
    if config.LLM_PROVIDER not in enabled:
        findings.append("primary LLM provider is not enabled")
    for provider in fallback:
        if provider not in enabled:
            findings.append(f"fallback LLM provider is not enabled: {provider}")
    keys = {
        "deepseek": config.DEEPSEEK_API_KEY,
        "gemini": config.GEMINI_API_KEY,
        "groq": config.GROQ_API_KEY,
    }
    models = {
        "deepseek": config.DEEPSEEK_MODEL,
        "gemini": config.GEMINI_MODEL,
        "groq": config.GROQ_MODEL,
    }
    purpose_values = {
        "deepseek": config.LLM_DEEPSEEK_PURPOSES,
        "gemini": config.LLM_GEMINI_PURPOSES,
        "groq": config.LLM_GROQ_PURPOSES,
    }
    parsed_purposes: dict[str, frozenset[LLMPurpose]] = {}
    for provider in enabled:
        if provider in supported and not keys[provider]:
            findings.append(f"enabled LLM provider is missing credentials: {provider}")
        if provider in supported and not models[provider].strip():
            findings.append(f"enabled LLM provider is missing a model: {provider}")
        if provider in supported:
            try:
                purposes = _provider_purposes(purpose_values[provider])
            except ValueError:
                findings.append(f"enabled LLM provider has invalid purpose eligibility: {provider}")
            else:
                parsed_purposes[provider] = purposes
                if not purposes:
                    findings.append(f"enabled LLM provider has no eligible purposes: {provider}")
    if "deepseek" in enabled and not config.DEEPSEEK_VISION_MODEL.strip():
        findings.append("DeepSeek vision model is not configured")
    configured = {provider for provider in enabled if provider in supported and keys[provider]}
    if not configured:
        findings.append("no configured model supports text and structured output")
    if "deepseek" not in configured:
        findings.append("no configured model supports grounded tool output and vision")
    elif LLMPurpose.CHAT_RESPONSE not in parsed_purposes.get("deepseek", frozenset()):
        findings.append("DeepSeek primary does not allow chat_response purpose")
    return findings


def build_llm_gateway(
    *, config: Settings, http_client: httpx.AsyncClient
) -> LLMGateway:
    """Build enabled adapters and their immutable capability declarations."""
    enabled = _provider_names(config.LLM_ENABLED_PROVIDERS)
    providers: list[ProviderModel] = []

    if "deepseek" in enabled and config.DEEPSEEK_API_KEY:
        from app.infrastructure.llm.adapters.deepseek import DeepSeekAdapter

        adapter = DeepSeekAdapter(http_client=http_client)
        providers.extend(
            [
                ProviderModel(
                    provider="deepseek",
                    model=config.DEEPSEEK_MODEL,
                    capabilities=frozenset(
                        {
                            *_TEXT_STRUCTURED_STREAM,
                            LLMCapability.TOOL_CALLING,
                        }
                    ),
                    purposes=_provider_purposes(config.LLM_DEEPSEEK_PURPOSES),
                    adapter=adapter,
                    concurrency_limit=config.LLM_DEEPSEEK_CONCURRENCY,
                ),
                ProviderModel(
                    provider="deepseek",
                    model=config.DEEPSEEK_VISION_MODEL,
                    capabilities=frozenset(
                        {
                            LLMCapability.TEXT,
                            LLMCapability.STRUCTURED_OUTPUT,
                            LLMCapability.VISION,
                            LLMCapability.TOOL_CALLING,
                        }
                    ),
                    purposes=_provider_purposes(config.LLM_DEEPSEEK_PURPOSES),
                    adapter=adapter,
                    concurrency_limit=config.LLM_DEEPSEEK_CONCURRENCY,
                ),
            ]
        )

    if "gemini" in enabled and config.GEMINI_API_KEY:
        from app.infrastructure.llm.adapters.gemini import GeminiAdapter

        providers.append(
            ProviderModel(
                provider="gemini",
                model=config.GEMINI_MODEL,
                capabilities=_TEXT_STRUCTURED_STREAM,
                purposes=_provider_purposes(config.LLM_GEMINI_PURPOSES),
                adapter=GeminiAdapter(),
                concurrency_limit=config.LLM_GEMINI_CONCURRENCY,
            )
        )

    if "groq" in enabled and config.GROQ_API_KEY:
        from app.infrastructure.llm.adapters.groq import GroqAdapter

        providers.append(
            ProviderModel(
                provider="groq",
                model=config.GROQ_MODEL,
                capabilities=_TEXT_STRUCTURED_STREAM,
                purposes=_provider_purposes(config.LLM_GROQ_PURPOSES),
                adapter=GroqAdapter(),
                concurrency_limit=config.LLM_GROQ_CONCURRENCY,
            )
        )

    return LLMGateway(
        providers,
        LLMGatewayPolicy(
            primary_provider=config.LLM_PROVIDER,
            fallback_providers=_provider_names(config.LLM_FALLBACK_PROVIDERS),
            per_attempt_timeout_seconds=config.LLM_CALL_TIMEOUT_SECONDS,
            first_token_timeout_seconds=config.LLM_FIRST_TOKEN_TIMEOUT_SECONDS,
            request_deadline_seconds=config.LLM_REQUEST_DEADLINE_SECONDS,
            bulkhead_wait_seconds=config.LLM_BULKHEAD_WAIT_SECONDS,
            retry_limit=config.LLM_RETRY_LIMIT,
            retry_base_seconds=config.LLM_RETRY_BASE_SECONDS,
            retry_max_seconds=config.LLM_RETRY_MAX_SECONDS,
            breaker_failure_threshold=config.LLM_BREAKER_FAILURE_THRESHOLD,
            breaker_recovery_seconds=config.LLM_BREAKER_RECOVERY_SECONDS,
        ),
    )
