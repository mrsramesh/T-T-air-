#!/usr/bin/env bash
# ==============================================================================
# 1-Click Local Runner for Mac & Local Network (Zero Cost, Stealth & Anti-Bot)
# ==============================================================================

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "======================================================================"
echo "🚀 Multi-Carrier Air Cargo Tracking System - Local Mac Runner"
echo "======================================================================"

# 1. Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ python3 not found. Please install Python 3.10+ from python.org or brew."
    exit 1
fi

echo "✔ Python version: $(python3 --version)"

# 2. Check Tor proxy status (Optional 100% Free Anonymous IP Rotation)
if command -v tor &> /dev/null; then
    if ! pgrep -x "tor" > /dev/null; then
        echo "🧅 Starting local Tor SOCKS5 daemon in background on port 9050..."
        tor --RunAsDaemon 1 || true
    else
        echo "✔ Tor SOCKS5 proxy already running on 127.0.0.1:9050."
    fi
else
    echo "ℹ️  Tip: If you want 100% free Tor IP rotation, install it via: brew install tor"
    echo "    (The system will automatically use the built-in Free Rotating Proxy Pool!)"
fi

# 3. Create persistent data directory
mkdir -p "$PROJECT_DIR/data"

# 4. Start Server
echo "======================================================================"
echo "✨ Starting Multi-Carrier Tracking Server on http://127.0.0.1:8000"
echo "   Press Ctrl+C to stop."
echo "======================================================================"

exec python3 server.py
