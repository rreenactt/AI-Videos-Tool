from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import os
from glob import glob
import json
import time
import re
import shutil
import copy

from backend.services.script_adjuster import adjust_script
from backend.services.character_extractor import extract_characters
from backend.services.prompt_generator import generate_prompts
from backend.services.image_generator import generate_images, generate_images_with_progress, regenerate_single_image
from backend.services.video_composer import compose_video
from backend.services.storyboard_generator import generate_storyboard_from_story
from openai import OpenAI
from dotenv import load_dotenv
import uuid
from datetime import datetime

app = FastAPI(title="AIVideosService Backend", version="0.1.0")

app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)


class StoryRequest(BaseModel):
	project_id: Optional[str] = None
	title: Optional[str] = None
	story: str
	min_shots_per_scene: Optional[int] = 1
	style_key: Optional[str] = "surreal"


class ImageJobRequest(BaseModel):
	project_id: Optional[str] = None
	prompts: List[str]
	model: Optional[str] = "fal-ai/flux/dev"
	size: Optional[str] = "portrait_16_9"
	output_dir: Optional[str] = "../data/outputs"


class VideoJobRequest(BaseModel):
	image_paths: List[str]
	project_id: Optional[str] = None
	fps: Optional[int] = 24
	audio_path: Optional[str] = None
	output_path: Optional[str] = "../data/outputs/final.mp4"


class RegenerateImageRequest(BaseModel):
	project_id: str
	prompt: str
	index: int
	model: Optional[str] = "fal-ai/flux/dev"
	size: Optional[str] = "portrait_16_9"
	output_dir: Optional[str] = "../data/outputs"


class NewProjectRequest(BaseModel):
	title: Optional[str] = None
	mode: Optional[str] = "story"  # "fusion" or "story"


class ProjectStateUpdate(BaseModel):
	title: Optional[str] = None
	story: Optional[str] = None
	min_shots_per_scene: Optional[int] = None
	prompts: Optional[List[str]] = None
	cuts: Optional[List[Dict[str, Any]]] = None
	saved_results: Optional[List[str]] = None
	image_job_id: Optional[str] = None
	image_progress: Optional[Dict[str, Any]] = None
	style_key: Optional[str] = None


BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.normpath(os.path.join(BASE_DIR, "../data"))
OUTPUTS_DIR = os.path.join(DATA_DIR, "outputs")
TEMP_DIR = os.path.join(DATA_DIR, "temp")
PROJECTS_DIR = os.path.join(DATA_DIR, "projects")

# 정적 파일 서빙 (이미지/영상 접근용)
if os.path.isdir(DATA_DIR):
	app.mount(
		"/media",
		StaticFiles(directory=DATA_DIR),
		name="media",
	)

DEFAULT_STATE = {
	"title": "",
	"story": "",
	"min_shots_per_scene": 1,
	"prompts": [],
	"cuts": [],
	"saved_results": [],
	"image_job_id": "",
	"image_progress": {"status": "", "progress": 0, "message": ""},
	"style_key": "surreal",
}


def _to_web_url(path: str) -> str:
	"""DATA_DIR 기준 파일 시스템 경로를 브라우저에서 접근 가능한 /media URL로 변환"""
	if not path:
		return ""
	# 절대 경로가 아니면 BASE_DIR 기준으로 정규화
	abs_path = path
	if not os.path.isabs(abs_path):
		abs_path = os.path.normpath(os.path.join(BASE_DIR, abs_path))
	try:
		rel = os.path.relpath(abs_path, DATA_DIR)
	except ValueError:
		# DATA_DIR 밖의 경로이면 원본을 그대로 반환
		return path
	rel = rel.replace(os.sep, "/")
	return f"/media/{rel}"


