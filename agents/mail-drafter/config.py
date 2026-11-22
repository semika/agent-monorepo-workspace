from pathlib import Path
from shared.config.settings import BaseAgentSettings

class Settings(BaseAgentSettings):
    agent_arn: str
    model_id: str
    opus_model_id: str
    ecr_repository: str
    agent_runtime_id: str
    email_history_table: str = "email-drafts"

    class Config:
        env_file = Path(__file__).parent / ".env"

settings = Settings()
