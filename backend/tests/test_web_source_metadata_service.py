from datetime import UTC, datetime, timedelta

import asyncio

import httpx
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import async_sessionmaker

from conftest import build_sqlite_test_context, init_sqlite_schema

from app.db.base import Base
from app.services.web_source_metadata_service import (
    enrich_web_sources,
)


def test_enrich_web_sources_extracts_source_and_published_at(tmp_path) -> None:
    db_file = tmp_path / "web-source-metadata.db"
    db_url = f"sqlite+aiosqlite:///{db_file.as_posix()}"
    engine, session_maker = build_sqlite_test_context(tmp_path, "web-source-metadata.db")

    html = """
    <html>
      <head>
        <title>国际油价收涨</title>
        <meta property="og:site_name" content="Reuters" />
        <meta property="article:published_time" content="2026-03-24T09:30:00Z" />
      </head>
      <body>市场继续关注供给端扰动。</body>
    </html>
    """

    async def run_test() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                status_code=200,
                headers={"content-type": "text/html; charset=utf-8"},
                text=html,
                request=request,
            )
        )
        async with httpx.AsyncClient(transport=transport) as client:
            async with session_maker() as session:
                result = await enrich_web_sources(
                    session=session,
                    raw_sources=[
                        {
                            "title": "国际油价收涨",
                            "url": "https://finance.example.com/oil",
                            "source": None,
                            "published_at": None,
                            "snippet": "市场继续关注供给端扰动。",
                        }
                    ],
                    http_client=client,
                    timeout_seconds=3,
                    success_ttl_seconds=86400,
                    failure_ttl_seconds=7200,
                    max_bytes=1024 * 512,
                )

                assert result[0]["source"] == "Reuters"
                assert result[0]["domain"] == "finance.example.com"
                assert result[0]["metadata_status"] == "enriched"
                assert result[0]["published_at"].startswith("2026-03-24")


    asyncio.run(run_test())


def test_enrich_web_sources_falls_back_to_domain_and_uses_cache(tmp_path) -> None:
    db_file = tmp_path / "web-source-cache.db"
    db_url = f"sqlite+aiosqlite:///{db_file.as_posix()}"
    engine, session_maker = build_sqlite_test_context(tmp_path, "web-source-cache.db")
    call_count = {"count": 0}

    async def run_test() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            table_names = await connection.run_sync(
                lambda sync_conn: inspect(sync_conn).get_table_names()
            )
            assert "web_source_metadata_cache" in table_names

        def handler(request: httpx.Request) -> httpx.Response:
            call_count["count"] += 1
            return httpx.Response(
                status_code=200,
                headers={"content-type": "text/html; charset=utf-8"},
                text="<html><head><title>Only Title</title></head><body></body></html>",
                request=request,
            )

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            async with session_maker() as session:
                first_result = await enrich_web_sources(
                    session=session,
                    raw_sources=[
                        {
                            "title": None,
                            "url": "https://unknown.example.com/report",
                            "source": None,
                            "published_at": None,
                            "snippet": None,
                        }
                    ],
                    http_client=client,
                    timeout_seconds=3,
                    success_ttl_seconds=86400,
                    failure_ttl_seconds=7200,
                    max_bytes=1024 * 512,
                )
                second_result = await enrich_web_sources(
                    session=session,
                    raw_sources=[
                        {
                            "title": None,
                            "url": "https://unknown.example.com/report",
                            "source": None,
                            "published_at": None,
                            "snippet": None,
                        }
                    ],
                    http_client=client,
                    timeout_seconds=3,
                    success_ttl_seconds=86400,
                    failure_ttl_seconds=7200,
                    max_bytes=1024 * 512,
                )

                assert first_result[0]["source"] == "unknown.example.com"
                assert first_result[0]["metadata_status"] == "domain_inferred"
                assert second_result[0]["source"] == "unknown.example.com"
                assert call_count["count"] == 1


    asyncio.run(run_test())


def test_enrich_web_sources_marks_unavailable_for_non_html(tmp_path) -> None:
    db_file = tmp_path / "web-source-unavailable.db"
    db_url = f"sqlite+aiosqlite:///{db_file.as_posix()}"
    engine, session_maker = build_sqlite_test_context(tmp_path, "web-source-unavailable.db")

    async def run_test() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                status_code=200,
                headers={"content-type": "application/pdf"},
                content=b"%PDF-1.7",
                request=request,
            )
        )
        async with httpx.AsyncClient(transport=transport) as client:
            async with session_maker() as session:
                result = await enrich_web_sources(
                    session=session,
                    raw_sources=[
                        {
                            "title": "PDF 引用",
                            "url": "https://files.example.com/report.pdf",
                            "source": None,
                            "published_at": None,
                            "snippet": None,
                        }
                    ],
                    http_client=client,
                    timeout_seconds=3,
                    success_ttl_seconds=86400,
                    failure_ttl_seconds=7200,
                    max_bytes=1024 * 512,
                )

                assert result[0]["metadata_status"] == "unavailable"
                assert result[0]["source"] == "files.example.com"
                assert result[0]["published_at"] is None


    asyncio.run(run_test())


def test_enrich_web_sources_fetches_uncached_urls_concurrently_and_keeps_order(
    tmp_path,
) -> None:
    db_file = tmp_path / "web-source-concurrency.db"
    db_url = f"sqlite+aiosqlite:///{db_file.as_posix()}"
    engine, session_maker = build_sqlite_test_context(tmp_path, "web-source-concurrency.db")
    active_requests = {"count": 0, "max": 0}
    requested_urls: list[str] = []

    async def run_test() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async def handler(request: httpx.Request) -> httpx.Response:
            requested_urls.append(str(request.url))
            active_requests["count"] += 1
            active_requests["max"] = max(
                active_requests["max"],
                active_requests["count"],
            )
            await asyncio.sleep(0.05)
            active_requests["count"] -= 1
            title = request.url.path.strip("/")
            return httpx.Response(
                status_code=200,
                headers={"content-type": "text/html; charset=utf-8"},
                text=(
                    "<html><head>"
                    f"<title>{title}</title>"
                    "<meta property='og:site_name' content='Example News' />"
                    "</head><body></body></html>"
                ),
                request=request,
            )

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            async with session_maker() as session:
                result = await enrich_web_sources(
                    session=session,
                    raw_sources=[
                        {
                            "title": None,
                            "url": "https://news.example.com/first",
                            "source": None,
                            "published_at": None,
                            "snippet": None,
                        },
                        {
                            "title": None,
                            "url": "https://news.example.com/second",
                            "source": None,
                            "published_at": None,
                            "snippet": None,
                        },
                        {
                            "title": None,
                            "url": "https://news.example.com/third",
                            "source": None,
                            "published_at": None,
                            "snippet": None,
                        },
                    ],
                    http_client=client,
                    timeout_seconds=3,
                    success_ttl_seconds=86400,
                    failure_ttl_seconds=7200,
                    max_bytes=1024 * 512,
                )

                assert [item["title"] for item in result] == [
                    "first",
                    "second",
                    "third",
                ]
                assert active_requests["max"] > 1
                assert requested_urls == [
                    "https://news.example.com/first",
                    "https://news.example.com/second",
                    "https://news.example.com/third",
                ]


    asyncio.run(run_test())
