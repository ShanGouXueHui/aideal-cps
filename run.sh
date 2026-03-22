#!/bin/bash

echo "🔪 Killing existing process on 8000..."
kill -9 $(lsof -t -i:8000) 2>/dev/null

echo "🚀 Starting server..."
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
