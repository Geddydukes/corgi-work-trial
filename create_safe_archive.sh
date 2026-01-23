#!/bin/bash
# Safe archive creation script - excludes .env and credentials

ARCHIVE_NAME="project_submission_$(date +%Y%m%d).zip"

echo "Creating safe archive: $ARCHIVE_NAME"
echo "Excluding: .env files, credentials/, node_modules/, __pycache__/, etc."

# Method 1: Use git archive (safest - only includes tracked files)
if git rev-parse --git-dir > /dev/null 2>&1; then
    echo "Using git archive (safest method)..."
    git archive -o "$ARCHIVE_NAME" HEAD
    echo "✅ Created: $ARCHIVE_NAME"
    echo "   This only includes files tracked by git (excludes .env automatically)"
else
    # Method 2: Manual zip with exclusions
    echo "Using zip with exclusions..."
    zip -r "$ARCHIVE_NAME" . \
        -x "*.env*" \
        -x "*credentials*" \
        -x "*gen-lang-client*" \
        -x "*node_modules*" \
        -x "*__pycache__*" \
        -x "*.pyc" \
        -x "*.log" \
        -x "*.db" \
        -x "*.sqlite*" \
        -x ".git/*" \
        -x "env/*" \
        -x "venv/*" \
        -x ".venv/*" \
        -x ".DS_Store" \
        -x "logs/*"
    echo "✅ Created: $ARCHIVE_NAME"
fi

echo ""
echo "Verifying archive contents..."
unzip -l "$ARCHIVE_NAME" | grep -E "\.env|credentials|gen-lang" || echo "✅ No .env or credential files found in archive"

echo ""
echo "Archive ready: $ARCHIVE_NAME"
