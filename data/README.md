# Data layout

- `raw/` contains immutable source snapshots and is ignored by Git.
- `processed/banner/` and `processed/assist_ge/` are reproducible intermediate
  transforms and are ignored by Git.
- `processed/structured_store/` is the small published exact-data snapshot used
  by tests and Streamlit; it is versioned.
- `processed/kb/` contains reviewed, KB-ready catalog, Cal-GETC area, combined
  transfer-pathway, and FAQ prose with metadata sidecars; it is versioned.

Canonical raw and historical copies also belong in private S3 buckets. Never
commit student transcripts or other personal data.
