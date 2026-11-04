"""Postgres. For now the service only asks whether the database answers; later lessons store data in it."""

import logging

import psycopg
from psycopg_pool import AsyncConnectionPool

log = logging.getLogger("ledgerlens.api")


async def open_pool(url: str) -> AsyncConnectionPool:
    """Open a small pool of connections without waiting for Postgres.

    The pool connects in the background and keeps retrying, so the service starts even while the
    database is down and recovers on its own when it comes back.
    """
    pool = AsyncConnectionPool(
        url,
        min_size=1,
        max_size=4,
        open=False,
        # Before handing out a connection, test it with a tiny query. One that died while Postgres
        # restarted is thrown away and replaced, instead of failing whoever asked for it.
        check=AsyncConnectionPool.check_connection,
        # After a failed connection the pool waits about 1 s, then 2, 4, 8... before trying again, until
        # reconnect_timeout has passed; then it gives up, and the next request starts again from 1 s.
        # With the default (300 s) the waits grew past a minute, so the service stayed unready long after
        # Postgres was back. With 10 s, readiness returned 2-10 s after Postgres did (lesson 1.4).
        reconnect_timeout=10,
        name="ledgerlens",
    )
    await pool.open(wait=False)
    return pool


async def answers(pool: AsyncConnectionPool) -> bool:
    """True if Postgres runs a query within a second. Readiness asks this on every call."""
    try:
        async with pool.connection(timeout=1.0) as conn:
            await conn.execute("SELECT 1")
    except psycopg.Error as err:  # includes the pool's own timeout
        log.warning("database not answering", extra={"fields": {"error": type(err).__name__}})
        return False
    return True
