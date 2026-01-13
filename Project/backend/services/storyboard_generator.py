from typing import List, Optional
from pydantic import BaseModel, Field
from openai import OpenAI
import json
import os
import re


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


def _generate_smart_narration(cut: StoryCut, cut_index: int, total_cuts: int) -> str:
	"""컷의 정보를 바탕으로 지능적인 나레이션 생성"""
	narration_parts = []
	
	# 장면 설명
	if cut.cut_name and cut.cut_name.lower() != "scene":
		narration_parts.append(cut.cut_name)
	
	# 인물 정보 (있을 경우)
	if cut.characters:
		if len(cut.characters) == 1:
			narration_parts.append(f"{cut.characters[0]}가 등장합니다")
		elif len(cut.characters) == 2:
			narration_parts.append(f"{cut.characters[0]}와 {cut.characters[1]}가 함께 있습니다")
		else:
			narration_parts.append(f"{', '.join(cut.characters[:2])} 등 여러 인물이 등장합니다")
	
	# 액션 정보 (있을 경우)
	if cut.actions:
		action_ko = []
		action_map = {
			"walking": "걷고 있습니다",
			"running": "달리고 있습니다",
			"standing": "서 있습니다",
			"sitting": "앉아 있습니다",
			"looking": "바라보고 있습니다",
			"talking": "이야기하고 있습니다",
			"turning": "돌아보고 있습니다",
			"smiling": "미소 짓고 있습니다",
			"crying": "울고 있습니다",
			"fighting": "싸우고 있습니다",
		}
		for action in cut.actions[:2]:
			action_lower = action.lower()
			for eng, ko in action_map.items():
				if eng in action_lower:
					action_ko.append(ko)
					break
		if action_ko:
			narration_parts.append(", ".join(action_ko))
	
	# 배경 정보 (간단히)
	if cut.background:
		bg_lower = cut.background.lower()
		if "night" in bg_lower or "dark" in bg_lower:
			narration_parts.append("어두운 분위기 속에서")
		elif "day" in bg_lower or "bright" in bg_lower or "sunlight" in bg_lower:
			narration_parts.append("밝은 햇살 아래")
		elif "sunset" in bg_lower or "dawn" in bg_lower:
			narration_parts.append("노을이 지는 하늘 아래")
		elif "indoor" in bg_lower or "room" in bg_lower or "office" in bg_lower:
			narration_parts.append("실내에서")
		elif "outdoor" in bg_lower or "street" in bg_lower or "city" in bg_lower:
			narration_parts.append("야외에서")
	
	# 진행 상황 (첫/중간/마지막 컷 구분)
	if cut_index == 0:
		narration_parts.insert(0, "이야기가 시작됩니다.")
	elif cut_index == total_cuts - 1:
		narration_parts.append("이야기가 마무리됩니다.")
	
	# 최종 나레이션 조합
	if narration_parts:
		return " ".join(narration_parts) + "."
	else:
		return f"{cut.cut_name}. 장면이 전개됩니다."


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
		f"- **CRITICAL REQUIREMENT**: EVERY SINGLE CUT MUST HAVE AT LEAST ONE NARRATION (speaker: '나레이션').\n"
		f"- **MANDATORY**: Even if a cut has character dialogue, it MUST also include narration for context.\n"
		f"- Narration should describe:\n"
		f"  * What is happening in the scene\n"
		f"  * Character emotions and atmosphere\n"
		f"  * Important visual details\n"
		f"  * Transition context if scene changes\n"
		f"- Each narration should be 1-3 sentences long and descriptive.\n"
		f"- Example narration format:\n"
		f"  {{'speaker': '나레이션', 'text': '어두운 숲 속, 주인공이 천천히 걸어갑니다. 달빛이 나뭇잎 사이로 스며들며 신비로운 분위기를 만듭니다.', 'emotion': null}}\n"
		f"- Break scenes into at least {min_cuts} diverse cuts with detailed descriptions.\n"
		f"- **VERIFY**: Before finalizing, check that EVERY cut has '나레이션' in dialogues array."
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
				dialogues=[DialogueLine(speaker="나레이션", text="장면이 시작됩니다.", emotion=None)],
				background="neutral background",
				actions=[],
				characters=[],
				duration=target_duration
			))
			return storyboard
		
		# 모든 컷에 나레이션이 있는지 확인하고 없으면 추가
		total_cuts = len(storyboard.cuts)
		for idx, cut in enumerate(storyboard.cuts):
			if not cut.dialogues or len(cut.dialogues) == 0:
				# 나레이션이 전혀 없는 경우: 스마트 나레이션 생성
				narration_text = _generate_smart_narration(cut, idx, total_cuts)
				default_narration = DialogueLine(
					speaker="나레이션",
					text=narration_text,
					emotion=None
				)
				cut.dialogues = [default_narration]
				print(f"⚠ 컷 {cut.cut_id}: 나레이션 자동 추가 - '{narration_text}'")
			else:
				# 나레이션이 있는지 확인
				has_narration = any(
					d.speaker and ("나레이션" in d.speaker or "narration" in d.speaker.lower())
					for d in cut.dialogues
				)
				
				if not has_narration:
					# 다른 대사는 있지만 나레이션이 없는 경우: 스마트 나레이션 추가
					narration_text = _generate_smart_narration(cut, idx, total_cuts)
					narration = DialogueLine(
						speaker="나레이션",
						text=narration_text,
						emotion=None
					)
					# 나레이션을 맨 앞에 추가
					cut.dialogues.insert(0, narration)
					print(f"⚠ 컷 {cut.cut_id}: 나레이션 자동 추가 (대사 앞) - '{narration_text}'")
		
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
		
		# 최종 검증: 모든 컷에 나레이션이 있는지 확인
		cuts_with_narration = 0
		total_dialogues = 0
		for cut in storyboard.cuts:
			if cut.dialogues:
				total_dialogues += len(cut.dialogues)
				has_narration = any(
					d.speaker and "나레이션" in d.speaker
					for d in cut.dialogues
				)
				if has_narration:
					cuts_with_narration += 1
		
		print(f"\n✅ 스토리보드 생성 완료:")
		print(f"   - 총 {len(storyboard.cuts)}개 컷")
		print(f"   - 나레이션이 있는 컷: {cuts_with_narration}개 ({cuts_with_narration/len(storyboard.cuts)*100:.0f}%)")
		print(f"   - 총 대사/나레이션: {total_dialogues}개")
		print(f"   - 총 재생 시간: {sum(cut.duration for cut in storyboard.cuts):.1f}초")
		
		return storyboard
		
	except json.JSONDecodeError as e:
		# JSON 파싱 실패 시 빈 스토리보드 반환
		return Storyboard(title=title or "Untitled", cuts=[])
	except Exception as e:
		raise Exception(f"스토리보드 생성 실패: {str(e)}")

