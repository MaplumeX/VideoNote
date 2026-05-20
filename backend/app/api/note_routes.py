"""Routes for tags, folders, and note organization."""

import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.auth import TokenData, get_current_user
from app.db import (
    add_tags_to_note,
    batch_add_tag,
    batch_move_to_folder,
    batch_remove_tag,
    batch_set_favorite,
    count_user_tasks,
    create_folder,
    create_tag,
    delete_folder,
    delete_tag,
    get_folder_by_id,
    get_folder_tree,
    get_folders_by_user,
    get_or_create_tag_by_name,
    get_tag_by_id,
    get_tags_by_user,
    get_tags_for_note,
    get_task,
    get_user_tasks,
    move_note_to_folder,
    remove_tag_from_note,
    toggle_favorite,
    update_folder,
    update_note_content,
    update_tag,
)
from app.schemas import (
    BatchFavoriteRequest,
    BatchMoveRequest,
    BatchTagRequest,
    FavoriteToggle,
    FolderCreate,
    FolderResponse,
    FolderUpdate,
    FolderWithChildren,
    NoteContentUpdate,
    NoteFolderUpdate,
    NoteResponse,
    NoteTagAdd,
    TagCreate,
    TagResponse,
    TagUpdate,
    TagWithCount,
    TaskListItem,
    TaskListResponse,
)
from app.services.markdown import normalize_note_markdown

CurrentUser = Annotated[TokenData, Depends(get_current_user)]

router = APIRouter(tags=["notes"])


# --- Tag endpoints ---


@router.get("/tags", response_model=list[TagWithCount])
async def list_tags(user: CurrentUser):
    """List all tags for the current user with note counts."""
    tags = await get_tags_by_user(user.user_id)
    return [TagWithCount(**t) for t in tags]


@router.post("/tags", response_model=TagResponse)
async def create_tag_endpoint(req: TagCreate, user: CurrentUser):
    """Create a new tag."""
    tag_id = str(uuid.uuid4())
    try:
        tag = await create_tag(tag_id, user.user_id, req.name, req.color)
    except Exception as exc:
        # UNIQUE constraint violation
        if "UNIQUE constraint" in str(exc):
            raise HTTPException(status_code=409, detail="Tag name already exists") from exc
        raise
    return TagResponse(**tag)


@router.get("/tags/{tag_id}", response_model=TagWithCount)
async def get_tag(tag_id: str, user: CurrentUser):
    """Get a tag by ID."""
    tag = await get_tag_by_id(tag_id)
    if not tag or tag["user_id"] != user.user_id:
        raise HTTPException(status_code=404, detail="Tag not found")
    # Get note count
    tags = await get_tags_by_user(user.user_id)
    for t in tags:
        if t["id"] == tag_id:
            return TagWithCount(**t)
    return TagWithCount(note_count=0, **tag)


@router.put("/tags/{tag_id}", response_model=TagResponse)
async def update_tag_endpoint(tag_id: str, req: TagUpdate, user: CurrentUser):
    """Update a tag's name and/or color."""
    tag = await get_tag_by_id(tag_id)
    if not tag or tag["user_id"] != user.user_id:
        raise HTTPException(status_code=404, detail="Tag not found")
    try:
        updated = await update_tag(tag_id, name=req.name, color=req.color)
    except Exception as exc:
        if "UNIQUE constraint" in str(exc):
            raise HTTPException(status_code=409, detail="Tag name already exists") from exc
        raise
    if not updated:
        raise HTTPException(status_code=404, detail="Tag not found")
    return TagResponse(**updated)


