#!/bin/bash

# Check if project name is provided
if [ -z "$1" ]; then
    echo "Usage: $0 <project-name>"
    exit 1
fi

PROJECT_NAME=$1

# Create project directory
mkdir -p "$PROJECT_NAME"
cd "$PROJECT_NAME" || exit

# Create .gitignore
cat > .gitignore <<EOL
# Python
__pycache__/
*.py[cod]
*$py.class
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual Environment
venv/
.env/
.venv/
env/

# IDE
.vscode/
.idea/

# Aider
.aider*

# Misc
.DS_Store
EOL

# Create conda environment
conda create -n "$PROJECT_NAME" python=3.10 -y
conda init
conda activate "$PROJECT_NAME"

# Install required packages
python -m pip install aider-install pre-commit
aider-install

# Initialize git and pre-commit
git init
cat > .pre-commit-config.yaml <<EOL
repos:
-   repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.4.0
    hooks:
    -   id: trailing-whitespace
    -   id: end-of-file-fixer
-   repo: https://github.com/psf/black
    rev: 23.9.1
    hooks:
    -   id: black
EOL

pre-commit install

# make a main.py for fun
touch main.py

echo "Project $PROJECT_NAME created successfully!"

cd ./"$PROJECT_NAME"
nvim .
