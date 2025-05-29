import os
import sys
from typing import Dict, List
from dotenv import load_dotenv
from trello import (
    get_trello_boards,
    get_trello_board_lists,
)
from merge_trello_cards import (
    create_trello_list,
    create_trello_card,
    create_checklist,
    add_checklist_item
)

load_dotenv()

def create_project_structure(board_id: str, project_data: Dict) -> None:
    """
    Creates a full project structure from parsed PDF data.
    
    Expected project_data structure:
    {
        "name": "Project Name",
        "description": "Overall project description",
        "phases": [
            {
                "name": "Phase 1",
                "description": "Phase description",
                "tasks": [
                    {
                        "name": "Task 1",
                        "description": "Task description",
                        "subtasks": ["Subtask 1", "Subtask 2"]
                    }
                ]
            }
        ]
    }
    """
    # Create main project list
    project_list = create_trello_list(board_id, project_data["name"])
    
    # Create overview card
    overview_card = create_trello_card(
        project_list["id"],
        "Project Overview",
        project_data["description"]
    )
    
    # For each phase
    for phase in project_data["phases"]:
        phase_card = create_trello_card(
            project_list["id"],
            phase["name"],
            phase["description"]
        )
        
        # Create tasks checklist
        tasks_checklist = create_checklist(phase_card["id"], "Tasks")
        
        # Create detailed cards for each task
        for task in phase["tasks"]:
            # Add task to phase checklist
            add_checklist_item(tasks_checklist["id"], task["name"])
            
            # Create detailed task card
            task_card = create_trello_card(
                project_list["id"],
                task["name"],
                task["description"]
            )
            
            # Add subtasks as checklist
            if task.get("subtasks"):
                subtasks_checklist = create_checklist(task_card["id"], "Subtasks")
                for subtask in task["subtasks"]:
                    add_checklist_item(subtasks_checklist["id"], subtask)

def main():
    if len(sys.argv) != 2:
        print("Usage: create-project-plan.py <project_data.json>")
        sys.exit(1)

    json_file = sys.argv[1]
    if not os.path.exists(json_file):
        print(f"Error: File {json_file} not found")
        sys.exit(1)

    # Get target board
    boards = get_trello_boards()
    target_board = next((board for board in boards if board["name"].lower() == "projects"), None)
    
    if not target_board:
        print("Could not find projects board")
        sys.exit(1)
    
    # Load project data from JSON file
    try:
        with open(json_file, 'r') as f:
            import json
            project_data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON file: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading file: {e}")
        sys.exit(1)
    
    # Create the project structure
    create_project_structure(target_board["id"], project_data)
    print("Project structure created successfully!")

if __name__ == "__main__":
    main()
