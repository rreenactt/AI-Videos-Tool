from typing import List, Optional
from pydantic import BaseModel, Field
from openai import OpenAI
import json
import os


class DialogueLine(BaseModel):
	speaker: str = Field(..., description="대사를 말하는 인물")
	text: str = Field(..., description="대사 내용")
	emotion: Optional[str] = Field(default=None, description="감정/톤")


class StoryCut(BaseModel):
	cut_id: int = Field(..., ge=1, description="컷 번호")
	cut_name: str = Field(..., description="컷 이름/장면 이름")
	composition: str = Field(..., description="구도/카메라/인물 배치")
	dialogues: List[DialogueLine] = Field(default_factory=list, description="대사 배열")
	background: str = Field(..., description="배경/분위기/사운드")
	actions: List[str] = Field(default_factory=list, description="액션/행동")
	characters: List[str] = Field(default_factory=list, description="등장 인물")
	duration: float = Field(default=3.0, ge=0.5, le=30.0, description="컷의 재생 시간(초). 대사 길이와 액션 복잡도에 따라 적절히 설정")


class Storyboard(BaseModel):
	title: str
	cuts: List[StoryCut] = Field(default_factory=list)


def generate_storyboard_from_story(
	client: OpenAI,
	story_text: str,
	title: Optional[str] = None,
	model: str = "gpt-5o-mini",
	target_duration: float = 30.0
) -> Storyboard:
	"""스토리 텍스트를 GPT에 보내서 컷별 요소를 추출한 스토리보드 JSON을 생성
	
	Args:
		client: OpenAI 클라이언트
		story_text: 스토리 텍스트
		title: 제목 (선택사항)
		model: 사용할 GPT 모델
		target_duration: 목표 영상 시간(초). 모든 컷의 duration 합이 이 값에 가깝게 생성됩니다.
	"""
	
	schema = Storyboard.model_json_schema()
	system_prompt = (
		"당신은 영상 콘티 기획 어시스턴트입니다. "
		"사용자가 제공한 스토리를 분석하여 장면을 컷 단위로 나누고, "
		"각 컷마다 구도, 대사, 배경, 액션, 등장 인물을 추출하여 구조화된 JSON으로 출력하세요. "
		"반드시 JSON만 출력하고, 코드 펜스는 사용하지 마세요."
	)
	
	user_prompt = (
		f"스토리:\n{story_text}\n\n"
		f"아래 JSON 스키마에 맞춰 스토리보드를 생성하세요:\n"
		f"{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
		f"주의사항:\n"
		f"- 스토리를 자연스럽게 여러 컷으로 나누세요.\n"
		f"- **중요**: 모든 컷의 duration 합이 약 {target_duration}초가 되도록 컷을 생성하세요.\n"
		f"- 각 컷은 고유한 cut_id를 가져야 합니다 (1부터 시작).\n"
		f"- composition은 카메라 구도와 인물 배치를 설명하세요.\n"
		f"- dialogues 배열에는 해당 컷의 모든 대사를 포함하세요.\n"
		f"- background는 장면의 분위기, 사운드, 환경을 설명하세요.\n"
		f"- actions는 인물의 행동/액션을 배열로 나열하세요.\n"
		f"- characters는 해당 컷에 등장하는 인물 이름을 배열로 나열하세요.\n"
		f"- duration은 각 컷의 재생 시간(초)입니다. 대사 길이, 액션 복잡도, 장면의 중요도에 따라 적절히 설정하세요:\n"
		f"  * 짧은 대사나 단순한 액션: 2-3초\n"
		f"  * 일반적인 대사나 액션: 3-5초\n"
		f"  * 긴 대사나 복잡한 액션: 4-6초\n"
		f"  * 중요한 장면이나 감정적 순간: 5-8초\n"
		f"  * 각 컷의 duration을 합산했을 때 총 {target_duration}초에 가깝게 조정하세요.\n"
		f"- dialogues은 한글로, 나머지 필드는 영어로 작성하세요.\n"
		f"- 모든 컷에는 나레이션 대사 또는 인물의 대사가 포함되어야 합니다."
	)
	
	try:
		response = client.chat.completions.create(
			model=model,
			messages=[
				{"role": "system", "content": system_prompt},
				{"role": "user", "content": user_prompt}
			],
			temperature=0.3,
			response_format={"type": "json_object"}
		)
		
		content = response.choices[0].message.content or "{}"
		print(content)
		content = content.strip()
		
		# 코드 펜스 제거
		if content.startswith("```"):
			content = content.strip("`\n ")
			if content.lower().startswith("json"):
				content = content[4:].strip()
		
		data = json.loads(content)
		storyboard = Storyboard.model_validate(data)
		
		# 제목이 없으면 설정
		if not storyboard.title:
			storyboard.title = title or "Untitled"
		
		# 컷이 없으면 기본 컷 생성
		if not storyboard.cuts:
			storyboard.cuts.append(StoryCut(
				cut_id=1,
				cut_name="Scene",
				composition="medium shot",
				dialogues=[],
				background="neutral background",
				actions=[],
				characters=[],
				duration=target_duration
			))
			return storyboard
		
		# 모든 컷의 duration 합 계산
		total_duration = sum(cut.duration for cut in storyboard.cuts)
		
		# 목표 시간에 맞춰 duration 조정
		if total_duration > 0 and abs(total_duration - target_duration) > 0.5:
			# 비율로 조정
			ratio = target_duration / total_duration
			for cut in storyboard.cuts:
				cut.duration = max(0.5, min(30.0, cut.duration * ratio))
			
			# 다시 합산하여 미세 조정
			total_duration = sum(cut.duration for cut in storyboard.cuts)
			diff = target_duration - total_duration
			
			if abs(diff) > 0.1:
				# 차이를 마지막 컷에 추가/제거
				if storyboard.cuts:
					last_cut = storyboard.cuts[-1]
					new_duration = max(0.5, min(30.0, last_cut.duration + diff))
					last_cut.duration = new_duration
		elif total_duration == 0:
			# duration이 0이면 기본값 설정
			avg_duration = target_duration / len(storyboard.cuts) if storyboard.cuts else target_duration
			for cut in storyboard.cuts:
				cut.duration = max(0.5, min(30.0, avg_duration))
		
		return storyboard
		
	except json.JSONDecodeError as e:
		# JSON 파싱 실패 시 빈 스토리보드 반환
		return Storyboard(title=title or "Untitled", cuts=[])
	except Exception as e:
		raise Exception(f"스토리보드 생성 실패: {str(e)}")

