
import sys
import os

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..', '..'))
sys.path.append(project_root)

from src.monitors.call_auction_screener import load_manual_focus, MANUAL_FOCUS_PATH

print(f"Loading from: {MANUAL_FOCUS_PATH}")
if not os.path.exists(MANUAL_FOCUS_PATH):
    print("File not found!")
else:
    print("File exists.")
    
try:
    focus_list = load_manual_focus()
    print(f"Successfully loaded {len(focus_list)} items.")
    print("Sample items:")
    for i, item in enumerate(list(focus_list)[:5]):
        print(f" - {item}")
except Exception as e:
    print(f"Error loading list: {e}")
