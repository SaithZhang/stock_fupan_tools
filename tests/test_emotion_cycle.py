import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import pandas as pd

# Add src to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.emotion_cycle import EmotionalCycleEngine
from src.config import ProjectConfig

class TestEmotionalCycleEngine(unittest.TestCase):
    def setUp(self):
        self.engine = EmotionalCycleEngine()
        self.config = ProjectConfig()

    @patch('src.core.emotion_cycle.ak.stock_zt_pool_em')
    def test_determine_phase_rising(self, mock_ak):
        # Mock recent data: Height increasing, Count stable
        # Day 1: 3 limit ups, max height 2
        # Day 2: 5 limit ups, max height 3
        # Day 3: 5 limit ups, max height 4 (Current)
        
        self.engine.history_stats = [
            {'date': '20230101', 'limit_up_count': 10, 'max_height': 2},
            {'date': '20230102', 'limit_up_count': 12, 'max_height': 3},
            {'date': '20230103', 'limit_up_count': 15, 'max_height': 5}
        ]
        
        phase = self.engine.determine_phase()
        self.assertEqual(phase, self.config.PHASE_RISING)

    @patch('src.core.emotion_cycle.ak.stock_zt_pool_em')
    def test_determine_phase_ice_point(self, mock_ak):
        # Mock recent data: Height very low
        self.engine.history_stats = [
            {'date': '20230101', 'limit_up_count': 5, 'max_height': 5},
            {'date': '20230102', 'limit_up_count': 3, 'max_height': 2}, # Ice point
            {'date': '20230103', 'limit_up_count': 4, 'max_height': 2}  # Ice point
        ]
        
        phase = self.engine.determine_phase()
        self.assertEqual(phase, self.config.PHASE_ICE_POINT)

    @patch('src.core.emotion_cycle.ak.stock_zt_pool_em')
    def test_determine_phase_decline(self, mock_ak):
        # Mock recent data: Height dropping significantly
        self.engine.history_stats = [
            {'date': '20230101', 'limit_up_count': 20, 'max_height': 7},
            {'date': '20230102', 'limit_up_count': 15, 'max_height': 4}, 
            {'date': '20230103', 'limit_up_count': 10, 'max_height': 3}  
        ]
        
        phase = self.engine.determine_phase()
        # Should be decline or ice point depending on height threshold (3 is ice point)
        # Let's adjust to be slightly above ice point to test decline, or accept ice point if it falls through
        
        # Test explicit decline
        self.engine.history_stats = [
            {'date': '20230101', 'limit_up_count': 20, 'max_height': 8},
            {'date': '20230102', 'limit_up_count': 20, 'max_height': 6},
            {'date': '20230103', 'limit_up_count': 15, 'max_height': 4}  # Dropped but > 3
        ]
        phase = self.engine.determine_phase()
        self.assertEqual(phase, self.config.PHASE_DECLINE)

if __name__ == '__main__':
    unittest.main()
