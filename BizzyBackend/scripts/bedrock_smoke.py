import argparse
import os

from backend.orchestration.bedrock import classify

parser = argparse.ArgumentParser(description="Paid inference smoke test; explicit external approval required.")
parser.add_argument("--approved-paid-inference", action="store_true", required=True)
parser.parse_args()
if os.getenv("BIZZY_MODEL_PROVIDER") != "bedrock" or not os.getenv("BEDROCK_MODEL_ID"):
    raise RuntimeError("Set the explicitly approved model and provider first.")
agents = classify("Which products are likely to run out of stock?")
if agents != ["inventory"]:
    raise RuntimeError(f"Unexpected routing: {agents}")
print("Approved real-inference routing smoke passed.")
