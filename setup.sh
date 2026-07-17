#!/bin/bash
# Setup script for Slack MCP Server (using uv)

echo "🚀 Setting up Slack MCP Server with uv..."

if ! command -v uv &> /dev/null; then
    echo "❌ uv is not installed. Install it: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

echo "📥 Installing dependencies with uv..."
uv sync

echo "✅ Setup complete!"
echo ""
echo "1. Create a Slack app and add User Token Scopes:"
echo "   search:read, channels:history, channels:read, users:read, chat:write"
echo "2. Export your user token:"
echo "   export SLACK_USER_TOKEN='xoxp-...'"
echo "3. Run the server:"
echo "   uv run slack-mcp"
