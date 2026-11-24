# Creating AWS Agent Runtime using Bedrock AgentCore Control API
import boto3
from mail_drafter.config import settings
try:
    client = boto3.client('bedrock-agentcore-control', region_name=settings.aws_region)

    response = client.create_agent_runtime(
        agentRuntimeName='mail_drafter_agent',
        agentRuntimeArtifact={
            'containerConfiguration': {
                'containerUri': settings.ecr_repository
            }
        },
        lifecycleConfiguration={
            'idleRuntimeSessionTimeout': 900,  # 30 minutes
            'maxLifetime': 28800  # 4 hours
        },
        networkConfiguration={"networkMode": "PUBLIC"},
        roleArn='arn:aws:iam::762002331286:role/AgentRuntimeRole'
    )

    print(f"Agent Runtime created successfully!")
    print(f"Agent Runtime ARN: {response['agentRuntimeArn']}")
    print(f"Status: {response['status']}")

except Exception as e:
    print(f"Error creating Agent Runtime: {str(e)}")    