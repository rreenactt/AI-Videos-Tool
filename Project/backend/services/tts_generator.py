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
	model: str = "tts-1",
	max_retries: int = 2
) -> str:
	"""OpenAI TTS를 사용하여 텍스트를 음성으로 변환
	
	Args:
		text: 변환할 텍스트
		output_path: 출력 오디오 파일 경로 (.mp3)
		voice: 음성 종류 ("alloy", "echo", "fable", "onyx", "nova", "shimmer")
		model: TTS 모델 ("tts-1" 또는 "tts-1-hd")
		max_retries: 최대 재시도 횟수
		
	Returns:
		생성된 오디오 파일 경로
	"""
	os.makedirs(os.path.dirname(output_path), exist_ok=True)
	
	# 텍스트가 너무 짧으면 실패할 수 있음
	if not text or len(text.strip()) < 2:
		raise Exception("텍스트가 너무 짧습니다")
	
	# 텍스트가 너무 길면 잘라냄 (4096자 제한)
	if len(text) > 4096:
		text = text[:4096]
	
	last_error = None
	
	for attempt in range(max_retries):
		try:
			response = openai_client.audio.speech.create(
				model=model,
				voice=voice,
				input=text.strip()
			)
			
			# 오디오 파일 저장
			response.stream_to_file(output_path)
			
			# 짧은 대기 (파일 시스템 동기화)
			import time
			time.sleep(0.1)
			
			# 파일이 제대로 생성되었는지 확인
			if not os.path.exists(output_path):
				raise Exception("오디오 파일이 생성되지 않았습니다")
			
			# 파일 크기 확인 (최소 100 바이트)
			file_size = os.path.getsize(output_path)
			if file_size < 100:
				raise Exception(f"오디오 파일이 너무 작습니다 ({file_size} bytes)")
			
			return output_path
			
		except Exception as e:
			last_error = e
			# 실패 시 파일 삭제
			if os.path.exists(output_path):
				try:
					os.remove(output_path)
				except:
					pass
			
			if attempt < max_retries - 1:
				# 재시도 전 짧은 대기
				import time
				time.sleep(0.5)
				continue
	
	# 모든 재시도 실패
	raise Exception(f"TTS 생성 실패 ({max_retries}회 시도): {str(last_error)}")

