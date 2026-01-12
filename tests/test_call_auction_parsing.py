
import os
import sys
import unittest
import pandas as pd
import tempfile

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from monitors.call_auction_screener import parse_call_auction_file

class TestCallAuctionParsing(unittest.TestCase):
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.test_dir)

    def create_dummy_file(self, filename, content, encoding='utf-8'):
        path = os.path.join(self.test_dir, filename)
        with open(path, 'w', encoding=encoding) as f:
            f.write(content)
        return path

    def test_parse_utf8_tabs(self):
        """Test standard tab-separated UTF-8 file"""
        content = """
序号	代码	名称	竞价涨幅%	竞价金额	现价
1	600000	浦发银行	1.23%	1000万	10.00
2	000001	平安银行	-0.50%	5000000	12.00
        """
        path = self.create_dummy_file("utf8_tabs.txt", content.strip(), 'utf-8')
        df = parse_call_auction_file(path)
        
        self.assertIsNotNone(df)
        self.assertEqual(len(df), 2)
        # Check 600000
        row1 = df[df['code'] == '600000'].iloc[0]
        self.assertEqual(row1['name'], '浦发银行')
        self.assertAlmostEqual(row1['auc_amt'], 1000.0) # 1000万 -> 1000
        self.assertAlmostEqual(row1['open_pct'], 1.23)

    def test_parse_gbk_spaces(self):
        """Test GBK encoded file with irregular spaces (simulating copy-paste)"""
        # Note: 5000000 -> 500.0 Wan
        content = """
序号   代码    名称    竞价涨幅%    竞价金额
1     600000  浦发银行   1.23%       1000万
2     000001  平安银行   -0.50       5000000
        """
        path = self.create_dummy_file("gbk_spaces.txt", content.strip(), 'gbk')
        df = parse_call_auction_file(path)
        
        self.assertIsNotNone(df)
        self.assertEqual(len(df), 2)
        
        row2 = df[df['code'] == '000001'].iloc[0]
        self.assertAlmostEqual(row2['auc_amt'], 500.0) # 5000000 -> 500
        self.assertAlmostEqual(row2['open_pct'], -0.50)

    def test_parse_mixed_separators(self):
        """Test file with mixed tabs and spaces, typical of bad copy-pastes"""
        content = """
序号	代码 	名称	    竞价涨幅%	 竞价金额
1	  600000	 浦发银行	    1.23%	 1000万
        """
        path = self.create_dummy_file("mixed.txt", content.strip(), 'utf-8')
        df = parse_call_auction_file(path)
        self.assertIsNotNone(df)
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]['code'], '600000')

    def test_parse_missing_columns(self):
        """Test file missing headers"""
        content = """
序号	名称	现价
1	浦发银行	10.00
        """
        path = self.create_dummy_file("bad.txt", content.strip(), 'utf-8')
        df = parse_call_auction_file(path)
        self.assertIsNone(df)

if __name__ == '__main__':
    unittest.main()
