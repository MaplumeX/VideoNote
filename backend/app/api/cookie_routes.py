"""Cookie management routes for per-user video platform cookies."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile

from app.auth import TokenData, get_current_user
from app.crypto import encrypt_api_key
from app.db import (
    delete_user_cookie,
    get_all_user_cookies,
    save_user_cookie,
)
from app.schemas import CookieInfoResponse

CurrentUser = Annotated[TokenData, Depends(get_current_user)]

router = APIRouter(prefix="/cookies", tags=["cookies"])

ALLOWED_PLATFORMS = {"youtube", "bilibili"}

# Domain allowlists for each platform
PLATFORM_DOMAINS: dict[str, list[str]] = {
    "youtube": [
        ".youtube.com",
        "youtube.com",
        ".google.com",
        "google.com",
        ".googleapis.com",
        "googleapis.com",
    ],
    "bilibili": [
        ".bilibili.com",
        "bilibili.com",
        ".b23.tv",
        "b23.tv",
        ".hdslb.com",
        "hdslb.com",
    ],
}


def _domain_matches(domain: str, allowed: list[str]) -> bool:
    """Check if a cookie domain matches any entry in the allowlist.

    Netscape cookies.txt domains may or may not have a leading dot.
    A domain like '.youtube.com' should match cookies for 'youtube.com' and
    '.youtube.com'. Conversely, 'youtube.com' should also match '.youtube.com'.
    """
    # Normalize: ensure leading dot for comparison
    norm = domain if domain.startswith(".") else f".{domain}"
    for entry in allowed:
        entry_norm = entry if entry.startswith(".") else f".{entry}"
        if norm == entry_norm or norm.endswith(entry_norm):
            return True
    return False


def _filter_cookies_by_platform(cookies_txt: str, platform: str) -> str:
    """Filter Netscape cookies.txt content to keep only entries matching the platform's domains.

    Each non-comment, non-empty line has tab-separated fields:
    domain\\tflag\\tpath\\tsecure\\texpiry\\tname\\tvalue
    """
    allowed = PLATFORM_DOMAINS.get(platform, [])
    lines = cookies_txt.splitlines()
    result: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            result.append(line)
            continue
        parts = stripped.split("\t")
        if len(parts) < 7:
            # Not a valid cookies.txt entry, skip
            continue
        domain = parts[0]
        if _domain_matches(domain, allowed):
            result.append(line)
    return "\n".join(result)


def _raw_cookie_to_netscape(cookie_str: str, platform: str) -> str:
    """Convert a raw cookie string (e.g. 'key1=val1; key2=val2') to Netscape cookies.txt format.

    Uses the platform's default domain.
    """
    domain = "youtube.com" if platform == "youtube" else "bilibili.com"
    lines: list[str] = []
    for pair in cookie_str.split(";"):
        pair = pair.strip()
        if not pair:
            continue
        if "=" not in pair:
            continue
        name, _, value = pair.partition("=")
        name = name.strip()
        value = value.strip()
        # domain  flag  path  secure  expiry  name  value
        lines.append(f".{domain}\tTRUE\t/\tTRUE\t0\t{name}\t{value}")
    if not lines:
        return ""
    return "# Netscape HTTP Cookie File\n" + "\n".join(lines)


def _parse_and_normalize_cookie(content: str, platform: str) -> str:
    """Parse cookie content: detect if it's Netscape format or raw cookie string,
    then filter by platform domains.

    Returns the filtered Netscape cookies.txt content.
    """
    stripped = content.strip()
    if not stripped:
        return ""

    # Heuristic: if it contains tab characters, treat as Netscape format
    if "\t" in stripped:
        filtered = _filter_cookies_by_platform(stripped, platform)
    else:
        # Treat as raw cookie string
        netscape = _raw_cookie_to_netscape(stripped, platform)
        if not netscape:
            return ""
        filtered = _filter_cookies_by_platform(netscape, platform)

    # Check that at least one cookie entry remains after filtering
    has_entries = any(
        line.strip() and not line.strip().startswith("#")
        for line in filtered.splitlines()
    )
    if not has_entries:
        return ""

    return filtered


@router.put("/{platform}")
async def save_cookie(
    platform: str,
    user: CurrentUser,
    request: Request,
):
    """Save cookie for a platform. Accepts either a file upload or a JSON body with cookie_text."""
    if platform not in ALLOWED_PLATFORMS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported platform: {platform}. "
            f"Allowed: {', '.join(sorted(ALLOWED_PLATFORMS))}",
        )

    content_type = (request.headers.get("content-type") or "").lower()
    content = ""

    if "multipart/form-data" in content_type:
        form = await request.form()
        file = form.get("file")
        if not file or not isinstance(file, UploadFile):
            raise HTTPException(
                status_code=422,
                detail="Provide a file upload named 'file'",
            )
        raw = await file.read()
        if len(raw) > 1024 * 1024:
            raise HTTPException(status_code=413, detail="Cookie file too large (max 1MB)")
        content = raw.decode("utf-8", errors="replace")
    elif "application/json" in content_type:
        body = await request.json()
        cookie_text = body.get("cookie_text", "")
        if not cookie_text:
            raise HTTPException(
                status_code=422,
                detail="Provide cookie_text in JSON body",
            )
        content = cookie_text
    else:
        raise HTTPException(
            status_code=422,
            detail="Content-Type must be multipart/form-data or application/json",
        )

    filtered = _parse_and_normalize_cookie(content, platform)
    if not filtered:
        raise HTTPException(
            status_code=422,
            detail=f"No valid cookie entries found for {platform} after domain filtering",
        )

    encrypted = encrypt_api_key(filtered)
    await save_user_cookie(user.user_id, platform, encrypted)

    return {"detail": "Cookie saved", "platform": platform}


@router.get("", response_model=list[CookieInfoResponse])
async def list_cookies(user: CurrentUser):
    """List user's cookies (platform and existence indicator, not content)."""
    records = await get_all_user_cookies(user.user_id)
    result = []
    for r in records:
        result.append(CookieInfoResponse(
            platform=r["platform"],
            has_cookie=True,
            updated_at=r["updated_at"],
        ))
    # Also include platforms without cookies so the frontend can show both
    existing_platforms = {r["platform"] for r in records}
    for p in sorted(ALLOWED_PLATFORMS):
        if p not in existing_platforms:
            result.append(CookieInfoResponse(platform=p, has_cookie=False, updated_at=None))
    return result


@router.delete("/{platform}")
async def delete_cookie(platform: str, user: CurrentUser):
    """Delete cookie for a platform."""
    if platform not in ALLOWED_PLATFORMS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported platform: {platform}",
        )
    deleted = await delete_user_cookie(user.user_id, platform)
    if not deleted:
        raise HTTPException(status_code=404, detail="No cookie found for this platform")
    return {"detail": "Cookie deleted", "platform": platform}
