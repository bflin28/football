#!/bin/bash
set -e

echo "=== Building frontend ==="
cd frontend
npm install
npm run build
echo "Frontend built to dist/"

echo "=== Installing backend dependencies ==="
cd ../backend
pip install -r requirements.txt
echo "Backend dependencies installed"

echo "=== Build complete ==="
