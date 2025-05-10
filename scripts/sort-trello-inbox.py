import os
import time
import requests
import readchar

from dotenv import load_dotenv

load_dotenv()
INBOX_BOARD_NAME = 'inbox'


def get_trello_boards():
    url = 'https://api.trello.com/1/members/me/boards'
    params = {
        'key': os.getenv("TRELLO_KEY"),
        'token': os.getenv("TRELLO_TOKEN")
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()


def get_trello_board_cards(board_id):
    url = f'https://api.trello.com/1/boards/{board_id}/cards'
    params = {
        'key': os.getenv("TRELLO_KEY"),
        'token': os.getenv("TRELLO_TOKEN")
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()


def move_trello_card_to_list(card_id, list_id):
    url = f'https://api.trello.com/1/cards/{card_id}'
    params = {
        'idList': list_id,
        'key': os.getenv("TRELLO_KEY"),
        'token': os.getenv("TRELLO_TOKEN")
    }
    response = requests.put(url, params=params)
    response.raise_for_status()
    return response.json()


def get_trello_board_lists(board_id):
    url = f'https://api.trello.com/1/boards/{board_id}/lists'
    params = {
        'key': os.getenv("TRELLO_KEY"),
        'token': os.getenv("TRELLO_TOKEN")
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()


def main():
    print("Getting Trello boards ...")
    boards = get_trello_boards()
    inbox_board_id = [board['id'] for board in boards if board['name'] == INBOX_BOARD_NAME][0]
    print(f"Inbox Board Id: {inbox_board_id}")

    print("Getting lists ...")
    lists = get_trello_board_lists(board_id=inbox_board_id)
    inbox_list_id = [ls['id'] for ls in lists if ls['name'] == 'inbox'][0]
    culled_list_id = [ls['id'] for ls in lists if ls['name'] == 'culled for upcoming week'][0]
    print(f"Inbox and culled list ids: {[inbox_list_id, culled_list_id]}")

    print("Looping through cards for culling ...")
    board_cards = get_trello_board_cards(board_id=inbox_board_id)
    inbox_cards = [card for card in board_cards if card['idList'] == inbox_list_id]
    responses = {}

    # logic for manually sorting the cards
    for card in inbox_cards:
        print("\033c", end="")  # ANSI escape code to clear terminal screen
        print("-"*3)
        print(f"\n\n{card['name']}\n\n")
        print("-"*3)
        
        print("\n\n\nPress SPACE to cull, or any other key to keep ...")
        key = readchar.readkey()
        if key == " ":
            response = move_trello_card_to_list(card_id=card['id'], list_id=culled_list_id)
            input("\nMoved card to culled list!")

    return True


# TODO: ability to delete
# TODO: ability to go back
# TODO: ability to dump already reviewed cards to the defer list
# TODO: show progress


if __name__ == "__main__":
    main()
