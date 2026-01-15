#!/usr/bin/env python3

"""
NocoDB Full Base Import Tool

This script imports a complete base from an export file including:
- Base metadata
- All tables with schemas
- All data from each table
"""

import re
from typing import Any
import os
import sys
import json
import time
from typing import Dict, List

from nocodb_utils import ApiClient, get_config_with_auth


def create_base(
    title: str, description: str, api_client: ApiClient, workspace_id: str = ''
) -> Dict:
    """Create a new base"""
    print(f'\n📋 Creating new base: {title}')

    base_data = {'title': title, 'description': description or 'Imported base'}

    if workspace_id:
        base_data['fk_workspace_id'] = workspace_id

    create_path = '/api/v2/meta/bases'
    new_base = api_client.make_request(
        method='POST', path=create_path, json_data=base_data
    )

    print(f'   ✓ Base created with ID: {new_base["id"]}')
    return new_base

def clean_color(choice: dict) -> dict:
    """Fixes some incompatibilities in the exported color format"""
    if color := choice.get('color'):
        if re.match(r'^#[0-9A-Fa-f]{3}$', color):
            # 3 digit -> 6 digit hex color
            choice['color'] = f'#{color[1]}{color[1]}{color[2]}{color[2]}{color[3]}{color[3]}'
    return choice

def clean_field_options(field: Dict) -> Dict:
    """Fixes some incompatibilities in the field options that can make it impossible to import"""
    if not field.get('options'):
        return field
    if field.get('type') in ('Email', 'PhoneNumber', 'URL'):
        field['options']['validation'] = field['options'].pop('validate', False)
    field['options'] = clean_color(field['options'])
    if choices := field['options'].get('choices'):
        field['options']['choices'] = [clean_color(c) for c in choices]
    for invalid_option in ('locale_string', 'notify'):
        field['options'].pop(invalid_option, None)
    return field

def create_table(
    base_id: str, source_id: str, table_schema: Dict, api_client: ApiClient
) -> Dict:
    """Create a table with its schema"""
    table_title = table_schema.get('title', 'Untitled')

    # Prepare columns
    disallowed_types = {
        'ID',
        'Links',
        'Lookup',
        'ForeignKey',
        'LinkToAnotherRecord',
        'CreatedTime',
        'LastModifiedTime',
    }
    fields = [
        f
        for f in table_schema.get('fields', [])
        if f.get('type') not in disallowed_types and not f.get('system')
    ]

    table_data = {
        'title': table_title,
        'table_name': table_schema.get('table_name', table_title),
        'fields': [clean_field_options(field) for field in fields],
    }

    create_path = f'/api/v3/meta/bases/{base_id}/tables'
    new_table = api_client.make_request(
        method='POST', path=create_path, json_data=table_data
    )

    return new_table


def import_table_data(
    table_id: str, data: List[Dict], api_client: ApiClient
) -> dict[int, int]:
    """
    Import data into a table
    Return a dictionary of old_record_id -> new_record_id
    """
    data_mapping: dict[int, int] = {}
    if not data:
        return data_mapping

    imported_count = 0
    batch_size = 100

    for i in range(0, len(data), batch_size):
        batch = data[i : i + batch_size]

        # Clean the data - remove system fields and null IDs
        cleaned_batch = []
        for record in batch:
            cleaned_record = {}
            for key, value in record.items():
                # Skip system fields
                if key in [
                    'Id',
                    'CreatedAt',
                    'UpdatedAt',
                    'Last modified by',
                    'nc_',
                    'ncRecordId',
                    'ncRecordHash',
                ]:
                    continue
                if isinstance(value, dict) or isinstance(value, list):
                    # probably a relationship field, skip
                    continue
                cleaned_record[key] = value
            cleaned_batch.append(cleaned_record)

        try:
            data_path = f'/api/v2/tables/{table_id}/records'
            # Try to bulk insert
            for old_record, record in zip(batch, cleaned_batch):
                try:
                    created = api_client.make_request(
                        method='POST', path=data_path, json_data=record
                    )
                    data_mapping[old_record['Id']] = created['Id']
                    imported_count += 1
                    print(
                        f'      Imported {imported_count}/{len(data)} records...',
                        end='\r',
                    )
                except Exception as e:
                    print(f'\n      Warning: Failed to import record: {str(e)}')
                    continue

        except Exception as e:
            print(f'\n      Warning: Batch import failed: {str(e)}')
            continue

    return data_mapping


