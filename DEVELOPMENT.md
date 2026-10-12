# 일조해 개발 및 Git 관리

로컬 프로젝트: `/Users/erickang/Documents/ChatGPT/smsg-aws`
운영 서버: AWS Lightsail `Ubuntu-1`, `/opt/smsg`
서비스: `smsg.service`
접속 주소: https://example.invalid

현재 운영은 Python 가상환경 + systemd + Nginx HTTPS 방식입니다. 기존 README의 Docker 배포 절차는 대안이며 현재 운영 구성과 다릅니다.

## 현재 기능
멤버, 경기, 식대정산 메뉴. 경기별 참가자 및 결과 입력, 전체 평균 핸디 계산, 참석 이력, 자동 조편성 및 수동 수정, 조편성 팝업과 경기 비고를 지원합니다.

## 자주 사용하는 Git 명령
```sh
git status
git diff
git add app.py static/app.js static/style.css
git commit -m "변경 내용 설명"
git log --oneline -10
```

비밀번호, 운영 DB, 백업, Python 가상환경은 Git에 포함하지 않습니다. 운영 회원·경기 데이터는 AWS의 `/opt/smsg/data/smsg.sqlite3`에 있으며 별도로 백업해야 합니다. Git 커밋은 운영 서버에 자동 배포되지 않습니다.

## 검증
```sh
python3 -m unittest discover -p 'test_*.py'
node --check static/app.js
```

현재는 로컬 저장소이며 원격 GitHub 저장소는 연결하지 않았습니다.
