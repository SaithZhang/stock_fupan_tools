import pandas as pd
from .base import BaseDataStep


class AuctionStep(BaseDataStep):
    """[P2] 云端竞价"""

    def fetch(self, date_str, context):
        print(f"   ├── [2/6] 获取云端竞价...", end="", flush=True)
        try:
            df = self.pro.stk_auction(trade_date=date_str, fields='ts_code,vol,amount,price,pre_close')
            if not df.empty:
                df[['price', 'pre_close', 'amount', 'vol']] = df[['price', 'pre_close', 'amount', 'vol']].apply(
                    pd.to_numeric, errors='coerce')

                df['auc_pct'] = 0.0
                mask = df['pre_close'] > 0
                df.loc[mask, 'auc_pct'] = (df.loc[mask, 'price'] - df.loc[mask, 'pre_close']) / df.loc[
                    mask, 'pre_close'] * 100

                df.rename(columns={'vol': 'auc_vol', 'amount': 'auc_amt'}, inplace=True)
                context['auction_df'] = df[['ts_code', 'auc_vol', 'auc_amt', 'auc_pct']]
                print(f" ✅ ({len(df)}条)")
            else:
                context['auction_df'] = pd.DataFrame()
                print(" ⚠️ 无数据")
        except:
            context['auction_df'] = pd.DataFrame()
            print(" ❌")