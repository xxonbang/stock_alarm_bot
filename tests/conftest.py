"""테스트 공통 픽스처"""
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가 (src/ import 가능하게)
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
