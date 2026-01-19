#!/bin/bash
# Run unified ontology demo
# This script ensures the correct Python path is set

cd "$(dirname "$0")/.."
PYTHONPATH=. python examples/unified_ontology_demo.py
