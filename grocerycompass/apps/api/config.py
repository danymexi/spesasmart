from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    app_env: str = "development"
    allowed_origins: str = "http://localhost:3000"

    # Database
    database_url: str = "postgresql+asyncpg://gc_user:gc_dev_password@localhost:5432/grocerycompass"
    database_pool_size: int = 20

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Meilisearch
    meilisearch_host: str = "http://localhost:7700"
    meilisearch_api_key: str = "gc_dev_meili_key"

    # Auth
    jwt_secret: str = "dev-jwt-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
