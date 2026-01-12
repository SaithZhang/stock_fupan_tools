
import os

path = r"d:\work\pyproject\data\input\call_auction\Table_20260113.txt"
if not os.path.exists(path):
    # Try finding any file
    base = os.path.dirname(path)
    files = os.listdir(base)
    files = [f for f in files if f.endswith('.txt')]
    if files:
        path = os.path.join(base, files[-1])
        print(f"Using {path}")

with open(path, 'rb') as f:
    for i in range(3):
        line = f.readline()
        print(f"Line {i}: {line}")
        try:
            print(f"Decoded: {line.decode('gbk')}")
        except:
            print("Decode error")
