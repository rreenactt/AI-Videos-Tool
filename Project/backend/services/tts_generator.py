"""
Google Cloud TTS + GPT SSML 변환 기반 음성 생성기
"""
from typing import Optional, List, Tuple
import os
import json
import re
from openai import OpenAI
from google.cloud import texttospeech
from dotenv import load_dotenv

load_dotenv()

# OpenAI 클라이언트 초기화 (SSML 변환용)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
	raise ValueError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")

openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Google Cloud TTS 클라이언트 초기화
# GOOGLE_APPLICATION_CREDENTIALS 환경변수 또는 직접 JSON 키 사용
_tts_client = None


def _get_tts_client():
	"""Google Cloud TTS 클라이언트 싱글톤"""
	global _tts_client
	if _tts_client is None:
		print("\n🔧 Google Cloud TTS 클라이언트 초기화 중...")
		
		# GOOGLE_APPLICATION_CREDENTIALS 환경변수 확인
		creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
		google_creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
		
		if creds_path:
			print(f"  📁 GOOGLE_APPLICATION_CREDENTIALS: {creds_path}")
			if os.path.exists(creds_path):
				print(f"  ✓ 파일 존재함 ({os.path.getsize(creds_path)} bytes)")
			else:
				print(f"  ✗ 파일 없음!")
		elif google_creds_json:
			print(f"  📄 GOOGLE_CREDENTIALS_JSON 환경변수 사용 ({len(google_creds_json)} chars)")
			import tempfile
			# 임시 파일에 credentials 저장
			creds_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
			creds_file.write(google_creds_json)
			creds_file.close()
			os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_file.name
			print(f"  📁 임시 파일 생성: {creds_file.name}")
		else:
			print("  ⚠️  Google 인증 정보 없음!")
			print("  GOOGLE_APPLICATION_CREDENTIALS 또는 GOOGLE_CREDENTIALS_JSON 필요")
		
		try:
			_tts_client = texttospeech.TextToSpeechClient()
			print("  ✓ TTS 클라이언트 생성 완료\n")
		except Exception as e:
			print(f"  ✗ 클라이언트 생성 실패: {e}\n")
			raise
	return _tts_client


# 한국어 음성 목록 (Google Cloud TTS)
KOREAN_VOICES = {
	"default": "ko-KR-Neural2-C",  # 남성 (기본)
	"female_a": "ko-KR-Neural2-A",  # 여성
	"female_b": "ko-KR-Neural2-B",  # 여성
	"male_a": "ko-KR-Neural2-C",    # 남성
	"male_b": "ko-KR-Standard-A",   # 남성 (스탠다드)
	"narrator": "ko-KR-Neural2-C",  # 나레이션용 (남성)
}


def split_text_for_subtitle(text: str, max_length: int = 12) -> List[str]:
	"""텍스트를 12글자 이내로 분할
	
	Args:
		text: 분할할 텍스트
		max_length: 최대 글자 수 (기본 12)
		
	Returns:
		분할된 텍스트 리스트
	"""
	if not text or len(text) <= max_length:
		return [text] if text else []
	
	# 공백, 구두점을 기준으로 분할
	parts = re.split(r'([\s,\.!?;:~])', text)
	
	# 단어와 구분자를 묶어서 처리 (공백/구두점은 앞 단어에 포함)
	cleaned_parts = []
	for part in parts:
		if not part:  # 빈 문자열만 스킵
			continue
		# 공백인 경우 앞 단어에 붙임
		if part == ' ':
			if cleaned_parts:
				cleaned_parts[-1] += part
		# 구두점인 경우 앞 단어에 붙임
		elif part in [',', '.', '!', '?', ';', ':', '~']:
			if cleaned_parts:
				cleaned_parts[-1] += part
		else:
			cleaned_parts.append(part)
	
	if not cleaned_parts:
		return [text] if text else []
	
	result = []
	current = ""
	
	for part in cleaned_parts:
		test = current + part if current else part
		if len(test) <= max_length:
			current = test
		else:
			if current.strip():
				result.append(current.strip())
			# 단일 파트가 max_length 초과 시 강제 분할
			if len(part) > max_length:
				while len(part) > max_length:
					result.append(part[:max_length])
					part = part[max_length:]
				current = part
			else:
				current = part
	
	if current.strip():
		result.append(current.strip())
	
	return result if result else [text]


