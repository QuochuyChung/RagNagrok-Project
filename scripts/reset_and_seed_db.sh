#!/usr/bin/env bash

set -Eeuo pipefail

# Run reset & seed script inside gateway container
docker compose exec gateway python scripts/reset_and_seed_db.py

