#!/bin/bash
cd "$(dirname "$0")"
python3 -c "from app import app, init_db; init_db()" 2>/dev/null
python3 app.py
