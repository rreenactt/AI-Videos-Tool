from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
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
from backend.services.image_generator import generate_images, generate_images_with_progress
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


class ImageJobRequest(BaseModel):
	project_id: Optional[str] = None
	prompts: List[str]
	model: Optional[str] = "gpt-image-1"
	size: Optional[str] = "1024x1024"
	output_dir: Optional[str] = "../data/outputs"


class VideoJobRequest(BaseModel):
	image_paths: List[str]
	fps: Optional[int] = 24
	audio_path: Optional[str] = None
	output_path: Optional[str] = "../data/outputs/final.mp4"


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


BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.normpath(os.path.join(BASE_DIR, "../data"))
OUTPUTS_DIR = os.path.join(DATA_DIR, "outputs")
TEMP_DIR = os.path.join(DATA_DIR, "temp")
PROJECTS_DIR = os.path.join(DATA_DIR, "projects")
DEFAULT_STATE = {
	"title": "",
	"story": "",
	"min_shots_per_scene": 1,
	"prompts": [],
	"cuts": [],
	"saved_results": [],
	"image_job_id": "",
	"image_progress": {"status": "", "progress": 0, "message": ""},
}


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
	return state


def _save_project_state(project_id: str, state: Dict[str, Any], *, require: bool = True) -> None:
	proj_dir = _get_project_dir(project_id, require=require)
	if not proj_dir:
		return
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
	images = sorted([p for p in glob(os.path.join(OUTPUTS_DIR, "*.*")) if os.path.splitext(p)[1].lower() in {".png", ".jpg", ".jpeg", ".webp"}])
	videos = sorted([p for p in glob(os.path.join(OUTPUTS_DIR, "*.*")) if os.path.splitext(p)[1].lower() in {".mp4", ".mov", ".webm"}])
	# projects: 디렉터리의 metadata.json 읽기
	projects: List[dict] = []
	for d in sorted(glob(os.path.join(PROJECTS_DIR, "*"))):
		if not os.path.isdir(d):
			continue
		meta_path = os.path.join(d, "metadata.json")
		meta = {"id": os.path.basename(d), "title": os.path.basename(d), "createdAt": None}
		if os.path.isfile(meta_path):
			try:
				with open(meta_path, "r", encoding="utf-8") as f:
					meta.update(json.load(f))
			except Exception:
				pass
		projects.append(meta)
	return {
		"dirs": {"outputs": OUTPUTS_DIR, "temp": TEMP_DIR, "projects": PROJECTS_DIR},
		"counts": {"prompts": len(prompts), "images": len(images), "videos": len(videos), "projects": len(projects)},
		"lists": {"prompts": prompts, "images": images, "videos": videos, "projects": projects},
	}


@app.post("/api/projects")
async def api_new_project(payload: NewProjectRequest):
	os.makedirs(PROJECTS_DIR, exist_ok=True)
	title = (payload.title or "새 프로젝트").strip()
	ts = time.strftime("%Y%m%d-%H%M%S")
	slug = f"{_slugify(title)}-{ts}"
	proj_dir = os.path.join(PROJECTS_DIR, slug)
	os.makedirs(proj_dir, exist_ok=True)
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
		storyboard = generate_storyboard_from_story(
			client=openai_client,
			story_text=adjusted,
			title=payload.title,
			model="gpt-4o-mini"
		)
		
		# 각 컷에서 프롬프트 생성 (이미지 생성용)
		prompts = []
		for cut in storyboard.cuts:
			characters_str = ", ".join(cut.characters) if cut.characters else "characters"
			dialogues_str = "; ".join([f"{d.speaker}: {d.text}" for d in cut.dialogues[:3]])
			prompt = (
				f"{cut.cut_name}, {cut.composition}. "
				f"characters: {characters_str}. "
				f"background: {cut.background}. "
				f"dialogues: {dialogues_str}. "
				f"cinematic anime illustration, detailed lineart, soft shading, dramatic lighting"
			)
			prompts.append(prompt)
		
		if payload.project_id:
			state = _load_project_state(payload.project_id)
			state["story"] = payload.story
			state["title"] = storyboard.title or state.get("title") or (payload.title or "")
			if payload.min_shots_per_scene:
				state["min_shots_per_scene"] = payload.min_shots_per_scene
			state["cuts"] = [cut.model_dump() for cut in storyboard.cuts]
			state["prompts"] = prompts
			state["saved_results"] = []
			state["image_job_id"] = ""
			state["image_progress"] = {"status": "", "progress": 0, "message": ""}
			_save_project_state(payload.project_id, state)
			meta = _load_project_meta(payload.project_id)
			if storyboard.title:
				meta["title"] = storyboard.title
				_save_project_meta(payload.project_id, meta)
		return {
			"title": storyboard.title,
			"cuts": [cut.model_dump() for cut in storyboard.cuts],
			"prompts": prompts,
		}
	except Exception as e:
		raise HTTPException(500, detail=str(e))


def run_image_generation(job_id: str, prompts: List[str], model: str, size: str, output_dir: str, project_id: Optional[str] = None):
	"""백그라운드에서 이미지 생성 실행"""
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
			output_dir=output_dir
		)
		progress_store[job_id]["results"] = results
		progress_store[job_id]["status"] = "completed"
		if project_id:
			try:
				state = _load_project_state(project_id, require=False)
				state["saved_results"] = results
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
		progress_store[job_id] = {
			"status": "queued",
			"progress": 0.0,
			"message": "작업 대기 중...",
			"updated_at": datetime.now().isoformat()
		}
		if payload.project_id:
			state = _load_project_state(payload.project_id)
			state["image_job_id"] = job_id
			state["image_progress"] = progress_store[job_id]
			state["saved_results"] = []
			_save_project_state(payload.project_id, state)
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
		raise HTTPException(500, detail=str(e))


@app.get("/api/images/progress/{job_id}")
async def api_images_progress(job_id: str):
	"""이미지 생성 진행 상황 조회"""
	if job_id not in progress_store:
		raise HTTPException(404, detail="작업을 찾을 수 없습니다")
	return progress_store[job_id]


@app.post("/api/video")
async def api_video(payload: VideoJobRequest):
	try:
		output = compose_video(image_paths=payload.image_paths, fps=payload.fps, audio_path=payload.audio_path, output_path=payload.output_path)
		return {"output": output}
	except Exception as e:
		raise HTTPException(500, detail=str(e))


if __name__ == "__main__":
	import uvicorn
	uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
