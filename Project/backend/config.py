"""
백엔드 설정 파일
"""
import os
import platform

# ImageMagick 설정
IMAGEMAGICK_BINARY = None

if platform.system() == "Windows":
	# Windows: ImageMagick 경로 (설치 위치에 맞게 수정)
	IMAGEMAGICK_BINARY = r"C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe"
elif platform.system() == "Darwin":  # macOS
	# macOS: Homebrew로 설치한 경우
	IMAGEMAGICK_BINARY = "/opt/homebrew/bin/magick"
	if not os.path.exists(IMAGEMAGICK_BINARY):
		IMAGEMAGICK_BINARY = "/usr/local/bin/magick"
else:  # Linux
	# Linux: 보통 /usr/bin/convert
	IMAGEMAGICK_BINARY = "/usr/bin/convert"

# 경로 존재 여부 확인
if IMAGEMAGICK_BINARY and not os.path.exists(IMAGEMAGICK_BINARY):
	print(f"⚠ ImageMagick을 찾을 수 없습니다: {IMAGEMAGICK_BINARY}")
	print(f"   자막 생성이 비활성화됩니다. (오디오는 정상 작동)")
	IMAGEMAGICK_BINARY = None
