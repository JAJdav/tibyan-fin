from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    app_env: str = "dev"
    log_level: str = "INFO"
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_db: str = "fraud_aml"
    mysql_user: str = "fraud_app"
    mysql_password: str = "change_me"
    mysql_pool_size: int = 10
    mysql_max_overflow: int = 20
    mysql_pool_recycle_s: int = 1800
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""
    llm_mode: str = "mock"
    llm_base_url: str = "http://127.0.0.1:11434"
    llm_model: str = "qwen3:8b"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8",
                                      case_sensitive=False, extra="ignore")

    @property
    def mysql_url(self) -> URL:
        return URL.create("mysql+pymysql", username=self.mysql_user,
                          password=self.mysql_password, host=self.mysql_host,
                          port=self.mysql_port, database=self.mysql_db,
                          query={"charset": "utf8mb4"})


settings = Settings()
