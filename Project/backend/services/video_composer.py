from typing import List, Optional, Dict, Any
import os
import platform
from moviepy.editor import (
	ImageClip, TextClip, CompositeVideoClip, concatenate_videoclips,
	ColorClip, AudioFileClip
)
from .tts_generator import generate_tts
from .subtitle_splitter import format_subtitle_lines


def _get_font_path() -> Optional[str]:
	"""시스템에 맞는 한글 지원 폰트 경로 반환"""
	system = platform.system()
	
	if system == "Windows":
		# Windows 한글 폰트 경로들
		font_paths = [
			"C:/Windows/Fonts/malgun.ttf",  # 맑은 고딕
			"C:/Windows/Fonts/gulim.ttc",   # 굴림
			"C:/Windows/Fonts/batang.ttc",  # 바탕
		]
		for path in font_paths:
			if os.path.exists(path):
				return path
	elif system == "Darwin":  # macOS
		font_paths = [
			"/System/Library/Fonts/AppleGothic.ttf",
			"/Library/Fonts/AppleGothic.ttf",
		]
		for path in font_paths:
			if os.path.exists(path):
				return path
	# Linux나 기타 시스템은 기본값 사용
	return None


def _create_single_video_clip(
	image_path: str,
	subtitle_text: str,
	audio_path: Optional[str],
	duration: float,
	output_dir: str,
	clip_index: int
) -> str:
	"""단일 이미지로 자막과 오디오가 포함된 영상 클립 생성
	
	Args:
		image_path: 이미지 파일 경로
		subtitle_text: 자막 텍스트
		audio_path: 오디오 파일 경로 (None이면 duration만큼 무음)
		duration: 영상 길이 (초)
		output_dir: 출력 디렉토리
		clip_index: 클립 인덱스
		
	Returns:
		생성된 영상 파일 경로
	"""
	if not os.path.exists(image_path):
		raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {image_path}")
	
	# 이미지 클립 생성
	img_clip = ImageClip(image_path, duration=duration)
	
	# 자막이 있으면 추가
	if subtitle_text:
		# 자막을 11글자 이상일 때 분할
		formatted_subtitle = format_subtitle_lines(subtitle_text, max_length=11)
		
		# 자막 너비 설정 (이미지 너비의 90%, 최소 400px)
		subtitle_width = max(int(img_clip.w * 0.9), 400)
		
		# 자막 클립 생성
		font_path = _get_font_path()
		subtitle_clip = None
		
		if font_path:
			try:
				subtitle_clip = TextClip(
					formatted_subtitle,
					fontsize=36,
					color='white',
					font=font_path,
					method='caption',
					size=(subtitle_width, None),
					align='center'
				).set_duration(duration)
			except Exception as e:
				print(f"폰트 경로 사용 실패 (클립 {clip_index}): {e}")
		
		if not subtitle_clip:
			try:
				subtitle_clip = TextClip(
					formatted_subtitle,
					fontsize=36,
					color='white',
					method='caption',
					size=(subtitle_width, None),
					align='center'
				).set_duration(duration)
			except Exception as e2:
				print(f"자막 생성 실패 (클립 {clip_index}): {e2}")
				subtitle_clip = None
		
		if subtitle_clip:
			# 자막 위치 설정 (하단 중앙, 여백 60px)
			subtitle_y = img_clip.h - subtitle_clip.h - 60
			subtitle_clip = subtitle_clip.set_position(('center', subtitle_y))
			
			# 반투명 배경 생성
			bg_clip = ColorClip(
				size=(subtitle_clip.w + 40, subtitle_clip.h + 20),
				color=(0, 0, 0),
				duration=duration
			).set_position(('center', subtitle_y - 10)).set_opacity(0.7)
			
			# 이미지, 배경, 자막 합성
			clip = CompositeVideoClip([img_clip, bg_clip, subtitle_clip])
		else:
			clip = img_clip
	else:
		clip = img_clip
	
	# 오디오 추가
	if audio_path and os.path.exists(audio_path):
		audio_clip = AudioFileClip(audio_path)
		# 오디오 길이에 맞춰 영상 조정
		if audio_clip.duration > duration:
			clip = clip.set_duration(audio_clip.duration)
		clip = clip.set_audio(audio_clip)
	
	# 개별 클립 저장
	clip_output_path = os.path.join(output_dir, f"clip_{clip_index:03d}.mp4")
	os.makedirs(output_dir, exist_ok=True)
	
	clip.write_videofile(
		clip_output_path,
		fps=24,
		codec='libx264',
		audio_codec='aac' if (audio_path and os.path.exists(audio_path)) else None,
		preset='medium',
		threads=4,
		verbose=False,
		logger=None
	)
	
	# 리소스 정리
	clip.close()
	if 'img_clip' in locals():
		img_clip.close()
	
	return clip_output_path


