"""
Gemini 2.5 Flash TTS 기반 음성 생성기
- 지시어로 연기력/감정 표현 가능
- 감정 태그 지원: [whisper], [excited], [laughing], [thinking] 등
- Kore 한국어 음성 지원
"""
from typing import Optional, List, Tuple, Dict, Any
import os
import wave
import struct
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# OpenAI 클라이언트 (대사 스타일링용 GPT)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai_client = None
if OPENAI_API_KEY:
	openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Gemini API 설정
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
_gemini_client = None


def _get_gemini_client():
	"""Gemini 클라이언트 싱글톤"""
	global _gemini_client
	if _gemini_client is None:
		print("\n🔧 Gemini TTS 클라이언트 초기화 중...")
		
		api_key = os.getenv("GEMINI_API_KEY")
		if not api_key:
			raise ValueError("GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")
		
		try:
			from google import genai
			_gemini_client = genai.Client(api_key=api_key)
			print("  ✓ Gemini 클라이언트 생성 완료\n")
		except Exception as e:
			print(f"  ✗ 클라이언트 생성 실패: {e}\n")
			raise
	return _gemini_client


# Gemini TTS 음성 목록 (한국어 지원)
GEMINI_VOICES = {
	"default": "Kore",      # 한국어 기본
	"kore": "Kore",         # 한국어
	"puck": "Puck",         # 영어 (활기찬)
	"charon": "Charon",     # 영어 (차분한)
	"kore_excited": "Kore", # 한국어 (신나는 스타일)
	"kore_calm": "Kore",    # 한국어 (차분한 스타일)
}

# 감정/스타일 태그 매핑
EMOTION_TAGS = {
	"neutral": "",
	"excited": "[excited]",
	"whisper": "[whisper]",
	"laughing": "[laughing]",
	"thinking": "[thinking]",
	"sad": "[sad]",
	"angry": "[angry]",
	"happy": "[happy]",
	"narrator": "",  # 나레이션은 차분하게
}


def enhance_dialogue_with_gpt(
	text: str,
	speaker: str = "",
	emotion: str = "neutral",
	style: str = "유튜버"
) -> str:
	"""GPT를 사용하여 대사에 감정/지시어를 추가
	
	Args:
		text: 원본 대사
		speaker: 화자 이름
		emotion: 감정 (neutral, excited, whisper, laughing, thinking, sad, angry, happy)
		style: 스타일 (유튜버, 나레이션, 캐릭터, 다큐멘터리 등)
		
	Returns:
		감정/지시어가 추가된 대사
	"""
	if not openai_client:
		# OpenAI 클라이언트가 없으면 기본 태그만 추가
		emotion_tag = EMOTION_TAGS.get(emotion, "")
		if emotion_tag:
			return f"{emotion_tag} {text}"
		return text
	
	if not text or len(text.strip()) < 2:
		return text
	
	prompt = f"""다음 대사를 Gemini TTS가 더 자연스럽고 감정이 담기게 읽을 수 있도록 수정해주세요.

원본 대사: "{text}"
화자: {speaker or "나레이터"}
원하는 감정: {emotion}
원하는 스타일: {style}

규칙:
1. 원본 대사의 의미는 절대 바꾸지 마세요
2. 다음 감정 태그를 적절한 위치에 삽입할 수 있습니다:
   - [whisper]: 속삭이듯
   - [excited]: 흥분/신남
   - [laughing]: 웃으면서
   - [thinking]: 고민하듯
3. 괄호 안에 읽는 방식 지시를 추가할 수 있습니다: (신나게), (천천히), (강조하며) 등
4. 문장 끝에 '~', '!', '?'를 적절히 사용하여 톤을 조절하세요
5. 스타일이 '유튜버'면 하이텐션으로, '나레이션'이면 차분하게, '캐릭터'면 개성있게 수정

예시:
- 입력: "오늘 소개할 기능은 정말 대단합니다"
- 출력 (유튜버): "와~ 여러분! (하이텐션으로) 오늘 소개할 기능은 [excited] 정말 대단해요!"
- 출력 (나레이션): "오늘 소개할 기능은, (차분하게) 정말 대단합니다."

수정된 대사만 출력하세요 (다른 설명 없이):"""

	try:
		response = openai_client.chat.completions.create(
			model="gpt-4o-mini",
			messages=[
				{"role": "system", "content": "You are a dialogue director. Output only the modified dialogue, nothing else."},
				{"role": "user", "content": prompt}
			],
			temperature=0.7,
			max_tokens=300
		)
		
		enhanced = response.choices[0].message.content.strip()
		
		# 결과가 너무 길거나 이상하면 원본 반환
		if len(enhanced) > len(text) * 3 or len(enhanced) < 2:
			print(f"  ⚠ GPT 결과 이상, 원본 사용")
			return text
		
		return enhanced
		
	except Exception as e:
		print(f"  ⚠ GPT 대사 강화 실패: {e}, 원본 사용")
		return text


