FROM python:3.12-slim

# 1. 시스템 라이브러리 설치 (OpenCV 및 ImageMagick 필수)
RUN apt-get update && apt-get install -y \
    libgl1 libglib2.0-0 imagemagick && \
    rm -rf /var/lib/apt/lists/*

# 2. ImageMagick 보안 정책 수정 (와일드카드(*)를 사용하여 경로 문제를 해결)
RUN sed -i 's/rights="none" pattern="@\*"/rights="read|write" pattern="@*"/g' /etc/*/policy.xml

# 3. 작업 디렉토리 설정 및 라이브러리 설치
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. 소스 코드 복사
COPY . .

# 5. 실행 설정
EXPOSE 8000
CMD ["python", "-m", "backend.main"]