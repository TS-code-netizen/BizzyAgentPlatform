import json
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError


def main():
    session = boto3.Session(region_name="ap-southeast-1")
    identity = session.client("sts").get_caller_identity()
    if identity["Account"] != "524097108092":
        raise RuntimeError("Unexpected AWS account; refusing discovery.")
    print(json.dumps({"account": identity["Account"], "caller": identity["Arn"]}))
    bedrock = session.client("bedrock")
    for profile in bedrock.list_inference_profiles()["inferenceProfileSummaries"]:
        if "nova-micro" in profile["inferenceProfileId"]:
            print(json.dumps({"profile": profile["inferenceProfileId"], "arn": profile["inferenceProfileArn"], "models": profile["models"]}))
    try:
        print(json.dumps({"availability": bedrock.get_foundation_model_availability(modelId="amazon.nova-micro-v1:0")} , default=str))
    except ClientError as exc:
        print(json.dumps({"availability_error": exc.response["Error"]["Code"]}))
    budgets = session.client("budgets")
    budget = budgets.describe_budget(AccountId=identity["Account"], BudgetName="My Monthly Cost Budget")["Budget"]
    print(json.dumps({"budget": budget}, default=str))
    now = datetime.now(timezone.utc)
    result = session.client("ce", region_name="us-east-1").get_cost_and_usage(
        TimePeriod={"Start": now.strftime("%Y-%m-01"), "End": now.strftime("%Y-%m-%d")},
        Granularity="MONTHLY", Metrics=["UnblendedCost"], GroupBy=[{"Type": "DIMENSION", "Key": "RECORD_TYPE"}],
    )
    print(json.dumps({"cost_by_record_type": result["ResultsByTime"]}, default=str))


if __name__ == "__main__":
    main()
