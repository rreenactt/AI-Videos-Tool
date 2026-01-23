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

# config에서 ImageMagick 경로 가져오기
try:
	import sys
	backend_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
	if backend_path not in sys.path:
		sys.path.insert(0, backend_path)
	from config import IMAGEMAGICK_BINARY
	
	# ImageMagick 경로 설정
	if IMAGEMAGICK_BINARY and os.path.exists(IMAGEMAGICK_BINARY):
		os.environ["IMAGEMAGICK_BINARY"] = IMAGEMAGICK_BINARY
		# MoviePy config에도 설정
		try:
			from moviepy.config import change_settings
			change_settings({"IMAGEMAGICK_BINARY": IMAGEMAGICK_BINARY})
			print(f"✅ ImageMagick 설정: {IMAGEMAGICK_BINARY}")
		except Exception as e:
			print(f"⚠ MoviePy 설정 실패: {e}")
	else:
		print(f"ℹ️  ImageMagick 미설정 (자막 비활성화, 오디오는 정상)")
except ImportError:
	print(f"⚠ config.py를 찾을 수 없습니다. backend/config.py를 생성하세요.")
	IMAGEMAGICK_BINARY = None


_SPEAKER_VOICE_CACHE: Dict[str, str] = {}
# Google Cloud TTS 한국어 음성 목록
_AVAILABLE_VOICES = ["default", "female_a", "female_b", "male_a", "male_b", "narrator"]


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
	elif system == "Linux":
		# Linux 한글 폰트 경로들 (Noto CJK, 나눔 폰트)
		font_paths = [
			# Noto CJK 폰트 (fonts-noto-cjk 패키지)
			"/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
			"/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
			"/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
			"/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
			# 나눔 폰트 (fonts-nanum 패키지)
			"/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
			"/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
			"/usr/share/fonts/opentype/nanum/NanumGothic.ttf",
		]
		for path in font_paths:
			if os.path.exists(path):
				return path
	# 기본값
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
	
	# 자막 생성 시도
	fontsize = min(45, int(height * 0.04))  # 화면 높이의 4%, 최대 45
	
	subtitle_clip = None
	
	try:
		font_path = _get_font_path()
		
		# 폰트 경로가 있으면 사용
		if font_path and os.path.exists(font_path):
			subtitle_clip = TextClip(
				formatted_subtitle,
				fontsize=fontsize,
				color='white',
				font=font_path,
				method='caption',
				size=(subtitle_width, None),
				align='center'
			).set_duration(duration).set_start(start_time)
		else:
			# 기본 폰트 사용
			subtitle_clip = TextClip(
				formatted_subtitle,
				fontsize=fontsize,
				color='white',
				method='caption',
				size=(subtitle_width, None),
				align='center'
			).set_duration(duration).set_start(start_time)
	except Exception as e:
		# 실패 원인 출력 (디버깅용)
		error_msg = str(e)
		if "ImageMagick" in error_msg or "magick" in error_msg.lower():
			# ImageMagick 문제는 조용히
			pass
		else:
			# 다른 에러는 출력
			print(f"  ⚠ 자막 생성 실패: {error_msg[:60]}")
		return None
	
	if not subtitle_clip:
		return None
	
	# 자막을 화면 상단 40% 위치에 배치 (기존 중앙에서 위로 이동)
	subtitle_y = int(height * 0.40) - (subtitle_clip.h // 2)
	subtitle_clip = subtitle_clip.set_position(('center', subtitle_y))
	
	# 반투명 배경 생성
	bg_clip = ColorClip(
		size=(subtitle_clip.w + 50, subtitle_clip.h + 25),
		color=(0, 0, 0),
		duration=duration
	).set_position(('center', subtitle_y - 12)).set_opacity(0.85).set_start(start_time)
	
	return CompositeVideoClip([bg_clip, subtitle_clip], size=video_size)


def _get_voice_for_speaker(speaker: str, default_voice: str = "default") -> str:
	"""화자 이름에 따라 고정된 Google TTS voice를 매핑
	
	같은 화자는 항상 같은 voice를 쓰도록 캐시합니다.
	"""
	if not speaker:
		return default_voice
	key = speaker.strip().lower()
	if key in _SPEAKER_VOICE_CACHE:
		return _SPEAKER_VOICE_CACHE[key]
	
	# 나레이션은 특별 처리
	if "나레이션" in key or "narration" in key or "narrator" in key:
		_SPEAKER_VOICE_CACHE[key] = "narrator"
		return "narrator"
	
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
	
	# 자막 클립들을 시간별로 생성 (12글자씩 분할하여 순차 표시)
	subtitle_clips = []
	current_time = 0
	
	subtitle_success_count = 0
	subtitle_fail_count = 0
	
	for subtitle_text, segment_duration in subtitle_segments:
		if subtitle_text and segment_duration > 0:
			# 자막을 12글자 단위로 분할
			from .subtitle_splitter import split_subtitle_by_length
			sub_segments = split_subtitle_by_length(subtitle_text, max_length=12)
			
			if len(sub_segments) > 1:
				# 여러 세그먼트로 분할된 경우: 시간을 균등 분배
				sub_duration = segment_duration / len(sub_segments)
				for sub_text in sub_segments:
					try:
						subtitle_clip = _create_subtitle_clip(
							subtitle_text=sub_text,
							duration=sub_duration,
							video_size=video_size,
							start_time=current_time
						)
						if subtitle_clip:
							subtitle_clips.append(subtitle_clip)
							print(f"  ✅ 자막: '{sub_text}' ({current_time:.1f}~{current_time + sub_duration:.1f}초)")
							subtitle_success_count += 1
						else:
							subtitle_fail_count += 1
					except Exception as e:
						subtitle_fail_count += 1
					current_time += sub_duration
			else:
				# 단일 세그먼트 (12글자 이하)
				try:
					subtitle_clip = _create_subtitle_clip(
						subtitle_text=subtitle_text,
						duration=segment_duration,
						video_size=video_size,
						start_time=current_time
					)
					if subtitle_clip:
						subtitle_clips.append(subtitle_clip)
						print(f"  ✅ 자막: '{subtitle_text}' ({current_time:.1f}~{current_time + segment_duration:.1f}초)")
						subtitle_success_count += 1
					else:
						subtitle_fail_count += 1
				except Exception as e:
					subtitle_fail_count += 1
				current_time += segment_duration
	
	if subtitle_fail_count > 0 and subtitle_success_count == 0:
		# 모든 자막이 실패한 경우에만 메시지 출력
		print(f"  ℹ️  자막 생성 실패 (ImageMagick 설정 필요 - 오디오만 사용)")
	
	# 이미지와 자막들을 합성
	if subtitle_clips:
		try:
			# 모든 자막 클립을 하나의 CompositeVideoClip으로 합성
			all_clips = [img_clip] + subtitle_clips
			clip = CompositeVideoClip(all_clips, size=video_size).set_duration(duration)
			if len(subtitle_clips) > 0:
				print(f"  💬 자막 합성 완료: {len(subtitle_clips)}개")
		except Exception as e:
			print(f"  ⚠ 자막 합성 실패: {str(e)[:50]}, 자막 없이 진행")
			clip = img_clip
			# 자막 클립 정리
			for sc in subtitle_clips:
				try:
					sc.close()
				except:
					pass
	else:
		clip = img_clip
	
	# 오디오 합치기 - 파일 경로로부터 새로 로드
	if audio_segments:
		audio_clips = []
		print(f"  🎵 오디오 로드 중: {len(audio_segments)}개 파일")
		
		for audio_path in audio_segments:
			if not os.path.exists(audio_path):
				print(f"  ⚠ 파일 없음: {os.path.basename(audio_path)}")
				continue
			
			try:
				# 파일 크기 먼저 확인
				file_size = os.path.getsize(audio_path)
				if file_size < 100:
					print(f"  ⚠ 파일 너무 작음 ({file_size} bytes): {os.path.basename(audio_path)}")
					continue
				
				# 새로 로드 (이전에 close된 클립 재사용 안함)
				audio_clip = AudioFileClip(audio_path)
				
				# 기본 검증
				if not hasattr(audio_clip, 'reader') or audio_clip.reader is None:
					print(f"  ⚠ 리더 None: {os.path.basename(audio_path)}")
					try:
						audio_clip.close()
					except:
						pass
					continue
				
				if audio_clip.duration <= 0:
					print(f"  ⚠ duration 0: {os.path.basename(audio_path)}")
					try:
						audio_clip.close()
					except:
						pass
					continue
				
				# 프레임 읽기 테스트
				try:
					test_frame = audio_clip.get_frame(0)
					if test_frame is None:
						raise Exception("프레임 None")
				except Exception as frame_e:
					print(f"  ⚠ 프레임 테스트 실패: {os.path.basename(audio_path)}")
					try:
						audio_clip.close()
					except:
						pass
					continue
				
				# 모든 검증 통과
				audio_clips.append(audio_clip)
				print(f"  ✓ 로드 완료: {os.path.basename(audio_path)} ({audio_clip.duration:.1f}초)")
				
			except Exception as e:
				print(f"  ⚠ 로드 실패: {os.path.basename(audio_path)} - {str(e)[:40]}")
				continue
		
		if audio_clips:
			try:
				# 모든 클립이 유효한지 최종 확인
				valid_clips = []
				for idx, ac in enumerate(audio_clips):
					try:
						# reader 체크
						if not hasattr(ac, 'reader') or ac.reader is None:
							print(f"  ⚠ 클립 {idx+1} 리더 None, 제거")
							ac.close()
							continue
						
						# get_frame 테스트
						test_frame = ac.get_frame(0)
						if test_frame is None:
							print(f"  ⚠ 클립 {idx+1} 프레임 None, 제거")
							ac.close()
							continue
						
						valid_clips.append(ac)
					except Exception as e:
						print(f"  ⚠ 클립 {idx+1} 검증 실패, 제거: {str(e)[:30]}")
						try:
							ac.close()
						except:
							pass
				
				if not valid_clips:
					print(f"  ⚠ 유효한 오디오 클립이 없음, 무음으로 진행")
				elif len(valid_clips) == 1:
					# 클립이 1개만 있으면 합성 없이 바로 사용
					single_audio = valid_clips[0]
					try:
						# duration 조정
						if single_audio.duration > duration:
							duration = single_audio.duration
							clip = clip.set_duration(duration)
						
						# 오디오 설정
						clip = clip.set_audio(single_audio)
						print(f"  ✅ 오디오 적용: {single_audio.duration:.1f}초")
					except Exception as e:
						print(f"  ⚠ 오디오 적용 실패: {str(e)[:50]}, 무음으로 진행")
						try:
							single_audio.close()
						except:
							pass
				else:
					# 여러 클립 합성
					print(f"  🔗 {len(valid_clips)}개 오디오 합성 중...")
					combined_success = False
					
					try:
						# concatenate 시도
						combined_audio = concatenate_audioclips(valid_clips)
						
						# 합성 결과 검증 (CompositeAudioClip은 reader가 없을 수 있음)
						# 프레임 읽기 테스트로 대체
						try:
							test_combined = combined_audio.get_frame(0)
							if test_combined is None:
								raise Exception("합성 오디오 프레임 None")
							
							# 성공 - 오디오 적용
							if combined_audio.duration > duration:
								duration = combined_audio.duration
								clip = clip.set_duration(duration)
							
							clip = clip.set_audio(combined_audio)
							print(f"  ✅ 오디오 합성 완료: {combined_audio.duration:.1f}초")
							combined_success = True
							
						except Exception as verify_error:
							print(f"  ⚠ 합성 오디오 검증 실패: {str(verify_error)[:50]}")
							try:
								combined_audio.close()
							except:
								pass
					
					except Exception as concat_error:
						print(f"  ⚠ concatenate 실패: {str(concat_error)[:50]}")
					
					# 합성 실패 시 가장 긴 클립만 사용
					if not combined_success and valid_clips:
						try:
							longest = max(valid_clips, key=lambda x: x.duration)
							if longest.duration > duration:
								duration = longest.duration
								clip = clip.set_duration(duration)
							clip = clip.set_audio(longest)
							print(f"  ⚠ 대신 가장 긴 오디오 사용: {longest.duration:.1f}초")
						except Exception as fallback_e:
							print(f"  ✗ 모든 방법 실패: {str(fallback_e)[:40]}, 무음")
						
			except Exception as e:
				print(f"  ⚠ 오디오 처리 실패: {str(e)[:70]}, 무음으로 진행")
			# finally:
			# 	# 오디오 클립은 close하지 않음 (clip.set_audio로 연결되어 있음)
			# 	# clip이 close될 때 자동으로 정리됨
			# 	pass
		else:
			print(f"  ℹ️  오디오 없음 (무음 영상)")
	
	# 개별 클립 저장
	clip_output_path = os.path.join(output_dir, f"clip_{clip_index:03d}.mp4")
	os.makedirs(output_dir, exist_ok=True)
	
	try:
		# 오디오가 있는지 확인
		has_audio = hasattr(clip, 'audio') and clip.audio is not None
		
		if has_audio:
			# 오디오 유효성 철저하게 검증
			audio_valid = False
			
			try:
				# 1. reader 확인 (있는 경우에만)
				if hasattr(clip.audio, 'reader'):
					if clip.audio.reader is None:
						print(f"  ⚠ 오디오 리더 None → 제거")
					else:
						audio_valid = True
				else:
					# CompositeAudioClip 등은 reader가 없을 수 있음
					audio_valid = True
				
				# 2. 프레임 읽기 테스트 (최종 검증)
				if audio_valid:
					try:
						test_frame = clip.audio.get_frame(0)
						if test_frame is None:
							audio_valid = False
							print(f"  ⚠ 오디오 프레임 None → 제거")
						else:
							# duration도 확인
							if clip.audio.duration <= 0:
								audio_valid = False
								print(f"  ⚠ 오디오 duration 0 → 제거")
					except Exception as frame_e:
						audio_valid = False
						print(f"  ⚠ 프레임 테스트 실패 → 제거: {str(frame_e)[:30]}")
				
			except Exception as check_error:
				audio_valid = False
				print(f"  ⚠ 오디오 검증 실패 → 제거: {str(check_error)[:30]}")
			
			if not audio_valid:
				# 유효하지 않으면 오디오 제거
				try:
					clip = clip.without_audio()
					has_audio = False
				except Exception as remove_e:
					print(f"  ⚠ 오디오 제거 실패: {str(remove_e)[:30]}")
					has_audio = False
		
		if has_audio:
			# 유효한 오디오가 있으면 오디오 포함 저장
			try:
				clip.write_videofile(
					clip_output_path,
					fps=24,
					codec='libx264',
					audio_codec='aac',
					preset='medium',
					threads=4,
					verbose=False,
					logger=None
				)
			except Exception as audio_error:
				# 오디오 포함 저장 실패 시, 오디오 제거하고 재시도
				print(f"  ⚠ 오디오 포함 저장 실패, 오디오 제거 후 재시도: {str(audio_error)[:70]}")
				try:
					clip = clip.without_audio()
					clip.write_videofile(
						clip_output_path,
						fps=24,
						codec='libx264',
						audio_codec=None,
						preset='medium',
						threads=4,
						verbose=False,
						logger=None
					)
					has_audio = False
				except Exception as retry_error:
					raise Exception(f"오디오 제거 후에도 저장 실패: {str(retry_error)[:50]}")
		else:
			# 오디오가 없으면 비디오만 저장
			clip.write_videofile(
				clip_output_path,
				fps=24,
				codec='libx264',
				audio_codec=None,
				preset='medium',
				threads=4,
				verbose=False,
				logger=None
			)
		
		# 파일이 제대로 생성되었는지 확인
		if not os.path.exists(clip_output_path):
			raise Exception("클립 파일이 생성되지 않았습니다")
		
		file_size = os.path.getsize(clip_output_path)
		if file_size < 1000:
			raise Exception(f"클립 파일이 너무 작습니다 ({file_size} bytes)")
		
		audio_status = "오디오 포함" if has_audio else "무음"
		print(f"  ✓ 클립 저장 완료: {os.path.basename(clip_output_path)} ({file_size / 1024:.1f} KB, {audio_status})")
		
	except Exception as e:
		raise Exception(f"클립 저장 실패: {str(e)}")
	finally:
		# 리소스 정리
		try:
			clip.close()
		except:
			pass
		if 'img_clip' in locals():
			try:
				img_clip.close()
			except:
				pass
	
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
						# 화자별 음성 선택 (자막에는 화자 표시 안함)
						subtitle_text = text  # [나레이션] 등 표시 제거
						if speaker and speaker.lower() not in ["narration", "나레이션"]:
							voice = _get_voice_for_speaker(speaker, default_voice=tts_voice)
						else:
							voice = tts_voice
						
						# TTS 생성 (Google Cloud TTS + SSML)
						seg_output_path = os.path.join(audio_dir, f"audio_{i:03d}_{seg_idx:02d}.mp3")
						try:
							generate_tts(
								text=text.strip(),
								output_path=seg_output_path,
								voice=voice,
								use_ssml=True,  # GPT로 SSML 변환
								emotion="neutral"
							)
							
							if not os.path.exists(seg_output_path):
								print(f"  ⚠ TTS 파일 생성 안됨 (대사 {seg_idx+1})")
								continue
							
							# 파일 크기 확인
							file_size = os.path.getsize(seg_output_path)
							if file_size < 100:
								print(f"  ⚠ TTS 파일 너무 작음 ({file_size} bytes, 대사 {seg_idx+1})")
								os.remove(seg_output_path)
								continue
							
							# 오디오 길이 측정 (간단하게)
							try:
								# ffprobe로 duration 확인 (더 안정적)
								from moviepy.video.io.ffmpeg_reader import ffmpeg_parse_infos
								try:
									infos = ffmpeg_parse_infos(seg_output_path)
									segment_duration = infos.get('duration', 0)
									
									if segment_duration <= 0:
										print(f"  ⚠ 오디오 duration 0 (대사 {seg_idx+1}), 파일 삭제")
										os.remove(seg_output_path)
										continue
									
									# 자막 세그먼트 추가 (파일 경로만 저장, 나중에 로드)
									subtitle_segments.append((subtitle_text, segment_duration))
									audio_segment_paths.append(seg_output_path)
									generated_audio_paths.append(seg_output_path)
									
									print(f"  ✓ 대사 {seg_idx+1}: '{text[:30]}...' ({segment_duration:.1f}초, {file_size/1024:.1f}KB)")
									
								except Exception as ffprobe_error:
									# ffprobe 실패 시 AudioFileClip으로 폴백
									test_clip = AudioFileClip(seg_output_path)
									
									# reader 확인
									if test_clip.reader is None:
										print(f"  ⚠ 오디오 리더 None (대사 {seg_idx+1}), 파일 삭제")
										test_clip.close()
										os.remove(seg_output_path)
										continue
									
									# duration 확인
									if test_clip.duration <= 0:
										print(f"  ⚠ 오디오 duration 0 (대사 {seg_idx+1}), 파일 삭제")
										test_clip.close()
										os.remove(seg_output_path)
										continue
									
									segment_duration = test_clip.duration
									test_clip.close()
									
									# 자막 세그먼트 추가
									subtitle_segments.append((subtitle_text, segment_duration))
									audio_segment_paths.append(seg_output_path)
									generated_audio_paths.append(seg_output_path)
									
									print(f"  ✓ 대사 {seg_idx+1}: '{text[:30]}...' ({segment_duration:.1f}초, {file_size/1024:.1f}KB)")
								
							except Exception as e:
								print(f"  ⚠ 오디오 검증 실패 (대사 {seg_idx+1}): {str(e)[:50]}")
								if os.path.exists(seg_output_path):
									os.remove(seg_output_path)
								continue
								
						except Exception as e:
							print(f"  ✗ TTS 생성 실패 (대사 {seg_idx+1}): {str(e)[:50]}")
							if os.path.exists(seg_output_path):
								try:
									os.remove(seg_output_path)
								except:
									pass
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
			print(f"\n{'='*60}")
			print(f"🎬 클립 {i+1}/{len(image_paths)}: {os.path.basename(image_path)}")
			print(f"{'='*60}")
			print(f"   💬 자막: {len(subtitle_segments)}개 | 🎵 오디오: {len(audio_segment_paths)}개 | ⏱️  {duration:.1f}초")
			
			clip_path = _create_single_video_clip(
				image_path=image_path,
				subtitle_segments=subtitle_segments,
				audio_segments=audio_segment_paths,
				duration=duration,
				output_dir=clips_dir,
				clip_index=i
			)
			clip_paths.append(clip_path)
			print(f"\n✅ 클립 {i+1} 완료\n")
		except Exception as e:
			print(f"\n❌ 클립 {i+1} 실패: {str(e)[:80]}")
			print(f"⏩ 다음 클립으로 계속...\n")
			continue
	
	if not clip_paths:
		raise ValueError("생성할 영상 클립이 없습니다. 모든 클립 생성에 실패했습니다.")
	
	print(f"\n{'='*60}")
	print(f"🎞️  최종 영상 합성")
	print(f"{'='*60}")
	print(f"✅ 생성 성공: {len(clip_paths)}개 클립")
	print(f"❌ 생성 실패: {len(image_paths) - len(clip_paths)}개 클립")
	print(f"{'='*60}\n")
	
	# 모든 클립 로드 및 합치기
	from moviepy.editor import VideoFileClip
	video_clips = []
	
	for idx, path in enumerate(clip_paths):
		if os.path.exists(path):
			try:
				clip = VideoFileClip(path)
				if clip.duration > 0:
					video_clips.append(clip)
					print(f"  ✓ 클립 {idx+1} 로드: {clip.duration:.1f}초")
				else:
					print(f"  ⚠ 클립 {idx+1} 스킵: duration이 0")
					clip.close()
			except Exception as e:
				print(f"  ✗ 클립 {idx+1} 로드 실패: {str(e)[:100]}")
				continue
		else:
			print(f"  ✗ 클립 {idx+1} 파일 없음: {path}")
	
	if not video_clips:
		raise ValueError("로드할 영상 클립이 없습니다. 모든 클립이 손상되었거나 누락되었습니다.")
	
	print(f"\n총 {len(video_clips)}개 클립을 합칩니다...")
	
	# 모든 클립 합치기
	try:
		final_clip = concatenate_videoclips(video_clips, method="compose")
		total_duration = final_clip.duration
		print(f"✓ 클립 합성 완료: {total_duration:.1f}초")
	except Exception as e:
		# 리소스 정리
		for clip in video_clips:
			try:
				clip.close()
			except:
				pass
		raise Exception(f"클립 합성 실패: {str(e)}")
	
	# 최종 영상 저장
	print(f"\n💾 최종 영상 저장 중...")
	print(f"   경로: {output_path}")
	print(f"   길이: {total_duration:.1f}초")
	print(f"   FPS: {fps}")
	try:
		final_clip.write_videofile(
			output_path,
			fps=fps,
			codec='libx264',
			audio_codec='aac',
			preset='medium',
			threads=4,
			verbose=False,
			logger=None
		)
		file_size = os.path.getsize(output_path) / (1024 * 1024)  # MB
		print(f"\n{'='*60}")
		print(f"🎉 영상 생성 완료!")
		print(f"{'='*60}")
		print(f"📁 파일: {os.path.basename(output_path)}")
		print(f"📏 크기: {file_size:.1f} MB")
		print(f"⏱️  길이: {total_duration:.1f}초")
		print(f"🎬 클립: {len(video_clips)}개")
		print(f"{'='*60}\n")
	except Exception as e:
		raise Exception(f"영상 저장 실패: {str(e)}")
	finally:
		# 리소스 정리
		try:
			final_clip.close()
		except:
			pass
		for clip in video_clips:
			try:
				clip.close()
			except:
				pass
	
	return {
		"output_path": output_path,
		"clip_paths": clip_paths,
		"audio_paths": generated_audio_paths,
		"total_duration": total_duration
	}