def get_style_prompt_text(style_key: str) -> str:
	"""스타일 키에 해당하는 프롬프트 스타일 텍스트 반환 (영어로, 상세하게)"""
	style_map = {
		"surreal": (
			"Style: surreal dreamlike atmosphere, fantastical ethereal composition, "
			"cinematic anime illustration with detailed lineart, soft cel shading, "
			"dramatic volumetric lighting, vibrant color palette, otherworldly elements, "
			"high quality digital art, professional illustration, 4K resolution"
		),
		"real": (
			"Style: photorealistic, ultra-realistic rendering, natural lighting with soft shadows, "
			"detailed skin textures and fabric, depth of field bokeh effect, "
			"professional photography quality, Canon EOS R5 style, "
			"cinematic color grading, 8K high resolution, sharp focus"
		),
		"future": (
			"Style: futuristic sci-fi aesthetic, cyberpunk atmosphere with neon lights, "
			"advanced technology elements, holographic displays, metallic surfaces, "
			"dramatic blue and purple color scheme, cinematic lighting with lens flares, "
			"detailed mechanical parts, high-tech environment, 4K digital art"
		),
		"simple3d": (
			"Style: 3D rendered illustration, simple clean geometry, smooth surfaces, "
			"minimalist modern design, soft pastel colors, subtle gradients, "
			"isometric or low-poly aesthetic, professional 3D modeling, "
			"ambient occlusion lighting, Blender or C4D style render"
		),
		"ghibli": (
			"Style: Studio Ghibli anime aesthetic, hand-drawn illustration quality, "
			"soft watercolor-like colors, whimsical magical atmosphere, "
			"detailed background art with depth, warm natural lighting, "
			"character-focused composition, nostalgic peaceful mood, "
			"Hayao Miyazaki inspired, high quality animation frame"
		),
		"dark": (
			"Style: dark fantasy aesthetic, gothic atmosphere, moody dramatic shadows, "
			"mysterious cinematic lighting, high contrast chiaroscuro, "
			"detailed intricate illustration, muted desaturated colors with accent highlights, "
			"ominous foreboding mood, Bloodborne or Dark Souls inspired, "
			"professional concept art quality"
		),
	}
	return style_map.get(style_key, style_map["surreal"])


def _normalize_saved_results(saved_results: Any, prompts: List[str]) -> list[dict]:
	"""문자/구조 혼재된 saved_results를 통일된 dict 리스트로 정규화"""
	normalized: list[dict] = []
	if not isinstance(saved_results, list):
		return normalized
	for i, item in enumerate(saved_results):
		if isinstance(item, str):
			# 문자열만 있는 경우: 파일 시스템 경로로 간주하고 URL 생성
			url = _to_web_url(item)
			normalized.append({
				"index": i,
				"prompt": prompts[i] if i < len(prompts) else "",
				"url": url,
				"path": item,
			})
		elif isinstance(item, dict):
			raw_path = item.get("path") or item.get("url") or ""
			url = item.get("url") or _to_web_url(raw_path)
			normalized.append({
				"index": item.get("index", i),
				"prompt": item.get("prompt") or (prompts[i] if i < len(prompts) else ""),
				"url": url,
				"path": item.get("path", raw_path),
				"message": item.get("message", "")
			})
	return normalized


def _get_project_dir(project_id: str, *, require: bool = True) -> Optional[str]:
	proj_dir = os.path.join(PROJECTS_DIR, project_id)
	if os.path.isdir(proj_dir):
		return proj_dir
	if require:
		raise HTTPException(404, detail="프로젝트를 찾을 수 없습니다")
	return None


def _load_project_meta(project_id: str) -> Dict[str, Any]:
	proj_dir = _get_project_dir(project_id)
	meta_path = os.path.join(proj_dir, "metadata.json")
	meta = {"id": project_id, "title": project_id, "createdAt": None, "mode": "story", "status": "unknown"}
	if os.path.isfile(meta_path):
		with open(meta_path, "r", encoding="utf-8") as f:
			loaded = json.load(f)
			meta.update(loaded)
	return meta


def _save_project_meta(project_id: str, meta: Dict[str, Any]) -> None:
	proj_dir = _get_project_dir(project_id)
	meta_path = os.path.join(proj_dir, "metadata.json")
	with open(meta_path, "w", encoding="utf-8") as f:
		json.dump(meta, f, ensure_ascii=False, indent=2)


def _load_project_state(project_id: str, *, require: bool = True) -> Dict[str, Any]:
	proj_dir = _get_project_dir(project_id, require=require)
	state = copy.deepcopy(DEFAULT_STATE)
	if not proj_dir:
		return state
	state_path = os.path.join(proj_dir, "state.json")
	if os.path.isfile(state_path):
		try:
			with open(state_path, "r", encoding="utf-8") as f:
				loaded = json.load(f)
			if isinstance(loaded, dict):
				state.update(loaded)
				if "image_progress" in loaded and isinstance(loaded["image_progress"], dict):
					state["image_progress"] = {**state["image_progress"], **loaded["image_progress"]}
		except Exception:
			pass
	state["saved_results"] = _normalize_saved_results(state.get("saved_results", []), state.get("prompts", []))
	return state


