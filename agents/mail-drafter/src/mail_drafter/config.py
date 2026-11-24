from pathlib import Path
from agent_shared.config.settings import BaseAgentSettings

class Settings(BaseAgentSettings):
    agent_arn: str
    model_id: str
    opus_model_id: str
    ecr_repository: str
    agent_runtime_id: str
    email_history_table: str = "email-drafts"

    class Config:
        # agents/mail-drafter/.env (this file is at agents/mail-drafter/src/mail_drafter/)
        env_file = Path(__file__).resolve().parents[2] / ".env"

settings = Settings()
