import os
import sys

# 어디서 pytest를 돌리든 reviewlens/ 가 import 루트가 되도록 (from store import db 등)
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