def _save_project_state(project_id: str, state: Dict[str, Any], *, require: bool = True) -> None:
	proj_dir = _get_project_dir(project_id, require=require)
	if not proj_dir:
		return
	# 저장 전에 결과 구조 정규화
	state["saved_results"] = _normalize_saved_results(state.get("saved_results", []), state.get("prompts", []))
	state_path = os.path.join(proj_dir, "state.json")
	with open(state_path, "w", encoding="utf-8") as f:
		json.dump(state, f, ensure_ascii=False, indent=2)


def _slugify(text: str) -> str:
	s = re.sub(r"[^\w\-\s]", "", text).strip().lower()
	s = re.sub(r"[\s\-]+", "-", s)
	return s or "untitled"


# OpenAI 클라이언트 초기화
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
	raise ValueError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# 진행 상황 추적 (in-memory)
progress_store: dict[str, dict] = {}


@app.get("/health")
async def health():
	return {"status": "ok"}


@app.get("/api/home")
async def api_home():
	os.makedirs(OUTPUTS_DIR, exist_ok=True)
	os.makedirs(TEMP_DIR, exist_ok=True)
	os.makedirs(PROJECTS_DIR, exist_ok=True)
	prompts = sorted(glob(os.path.join(OUTPUTS_DIR, "prompt_*.txt")))
	images_fs = sorted([p for p in glob(os.path.join(OUTPUTS_DIR, "*.*")) if os.path.splitext(p)[1].lower() in {".png", ".jpg", ".jpeg", ".webp"}])
	videos_fs = sorted([p for p in glob(os.path.join(OUTPUTS_DIR, "*.*")) if os.path.splitext(p)[1].lower() in {".mp4", ".mov", ".webm"}])
	# projects: 디렉터리의 metadata.json 읽기
	projects: List[dict] = []
	for d in sorted(glob(os.path.join(PROJECTS_DIR, "*"))):
		if not os.path.isdir(d):
			continue
		meta_path = os.path.join(d, "metadata.json")
		state_path = os.path.join(d, "state.json")
		meta = {"id": os.path.basename(d), "title": os.path.basename(d), "createdAt": None, "videoPath": None, "imageCount": 0}
		if os.path.isfile(meta_path):
			try:
				with open(meta_path, "r", encoding="utf-8") as f:
					meta.update(json.load(f))
			except Exception:
				pass
		# state.json에서 비디오 경로와 이미지 개수 가져오기
		if os.path.isfile(state_path):
			try:
				with open(state_path, "r", encoding="utf-8") as f:
					state_data = json.load(f)
					if state_data.get("video_path"):
						meta["videoPath"] = state_data.get("video_path")
					if state_data.get("saved_results"):
						meta["imageCount"] = len(state_data.get("saved_results"))
			except Exception:
				pass
		projects.append(meta)
	return {
		"dirs": {"outputs": OUTPUTS_DIR, "temp": TEMP_DIR, "projects": PROJECTS_DIR},
		"counts": {"prompts": len(prompts), "images": len(images_fs), "videos": len(videos_fs), "projects": len(projects)},
		"lists": {
			"prompts": prompts,
			"images": [ _to_web_url(p) for p in images_fs ],
			"videos": [ _to_web_url(v) for v in videos_fs ],
			"projects": projects,
		},
	}


