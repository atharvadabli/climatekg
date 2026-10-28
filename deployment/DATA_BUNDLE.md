# Serving data bundle

The code repository does not contain the indexed graph or map assets. The
current serving bundle is built from the 115-paper index and includes the
Parquet graph, GraphRAG and Plain RAG indexes, the watershed GeoJSON, and the
Koppen KMZ. It does not include PDF files, Ollama weights, or credentials.
ClimateKG is an indexed graph, not a separately fine-tuned language model;
Ollama downloads the required Qwen weights during deployment.

**Keep this bundle private until source-text redistribution rights are
reviewed.** `source_blocks.parquet` and the baseline corpus contain passages
from published papers. Public availability of a PDF does not by itself grant
permission to republish its text.

## Build and check

From the code repository root, with Python 3.11 or newer:

```bash
python scripts/package_serving_data.py \
  /path/to/three_system_benchmark \
  /path/to/assets \
  /path/to/climatekg-serving-v1.zip
sha256sum -c /path/to/climatekg-serving-v1.zip.sha256
unzip -t /path/to/climatekg-serving-v1.zip
```

The bundle contains `data/` and `assets/` at its root. Extract it under
`/srv/climatekg` on the Linux server:

```bash
sudo unzip /path/to/climatekg-serving-v1.zip -d /srv/climatekg
```

Check `/srv/climatekg/data/parquet_graph/manifest.json` and the two files in
`/srv/climatekg/assets/` before starting Compose. Do not put credentials in
the archive.

## Private Hugging Face dataset

A private Hugging Face dataset is suitable for the 526 MB bundle. The account
that owns it must first authenticate with `hf auth login`. Replace `<OWNER>`
with that account's user or organization name:

```bash
hf repos create <OWNER>/climatekg-serving-v1 --repo-type dataset --private
hf upload <OWNER>/climatekg-serving-v1 /path/to/climatekg-serving-v1.zip --repo-type dataset
hf upload <OWNER>/climatekg-serving-v1 /path/to/climatekg-serving-v1.zip.sha256 --repo-type dataset
```

On a new Linux server, authenticate with a read-only token authorized for
that private dataset. Download both files and verify before extracting:

```bash
hf auth login
hf download <OWNER>/climatekg-serving-v1 \
  climatekg-serving-v1.zip climatekg-serving-v1.zip.sha256 \
  --repo-type dataset --local-dir /tmp/climatekg-bundle
cd /tmp/climatekg-bundle
sha256sum -c climatekg-serving-v1.zip.sha256
sudo unzip climatekg-serving-v1.zip -d /srv/climatekg
```

The current bundle has **not** been uploaded. Do not put a Hugging Face token
in `.env`, Git, or a container image. The server only needs the extracted
files; it does not need Hugging Face credentials after installation.
