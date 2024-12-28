#!/usr/bin/env sh

set -exu

INITIAL_REVISION=f0f76bb9b563

# If no upgrade fails assume db is with initial schema without `alembic_version` table.
alembic upgrade head || alembic stamp $INITIAL_REVISION

lmbatbot
