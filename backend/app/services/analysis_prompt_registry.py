ANALYSIS_PROMPT_VERSION = "stock-analysis-v1"


def get_analysis_prompt_version() -> str:
    # 统一在注册表里固定 prompt 版本，避免版本号散落在多处逻辑中。
    return ANALYSIS_PROMPT_VERSION
