#!/bin/bash
# Setup Chrome debug profile with all your data

SOURCE_PROFILE="$HOME/Library/Application Support/Google/Chrome"
DEBUG_PROFILE="$HOME/.chrome-debug-with-extensions"

echo "=== Chrome Debug Profile Setup ==="
echo ""
echo "This will:"
echo "  1. Copy your Chrome profile to: $DEBUG_PROFILE"
echo "  2. Preserve all extensions, bookmarks, and settings"
echo "  3. Enable remote debugging"
echo ""
echo "⚠️  Note: Login sessions (cookies) will be copied but may need re-login"
echo ""
echo "Press Enter to continue, Ctrl+C to cancel..."
read

# Close Chrome
echo "Closing existing Chrome..."
killall "Google Chrome" 2>/dev/null
sleep 2

# Check if debug profile already exists
if [ -d "$DEBUG_PROFILE" ]; then
    echo "⚠️  Debug profile already exists at: $DEBUG_PROFILE"
    echo "Do you want to:"
    echo "  1) Use existing profile (faster)"
    echo "  2) Delete and re-copy from current Chrome (fresh sync)"
    echo ""
    read -p "Choice (1 or 2): " choice
    
    if [ "$choice" = "2" ]; then
        echo "Deleting old debug profile..."
        rm -rf "$DEBUG_PROFILE"
    else
        echo "Using existing profile..."
    fi
fi

# Copy profile if needed
if [ ! -d "$DEBUG_PROFILE" ]; then
    echo ""
    echo "Copying Chrome profile... (this may take a minute)"
    cp -R "$SOURCE_PROFILE" "$DEBUG_PROFILE"
    
    # Remove lock files that might cause issues
    rm -f "$DEBUG_PROFILE/SingletonLock" 2>/dev/null
    rm -f "$DEBUG_PROFILE/SingletonSocket" 2>/dev/null
    rm -f "$DEBUG_PROFILE/SingletonCookie" 2>/dev/null
    
    echo "✅ Profile copied successfully"
fi

echo ""
echo "Starting Chrome with debug profile..."
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="$DEBUG_PROFILE" \
  --no-first-run \
  --no-default-browser-check &

CHROME_PID=$!
echo "Chrome PID: $CHROME_PID"

sleep 4
echo ""
echo "Testing CDP connection..."
RESPONSE=$(curl -s http://localhost:9222/json/version 2>&1)

if echo "$RESPONSE" | grep -q "Browser"; then
    echo "✅ CDP connection successful!"
    echo ""
    echo "$RESPONSE" | python3 -m json.tool | head -10
    echo ""
    echo "🎉 Success! Chrome is now running with:"
    echo "   ✅ All your extensions"
    echo "   ✅ All your settings"
    echo "   ✅ Remote debugging enabled on port 9222"
    echo ""
    echo "⚠️  Note: You may need to log in to websites again"
else
    echo "❌ CDP connection failed"
    echo "Response: $RESPONSE"
    echo ""
    echo "Troubleshooting:"
    echo "  - Check if Chrome started successfully"
    echo "  - Check: lsof -i :9222"
fi
