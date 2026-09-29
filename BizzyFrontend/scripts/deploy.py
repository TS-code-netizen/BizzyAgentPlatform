import json
import os
import ssl
import time
import urllib.request

import boto3
from botocore.config import Config
from botocore.httpsession import get_cert_path

session = boto3.Session(region_name="ap-southeast-1")
if session.client("sts").get_caller_identity()["Account"] != "524097108092":
    raise RuntimeError("Unexpected deployment account.")
client = session.client("amplify", config=Config(connect_timeout=3, read_timeout=30, retries={"total_max_attempts": 2}))
app = os.environ["AMPLIFY_APP_ID"]
job = client.create_deployment(appId=app, branchName="poc")
with open("frontend.zip", "rb") as archive:
    request = urllib.request.Request(job["zipUploadUrl"], data=archive.read(), method="PUT", headers={"Content-Type": "application/zip"})
    tls_context = ssl.create_default_context(cafile=os.environ.get("AWS_CA_BUNDLE") or get_cert_path(True))
    with urllib.request.urlopen(request, timeout=90, context=tls_context) as response:
        if response.status != 200:
            raise RuntimeError("Frontend upload failed.")
client.start_deployment(appId=app, branchName="poc", jobId=job["jobId"])
for attempt in range(60):
    status = client.get_job(appId=app, branchName="poc", jobId=job["jobId"])["job"]["summary"]["status"]
    if status == "SUCCEED":
        print(json.dumps({"app_id": app, "job_id": job["jobId"], "commit": os.environ["GITHUB_SHA"]}))
        break
    if status in {"FAILED", "CANCELLED"}:
        raise RuntimeError(f"Amplify deployment {status}.")
    time.sleep(10)
else:
    raise TimeoutError("Amplify did not finish within ten minutes; inspect the job before retrying.")
