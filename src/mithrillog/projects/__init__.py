"""
MithrilLog Projects Module

Project management features:
- Monday.com-style project boards
- Task and timeline management
- Meeting tracking
- Document generation
"""

from .board_manager import BoardManager, Board, Task

__all__ = [
    "BoardManager",
    "Board",
    "Task",
]
