import re
import sys

from dotenv import load_dotenv

from client import (
    get_trello_boards,
    get_trello_board_lists,
    get_trello_board_cards,
    get_trello_card,
    create_trello_list,
    create_trello_card,
    create_checklist,
    add_checklist_item,
    get_card_checklists,
    delete_trello_list,
)

load_dotenv()

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

lists_not_to_merge = ["inbox", "culled for upcoming week", "deferred", "...", "merged cards"]

def should_merge_list(list_name: str) -> bool:
    """Determine if a list should be merged based on exclusion rules."""
    # Skip if in exclusion list
    if list_name.lower() in [name.lower() for name in lists_not_to_merge]:
        return False
    
    # Skip if contains numerals
    if re.search(r'\d', list_name):
        return False
    
    return True

def main():
    # Get inbox board
    boards = get_trello_boards()
    inbox_board = next((board for board in boards if board['name'].lower() == 'inbox'), None)
    
    if not inbox_board:
        print("Could not find inbox board")
        sys.exit(1)
    
    # Get all lists from inbox board
    lists = get_trello_board_lists(inbox_board['id'])
    
    # Filter lists that should be merged
    lists_to_merge = [lst for lst in lists if should_merge_list(lst['name'])]
    
    if not lists_to_merge:
        print("No lists found to merge")
        return
    
    print(f"Found {len(lists_to_merge)} list(s) to merge:")
    for lst in lists_to_merge:
        print(f"  - {lst['name']}")
    
    # Merge each qualifying list
    for lst in lists_to_merge:
        print(f"\nMerging cards from list '{lst['name']}'...")
        merge_list_cards_into_single_card_in_new_list(inbox_board['id'], lst['id'])
        
        # Delete source list after successful merge
        print(f"Archiving list '{lst['name']}'...")
        delete_trello_list(lst['id'])
    
    print("\nDone!")

if __name__ == "__main__":
    main()
