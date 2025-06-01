#!/usr/bin/env python3
import json
import os
import argparse
import asyncio
import concurrent.futures
from typing import Dict, List, Optional
from dotenv import load_dotenv
import openai
from tqdm import tqdm
import requests

from trello import (
    get_trello_boards,
    get_trello_board_cards,
    move_trello_card_to_list,
    get_trello_board_lists
)

load_dotenv()

INBOX_BOARD_NAME = 'inbox'
DEFERRED_LIST_NAME = 'deferred'
INBOX_LIST_NAME = 'inbox'
ARCHIVE_LIST_NAME = 'archive'
UNCERTAIN_LIST_NAME = 'culled for upcoming week'

def load_priorities() -> Dict:
    """Load priorities from priorities.json file."""
    with open('priorities.json', 'r') as f:
        return json.load(f)

def load_prompt_template() -> str:
    """Load prompt template from prompt.txt file."""
    with open('prompt.txt', 'r') as f:
        return f.read()

def format_prompt(template: str, priorities: Dict, note_text: str) -> str:
    """Format the prompt template with priorities and note text."""
    priorities_text = '\n'.join([f"- {priority}" for priority in priorities['year']])
    short_term_text = '\n'.join([f"- {priority}" for priority in priorities['short-term']])
    context_text = '\n'.join([f"- {ctx}" for ctx in priorities['context']])
    
    return template.format(
        priorities=priorities_text,
        short=short_term_text,
        context=context_text,
        note_text=note_text
    )

def get_llm_decision(prompt: str) -> str:
    """Call OpenAI API to get categorization decision."""
    client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "user", "content": prompt}
        ],
        max_tokens=10,
        temperature=0
    )
    
    return response.choices[0].message.content.strip()

def move_trello_card_with_timeout(card_id: str, list_id: str, timeout: int = 30) -> bool:
    """Move a card to a different list with timeout handling."""
    url = f'https://api.trello.com/1/cards/{card_id}'
    params = {
        'idList': list_id,
        'key': os.getenv("TRELLO_KEY"),
        'token': os.getenv("TRELLO_TOKEN")
    }
    try:
        response = requests.put(url, params=params, timeout=timeout)
        response.raise_for_status()
        return True
    except (requests.exceptions.Timeout, requests.exceptions.RequestException):
        return False

async def process_card_async(executor, card: Dict, prompt_template: str, priorities: Dict, list_mapping: Dict, dry_run: bool) -> Optional[Dict]:
    """Process a single card asynchronously."""
    note_text = f"Title: {card['name']}"
    if card.get('desc'):
        note_text += f"\nDescription: {card['desc']}"
    
    prompt = format_prompt(prompt_template, priorities, note_text)
    
    try:
        # Run LLM decision in thread pool
        decision = await asyncio.get_event_loop().run_in_executor(
            executor, get_llm_decision, prompt
        )
        decision = decision.upper().strip()
        
        if decision not in ['INBOX', 'UNCERTAIN', 'ARCHIVE']:
            decision = 'UNCERTAIN'
        
        result = {
            'card': card,
            'decision': decision,
            'note_text': note_text,
            'moved': False
        }
        
        if not dry_run:
            # Run Trello API call in thread pool with timeout
            if decision == 'INBOX':
                target_list = list_mapping['inbox']
            elif decision == 'ARCHIVE':
                target_list = list_mapping['archive']
            elif decision == 'UNCERTAIN':
                target_list = list_mapping['uncertain']
            
            moved = await asyncio.get_event_loop().run_in_executor(
                executor, move_trello_card_with_timeout, card['id'], target_list
            )
            result['moved'] = moved
        
        return result
        
    except Exception as e:
        print(f"Error processing card '{card['name']}': {e}")
        return {
            'card': card,
            'decision': 'UNCERTAIN',
            'note_text': note_text,
            'moved': False,
            'error': str(e)
        }

async def main_async():
    parser = argparse.ArgumentParser(description='LLM-assisted note sorting for Trello cards')
    parser.add_argument('--dry-run', action='store_true', help='Preview decisions without moving cards')
    parser.add_argument('--max-workers', type=int, default=10, help='Maximum number of concurrent workers')
    args = parser.parse_args()
    
    print("Loading priorities and prompt template...")
    priorities = load_priorities()
    prompt_template = load_prompt_template()
    
    print("Getting Trello boards...")
    boards = get_trello_boards()
    inbox_board_id = None
    for board in boards:
        if board['name'] == INBOX_BOARD_NAME:
            inbox_board_id = board['id']
            break
    
    if not inbox_board_id:
        print(f"Error: Could not find board named '{INBOX_BOARD_NAME}'")
        return
    
    print(f"Found inbox board: {inbox_board_id}")
    
    print("Getting board lists...")
    lists = get_trello_board_lists(board_id=inbox_board_id)
    
    list_mapping = {}
    for lst in lists:
        if lst['name'] == DEFERRED_LIST_NAME:
            list_mapping['deferred'] = lst['id']
        elif lst['name'] == INBOX_LIST_NAME:
            list_mapping['inbox'] = lst['id']
        elif lst['name'] == ARCHIVE_LIST_NAME:
            list_mapping['archive'] = lst['id']
        elif lst['name'] == UNCERTAIN_LIST_NAME:
            list_mapping['uncertain'] = lst['id']
    
    required_lists = ['deferred', 'inbox', 'archive', 'uncertain']
    missing_lists = [name for name in required_lists if name not in list_mapping]
    if missing_lists:
        print(f"Error: Could not find required lists: {missing_lists}")
        return
    
    print("Getting cards from deferred list...")
    board_cards = get_trello_board_cards(board_id=inbox_board_id)
    deferred_cards = [card for card in board_cards if card['idList'] == list_mapping['deferred']]
    
    if not deferred_cards:
        print("No cards found in deferred list.")
        return
    
    print(f"Found {len(deferred_cards)} cards to process...")
    
    # Process cards concurrently using thread pool
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        print("Processing cards concurrently...")
        tasks = []
        for card in deferred_cards:
            task = process_card_async(executor, card, prompt_template, priorities, list_mapping, args.dry_run)
            tasks.append(task)
        
        # Process all cards concurrently with progress bar
        results = []
        for coro in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Processing cards"):
            result = await coro
            if result:
                results.append(result)
                if args.dry_run:
                    print(f"Card: {result['card']['name'][:50]}... -> {result['decision']}")
    
    # Summary
    if args.dry_run:
        print("\nDry run complete. Summary:")
        decision_counts = {}
        for result in results:
            decision_counts[result['decision']] = decision_counts.get(result['decision'], 0) + 1
        for decision, count in decision_counts.items():
            print(f"  {decision}: {count} cards")
    else:
        moved_count = sum(1 for r in results if r.get('moved', False))
        failed_count = len(results) - moved_count
        print(f"\nProcessing complete!")
        print(f"  Successfully moved: {moved_count} cards")
        print(f"  Failed/timed out: {failed_count} cards (left in deferred list)")
        
        if failed_count > 0:
            print("\nFailed cards:")
            for result in results:
                if not result.get('moved', False):
                    card_name = result['card']['name'][:50]
                    reason = "timeout/error" if 'error' not in result else f"error: {result['error']}"
                    print(f"  - {card_name}... ({reason})")

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()