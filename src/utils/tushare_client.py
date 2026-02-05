# ==============================================================================
# 🔌 Tushare 客户端工厂 (src/utils/tushare_client.py)
# 功能：统一处理 Token 认证和代理注入
# ==============================================================================

import tushare as ts
from colorama import Fore

try:
    from src.config.secrets import TUSHARE_TOKEN, TUSHARE_PROXY_URL
except ImportError:
    # 防止因为没创建 secrets.py 导致直接报错
    TUSHARE_TOKEN = ""
    TUSHARE_PROXY_URL = ""


def get_tushare_client():
    """
    初始化 Tushare 接口并自动注入代理
    :return: pro 接口对象 或 None
    """
    if not TUSHARE_TOKEN:
        print(f"{Fore.RED}❌ 缺少配置: 请在 src/config/secrets.py 中配置 TUSHARE_TOKEN")
        return None

    try:
        # 1. 初始化
        pro = ts.pro_api(TUSHARE_TOKEN)

        # 2. 注入代理 (核心黑科技)
        if TUSHARE_PROXY_URL:
            pro._DataApi__http_url = TUSHARE_PROXY_URL
            pro._DataApi__token = TUSHARE_TOKEN  # 双重保险
            print(f"{Fore.GREEN}✅ Tushare 接口已就绪 (代理模式){Fore.RESET}")
        else:
            print(f"{Fore.YELLOW}⚠️ Tushare 未配置代理，使用官方通道 (需积分支持){Fore.RESET}")

        return pro

    except Exception as e:
        print(f"{Fore.RED}❌ Tushare 初始化异常: {e}{Fore.RESET}")
        return None