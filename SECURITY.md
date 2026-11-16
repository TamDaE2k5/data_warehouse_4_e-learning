# Security scope

This is a local learning and portfolio project using synthetic data. It is not an authenticated multi-user service.

The Compose file binds published database and dashboard ports to `127.0.0.1`. Keep them local. Do not expose the stack through a public tunnel or bind it to all interfaces without adding authentication, authorization, TLS and network controls appropriate to the deployment.

Demo passwords in `.env.example` are public development defaults. Set distinct local passwords before creating volumes. Changing an environment variable after a database volume exists does not by itself rotate the database role's password. Never commit `.env` or reuse a real service password.

The ETL source reader and staging roles are separate. ClickHouse credentials used by the local app are still privileged; a read-only interface is not a substitute for a restricted database account. Runner and dashboard containers disable privilege escalation, but this does not establish a hardened production boundary.

Failure tests intentionally update and delete data and terminate a process mid-publication. Use `python scripts/verify.py`; its project and artifact guards prevent ordinary configuration from enabling these scenarios accidentally. Do not disable the guard to run them on important data.

For a suspected vulnerability, contact the repository owner privately through their GitHub profile. Do not put credentials, exploitable personal data or access tokens into a public issue. No response-time or production support commitment is implied.
