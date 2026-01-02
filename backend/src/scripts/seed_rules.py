#!/usr/bin/env python3
"""
Seed the database with initial rules from a JSON file.

Usage:
    poetry run python -m scripts.seed_rules
    poetry run python -m scripts.seed_rules --file config/rules.json
    poetry run python -m scripts.seed_rules --file /run/secrets/rules.json
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.models import Base, Ruleset, RulesConfig

load_dotenv()

# Default paths to check for rules file
DEFAULT_RULES_PATHS = [
    "config/rules.json",
    "/run/secrets/rules.json",
]


def get_database_url() -> str:
    """Get database URL from environment."""
    url = os.getenv("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL environment variable is required")
    return url


def load_rules_file(file_path: str) -> dict:
    """Load and validate rules from JSON file."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Rules file not found: {file_path}")

    with open(path) as f:
        rules_dict = json.load(f)

    # Validate by attempting to create RulesConfig
    try:
        RulesConfig(**rules_dict)
    except TypeError as e:
        raise ValueError(f"Invalid rules format: {e}")

    return rules_dict


def compute_rules_hash(rules_dict: dict) -> str:
    """Compute a deterministic hash of the rules."""
    # Sort keys for deterministic serialization
    rules_json = json.dumps(rules_dict, sort_keys=True)
    return hashlib.sha256(rules_json.encode()).hexdigest()[:16]


def find_rules_file() -> str:
    """Find the first existing rules file from default paths."""
    for path in DEFAULT_RULES_PATHS:
        if Path(path).exists():
            return path
    raise FileNotFoundError(
        f"No rules file found. Checked: {', '.join(DEFAULT_RULES_PATHS)}"
    )


def seed_rules(file_path: str | None = None, force: bool = False) -> None:
    """
    Seed the database with rules from a JSON file.

    Args:
        file_path: Path to rules JSON file. If None, searches default locations.
        force: If True, insert even if rules with same hash exist.
    """
    # Find rules file
    if file_path is None:
        file_path = find_rules_file()

    print(f"Loading rules from: {file_path}")
    rules_dict = load_rules_file(file_path)
    rules_hash = compute_rules_hash(rules_dict)

    print(f"Rules hash: {rules_hash}")
    print(f"Rules config: {json.dumps(rules_dict, indent=2)}")

    # Connect to database
    database_url = get_database_url()
    engine = create_engine(database_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine)

    with SessionLocal() as session:
        # Check if rules with this hash already exist
        existing = session.execute(
            select(Ruleset).where(Ruleset.hash == rules_hash)
        ).scalar_one_or_none()

        if existing and not force:
            print(f"Rules with hash {rules_hash} already exist (id={existing.id}, version={existing.version})")
            print("Use --force to insert anyway.")
            return

        # Get the next version number
        latest = session.execute(
            select(Ruleset).order_by(Ruleset.version.desc()).limit(1)
        ).scalar_one_or_none()

        next_version = (latest.version + 1) if latest else 1

        # Insert new ruleset
        new_ruleset = Ruleset(
            version=next_version,
            hash=rules_hash,
            ruleset=rules_dict,
        )
        session.add(new_ruleset)
        session.commit()

        print(f"✓ Inserted ruleset version {next_version} with hash {rules_hash}")


def main():
    parser = argparse.ArgumentParser(
        description="Seed the database with rules from a JSON file."
    )
    parser.add_argument(
        "--file", "-f",
        type=str,
        default=None,
        help="Path to rules JSON file. Defaults to searching config/rules.json and /run/secrets/rules.json"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Insert rules even if the same hash already exists"
    )

    args = parser.parse_args()
    seed_rules(file_path=args.file, force=args.force)


if __name__ == "__main__":
    main()

