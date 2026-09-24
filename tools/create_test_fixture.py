import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'backend'),str(ROOT/'tests/backend')]
from test_regressions import fixture
directory=ROOT/'.local/verification/browser'
directory.mkdir(parents=True,exist_ok=True)
print(fixture(directory))
