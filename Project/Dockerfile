FROM node:20-slim AS frontend-build

WORKDIR /frontend
COPY frontend/package*.json ./
ENV NODE_ENV=development
RUN npm ci --include=dev
COPY frontend ./
RUN npm run build

FROM python:3.12-slim

# 1. 시스템 라이브러리 및 빌드 도구 설치 (컴파일러 포함)
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    libgl1 \
    libglib2.0-0 \
    libsndfile1 \
    libsndfile1-dev \
    ffmpeg \
    imagemagick \
    && rm -rf /var/lib/apt/lists/*

# 2. ImageMagick 보안 정책 수정
RUN sed -i 's/rights="none" pattern="@\*"/rights="read|write" pattern="@*"/g' /etc/ImageMagick-*/policy.xml

WORKDIR /app

# 3. 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

    
# 4. 소스 코드 복사
COPY . .
COPY --from=frontend-build /frontend/dist ./frontend/dist

# 5. 실행 설정
EXPOSE 8000
CMD ["python", "-m", "backend.main"]