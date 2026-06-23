from __future__ import annotations

import getpass

from app.auth import auth_store


def main() -> None:
    print("Create or update a local fallback account")
    username = input("Username: ").strip()
    display_name = input("Display name (optional): ").strip() or username
    password = getpass.getpass("Password (minimum 12 characters): ")
    confirmation = getpass.getpass("Confirm password: ")

    if password != confirmation:
        raise SystemExit("Passwords do not match.")

    try:
        auth_store.create_or_update_local_user(username, password, display_name)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    print(f"Local fallback account '{username}' is ready.")


if __name__ == "__main__":
    main()