def convert_text_to_ssml_with_gpt(text: str, emotion: str = "neutral") -> str:
	"""GPT를 사용하여 텍스트를 SSML로 변환
	
	Args:
		text: 변환할 텍스트
		emotion: 감정 힌트 (neutral, excited, sad, angry, whisper 등)
		
	Returns:
		SSML 형식 텍스트
	"""
	if not text or len(text.strip()) < 2:
		return f"<speak>{text}</speak>"
	
	prompt = f"""다음 텍스트를 Google Cloud TTS용 SSML로 변환해주세요.
자연스럽고 감정이 담긴 음성이 되도록 SSML 태그를 적절히 사용하세요.

사용 가능한 SSML 태그:
- <break time="Xms"/> : 휴식 (예: 500ms)
- <emphasis level="strong/moderate/reduced"> : 강조
- <prosody pitch="+/-Xst" rate="slow/medium/fast" volume="soft/medium/loud"> : 음높이/속도/볼륨
- <say-as interpret-as="cardinal/ordinal/date"> : 숫자/날짜 읽기

규칙:
1. 반드시 <speak>로 시작하고 </speak>로 끝나야 합니다
2. 문장 사이에 적절한 휴식(<break>)을 넣으세요
3. 강조할 부분은 <emphasis>로 감싸세요
4. 감정: {emotion}
5. 원문 텍스트는 절대 변경하지 마세요 (SSML 태그만 추가)

텍스트: {text}

SSML만 출력하세요 (다른 설명 없이):"""

	try:
		response = openai_client.chat.completions.create(
			model="gpt-4o-mini",
			messages=[
				{"role": "system", "content": "You are an SSML expert. Output only valid SSML, nothing else. Never duplicate the original text."},
				{"role": "user", "content": prompt}
			],
			temperature=0.3,
			max_tokens=500
		)
		
		ssml = response.choices[0].message.content.strip()
		
		# SSML 유효성 검사
		if not ssml.startswith("<speak>"):
			ssml = f"<speak>{ssml}"
		if not ssml.endswith("</speak>"):
			ssml = f"{ssml}</speak>"
		
		# 텍스트 중복 체크 - 원본 텍스트가 2번 이상 포함되면 간단한 SSML 사용
		clean_text = text.strip()
		if ssml.count(clean_text) > 1:
			print(f"  ⚠ SSML에 텍스트 중복 감지, 기본 SSML 사용")
			return f"<speak>{clean_text}</speak>"
		
		return ssml
		
	except Exception as e:
		print(f"  ⚠ GPT SSML 변환 실패: {e}, 기본 SSML 사용")
		return f"<speak>{text}</speak>"


def process_text_for_tts(text: str, emotion: str = "neutral") -> List[Tuple[str, str]]:
	"""텍스트를 12글자 단위로 분할하고 각각 SSML로 변환
	
	Args:
		text: 원본 텍스트
		emotion: 감정 힌트
		
	Returns:
		[(자막텍스트, SSML), ...] 리스트
	"""
	# 12글자 단위로 분할
	segments = split_text_for_subtitle(text, max_length=12)
	
	result = []
	for segment in segments:
		ssml = convert_text_to_ssml_with_gpt(segment, emotion)
		result.append((segment, ssml))
	
	return result


