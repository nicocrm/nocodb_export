#!/usr/bin/env python3

"""
NocoDB Utilities

Shared functions for NocoDB export/import scripts including:
- HTTP request handling
- Authentication token retrieval
- Configuration management
"""

import dotenv
import os
import sys
import requests
from typing import Dict, Optional



def make_request(url: str, method: str = 'GET', token: str = '',
                 json_data: Optional[Dict] = None, params: Optional[Dict] = None) -> Dict:
    """Make HTTP request to NocoDB API"""
    headers = {
        'xc-auth': token,
        'Content-Type': 'application/json'
    }

    print(f"{url=} {method=} {token=} {json_data=} {params=}")
    try:
        if method == 'GET':
            response = requests.get(url, headers=headers, params=params)
        elif method == 'POST':
            response = requests.post(url, headers=headers, json=json_data)
        elif method == 'PUT':
            response = requests.put(url, headers=headers, json=json_data)
        elif method == 'PATCH':
            response = requests.patch(url, headers=headers, json=json_data)
        else:
            raise ValueError(f"Unsupported method: {method}")

        response.raise_for_status()
        return response.json() if response.content else {}

    except requests.exceptions.RequestException as e:
        print(f'   Error: {str(e)}')
        if hasattr(e, 'response') and e.response is not None:
            print(f'   Response: {e.response.text}')
        raise


def get_auth_token(url: str, email: str, password: str) -> str:
    """
    Get authentication token from NocoDB

    Args:
        url: NocoDB instance URL
        email: User email
        password: User password

    Returns:
        Authentication token string
    """
    auth_url = f"{url}/api/v1/auth/user/signin"

    try:
        response = requests.post(
            auth_url,
            headers={'Content-Type': 'application/json'},
            json={'email': email, 'password': password}
        )
        response.raise_for_status()

        data = response.json()
        token = data.get('token')

        if not token:
            raise ValueError("No token returned from authentication")

        return token

    except requests.exceptions.RequestException as e:
        print(f'❌ Authentication failed: {str(e)}')
        if hasattr(e, 'response') and e.response is not None:
            print(f'   Response: {e.response.text}')
        raise


def get_config_with_auth(required_vars: list, optional_vars: dict = None) -> Dict:
    """
    Get configuration from environment variables with authentication support

    Supports two authentication methods:
    1. Direct token: NOCODB_TOKEN
    2. Email/password: NOCODB_EMAIL and NOCODB_PASSWORD (will fetch token automatically)

    Args:
        required_vars: List of required variable names (besides auth)
        optional_vars: Dict of optional variables with their defaults

    Returns:
        Configuration dictionary
    """
    dotenv.load_dotenv()
    optional_vars = optional_vars or {}

    # Base configuration
    config = {
        'url': os.getenv('NOCODB_URL', 'http://localhost:8500'),
    }

    # Add optional variables
    for key, default in optional_vars.items():
        config[key.lower()] = os.getenv(key, default)

    # Authentication: token OR email/password
    token = os.getenv('NOCODB_TOKEN', '')
    email = os.getenv('NOCODB_EMAIL', '')
    password = os.getenv('NOCODB_PASSWORD', '')

    if token:
        # Direct token provided
        config['token'] = token
    elif email and password:
        # Authenticate with email/password
        print('🔐 Authenticating with email/password...')
        try:
            config['token'] = get_auth_token(config['url'], email, password)
            print('   ✓ Authentication successful')
        except Exception as e:
            print(f'❌ Failed to get authentication token: {str(e)}')
            sys.exit(1)
    else:
        # No valid authentication provided
        config['token'] = ''

    # Check required variables
    missing_vars = []
    for var in required_vars:
        value = os.getenv(var, '')
        config[var.lower()] = value
        if not value:
            missing_vars.append(var)

    if not config['token']:
        missing_vars.append('NOCODB_TOKEN or (NOCODB_EMAIL + NOCODB_PASSWORD)')

    if missing_vars:
        print('❌ Error: Missing required configuration\n')
        print('Required environment variables:')
        for var in required_vars:
            print(f'  - {var}')
        print('  - NOCODB_TOKEN or (NOCODB_EMAIL + NOCODB_PASSWORD) for authentication\n')

        if optional_vars:
            print('Optional environment variables:')
            print('  - NOCODB_URL: NocoDB URL (default: http://localhost:8500)')
            for key, default in optional_vars.items():
                print(f'  - {key}: (default: {default})')

        sys.exit(1)

    return config
