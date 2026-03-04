import asyncio
from datetime import UTC, datetime, timedelta

import tushare as ts


STOCK_BASIC_FIELDS = (
    "ts_code,symbol,name,area,industry,fullname,enname,cnspell,market,exchange,"
    "curr_type,list_status,list_date,delist_date,is_hs,act_name,act_ent_type"
)


class TushareGateway:
    def __init__(self, token: str) -> None:
        self._token = token.strip()
        if not self._token:
            raise ValueError("TUSHARE_TOKEN is required for stock sync")
        self._client = ts.pro_api(self._token)

    async def fetch_stock_basic_by_status(
        self, list_status: str
    ) -> list[dict[str, str]]:
        def _run() -> list[dict[str, str]]:
            frame = self._client.stock_basic(
                exchange="",
                list_status=list_status,
                fields=STOCK_BASIC_FIELDS,
            )
            return frame.to_dict(orient="records")

        return await asyncio.to_thread(_run)

    async def fetch_recent_open_trade_dates(self, limit: int) -> list[str]:
        def _run() -> list[str]:
            end_date = datetime.now(UTC).strftime("%Y%m%d")
            start_date = (datetime.now(UTC) - timedelta(days=500)).strftime("%Y%m%d")
            frame = self._client.trade_cal(
                exchange="SSE",
                start_date=start_date,
                end_date=end_date,
                is_open="1",
                fields="cal_date",
            )
            values = [str(item["cal_date"]) for item in frame.to_dict(orient="records")]
            values.sort(reverse=True)
            return values[:limit]

        return await asyncio.to_thread(_run)

    async def fetch_daily_for_trade_date(
        self, trade_date: str
    ) -> list[dict[str, str | float]]:
        def _run() -> list[dict[str, str | float]]:
            frame = self._client.daily(
                trade_date=trade_date,
                fields="ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount",
            )
            return frame.to_dict(orient="records")

        return await asyncio.to_thread(_run)

    async def fetch_daily_basic_for_trade_date(
        self, trade_date: str
    ) -> list[dict[str, str | float]]:
        def _run() -> list[dict[str, str | float]]:
            frame = self._client.daily_basic(
                trade_date=trade_date,
                fields="ts_code,trade_date,turnover_rate,volume_ratio,pe,pb,total_mv,circ_mv",
            )
            return frame.to_dict(orient="records")

        return await asyncio.to_thread(_run)

    async def fetch_daily_by_range(
        self,
        *,
        ts_code: str,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, str | float]]:
        def _run() -> list[dict[str, str | float]]:
            frame = self._client.daily(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                fields=(
                    "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount"
                ),
            )
            return frame.to_dict(orient="records")

        return await asyncio.to_thread(_run)

    async def fetch_weekly_by_range(
        self,
        *,
        ts_code: str,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, str | float]]:
        def _run() -> list[dict[str, str | float]]:
            frame = self._client.weekly(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                fields=(
                    "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount"
                ),
            )
            return frame.to_dict(orient="records")

        return await asyncio.to_thread(_run)

    async def fetch_monthly_by_range(
        self,
        *,
        ts_code: str,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, str | float]]:
        def _run() -> list[dict[str, str | float]]:
            frame = self._client.monthly(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                fields=(
                    "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount"
                ),
            )
            return frame.to_dict(orient="records")

        return await asyncio.to_thread(_run)

    async def fetch_trade_cal_by_range(
        self,
        *,
        exchange: str,
        start_date: str,
        end_date: str,
        is_open: str | None,
    ) -> list[dict[str, str]]:
        def _run() -> list[dict[str, str]]:
            frame = self._client.trade_cal(
                exchange=exchange,
                start_date=start_date,
                end_date=end_date,
                is_open=is_open,
                fields="exchange,cal_date,is_open,pretrade_date",
            )
            return frame.to_dict(orient="records")

        return await asyncio.to_thread(_run)

    async def fetch_adj_factor_by_range(
        self,
        *,
        ts_code: str,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, str | float]]:
        def _run() -> list[dict[str, str | float]]:
            frame = self._client.adj_factor(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                fields="ts_code,trade_date,adj_factor",
            )
            return frame.to_dict(orient="records")

        return await asyncio.to_thread(_run)
