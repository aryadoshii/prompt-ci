"""
Sends HTML regression report via Composio Gmail.
Uses Composio SDK v1.0.0-rc2 (tools.execute API).
"""

from composio import Composio
from config.settings import COMPOSIO_API_KEY


def _get_gmail_account(client: Composio) -> tuple[str, str] | tuple[None, None]:
    """Return (account_id, user_id) for the first active Gmail connection."""
    try:
        accounts = client.connected_accounts.list()
        for item in accounts.items:
            if item.toolkit.slug == "gmail" and item.status == "ACTIVE":
                return item.id, item.user_id
    except Exception:
        pass
    return None, None


def _get_gmail_version(client: Composio) -> str:
    """Return the latest available Gmail toolkit version."""
    try:
        toolkit = client.toolkits.get(slug="gmail")
        versions = toolkit.meta.available_versions
        return versions[0] if versions else "20260330_00"
    except Exception:
        return "20260330_00"


def send_report_email(
    to: str,
    subject: str,
    html_body: str,
    run_id: str,  # noqa: ARG001 — reserved for future per-run tracking
) -> dict:
    """Send the regression report email using Composio Gmail."""
    try:
        client = Composio(api_key=COMPOSIO_API_KEY)
        account_id, user_id = _get_gmail_account(client)

        if not account_id:
            return {"success": False, "error": "No active Gmail account connected in Composio"}

        version = _get_gmail_version(client)

        response = client.tools.execute(
            slug="GMAIL_SEND_EMAIL",
            arguments={
                "recipient_email": to,
                "subject": subject,
                "body": html_body,
                "is_html": True,
            },
            connected_account_id=account_id,
            user_id=user_id,
            version=version,
        )

        # ToolExecutionResponse has a .data dict and a .error field
        if hasattr(response, "error") and response.error:
            return {"success": False, "error": str(response.error)}

        return {"success": True, "error": ""}

    except Exception as e:
        return {"success": False, "error": str(e)}


def get_gmail_status() -> dict:
    """Returns {"connected": bool, "email": str}"""
    try:
        client = Composio(api_key=COMPOSIO_API_KEY)
        account_id, _ = _get_gmail_account(client)
        if account_id:
            return {"connected": True, "email": f"Connected (account: {account_id})"}
        return {"connected": False, "email": "No active Gmail connected in Composio"}
    except Exception as e:
        return {"connected": False, "email": f"Error: {str(e)}"}