def generate_tts(
	text: str,
	output_path: str,
	voice: str = "default",
	use_ssml: bool = True,
	emotion: str = "neutral",
	speaking_rate: float = 1.0,
	max_retries: int = 2
) -> str:
	"""Google Cloud TTS를 사용하여 텍스트를 음성으로 변환
	
	Args:
		text: 변환할 텍스트 (또는 SSML)
		output_path: 출력 오디오 파일 경로 (.mp3)
		voice: 음성 종류 (KOREAN_VOICES 키 또는 직접 음성 ID)
		use_ssml: SSML 사용 여부 (True면 GPT로 SSML 변환)
		emotion: 감정 힌트 (use_ssml=True일 때 사용)
		speaking_rate: 말 속도 (0.5~2.0, 기본 1.0)
		max_retries: 최대 재시도 횟수
		
	Returns:
		생성된 오디오 파일 경로
	"""
	os.makedirs(os.path.dirname(output_path), exist_ok=True)
	
	if not text or len(text.strip()) < 2:
		raise Exception("텍스트가 너무 짧습니다")
	
	# 음성 선택
	voice_name = KOREAN_VOICES.get(voice, voice)
	if not voice_name.startswith("ko-KR"):
		voice_name = KOREAN_VOICES["default"]
	
	# SSML 변환 (옵션)
	if use_ssml and not text.strip().startswith("<speak>"):
		synthesis_input = texttospeech.SynthesisInput(
			ssml=convert_text_to_ssml_with_gpt(text, emotion)
		)
	elif text.strip().startswith("<speak>"):
		synthesis_input = texttospeech.SynthesisInput(ssml=text)
	else:
		synthesis_input = texttospeech.SynthesisInput(text=text)
	
	# 음성 설정
	voice_params = texttospeech.VoiceSelectionParams(
		language_code="ko-KR",
		name=voice_name
	)
	
	# 오디오 설정 (말 속도 0.5~2.0 범위로 제한)
	rate = max(0.5, min(2.0, speaking_rate))
	audio_config = texttospeech.AudioConfig(
		audio_encoding=texttospeech.AudioEncoding.MP3,
		speaking_rate=rate,
		pitch=0.0
	)
	
	client = _get_tts_client()
	last_error = None
	
	for attempt in range(max_retries):
		try:
			response = client.synthesize_speech(
				input=synthesis_input,
				voice=voice_params,
				audio_config=audio_config
			)
			
			# 오디오 파일 저장
			with open(output_path, "wb") as f:
				f.write(response.audio_content)
			
			# 파일 확인
			import time
			time.sleep(0.1)
			
			if not os.path.exists(output_path):
				raise Exception("오디오 파일이 생성되지 않았습니다")
			
			file_size = os.path.getsize(output_path)
			if file_size < 100:
				raise Exception(f"오디오 파일이 너무 작습니다 ({file_size} bytes)")
			
			return output_path
			
		except Exception as e:
			last_error = e
			error_str = str(e)
			
			# 상세 에러 로그 출력
			print(f"\n{'='*60}")
			print(f"❌ Google TTS 에러 (시도 {attempt+1}/{max_retries})")
			print(f"{'='*60}")
			print(f"에러 타입: {type(e).__name__}")
			print(f"에러 메시지: {error_str}")
			
			# 403 에러 상세 안내
			if "403" in error_str:
				print("\n⚠️  403 에러 원인:")
				print("  1. Google Cloud Console에서 'Cloud Text-to-Speech API' 활성화 필요")
				print("  2. 서비스 계정에 'Cloud Text-to-Speech User' 역할 필요")
				print("  3. 프로젝트에 결제(Billing) 설정 필요")
				print("  4. GOOGLE_APPLICATION_CREDENTIALS 경로 확인 필요")
				creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "설정안됨")
				print(f"  현재 credentials 경로: {creds_path}")
				if creds_path != "설정안됨" and os.path.exists(creds_path):
					print(f"  ✓ 파일 존재함")
				else:
					print(f"  ✗ 파일 없음!")
			
			# 401 에러 상세 안내
			if "401" in error_str:
				print("\n⚠️  401 에러 원인:")
				print("  - 인증 정보가 유효하지 않음")
				print("  - 서비스 계정 키가 만료되었거나 잘못됨")
			
			print(f"{'='*60}\n")
			
			if os.path.exists(output_path):
				try:
					os.remove(output_path)
				except:
					pass
			
			if attempt < max_retries - 1:
				import time
				time.sleep(0.5)
				continue
	
	raise Exception(f"TTS 생성 실패 ({max_retries}회 시도): {str(last_error)[:200]}")


def generate_tts_segments(
	text: str,
	output_dir: str,
	base_filename: str = "segment",
	voice: str = "default",
	emotion: str = "neutral"
) -> List[Tuple[str, str, float]]:
	"""텍스트를 12글자 단위로 분할하여 각각 TTS 생성
	
	Args:
		text: 원본 텍스트
		output_dir: 출력 디렉토리
		base_filename: 기본 파일명
		voice: 음성 종류
		emotion: 감정 힌트
		
	Returns:
		[(자막텍스트, 오디오경로, 오디오길이), ...] 리스트
	"""
	from mutagen.mp3 import MP3
	
	os.makedirs(output_dir, exist_ok=True)
	
	# 텍스트 분할 및 SSML 변환
	segments = process_text_for_tts(text, emotion)
	
	results = []
	for i, (subtitle_text, ssml) in enumerate(segments):
		output_path = os.path.join(output_dir, f"{base_filename}_{i:03d}.mp3")
		
		try:
			# TTS 생성 (이미 SSML이므로 use_ssml=False)
			generate_tts(
				text=ssml,
				output_path=output_path,
				voice=voice,
				use_ssml=False  # 이미 SSML 형태
			)
			
			# 오디오 길이 계산
			try:
				audio = MP3(output_path)
				duration = audio.info.length
			except:
				duration = 2.0  # 기본값
			
			results.append((subtitle_text, output_path, duration))
			print(f"  ✅ 세그먼트 {i+1}: '{subtitle_text}' ({duration:.1f}초)")
			
		except Exception as e:
			print(f"  ⚠ 세그먼트 {i+1} 실패: {e}")
			continue
	
	return results