@app.post("/api/projects")
async def api_new_project(payload: NewProjectRequest):
	os.makedirs(PROJECTS_DIR, exist_ok=True)
	title = (payload.title or "새 프로젝트").strip()
	ts = time.strftime("%Y%m%d-%H%M%S")
	slug = f"{_slugify(title)}-{ts}"
	proj_dir = os.path.join(PROJECTS_DIR, slug)
	os.makedirs(proj_dir, exist_ok=True)
	
	# 프로젝트별 폴더 구조 생성
	os.makedirs(os.path.join(proj_dir, "images"), exist_ok=True)
	os.makedirs(os.path.join(proj_dir, "videos"), exist_ok=True)
	os.makedirs(os.path.join(proj_dir, "videos", "clips"), exist_ok=True)
	os.makedirs(os.path.join(proj_dir, "audio"), exist_ok=True)
	os.makedirs(os.path.join(proj_dir, "prompts"), exist_ok=True)
	
	mode = payload.mode or "story"
	if mode not in ("fusion", "story"):
		mode = "story"
	meta = {
		"id": slug,
		"title": title,
		"createdAt": ts,
		"status": "created",
		"mode": mode,
	}
	with open(os.path.join(proj_dir, "metadata.json"), "w", encoding="utf-8") as f:
		json.dump(meta, f, ensure_ascii=False, indent=2)
	state = copy.deepcopy(DEFAULT_STATE)
	state["title"] = title
	_save_project_state(slug, state)
	return meta


@app.delete("/api/projects/{project_id}")
async def api_delete_project(project_id: str):
	proj_dir = os.path.join(PROJECTS_DIR, project_id)
	if not os.path.isdir(proj_dir):
		raise HTTPException(404, detail="프로젝트를 찾을 수 없습니다")
	try:
		shutil.rmtree(proj_dir)
		return {"deleted": project_id}
	except Exception as e:
		raise HTTPException(500, detail=f"삭제 실패: {str(e)}")


@app.get("/api/projects/{project_id}")
async def api_get_project(project_id: str):
	meta = _load_project_meta(project_id)
	state = _load_project_state(project_id)
	return {"meta": meta, "state": state}


@app.patch("/api/projects/{project_id}")
async def api_update_project(project_id: str, payload: ProjectStateUpdate):
	meta = _load_project_meta(project_id)
	state = _load_project_state(project_id)
	updates = payload.model_dump(exclude_unset=True)
	if not updates:
		return {"meta": meta, "state": state}
	for key, value in updates.items():
		if key == "image_progress" and isinstance(value, dict):
			state["image_progress"] = {**state.get("image_progress", {}), **value}
		else:
			state[key] = value
	if "title" in updates and updates["title"]:
		meta["title"] = updates["title"]
		_save_project_meta(project_id, meta)
	_save_project_state(project_id, state)
	return {"meta": meta, "state": state}


