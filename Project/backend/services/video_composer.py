from typing import List, Optional, Dict, Any, Tuple
import os
import platform
from moviepy.editor import (
	ImageClip, TextClip, CompositeVideoClip, concatenate_videoclips,
	ColorClip, AudioFileClip, concatenate_audioclips
)
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from .tts_generator import generate_tts
from .subtitle_splitter import format_subtitle_lines


_SPEAKER_VOICE_CACHE: Dict[str, str] = {}
_AVAILABLE_VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]


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


def _create_subtitle_clip(subtitle_text: str, duration: float, video_size: Tuple[int, int], start_time: float = 0) -> Optional[CompositeVideoClip]:
	"""자막 클립을 생성합니다 (MoviePy 방식)
	
	Args:
		subtitle_text: 자막 텍스트
		duration: 표시 시간 (초)
		video_size: 비디오 크기 (width, height)
		start_time: 시작 시간 (초)
		
	Returns:
		자막 클립 (배경 + 텍스트)
	"""
	if not subtitle_text or duration <= 0:
		return None
	
	width, height = video_size
	
	# 자막 텍스트 포맷팅 (12글자로 줄바꿈)
	formatted_subtitle = format_subtitle_lines(subtitle_text, max_length=12)
	
	# 자막 너비 설정 (화면의 80%)
	subtitle_width = int(width * 0.8)
	
	# 폰트 크기를 화면 크기에 맞게 조정
	fontsize = min(45, int(height * 0.04))  # 화면 높이의 4%, 최대 45
	
	# 폰트 경로
	font_path = _get_font_path()
	
	subtitle_clip = None
	
	# 폰트 경로가 있으면 사용
	if font_path:
		try:
			subtitle_clip = TextClip(
				formatted_subtitle,
				fontsize=fontsize,
				color='white',
				font=font_path,
				method='caption',
				size=(subtitle_width, None),
				align='center',
				stroke_color='black',
				stroke_width=2
			).set_duration(duration).set_start(start_time)
		except Exception as e:
			print(f"폰트 경로 사용 실패: {e}")
	
	# 폰트 경로 실패 시 기본 폰트
	if not subtitle_clip:
		try:
			subtitle_clip = TextClip(
				formatted_subtitle,
				fontsize=fontsize,
				color='white',
				method='caption',
				size=(subtitle_width, None),
				align='center',
				stroke_color='black',
				stroke_width=2
			).set_duration(duration).set_start(start_time)
		except Exception as e:
			print(f"자막 생성 실패: {e}")
			return None
	
	if not subtitle_clip:
		return None
	
	# 자막을 화면 중앙에 배치
	subtitle_y = (height - subtitle_clip.h) // 2
	subtitle_clip = subtitle_clip.set_position(('center', subtitle_y))
	
	# 반투명 배경 생성
	bg_clip = ColorClip(
		size=(subtitle_clip.w + 50, subtitle_clip.h + 25),
		color=(0, 0, 0),
		duration=duration
	).set_position(('center', subtitle_y - 12)).set_opacity(0.85).set_start(start_time)
	
	return CompositeVideoClip([bg_clip, subtitle_clip], size=video_size)


def _get_voice_for_speaker(speaker: str, default_voice: str = "alloy") -> str:
	"""화자 이름에 따라 고정된 TTS voice를 매핑
	
	같은 화자는 항상 같은 voice를 쓰도록 캐시합니다.
	"""
	if not speaker:
		return default_voice
	key = speaker.strip().lower()
	if key in _SPEAKER_VOICE_CACHE:
		return _SPEAKER_VOICE_CACHE[key]
	if not _AVAILABLE_VOICES:
		_SPEAKER_VOICE_CACHE[key] = default_voice
		return default_voice
	# 화자명을 기준으로 단순 해시 → 인덱스
	idx = abs(hash(key)) % len(_AVAILABLE_VOICES)
	voice = _AVAILABLE_VOICES[idx]
	_SPEAKER_VOICE_CACHE[key] = voice
	return voice


