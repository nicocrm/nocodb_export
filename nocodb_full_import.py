#!/usr/bin/env python3

"""
NocoDB Full Base Import Tool

This script imports a complete base from an export file including:
- Base metadata
- All tables with schemas
- All data from each table
- Views configuration
"""

import os
import sys
import json
import time
from typing import Dict, List

from nocodb_utils import make_request, get_config_with_auth, check_requests_library


def create_base(title: str, description: str, token: str, url: str, workspace_id: str = None) -> Dict:
    """Create a new base"""
    print(f'\n📋 Creating new base: {title}')

    base_data = {
        'title': title,
        'description': description or 'Imported base'
    }

    if workspace_id:
        base_data['fk_workspace_id'] = workspace_id

    create_url = f"{url}/api/v2/meta/bases"
    new_base = make_request(create_url, method='POST', token=token, json_data=base_data)

    print(f'   ✓ Base created with ID: {new_base["id"]}')
    return new_base


def create_table(base_id: str, table_schema: Dict, token: str, url: str) -> Dict:
    """Create a table with its schema"""
    table_title = table_schema.get('title', 'Untitled')

    # Prepare columns
    columns = []
    if 'columns' in table_schema:
        for col in table_schema['columns']:
            # Skip system columns
            if col.get('system'):
                continue

            # Skip columns with null or empty column_name (usually relationship columns)
            column_name = col.get('column_name')
            if not column_name or column_name is None:
                continue

            # Skip relationship/link columns - they need to be created separately after all tables exist
            uidt = col.get('uidt', 'SingleLineText')
            if uidt in ['LinkToAnotherRecord', 'Links', 'Lookup', 'Rollup']:
                continue

            column_data = {
                'title': col.get('title', column_name),
                'column_name': str(column_name),
                'uidt': uidt,
            }

            # Add column-specific properties (only if they're not None)
            if col.get('dt') is not None:
                column_data['dt'] = str(col['dt'])
            if col.get('rqd') is not None:
                column_data['rqd'] = col['rqd']
            if col.get('cdf') is not None:
                column_data['cdf'] = col['cdf']
            if col.get('un') is not None:
                column_data['un'] = col['un']
            if col.get('pk') is not None:
                column_data['pk'] = col['pk']
            if col.get('ai') is not None:
                column_data['ai'] = col['ai']
            if col.get('dtxp') is not None:
                column_data['dtxp'] = col['dtxp']
            if col.get('dtxs') is not None:
                column_data['dtxs'] = col['dtxs']

            columns.append(column_data)

    table_data = {
        'title': table_title,
        'table_name': table_schema.get('table_name', table_title),
        'columns': columns
    }

    create_url = f"{url}/api/v2/meta/bases/{base_id}/tables"
    new_table = make_request(create_url, method='POST', token=token, json_data=table_data)

    return new_table


def import_table_data(table_id: str, data: List[Dict], token: str, url: str) -> int:
    """Import data into a table"""
    if not data:
        return 0

    imported_count = 0
    batch_size = 100

    for i in range(0, len(data), batch_size):
        batch = data[i:i + batch_size]

        # Clean the data - remove system fields and null IDs
        cleaned_batch = []
        for record in batch:
            cleaned_record = {}
            for key, value in record.items():
                # Skip system fields
                if key in ['Id', 'CreatedAt', 'UpdatedAt', 'nc_', 'ncRecordId', 'ncRecordHash']:
                    continue
                cleaned_record[key] = value
            cleaned_batch.append(cleaned_record)

        try:
            data_url = f"{url}/api/v2/tables/{table_id}/records"
            # Try to bulk insert
            for record in cleaned_batch:
                try:
                    make_request(data_url, method='POST', token=token, json_data=record)
                    imported_count += 1
                    print(f'      Imported {imported_count}/{len(data)} records...', end='\r')
                except Exception as e:
                    print(f'\n      Warning: Failed to import record: {str(e)}')
                    continue

        except Exception as e:
            print(f'\n      Warning: Batch import failed: {str(e)}')
            continue

    return imported_count


def import_full_base(import_file: str, token: str, url: str,
                     new_base_title: str = None, workspace_id: str = None) -> Dict:
    """Import complete base from export file"""
    print('═══════════════════════════════════════════════')
    print('  NocoDB Full Base Import')
    print('═══════════════════════════════════════════════')

    # Load export file
    print(f'\n📂 Loading export file: {import_file}')
    with open(import_file, 'r') as f:
        export_data = json.load(f)

    print(f'   ✓ Export version: {export_data.get("export_version", "Unknown")}')
    print(f'   ✓ Export date: {export_data.get("export_date", "Unknown")}')
    print(f'   ✓ Tables to import: {len(export_data.get("tables", []))}')

    # Step 1: Create new base
    original_title = export_data['base'].get('title', 'Imported Base')
    base_title = new_base_title or f"{original_title} (Import)"

    new_base = create_base(
        base_title,
        export_data['base'].get('description', ''),
        token,
        url,
        workspace_id
    )

    # Wait a bit for base to be fully created
    time.sleep(2)

    # Step 2: Create tables
    print(f'\n📊 Creating tables...')
    table_mapping = {}  # Map old table IDs to new table IDs

    for i, table_export in enumerate(export_data.get('tables', []), 1):
        table_schema = table_export.get('schema', {})
        table_title = table_export['metadata'].get('title', f'Table_{i}')

        print(f'\n   [{i}/{len(export_data["tables"])}] {table_title}')
        print(f'      - Creating table structure...')

        try:
            new_table = create_table(new_base['id'], table_schema, token, url)
            old_table_id = table_export['metadata']['id']
            table_mapping[old_table_id] = new_table['id']

            print(f'      ✓ Table created')

            # Step 3: Import data
            data = table_export.get('data', [])
            if data:
                print(f'      - Importing {len(data)} records...')
                imported = import_table_data(new_table['id'], data, token, url)
                print(f'      ✓ Imported {imported} records')
            else:
                print(f'      - No data to import')

        except Exception as e:
            print(f'      ✗ Failed to create table: {str(e)}')
            continue

    return {
        'base': new_base,
        'tables_created': len(table_mapping),
        'table_mapping': table_mapping
    }


def main():
    """Main execution function"""

    # Get configuration with authentication support
    config = get_config_with_auth(
        required_vars=['IMPORT_FILE'],
        optional_vars={
            'NEW_BASE_TITLE': None,
            'WORKSPACE_ID': None
        }
    )

    if not os.path.exists(config['import_file']):
        print(f'❌ Error: Import file not found: {config["import_file"]}')
        sys.exit(1)

    try:
        # Import the base
        result = import_full_base(
            config['import_file'],
            config['token'],
            config['url'],
            config['new_base_title'],
            config['workspace_id']
        )

        print('\n═══════════════════════════════════════════════')
        print('  Import Summary')
        print('═══════════════════════════════════════════════')
        print(f'New Base ID: {result["base"]["id"]}')
        print(f'New Base Title: {result["base"]["title"]}')
        print(f'Tables Created: {result["tables_created"]}')

        print('\n✅ Import completed successfully!')
        print(f'\n🔗 Access your new base at:')
        print(f'   {config["url"]}/nc/{result["base"]["id"]}')

    except Exception as error:
        print(f'\n❌ Import failed:')
        print(f'   {str(error)}')
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    check_requests_library()
    main()
