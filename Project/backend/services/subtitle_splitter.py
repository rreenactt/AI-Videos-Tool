import re
from typing import List


def split_subtitle_by_length(text: str, max_length: int = 12) -> List[str]:
	"""자막을 최대 길이에 맞춰 어순에 맞게 분할
	
	Args:
		text: 분할할 텍스트
		max_length: 최대 글자 수 (기본 12글자)
		
	Returns:
		분할된 텍스트 리스트
	"""
	if len(text) <= max_length:
		return [text]
	
	# 공백이나 구두점을 기준으로 단어/구분 단위로 분할
	# 한글, 영문, 숫자, 구두점을 모두 고려
	parts = re.split(r'([\s,\.!?;:])', text)
	
	# 단어와 구분자를 묶어서 처리 (공백은 앞 단어에 포함, 구두점도 앞 단어에 포함)
	cleaned_parts = []
	for i, part in enumerate(parts):
		if not part:  # 빈 문자열만 스킵
			continue
		# 공백인 경우 앞 단어에 붙임
		if part == ' ':
			if cleaned_parts:
				cleaned_parts[-1] += part
		# 구두점인 경우 앞 단어에 붙임
		elif part in [',', '.', '!', '?', ';', ':']:
			if cleaned_parts:
				cleaned_parts[-1] += part
		else:
			cleaned_parts.append(part)
	
	if not cleaned_parts:
		return [text]
	
	# 최대 길이에 맞춰 그룹화
	result = []
	current_line = ""
	
	for part in cleaned_parts:
		# 현재 라인에 추가했을 때 길이 확인
		test_line = current_line + part if current_line else part
		
		if len(test_line) <= max_length:
			current_line = test_line
		else:
			# 현재 라인이 있으면 저장
			if current_line:
				result.append(current_line.strip())
				current_line = part
			else:
				# 단일 단어가 max_length를 초과하는 경우 강제로 자름
				if len(part) > max_length:
					# 단어를 강제로 나눔 (최대한 자연스럽게)
					while len(part) > max_length:
						result.append(part[:max_length])
						part = part[max_length:]
					if part:
						current_line = part
				else:
					current_line = part
	
	# 마지막 라인 추가
	if current_line:
		result.append(current_line.strip())
	
	return result if result else [text]


def format_subtitle_lines(text: str, max_length: int = 12) -> str:
	"""자막을 최대 길이에 맞춰 여러 줄로 포맷팅
	
	Args:
		text: 포맷팅할 텍스트
		max_length: 최대 글자 수 (기본 12글자)
		
	Returns:
		줄바꿈이 포함된 텍스트
	"""
	lines = split_subtitle_by_length(text, max_length)
	return "\n".join(lines)

