"""
monday_client.py
Handles all Monday.com API interactions via GraphQL.
"""

import os
import requests
import json
from typing import Optional

MONDAY_API_URL = "https://api.monday.com/v2"


def get_headers() -> dict:
    token = os.environ.get("MONDAY_API_TOKEN", "")
    return {
        "Authorization": token,
        "Content-Type": "application/json",
        "API-Version": "2024-01",
    }


def run_query(query: str, variables: Optional[dict] = None) -> dict:
    """Execute a GraphQL query against the Monday.com API."""
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    try:
        response = requests.post(
            MONDAY_API_URL,
            headers=get_headers(),
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        return {"errors": [{"message": "Monday.com API request timed out."}]}
    except requests.exceptions.ConnectionError:
        return {"errors": [{"message": "Failed to connect to Monday.com API."}]}
    except requests.exceptions.HTTPError as e:
        return {"errors": [{"message": f"HTTP error: {e}"}]}
    except Exception as e:
        return {"errors": [{"message": f"Unexpected error: {e}"}]}


def get_all_boards() -> list:
    """Fetch all boards the API token has access to."""
    query = """
    query {
        boards(limit: 50) {
            id
            name
            description
        }
    }
    """
    result = run_query(query)
    if "errors" in result:
        return []
    return result.get("data", {}).get("boards", [])


def get_board_items(board_id: str, limit: int = 500) -> list:
    """Fetch all items + column values from a board, handling pagination."""
    all_items = []
    cursor = None

    while True:
        if cursor:
            query = """
            query($board_id: ID!, $limit: Int!, $cursor: String!) {
                boards(ids: [$board_id]) {
                    items_page(limit: $limit, cursor: $cursor) {
                        cursor
                        items {
                            id
                            name
                            column_values {
                                id
                                text
                                value
                                column {
                                    title
                                    type
                                }
                            }
                        }
                    }
                }
            }
            """
            variables = {"board_id": board_id, "limit": limit, "cursor": cursor}
        else:
            query = """
            query($board_id: ID!, $limit: Int!) {
                boards(ids: [$board_id]) {
                    items_page(limit: $limit) {
                        cursor
                        items {
                            id
                            name
                            column_values {
                                id
                                text
                                value
                                column {
                                    title
                                    type
                                }
                            }
                        }
                    }
                }
            }
            """
            variables = {"board_id": board_id, "limit": limit}

        result = run_query(query, variables)
        if "errors" in result:
            break

        boards_data = result.get("data", {}).get("boards", [])
        if not boards_data:
            break

        items_page = boards_data[0].get("items_page", {})
        items = items_page.get("items", [])
        all_items.extend(items)

        cursor = items_page.get("cursor")
        if not cursor:
            break

    return all_items


def parse_item_to_dict(item: dict) -> dict:
    """Convert a Monday.com item (with column_values) into a flat dict."""
    result = {"id": item.get("id"), "name": item.get("name", "")}
    for cv in item.get("column_values", []):
        col_title = cv.get("column", {}).get("title", cv.get("id", "unknown"))
        text_val = cv.get("text", "") or ""
        result[col_title] = text_val.strip()
    return result


def get_board_as_records(board_id: str) -> list[dict]:
    """Return a board's items as a list of flat dicts."""
    items = get_board_items(board_id)
    return [parse_item_to_dict(item) for item in items]


def test_connection() -> bool:
    """Verify that the API token is valid."""
    query = "query { me { name } }"
    result = run_query(query)
    return "errors" not in result and bool(result.get("data", {}).get("me"))
