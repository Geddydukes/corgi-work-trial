#!/bin/bash

# Script to create a private GitHub repo and push the code
# Usage: ./setup_github_repo.sh [repo-name] [github-username]

REPO_NAME="${1:-Corgi}"
GITHUB_USER="${2:-}"

if [ -z "$GITHUB_USER" ]; then
    echo "GitHub username not provided. Please provide it as the second argument."
    echo "Usage: ./setup_github_repo.sh [repo-name] [github-username]"
    exit 1
fi

echo "Creating private GitHub repository: $GITHUB_USER/$REPO_NAME"

# Check if GitHub CLI is available
if command -v gh &> /dev/null; then
    echo "Using GitHub CLI..."
    gh repo create "$REPO_NAME" --private --source=. --remote=origin --push
else
    # Try using GitHub API
    if [ -z "$GITHUB_TOKEN" ]; then
        echo "GitHub token not found in environment."
        echo "Please create the repo manually at: https://github.com/new"
        echo "Then run:"
        echo "  git remote add origin https://github.com/$GITHUB_USER/$REPO_NAME.git"
        echo "  git branch -M main"
        echo "  git push -u origin main"
        exit 1
    fi
    
    echo "Using GitHub API..."
    curl -X POST \
        -H "Authorization: token $GITHUB_TOKEN" \
        -H "Accept: application/vnd.github.v3+json" \
        https://api.github.com/user/repos \
        -d "{\"name\":\"$REPO_NAME\",\"private\":true}"
    
    git remote add origin "https://github.com/$GITHUB_USER/$REPO_NAME.git"
    git branch -M main
    git push -u origin main
fi

echo "Done! Repository created and code pushed."

