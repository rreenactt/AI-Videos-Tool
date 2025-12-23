from typing import List
import re


def extract_characters(script_text: str) -> List[str]:
	"""스크립트에서 고유명(간단 추정) 후보를 수집.
	실서비스에선 LLM/NER로 교체 권장.
	"""
	# 따옴표 앞 화자 패턴, 간단 추출 예시
	candidates = set(re.findall(r"([가-힣A-Za-z0-9_]+)\s*:\s*", script_text))
	return sorted(candidates)
