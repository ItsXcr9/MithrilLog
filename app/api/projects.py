"""
MithrilLog Projects API

REST endpoints for:
- Project boards (Monday.com-style)
- Tasks and timeline
- Board views (Kanban, Gantt)
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger("mithrillog.api.projects")

router = APIRouter(prefix="/api/projects", tags=["Projects"])


# --- Request Models ---

class CreateBoardRequest(BaseModel):
    """Create board request."""
    tenant_id: str
    name: str
    description: str = ""
    created_by: str = ""
    custom_fields: List[Dict[str, str]] = []


class UpdateBoardRequest(BaseModel):
    """Update board request."""
    name: Optional[str] = None
    description: Optional[str] = None


class CreateTaskRequest(BaseModel):
    """Create task request."""
    title: str
    description: str = ""
    created_by: str = ""
    assignee: str = ""
    priority: int = Field(3, ge=1, le=4)  # 1=critical, 4=low
    due_date: Optional[date] = None
    start_date: Optional[date] = None
    estimated_hours: Optional[float] = None
    dependencies: List[str] = []
    labels: List[str] = []
    custom_fields: Dict[str, Any] = {}


class UpdateTaskRequest(BaseModel):
    """Update task request."""
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[int] = None
    assignee: Optional[str] = None
    due_date: Optional[date] = None
    start_date: Optional[date] = None
    estimated_hours: Optional[float] = None
    actual_hours: Optional[float] = None
    dependencies: Optional[List[str]] = None
    labels: Optional[List[str]] = None
    custom_fields: Optional[Dict[str, Any]] = None


# --- Board Endpoints ---

@router.post("/boards")
async def create_board(request: CreateBoardRequest):
    """Create a new project board."""
    from mithrillog.projects.board_manager import get_board_manager
    
    manager = get_board_manager()
    board = manager.create_board(
        tenant_id=request.tenant_id,
        name=request.name,
        description=request.description,
        created_by=request.created_by,
        custom_fields=request.custom_fields,
    )
    
    return {"success": True, "board": board.to_dict()}


@router.get("/boards")
async def list_boards(tenant_id: Optional[str] = None):
    """List project boards."""
    from mithrillog.projects.board_manager import get_board_manager
    
    manager = get_board_manager()
    boards = manager.list_boards(tenant_id=tenant_id)
    
    return {
        "count": len(boards),
        "boards": [b.to_dict() for b in boards],
    }


@router.get("/boards/{board_id}")
async def get_board(board_id: str):
    """Get a board with all tasks."""
    from mithrillog.projects.board_manager import get_board_manager
    
    manager = get_board_manager()
    board = manager.get_board(board_id)
    
    if not board:
        raise HTTPException(404, f"Board not found: {board_id}")
    
    tasks = manager.list_tasks(board_id=board_id)
    
    return {
        "board": board.to_dict(),
        "tasks": [t.to_dict() for t in tasks],
    }


@router.patch("/boards/{board_id}")
async def update_board(board_id: str, request: UpdateBoardRequest):
    """Update a board."""
    from mithrillog.projects.board_manager import get_board_manager
    
    manager = get_board_manager()
    updates = request.dict(exclude_unset=True)
    
    board = manager.update_board(board_id, **updates)
    
    if not board:
        raise HTTPException(404, f"Board not found: {board_id}")
    
    return {"success": True, "board": board.to_dict()}


@router.delete("/boards/{board_id}")
async def delete_board(board_id: str):
    """Delete a board."""
    from mithrillog.projects.board_manager import get_board_manager
    
    manager = get_board_manager()
    success = manager.delete_board(board_id)
    
    if not success:
        raise HTTPException(404, f"Board not found: {board_id}")
    
    return {"success": True}


# --- Board Views ---

@router.get("/boards/{board_id}/kanban")
async def get_kanban_view(board_id: str):
    """Get Kanban view (tasks grouped by status)."""
    from mithrillog.projects.board_manager import get_board_manager
    
    manager = get_board_manager()
    board = manager.get_board(board_id)
    
    if not board:
        raise HTTPException(404, f"Board not found: {board_id}")
    
    return {
        "board_id": board_id,
        "board_name": board.name,
        "columns": manager.get_kanban_view(board_id),
    }


@router.get("/boards/{board_id}/timeline")
async def get_timeline_view(board_id: str):
    """Get timeline/Gantt view."""
    from mithrillog.projects.board_manager import get_board_manager
    
    manager = get_board_manager()
    board = manager.get_board(board_id)
    
    if not board:
        raise HTTPException(404, f"Board not found: {board_id}")
    
    return {
        "board_id": board_id,
        "board_name": board.name,
        "timeline": manager.get_timeline_view(board_id),
    }


@router.get("/boards/{board_id}/stats")
async def get_board_stats(board_id: str):
    """Get board statistics."""
    from mithrillog.projects.board_manager import get_board_manager
    
    manager = get_board_manager()
    stats = manager.get_board_stats(board_id)
    
    if not stats:
        raise HTTPException(404, f"Board not found: {board_id}")
    
    return stats


# --- Task Endpoints ---

@router.post("/boards/{board_id}/tasks")
async def create_task(board_id: str, request: CreateTaskRequest):
    """Create a new task."""
    from mithrillog.projects.board_manager import get_board_manager, TaskPriority
    
    manager = get_board_manager()
    
    try:
        priority = TaskPriority(request.priority)
    except ValueError:
        raise HTTPException(400, f"Invalid priority: {request.priority}")
    
    task = manager.create_task(
        board_id=board_id,
        title=request.title,
        description=request.description,
        created_by=request.created_by,
        assignee=request.assignee,
        priority=priority,
        due_date=request.due_date,
        dependencies=request.dependencies,
        labels=request.labels,
        custom_fields=request.custom_fields,
    )
    
    if not task:
        raise HTTPException(404, f"Board not found: {board_id}")
    
    return {"success": True, "task": task.to_dict()}


@router.get("/tasks")
async def list_all_tasks(
    board_id: Optional[str] = None,
    status: Optional[str] = None,
    assignee: Optional[str] = None,
):
    """List tasks with filtering."""
    from mithrillog.projects.board_manager import get_board_manager, TaskStatus
    
    manager = get_board_manager()
    
    status_filter = None
    if status:
        try:
            status_filter = TaskStatus(status)
        except ValueError:
            raise HTTPException(400, f"Invalid status: {status}")
    
    tasks = manager.list_tasks(
        board_id=board_id,
        status=status_filter,
        assignee=assignee,
    )
    
    return {
        "count": len(tasks),
        "tasks": [t.to_dict() for t in tasks],
    }


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    """Get a specific task."""
    from mithrillog.projects.board_manager import get_board_manager
    
    manager = get_board_manager()
    task = manager.get_task(task_id)
    
    if not task:
        raise HTTPException(404, f"Task not found: {task_id}")
    
    return {"task": task.to_dict()}


@router.patch("/tasks/{task_id}")
async def update_task(task_id: str, request: UpdateTaskRequest):
    """Update a task."""
    from mithrillog.projects.board_manager import get_board_manager
    
    manager = get_board_manager()
    updates = request.dict(exclude_unset=True)
    
    task = manager.update_task(task_id, **updates)
    
    if not task:
        raise HTTPException(404, f"Task not found: {task_id}")
    
    return {"success": True, "task": task.to_dict()}


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    """Delete a task."""
    from mithrillog.projects.board_manager import get_board_manager
    
    manager = get_board_manager()
    success = manager.delete_task(task_id)
    
    if not success:
        raise HTTPException(404, f"Task not found: {task_id}")
    
    return {"success": True}


@router.post("/tasks/{task_id}/move")
async def move_task(task_id: str, status: str = Query(...)):
    """Move a task to a new status."""
    from mithrillog.projects.board_manager import get_board_manager, TaskStatus
    
    manager = get_board_manager()
    
    try:
        new_status = TaskStatus(status)
    except ValueError:
        raise HTTPException(400, f"Invalid status: {status}")
    
    task = manager.move_task(task_id, new_status)
    
    if not task:
        raise HTTPException(404, f"Task not found: {task_id}")
    
    return {"success": True, "task": task.to_dict()}


# --- Batch Operations ---

@router.post("/boards/{board_id}/tasks/batch")
async def batch_create_tasks(board_id: str, tasks: List[CreateTaskRequest]):
    """Create multiple tasks at once."""
    from mithrillog.projects.board_manager import get_board_manager, TaskPriority
    
    manager = get_board_manager()
    board = manager.get_board(board_id)
    
    if not board:
        raise HTTPException(404, f"Board not found: {board_id}")
    
    created = []
    for request in tasks:
        priority = TaskPriority(request.priority)
        task = manager.create_task(
            board_id=board_id,
            title=request.title,
            description=request.description,
            created_by=request.created_by,
            assignee=request.assignee,
            priority=priority,
            due_date=request.due_date,
            dependencies=request.dependencies,
            labels=request.labels,
            custom_fields=request.custom_fields,
        )
        if task:
            created.append(task.to_dict())
    
    return {
        "success": True,
        "created_count": len(created),
        "tasks": created,
    }
