#!/usr/bin/env python3

"""
NocoDB Full Base Export Tool

This script exports a complete base including:
- Base metadata
- All tables with schemas
- All data from each table
- Views configuration
"""

import os
import sys
import json
from datetime import datetime
from typing import Dict, List

from nocodb_utils import make_request, get_config_with_auth, check_requests_library


def export_base_metadata(base_id: str, token: str, url: str) -> Dict:
    """Export base metadata"""
    print(f'\n📋 Exporting base metadata...')
    base_url = f"{url}/api/v2/meta/bases/{base_id}"
    metadata = make_request(base_url, token=token)
    print(f'   ✓ Base: {metadata.get("title", "Unknown")}')
    return metadata


def export_tables(base_id: str, token: str, url: str) -> List[Dict]:
    """Export all tables in the base"""
    print(f'\n📊 Exporting tables...')
    tables_url = f"{url}/api/v2/meta/bases/{base_id}/tables"
    tables_response = make_request(tables_url, token=token)
    tables = tables_response.get('list', [])
    print(f'   ✓ Found {len(tables)} tables')
    return tables


def export_table_schema(table_id: str, token: str, url: str) -> Dict:
    """Export table schema (columns, relationships, etc.)"""
    schema_url = f"{url}/api/v2/meta/tables/{table_id}"
    schema = make_request(schema_url, token=token)
    return schema


def export_table_data(base_id: str, table_id: str, table_name: str, token: str, url: str) -> List[Dict]:
    """Export all data from a table"""
    all_data = []
    offset = 0
    limit = 1000  # Fetch 1000 records at a time

    while True:
        # Use the data API endpoint
        data_url = f"{url}/api/v2/tables/{table_id}/records"
        params = {
            'limit': limit,
            'offset': offset
        }

        try:
            response = make_request(data_url, token=token, params=params)
            records = response.get('list', [])

            if not records:
                break

            all_data.extend(records)
            offset += len(records)

            print(f'      Fetched {len(all_data)} records...', end='\r')

            # If we got fewer records than the limit, we're done
            if len(records) < limit:
                break

        except Exception as e:
            print(f'\n      Warning: Could not fetch data for table {table_name}: {str(e)}')
            break

    return all_data


def export_table_views(table_id: str, token: str, url: str) -> List[Dict]:
    """Export views for a table"""
    try:
        views_url = f"{url}/api/v2/meta/tables/{table_id}/views"
        response = make_request(views_url, token=token)
        return response.get('list', [])
    except Exception as e:
        print(f'      Warning: Could not fetch views: {str(e)}')
        return []


def export_full_base(base_id: str, token: str, url: str, include_data: bool = True) -> Dict:
    """Export complete base with all tables, schemas, and data"""
    print('═══════════════════════════════════════════════')
    print('  NocoDB Full Base Export')
    print('═══════════════════════════════════════════════')

    export_data = {
        'export_version': '1.0',
        'export_date': datetime.now().isoformat(),
        'base': {},
        'tables': []
    }

    # Step 1: Export base metadata
    export_data['base'] = export_base_metadata(base_id, token, url)

    # Step 2: Export all tables
    tables = export_tables(base_id, token, url)

    # Step 3: For each table, export schema and data
    print(f'\n📦 Exporting table details...')
    for i, table in enumerate(tables, 1):
        table_id = table['id']
        table_title = table['title']

        print(f'\n   [{i}/{len(tables)}] {table_title}')

        # Export schema
        print(f'      - Fetching schema...')
        schema = export_table_schema(table_id, token, url)

        # Export views
        print(f'      - Fetching views...')
        views = export_table_views(table_id, token, url)

        # Export data
        data = []
        if include_data:
            print(f'      - Fetching data...')
            data = export_table_data(base_id, table_id, table_title, token, url)
            print(f'      ✓ Exported {len(data)} records')
        else:
            print(f'      - Skipping data (schema only)')

        export_data['tables'].append({
            'metadata': table,
            'schema': schema,
            'views': views,
            'data': data,
            'record_count': len(data)
        })

    return export_data


def main():
    """Main execution function"""

    # Get configuration with authentication support
    config = get_config_with_auth(
        required_vars=['BASE_ID'],
        optional_vars={
            'INCLUDE_DATA': 'true',
            'OUTPUT_FILE': None
        }
    )

    # Process boolean values
    config['include_data'] = config.get('include_data', 'true').lower() == 'true'

    try:
        # Export the base
        export_data = export_full_base(
            config['base_id'],
            config['token'],
            config['url'],
            config['include_data']
        )

        # Save to file
        if config['output_file']:
            output_file = config['output_file']
        else:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            base_title = export_data['base'].get('title', 'base').replace(' ', '_')
            output_file = f"nocodb_export_{base_title}_{timestamp}.json"

        with open(output_file, 'w') as f:
            json.dump(export_data, f, indent=2)

        print('\n═══════════════════════════════════════════════')
        print('  Export Summary')
        print('═══════════════════════════════════════════════')
        print(f'Base: {export_data["base"].get("title", "Unknown")}')
        print(f'Tables: {len(export_data["tables"])}')

        total_records = sum(t['record_count'] for t in export_data['tables'])
        print(f'Total Records: {total_records}')
        print(f'\n💾 Export saved to: {output_file}')
        print(f'   File size: {os.path.getsize(output_file) / (1024*1024):.2f} MB')

        print('\n✅ Export completed successfully!')

    except Exception as error:
        print(f'\n❌ Export failed:')
        print(f'   {str(error)}')
        sys.exit(1)


if __name__ == '__main__':
    check_requests_library()
    main()
