import json
import os
import time
import urllib.request
from pathlib import Path

import boto3
from botocore.config import Config


def main():
    session = boto3.Session(region_name="ap-southeast-1")
    if session.client("sts").get_caller_identity()["Account"] != "524097108092":
        raise RuntimeError("Unexpected AWS account.")
    function = "bizzybee-poc-backend"
    image = os.environ["IMAGE_URI"]
    if not image.startswith("524097108092.dkr.ecr.ap-southeast-1.amazonaws.com/bizzybee-poc-backend@sha256:"):
        raise RuntimeError("Expected an immutable image in the approved ECR repository.")
    client = session.client("lambda", config=Config(connect_timeout=3, read_timeout=35, retries={"total_max_attempts": 2}))
    previous = client.get_alias(FunctionName=function, Name="live")
    metadata = {"backend_commit": os.environ["GITHUB_SHA"], "image": image, "previous_version": previous["FunctionVersion"],
        "dataset": json.loads(Path("docker/data-manifest.json").read_text()), "frontend_commit": os.environ["FRONTEND_COMMIT"]}
    Path("release.json").write_text(json.dumps(metadata, indent=2))
    config = client.get_function_configuration(FunctionName=function)
    client.update_function_code(FunctionName=function, ImageUri=image, RevisionId=config["RevisionId"])
    client.get_waiter("function_updated_v2").wait(FunctionName=function, WaiterConfig={"Delay": 5, "MaxAttempts": 60})
    config = client.get_function_configuration(FunctionName=function)
    version = client.publish_version(FunctionName=function, CodeSha256=config["CodeSha256"], RevisionId=config["RevisionId"])["Version"]
    metadata.update(version=version, model_id=config["Environment"]["Variables"].get("BEDROCK_MODEL_ID"), provider=config["Environment"]["Variables"].get("BIZZY_MODEL_PROVIDER"))
    Path("release.json").write_text(json.dumps(metadata, indent=2))
    event = {"version": "2.0", "rawPath": "/ready", "rawQueryString": "", "headers": {"host": "localhost"},
        "requestContext": {"http": {"method": "GET", "path": "/ready", "sourceIp": "127.0.0.1"}}, "isBase64Encoded": False}
    result = client.invoke(FunctionName=function, Qualifier=version, Payload=json.dumps(event).encode())
    if "FunctionError" in result or json.loads(result["Payload"].read()).get("statusCode") != 200:
        raise RuntimeError("Candidate readiness failed; live alias unchanged.")
    updated = client.update_alias(FunctionName=function, Name="live", FunctionVersion=version, RevisionId=previous["RevisionId"])
    try:
        for attempt in range(5):
            with urllib.request.urlopen(os.environ["API_ORIGIN"] + "/ready", timeout=15) as response:
                if json.load(response).get("status") != "ready":
                    raise RuntimeError("Public readiness failed.")
            time.sleep(1)
    except Exception:
        client.update_alias(FunctionName=function, Name="live", FunctionVersion=previous["FunctionVersion"], RevisionId=updated["RevisionId"])
        raise
    print(f"Deployed version {version}; rollback version {previous['FunctionVersion']} recorded.")


if __name__ == "__main__":
    main()