@router.delete("/tags/{tag_id}")
async def delete_tag_endpoint(tag_id: str, user: CurrentUser):
    """Delete a tag. Removes all note associations."""
    tag = await get_tag_by_id(tag_id)
    if not tag or tag["user_id"] != user.user_id:
        raise HTTPException(status_code=404, detail="Tag not found")
    deleted = await delete_tag(tag_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Tag not found")
    return {"detail": "Tag deleted"}


@router.get("/tags/{tag_id}/notes", response_model=TaskListResponse)
async def get_notes_by_tag(
    tag_id: str,
    user: CurrentUser,
    page: int = 1,
    limit: int = 20,
):
    """List notes with a specific tag."""
    tag = await get_tag_by_id(tag_id)
    if not tag or tag["user_id"] != user.user_id:
        raise HTTPException(status_code=404, detail="Tag not found")
    if page < 1:
        page = 1
    if limit < 1 or limit > 100:
        limit = 20
    offset = (page - 1) * limit
    tasks = await get_user_tasks(user.user_id, limit=limit, offset=offset, tag_id=tag_id)
    total = await count_user_tasks(user.user_id, tag_id=tag_id)
    return TaskListResponse(
        items=[TaskListItem(**t) for t in tasks],
        total=total,
        page=page,
        limit=limit,
    )


# --- Folder endpoints ---


@router.get("/folders", response_model=list[FolderResponse])
async def list_folders(user: CurrentUser):
    """List all folders for the current user as a flat list."""
    folders = await get_folders_by_user(user.user_id)
    return [FolderResponse(**f) for f in folders]


@router.get("/folders/tree", response_model=list[FolderWithChildren])
async def get_folders_tree(user: CurrentUser):
    """Get folder tree with note counts."""
    tree = await get_folder_tree(user.user_id)
    return [FolderWithChildren(**f) for f in tree]


@router.post("/folders", response_model=FolderResponse)
async def create_folder_endpoint(req: FolderCreate, user: CurrentUser):
    """Create a new folder."""
    # Validate parent_id if provided
    if req.parent_id:
        parent = await get_folder_by_id(req.parent_id)
        if not parent or parent["user_id"] != user.user_id:
            raise HTTPException(status_code=404, detail="Parent folder not found")
    folder_id = str(uuid.uuid4())
    folder = await create_folder(
        folder_id, user.user_id, req.name, req.parent_id, req.sort_order,
    )
    return FolderResponse(**folder)


@router.get("/folders/{folder_id}", response_model=FolderResponse)
async def get_folder(folder_id: str, user: CurrentUser):
    """Get a folder by ID."""
    folder = await get_folder_by_id(folder_id)
    if not folder or folder["user_id"] != user.user_id:
        raise HTTPException(status_code=404, detail="Folder not found")
    return FolderResponse(**folder)


@router.put("/folders/{folder_id}", response_model=FolderResponse)
async def update_folder_endpoint(folder_id: str, req: FolderUpdate, user: CurrentUser):
    """Update a folder's name and/or move it to a different parent."""
    folder = await get_folder_by_id(folder_id)
    if not folder or folder["user_id"] != user.user_id:
        raise HTTPException(status_code=404, detail="Folder not found")
    # Validate new parent if provided
    if req.parent_id is not None and req.parent_id:
        parent = await get_folder_by_id(req.parent_id)
        if not parent or parent["user_id"] != user.user_id:
            raise HTTPException(status_code=404, detail="Parent folder not found")
    try:
        updated = await update_folder(folder_id, name=req.name, parent_id=req.parent_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="Folder not found")
    return FolderResponse(**updated)


@router.delete("/folders/{folder_id}")
async def delete_folder_endpoint(folder_id: str, user: CurrentUser):
    """Delete a folder. Subfolders are also deleted; notes become uncategorized."""
    folder = await get_folder_by_id(folder_id)
    if not folder or folder["user_id"] != user.user_id:
        raise HTTPException(status_code=404, detail="Folder not found")
    deleted = await delete_folder(folder_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Folder not found")
    return {"detail": "Folder deleted"}


@router.get("/folders/{folder_id}/notes", response_model=TaskListResponse)
async def get_notes_by_folder(
    folder_id: str,
    user: CurrentUser,
    page: int = 1,
    limit: int = 20,
):
    """List notes in a specific folder."""
    folder = await get_folder_by_id(folder_id)
    if not folder or folder["user_id"] != user.user_id:
        raise HTTPException(status_code=404, detail="Folder not found")
    if page < 1:
        page = 1
    if limit < 1 or limit > 100:
        limit = 20
    offset = (page - 1) * limit
    tasks = await get_user_tasks(user.user_id, limit=limit, offset=offset, folder_id=folder_id)
    total = await count_user_tasks(user.user_id, folder_id=folder_id)
    return TaskListResponse(
        items=[TaskListItem(**t) for t in tasks],
        total=total,
        page=page,
        limit=limit,
    )


# --- Note-tag association endpoints ---


@router.get("/tasks/{job_id}/tags")
async def get_note_tags_endpoint(job_id: str, user: CurrentUser):
    """Get all tags for a note."""
    task = await get_task(job_id)
    if not task or task.get("user_id") != user.user_id:
        raise HTTPException(status_code=404, detail="Task not found")
    tags = await get_tags_for_note(job_id)
    return {"tags": [TagResponse(**t) for t in tags]}


@router.post("/tasks/{job_id}/tags")
async def add_tags_to_note_endpoint(job_id: str, req: NoteTagAdd, user: CurrentUser):
    """Add tags to a note. Supports both tag_ids and tag_names (auto-create)."""
    task = await get_task(job_id)
    if not task or task.get("user_id") != user.user_id:
        raise HTTPException(status_code=404, detail="Task not found")

    all_tag_ids: list[str] = list(req.tag_ids)

    # Auto-create tags by name
    for name in req.tag_names:
        tag = await get_or_create_tag_by_name(user.user_id, name)
        if tag["id"] not in all_tag_ids:
            all_tag_ids.append(tag["id"])

    if all_tag_ids:
        await add_tags_to_note(job_id, all_tag_ids)

    # Return updated tags
    tags = await get_tags_for_note(job_id)
    return {"tags": [TagResponse(**t) for t in tags]}


@router.delete("/tasks/{job_id}/tags/{tag_id}")
async def remove_tag_from_note_endpoint(job_id: str, tag_id: str, user: CurrentUser):
    """Remove a tag from a note."""
    task = await get_task(job_id)
    if not task or task.get("user_id") != user.user_id:
        raise HTTPException(status_code=404, detail="Task not found")
    removed = await remove_tag_from_note(job_id, tag_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Tag not associated with this note")
    return {"detail": "Tag removed"}


# --- Note folder/favorite endpoints ---


@router.put("/tasks/{job_id}/folder")
async def move_note_to_folder_endpoint(job_id: str, req: NoteFolderUpdate, user: CurrentUser):
    """Move a note to a folder. Set folder_id to null to uncategorize."""
    task = await get_task(job_id)
    if not task or task.get("user_id") != user.user_id:
        raise HTTPException(status_code=404, detail="Task not found")

    if req.folder_id:
        folder = await get_folder_by_id(req.folder_id)
        if not folder or folder["user_id"] != user.user_id:
            raise HTTPException(status_code=404, detail="Folder not found")

    updated = await move_note_to_folder(job_id, req.folder_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"detail": "Note moved"}


@router.put("/tasks/{job_id}/favorite")
async def toggle_favorite_endpoint(job_id: str, req: FavoriteToggle, user: CurrentUser):
    """Set or unset favorite on a note."""
    task = await get_task(job_id)
    if not task or task.get("user_id") != user.user_id:
        raise HTTPException(status_code=404, detail="Task not found")

    updated = await toggle_favorite(job_id, req.is_favorite)
    if not updated:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"detail": "Favorite updated"}


@router.put("/tasks/{job_id}/content", response_model=NoteResponse)
async def update_note_content_endpoint(job_id: str, req: NoteContentUpdate, user: CurrentUser):
    """Update the markdown content of a note."""
    task = await get_task(job_id)
    if not task or task.get("user_id") != user.user_id:
        raise HTTPException(status_code=404, detail="Task not found")

    result_raw = task.get("result_json")
    if not result_raw:
        raise HTTPException(status_code=400, detail="Note has no content to update")

    markdown = normalize_note_markdown(req.markdown)
    updated = await update_note_content(job_id, markdown, req.title)
    if not updated:
        raise HTTPException(status_code=404, detail="Task not found")

    # Return the updated note
    result = json.loads(result_raw)
    new_title = req.title if req.title is not None else result.get("title")
    return NoteResponse(job_id=job_id, markdown=markdown, title=new_title)


# --- Batch operation endpoints ---
# These must be defined before /tasks/{job_id} routes in the main router to avoid shadowing.
# Since this router is mounted separately, we use explicit /batch paths.


@router.post("/tasks/batch/tag")
async def batch_tag_endpoint(req: BatchTagRequest, user: CurrentUser):
    """Add a tag to multiple notes."""
    tag = await get_tag_by_id(req.tag_id)
    if not tag or tag["user_id"] != user.user_id:
        raise HTTPException(status_code=404, detail="Tag not found")

    # Verify all tasks belong to user
    for job_id in req.job_ids:
        task = await get_task(job_id)
        if not task or task.get("user_id") != user.user_id:
            raise HTTPException(status_code=404, detail=f"Task {job_id} not found")

    await batch_add_tag(req.job_ids, req.tag_id)
    return {"detail": "Tag added to all notes"}


@router.post("/tasks/batch/untag")
async def batch_remove_tag_endpoint(req: BatchTagRequest, user: CurrentUser):
    """Remove a tag from multiple notes."""
    tag = await get_tag_by_id(req.tag_id)
    if not tag or tag["user_id"] != user.user_id:
        raise HTTPException(status_code=404, detail="Tag not found")

    for job_id in req.job_ids:
        task = await get_task(job_id)
        if not task or task.get("user_id") != user.user_id:
            raise HTTPException(status_code=404, detail=f"Task {job_id} not found")

    await batch_remove_tag(req.job_ids, req.tag_id)
    return {"detail": "Tag removed from all notes"}


@router.post("/tasks/batch/move")
async def batch_move_endpoint(req: BatchMoveRequest, user: CurrentUser):
    """Move multiple notes to a folder."""
    if req.folder_id:
        folder = await get_folder_by_id(req.folder_id)
        if not folder or folder["user_id"] != user.user_id:
            raise HTTPException(status_code=404, detail="Folder not found")

    for job_id in req.job_ids:
        task = await get_task(job_id)
        if not task or task.get("user_id") != user.user_id:
            raise HTTPException(status_code=404, detail=f"Task {job_id} not found")

    await batch_move_to_folder(req.job_ids, req.folder_id)
    return {"detail": "Notes moved"}


@router.post("/tasks/batch/favorite")
async def batch_favorite_endpoint(req: BatchFavoriteRequest, user: CurrentUser):
    """Set favorite on multiple notes."""
    for job_id in req.job_ids:
        task = await get_task(job_id)
        if not task or task.get("user_id") != user.user_id:
            raise HTTPException(status_code=404, detail=f"Task {job_id} not found")

    await batch_set_favorite(req.job_ids, req.is_favorite)
    return {"detail": "Favorites updated"}
