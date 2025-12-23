from typing import Optional


def adjust_script(raw_script: str, *, language: Optional[str] = "ko") -> str:
	"""러프 스토리 텍스트를 문장 정리/오탈자 보정/간결화 등 사전 정제.
	실서비스에서는 LLM 호출 또는 규칙 기반 전처리를 연결.
	"""
	text = raw_script.strip()
	text = text.replace("\r\n", "\n").replace("\r", "\n")
	return text