def generate_gemini_tts(
	text: str,
	output_path: str,
	voice: str = "default",
	emotion: str = "neutral",
	style: str = "유튜버",
	enhance_with_gpt: bool = True,
	max_retries: int = 2
) -> str:
	"""Gemini 2.5 Flash TTS를 사용하여 텍스트를 음성으로 변환
	
	Args:
		text: 변환할 텍스트
		output_path: 출력 오디오 파일 경로 (.wav)
		voice: 음성 종류 (GEMINI_VOICES 키)
		emotion: 감정 (neutral, excited, whisper, laughing, thinking)
		style: 스타일 (유튜버, 나레이션, 캐릭터, 다큐멘터리)
		enhance_with_gpt: GPT로 대사 강화 여부
		max_retries: 최대 재시도 횟수
		
	Returns:
		생성된 오디오 파일 경로
	"""
	from google import genai
	from google.genai import types
	
	os.makedirs(os.path.dirname(output_path), exist_ok=True)
	
	if not text or len(text.strip()) < 2:
		raise Exception("텍스트가 너무 짧습니다")
	
	# 음성 선택
	voice_name = GEMINI_VOICES.get(voice, GEMINI_VOICES["default"])
	
	# GPT로 대사 강화 (옵션)
	if enhance_with_gpt:
		enhanced_text = enhance_dialogue_with_gpt(text, emotion=emotion, style=style)
		print(f"  📝 원본: {text[:50]}...")
		print(f"  ✨ 강화: {enhanced_text[:50]}...")
	else:
		enhanced_text = text
		# 기본 감정 태그 추가
		emotion_tag = EMOTION_TAGS.get(emotion, "")
		if emotion_tag:
			enhanced_text = f"{emotion_tag} {text}"
	
	client = _get_gemini_client()
	last_error = None
	
	for attempt in range(max_retries):
		try:
			# Gemini TTS 요청
			response = client.models.generate_content(
				model="gemini-2.5-flash-preview-tts",
				contents=enhanced_text,
				config=types.GenerateContentConfig(
					response_modalities=["AUDIO"],
					speech_config=types.SpeechConfig(
						voice_config=types.VoiceConfig(
							prebuilt_voice_config=types.PrebuiltVoiceConfig(
								voice_name=voice_name,
							)
						)
					)
				)
			)
			
			# 응답에서 오디오 데이터 추출
			audio_data = response.candidates[0].content.parts[0].inline_data.data
			
			# WAV 파일로 저장
			# Gemini TTS는 기본적으로 24kHz, 16-bit PCM을 반환
			with wave.open(output_path, "wb") as wf:
				wf.setnchannels(1)  # 모노
				wf.setsampwidth(2)  # 16-bit
				wf.setframerate(24000)  # 24kHz
				wf.writeframes(audio_data)
			
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
			
			print(f"\n{'='*60}")
			print(f"❌ Gemini TTS 에러 (시도 {attempt+1}/{max_retries})")
			print(f"{'='*60}")
			print(f"에러 타입: {type(e).__name__}")
			print(f"에러 메시지: {error_str}")
			
			if "API_KEY" in error_str or "authentication" in error_str.lower():
				print("\n⚠️  API 키 에러:")
				print("  - GEMINI_API_KEY 환경변수 확인 필요")
				print("  - Google AI Studio에서 API 키 발급: https://aistudio.google.com/")
			
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
	
	raise Exception(f"Gemini TTS 생성 실패 ({max_retries}회 시도): {str(last_error)[:200]}")


