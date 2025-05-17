import readchar
from tqdm import tqdm
import requests
from dotenv import load_dotenv
from trello import (
    get_trello_boards,
    get_trello_board_cards,
    move_trello_card_to_list,
    delete_trello_card,
    get_trello_board_lists
)

load_dotenv()
INBOX_BOARD_NAME = 'inbox'

def main():
    print("Getting Trello boards ...")
    boards = get_trello_boards()
    inbox_board_id = [board['id'] for board in boards if board['name'] == INBOX_BOARD_NAME][0]
    print(f"Inbox Board Id: {inbox_board_id}")

    print("Getting lists ...")
    lists = get_trello_board_lists(board_id=inbox_board_id)
    inbox_list_id = [ls['id'] for ls in lists if ls['name'] == 'inbox'][0]
    culled_list_id = [ls['id'] for ls in lists if ls['name'] == 'culled for upcoming week'][0]
    defer_list_id = [ls['id'] for ls in lists if ls['name'] == 'deferred'][0]
    print(f"Inbox and culled list ids: {[inbox_list_id, culled_list_id]}")

    print("Looping through cards for culling ...")
    board_cards = get_trello_board_cards(board_id=inbox_board_id)
    inbox_cards = [card for card in board_cards if card['idList'] == inbox_list_id]
    
    # Track cards that were reviewed but not culled/deleted
    cards_to_defer = []
    
    i = 0
    total_cards = len(inbox_cards)
    while i < total_cards:
        print("\033c", end="")  # ANSI escape code to clear terminal screen
        print(f"Progress: {i + 1}/{total_cards} cards")
        print("-"*3)
        print(f"\n\n{inbox_cards[i]['name']}\n\n")
        print("-"*3)

        print("\n\n\nPress SPACE to cull, D to delete, U to defer all reviewed cards,")
        print("BACKSPACE to go back, or any other key to keep ...")
        print("\nYou can press CTRL-C at any time to quit the session, it is recommended to press 'U' first to save your state.")

        try:
            key = readchar.readkey()

        except KeyboardInterrupt:
            print("\n\nGracefully exiting...")
            # Auto-defer any remaining reviewed cards
            if cards_to_defer:
                print(f"\nAuto-deferring {len(cards_to_defer)} reviewed cards...")
                for card in tqdm(cards_to_defer, desc="Auto-deferring cards"):
                    move_trello_card_to_list(card_id=card['id'], list_id=defer_list_id)
                print("\nDone!")

            return True
        
        if key.lower() == "u":
            if cards_to_defer:
                print(f"\nDeferring {len(cards_to_defer)} cards...")
                # Move all reviewed but not culled/deleted cards to defer list
                for card in tqdm(cards_to_defer, desc="Deferring cards"):
                    move_trello_card_to_list(card_id=card['id'], list_id=defer_list_id)
                input("\nDone! Press Enter to continue...")

            cards_to_defer = []  # Clear the list after deferring
            continue

        if key == "\x7f":  # Backspace key
            i = max(0, i - 1)  # Go back one card, but not before the first card
            continue
            
        if key == " ":
            move_trello_card_to_list(card_id=inbox_cards[i]['id'], list_id=culled_list_id)
            input("\nMoved card to culled list!")

        elif key.lower() == "d":
            delete_trello_card(card_id=inbox_cards[i]['id'])
            input("\nDeleted card!")

        else:
            # Card was reviewed but not culled/deleted, add to defer candidates
            cards_to_defer.append(inbox_cards[i])
            
        i += 1

    # Handle any remaining cards that need to be deferred
    if cards_to_defer:
        print(f"\nDeferring {len(cards_to_defer)} remaining cards...")
        for card in tqdm(cards_to_defer, desc="Deferring final cards"):
            try: 
                move_trello_card_to_list(card_id=card['id'], list_id=defer_list_id)
            except requests.exceptions.HTTPError:
                print("ERROR when moving card!")
                pass
        print("\nDone!")

    return True


# TODO: text is narrower
# TODO: ability to get more details on a card


if __name__ == "__main__":
    main()
