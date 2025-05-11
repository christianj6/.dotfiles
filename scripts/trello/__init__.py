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
