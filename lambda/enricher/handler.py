import json
import re
import boto3

s3_client = boto3.client('s3')

# ── Volume → edition lookup ────────────────────────────────────────────────────
# Add new volumes here as they are published.
VOLUME_EDITIONS = {
    "1":  {"year": "1995", "month": "01", "edition": "1995"},
    "31": {"year": "2024", "month": "10", "edition": "Oct 2024"},
    "32": {"year": "2025", "month": "04", "edition": "Apr 2025"},
    "33": {"year": "2025", "month": "11", "edition": "Nov 2025"},
    "34": {"year": "2026", "month": "04", "edition": "Apr 2026"},
}

KNOWN_RINGS = {"Adopt", "Trial", "Assess", "Hold", "Caution"}

KNOWN_QUADRANTS = {
    "Techniques",
    "Platforms",
    "Tools",
    "Languages and Frameworks",
}

# Lines to strip before parsing (copyright, page numbers, etc.)
_SKIP_LINE_RE = re.compile(
    r'^©|^All Rights Reserved|^Thoughtworks|^\d+$'
)

# Blip entry: "42. Bruno" or "7 7. CAP" (OCR sometimes inserts a space)
_BLIP_LINE_RE = re.compile(r'^\d[\d ]*\.\s+(.+)$')


def lambda_handler(event, context):
    print(f"Event received: {json.dumps(event)}")

    bucket_name = event['bucketName']
    input_files = event.get('inputFiles', [])
    output_files = []

    for input_file in input_files:
        original_location = input_file.get('originalFileLocation', {})
        source_uri = original_location.get('s3_location', {}).get('uri', '')
        volume = _extract_volume(source_uri)
        edition_info = VOLUME_EDITIONS.get(volume, {})
        year    = edition_info.get("year",    "unknown")
        month   = edition_info.get("month",   "unknown")
        edition = edition_info.get("edition", f"vol-{volume}" if volume != "unknown" else "unknown")

        print(f"File: {source_uri} -> volume={volume}, year={year}, edition={edition}")

        output_batches = []

        for batch in input_file.get('contentBatches', []):
            input_key = batch['key']
            print(f"Reading batch: s3://{bucket_name}/{input_key}")

            obj = s3_client.get_object(Bucket=bucket_name, Key=input_key)
            raw = obj['Body'].read().decode('utf-8')
            batch_data = json.loads(raw)

            _enrich_batch_in_place(batch_data, volume, year, month, edition)

            output_key = _output_key(input_key)
            output_body = json.dumps(batch_data)
            s3_client.put_object(
                Bucket=bucket_name,
                Key=output_key,
                Body=output_body,
                ContentType='application/json',
            )
            print(f"Written to s3://{bucket_name}/{output_key}")
            output_batches.append({"key": output_key})

        output_files.append({
            "originalFileLocation": input_file['originalFileLocation'],
            "fileMetadata": {
                "volume":  volume,
                "year":    year,
                "month":   month,
                "edition": edition,
            },
            "contentBatches": output_batches,
        })

    response = {"outputFiles": output_files}
    print(f"Response: {json.dumps(response)}")
    return response


# ── Batch / chunk enrichment ───────────────────────────────────────────────────

def _enrich_batch_in_place(batch_data, volume, year, month, edition):
    for key in ('chunks', 'chunkList'):
        chunks = batch_data.get(key)
        if chunks is not None:
            for chunk in chunks:
                _enrich_chunk_in_place(chunk, volume, year, month, edition)
            return


def _enrich_chunk_in_place(chunk, volume, year, month, edition):
    text = chunk.get('content', {}).get('text', '')
    parsed = _parse_chunk_text(text)

    new_attrs = {
        "volume":     volume,
        "year":       year,
        "month":      month,
        "edition":    edition,
        "ring":       parsed["ring"],
        "blip_name":  parsed["blip_name"],
        "quadrant":   parsed["quadrant"],
        "processed_by": "advanced-rag-enricher",
    }

    metadata = chunk.setdefault('metadata', {})
    attrs = metadata.get('attributes')

    if isinstance(attrs, list):
        existing_keys = {a.get('key') for a in attrs}
        for k, v in new_attrs.items():
            if k not in existing_keys:
                attrs.append({"key": k, "value": v, "type": "STRING"})
    elif isinstance(attrs, dict):
        for k, v in new_attrs.items():
            attrs.setdefault(k, v)
    else:
        metadata['attributes'] = [
            {"key": k, "value": v, "type": "STRING"}
            for k, v in new_attrs.items()
        ]


# ── Text parsing ───────────────────────────────────────────────────────────────

def _parse_chunk_text(text):
    """Extract ring, blip_name and quadrant from a chunk's plain text."""
    result = {"ring": "unknown", "blip_name": "unknown", "quadrant": "unknown"}
    if not text:
        return result

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    clean = [l for l in lines if not _SKIP_LINE_RE.match(l)]

    # Quadrant: present when a section starts (first blip page of that section)
    # Also handle "Languages and \nFrameworks" which may be split across lines.
    full_text = ' '.join(clean)
    if "Languages and Frameworks" in full_text or "Languages and \nFrameworks" in text:
        result["quadrant"] = "Languages and Frameworks"
    else:
        for line in clean:
            if line in KNOWN_QUADRANTS:
                result["quadrant"] = line
                break

    # Blip name: first line matching "N. Name" pattern
    for line in clean:
        m = _BLIP_LINE_RE.match(line)
        if m:
            result["blip_name"] = m.group(1).strip()
            break

    # Ring: first line that is exactly a ring keyword
    for line in clean:
        if line in KNOWN_RINGS:
            result["ring"] = line
            break

    return result


# ── Filename helpers ───────────────────────────────────────────────────────────

def _extract_volume(source_uri):
    """Extract volume number string from a Radar S3 URI, e.g. 'tr_technology_radar_vol_33_en.pdf' -> '33'."""
    if not source_uri:
        return "unknown"
    filename = source_uri.split('/')[-1]
    m = re.search(r'vol_?(\d+)', filename, re.IGNORECASE)
    return m.group(1) if m else "unknown"


def _output_key(input_key):
    """Derive the output S3 key by inserting an 'output/' directory segment."""
    parts = input_key.rsplit('/', 1)
    if len(parts) == 2:
        return f"{parts[0]}/output/{parts[1]}"
    return f"output/{input_key}"
