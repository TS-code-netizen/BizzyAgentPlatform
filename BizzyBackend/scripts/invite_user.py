import argparse

import boto3
from botocore.exceptions import ClientError

parser = argparse.ArgumentParser(description="Send an approved Cognito invitation; never prints passwords.")
parser.add_argument("--pool-id", required=True)
parser.add_argument("--email", required=True)
parser.add_argument("--approver", action="store_true")
parser.add_argument("--execute-approved-invitation", action="store_true", required=True)
args = parser.parse_args()
session = boto3.Session(region_name="ap-southeast-1")
if session.client("sts").get_caller_identity()["Account"] != "524097108092":
    raise RuntimeError("Unexpected AWS account.")
client = session.client("cognito-idp")
pool = client.describe_user_pool(UserPoolId=args.pool_id)["UserPool"]
if pool["Name"] != "bizzybee-poc":
    raise RuntimeError("Unexpected user pool.")
try:
    user = client.admin_get_user(UserPoolId=args.pool_id, Username=args.email)
    username = user["Username"]
except ClientError as exc:
    if exc.response["Error"]["Code"] != "UserNotFoundException":
        raise
    created = client.admin_create_user(UserPoolId=args.pool_id, Username=args.email,
        UserAttributes=[{"Name": "email", "Value": args.email}], DesiredDeliveryMediums=["EMAIL"])
    username = created["User"]["Username"]
if args.approver:
    client.admin_add_user_to_group(UserPoolId=args.pool_id, Username=username, GroupName="approvers")
print("User exists; requested group assignment complete. No credentials displayed.")