@app.post("/api/storyboard")
async def api_storyboard(payload: StoryRequest):
	try:
		# 스토리 전처리
		adjusted = adjust_script(payload.story)
		
		# GPT로 컷별 요소 추출
		# min_shots_per_scene을 목표 영상 시간(초)으로 사용
		target_duration = float(payload.min_shots_per_scene or 30)
		storyboard = generate_storyboard_from_story(
			client=openai_client,
			story_text=adjusted,
			title=payload.title,
			model="gpt-4o-mini",
			target_duration=target_duration,
			min_cuts=16  # 최소 16개 컷 생성
		)
		
		# 각 컷에서 프롬프트 생성 (이미지 생성용 - 영어로만, 고품질)
		style_key = payload.style_key or "surreal"
		style_text = get_style_prompt_text(style_key)
		
		# 캐릭터 일관성을 위한 character description 추출 및 강화
		character_descriptions = {}
		character_appearance_count = {}
		
		# 모든 캐릭터 수집 및 등장 횟수 계산
		for cut in storyboard.cuts:
			for char in cut.characters:
				if char and char.strip():
					char_key = char.strip()
					if char_key not in character_descriptions:
						# 캐릭터 설명 저장 (일관성 유지를 위해 원본 그대로)
						character_descriptions[char_key] = char_key
						character_appearance_count[char_key] = 0
					character_appearance_count[char_key] += 1
		
		# 주요 캐릭터 식별 (3회 이상 등장)
		main_characters = [char for char, count in character_appearance_count.items() if count >= 3]
		
		prompts = []
		for cut_idx, cut in enumerate(storyboard.cuts):
			# 캐릭터 설명 (일관성 유지)
			characters_in_scene = []
			if cut.characters:
				for char in cut.characters:
					char_key = char.strip()
					if char_key in character_descriptions:
						char_desc = character_descriptions[char_key]
						# 주요 캐릭터인 경우 "CONSISTENT:" 태그 추가로 일관성 강조
						if char_key in main_characters:
							characters_in_scene.append(f"CONSISTENT: {char_desc}")
						else:
							characters_in_scene.append(char_desc)
			
			characters_str = ", ".join(characters_in_scene) if characters_in_scene else ""
			
			# 액션 정보 (있을 경우, 최대 2개로 제한)
			actions_str = ", ".join(cut.actions[:2]) if cut.actions else ""
			
			# 프롬프트 구성: 핵심 정보만 명확하게
			# 대사(dialogues), duration, 불필요한 메타데이터 제외
			prompt_parts = []
			
			# 1. Composition (카메라 앵글 + 구도) - 가장 중요
			prompt_parts.append(cut.composition)
			
			# 2. Characters (일관성 있게, 있을 경우만)
			if characters_str:
				prompt_parts.append(characters_str)
			
			# 3. Actions (간결하게, 있을 경우만)
			if actions_str:
				prompt_parts.append(actions_str)
			
			# 4. Background (환경 + 분위기)
			prompt_parts.append(cut.background)
			
			# 5. Style (스타일 + 품질 지시어)
			prompt_parts.append(style_text)
			
			# 6. 포맷 최적화 (세로형 비율)
			prompt_parts.append("vertical composition, portrait orientation optimized, centered framing")
			
			# 7. 품질 향상 지시어
			prompt_parts.append("masterpiece, best quality, highly detailed, sharp focus, professional artwork")
			
			# 최종 프롬프트 (영어로만, 쉼표로 구분하여 깔끔하게)
			prompt = ", ".join(prompt_parts)
			
			# Negative 요소 방지를 위한 추가 (프롬프트 끝에)
			prompt += ". Avoid: blurry, low quality, distorted, bad anatomy, extra limbs, duplicate characters, text, watermark, signature, deformed faces"
			
			prompts.append(prompt)
			print(f"[프롬프트 {cut_idx+1}] {prompt[:100]}...")
		
		if payload.project_id:
			state = _load_project_state(payload.project_id)
			state["story"] = payload.story
			state["title"] = storyboard.title or state.get("title") or (payload.title or "")
			if payload.min_shots_per_scene:
				state["min_shots_per_scene"] = payload.min_shots_per_scene
			if payload.style_key:
				state["style_key"] = payload.style_key
			state["cuts"] = [cut.model_dump() for cut in storyboard.cuts]
			state["prompts"] = prompts
			state["saved_results"] = []
			state["image_job_id"] = ""
			state["image_progress"] = {"status": "", "progress": 0, "message": ""}
			# 캐릭터 정보 저장 (일관성 유지를 위해)
			state["character_descriptions"] = character_descriptions
			state["main_characters"] = main_characters
			_save_project_state(payload.project_id, state)
			meta = _load_project_meta(payload.project_id)
			if storyboard.title:
				meta["title"] = storyboard.title
				_save_project_meta(payload.project_id, meta)
		# 나레이션 통계
		cuts_with_narration = sum(
			1 for cut in storyboard.cuts 
			if any(d.speaker and "나레이션" in d.speaker for d in cut.dialogues)
		)
		print(f"\n📊 스토리보드 생성 결과:")
		print(f"   - 총 컷: {len(storyboard.cuts)}개")
		print(f"   - 나레이션 포함: {cuts_with_narration}/{len(storyboard.cuts)}개")
		print(f"   - 프롬프트: {len(prompts)}개")
		
		return {
			"title": storyboard.title,
			"cuts": [cut.model_dump() for cut in storyboard.cuts],
			"prompts": prompts,
		}
	except Exception as e:
		raise HTTPException(500, detail=str(e))


