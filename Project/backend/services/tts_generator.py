from typing import Optional
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# OpenAI 클라이언트 초기화
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
	raise ValueError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")

openai_client = OpenAI(api_key=OPENAI_API_KEY)


def generate_tts(
	text: str,
	output_path: str,
	voice: str = "alloy",
	model: str = "tts-1"
) -> str:
	"""OpenAI TTS를 사용하여 텍스트를 음성으로 변환
	
	Args:
		text: 변환할 텍스트
		output_path: 출력 오디오 파일 경로 (.mp3)
		voice: 음성 종류 ("alloy", "echo", "fable", "onyx", "nova", "shimmer")
		model: TTS 모델 ("tts-1" 또는 "tts-1-hd")
		
	Returns:
		생성된 오디오 파일 경로
	"""
	os.makedirs(os.path.dirname(output_path), exist_ok=True)
	
	try:
		response = openai_client.audio.speech.create(
			model=model,
			voice=voice,
			input=text
		)
		
		# 오디오 파일 저장
		response.stream_to_file(output_path)
		
		return output_path
	except Exception as e:
		raise Exception(f"TTS 생성 실패: {str(e)}")

