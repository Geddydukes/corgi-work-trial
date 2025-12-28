#!/usr/bin/env python3
"""
Infrastructure Check Script

Verifies that all required infrastructure components are running and configured correctly:
- PostgreSQL database connection
- Redis connection
- Gemini API key (if Tier 3 OCR enabled)
- Database schema (tables exist)
- Required environment variables
"""

import os
import sys
from pathlib import Path
from typing import List, Tuple
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def check_postgres(db_url: str) -> Tuple[bool, str]:
    """Check PostgreSQL connection and schema."""
    try:
        from sqlalchemy import create_engine, text, inspect
        
        engine = create_engine(db_url)
        
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            logger.info(f"✓ PostgreSQL connected: {version.split(',')[0]}")
            
            inspector = inspect(engine)
            required_tables = [
                'claims',
                'claim_documents',
                'decisions',
                'decision_validation'
            ]
            
            existing_tables = inspector.get_table_names(schema='claims')
            if not existing_tables:
                existing_tables = inspector.get_table_names()
            
            missing_tables = []
            for table in required_tables:
                if table not in existing_tables:
                    missing_tables.append(table)
                else:
                    logger.info(f"  ✓ Table '{table}' exists")
            
            if missing_tables:
                return False, f"Missing tables: {', '.join(missing_tables)}"
            
            row_count = conn.execute(text("SELECT COUNT(*) FROM claims")).scalar()
            logger.info(f"  ✓ Found {row_count} claims in database")
            
            return True, "PostgreSQL is ready"
    
    except ImportError:
        return False, "sqlalchemy not installed. Run: pip install sqlalchemy psycopg2-binary"
    except Exception as e:
        return False, f"PostgreSQL connection failed: {str(e)}"


def check_redis(redis_url: str) -> Tuple[bool, str]:
    """Check Redis connection."""
    try:
        import redis
        
        r = redis.from_url(redis_url)
        r.ping()
        logger.info("✓ Redis connected")
        return True, "Redis is ready"
    
    except ImportError:
        return False, "redis not installed. Run: pip install redis"
    except Exception as e:
        return False, f"Redis connection failed: {str(e)}"


def check_gemini_api_key() -> Tuple[bool, str]:
    """Check if Gemini API key is configured."""
    api_key = os.getenv('GEMINI_API_KEY')
    
    if not api_key or api_key == 'your_gemini_api_key_here':
        return False, "GEMINI_API_KEY not set in environment. Add it to .env file"
    
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        models = list(genai.list_models())
        logger.info("✓ Gemini API key is valid")
        return True, "Gemini API is ready"
    
    except ImportError:
        return False, "google-generativeai not installed. Run: pip install google-generativeai"
    except Exception as e:
        error_msg = str(e).lower()
        if 'api key' in error_msg or 'invalid' in error_msg:
            return False, f"Gemini API key is invalid: {str(e)}"
        return False, f"Gemini API check failed: {str(e)}"


def check_environment_variables() -> Tuple[bool, List[str]]:
    """Check required environment variables."""
    required_vars = {
        'DATABASE_URL': 'PostgreSQL connection string',
        'REDIS_URL': 'Redis connection string',
    }
    
    optional_vars = {
        'GEMINI_API_KEY': 'Required if OCR_TIER3_ENABLED=true',
        'OCR_TIER3_ENABLED': 'Enable Tier 3 OCR (default: false)',
    }
    
    missing = []
    warnings = []
    
    for var, description in required_vars.items():
        if not os.getenv(var):
            missing.append(f"{var} ({description})")
        else:
            logger.info(f"✓ {var} is set")
    
    tier3_enabled = os.getenv('OCR_TIER3_ENABLED', 'false').lower() == 'true'
    if tier3_enabled:
        if not os.getenv('GEMINI_API_KEY') or os.getenv('GEMINI_API_KEY') == 'your_gemini_api_key_here':
            warnings.append("OCR_TIER3_ENABLED=true but GEMINI_API_KEY is not set")
    
    return len(missing) == 0, missing + warnings


def check_docker_services() -> Tuple[bool, str]:
    """Check if Docker services are running."""
    try:
        import subprocess
        
        result = subprocess.run(
            ['docker', 'ps', '--format', '{{.Names}}'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode != 0:
            return False, "Docker is not running or docker command not available"
        
        running_services = result.stdout.strip().split('\n')
        expected_services = ['corgi-postgres', 'corgi-redis']
        
        found_services = []
        for service in expected_services:
            if service in running_services:
                found_services.append(service)
                logger.info(f"✓ Docker service '{service}' is running")
            else:
                logger.warning(f"✗ Docker service '{service}' is not running")
        
        if len(found_services) == len(expected_services):
            return True, "All required Docker services are running"
        else:
            missing = set(expected_services) - set(found_services)
            return False, f"Missing Docker services: {', '.join(missing)}. Run: docker-compose up -d"
    
    except FileNotFoundError:
        return False, "Docker command not found. Install Docker or run services manually"
    except Exception as e:
        return False, f"Docker check failed: {str(e)}"


def load_env_file() -> bool:
    """Load .env file if it exists."""
    env_file = Path('.env')
    if env_file.exists():
        logger.info(f"Loading environment from .env file")
        from dotenv import load_dotenv
        load_dotenv()
        return True
    else:
        logger.warning(".env file not found. Create one from .env.example")
        return False


def main():
    """Run all infrastructure checks."""
    logger.info("=" * 60)
    logger.info("Infrastructure Check")
    logger.info("=" * 60)
    
    load_env_file()
    
    checks = []
    
    env_ok, env_issues = check_environment_variables()
    checks.append(("Environment Variables", env_ok, env_issues))
    
    docker_ok, docker_msg = check_docker_services()
    checks.append(("Docker Services", docker_ok, [docker_msg] if not docker_ok else []))
    
    db_url = os.getenv('DATABASE_URL')
    if db_url:
        db_ok, db_msg = check_postgres(db_url)
        checks.append(("PostgreSQL", db_ok, [db_msg] if not db_ok else []))
    else:
        checks.append(("PostgreSQL", False, ["DATABASE_URL not set"]))
    
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    redis_ok, redis_msg = check_redis(redis_url)
    checks.append(("Redis", redis_ok, [redis_msg] if not redis_ok else []))
    
    tier3_enabled = os.getenv('OCR_TIER3_ENABLED', 'false').lower() == 'true'
    if tier3_enabled:
        gemini_ok, gemini_msg = check_gemini_api_key()
        checks.append(("Gemini API", gemini_ok, [gemini_msg] if not gemini_ok else []))
    else:
        logger.info("ℹ OCR_TIER3_ENABLED=false, skipping Gemini API check")
        checks.append(("Gemini API", True, []))
    
    logger.info("=" * 60)
    logger.info("Summary:")
    logger.info("=" * 60)
    
    all_passed = True
    for name, passed, issues in checks:
        status = "✓ PASS" if passed else "✗ FAIL"
        logger.info(f"{status}: {name}")
        if issues:
            for issue in issues:
                logger.info(f"  - {issue}")
            all_passed = False
    
    logger.info("=" * 60)
    
    if all_passed:
        logger.info("✓ All infrastructure checks passed!")
        return 0
    else:
        logger.error("✗ Some infrastructure checks failed. Please fix the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