def _create_single_video_clip(
	image_path: str,
	subtitle_segments: List[Tuple[str, float]],  # [(자막텍스트, 오디오길이), ...]
	audio_segments: List[str],  # 오디오 파일 경로 리스트
	duration: float,
	output_dir: str,
	clip_index: int
) -> str:
	"""단일 이미지로 자막과 오디오가 포함된 영상 클립 생성 (음성과 동기화된 자막)
	
	Args:
		image_path: 이미지 파일 경로
		subtitle_segments: 자막 세그먼트 리스트 [(텍스트, 길이), ...]
		audio_segments: 오디오 파일 경로 리스트
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
	video_size = (img_clip.w, img_clip.h)
	
	# 자막 클립들을 시간별로 생성
	subtitle_clips = []
	current_time = 0
	
	for subtitle_text, segment_duration in subtitle_segments:
		if subtitle_text and segment_duration > 0:
			subtitle_clip = _create_subtitle_clip(
				subtitle_text=subtitle_text,
				duration=segment_duration,
				video_size=video_size,
				start_time=current_time
			)
			if subtitle_clip:
				subtitle_clips.append(subtitle_clip)
				print(f"  자막 추가: '{subtitle_text[:20]}...' ({current_time:.1f}초 ~ {current_time + segment_duration:.1f}초)")
		current_time += segment_duration
	
	# 이미지와 자막들을 합성
	if subtitle_clips:
		# 모든 자막 클립을 하나의 CompositeVideoClip으로 합성
		all_clips = [img_clip] + subtitle_clips
		clip = CompositeVideoClip(all_clips, size=video_size).set_duration(duration)
		print(f"✓ {len(subtitle_clips)}개 자막 세그먼트 추가 완료 (클립 {clip_index})")
	else:
		clip = img_clip
		print(f"ℹ 자막 없음 (클립 {clip_index})")
	
	# 오디오 합치기
	if audio_segments:
		audio_clips = []
		for audio_path in audio_segments:
			if os.path.exists(audio_path):
				audio_clips.append(AudioFileClip(audio_path))
		
		if audio_clips:
			combined_audio = concatenate_audioclips(audio_clips)
			# 오디오 길이에 맞춰 영상 조정
			if combined_audio.duration > duration:
				clip = clip.set_duration(combined_audio.duration)
			clip = clip.set_audio(combined_audio)
			
			# 오디오 클립 정리
			for ac in audio_clips:
				ac.close()
	
	# 개별 클립 저장
	clip_output_path = os.path.join(output_dir, f"clip_{clip_index:03d}.mp4")
	os.makedirs(output_dir, exist_ok=True)
	
	clip.write_videofile(
		clip_output_path,
		fps=24,
		codec='libx264',
		audio_codec='aac' if audio_segments else None,
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
		
		# 자막 세그먼트와 TTS 세그먼트 추출
		subtitle_segments: List[Tuple[str, float]] = []  # [(자막텍스트, 길이), ...]
		audio_segment_paths: List[str] = []
		
		if cut and "dialogues" in cut and use_tts:
			dialogues = cut.get("dialogues", [])
			
			# 각 대사별로 TTS 생성 및 길이 측정
			for seg_idx, dialogue in enumerate(dialogues):
				if isinstance(dialogue, dict):
					speaker = dialogue.get("speaker", "")
					text = dialogue.get("text", "")
					
					if text:
						# 화자별 음성 선택
						if speaker and speaker.lower() != "narration":
							subtitle_text = f"[{speaker}] {text}"
							voice = _get_voice_for_speaker(speaker, default_voice=tts_voice)
						else:
							subtitle_text = text
							voice = tts_voice
						
						# TTS 생성
						seg_output_path = os.path.join(audio_dir, f"audio_{i:03d}_{seg_idx:02d}.mp3")
						try:
							generate_tts(
								text=text.strip(),
								output_path=seg_output_path,
								voice=voice
							)
							
							if os.path.exists(seg_output_path):
								# 오디오 길이 측정
								audio_clip = AudioFileClip(seg_output_path)
								segment_duration = audio_clip.duration
								audio_clip.close()
								
								# 자막 세그먼트 추가
								subtitle_segments.append((subtitle_text, segment_duration))
								audio_segment_paths.append(seg_output_path)
								generated_audio_paths.append(seg_output_path)
								
								print(f"  대사 {seg_idx+1}: '{text[:30]}...' ({segment_duration:.1f}초)")
						except Exception as e:
							print(f"  TTS 생성 실패 (대사 {seg_idx+1}): {e}")
							continue
			
			# 전체 duration을 오디오 길이 합으로 조정
			if subtitle_segments:
				total_audio_duration = sum(seg[1] for seg in subtitle_segments)
				duration = max(duration, total_audio_duration)
		
		elif audio_path and i == 0:
			# 첫 번째 이미지에만 기존 오디오 사용
			audio_segment_paths = [audio_path]
		
		# 개별 영상 클립 생성
		try:
			print(f"\n=== 클립 {i+1}/{len(image_paths)} 생성 시작 ===")
			print(f"이미지: {os.path.basename(image_path)}")
			print(f"자막 세그먼트: {len(subtitle_segments)}개")
			print(f"오디오 세그먼트: {len(audio_segment_paths)}개")
			print(f"전체 길이: {duration:.1f}초")
			
			clip_path = _create_single_video_clip(
				image_path=image_path,
				subtitle_segments=subtitle_segments,
				audio_segments=audio_segment_paths,
				duration=duration,
				output_dir=clips_dir,
				clip_index=i
			)
			clip_paths.append(clip_path)
			print(f"✓ 클립 생성 완료: {os.path.basename(clip_path)}")
		except Exception as e:
			print(f"✗ 클립 생성 실패 (이미지 {i+1}): {e}")
			import traceback
			traceback.print_exc()
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
