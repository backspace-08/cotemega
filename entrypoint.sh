#!/bin/sh
set -e

echo "Running seed..."
python seed.py

echo "Starting bot..."
exec python bot.py
