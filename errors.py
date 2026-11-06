"""Safe, actionable service errors; never expose provider bodies or credentials."""


def friendly_error(error):
    status = getattr(error, "status_code", None)
    if status in (401, 403):
        return "密钥无效或没有访问权限，请在侧栏更新 DeepSeek API 密钥。"
    if status == 402:
        return "DeepSeek 余额不足，请充值后重试。"
    if status == 429:
        return "DeepSeek 暂时限流或额度不足，请检查账户后稍候重试。"
    if isinstance(error, (TimeoutError, ConnectionError, OSError)) or "Timeout" in type(error).__name__ or "Connection" in type(error).__name__:
        return "连接超时或网络不可用，请检查网络后重试。"
    return "服务未返回可用结果，请稍候重试；已完成的结果会保留。"
