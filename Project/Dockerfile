# 1단계: 프론트엔드 빌드
FROM node:20 AS frontend-build

WORKDIR /frontend

# 1. 의존성 파일 먼저 복사 및 설치
COPY frontend/package*.json ./
RUN npm install

# 2. 전체 소스 복사
COPY frontend/ ./

# 3. 중요: 실행 권한 강제 부여 (권한 문제 해결)
RUN chmod -R +x node_modules/.bin

# 4. npx 대신 npm run build 사용 (package.json의 스크립트 실행)
RUN npm run build

# --- 이후 파이썬 설정은 기존과 동일 ---
FROM python:3.12-slim

# 1. 시스템 라이브러리 및 빌드 도구 설치 (컴파일러 포함)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    libgl1 \
    libglib2.0-0 \
    libsndfile1 \
    libsndfile1-dev \
    ffmpeg \
    imagemagick \
    fonts-noto-cjk \
    fontconfig \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -fv

# 2. ImageMagick 보안 정책 수정
RUN sed -i 's/rights="none" pattern="@\*"/rights="read|write" pattern="@*"/g' /etc/ImageMagick-*/policy.xml

WORKDIR /app

# 3. 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

    
# 4. 소스 코드 복사
COPY . .
COPY --from=frontend-build /frontend/dist ./frontend/dist

# 5. 실행 설정
EXPOSE 8000
CMD ["python", "-m", "backend.main"]