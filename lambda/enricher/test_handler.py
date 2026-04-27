"""
Unit and integration tests for the Bedrock KB enricher Lambda.

Uses moto to mock S3 so no real AWS credentials are required.
"""

import json
import os
import pytest
import boto3
from moto import mock_aws

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BUCKET = "test-temp-bucket"
KB_ID = "TESTKB123"
DS_ID = "TESTDS456"
JOB_ID = "TESTJOB789"
BASE_PREFIX = f"aws/bedrock/knowledge_bases/{KB_ID}/{DS_ID}/{JOB_ID}"

ORIGINAL_URI_V33 = "s3://data-bucket/tr_technology_radar_vol_33_en.pdf"
ORIGINAL_URI_V31 = "s3://data-bucket/tr_technology_radar_vol_31_en.pdf"

BATCH_1_KEY = f"{BASE_PREFIX}/tr_technology_radar_vol_33_en_1.JSON"
BATCH_2_KEY = f"{BASE_PREFIX}/tr_technology_radar_vol_33_en_2.JSON"

# ---------------------------------------------------------------------------
# Sample chunk texts that mimic real Bedrock-extracted PDF content
# ---------------------------------------------------------------------------

TEXT_BLIP_RAG = (
    "© Thoughtworks, Inc. All Rights Reserved.\n"
    "13\n"
    "4. Retrieval-augmented generation (RAG)\n"
    "Adopt\n"
    "Retrieval-augmented generation (RAG) is the preferred pattern for our teams."
)

TEXT_BLIP_WITH_QUADRANT = (
    "© Thoughtworks, Inc. All Rights Reserved.\n"
    "12\n"
    "Techniques\n"
    "1. 1% canary\n"
    "Adopt\n"
    "For many years, we've used the canary release approach."
)

TEXT_BLIP_LF = (
    "© Thoughtworks, Inc. All Rights Reserved.\n"
    "37\n"
    "Languages and \nFrameworks\n"
    "75. dbt\n"
    "Adopt\n"
    "We continue to see dbt as a strong option for ELT pipelines."
)

TEXT_BLIP_PLATFORMS = (
    "© Thoughtworks, Inc. All Rights Reserved.\n"
    "21\n"
    "Platforms\n"
    "24. Databricks Unity Catalog\n"
    "Trial\n"
    "Databricks Unity Catalog is a data governance solution."
)

TEXT_THEME = (
    "© Thoughtworks, Inc. All Rights Reserved.\n"
    "6\n"
    "Coding assistance antipatterns\n"
    "To the surprise of no one, generative AI and LLMs dominated our conversations."
)