def create_relationship_fields(
    base_id: str,
    table_id: str,
    table_schema: Dict,
    table_mapping: Dict,
    api_client: ApiClient,
) -> dict[str, str]:
    """
    Create relationship fields for a table
    Return a dictionary of title -> id
    """
    created_fields: dict[str, str] = {}
    fields_path = f'/api/v3/meta/bases/{base_id}/tables/{table_id}/fields'
    for field in table_schema.get('fields', []):
        if field.get('type') == 'Links' or field.get('type') == 'LinkToAnotherRecord':
            linked_table = table_mapping.get(
                field.get('options', {}).get('related_table_id')
            )
            if not linked_table:
                print(
                    f'      ✗ Linked table not found: {field.get("options", {}).get("related_table_id")}'
                )
                continue
            if field.get('options', {}).get('relation_type') == 'mm':
                if linked_table < table_id:
                    # skip this end of the relationship, we'll create it from the other side
                    continue
            # bottom side of the relationship
            if field.get('options', {}).get('bt') is True:
                continue
            if field.get('options', {}).get('relation_type') == 'bt':
                continue
            field_data = {
                'title': field.get('title'),
                'type': 'Links',
                'description': field.get('description'),
                'options': {
                    'related_table_id': linked_table,
                    'relation_type': field['options']['relation_type'],
                },
            }
            created = api_client.make_request(
                method='POST', path=fields_path, json_data=field_data
            )
            created_fields[created['title']] = created['id']
            print(f'      ✓ Relationship field created: {field_data["title"]}')
    return created_fields

def find_old_link_field(link_field: dict, table_schema: dict, table_mapping: dict[str, str]) -> dict | None:
    """
    Find the link field in the OLD table schema using the (old) related table id

    link_field is the link field from the NEW schema
    table_schema is the OLD table schema
    table_mapping is a dictionary of:
        old_table_id -> new_table_id
    """
    new_table_id = link_field.get('options', {}).get('related_table_id')
    old_table_id = next(
        (k for k, v in table_mapping.items() if v == new_table_id), None
    )
    if not old_table_id:
        return None
    by_title = {f['title']: f for f in table_schema.get('fields', []) if f.get('options', {}).get('related_table_id') == old_table_id}
    by_title_without_space = {k.replace(' ', ''): v for k, v in by_title.items()}
    if len(by_title) == 1:
        return next(iter(by_title.values()))
    if f := by_title.get(link_field['title']):
        return f
    if f := by_title_without_space.get(link_field['title'].replace(' ', '')):
        return f
    return None

def import_relationship_data(
    base_id: str,
    table_id: str,
    old_table_schema: dict,
    table_data: list[dict[str, Any]],
    table_mapping: dict[str, str],
    data_mapping: dict[str, dict[int, int]],
    api_client: ApiClient,
) -> int:
    """
    Import relationship data into a table

    data_mapping is a dictionary of:
        new_table_id -> {old_record_id -> new_record_id}
    table_id is the NEW table id
    old_table_schema is the OLD table schema
    table_mapping is a dictionary of:
        old_table_id -> new_table_id
    """
    new_table_schema = api_client.make_request(
        method='GET', path=f'/api/v3/meta/bases/{base_id}/tables/{table_id}'
    )
    link_fields = [
        field
        for field in new_table_schema.get('fields', [])
        if field.get('type') == 'LinkToAnotherRecord'
        and field.get('options', {}).get('related_table_id') in data_mapping
    ]
    table_record_mapping = data_mapping[table_id]
    linked_count = 0
    for link_field in link_fields:
        linked_table_id = link_field.get('options', {}).get('related_table_id')
        linked_table_id_mapping = data_mapping.get(linked_table_id)
        old_link_field = find_old_link_field(link_field, old_table_schema, table_mapping)
        if not old_link_field:
            print(f'      ✗ Link field not found: {link_field["title"]}')
            continue
        assert linked_table_id_mapping is not None
        for record in table_data:
            linked_record = record.get(old_link_field['title'])
            if not linked_record:
                continue
            linked_record_id = linked_record['Id']
            new_linked_record_id = linked_table_id_mapping.get(linked_record_id)
            if not new_linked_record_id:
                print(f'      ✗ Linked record not found: {linked_record_id}')
                continue
            record_to_link = table_record_mapping.get(record['Id'])
            if not record_to_link:
                print(f'      ✗ Record to link not found: {record["Id"]}')
                continue
            api_client.make_request(
                method='POST',
                path=f'/api/v3/data/{base_id}/{table_id}/links/{link_field["id"]}/{record_to_link}',
                json_data={'id': str(new_linked_record_id)},
            )
            linked_count = linked_count + 1

    return linked_count


