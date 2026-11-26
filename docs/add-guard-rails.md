`ChatBedrockConverse` already supports this through the `guardrail_config` parameter, which you've started on in your selection. In langchain-aws 1.5.0 the dict is passed to the Bedrock Converse API's `guardrailConfig`, and snake_case keys are converted to camelCase for you. I haven't changed any code.

## 1. Create a guardrail in Bedrock (one-time)

The model needs the ID and version of a guardrail that already exists. Create it in the console under **Bedrock → Guardrails**, or with the CLI:

```bash
aws bedrock create-guardrail --region ap-southeast-1 \
  --name mail-drafter-guardrail \
  --blocked-input-messaging "Sorry, I can't help with that request." \
  --blocked-outputs-messaging "Sorry, I can't produce that content." \
  --content-policy-config '{"filtersConfig":[
      {"type":"HATE","inputStrength":"HIGH","outputStrength":"HIGH"},
      {"type":"INSULTS","inputStrength":"HIGH","outputStrength":"HIGH"},
      {"type":"SEXUAL","inputStrength":"HIGH","outputStrength":"HIGH"},
      {"type":"VIOLENCE","inputStrength":"MEDIUM","outputStrength":"MEDIUM"},
      {"type":"PROMPT_ATTACK","inputStrength":"HIGH","outputStrength":"NONE"}]}' \
  --sensitive-information-policy-config '{"piiEntitiesConfig":[
      {"type":"CREDIT_DEBIT_CARD_NUMBER","action":"BLOCK"},
      {"type":"PASSWORD","action":"BLOCK"}]}'

# Freeze the current draft as version "1" for production use
aws bedrock create-guardrail-version --guardrail-identifier <guardrailId> --region ap-southeast-1
```

This is only an example. The filter types and strength levels are up to you.

## 2. Add the IDs to settings

In [config.py](agents/mail-drafter/src/mail_drafter/config.py):
```python
class Settings(BaseAgentSettings):
    ...
    guardrail_id: str
    guardrail_version: str = "DRAFT"   # use a numbered version ("1") in production
```
In `agents/mail-drafter/.env`:
```env
guardrail_id=abc123xyz
guardrail_version=1
```

If other agents will use guardrails too, put these two fields in `BaseAgentSettings` in `agent_shared` instead.

## 3. Pass it to the model

```python
GUARDRAIL_CONFIG = {
    "guardrailIdentifier": settings.guardrail_id,
    "guardrailVersion": settings.guardrail_version,
    "trace": "enabled",   # "enabled" | "enabled_full" | "disabled"; shows why it intervened
}

model = ChatBedrockConverse(
    model_id=settings.model_id,
    region_name=settings.aws_region,
    temperature=1,
    provider="anthropic",
    guardrail_config=GUARDRAIL_CONFIG,
    # guard_last_turn_only=True,  # optional: only check the newest user turn, not the whole history
)
```

`opus_model` can use the same config, or a stricter guardrail of its own.

**Don't leave `guardrail_config={}` as it is now.** An empty dict may be sent as an empty `guardrailConfig`, which Bedrock would reject because `guardrailIdentifier` is required. Use `None` (or leave the parameter out) until the guardrail exists.

## 4. Handle blocked requests

When the guardrail blocks something, the call doesn't raise an error. It returns your "blocked" message as normal text:

```python
response = model.invoke(messages)
if response.response_metadata.get("stopReason") == "guardrail_intervened":
    logger.warning("Guardrail intervened: %s", response.response_metadata.get("trace"))
    # e.g. end the graph and return a safe message to the caller
```

This matters for your gatherer and reviewer nodes, which use `with_structured_output(...)`. If the guardrail blocks one of their calls, the model returns the blocked text instead of the structured result, and parsing fails. Catch that in those nodes, or give them a separate model with no guardrail and only guard the drafter.

## 5. IAM permission

The AgentCore runtime role (`AgentRuntimeRole`) needs `bedrock:ApplyGuardrail` on the guardrail's ARN. Without it, the model calls will fail with AccessDenied after you deploy.

**Separate bug:** `opus_model` at [main.py:73](agents/mail-drafter/src/mail_drafter/main.py#L73) uses `settings.model_id`, not `settings.opus_model_id`. As written, the reviewer runs on the same model as the drafter rather than Opus.

I can apply steps 2–4 when you have the guardrail ID, including the `stopReason` handling in the structured-output nodes and the `opus_model` fix.