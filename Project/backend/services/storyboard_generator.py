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


class Storyboard(BaseModel):
	title: str
	cuts: List[StoryCut] = Field(default_factory=list)


def generate_storyboard_from_story(
	client: OpenAI,
	story_text: str,
	title: Optional[str] = None,
	model: str = "gpt-4o-mini",
	min_shots_per_scene: int = 1
) -> Storyboard:
	"""스토리 텍스트를 GPT에 보내서 컷별 요소를 추출한 스토리보드 JSON을 생성"""
	
	schema = Storyboard.model_json_schema()
	system_prompt = (
		"당신은 영상 콘티 기획 어시스턴트입니다. "
		"사용자가 제공한 스토리를 분석하여 장면을 컷 단위로 나누고, "
		"각 컷마다 구도, 대사, 배경, 액션, 등장 인물을 추출하여 구조화된 JSON으로 출력하세요. "
		"반드시 JSON만 출력하고, 코드 펜스는 사용하지 마세요."
	)
	
	min_cuts = max(1, min_shots_per_scene)
	user_prompt = (
		f"스토리:\n{story_text}\n\n"
		f"아래 JSON 스키마에 맞춰 스토리보드를 생성하세요:\n"
		f"{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
		f"주의사항:\n"
		f"- 스토리를 자연스럽게 여러 컷으로 나누세요.\n"
		f"- 최소 {min_cuts}개 이상의 컷을 생성해야 합니다.\n"
		f"- 각 컷은 고유한 cut_id를 가져야 합니다 (1부터 시작).\n"
		f"- composition은 카메라 구도와 인물 배치를 설명하세요.\n"
		f"- dialogues 배열에는 해당 컷의 모든 대사를 포함하세요.\n"
		f"- background는 장면의 분위기, 사운드, 환경을 설명하세요.\n"
		f"- actions는 인물의 행동/액션을 배열로 나열하세요.\n"
		f"- characters는 해당 컷에 등장하는 인물 이름을 배열로 나열하세요.\n"
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
		
		# 최소 컷 수 확인 및 보정
		min_cuts = max(1, min_shots_per_scene)
		if len(storyboard.cuts) < min_cuts:
			# 컷이 부족하면 마지막 컷을 복제하거나 분할하여 추가
			existing_cuts = storyboard.cuts.copy()
			while len(storyboard.cuts) < min_cuts:
				# 마지막 컷을 기반으로 새 컷 생성
				if existing_cuts:
					last_cut = existing_cuts[-1]
					new_cut = StoryCut(
						cut_id=len(storyboard.cuts) + 1,
						cut_name=f"{last_cut.cut_name} (continued)",
						composition=last_cut.composition,
						dialogues=last_cut.dialogues.copy() if last_cut.dialogues else [],
						background=last_cut.background,
						actions=last_cut.actions.copy() if last_cut.actions else [],
						characters=last_cut.characters.copy() if last_cut.characters else []
					)
					storyboard.cuts.append(new_cut)
				else:
					# 컷이 아예 없으면 기본 컷 생성
					storyboard.cuts.append(StoryCut(
						cut_id=1,
						cut_name="Scene",
						composition="medium shot",
						dialogues=[],
						background="neutral background",
						actions=[],
						characters=[]
					))
		
		return storyboard
		
	except json.JSONDecodeError as e:
		# JSON 파싱 실패 시 빈 스토리보드 반환
		return Storyboard(title=title or "Untitled", cuts=[])
	except Exception as e:
		raise Exception(f"스토리보드 생성 실패: {str(e)}")