def run_image_generation(job_id: str, prompts: List[str], model: str, size: str, output_dir: str, project_id: Optional[str] = None):
	"""백그라운드에서 이미지 생성 실행"""
	# progress_store에 초기 상태 설정 (없으면 생성)
	if job_id not in progress_store:
		progress_store[job_id] = {
			"status": "starting",
			"progress": 0.0,
			"message": "작업 시작 중...",
			"updated_at": datetime.now().isoformat()
		}
	
	# 프로젝트별 폴더에 저장
	if project_id:
		proj_dir = _get_project_dir(project_id, require=False)
		if proj_dir:
			target_output_dir = os.path.join(proj_dir, "images")
			os.makedirs(target_output_dir, exist_ok=True)
		else:
			# 프로젝트가 없으면 기본 경로 사용
			target_output_dir = output_dir
			if output_dir and not os.path.isabs(output_dir):
				target_output_dir = os.path.normpath(os.path.join(BASE_DIR, output_dir))
	else:
		# 상대 경로를 backend 기준 절대 경로로 변환
		target_output_dir = output_dir
		if output_dir and not os.path.isabs(output_dir):
			target_output_dir = os.path.normpath(os.path.join(BASE_DIR, output_dir))

	def progress_callback(status: str, progress: float, message: str):
		progress_store[job_id] = {
			"status": status,
			"progress": progress,
			"message": message,
			"updated_at": datetime.now().isoformat()
		}
		if project_id:
			try:
				state = _load_project_state(project_id, require=False)
				state["image_progress"] = {"status": status, "progress": progress, "message": message}
				if status in {"completed", "error"}:
					state["image_job_id"] = ""
				else:
					state["image_job_id"] = job_id
				_save_project_state(project_id, state, require=False)
			except Exception:
				pass
	
	try:
		results = generate_images_with_progress(
			prompts,
			progress_callback=progress_callback,
			model=model,
			size=size,
			output_dir=target_output_dir
		)
		progress_store[job_id]["results"] = results
		progress_store[job_id]["status"] = "completed"
		if project_id:
			try:
				state = _load_project_state(project_id, require=False)
				state["saved_results"] = _normalize_saved_results(results, prompts)
				state["image_job_id"] = ""
				state["image_progress"] = {"status": "completed", "progress": 100.0, "message": "모든 이미지 생성 완료"}
				_save_project_state(project_id, state, require=False)
			except Exception:
				pass
	except Exception as e:
		progress_store[job_id]["status"] = "error"
		progress_store[job_id]["error"] = str(e)
		if project_id:
			try:
				state = _load_project_state(project_id, require=False)
				state["image_job_id"] = ""
				state["image_progress"] = {"status": "error", "progress": 0, "message": str(e)}
				_save_project_state(project_id, state, require=False)
			except Exception:
				pass


@app.post("/api/images")
async def api_images(payload: ImageJobRequest, background_tasks: BackgroundTasks):
	try:
		job_id = str(uuid.uuid4())
		# progress_store에 즉시 등록
		progress_store[job_id] = {
			"status": "queued",
			"progress": 0.0,
			"message": "작업 대기 중...",
			"updated_at": datetime.now().isoformat()
		}
		
		if payload.project_id:
			try:
				state = _load_project_state(payload.project_id, require=False)
				if not state:
					state = copy.deepcopy(DEFAULT_STATE)
				state["image_job_id"] = job_id
				state["image_progress"] = progress_store[job_id].copy()
				state["saved_results"] = []
				_save_project_state(payload.project_id, state, require=False)
			except Exception as e:
				print(f"프로젝트 상태 저장 실패: {e}")
				# 프로젝트 상태 저장 실패해도 작업은 계속 진행
		
		# 백그라운드 작업 시작
		background_tasks.add_task(
			run_image_generation,
			job_id,
			payload.prompts,
			payload.model,
			payload.size,
			payload.output_dir,
			payload.project_id
		)
		
		return {"job_id": job_id}
	except Exception as e:
		# 예외 발생 시에도 job_id가 있으면 progress_store에 에러 상태 저장
		if 'job_id' in locals():
			progress_store[job_id] = {
				"status": "error",
				"progress": 0.0,
				"message": f"작업 시작 실패: {str(e)}",
				"error": str(e),
				"updated_at": datetime.now().isoformat()
			}
		raise HTTPException(500, detail=str(e))


@app.post("/api/images/regenerate")
async def api_regenerate_image(payload: RegenerateImageRequest):
	"""단일 프롬프트만 다시 생성 (fal.ai 기반)"""
	try:
		target_output_dir = payload.output_dir
		if target_output_dir and not os.path.isabs(target_output_dir):
			target_output_dir = os.path.normpath(os.path.join(BASE_DIR, target_output_dir))

		result = regenerate_single_image(
			prompt=payload.prompt,
			index=payload.index,
			model=payload.model or "fal-ai/flux/dev",
			size=payload.size or "portrait_16_9",
			output_dir=target_output_dir or OUTPUTS_DIR
		)

		if payload.project_id:
			state = _load_project_state(payload.project_id, require=False)
			prompts = state.get("prompts", [])
			if payload.index < len(prompts):
				prompts[payload.index] = payload.prompt
			else:
				# 부족한 인덱스는 빈 값으로 채우고 append
				while len(prompts) < payload.index:
					prompts.append("")
				prompts.append(payload.prompt)

			saved = _normalize_saved_results(state.get("saved_results", []), prompts)
			if payload.index < len(saved):
				saved[payload.index] = result
			else:
				while len(saved) < payload.index:
					saved.append({})
				saved.append(result)

			state["prompts"] = prompts
			state["saved_results"] = saved
			state["image_progress"] = {"status": "completed", "progress": 100.0, "message": "단일 이미지 재생성 완료"}
			_save_project_state(payload.project_id, state, require=False)

		return {"result": result}
	except Exception as e:
		raise HTTPException(500, detail=str(e))


