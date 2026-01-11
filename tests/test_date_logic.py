import sys
import os
import pytest
import tempfile
import shutil

# Allow importing from src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
from core.market_data import MarketDataManager

@pytest.fixture
def temp_env():
    """Create a temporary directory simulating data inputs"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create dapan dir
        dapan_dir = os.path.join(temp_dir, 'dapan')
        os.makedirs(dapan_dir)
        yield temp_dir

def test_find_latest_file_logic(temp_env):
    """
    Test that MarketDataManager correctly picks the LATEST dated file 
    regardless of system time, which is critical for Weekend stability.
    """
    dapan_dir = os.path.join(temp_env, 'dapan')
    
    # Create fake files simulating Friday and Thursday
    # Assume today is Sunday (doesn't matter what today actually is)
    
    # Thursday file
    with open(os.path.join(dapan_dir, 'dapan-20260108.txt'), 'w') as f:
        f.write("dummy")
        
    # Friday file (Should be picked)
    with open(os.path.join(dapan_dir, 'dapan-20260109.txt'), 'w') as f:
        f.write("dummy")
        
    md = MarketDataManager(dapan_dir)
    target = md.find_latest_file()
    
    assert target is not None
    assert '20260109' in target, "Should pick Friday's file (0109) even if run on Sat/Sun"

def test_find_latest_subdir_logic(temp_env):
    """Test finding files in sibling directories (concepts, etc)"""
    # Create sibling structure
    # temp_env/dapan/
    # temp_env/ths/concepts/
    
    dapan_dir = os.path.join(temp_env, 'dapan')
    if not os.path.exists(dapan_dir): os.makedirs(dapan_dir)
    
    ths_dir = os.path.join(temp_env, 'ths')
    concepts_dir = os.path.join(ths_dir, 'concepts')
    os.makedirs(concepts_dir)
    
    # Case 1: Multiple concept files, should pick latest
    with open(os.path.join(concepts_dir, 'concept-20260108.txt'), 'w') as f: f.write("old")
    with open(os.path.join(concepts_dir, 'concept-20260109.txt'), 'w') as f: f.write("new")
    
    md = MarketDataManager(dapan_dir) 
    # Note: md connects to ../ths relative to dapan_dir
    
    target = md.find_latest_file_in_dir("concepts", "concept")
    
    assert target is not None
    assert '20260109' in target, "Should pick the latest concept file"

def test_missing_files_handling(temp_env):
    """Ensure it doesn't crash if files are missing"""
    dapan_dir = os.path.join(temp_env, 'dapan')
    # Empty dir
    if not os.path.exists(dapan_dir): os.makedirs(dapan_dir)
    
    md = MarketDataManager(dapan_dir)
    assert md.find_latest_file() is None, "Should pass gracefully if no files"
    assert md.find_latest_file_in_dir("concepts", "concept") is None
