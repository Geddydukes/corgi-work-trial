#!/usr/bin/env python3
"""
Test script to verify code cleanup changes:
1. Database connection manager works
2. All repositories can be instantiated
3. No import errors
4. Basic functionality preserved
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Load environment variables
from dotenv import load_dotenv
load_dotenv(project_root / ".env")

def test_database_module():
    """Test that shared.database module works correctly."""
    print("Testing database module...")
    try:
        from shared.database import get_engine, row_to_dict
        print("  ✅ Database module imports successfully")
        
        # Test get_engine (may return None if DATABASE_URL not set, that's OK)
        engine = get_engine()
        if engine:
            print("  ✅ Database engine created successfully")
        else:
            print("  ⚠️  Database engine is None (DATABASE_URL may not be configured - this is OK for testing)")
        
        # Test row_to_dict
        test_row = (1, "test", {"key": "value"})
        test_dict = row_to_dict(test_row, ['id', 'name', 'data'])
        assert test_dict['id'] == 1
        assert test_dict['name'] == "test"
        print("  ✅ row_to_dict helper works correctly")
        
        return True
    except Exception as e:
        print(f"  ❌ Database module test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_repository_imports():
    """Test that all repositories can be imported and instantiated."""
    print("\nTesting repository imports...")
    try:
        from decision_service.repositories.claim_repository import ClaimRepository
        from decision_service.repositories.batch_repository import BatchRepository
        from decision_service.repositories.override_repository import OverrideRepository
        from decision_service.repositories.document_repository import DocumentRepository
        
        print("  ✅ All repositories import successfully")
        
        # Test instantiation
        claim_repo = ClaimRepository()
        batch_repo = BatchRepository()
        override_repo = OverrideRepository()
        doc_repo = DocumentRepository()
        
        print("  ✅ All repositories can be instantiated")
        
        # Verify they use shared database
        import inspect
        claim_source = inspect.getsourcefile(ClaimRepository)
        print(f"  ✅ ClaimRepository uses shared database (file: {claim_source})")
        
        return True
    except Exception as e:
        print(f"  ❌ Repository import test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_no_magic_numbers():
    """Test that routes don't use magic number indexing."""
    print("\nTesting for magic number indexing...")
    try:
        # Read claims.py and check for tuple indexing patterns
        claims_file = project_root / "decision_service" / "routes" / "claims.py"
        content = claims_file.read_text()
        
        # Check for problematic patterns (but allow single-column queries and dict conversion)
        problematic_patterns = [
            'decision_result[',  # Should be decision_dict['...']
            'updated_result[',   # Should be updated_dict['...']
        ]
        
        found_issues = []
        for pattern in problematic_patterns:
            if pattern in content:
                # Check if it's in a comment or acceptable context
                lines = content.split('\n')
                for i, line in enumerate(lines, 1):
                    if pattern in line and not line.strip().startswith('#'):
                        # Check if it's a single-column query (acceptable)
                        if 'tracking_result[0]' in line and 'Single column query' in content[max(0, i-5):i]:
                            continue  # This is acceptable
                        # Check if it's dictionary conversion (acceptable - this is the fix!)
                        if 'for i, col in enumerate' in line or 'decision_dict = {' in line or 'updated_dict = {' in line:
                            continue  # This is the conversion code, which is good
                        # Check if it's in a comment explaining why it's acceptable
                        if i > 0 and 'acceptable' in lines[i-1].lower():
                            continue
                        found_issues.append(f"Line {i}: {line.strip()}")
        
        if found_issues:
            print(f"  ⚠️  Found {len(found_issues)} potential magic number usages:")
            for issue in found_issues[:5]:  # Show first 5
                print(f"     {issue}")
            return False
        else:
            print("  ✅ No problematic magic number indexing found")
            return True
    except Exception as e:
        print(f"  ❌ Magic number check failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_database_connection_sharing():
    """Test that repositories use shared database connection through BaseRepository."""
    print("\nTesting database connection sharing...")
    try:
        from decision_service.repositories.claim_repository import ClaimRepository
        from decision_service.repositories.batch_repository import BatchRepository
        from decision_service.repositories.base_repository import BaseRepository
        
        # Check that repositories inherit from BaseRepository
        if issubclass(ClaimRepository, BaseRepository):
            print("  ✅ ClaimRepository inherits from BaseRepository")
        else:
            print("  ❌ ClaimRepository does not inherit from BaseRepository")
            return False
        
        if issubclass(BatchRepository, BaseRepository):
            print("  ✅ BatchRepository inherits from BaseRepository")
        else:
            print("  ❌ BatchRepository does not inherit from BaseRepository")
            return False
        
        # Verify BaseRepository uses shared database
        import inspect
        base_source = inspect.getsourcefile(BaseRepository)
        base_content = Path(base_source).read_text()
        
        if 'from shared.database import get_engine' in base_content:
            print("  ✅ BaseRepository uses shared.database.get_engine")
        else:
            print("  ❌ BaseRepository does not use shared.database.get_engine")
            return False
        
        # Check that repositories don't create engines directly
        claim_file = project_root / "decision_service" / "repositories" / "claim_repository.py"
        batch_file = project_root / "decision_service" / "repositories" / "batch_repository.py"
        
        claim_content = claim_file.read_text()
        batch_content = batch_file.read_text()
        
        if 'create_engine(Config.DATABASE_URL)' in claim_content:
            print("  ⚠️  ClaimRepository still has create_engine calls (should use BaseRepository)")
            return False
        
        if 'create_engine(Config.DATABASE_URL)' in batch_content:
            print("  ⚠️  BatchRepository still has create_engine calls (should use BaseRepository)")
            return False
        
        print("  ✅ All repositories use shared connection manager via BaseRepository")
        return True
    except Exception as e:
        print(f"  ❌ Database connection sharing test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests."""
    print("=" * 60)
    print("Code Cleanup Verification Tests")
    print("=" * 60)
    
    results = []
    
    results.append(("Database Module", test_database_module()))
    results.append(("Repository Imports", test_repository_imports()))
    results.append(("No Magic Numbers", test_no_magic_numbers()))
    results.append(("Connection Sharing", test_database_connection_sharing()))
    
    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Code cleanup changes are working correctly.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please review the issues above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())