# ============================================================
# 통합 TTS 함수 (Google TTS / Gemini TTS 선택)
# ============================================================

def generate_tts_unified(
	text: str,
	output_path: str,
	tts_type: str = "google",
	voice: str = "default",
	emotion: str = "neutral",
	style: str = "유튜버",
	speaker: str = "",
	speaking_rate: float = 1.0,
	enhance_with_gpt: bool = True,
	max_retries: int = 2
) -> str:
	"""통합 TTS 함수 - Google TTS 또는 Gemini TTS 선택
	
	Args:
		text: 변환할 텍스트
		output_path: 출력 오디오 파일 경로 (.mp3)
		tts_type: TTS 타입 ("google" 또는 "gemini")
		voice: 음성 종류
		emotion: 감정 (Gemini TTS용)
		style: 스타일 (Gemini TTS용, 유튜버/나레이션/캐릭터)
		speaker: 화자 이름
		speaking_rate: 말 속도 (0.5~2.0, 기본 1.0)
		enhance_with_gpt: GPT로 대사 강화 여부 (Gemini TTS용)
		max_retries: 최대 재시도 횟수
		
	Returns:
		생성된 오디오 파일 경로
	"""
	if tts_type.lower() == "gemini":
		# Gemini TTS 사용
		try:
			from .gemini_tts_generator import (
				generate_gemini_tts_with_mp3,
				get_emotion_from_speaker,
				GEMINI_VOICES
			)
			
			# 화자에서 감정 추론
			if emotion == "neutral" and speaker:
				emotion = get_emotion_from_speaker(speaker)
			
			# 나레이션인 경우 스타일 조정
			if "나레이션" in speaker.lower() if speaker else False:
				style = "나레이션"
			
			# Gemini 음성 매핑
			gemini_voice = GEMINI_VOICES.get(voice, "Kore")
			
			return generate_gemini_tts_with_mp3(
				text=text,
				output_path=output_path,
				voice=gemini_voice,
				emotion=emotion,
				style=style,
				speaking_rate=speaking_rate,
				enhance_with_gpt=enhance_with_gpt,
				max_retries=max_retries
			)
			
		except ImportError as e:
			print(f"  ⚠ Gemini TTS 모듈 로드 실패: {e}")
			print(f"  → Google TTS로 폴백")
			tts_type = "google"
		except Exception as e:
			print(f"  ⚠ Gemini TTS 실패: {e}")
			print(f"  → Google TTS로 폴백")
			tts_type = "google"
	
	# Google TTS 사용 (기본)
	return generate_tts(
		text=text,
		output_path=output_path,
		voice=voice,
		use_ssml=True,
		emotion=emotion,
		speaking_rate=speaking_rate,
		max_retries=max_retries
	)


def get_available_tts_types() -> List[dict]:
	"""사용 가능한 TTS 타입 목록 반환"""
	types = [
		{
			"id": "google",
			"name": "Google Cloud TTS",
			"description": "안정적인 Google Neural2 음성",
			"voices": list(KOREAN_VOICES.keys()),
			"features": ["SSML 지원", "안정적", "다양한 음성"]
		}
	]
	
	# Gemini API 키가 있는지 확인
	if os.getenv("GEMINI_API_KEY"):
		types.append({
			"id": "gemini",
			"name": "Gemini 2.5 Flash TTS",
			"description": "AI 기반 감정 표현, 유튜버 스타일",
			"voices": ["Kore", "Puck", "Charon"],
			"features": ["감정 태그", "지시어 인식", "GPT 대사 강화", "유튜버 스타일"]
		})
	
	return types
