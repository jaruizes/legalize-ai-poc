#!/usr/bin/env python3
"""Run the enricher Lambda locally using the test_event.json fixture (S3 mocked via moto)."""

import json
import os
import boto3
from moto import mock_aws

os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_DEFAULT_REGION"] = "eu-west-1"

with open("test_event.json") as f:
    event = json.load(f)

BUCKET = event["bucketName"]

# Sample chunk batches that Bedrock would have written after CHUNKING
SAMPLE_BATCHES = {
    "aws/bedrock/knowledge_bases/XPTBIZ5WPT/LVJLXLGMHV/TAEUE4ZXF6/tr_technology_radar_vol_33_en_1.JSON": {
        "version": "1.0",
        "chunks": [
            {
                "content": {"type": "TEXT", "text": "Adopt. Terraform has become the dominant infrastructure-as-code tool across the industry."},
                "metadata": {"attributes": [{"key": "x-amz-bedrock-kb-source-uri", "value": "s3://data-bucket/tr_technology_radar_vol_33_en.pdf", "type": "STRING"}]},
            },
            {
                "content": {"type": "TEXT", "text": "Trial. Platform engineering reduces cognitive load for development teams."},
                "metadata": {"attributes": []},
            },
        ],
    },
    "aws/bedrock/knowledge_bases/XPTBIZ5WPT/LVJLXLGMHV/TAEUE4ZXF6/tr_technology_radar_vol_33_en_2.JSON": {
        "version": "1.0",
        "chunks": [
            {
                "content": {"type": "TEXT", "text": "Hold. Vendor-specific Kubernetes distributions add unnecessary complexity."},
                "metadata": {"attributes": []},
            }
        ],
    },
}


@mock_aws
def run():
    # Create mock S3 bucket and upload sample batch files
    s3 = boto3.client("s3", region_name="eu-west-1")
    s3.create_bucket(
        Bucket=BUCKET,
        CreateBucketConfiguration={"LocationConstraint": "eu-west-1"},
    )
    for key, content in SAMPLE_BATCHES.items():
        s3.put_object(Bucket=BUCKET, Key=key, Body=json.dumps(content))

    print("Testing enricher Lambda handler locally (S3 mocked via moto)...\n")
    print(f"Input files:  {len(event['inputFiles'])}")
    print(f"Input batches: {sum(len(f['contentBatches']) for f in event['inputFiles'])}\n")

    from handler import lambda_handler
    result = lambda_handler(event, None)

    print(f"\nResponse version: {result['version']}")
    print(f"Output files:    {len(result['outputFiles'])}")

    for i, out_file in enumerate(result["outputFiles"]):
        print(f"\n  File {i + 1}: {out_file['originalFileLocation']['s3_location']['uri']}")
        for j, batch in enumerate(out_file["contentBatches"]):
            output_key = batch["key"]
            obj = s3.get_object(Bucket=BUCKET, Key=output_key)
            data = json.loads(obj["Body"].read())
            print(f"    Batch {j + 1} ({output_key}):")
            for k, chunk in enumerate(data["chunkList"]):
                attrs = chunk["metadata"]["metadataAttributes"]
                text = chunk["content"]["text"][:70] + "..." if len(chunk["content"]["text"]) > 70 else chunk["content"]["text"]
                print(f"      Chunk {k + 1}: year={attrs.get('year')} volume={attrs.get('volume')} | {text}")

    # Verify Bedrock contract
    assert "outputFiles" in result
    assert "version" not in result, "top-level 'version' is not part of the output schema"
    for out_file in result["outputFiles"]:
        for batch in out_file["contentBatches"]:
            obj = s3.get_object(Bucket=BUCKET, Key=batch["key"])
            data = json.loads(obj["Body"].read())
            assert "chunkList" in data
            assert "version" not in data, "output batch file must not have top-level 'version'"
            for chunk in data["chunkList"]:
                assert "type" not in chunk["content"], "content must not have 'type'"
                assert "metadataAttributes" in chunk["metadata"], "must use 'metadataAttributes'"
                assert "attributes" not in chunk["metadata"], "must not use 'attributes'"

    print("\nBedrock output schema contract: OK")


run()
