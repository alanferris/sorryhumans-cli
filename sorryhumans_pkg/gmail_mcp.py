"""Sorry, humans — Gmail MCP server.

Exposes the connected user's Gmail to the agent as MCP tools (search, read,
create draft) so the agent can act on email in plain language — only at the
user's request. The agent NEVER sees the OAuth token: this server fetches a
short-lived access token from the bus, which holds the refresh token
server-side, using the project's api_key + the connected member's uid.

Transport: stdio. Wired by the connector, e.g.:
  claude mcp add gmail --env SORRYHUMANS_KEY=... --env SORRYHUMANS_TEAM_ID=... \
    --env SORRYHUMANS_MEMBER_UID=... -- python3 -m sorryhumans_pkg.gmail_mcp
"""
from __future__ import annotations

import base64
import os
from email.message import EmailMessage

import httpx
from mcp.server.fastmcp import FastMCP

BUS = os.environ.get("SORRYHUMANS_BUS", "https://api.sorryhumans.dev")
KEY = os.environ.get("SORRYHUMANS_KEY", "")
TEAM_ID = os.environ.get("SORRYHUMANS_TEAM_ID", "")
MEMBER_UID = os.environ.get("SORRYHUMANS_MEMBER_UID", "")
GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"

mcp = FastMCP(
    "gmail",
    instructions=(
        "Gmail tools for the connected user's own mailbox. Use them only when the user "
        "asks (e.g. 'search my inbox', 'summarize this thread', 'draft a reply'). "
        "gmail_create_draft creates a DRAFT and never sends without the user."
    ),
)


def _access_token() -> str:
    """Mint a short-lived Gmail access token via the bus (refresh stays server-side)."""
    r = httpx.get(
        f"{BUS}/v1/projects/{TEAM_ID}/integrations/gmail/access-token",
        params={"uid": MEMBER_UID},
        headers={"Authorization": f"Bearer {KEY}"},
        timeout=20,
    )
    if r.status_code == 404:
        raise RuntimeError("Gmail is not connected for this user/project. Connect it in the Tools tab.")
    r.raise_for_status()
    return r.json()["access_token"]


def _auth() -> dict:
    return {"Authorization": f"Bearer {_access_token()}"}


def _extract_body(payload: dict) -> str:
    """Walk a Gmail payload tree for the first text/plain body."""
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data.encode()).decode("utf-8", "replace")
    for part in payload.get("parts", []) or []:
        text = _extract_body(part)
        if text:
            return text
    return ""


@mcp.tool()
def gmail_search(query: str = "", max_results: int = 10) -> dict:
    """Search the user's Gmail. `query` uses Gmail search syntax
    (e.g. 'from:alice newer_than:7d', 'subject:invoice'). Returns id + from/subject/date/snippet."""
    with httpx.Client(timeout=30) as c:
        headers = _auth()
        r = c.get(f"{GMAIL}/messages", params={"q": query, "maxResults": max_results}, headers=headers)
        r.raise_for_status()
        out = []
        for m in r.json().get("messages", []):
            mr = c.get(
                f"{GMAIL}/messages/{m['id']}",
                params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]},
                headers=headers,
            )
            if mr.is_success:
                j = mr.json()
                hdr = {h["name"]: h["value"] for h in j.get("payload", {}).get("headers", [])}
                out.append({
                    "id": m["id"], "from": hdr.get("From", ""), "subject": hdr.get("Subject", ""),
                    "date": hdr.get("Date", ""), "snippet": j.get("snippet", ""),
                })
        return {"messages": out, "count": len(out)}


@mcp.tool()
def gmail_read(message_id: str) -> dict:
    """Read a full Gmail message by id — headers plus the plain-text body."""
    with httpx.Client(timeout=30) as c:
        r = c.get(f"{GMAIL}/messages/{message_id}", params={"format": "full"}, headers=_auth())
        r.raise_for_status()
        j = r.json()
        hdr = {h["name"]: h["value"] for h in j.get("payload", {}).get("headers", [])}
        return {
            "id": message_id, "from": hdr.get("From", ""), "to": hdr.get("To", ""),
            "subject": hdr.get("Subject", ""), "date": hdr.get("Date", ""),
            "body": _extract_body(j.get("payload", {})),
        }


@mcp.tool()
def gmail_create_draft(to: str, subject: str, body: str) -> dict:
    """Create a Gmail DRAFT (never sends). Returns the draft id; the user reviews/sends it."""
    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    with httpx.Client(timeout=30) as c:
        r = c.post(f"{GMAIL}/drafts", json={"message": {"raw": raw}}, headers=_auth())
        r.raise_for_status()
        return {"draft_id": r.json().get("id"), "status": "draft created (not sent)"}


if __name__ == "__main__":
    mcp.run()  # stdio