def compose_video(
	image_paths: List[str],
	cuts: Optional[List[Dict[str, Any]]] = None,
	*,
	fps: int = 24,
	audio_path: Optional[str] = None,
	output_path: str = "../data/outputs/final.mp4",
	project_id: Optional[str] = None,
	use_tts: bool = True,
	tts_voice: str = "alloy"
) -> Dict[str, Any]:
	"""MoviePy를 사용하여 이미지들에 자막과 TTS를 추가하고 영상으로 합성
	
	각 이미지별로 개별 영상을 생성한 후 모두 합쳐서 최종 영상을 만듭니다.
	
	Args:
		image_paths: 이미지 파일 경로 리스트
		cuts: 컷 정보 리스트 (각 컷의 dialogues와 duration 포함)
		fps: 프레임 레이트
		audio_path: 기존 오디오 파일 경로 (선택사항, TTS 우선)
		output_path: 출력 영상 파일 경로
		project_id: 프로젝트 ID (데이터 보관용)
		use_tts: TTS 사용 여부
		tts_voice: TTS 음성 종류
		
	Returns:
		생성된 영상 파일 경로와 메타데이터
	"""
	os.makedirs(os.path.dirname(output_path), exist_ok=True)
	
	# 프로젝트별 디렉토리 구조 설정
	if project_id:
		# 상대 경로로 PROJECTS_DIR 계산
		BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
		DATA_DIR = os.path.normpath(os.path.join(BASE_DIR, "../data"))
		PROJECTS_DIR = os.path.join(DATA_DIR, "projects")
		proj_dir = os.path.join(PROJECTS_DIR, project_id)
		clips_dir = os.path.join(proj_dir, "videos", "clips")
		audio_dir = os.path.join(proj_dir, "audio")
		os.makedirs(clips_dir, exist_ok=True)
		os.makedirs(audio_dir, exist_ok=True)
	else:
		clips_dir = os.path.join(os.path.dirname(output_path), "clips")
		audio_dir = os.path.join(os.path.dirname(output_path), "audio")
		os.makedirs(clips_dir, exist_ok=True)
		os.makedirs(audio_dir, exist_ok=True)
	
	clip_paths = []
	generated_audio_paths = []
	
	# 각 이미지별로 개별 영상 생성
	for i, image_path in enumerate(image_paths):
		if not os.path.exists(image_path):
			print(f"경고: 이미지 파일을 찾을 수 없습니다: {image_path}")
			continue
		
		# 컷 정보 가져오기
		cut = None
		if cuts and i < len(cuts):
			cut = cuts[i]
		
		# duration 설정
		duration = 3.0
		if cut and "duration" in cut:
			duration = float(cut.get("duration", 3.0))
		
		# 자막 텍스트 추출
		subtitle_texts = []
		full_text_for_tts = ""
		if cut and "dialogues" in cut:
			dialogues = cut.get("dialogues", [])
			for dialogue in dialogues:
				if isinstance(dialogue, dict):
					speaker = dialogue.get("speaker", "")
					text = dialogue.get("text", "")
					if text:
						if speaker and speaker.lower() != "narration":
							subtitle_texts.append(f"{speaker}: {text}")
							full_text_for_tts += f"{speaker}: {text} "
						else:
							subtitle_texts.append(text)
							full_text_for_tts += f"{text} "
		
		subtitle_text = "\n".join(subtitle_texts) if subtitle_texts else ""
		
		# TTS 생성
		clip_audio_path = None
		if use_tts and full_text_for_tts.strip():
			try:
				audio_output_path = os.path.join(audio_dir, f"audio_{i:03d}.mp3")
				generate_tts(
					text=full_text_for_tts.strip(),
					output_path=audio_output_path,
					voice=tts_voice
				)
				clip_audio_path = audio_output_path
				generated_audio_paths.append(audio_output_path)
				
				# TTS 길이에 맞춰 duration 조정
				if os.path.exists(audio_output_path):
					audio_clip = AudioFileClip(audio_output_path)
					duration = max(duration, audio_clip.duration)
					audio_clip.close()
			except Exception as e:
				print(f"TTS 생성 실패 (이미지 {i+1}): {e}")
		elif audio_path and i == 0:
			# 첫 번째 이미지에만 기존 오디오 사용 (전체 오디오인 경우)
			clip_audio_path = audio_path
		
		# 개별 영상 클립 생성
		try:
			clip_path = _create_single_video_clip(
				image_path=image_path,
				subtitle_text=subtitle_text,
				audio_path=clip_audio_path,
				duration=duration,
				output_dir=clips_dir,
				clip_index=i
			)
			clip_paths.append(clip_path)
		except Exception as e:
			print(f"클립 생성 실패 (이미지 {i+1}): {e}")
			continue
	
	if not clip_paths:
		raise ValueError("생성할 영상 클립이 없습니다.")
	
	# 모든 클립 로드 및 합치기
	from moviepy.editor import VideoFileClip
	video_clips = [VideoFileClip(path) for path in clip_paths if os.path.exists(path)]
	
	if not video_clips:
		raise ValueError("로드할 영상 클립이 없습니다.")
	
	# 모든 클립 합치기
	final_clip = concatenate_videoclips(video_clips, method="compose")
	
	# 최종 영상 저장
	final_clip.write_videofile(
		output_path,
		fps=fps,
		codec='libx264',
		audio_codec='aac',
		preset='medium',
		threads=4
	)
	
	# 리소스 정리
	final_clip.close()
	for clip in video_clips:
		clip.close()
	
	return {
		"output_path": output_path,
		"clip_paths": clip_paths,
		"audio_paths": generated_audio_paths,
		"total_duration": sum(clip.duration for clip in video_clips)
	}
