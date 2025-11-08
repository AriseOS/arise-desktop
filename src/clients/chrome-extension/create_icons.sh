#!/bin/bash

# Create simple PNG icons for Chrome extension
# This script creates basic gradient icons

cd "$(dirname "$0")/icons"

# Create icon16.png (simple 16x16 purple square)
base64 -d > icon16.png << 'EOF'
iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAQElEQVR42mNgGAWjYBSMAhBgZGBg
+M/AwMDw//9/BiYGBgYmBkYGZgZGBhYGJgYWBiYGVgYmBlYGJgZWBiYGVgYAn0QH+WMpBykAAAAA
SUVORK5CYII=
EOF

# Create icon48.png  (48x48 purple square)
base64 -d > icon48.png << 'EOF'
iVBORw0KGgoAAAANSUhEUgAAADAAAAAwCAYAAABXAvmHAAAAnElEQVR42u3XMQ0AIAwEwWpgARPY
wAYmMAEGMIEJ/kOAJKTou5t0yZeqql1VVb+qqnpVVdWrqqpeVVX1qqqqV1VVvaqqetVVVa+qqnpV
VdWrqqpeVVX1qqqqV1VVvaqqelVV1auqql5VVfWqqqpXVVW9qqrqVVVVr6qqelVV1auqql5VVfWq
qqpXVVW9qqrqVVVVr6qqelVV1auqql5VVfUfuQEWTAf5YkEGswAAAABJRU5ErkJggg==
EOF

# Create icon128.png (128x128 purple square)
base64 -d > icon128.png << 'EOF'
iVBORw0KGgoAAAANSUhEUgAAAIAAAACACAYAAADDPmHLAAAAqUlEQVR42u3SMQEAAAwCoNm/9Cx4
CEJQaG1tqaqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq
qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq
qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqpgAdRgB
wLYTJKoAAAAASUVORK5CYII=
EOF

echo "Icons created successfully!"
ls -lah