import os
import requests
import sys
from typing import List, Dict
from dotenv import load_dotenv
from tqdm import tqdm
from trello import (
    get_trello_card,
    update_card_description,
    delete_trello_card,
    get_trello_boards,
    get_trello_board_lists,
    get_trello_board_cards,
    delete_trello_list
)

load_dotenv()

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

def merge_list_cards_into_single_card_in_new_list(board_id: str, source_list_id: str):
    """Merge all cards from a list into a single new card in a new list."""
    # Get source list details
    lists = get_trello_board_lists(board_id)
    source_list = next((lst for lst in lists if lst['id'] == source_list_id), None)
    
    if not source_list:
        raise ValueError(f"Could not find list with ID {source_list_id}")

    # Check if "merged cards" list already exists
    lists = get_trello_board_lists(board_id)
    merged_list = next((lst for lst in lists if lst['name'] == "merged cards"), None)
    
    # Create "merged cards" list if it doesn't exist
    if not merged_list:
        merged_list = create_trello_list(board_id, "merged cards")
    
    # Get all cards from source list
    cards = get_trello_board_cards(board_id)
    source_cards = [card for card in cards if card['idList'] == source_list_id]
    
    if not source_cards:
        print("No cards found in source list")
        return
    
    # Create new merged card
    merged_description = ""
    for card in source_cards:
        card_details = get_trello_card(card['id'])
        merged_description += f"### {card['name']}\n\n"
        
        # Add description if it exists
        if card_details['desc']:
            merged_description += f"{card_details['desc']}\n\n"
        
        # Add any attachments/links
        if card_details['attachments']:
            merged_description += "**Attachments:**\n"
            for attachment in card_details['attachments']:
                if attachment['url']:
                    merged_description += f"- [{attachment['name'] or attachment['url']}]({attachment['url']})\n"
            merged_description += "\n"
        
        merged_description += "---\n\n"
    
    new_card = create_trello_card(
        merged_list['id'],
        source_list['name'],
        merged_description
    )
    
    # Create default checklist with card names
    default_checklist = create_checklist(new_card['id'], "Original Cards")
    for card in source_cards:
        add_checklist_item(default_checklist['id'], card['name'])
    
    # Handle cards with checklists
    for card in source_cards:
        checklists = get_card_checklists(card['id'])
        if checklists:
            for checklist in checklists:
                # Create new checklist named after original card + checklist
                new_checklist = create_checklist(
                    new_card['id'],
                    f"{card['name']} - {checklist['name']}"
                )
                # Add all items from original checklist
                for item in checklist['checkItems']:
                    add_checklist_item(new_checklist['id'], item['name'])

def main():
    if len(sys.argv) != 2:
        print("Usage: merge-trello-cards.py <inbox list name>")
        sys.exit(1)
    
    inbox_list_name = sys.argv[1]
    
    # Get inbox board
    boards = get_trello_boards()
    inbox_board = next((board for board in boards if board['name'].lower() == 'inbox'), None)
    
    if not inbox_board:
        print("Could not find inbox board")
        sys.exit(1)
    
    # Get list ID for the specified list name
    lists = get_trello_board_lists(inbox_board['id'])
    target_list = next((lst for lst in lists if lst['name'].lower() == inbox_list_name.lower()), None)
    
    if not target_list:
        print(f"Could not find list named '{inbox_list_name}' in inbox board")
        sys.exit(1)
    
    print(f"Merging cards from list '{inbox_list_name}'...")
    merge_list_cards_into_single_card_in_new_list(inbox_board['id'], target_list['id'])
    
    # delete source list after successful merge
    print("Archiving source list...")
    delete_trello_list(target_list['id'])
    print("Done!")


if __name__ == "__main__":
    main()
