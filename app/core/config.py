from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost/efko_access_dev"
    jwt_secret_key: str = "dev-secret-key"
    jwt_algorithm: str = "HS256"
    rabbitmq_url: str = "amqp://guest:guest@localhost/"
    redis_url: str = "redis://localhost:6379/0"
    api_port: int = 8000
    api_host: str = "0.0.0.0"
    environment: str = "development"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

settings = Settings()