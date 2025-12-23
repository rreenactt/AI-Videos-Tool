from typing import List, Optional
import os
import subprocess


def compose_video(image_paths: List[str], *, fps: int = 24, audio_path: Optional[str] = None, output_path: str = "../data/outputs/final.mp4") -> str:
	"""FFmpeg으로 이미지들을 영상으로 합치는 간단한 예시.
	- 실제로는 리스트파일 작성 후 -r/-i 파턴 등을 사용 권장.
	- 여기선 placeholder로 파일 존재만 확인하여 출력 경로 문자열 반환.
	"""
	os.makedirs(os.path.dirname(output_path), exist_ok=True)
	# TODO: 실제 ffmpeg 명령 구성 (예: 이미지 시퀀스 사용)
	# 여기서는 연동 전 단계이므로 파일 경로만 반환
	return output_path
