from datetime import datetime
import hashlib
import re


SOURCE_COVERAGE_MAP: dict[str, str] = {
    "akshare": "AK",
    "tushare": "TS",
    "internal": "IN",
}


def normalize_provider(provider: str | None, source: str | None = None) -> str:
    provider_text = str(provider or "").strip().lower()
    source_text = str(source or "").strip().lower()
    if provider_text and provider_text != "internal":
        return provider_text
    if "tushare" in source_text:
        return "tushare"
    if source_text:
        return "akshare"
    return "internal"


def providers_to_source_coverage(providers: list[str]) -> str:
    # 聚合来源标签用于显示覆盖面，不暴露具体源列表。
    normalized = sorted(
        {normalize_provider(provider) for provider in providers if provider}
    )
    if not normalized:
        return "IN"
    labels = [SOURCE_COVERAGE_MAP.get(provider, provider.upper()) for provider in normalized]
    return "+".join(labels)


def _normalize_title(title: str) -> str:
    # 标题规范化用于聚类，去掉常见媒体尾缀与噪声符号。
    lowered = title.strip().lower()
    lowered = re.sub(r"[：:|｜\-—_·•\s]+", "", lowered)
    lowered = re.sub(r"(财联社|证券时报|东方财富|巨潮资讯|央视新闻)$", "", lowered)
    return lowered


def build_cluster_key(
    *,
    title: str,
    published_at: datetime | None,
    macro_topic: str | None,
) -> str:
    # 聚类键以“标题+日期+主题”稳定生成，避免跨日误并。
    normalized_date = (published_at or datetime.min).strftime("%Y%m%d")
    normalized_title = _normalize_title(title)
    digest = hashlib.sha1(
        f"{normalized_title}|{normalized_date}|{macro_topic or ''}".encode("utf-8")
    ).hexdigest()
    return digest[:24]
