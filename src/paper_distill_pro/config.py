"""Configuration — all settings from environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── General ──────────────────────────────────────────────────────────────
    log_level: str = "INFO"
    http_timeout: float = 15.0
    http_retries: int = 3
    user_agent: str = "paper-distill-pro/0.1.0 (mailto:user@example.com)"

    # ── Academic API keys ─────────────────────────────────────────────────────
    semantic_scholar_api_key: str | None = None
    core_api_key: str | None = None
    unpaywall_email: str = "user@example.com"
    ieee_api_key: str | None = None  # developer.ieee.org (free)
    pubmed_api_key: str | None = None
    elsevier_api_key: str | None = None  # Scopus / ScienceDirect (for ACM/IEEE fallback)
    ssrn_api_key: str | None = None  # optional

    # ── Zotero ───────────────────────────────────────────────────────────────
    zotero_api_key: str | None = None
    zotero_user_id: str | None = None
    zotero_group_id: str | None = None

    # ── Mendeley (OAuth 2.0 client credentials) ───────────────────────────────
    mendeley_client_id: str | None = None
    mendeley_client_secret: str | None = None
    mendeley_redirect_uri: str = "http://localhost:8080/callback"
    # Store the access token after first auth
    mendeley_access_token: str | None = None
    mendeley_refresh_token: str | None = None

    # ── Notion ────────────────────────────────────────────────────────────────
    notion_token: str | None = None
    notion_database_id: str | None = None

    # ── Push channels ─────────────────────────────────────────────────────────
    slack_webhook_url: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    wecom_webhook_url: str | None = None
    feishu_webhook_url: str | None = None
    discord_webhook_url: str | None = None

    # SMTP
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_to: str | None = None

    # ── Digest scheduler ──────────────────────────────────────────────────────
    push_keywords: str = "large language models,retrieval augmented generation"
    push_max_papers_per_keyword: int = 5
    push_since_days: int = 7
    push_channels: str = "slack"
    push_digest_title: str = "Scholar Daily Digest"

    # ── Sub-agent (LLM for enhanced parsing) ─────────────────────────────────
    sub_agent_api_key: str | None = None
    sub_agent_base_url: str = "https://api.anthropic.com/v1"
    sub_agent_model: str = "claude-3-5-sonnet-20241022"
    sub_agent_max_tokens: int = 4096

    # ── Local storage ─────────────────────────────────────────────────────────
    obsidian_vault_path: str | None = None
    cache_dir: str = ".paper_cache"

    @property
    def keywords_list(self) -> list[str]:
        return [k.strip() for k in self.push_keywords.split(",") if k.strip()]

    @property
    def channels_list(self) -> list[str]:
        return [c.strip() for c in self.push_channels.split(",") if c.strip()]

    @property
    def smtp_recipients(self) -> list[str]:
        if not self.smtp_to:
            return []
        return [r.strip() for r in self.smtp_to.split(",") if r.strip()]


settings = Settings()
