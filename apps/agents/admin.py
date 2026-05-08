"""Agents app — no admin registrations.

The Agent and AgentCommand models exist for authorization, JWT issuance and
rescan-command queueing, but are deliberately NOT exposed through the Django
Admin. The web UI is kept minimal: only Assets and Scans are user-facing.

Operational tasks (revoking an agent, issuing a rescan) go through:
  - the API: POST /api/v1/assets/{id}/rescan
  - or services in apps.agents.services (revoke_agent, issue_rescan_command)
    accessible via Django shell or custom management commands.
"""
