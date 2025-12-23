from typing import List, Dict, Optional


def generate_prompts(script_text: str, characters: List[str], *, title: Optional[str] = None, min_shots: int = 1) -> List[str]:
	"""스토리 텍스트를 받아 컷/샷 프롬프트 후보를 간단 생성.
	실서비스에선 스토리보드 JSON → 샷 단위 프롬프트로 세분화 권장.
	"""
	base_style = "cinematic anime illustration, detailed lineart, soft shading, dramatic lighting"
	lines = [l.strip() for l in script_text.split("\n") if l.strip()]
	prompts: List[str] = []
	for i, line in enumerate(lines[: max(min_shots, 1) * 3]):
		actors = ", ".join(characters[:3]) if characters else "protagonist"
		prompt = f"{title or 'scene'} #{i+1}: {line}. characters: {actors}. style: {base_style}"
		prompts.append(prompt)
	return prompts
