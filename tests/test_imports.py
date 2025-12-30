#!/usr/bin/env python3
"""Test script to verify imports work correctly."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Test imports
try:
    from decision_service.schemas.request import DecisionRequest
    print("✓ decision_service.schemas.request imported")
except ImportError as e:
    print(f"✗ decision_service.schemas.request failed: {e}")

try:
    from shared.models import DocumentType
    print("✓ shared.models imported")
except ImportError as e:
    print(f"✗ shared.models failed: {e}")

try:
    from decision_service.engine.decision_engine import DecisionEngine
    print("✓ decision_service.engine.decision_engine imported")
except ImportError as e:
    print(f"✗ decision_service.engine.decision_engine failed: {e}")

print(f"\nPython path includes: {project_root}")
print(f"Python executable: {sys.executable}")








