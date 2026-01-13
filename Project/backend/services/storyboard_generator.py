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
	target_duration: float = 30.0,
	min_cuts: int = 16
) -> Storyboard:
	"""스토리 텍스트를 GPT에 보내서 컷별 요소를 추출한 스토리보드 JSON을 생성
	
	Args:
		client: OpenAI 클라이언트
		story_text: 스토리 텍스트
		title: 제목 (선택사항)
		model: 사용할 GPT 모델
		target_duration: 목표 영상 시간(초). 모든 컷의 duration 합이 이 값에 가깝게 생성됩니다.
		min_cuts: 최소 컷 개수 (기본값 16)
	"""
	
	schema = Storyboard.model_json_schema()
	avg_duration_per_cut = target_duration / min_cuts if min_cuts > 0 else 3.0
	
	system_prompt = (
		"You are a professional storyboard assistant for video production. "
		"Analyze the provided story and break it down into detailed cuts/scenes. "
		"For each cut, extract composition, dialogues (in Korean), background, actions, and characters in a structured JSON format. "
		"Include rich narration so viewers can understand the situation well. "
		"Output only JSON without code fences."
	)
	
	user_prompt = (
		f"Story:\n{story_text}\n\n"
		f"Generate a storyboard following this JSON schema:\n"
		f"{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
		f"Important guidelines:\n"
		f"- **CRITICAL**: Break the story into at least {min_cuts} detailed cuts.\n"
		f"- Each scene transition, viewpoint change, or character expression change should be a separate cut.\n"
		f"- Average duration per cut should be around {avg_duration_per_cut:.1f} seconds, but adjust based on content.\n"
		f"- **IMPORTANT**: Total duration of all cuts should sum to approximately {target_duration} seconds.\n"
		f"- Each cut must have a unique cut_id (starting from 1).\n"
		f"- **composition**: Describe camera angle, shot type, and character placement in ENGLISH. Examples:\n"
		f"  * 'close-up of protagonist's face, centered, neutral expression'\n"
		f"  * 'wide shot, two characters facing each other in urban street'\n"
		f"  * 'over-the-shoulder shot from behind character A looking at character B'\n"
		f"- **dialogues**: Keep dialogue text in Korean. Include speaker name and emotion.\n"
		f"- **background**: Describe scene atmosphere, lighting, and environment in ENGLISH. Examples:\n"
		f"  * 'dark forest at night, moonlight filtering through trees, mysterious ambiance'\n"
		f"  * 'modern office interior, bright fluorescent lighting, minimalist design'\n"
		f"  * 'busy city street at sunset, warm orange glow, crowded with people'\n"
		f"- **actions**: List character actions/movements in ENGLISH as array. Examples: ['walking forward', 'turning head', 'smiling']\n"
		f"- **characters**: List character names appearing in the cut. For consistency, use same names throughout. Examples:\n"
		f"  * Use descriptive names like 'young woman with long black hair', 'elderly man in suit', 'child with backpack'\n"
		f"  * Keep character descriptions consistent across all cuts for the same character\n"
		f"- **duration**: Set appropriate duration (seconds) based on dialogue length and action complexity:\n"
		f"  * Short dialogue or simple action: 2-4 seconds\n"
		f"  * Normal dialogue or action: 3-5 seconds\n"
		f"  * Long dialogue or complex action: 4-6 seconds\n"
		f"  * Important scene or emotional moment: 5-7 seconds\n"
		f"  * Total duration should sum to approximately {target_duration} seconds.\n"
		f"- **ALL fields except dialogues.text must be in ENGLISH**: cut_name, composition, background, actions, characters.\n"
		f"- Every cut must include either narration or character dialogue.\n"
		f"- Add sufficient narration (speaker: '나레이션') to help viewers understand the scene, emotions, and context.\n"
		f"- Break scenes into at least {min_cuts} diverse cuts with detailed descriptions."
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

