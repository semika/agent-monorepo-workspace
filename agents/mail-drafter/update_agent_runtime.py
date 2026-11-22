import boto3
from config import settings

client = boto3.client('bedrock-agentcore-control', region_name=settings.aws_region)

agent_runtime_id = settings.agent_runtime_id

try:
    response = client.update_agent_runtime(
        agentRuntimeId=agent_runtime_id,
        agentRuntimeArtifact={
            'containerConfiguration': {
                'containerUri': settings.ecr_repository
            }
        },
        networkConfiguration={'networkMode': 'PUBLIC'},
        roleArn='arn:aws:iam::762002331286:role/AgentRuntimeRole',
        lifecycleConfiguration={
            'idleRuntimeSessionTimeout': 600,   # 10 minutes
            'maxLifetime': 7200                 # 2 hours
        }
    )

    print("Lifecycle configuration updated successfully")
except client.exceptions.ValidationException as e:
    print(f"Validation error: {e}")
except client.exceptions.ResourceNotFoundException:
    print("Agent runtime not found")
except Exception as e:
    print(f"Error updating configuration: {e}") 