TEXT_TOOLS_BLIP = (
    "© Thoughtworks, Inc. All Rights Reserved.\n"
    "27\n"
    "Tools\n"
    "42. Bruno\n"
    "Adopt\n"
    "Bruno is an open-source desktop alternative to Postman."
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _batch(chunks, wrapper_key="chunks"):
    return json.dumps({"version": "1.0", wrapper_key: chunks}).encode()


def _chunk(text, attributes=None):
    return {
        "content": {"type": "TEXT", "text": text},
        "metadata": {"attributes": attributes or []},
    }


def _attr(key, value):
    return {"key": key, "value": value, "type": "STRING"}


def _event(bucket=BUCKET, batches=None, original_uri=ORIGINAL_URI_V33):
    batches = batches or [{"key": BATCH_1_KEY}]
    return {
        "version": "1.0",
        "bucketName": bucket,
        "knowledgeBaseId": KB_ID,
        "dataSourceId": DS_ID,
        "ingestionJobId": JOB_ID,
        "priorTask": "CHUNKING",
        "inputFiles": [
            {
                "contentBatches": batches,
                "originalFileLocation": {
                    "type": "S3",
                    "s3_location": {"uri": original_uri},
                },
            }
        ],
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def aws_credentials(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-1")


@pytest.fixture()
def s3(aws_credentials):
    with mock_aws():
        client = boto3.client("s3", region_name="eu-west-1")
        client.create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={"LocationConstraint": "eu-west-1"},
        )
        yield client


def _put_batch(s3_client, key, chunks, wrapper_key="chunks"):
    s3_client.put_object(Bucket=BUCKET, Key=key, Body=_batch(chunks, wrapper_key))


def _read_output(s3_client, input_key):
    from handler import _output_key
    obj = s3_client.get_object(Bucket=BUCKET, Key=_output_key(input_key))
    return json.loads(obj["Body"].read().decode())


def _output_attrs(s3_client, input_key, chunk_index=0):
    data = _read_output(s3_client, input_key)
    chunks = data.get("chunks") or data.get("chunkList") or []
    return chunks[chunk_index]["metadata"]["attributes"]


def _attr_value(attrs, key):
    if isinstance(attrs, list):
        for a in attrs:
            if a.get("key") == key:
                return a.get("value")
        return None
    return attrs.get(key)


# ---------------------------------------------------------------------------
# Lambda response schema (Bedrock contract)
# ---------------------------------------------------------------------------

def test_response_has_outputFiles_only(s3):
    _put_batch(s3, BATCH_1_KEY, [_chunk("Some text")])
    with mock_aws():
        from handler import lambda_handler
        result = lambda_handler(_event(), None)
    assert "outputFiles" in result
    assert "version" not in result, "top-level 'version' must not be in the Lambda response"


def test_response_outputFiles_structure(s3):
    _put_batch(s3, BATCH_1_KEY, [_chunk("Text")])
    with mock_aws():
        from handler import lambda_handler
        result = lambda_handler(_event(), None)
    out_file = result["outputFiles"][0]
    assert "originalFileLocation" in out_file
    assert "fileMetadata" in out_file
    assert "contentBatches" in out_file
    assert out_file["originalFileLocation"]["s3_location"]["uri"] == ORIGINAL_URI_V33


def test_fileMetadata_fields(s3):
    """fileMetadata must contain volume, year, month, edition."""
    _put_batch(s3, BATCH_1_KEY, [_chunk("Text")])
    with mock_aws():
        from handler import lambda_handler
        result = lambda_handler(_event(original_uri=ORIGINAL_URI_V33), None)
    fm = result["outputFiles"][0]["fileMetadata"]
    assert fm["volume"] == "33"
    assert fm["year"] == "2025"
    assert fm["month"] == "11"
    assert fm["edition"] == "Nov 2025"


def test_fileMetadata_vol31(s3):
    _put_batch(s3, BATCH_1_KEY, [_chunk("Text")])
    with mock_aws():
        from handler import lambda_handler
        result = lambda_handler(_event(original_uri=ORIGINAL_URI_V31), None)
    fm = result["outputFiles"][0]["fileMetadata"]
    assert fm["volume"] == "31"
    assert fm["year"] == "2024"
    assert fm["edition"] == "Oct 2024"


def test_output_batch_count_matches_input(s3):
    _put_batch(s3, BATCH_1_KEY, [_chunk("A")])
    _put_batch(s3, BATCH_2_KEY, [_chunk("B")])
    with mock_aws():
        from handler import lambda_handler
        result = lambda_handler(_event(batches=[{"key": BATCH_1_KEY}, {"key": BATCH_2_KEY}]), None)
    assert len(result["outputFiles"][0]["contentBatches"]) == 2


# ---------------------------------------------------------------------------
# Output key naming
# ---------------------------------------------------------------------------

def test_output_key_inserts_output_subdirectory():
    from handler import _output_key
    assert _output_key(f"{BASE_PREFIX}/file_1.JSON") == f"{BASE_PREFIX}/output/file_1.JSON"


def test_output_key_fallback_for_flat_key():
    from handler import _output_key
    assert _output_key("file.JSON") == "output/file.JSON"


# ---------------------------------------------------------------------------
# Pass-through: input structure preserved in output
# ---------------------------------------------------------------------------

def test_output_preserves_top_level_structure(s3):
    _put_batch(s3, BATCH_1_KEY, [_chunk("Text")])
    with mock_aws():
        from handler import lambda_handler
        lambda_handler(_event(), None)
    data = _read_output(s3, BATCH_1_KEY)
    assert "version" in data
    assert "chunks" in data


def test_output_preserves_chunk_text(s3):
    text = "Adopt. Terraform is the dominant IaC tool."
    _put_batch(s3, BATCH_1_KEY, [_chunk(text)])
    with mock_aws():
        from handler import lambda_handler
        lambda_handler(_event(), None)
    data = _read_output(s3, BATCH_1_KEY)
    chunks = data.get("chunks") or data.get("chunkList")
    assert chunks[0]["content"]["text"] == text


def test_output_preserves_content_type_field(s3):
    _put_batch(s3, BATCH_1_KEY, [_chunk("Text")])
    with mock_aws():
        from handler import lambda_handler
        lambda_handler(_event(), None)
    data = _read_output(s3, BATCH_1_KEY)
    chunks = data.get("chunks") or data.get("chunkList")
    assert chunks[0]["content"].get("type") == "TEXT"


def test_handles_chunkList_key(s3):
    _put_batch(s3, BATCH_1_KEY, [_chunk("Text")], wrapper_key="chunkList")
    with mock_aws():
        from handler import lambda_handler
        lambda_handler(_event(), None)
    data = _read_output(s3, BATCH_1_KEY)
    assert "chunkList" in data


# ---------------------------------------------------------------------------
# Metadata enrichment — core fields
# ---------------------------------------------------------------------------

def test_year_added_from_volume_lookup(s3):
    _put_batch(s3, BATCH_1_KEY, [_chunk("Text")])
    with mock_aws():
        from handler import lambda_handler
        lambda_handler(_event(original_uri=ORIGINAL_URI_V33), None)
    assert _attr_value(_output_attrs(s3, BATCH_1_KEY), "year") == "2025"


def test_edition_added_from_volume_lookup(s3):
    _put_batch(s3, BATCH_1_KEY, [_chunk("Text")])
    with mock_aws():
        from handler import lambda_handler
        lambda_handler(_event(original_uri=ORIGINAL_URI_V33), None)
    assert _attr_value(_output_attrs(s3, BATCH_1_KEY), "edition") == "Nov 2025"


def test_volume_added_to_chunk_attributes(s3):
    _put_batch(s3, BATCH_1_KEY, [_chunk("Text")])
    with mock_aws():
        from handler import lambda_handler
        lambda_handler(_event(original_uri=ORIGINAL_URI_V33), None)
    assert _attr_value(_output_attrs(s3, BATCH_1_KEY), "volume") == "33"


def test_processed_by_added(s3):
    _put_batch(s3, BATCH_1_KEY, [_chunk("Text")])
    with mock_aws():
        from handler import lambda_handler
        lambda_handler(_event(), None)
    assert _attr_value(_output_attrs(s3, BATCH_1_KEY), "processed_by") == "advanced-rag-enricher"


def test_unknown_volume_and_year_for_unrecognised_file(s3):
    _put_batch(s3, BATCH_1_KEY, [_chunk("Text")])
    with mock_aws():
        from handler import lambda_handler
        lambda_handler(_event(original_uri="s3://b/some_document.pdf"), None)
    attrs = _output_attrs(s3, BATCH_1_KEY)
    assert _attr_value(attrs, "volume") == "unknown"
    assert _attr_value(attrs, "year") == "unknown"


def test_volume_extraction_case_insensitive(s3):
    _put_batch(s3, BATCH_1_KEY, [_chunk("Text")])
    with mock_aws():
        from handler import lambda_handler
        lambda_handler(_event(original_uri="s3://b/radar_VOL_29.pdf"), None)
    assert _attr_value(_output_attrs(s3, BATCH_1_KEY), "volume") == "29"


def test_volume_extraction_without_separator(s3):
    _put_batch(s3, BATCH_1_KEY, [_chunk("Text")])
    with mock_aws():
        from handler import lambda_handler
        lambda_handler(_event(original_uri="s3://b/radar_vol31.pdf"), None)
    assert _attr_value(_output_attrs(s3, BATCH_1_KEY), "volume") == "31"


def test_existing_attributes_preserved(s3):
    chunk = _chunk("Text", attributes=[_attr("custom", "radar")])
    _put_batch(s3, BATCH_1_KEY, [chunk])
    with mock_aws():
        from handler import lambda_handler
        lambda_handler(_event(), None)
    assert _attr_value(_output_attrs(s3, BATCH_1_KEY), "custom") == "radar"


def test_enrichment_does_not_duplicate_existing_key(s3):
    chunk = _chunk("Text", attributes=[_attr("year", "1999")])
    _put_batch(s3, BATCH_1_KEY, [chunk])
    with mock_aws():
        from handler import lambda_handler
        lambda_handler(_event(original_uri=ORIGINAL_URI_V33), None)
    attrs = _output_attrs(s3, BATCH_1_KEY)
    year_entries = [a for a in attrs if a.get("key") == "year"]
    assert len(year_entries) == 1
    assert year_entries[0]["value"] == "1999"  # original value kept


def test_all_chunks_enriched_with_same_edition(s3):
    _put_batch(s3, BATCH_1_KEY, [_chunk("A"), _chunk("B")])
    with mock_aws():
        from handler import lambda_handler
        lambda_handler(_event(original_uri=ORIGINAL_URI_V33), None)
    for i in range(2):
        attrs = _output_attrs(s3, BATCH_1_KEY, chunk_index=i)
        assert _attr_value(attrs, "year") == "2025"
        assert _attr_value(attrs, "volume") == "33"
        assert _attr_value(attrs, "edition") == "Nov 2025"


# ---------------------------------------------------------------------------
# Metadata enrichment — ring, blip_name, quadrant
# ---------------------------------------------------------------------------

def test_ring_extracted_from_blip_chunk(s3):
    _put_batch(s3, BATCH_1_KEY, [_chunk(TEXT_BLIP_RAG)])
    with mock_aws():
        from handler import lambda_handler
        lambda_handler(_event(), None)
    assert _attr_value(_output_attrs(s3, BATCH_1_KEY), "ring") == "Adopt"


def test_blip_name_extracted_from_blip_chunk(s3):
    _put_batch(s3, BATCH_1_KEY, [_chunk(TEXT_BLIP_RAG)])
    with mock_aws():
        from handler import lambda_handler
        lambda_handler(_event(), None)
    val = _attr_value(_output_attrs(s3, BATCH_1_KEY), "blip_name")
    assert "Retrieval-augmented generation" in val


def test_ring_trial_extracted(s3):
    _put_batch(s3, BATCH_1_KEY, [_chunk(TEXT_BLIP_PLATFORMS)])
    with mock_aws():
        from handler import lambda_handler
        lambda_handler(_event(), None)
    assert _attr_value(_output_attrs(s3, BATCH_1_KEY), "ring") == "Trial"


def test_quadrant_techniques_extracted(s3):
    _put_batch(s3, BATCH_1_KEY, [_chunk(TEXT_BLIP_WITH_QUADRANT)])
    with mock_aws():
        from handler import lambda_handler
        lambda_handler(_event(), None)
    assert _attr_value(_output_attrs(s3, BATCH_1_KEY), "quadrant") == "Techniques"


def test_quadrant_platforms_extracted(s3):
    _put_batch(s3, BATCH_1_KEY, [_chunk(TEXT_BLIP_PLATFORMS)])
    with mock_aws():
        from handler import lambda_handler
        lambda_handler(_event(), None)
    assert _attr_value(_output_attrs(s3, BATCH_1_KEY), "quadrant") == "Platforms"


def test_quadrant_tools_extracted(s3):
    _put_batch(s3, BATCH_1_KEY, [_chunk(TEXT_TOOLS_BLIP)])
    with mock_aws():
        from handler import lambda_handler
        lambda_handler(_event(), None)
    assert _attr_value(_output_attrs(s3, BATCH_1_KEY), "quadrant") == "Tools"


def test_quadrant_languages_and_frameworks_extracted(s3):
    _put_batch(s3, BATCH_1_KEY, [_chunk(TEXT_BLIP_LF)])
    with mock_aws():
        from handler import lambda_handler
        lambda_handler(_event(), None)
    assert _attr_value(_output_attrs(s3, BATCH_1_KEY), "quadrant") == "Languages and Frameworks"


def test_quadrant_unknown_when_not_in_text(s3):
    """A blip page without a section header has quadrant=unknown."""
    _put_batch(s3, BATCH_1_KEY, [_chunk(TEXT_BLIP_RAG)])
    with mock_aws():
        from handler import lambda_handler
        lambda_handler(_event(), None)
    assert _attr_value(_output_attrs(s3, BATCH_1_KEY), "quadrant") == "unknown"


def test_ring_unknown_for_non_blip_chunk(s3):
    _put_batch(s3, BATCH_1_KEY, [_chunk(TEXT_THEME)])
    with mock_aws():
        from handler import lambda_handler
        lambda_handler(_event(), None)
    assert _attr_value(_output_attrs(s3, BATCH_1_KEY), "ring") == "unknown"


def test_blip_name_unknown_for_theme_chunk(s3):
    _put_batch(s3, BATCH_1_KEY, [_chunk(TEXT_THEME)])
    with mock_aws():
        from handler import lambda_handler
        lambda_handler(_event(), None)
    assert _attr_value(_output_attrs(s3, BATCH_1_KEY), "blip_name") == "unknown"


# ---------------------------------------------------------------------------
# Multi-batch / empty cases
# ---------------------------------------------------------------------------

def test_empty_batch_written_to_s3(s3):
    _put_batch(s3, BATCH_1_KEY, [])
    with mock_aws():
        from handler import lambda_handler
        lambda_handler(_event(), None)
    data = _read_output(s3, BATCH_1_KEY)
    chunks = data.get("chunks") or data.get("chunkList") or []
    assert chunks == []


def test_multiple_batches_written_independently(s3):
    _put_batch(s3, BATCH_1_KEY, [_chunk("Batch 1 text")])
    _put_batch(s3, BATCH_2_KEY, [_chunk("Batch 2 text")])
    with mock_aws():
        from handler import lambda_handler
        lambda_handler(_event(batches=[{"key": BATCH_1_KEY}, {"key": BATCH_2_KEY}]), None)
    d1 = _read_output(s3, BATCH_1_KEY)
    d2 = _read_output(s3, BATCH_2_KEY)
    c1 = (d1.get("chunks") or d1.get("chunkList"))[0]
    c2 = (d2.get("chunks") or d2.get("chunkList"))[0]
    assert c1["content"]["text"] == "Batch 1 text"
    assert c2["content"]["text"] == "Batch 2 text"


# ---------------------------------------------------------------------------
# Unit tests for helpers
# ---------------------------------------------------------------------------

def test_extract_volume_standard():
    from handler import _extract_volume
    assert _extract_volume("s3://b/tr_technology_radar_vol_33_en.pdf") == "33"
    assert _extract_volume("s3://b/radar_VOL_31.pdf") == "31"
    assert _extract_volume("s3://b/radar_vol31.pdf") == "31"
    assert _extract_volume("") == "unknown"
    assert _extract_volume("s3://b/some_doc.pdf") == "unknown"


def test_parse_chunk_text_blip_with_all_fields():
    from handler import _parse_chunk_text
    result = _parse_chunk_text(TEXT_BLIP_WITH_QUADRANT)
    assert result["ring"] == "Adopt"
    assert result["blip_name"] == "1% canary"
    assert result["quadrant"] == "Techniques"


def test_parse_chunk_text_blip_no_quadrant():
    from handler import _parse_chunk_text
    result = _parse_chunk_text(TEXT_BLIP_RAG)
    assert result["ring"] == "Adopt"
    assert "Retrieval-augmented generation" in result["blip_name"]
    assert result["quadrant"] == "unknown"


def test_parse_chunk_text_lf_quadrant():
    from handler import _parse_chunk_text
    result = _parse_chunk_text(TEXT_BLIP_LF)
    assert result["quadrant"] == "Languages and Frameworks"
    assert result["blip_name"] == "dbt"
    assert result["ring"] == "Adopt"


def test_parse_chunk_text_theme():
    from handler import _parse_chunk_text
    result = _parse_chunk_text(TEXT_THEME)
    assert result["ring"] == "unknown"
    assert result["blip_name"] == "unknown"


def test_parse_chunk_text_empty():
    from handler import _parse_chunk_text
    result = _parse_chunk_text("")
    assert result == {"ring": "unknown", "blip_name": "unknown", "quadrant": "unknown"}


def test_enrich_chunk_in_place_new_signature():
    from handler import _enrich_chunk_in_place
    chunk = {"content": {"text": TEXT_BLIP_RAG}, "metadata": {"attributes": []}}
    _enrich_chunk_in_place(chunk, "33", "2025", "11", "Nov 2025")
    attrs = {a["key"]: a["value"] for a in chunk["metadata"]["attributes"]}
    assert attrs["volume"] == "33"
    assert attrs["year"] == "2025"
    assert attrs["edition"] == "Nov 2025"
    assert attrs["ring"] == "Adopt"
    assert "Retrieval-augmented generation" in attrs["blip_name"]


def test_enrich_chunk_in_place_dict_attrs():
    from handler import _enrich_chunk_in_place
    chunk = {"content": {"text": "x"}, "metadata": {"attributes": {}}}
    _enrich_chunk_in_place(chunk, "33", "2025", "11", "Nov 2025")
    attrs = chunk["metadata"]["attributes"]
    assert attrs["year"] == "2025"
    assert attrs["volume"] == "33"


def test_enrich_chunk_in_place_no_attrs():
    from handler import _enrich_chunk_in_place
    chunk = {"content": {"text": "x"}, "metadata": {}}
    _enrich_chunk_in_place(chunk, "31", "2024", "10", "Oct 2024")
    attrs = chunk["metadata"]["attributes"]
    assert isinstance(attrs, list)
    assert any(a["key"] == "year" for a in attrs)


def test_enrich_batch_in_place_chunks_key():
    from handler import _enrich_batch_in_place
    batch = {"version": "1.0", "chunks": [{"content": {"text": "t"}, "metadata": {"attributes": []}}]}
    _enrich_batch_in_place(batch, "33", "2025", "11", "Nov 2025")
    attrs = batch["chunks"][0]["metadata"]["attributes"]
    assert any(a["key"] == "volume" for a in attrs)


def test_enrich_batch_in_place_chunkList_key():
    from handler import _enrich_batch_in_place
    batch = {"version": "1.0", "chunkList": [{"content": {"text": "t"}, "metadata": {"attributes": []}}]}
    _enrich_batch_in_place(batch, "33", "2025", "11", "Nov 2025")
    attrs = batch["chunkList"][0]["metadata"]["attributes"]
    assert any(a["key"] == "volume" for a in attrs)
