import sys
import os
import pytest
import pandas as pd

# Allow importing from src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
from core.market_data import MarketDataManager

@pytest.fixture
def manager():
    # Construct path to actual data for integration testing
    # In a real CI/CD we might use mock files, but here we want to verify the User's actual data loads
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    dapan_dir = os.path.join(root, 'data', 'input', 'dapan')
    print(f"DEBUG: Fixture dapan_dir: {dapan_dir}")
    if os.path.exists(dapan_dir):
        print(f"DEBUG: Files in dapan_dir: {os.listdir(dapan_dir)}")
    else:
        print("DEBUG: dapan_dir does not exist!")
    return MarketDataManager(dapan_dir)

def test_load_data_integration(manager):
    """Test that we can load the real data files present in the system"""
    # This validates the file format hasn't changed or become unreadable
    success = manager.load_data()
    assert success is True, "MarketDataManager failed to load data"
    
    # Check data integrity
    summary = manager.get_summary()
    assert summary is not None
    
    # Debug print if keys are missing
    if 'total_turnover' not in summary:
        print(f"DEBUG: Summary keys found: {summary.keys()}")
    
    assert 'total_turnover' in summary, "Key 'total_turnover' missing from summary"
    assert summary['total_turnover'] > 0, "Total turnover should be positive"
    
    # Check Indices
    assert 'indices' in summary
    assert 'sh_index' in summary['indices']
    assert summary['indices']['sh_index']['pct'] != 0.0, "Index pct should probably not be exactly 0.0 (unless extremely rare)"

def test_breadth_data(manager):
    """Verify Market Breadth parsing"""
    manager.load_data()
    summary = manager.get_summary()
    
    breadth = summary.get('market_breadth')
    assert breadth is not None, "Market breadth data missing"
    assert 'rise_count' in breadth
    assert 'fall_count' in breadth
    
    total = breadth['rise_count'] + breadth['fall_count']
    assert total > 1000, "Total stocks (rise+fall) should be significant (>1000)"

def test_sector_ranks(manager):
    """Verify Sector Ranks"""
    manager.load_data()
    summary = manager.get_summary()
    
    ranks = summary.get('sector_ranks')
    assert ranks is not None, "Sector ranks missing"
    assert 'industry' in ranks
    assert 'concept' in ranks
    
    # Check structure
    ind_gainers = ranks['industry']['gainers']
    assert len(ind_gainers) == 5, "Should have top 5 industry gainers"
    assert 'net_inflow' in ind_gainers[0]