def convert_wav_to_mp3(wav_path: str, mp3_path: str) -> str:
	"""WAV 파일을 MP3로 변환 (ffmpeg 사용)
	
	Args:
		wav_path: 입력 WAV 파일 경로
		mp3_path: 출력 MP3 파일 경로
		
	Returns:
		생성된 MP3 파일 경로
	"""
	import subprocess
	
	try:
		# ffmpeg로 변환
		cmd = [
			"ffmpeg", "-y",  # 덮어쓰기
			"-i", wav_path,
			"-codec:a", "libmp3lame",
			"-qscale:a", "2",  # 높은 품질
			mp3_path
		]
		
		result = subprocess.run(
			cmd,
			capture_output=True,
			text=True,
			timeout=30
		)
		
		if result.returncode != 0:
			raise Exception(f"ffmpeg 에러: {result.stderr[:100]}")
		
		if not os.path.exists(mp3_path):
			raise Exception("MP3 파일이 생성되지 않았습니다")
		
		return mp3_path
		
	except FileNotFoundError:
		# ffmpeg가 없으면 WAV 그대로 사용
		print("  ⚠ ffmpeg 없음, WAV 파일 사용")
		return wav_path
	except Exception as e:
		print(f"  ⚠ MP3 변환 실패: {e}, WAV 파일 사용")
		return wav_path


def generate_gemini_tts_with_mp3(
	text: str,
	output_path: str,
	voice: str = "default",
	emotion: str = "neutral",
	style: str = "유튜버",
	enhance_with_gpt: bool = True,
	max_retries: int = 2
) -> str:
	"""Gemini TTS로 음성 생성 후 MP3로 변환
	
	Args:
		text: 변환할 텍스트
		output_path: 출력 오디오 파일 경로 (.mp3)
		voice: 음성 종류
		emotion: 감정
		style: 스타일
		enhance_with_gpt: GPT로 대사 강화 여부
		max_retries: 최대 재시도 횟수
		
	Returns:
		생성된 오디오 파일 경로 (MP3 또는 WAV)
	"""
	# 먼저 WAV로 생성
	wav_path = output_path.rsplit('.', 1)[0] + ".wav"
	
	generate_gemini_tts(
		text=text,
		output_path=wav_path,
		voice=voice,
		emotion=emotion,
		style=style,
		enhance_with_gpt=enhance_with_gpt,
		max_retries=max_retries
	)
	
	# MP3로 변환
	if output_path.endswith('.mp3'):
		result_path = convert_wav_to_mp3(wav_path, output_path)
		
		# WAV 파일 삭제 (MP3 변환 성공 시)
		if result_path == output_path and os.path.exists(wav_path):
			try:
				os.remove(wav_path)
			except:
				pass
		
		return result_path
	else:
		return wav_path


def get_emotion_from_speaker(speaker: str) -> str:
	"""화자 이름에서 감정 추론
	
	Args:
		speaker: 화자 이름
		
	Returns:
		추론된 감정
	"""
	if not speaker:
		return "neutral"
	
	speaker_lower = speaker.lower()
	
	# 나레이션은 차분하게
	if "나레이션" in speaker_lower or "narration" in speaker_lower or "narrator" in speaker_lower:
		return "narrator"
	
	# 특정 감정 키워드 체크
	if "신나" in speaker_lower or "excited" in speaker_lower:
		return "excited"
	if "속삭" in speaker_lower or "whisper" in speaker_lower:
		return "whisper"
	if "웃" in speaker_lower or "laugh" in speaker_lower:
		return "laughing"
	if "슬프" in speaker_lower or "sad" in speaker_lower:
		return "sad"
	if "화난" in speaker_lower or "angry" in speaker_lower:
		return "angry"
	
	return "neutral"


def get_style_from_context(cuts: List[Dict[str, Any]] = None) -> str:
	"""컷 정보에서 스타일 추론
	
	Args:
		cuts: 컷 정보 리스트
		
	Returns:
		추론된 스타일
	"""
	if not cuts:
		return "유튜버"
	
	# 나레이션이 많으면 다큐멘터리/나레이션 스타일
	narration_count = sum(
		1 for cut in cuts 
		for d in cut.get("dialogues", [])
		if "나레이션" in d.get("speaker", "").lower()
	)
	
	total_dialogues = sum(len(cut.get("dialogues", [])) for cut in cuts)
	
	if total_dialogues > 0 and narration_count / total_dialogues > 0.7:
		return "나레이션"
	
	return "유튜버"
