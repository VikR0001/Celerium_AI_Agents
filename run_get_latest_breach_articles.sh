#!/bin/bash

# Set up environment for cron
export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"

# Change to script directory
cd /Users/sta_2020/Documents/code/src/github.com/VikR0001/Celerium_AI_Agents

# Check if virtual environment exists
if [ ! -f ".venv/bin/activate" ]; then
    echo "Error: Virtual environment not found at .venv/bin/activate" >&2
    exit 1
fi

# Activate virtual environment
source .venv/bin/activate

# Verify Python is available
if ! command -v python &> /dev/null; then
    echo "Error: Python not found in virtual environment" >&2
    exit 1
fi

# Run the Django command with full output
echo "Starting news article gathering at $(date)"
python manage.py gather_news_articles_and_save_them_to_db
echo "Completed news article gathering at $(date)"
