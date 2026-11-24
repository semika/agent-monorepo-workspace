import boto3
import json
from mail_drafter.config import settings

try:
    agent_core_client = boto3.client('bedrock-agentcore', region_name=settings.aws_region)
    payload = json.dumps({
        "input": {"prompt": "What is the largest country in the world ?"}
    })

    response = agent_core_client.invoke_agent_runtime(
        agentRuntimeArn=settings.agent_arn,
        runtimeSessionId='dfmeoagmreaklgmrkleafremoigrmtesogmtrskhmtkrlshmt',  # Must be 33+ chars
        payload=payload,
        qualifier="DEFAULT"
    )

    # For detail list of all the supported parameters for invoke_agent_runtime, refer to:
    # https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/API_InvokeAgentRuntime.html

    response_body = response['response'].read()
    response_data = json.loads(response_body)
    print("Agent Response:", response_data)
except Exception as e:
    print(f"Error invoking Agent Runtime: {str(e)}")