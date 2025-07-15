#!/bin/bash

echo "🚀 Installing Python dependencies..."
pip install -r requirements.txt

echo "🧩 Installing Playwright browsers..."
npx playwright install --with-deps

echo "✅ Done setting up."
