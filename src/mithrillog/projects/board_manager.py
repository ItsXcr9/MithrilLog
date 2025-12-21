"""
Project Board Manager

Monday.com-compatible project board management:
- Kanban-style boards
- Task tracking with priorities and dependencies
- Timeline/Gantt support
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("mithrillog.projects.board_manager")


class TaskStatus(str, Enum):
    """Task status values (Kanban columns)."""
    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    BLOCKED = "blocked"
    DONE = "done"
    CANCELLED = "cancelled"


class TaskPriority(int, Enum):
    """Task priority levels."""
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4


@dataclass
class Task:
    """A project task."""
    id: str
    board_id: str
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority = TaskPriority.MEDIUM
    assignee: str = ""
    created_by: str = ""
    due_date: Optional[date] = None
    start_date: Optional[date] = None
    estimated_hours: Optional[float] = None
    actual_hours: Optional[float] = None
    dependencies: List[str] = field(default_factory=list)  # Task IDs
    labels: List[str] = field(default_factory=list)
    custom_fields: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "board_id": self.board_id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "priority": self.priority.value,
            "priority_name": self.priority.name.lower(),
            "assignee": self.assignee,
            "created_by": self.created_by,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "estimated_hours": self.estimated_hours,
            "actual_hours": self.actual_hours,
            "dependencies": self.dependencies,
            "labels": self.labels,
            "custom_fields": self.custom_fields,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


@dataclass
class Board:
    """A project board."""
    id: str
    tenant_id: str
    name: str
    description: str = ""
    created_by: str = ""
    task_ids: List[str] = field(default_factory=list)
    columns: List[str] = field(default_factory=lambda: [s.value for s in TaskStatus])
    custom_fields: List[Dict[str, str]] = field(default_factory=list)  # [{name, type}]
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "description": self.description,
            "created_by": self.created_by,
            "task_count": len(self.task_ids),
            "columns": self.columns,
            "custom_fields": self.custom_fields,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class BoardManager:
    """
    Manages project boards and tasks.
    
    Features:
    - Board CRUD
    - Task CRUD with status workflow
    - Dependency tracking
    - Timeline/Gantt export
    """
    
    def __init__(self):
        self._boards: Dict[str, Board] = {}
        self._tasks: Dict[str, Task] = {}
    
    # --- Board Operations ---
    
    def create_board(
        self,
        tenant_id: str,
        name: str,
        description: str = "",
        created_by: str = "",
        custom_fields: List[Dict[str, str]] = None,
    ) -> Board:
        """Create a new project board."""
        board_id = str(uuid.uuid4())
        
        board = Board(
            id=board_id,
            tenant_id=tenant_id,
            name=name,
            description=description,
            created_by=created_by,
            custom_fields=custom_fields or [],
        )
        
        self._boards[board_id] = board
        logger.info(f"Created board: {name} ({board_id})")
        return board
    
    def get_board(self, board_id: str) -> Optional[Board]:
        """Get a board by ID."""
        return self._boards.get(board_id)
    
    def list_boards(self, tenant_id: Optional[str] = None) -> List[Board]:
        """List boards, optionally filtered by tenant."""
        boards = list(self._boards.values())
        
        if tenant_id:
            boards = [b for b in boards if b.tenant_id == tenant_id]
        
        return sorted(boards, key=lambda b: b.updated_at, reverse=True)
    
    def update_board(
        self,
        board_id: str,
        **updates,
    ) -> Optional[Board]:
        """Update a board."""
        board = self._boards.get(board_id)
        if not board:
            return None
        
        for key, value in updates.items():
            if hasattr(board, key) and key not in ("id", "tenant_id", "created_at"):
                setattr(board, key, value)
        
        board.updated_at = datetime.utcnow()
        return board
    
    def delete_board(self, board_id: str) -> bool:
        """Delete a board and all its tasks."""
        board = self._boards.get(board_id)
        if not board:
            return False
        
        # Delete all tasks
        for task_id in board.task_ids:
            if task_id in self._tasks:
                del self._tasks[task_id]
        
        del self._boards[board_id]
        logger.info(f"Deleted board: {board_id}")
        return True
    
    # --- Task Operations ---
    
    def create_task(
        self,
        board_id: str,
        title: str,
        description: str = "",
        created_by: str = "",
        assignee: str = "",
        priority: TaskPriority = TaskPriority.MEDIUM,
        due_date: Optional[date] = None,
        dependencies: List[str] = None,
        labels: List[str] = None,
        custom_fields: Dict[str, Any] = None,
    ) -> Optional[Task]:
        """Create a new task on a board."""
        board = self._boards.get(board_id)
        if not board:
            return None
        
        task_id = str(uuid.uuid4())
        
        task = Task(
            id=task_id,
            board_id=board_id,
            title=title,
            description=description,
            created_by=created_by,
            assignee=assignee,
            priority=priority,
            due_date=due_date,
            dependencies=dependencies or [],
            labels=labels or [],
            custom_fields=custom_fields or {},
        )
        
        self._tasks[task_id] = task
        board.task_ids.append(task_id)
        board.updated_at = datetime.utcnow()
        
        logger.info(f"Created task: {title} ({task_id}) on board {board_id}")
        return task
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID."""
        return self._tasks.get(task_id)
    
    def list_tasks(
        self,
        board_id: Optional[str] = None,
        status: Optional[TaskStatus] = None,
        assignee: Optional[str] = None,
    ) -> List[Task]:
        """List tasks with optional filtering."""
        tasks = list(self._tasks.values())
        
        if board_id:
            tasks = [t for t in tasks if t.board_id == board_id]
        
        if status:
            tasks = [t for t in tasks if t.status == status]
        
        if assignee:
            tasks = [t for t in tasks if t.assignee == assignee]
        
        return sorted(tasks, key=lambda t: (t.priority.value, t.updated_at), reverse=True)
    
    def update_task(
        self,
        task_id: str,
        **updates,
    ) -> Optional[Task]:
        """Update a task."""
        task = self._tasks.get(task_id)
        if not task:
            return None
        
        # Handle status changes
        if "status" in updates:
            new_status = updates["status"]
            if isinstance(new_status, str):
                new_status = TaskStatus(new_status)
            
            if new_status == TaskStatus.DONE and task.status != TaskStatus.DONE:
                task.completed_at = datetime.utcnow()
            elif new_status != TaskStatus.DONE:
                task.completed_at = None
            
            updates["status"] = new_status
        
        # Handle priority
        if "priority" in updates:
            priority = updates["priority"]
            if isinstance(priority, int):
                updates["priority"] = TaskPriority(priority)
        
        for key, value in updates.items():
            if hasattr(task, key) and key not in ("id", "board_id", "created_at"):
                setattr(task, key, value)
        
        task.updated_at = datetime.utcnow()
        
        # Update board timestamp
        board = self._boards.get(task.board_id)
        if board:
            board.updated_at = datetime.utcnow()
        
        return task
    
    def delete_task(self, task_id: str) -> bool:
        """Delete a task."""
        task = self._tasks.get(task_id)
        if not task:
            return False
        
        # Remove from board
        board = self._boards.get(task.board_id)
        if board and task_id in board.task_ids:
            board.task_ids.remove(task_id)
            board.updated_at = datetime.utcnow()
        
        # Remove from other tasks' dependencies
        for other_task in self._tasks.values():
            if task_id in other_task.dependencies:
                other_task.dependencies.remove(task_id)
        
        del self._tasks[task_id]
        logger.info(f"Deleted task: {task_id}")
        return True
    
    def move_task(self, task_id: str, new_status: TaskStatus) -> Optional[Task]:
        """Move a task to a new status column."""
        return self.update_task(task_id, status=new_status)
    
    # --- Board Views ---
    
    def get_kanban_view(self, board_id: str) -> Dict[str, List[Dict]]:
        """Get Kanban view of a board (tasks grouped by status)."""
        board = self._boards.get(board_id)
        if not board:
            return {}
        
        tasks = [self._tasks[tid] for tid in board.task_ids if tid in self._tasks]
        
        kanban = {column: [] for column in board.columns}
        
        for task in tasks:
            status = task.status.value
            if status in kanban:
                kanban[status].append(task.to_dict())
        
        # Sort by priority within each column
        for column in kanban:
            kanban[column].sort(key=lambda t: t["priority"])
        
        return kanban
    
    def get_timeline_view(self, board_id: str) -> List[Dict[str, Any]]:
        """Get timeline/Gantt view of a board."""
        board = self._boards.get(board_id)
        if not board:
            return []
        
        tasks = [self._tasks[tid] for tid in board.task_ids if tid in self._tasks]
        
        # Filter to tasks with dates
        tasks_with_dates = [
            t for t in tasks
            if t.start_date or t.due_date
        ]
        
        timeline = []
        for task in sorted(tasks_with_dates, key=lambda t: t.start_date or t.due_date):
            timeline.append({
                "id": task.id,
                "title": task.title,
                "status": task.status.value,
                "start_date": task.start_date.isoformat() if task.start_date else None,
                "due_date": task.due_date.isoformat() if task.due_date else None,
                "estimated_hours": task.estimated_hours,
                "dependencies": task.dependencies,
                "assignee": task.assignee,
                "priority": task.priority.name.lower(),
            })
        
        return timeline
    
    def get_board_stats(self, board_id: str) -> Dict[str, Any]:
        """Get statistics for a board."""
        board = self._boards.get(board_id)
        if not board:
            return {}
        
        tasks = [self._tasks[tid] for tid in board.task_ids if tid in self._tasks]
        
        by_status = {}
        by_priority = {}
        by_assignee = {}
        
        total_estimated = 0
        total_actual = 0
        overdue_count = 0
        today = date.today()
        
        for task in tasks:
            # By status
            status = task.status.value
            by_status[status] = by_status.get(status, 0) + 1
            
            # By priority
            priority = task.priority.name.lower()
            by_priority[priority] = by_priority.get(priority, 0) + 1
            
            # By assignee
            if task.assignee:
                by_assignee[task.assignee] = by_assignee.get(task.assignee, 0) + 1
            
            # Hours
            if task.estimated_hours:
                total_estimated += task.estimated_hours
            if task.actual_hours:
                total_actual += task.actual_hours
            
            # Overdue
            if task.due_date and task.due_date < today and task.status not in (TaskStatus.DONE, TaskStatus.CANCELLED):
                overdue_count += 1
        
        done_count = by_status.get("done", 0)
        total_count = len(tasks)
        
        return {
            "board_id": board_id,
            "board_name": board.name,
            "total_tasks": total_count,
            "by_status": by_status,
            "by_priority": by_priority,
            "by_assignee": by_assignee,
            "completion_rate": (done_count / total_count * 100) if total_count > 0 else 0,
            "overdue_count": overdue_count,
            "total_estimated_hours": total_estimated,
            "total_actual_hours": total_actual,
        }


# Singleton instance
_board_manager: Optional[BoardManager] = None


def get_board_manager() -> BoardManager:
    """Get or create the singleton BoardManager instance."""
    global _board_manager
    if _board_manager is None:
        _board_manager = BoardManager()
    return _board_manager
