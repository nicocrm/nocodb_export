#!/usr/bin/env python3

"""
NocoDB Full Base Export Tool

This script exports a complete base including:
- Base metadata
- All tables with schemas
- All data from each table
- Views configuration
"""

from dataclasses import asdict
from dataclasses import dataclass
import os
import sys
import json
from datetime import datetime
from typing import Dict, List

from nocodb_utils import ApiClient, get_config_with_auth


def export_base_metadata(base_id: str, api_client: ApiClient) -> Dict:
    """Export base metadata"""
    print(f'\n📋 Exporting base metadata...')
    base_path = f"/api/v3/meta/bases/{base_id}"
    metadata = api_client.make_request(method='GET', path=base_path)
    print(f'   ✓ Base: {metadata.get("title", "Unknown")}')
    return metadata


def export_tables(base_id: str, api_client: ApiClient) -> List[Dict]:
    """Export all tables in the base"""
    print(f'\n📊 Exporting tables...')
    tables_path = f"/api/v3/meta/bases/{base_id}/tables"
    tables_response = api_client.make_request(method='GET', path=tables_path)
    tables = tables_response.get('list', [])
    print(f'   ✓ Found {len(tables)} tables')
    return tables


def export_table_schema(base_id: str, table_id: str, api_client: ApiClient) -> Dict:
    """
    Export table schema (columns, relationships, etc.)

    View names are part of the schema, but we don't do anything with them
    since the API is not supported in the CE edition.
    """
    schema_path = f"/api/v3/meta/bases/{base_id}/tables/{table_id}"
    schema = api_client.make_request(method='GET', path=schema_path)
    return schema


def export_table_data(base_id: str, table_id: str, table_name: str, api_client: ApiClient) -> List[Dict]:
    """Export all data from a table"""
    all_data = []
    offset = 0
    limit = 1000  # Fetch 1000 records at a time

    while True:
        # Use the data API endpoint
        data_path = f"/api/v2/tables/{table_id}/records"
        params = {
            'limit': limit,
            'offset': offset
        }

        try:
            response = api_client.make_request(method='GET', path=data_path, params=params)
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

@dataclass
class ExportData:
    export_version: str
    export_date: str
    base: dict
    tables: list[dict]

    def to_dict(self) -> dict:
        return asdict(self)


def export_full_base(base_id: str, api_client: ApiClient, include_data: bool = True) -> ExportData:
    """Export complete base with all tables, schemas, and data"""
    print('═══════════════════════════════════════════════')
    print('  NocoDB Full Base Export')
    print('═══════════════════════════════════════════════')

    export_data = ExportData(
        export_version='2.0',
        export_date=datetime.now().isoformat(),
        base={},
        tables=[]
    )

    # Step 1: Export base metadata
    export_data.base = export_base_metadata(base_id, api_client)

    # Step 2: Export all tables
    tables = export_tables(base_id, api_client)

    # Step 3: For each table, export schema and data
    print(f'\n📦 Exporting table details...')
    for i, table in enumerate(tables, 1):
        table_id = table['id']
        table_title = table['title']

        print(f'\n   [{i}/{len(tables)}] {table_title}')

        # Export schema
        print(f'      - Fetching schema...')
        schema = export_table_schema(base_id, table_id, api_client)

        # Export data
        data = []
        if include_data:
            print(f'      - Fetching data...')
            data = export_table_data(base_id, table_id, table_title, api_client)
            print(f'      ✓ Exported {len(data)} records')
        else:
            print(f'      - Skipping data (schema only)')

        export_data.tables.append({
            'metadata': table,
            'schema': schema,
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
        # Create ApiClient instance
        api_client = ApiClient(
            token=config['token'],
            token_type=config['token_type'],
            url=config['url']
        )

        # Export the base
        export_data = export_full_base(
            config['base_id'],
            api_client,
            config['include_data']
        )

        # Save to file
        if config['output_file']:
            output_file = config['output_file']
        else:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            base_title = export_data.base.get('title', 'base').replace(' ', '_')
            output_file = f"nocodb_export_{base_title}_{timestamp}.json"

        with open(output_file, 'w') as f:
            json.dump(export_data.to_dict(), f, indent=2)

        print('\n═══════════════════════════════════════════════')
        print('  Export Summary')
        print('═══════════════════════════════════════════════')
        print(f'Base: {export_data.base.get("title", "Unknown")}')
        print(f'Tables: {len(export_data.tables)}')

        total_records = sum(t['record_count'] for t in export_data.tables)
        print(f'Total Records: {total_records}')
        print(f'\n💾 Export saved to: {output_file}')
        print(f'   File size: {os.path.getsize(output_file) / (1024*1024):.2f} MB')

        print('\n✅ Export completed successfully!')

    except Exception as error:
        print(f'\n❌ Export failed:')
        print(f'   {str(error)}')
        sys.exit(1)


if __name__ == '__main__':
    main()
