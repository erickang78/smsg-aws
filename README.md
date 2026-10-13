# 일조해(SMSG) — AWS 배포용 모바일 앱

메뉴: 멤버 / 핸디 / 금주 조편성 / 식대정산.

## 구현된 기능
- 멤버 이름·핸디·메모·활동 여부 등록 및 수정. 실제 멤버 명단은 미입력.
- 직접 등록한 핸디 순서 조회 및 수정.
- 날짜·참가자·조당 최대 인원(2~4명)을 선택해 인원과 핸디 합계를 고려한 조편성, 날짜별 저장. 같은 날짜 저장 시 교체 확인. 전역 최적화나 공식 골프 핸디 계산은 아님.
- 사진의 43건 식대 내역 초기 등록. 수입 16,902,000원, 캐시백/이자 35,426원, 지출 16,255,550원, 이월 132,843원, 최종 814,719원. 공란 금액은 0원. 일부 장소명은 사진 판독값이므로 수정 가능.
- 식대 입력 중 정산 계산; 저장·수정·삭제 후 전체 잔액 재계산. CSV 내보내기.
- SQLite 서버 저장. 브라우저를 바꿔도 같은 서버 장부 사용. 기존 ChatGPT Site의 이후 수정 사항과 자동 동기화되지 않음.
- 모임 공유 비밀번호 로그인. 로그인한 사람 모두 조회·수정 가능. 개별 계정/관리자 권한 구분은 포함되지 않음.

## 배포 상태
AWS에 배포되지 않았습니다. 현재 작성 세션에 AWS 인증 및 Cloud 실행 기능이 없어 서버 상태·도메인·Nginx 설정은 확인하지 못했습니다. 기존 운영 서비스를 건드리지 않은 독립 앱입니다. 실제 AWS URL은 아직 없습니다.

## AWS Ubuntu 배포 절차
운영 서버에 Docker Compose와 HTTPS Nginx가 설치되어 있다는 전제입니다. 기존 설정을 먼저 읽고, 사용 가능한 서브도메인과 포트를 확인하세요. 자동매매 프로세스/DB/서비스를 수정하거나 재시작하지 마세요.

1. 이 폴더를 `/opt/smsg` 등 별도 경로로 복사합니다.
2. 그 폴더에서 `python3 make_password.py`로 비밀번호를 설정합니다. 인증 값은 로그·채팅·Git에 넣지 않습니다.
3. `docker compose up -d --build`로 앱을 시작합니다. 앱은 호스트의 `127.0.0.1:8091`에만 열립니다.
4. 별도 HTTPS 도메인의 Nginx server 설정에서 아래 location을 사용합니다. 실제 도메인과 인증서는 운영 설정에 맞춰 준비합니다.

```nginx
location / {
    proxy_pass http://127.0.0.1:8091;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Real-IP $remote_addr;
}
```

독립 서브도메인 사용을 전제로 루트(`/`) 경로를 사용합니다. 기존 서비스에 `/smsg` 경로로 붙이려면 경로 접두사 지원을 추가해야 합니다. Nginx 설정을 검증(`nginx -t`)한 뒤 reload하고 HTTPS에서 로그인·저장·재접속을 확인합니다. 공유 비밀번호가 설정되지 않으면 로그인은 차단됩니다. 실제 TLS 종단은 Nginx입니다. 공개 8091/8000 포트를 열지 마세요.

## 보관 및 백업
데이터는 Docker volume `smsg-data`에 보관됩니다. 컨테이너 교체 시 보존되지만 `docker compose down -v`는 데이터를 삭제하므로 사용하지 마세요. 데이터베이스는 실행 중 원본 파일만 복사하지 말고 SQLite backup API로 일관된 백업을 만드세요.

```sh
docker compose exec smsg python -c 'import sqlite3; s=sqlite3.connect("/data/smsg.sqlite3"); d=sqlite3.connect("/data/smsg-backup.sqlite3"); s.backup(d); d.close(); s.close()'
```

백업 파일은 볼륨 밖의 별도 보관소에 복사해야 서버 손실에도 복구할 수 있습니다.

운영 서버는 매일 한국 시간 새벽 1시 30분에 골프존 공개 코스 목록을 다시 받아 `golfzon-courses.json`을 원자적으로 갱신합니다. 갱신 전 파일은 `/opt/smsg/backups/course-catalog/`에 30일간 보관하며, 실패 시 기존 목록을 유지합니다. 스케줄 파일은 `ops/systemd/smsg-course-catalog-refresh.{service,timer}`입니다.

## 로컬 검증
`python3 test_app.py` 및 `node --check static/app.js`. 로컬 UI는 `python3 app.py`로 127.0.0.1:8091에서 시작합니다. `.env`를 자동 로드하지 않으므로 로컬 실행 시 `SMSG_PASSWORD_HASH` 환경변수를 설정해야 로그인할 수 있습니다. 이 패키지는 브라우저 시각 검증과 실제 AWS 배포 검증을 거치지 않았습니다.