def import_full_base(
    import_file: str,
    api_client: ApiClient,
    new_base_title: str = '',
    workspace_id: str = '',
) -> Dict:
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
    base_title = new_base_title or f'{original_title} (Import)'

    new_base = create_base(
        base_title, export_data['base'].get('description', ''), api_client, workspace_id
    )
    new_base_id = new_base['id']
    new_source_id = new_base['sources'][0]['id']

    # Wait a bit for base to be fully created
    time.sleep(2)

    # Step 2: Create tables with basic fields
    print(f'\n📊 Creating tables...')
    table_mapping: dict[str, str] = {}  # Map old table IDs to new table IDs
    for i, table_export in enumerate(export_data.get('tables', []), 1):
        table_schema = table_export.get('schema', {})
        table_title = table_export['metadata'].get('title', f'Table_{i}')

        print(f'\n   [{i}/{len(export_data["tables"])}] {table_title}')

        try:
            new_table = create_table(
                new_base_id, new_source_id, table_schema, api_client
            )
            old_table_id = table_export['metadata']['id']
            table_mapping[old_table_id] = new_table['id']

            print(f'      ✓ Table created')

        except Exception as e:
            print(f'      ❌ Failed to create table: {str(e)}')
            sys.exit(1)

    # Step 3: Create relationship fields
    print(f'\n📊 Creating relationship fields...')
    for i, table_export in enumerate(export_data.get('tables', []), 1):
        table_schema = table_export.get('schema', {})
        new_table_id = table_mapping.get(table_export['metadata']['id'])
        print(
            f'\n   [{i}/{len(export_data["tables"])}] {table_export["metadata"]["title"]}'
        )
        if not new_table_id:
            print(f'      ✗ Table not found: {table_export["metadata"]["id"]}')
            continue
        try:
            create_relationship_fields(
                new_base_id, new_table_id, table_schema, table_mapping, api_client
            )
        except Exception as e:
            print(f'      ❌ Failed to create relationship fields: {str(e)}')
            sys.exit(1)

    # Step 4: Import data
    print(f'\n📊 Importing data...')
    data_mapping: dict[str, dict[int, int]] = {}
    for i, table_export in enumerate(export_data.get('tables', []), 1):
        data = table_export.get('data', [])
        new_table_id = table_mapping[table_export['metadata']['id']]
        print(
            f'\n   [{i}/{len(export_data["tables"])}] {table_export["metadata"]["title"]}'
        )
        if not new_table_id:
            print(f'      ✗ Table not found: {table_export["metadata"]["id"]}')
            continue
        if data:
            print(f'      - Importing {len(data)} records...')
            imported = import_table_data(new_table_id, data, api_client)
            data_mapping[new_table_id] = imported
            print(f'      ✓ Imported {len(imported)} records')
        else:
            print(f'      - No data to import')
            data_mapping[new_table_id] = {}

    # Step 5: Import relationship data
    print(f'\n📊 Importing relationship data...')
    for i, table_export in enumerate(export_data.get('tables', []), 1):
        new_table_id = table_mapping.get(table_export['metadata']['id'])
        print(
            f'\n   [{i}/{len(export_data["tables"])}] {table_export["metadata"]["title"]}'
        )
        if not new_table_id:
            print(f'      ✗ Table not found: {table_export["metadata"]["id"]}')
            continue
        data = table_export.get('data', [])
        if not data:
            print(f'      - No data to import')
            continue
        linked_count = import_relationship_data(
            new_base_id, new_table_id, table_export.get('schema', {}), data, table_mapping, data_mapping, api_client
        )
        print(f'      ✓ Linked {linked_count} records')

    return {
        'base': new_base,
        'tables_created': len(table_mapping),
        'table_mapping': table_mapping,
    }


def main():
    """Main execution function"""

    # Get configuration with authentication support
    config = get_config_with_auth(
        required_vars=['IMPORT_FILE'],
        optional_vars={'NEW_BASE_TITLE': None, 'WORKSPACE_ID': None},
    )

    if not os.path.exists(config['import_file']):
        print(f'❌ Error: Import file not found: {config["import_file"]}')
        sys.exit(1)

    try:
        # Create ApiClient instance
        api_client = ApiClient(
            token=config['token'], token_type=config['token_type'], url=config['url']
        )

        # Import the base
        result = import_full_base(
            config['import_file'],
            api_client,
            config['new_base_title'],
            config['workspace_id'],
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
    main()
