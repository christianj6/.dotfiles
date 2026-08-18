import os
import requests
from typing import Dict, List


def get_trello_boards() -> List[Dict]:
    """Get all Trello boards for the authenticated user."""
    url = 'https://api.trello.com/1/members/me/boards'
    params = {
        'key': os.getenv("TRELLO_KEY"),
        'token': os.getenv("TRELLO_TOKEN")
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()

def get_trello_board_cards(board_id: str) -> List[Dict]:
    """Get all cards from a specific board."""
    url = f'https://api.trello.com/1/boards/{board_id}/cards'
    params = {
        'key': os.getenv("TRELLO_KEY"),
        'token': os.getenv("TRELLO_TOKEN")
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()

def move_trello_card_to_list(card_id: str, list_id: str) -> Dict:
    """Move a card to a different list."""
    url = f'https://api.trello.com/1/cards/{card_id}'
    params = {
        'idList': list_id,
        'key': os.getenv("TRELLO_KEY"),
        'token': os.getenv("TRELLO_TOKEN")
    }
    response = requests.put(url, params=params)
    response.raise_for_status()
    return response.json()

def delete_trello_card(card_id: str) -> None:
    """Delete a Trello card."""
    url = f'https://api.trello.com/1/cards/{card_id}'
    params = {
        'key': os.getenv("TRELLO_KEY"),
        'token': os.getenv("TRELLO_TOKEN")
    }
    response = requests.delete(url, params=params)
    response.raise_for_status()

def get_trello_board_lists(board_id: str) -> List[Dict]:
    """Get all lists from a specific board."""
    url = f'https://api.trello.com/1/boards/{board_id}/lists'
    params = {
        'key': os.getenv("TRELLO_KEY"),
        'token': os.getenv("TRELLO_TOKEN")
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()

def get_trello_card(card_id: str) -> Dict:
    """Get full details of a Trello card including attachments and comments."""
    url = f'https://api.trello.com/1/cards/{card_id}'
    params = {
        'key': os.getenv("TRELLO_KEY"),
        'token': os.getenv("TRELLO_TOKEN"),
        'attachments': 'true',
        'comments': 'true'
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()

def update_card_description(card_id: str, description: str) -> None:
    """Update a card's description."""
    url = f'https://api.trello.com/1/cards/{card_id}'
    params = {
        'key': os.getenv("TRELLO_KEY"),
        'token': os.getenv("TRELLO_TOKEN"),
        'desc': description
    }
    response = requests.put(url, params=params)
    response.raise_for_status()

def delete_trello_list(list_id: str) -> None:
    """Delete a Trello list."""
    url = f'https://api.trello.com/1/lists/{list_id}/closed'
    params = {
        'value': 'true',  # Archive/close the list
        'key': os.getenv("TRELLO_KEY"),
        'token': os.getenv("TRELLO_TOKEN")
    }
    response = requests.put(url, params=params)
    response.raise_for_status()

def create_trello_list(board_id: str, name: str) -> Dict:
    """Create a new list in the specified board."""
    # First get existing lists to calculate position
    lists = get_trello_board_lists(board_id)
    if len(lists) >= 2:
        # Get position of second list
        third_position = (lists[1]['pos'] + lists[2]['pos']) / 2 if len(lists) > 2 else lists[1]['pos'] + 16384
    else:
        third_position = 32768  # Default Trello position increment

    url = f'https://api.trello.com/1/lists'
    params = {
        'name': name,
        'idBoard': board_id,
        'pos': third_position,
        'key': os.getenv("TRELLO_KEY"),
        'token': os.getenv("TRELLO_TOKEN")
    }

    response = requests.post(url, params=params)
    response.raise_for_status()
    return response.json()

def create_trello_card(list_id: str, name: str, description: str = "") -> Dict:
    """Create a new card in the specified list."""
    MAX_DESC_LENGTH = 8000  # Trello's limit with some buffer

    # If description is too long, create card with attachment instead
    if len(description) > MAX_DESC_LENGTH:
        print(f"Description exceeds {MAX_DESC_LENGTH} characters. Creating card with attachment...")
        return create_trello_card_with_attachment(list_id, name, description)

    url = f'https://api.trello.com/1/cards'
    params = {
        'name': name,
        'idList': list_id,
        'desc': description,
        'key': os.getenv("TRELLO_KEY"),
        'token': os.getenv("TRELLO_TOKEN")
    }
    response = requests.post(url, params=params)
    response.raise_for_status()
    return response.json()

def create_trello_card_with_attachment(list_id: str, name: str, description: str = "") -> Dict:
    """Create a card and add large content as an attachment."""
    from tempfile import NamedTemporaryFile

    # Create card with minimal description
    card = create_trello_card(
        list_id,
        name,
        "This card's full content is available in the attached markdown file due to length."
    )

    # Create temporary file with full content
    with NamedTemporaryFile(mode='w', suffix='.md', delete=False) as temp_file:
        temp_file.write(description)
        temp_path = temp_file.name

    try:
        # Upload as attachment
        url = f'https://api.trello.com/1/cards/{card["id"]}/attachments'
        with open(temp_path, 'rb') as file_content:
            files = {
                'file': (
                    f'{name}_full_content.md',
                    file_content,
                    'text/markdown'
                )
            }
            params = {
                'key': os.getenv("TRELLO_KEY"),
                'token': os.getenv("TRELLO_TOKEN")
            }
            response = requests.post(url, params=params, files=files)
            response.raise_for_status()
    finally:
        os.unlink(temp_path)

    return card

def create_checklist(card_id: str, name: str) -> Dict:
    """Create a new checklist on a card."""
    url = f'https://api.trello.com/1/checklists'
    params = {
        'name': name,
        'idCard': card_id,
        'key': os.getenv("TRELLO_KEY"),
        'token': os.getenv("TRELLO_TOKEN")
    }
    response = requests.post(url, params=params)
    response.raise_for_status()
    return response.json()

def add_checklist_item(checklist_id: str, name: str) -> Dict:
    """Add an item to a checklist."""
    url = f'https://api.trello.com/1/checklists/{checklist_id}/checkItems'
    params = {
        'name': name,
        'key': os.getenv("TRELLO_KEY"),
        'token': os.getenv("TRELLO_TOKEN")
    }
    response = requests.post(url, params=params)
    response.raise_for_status()
    return response.json()

def get_card_checklists(card_id: str) -> List[Dict]:
    """Get all checklists from a card."""
    url = f'https://api.trello.com/1/cards/{card_id}/checklists'
    params = {
        'key': os.getenv("TRELLO_KEY"),
        'token': os.getenv("TRELLO_TOKEN")
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()
