from pydantic_settings import BaseSettings

class BaseAgentSettings(BaseSettings):
    aws_region: str
    mcp_server_arn: str
    profile_mcp_server_arn: str
