#!/usr/bin/env python3
"""
Test: Compare snapshot length for short vs long product lists.
Verifies that more products → proportionally more snapshot content.
"""

import asyncio
import sys
import re
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.clients.desktop_app.ami_daemon.base_agent.tools.toolkits.browser_toolkit import BrowserToolkit


async def main():
    toolkit = BrowserToolkit(
        session_id="test-links",
        headless=False,
    )

    url = "https://www.producthunt.com/leaderboard/weekly/2026/6"
    print(f"\n1. Visiting {url}")
    await toolkit.browser_visit_page(url)
    await asyncio.sleep(3)

    session = await toolkit._get_session()
    page = await session.get_page()

    # SHORT PAGE: snapshot before scrolling (initial load ~20 products)
    print("\n2. SHORT PAGE snapshot (initial load)...")
    count_short = await page.evaluate(
        "document.querySelectorAll('[data-test^=\"post-item-\"]').length"
    )
    snapshot_short = await toolkit.browser_get_page_snapshot(include_links=True)
    lines_short = len(snapshot_short.splitlines())
    print(f"   Products: {count_short}")
    print(f"   Snapshot: {len(snapshot_short)} chars, {lines_short} lines")
    print(f"   Chars per product: {len(snapshot_short) // max(count_short, 1)}")

    # Scroll to load all products
    print("\n3. Scrolling to load all products...")
    prev_count = 0
    stable = 0
    for round_num in range(10):
        for i in range(15):
            await toolkit.browser_scroll(direction="down", amount=5000)
            await asyncio.sleep(0.8)
        count = await page.evaluate(
            "document.querySelectorAll('[data-test^=\"post-item-\"]').length"
        )
        print(f"   Round {round_num + 1}: {count} products")
        if count == prev_count:
            stable += 1
            if stable >= 2:
                break
        else:
            stable = 0
        prev_count = count

    # Scroll back to top
    await page.evaluate("window.scrollTo(0, 0)")
    await asyncio.sleep(1)

    # LONG PAGE: snapshot after full load
    print("\n4. LONG PAGE snapshot (fully loaded)...")
    count_long = await page.evaluate(
        "document.querySelectorAll('[data-test^=\"post-item-\"]').length"
    )
    snapshot_long = await toolkit.browser_get_page_snapshot(include_links=True)
    lines_long = len(snapshot_long.splitlines())
    print(f"   Products: {count_long}")
    print(f"   Snapshot: {len(snapshot_long)} chars, {lines_long} lines")
    print(f"   Chars per product: {len(snapshot_long) // max(count_long, 1)}")

    # Check product coverage in long snapshot
    dom_products = await page.evaluate("""
    (() => {
        const items = document.querySelectorAll('[data-test^="post-item-"]');
        return Array.from(items).map(item => {
            const link = item.querySelector('a[href^="/products/"]');
            return link ? link.textContent.trim().split('\\n')[0].trim() : '(unknown)';
        });
    })()
    """)

    found = 0
    missing_names = []
    for name in dom_products:
        search = name[:15] if len(name) > 15 else name
        if search in snapshot_long:
            found += 1
        else:
            missing_names.append(name)

    # Summary
    print("\n" + "=" * 60)
    print("COMPARISON")
    print("=" * 60)
    print(f"   SHORT: {count_short:3d} products → {len(snapshot_short):7d} chars, {lines_short:5d} lines ({len(snapshot_short) // max(count_short, 1)} chars/product)")
    print(f"   LONG:  {count_long:3d} products → {len(snapshot_long):7d} chars, {lines_long:5d} lines ({len(snapshot_long) // max(count_long, 1)} chars/product)")
    ratio = count_long / max(count_short, 1)
    size_ratio = len(snapshot_long) / max(len(snapshot_short), 1)
    print(f"\n   Product count ratio: {ratio:.1f}x")
    print(f"   Snapshot size ratio: {size_ratio:.1f}x")
    if size_ratio < ratio * 0.5:
        print(f"   ⚠️  BUG: Snapshot grew only {size_ratio:.1f}x but products grew {ratio:.1f}x!")
    else:
        print(f"   ✓ Snapshot scales proportionally with product count")

    print(f"\n   Coverage: {found}/{len(dom_products)}")
    if missing_names:
        print(f"   Missing ({len(missing_names)}):")
        for n in missing_names[:10]:
            print(f"     - {n}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
