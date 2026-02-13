#!/usr/bin/env python3
"""Test URL description generation."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.clients.desktop_app.ami_daemon.base_agent.core.ami_task_planner import AMITaskPlanner


def test_url_descriptions():
    """Test _generate_url_description with various URLs."""
    print("=" * 60)
    print("Testing URL Description Generation")
    print("=" * 60)

    test_urls = [
        "https://www.producthunt.com/leaderboard/daily/2026/1/27?ref=header_nav",
        "https://www.producthunt.com/leaderboard/weekly/2026/5",
        "https://www.producthunt.com/products/kilocode",
        "https://www.producthunt.com/",
        "https://www.amazon.com/products/12345",
        "https://example.com/search?q=test",
        "https://example.com/cart",
    ]

    for url in test_urls:
        desc = AMITaskPlanner._generate_url_description(url)
        print(f"\n{url}")
        print(f"  → {desc}")


if __name__ == "__main__":
    test_url_descriptions()
