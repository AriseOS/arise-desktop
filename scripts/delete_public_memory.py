"""Delete all public memory data by connecting directly to SurrealDB.

Usage:
    python scripts/delete_public_memory.py [--url URL] [--namespace NS] [--user USER] [--password PASS] [--yes]

Examples:
    python scripts/delete_public_memory.py
    python scripts/delete_public_memory.py --url ws://localhost:8000/rpc --yes
"""
import argparse
import asyncio
import os


# Tables to delete, edges first then nodes (same order as clear_memory endpoint)
EDGE_TABLES = ["action", "has_instance", "has_sequence", "manages"]
NODE_TABLES = ["state", "pageinstance", "domain", "cognitivephrase", "intentsequence"]


async def delete_public_memory(url: str, namespace: str, username: str, password: str):
    from surrealdb import AsyncSurreal

    client = AsyncSurreal(url)
    await client.connect()
    await client.signin({"username": username, "password": password})
    await client.use(namespace, "public")

    print(f"Connected: {url}/{namespace}/public")
    print()

    # Delete edges first
    for table in EDGE_TABLES:
        result = await client.query(f"DELETE FROM {table} RETURN BEFORE")
        count = len(result) if result and isinstance(result, list) else 0
        print(f"  {table:20s} deleted {count}")

    # Delete nodes
    total = {}
    for table in NODE_TABLES:
        result = await client.query(f"DELETE FROM {table} RETURN BEFORE")
        count = len(result) if result and isinstance(result, list) else 0
        total[table] = count
        print(f"  {table:20s} deleted {count}")

    print()
    print("Done.")


def main():
    parser = argparse.ArgumentParser(description="Delete all public memory (direct SurrealDB)")
    parser.add_argument("--url", default=os.getenv("SURREALDB_URL", "ws://localhost:8000/rpc"))
    parser.add_argument("--namespace", default=os.getenv("SURREALDB_NAMESPACE", "ami"))
    parser.add_argument("--user", default=os.getenv("SURREALDB_USER", "root"))
    parser.add_argument("--password", default=os.getenv("SURREALDB_PASSWORD", ""))
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()

    if not args.yes:
        answer = input(
            "This will DELETE ALL data from public memory "
            f"({args.url}/{args.namespace}/public). Continue? [y/N] "
        )
        if answer.strip().lower() != "y":
            print("Aborted.")
            return

    asyncio.run(delete_public_memory(args.url, args.namespace, args.user, args.password))


if __name__ == "__main__":
    main()
