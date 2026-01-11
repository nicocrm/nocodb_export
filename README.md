# NocoDB Base Export/Import Tool

Export and import NocoDB bases between instances.

## Quick Start

### Install
```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Export a Base
```bash
NOCODB_EMAIL="your@email.com" \
NOCODB_PASSWORD="yourpassword" \
BASE_ID="p2b1mor87640vjw" \
uv run nocodb_full_export.py
```

### Import a Base
```bash
NOCODB_EMAIL="your@email.com" \
NOCODB_PASSWORD="yourpassword" \
IMPORT_FILE="nocodb_export_BaseName_TIMESTAMP.json" \
uv run nocodb_full_import.py
```

## Authentication

**Option 1: Email/Password (Recommended)**
```bash
NOCODB_EMAIL="your@email.com" NOCODB_PASSWORD="yourpassword"
```

**Option 2: Auth Token**
```bash
NOCODB_TOKEN="eyJhbGc..."
```

## Configuration

### Export Script

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NOCODB_EMAIL` + `NOCODB_PASSWORD` | Yes* | - | Email/password auth |
| `NOCODB_TOKEN` | Yes* | - | Token auth (alternative) |
| `BASE_ID` | Yes | - | Base ID (from URL) |
| `NOCODB_URL` | No | `http://localhost:8500` | NocoDB instance URL |
| `INCLUDE_DATA` | No | `true` | Include table data |
| `OUTPUT_FILE` | No | auto | Custom output filename |

*Either EMAIL+PASSWORD or TOKEN required

### Import Script

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NOCODB_EMAIL` + `NOCODB_PASSWORD` | Yes* | - | Email/password auth |
| `NOCODB_TOKEN` | Yes* | - | Token auth (alternative) |
| `IMPORT_FILE` | Yes | - | Path to export file |
| `NOCODB_URL` | No | `http://localhost:8500` | NocoDB instance URL |
| `NEW_BASE_TITLE` | No | `{original} (Import)` | New base title |
| `WORKSPACE_ID` | No | - | Target workspace ID |

*Either EMAIL+PASSWORD or TOKEN required

## What's Included

✅ Base metadata, tables, schemas, columns, data, views
⚠️ **NOT included:** Link/Relationship columns, Lookup/Rollup columns, Webhooks, API tokens

## Use Cases

**Duplicate a base:**
```bash
NOCODB_EMAIL="user@email.com" NOCODB_PASSWORD="pass" BASE_ID="p123" uv run --with requests nocodb_full_export.py
NOCODB_EMAIL="user@email.com" NOCODB_PASSWORD="pass" IMPORT_FILE="nocodb_export_*.json" uv run --with requests nocodb_full_import.py
```

**Transfer between instances:**
```bash
NOCODB_URL="http://source:8500" NOCODB_EMAIL="user@email.com" NOCODB_PASSWORD="pass" BASE_ID="p123" uv run --with requests nocodb_full_export.py
NOCODB_URL="http://target:8500" NOCODB_EMAIL="user2@email.com" NOCODB_PASSWORD="pass2" IMPORT_FILE="nocodb_export_*.json" uv run --with requests nocodb_full_import.py
```

**Schema only (no data):**
```bash
INCLUDE_DATA="false" NOCODB_EMAIL="user@email.com" NOCODB_PASSWORD="pass" BASE_ID="p123" uv run --with requests nocodb_full_export.py
```

## Finding Your Base ID

Open your base in NocoDB and look at the URL:
```
http://your-instance/nc/p2b1mor87640vjw
                        ^^^^^^^^^^^^^^^^
                        This is your BASE_ID
```

## Tips

**Use .env file:**
```bash
cat > .env << EOF
NOCODB_EMAIL=your@email.com
NOCODB_PASSWORD=yourpassword
BASE_ID=p123abc
EOF

uv run nocodb_full_export.py
```

**Batch export:**
```bash
for BASE_ID in p123 p456 p789; do
  NOCODB_EMAIL="user@email.com" NOCODB_PASSWORD="pass" BASE_ID="$BASE_ID" uv run --with requests nocodb_full_export.py
done
```

## Troubleshooting

- **401 Unauthorized:** Use email/password auth or get fresh token
- **Base not found:** Check BASE_ID format (starts with 'p')
- **Missing relationships after import:** Recreate Link columns manually in UI
- **Slow exports:** Use `INCLUDE_DATA="false"` for schema only