@app.get("/api/images/progress/{job_id}")
async def api_images_progress(job_id: str):
	"""이미지 생성 진행 상황 조회"""
	# progress_store에서 먼저 확인
	if job_id in progress_store:
		return progress_store[job_id]
	
	# progress_store에 없으면 프로젝트 상태에서 찾기
	# 모든 프로젝트를 확인하여 해당 job_id를 가진 프로젝트 찾기
	import glob
	projects = glob.glob(os.path.join(PROJECTS_DIR, "*"))
	for proj_path in projects:
		if not os.path.isdir(proj_path):
			continue
		try:
			state = _load_project_state(os.path.basename(proj_path), require=False)
			if state.get("image_job_id") == job_id:
				# 프로젝트 상태의 image_progress 반환
				progress = state.get("image_progress", {
					"status": "unknown",
					"progress": 0.0,
					"message": "상태를 확인할 수 없습니다"
				})
				# progress_store에도 복원
				progress_store[job_id] = {
					**progress,
					"updated_at": datetime.now().isoformat()
				}
				return progress_store[job_id]
		except Exception:
			continue
	
	# 찾을 수 없으면 기본값 반환 (404 대신)
	return {
		"status": "not_found",
		"progress": 0.0,
		"message": "작업을 찾을 수 없습니다. 작업이 완료되었거나 취소되었을 수 있습니다.",
		"updated_at": datetime.now().isoformat()
	}


@app.post("/api/video")
async def api_video(payload: VideoJobRequest):
	try:
		# 프로젝트에서 cuts 정보 가져오기
		cuts = None
		output_path = payload.output_path
		
		if payload.project_id:
			state = _load_project_state(payload.project_id, require=False)
			cuts = state.get("cuts", [])
			
			# 프로젝트별 출력 경로 설정
			proj_dir = _get_project_dir(payload.project_id, require=False)
			if proj_dir:
				videos_dir = os.path.join(proj_dir, "videos")
				os.makedirs(videos_dir, exist_ok=True)
				output_path = os.path.join(videos_dir, "final.mp4")
		
		result = compose_video(
			image_paths=payload.image_paths,
			cuts=cuts,
			fps=payload.fps,
			audio_path=payload.audio_path,
			output_path=output_path,
			project_id=payload.project_id,
			use_tts=True,
			tts_voice="alloy"
		)
		
		# 웹에서 접근 가능한 URL 생성
		web_output = _to_web_url(result["output_path"])
		
		# 프로젝트 상태에 영상 정보 저장
		if payload.project_id:
			state = _load_project_state(payload.project_id, require=False)
			state["video_path"] = web_output
			state["video_clips"] = result.get("clip_paths", [])
			state["audio_paths"] = result.get("audio_paths", [])
			state["video_duration"] = result.get("total_duration", 0)
			_save_project_state(payload.project_id, state, require=False)
		
		# 프론트엔드에는 웹 URL을 우선 제공
		return {"output": web_output, "metadata": {**result, "web_output": web_output}}
	except Exception as e:
		raise HTTPException(500, detail=str(e))


if __name__ == "__main__":
	import uvicorn
	import logging
	
	# uvicorn 리로드 관련 예외 로그 필터링
	logging.getLogger("uvicorn.lifespan.on").setLevel(logging.WARNING)
	logging.getLogger("asyncio").setLevel(logging.WARNING)
	
	uvicorn.run(
		"backend.main:app",
		host="0.0.0.0",
		port=8000,
		reload=True,
		log_level="info",
		access_log=True
	)
