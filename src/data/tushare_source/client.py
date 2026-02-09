# ==============================================================================
# 🔌 Tushare 连接客户端 (src/data/tushare_source/client.py)
# ==============================================================================
import tushare as ts
from colorama import Fore

# 尝试导入密钥
try:
    from src.config.secrets import TUSHARE_TOKEN, TUSHARE_PROXY_URL
except ImportError:
    TUSHARE_TOKEN = ""
    TUSHARE_PROXY_URL = ""

class TushareClient:
    _pro = None

    @classmethod
    def get_pro(cls):
        """单例模式获取 Pro 接口"""
        if cls._pro:
            return cls._pro

        if not TUSHARE_TOKEN:
            print(f"{Fore.RED}❌ 缺少配置: 请在 src/config/secrets.py 中配置 TUSHARE_TOKEN")
            return None

        try:
            # 1. 初始化
            pro = ts.pro_api(TUSHARE_TOKEN)

            # 2. 注入代理 (如果配置了)
            if TUSHARE_PROXY_URL:
                pro._DataApi__http_url = TUSHARE_PROXY_URL
                pro._DataApi__token = TUSHARE_TOKEN
                print(f"{Fore.GREEN}✅ Tushare 接口已就绪 (代理模式){Fore.RESET}")
            else:
                print(f"{Fore.YELLOW}⚠️ Tushare 未配置代理，使用官方通道{Fore.RESET}")

            cls._pro = pro
            return pro
        except Exception as e:
            print(f"{Fore.RED}❌ Tushare 初始化异常: {e}{Fore.RESET}")
            return None