# ==============================================================================
# 🛠️ 文本处理工具 (src/utils/text_tools.py)
# 负责代码格式化、标签清洗、概念提取
# ==============================================================================

import re
import os
from colorama import Fore

# 导入配置以获取关键词和映射表
# 注意：确保你的 Python 环境能解析到 src 包，或者在根目录下运行
try:
    from src.config.settings import Config
except ImportError:
    # 备用方案：如果相对导入失败，尝试从当前路径计算
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from src.config.settings import Config

class TextUtils:
    @staticmethod
    def format_sina_code(code: str) -> str:
        """将 6 位数字代码转换为新浪接口格式 (sz/sh/bj)"""
        code = str(code)
        if code.startswith('6'): return f"sh{code}"
        if code.startswith(('8', '4')): return f"bj{code}"
        return f"sz{code}"

    @staticmethod
    def get_link_dragon(code: str) -> str:
        """获取关联的大哥代码 (依赖 Config 配置)"""
        if code in Config.HOLDING_STRATEGIES:
            dragon = Config.HOLDING_STRATEGIES[code][1]
            if dragon: return dragon

        dragon = Config.LINK_DRAGON_MAP.get(code, '')
        if dragon:
            if dragon.startswith(('sz', 'sh')): return dragon
            return TextUtils.format_sina_code(dragon)
        return ''

    @staticmethod
    def clean_manual_tag(tag: str, is_zt_tag_present: bool) -> str:
        """清洗手工填写的标签，去除重复的板数描述"""
        if not tag: return ""
        if tag.startswith("F佬/"):
            tag = tag[3:]
        elif tag.startswith("F佬"):
            tag = tag.lstrip("F佬").lstrip("/")

        if is_zt_tag_present:
            # 如果程序已经识别了涨停，就去掉手工备注里的 "2板", "(3板)" 等字样
            tag = re.sub(r'(^|/|[(])\d+板([)]|/|$)', r'\1\2', tag)
            tag = tag.replace('()', '').replace('//', '/').replace('(/', '(').replace('/)', ')')
            tag = tag.strip('/')
        return tag

    @staticmethod
    def get_unique_concepts(base_str: str, new_concepts_str: str) -> str:
        """合并概念，避免重复"""
        if not new_concepts_str: return ""
        base_parts = re.split(r'[/()]', base_str)
        base_set = set(p.strip() for p in base_parts if p.strip())

        final_new = []
        for c in new_concepts_str.split('/'):
            c = c.strip()
            if c and c not in base_set and c not in base_str:
                final_new.append(c)
        return "/".join(final_new)

    @staticmethod
    def get_core_concepts_local(name: str, raw_tag: str) -> str:
        """根据 Config.CORE_KEYWORDS 提取核心概念"""
        matched = set()
        source_text = f"{name} {raw_tag}"
        for key in Config.CORE_KEYWORDS:
            if key in source_text:
                matched.add(key)
        return "/".join(list(matched))

    @staticmethod
    def load_text_list(filepath: str) -> dict:
        """加载 txt 格式的股票列表 (code tag)"""
        if not os.path.exists(filepath): return {}
        mapping = {}
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'): continue
                    parts = re.split(r'\s+', line, maxsplit=1)
                    code = parts[0].strip().replace("SZ", "").replace("SH", "")
                    if code.isdigit() and len(code) == 6:
                        tag = parts[1].strip() if len(parts) > 1 else "关注"
                        mapping[code] = tag
        except Exception as e:
            print(f"{Fore.RED}加载列表失败 {filepath}: {e}")
        return mapping