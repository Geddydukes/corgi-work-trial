"""
Standardized error handling for route handlers.

Provides consistent error handling patterns across all routes.
"""

import logging
import functools
from fastapi import HTTPException
from typing import Callable, TypeVar, Any

logger = logging.getLogger(__name__)

T = TypeVar('T')


def handle_route_errors(func: Callable[..., T]) -> Callable[..., T]:
    """
    Decorator for standardizing error handling in route handlers.
    
    Ensures:
    - HTTPException is re-raised as-is
    - All other exceptions are logged and converted to 500 errors
    - Consistent error messages
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs) -> T:
        try:
            return await func(*args, **kwargs)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                f"Error in {func.__name__}: {str(e)}",
                exc_info=True
            )
            raise HTTPException(
                status_code=500,
                detail=f"Internal server error: {str(e)}"
            )
    return wrapper


