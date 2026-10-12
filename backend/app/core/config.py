"""应用配置：从环境变量 / 上级目录 ``.env`` 读取（pydantic-settings）。"""

import warnings
from typing import Literal, Self

from pydantic import (
    EmailStr,
    HttpUrl,
    PostgresDsn,
    computed_field,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置项。

    Attributes:
        DATABASE_URL: 运行时连接串（``app_user``，非表 owner、NOBYPASSRLS）。
        MIGRATION_DATABASE_URL: 迁移 / 维护用连接串（表 owner），缺省回退到 DATABASE_URL。
        SECRET_KEY: JWT 签名密钥，生产环境必须修改。
        FIRST_SUPERUSER: 首个超级用户邮箱（init_db 创建）。
        FASTAPI_ENV: 运行环境；``development`` 时挂载 private 路由。
        UPLOAD_DIR: 上传文件目录（相对路径基于 backend/）。
    """

    model_config = SettingsConfigDict(
        # 使用顶层 .env 文件（./backend/ 的上一级）
        env_file="../.env",
        env_ignore_empty=True,
        extra="ignore",
    )
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str
    # 60 minutes * 24 hours * 8 days = 8 days
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8
    #: Q-Time 超时自动扫描周期（秒），0 表示关闭后台扫描
    QTIME_SWEEP_SECONDS: int = 0
    FRONTEND_HOST: str = "http://localhost:5173"
    FASTAPI_ENV: Literal["development"] | None = None

    PROJECT_NAME: str
    # 上传文件（品牌图片等）目录，相对路径基于 backend/
    UPLOAD_DIR: str = "data/uploads"
    MAX_UPLOAD_BYTES: int = 5 * 1024 * 1024
    SENTRY_DSN: HttpUrl | None = None
    DATABASE_URL: PostgresDsn
    # 特权连接串（表 owner），用于迁移 / 角色初始化。应用本身
    # 以非 owner 角色经 DATABASE_URL 连接，从而强制 Postgres RLS。
    MIGRATION_DATABASE_URL: PostgresDsn | None = None

    @property
    def migration_database_url(self) -> str:
        """迁移用连接串：MIGRATION_DATABASE_URL，未配置时回退到 DATABASE_URL。"""
        return str(self.MIGRATION_DATABASE_URL or self.DATABASE_URL)

    @field_validator("DATABASE_URL", "MIGRATION_DATABASE_URL", mode="before")
    @classmethod
    def _use_psycopg_driver(cls, value: str | PostgresDsn | None) -> str | None:
        if value is None:
            return None
        database_url = str(value)
        for scheme in ("postgres://", "postgresql://"):
            if database_url.startswith(scheme):
                return database_url.replace(scheme, "postgresql+psycopg://", 1)
        return database_url

    SMTP_TLS: bool = True
    SMTP_SSL: bool = False
    SMTP_PORT: int = 587
    SMTP_HOST: str | None = None
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    EMAILS_FROM_EMAIL: EmailStr | None = None
    EMAILS_FROM_NAME: str | None = None

    @model_validator(mode="after")
    def _set_default_emails_from(self) -> Self:
        if not self.EMAILS_FROM_NAME:
            self.EMAILS_FROM_NAME = self.PROJECT_NAME
        return self

    EMAIL_RESET_TOKEN_EXPIRE_HOURS: int = 48

    @computed_field  # type: ignore[prop-decorator]
    @property
    def emails_enabled(self) -> bool:
        """是否已配置 SMTP 与发件人（决定是否发送邮件）。"""
        return bool(self.SMTP_HOST and self.EMAILS_FROM_EMAIL)

    EMAIL_TEST_USER: EmailStr = "test@example.com"
    FIRST_SUPERUSER: EmailStr
    FIRST_SUPERUSER_USERNAME: str = "admin"
    FIRST_SUPERUSER_PASSWORD: str

    def _check_default_secret(self, var_name: str, value: str | None) -> None:
        if value == "changethis":
            message = (
                f'The value of {var_name} is "changethis", '
                "for security, please change it, at least for deployments."
            )
            if self.FASTAPI_ENV == "development":
                warnings.warn(message, stacklevel=1)
            else:
                raise ValueError(message)

    @model_validator(mode="after")
    def _enforce_non_default_secrets(self) -> Self:
        self._check_default_secret("SECRET_KEY", self.SECRET_KEY)
        for host in self.DATABASE_URL.hosts():
            self._check_default_secret("DATABASE_URL password", host["password"])
        self._check_default_secret(
            "FIRST_SUPERUSER_PASSWORD", self.FIRST_SUPERUSER_PASSWORD
        )

        return self


settings = Settings()  # type: ignore # ty: ignore[unused-ignore-comment]
