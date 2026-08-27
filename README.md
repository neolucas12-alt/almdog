# 알림dog — KSIA 반도체 교육과정 알림

한국반도체산업협회 인력양성 사이트의 교육과정을 30분마다 확인해서
새 과정이 올라오거나 모집이 시작되면 Telegram으로 알려줍니다.
서버 없이 GitHub Actions로 24시간 동작합니다.

## 설치 (약 20분)

### 1. Telegram 봇 만들기
1. Telegram에서 `@BotFather` 검색 → `/newbot`
2. 봇 이름과 아이디를 정하면 **토큰**을 줍니다. (`1234567890:AAxx...` 형태)
3. 만들어진 봇을 검색해서 대화창을 열고 아무 메시지나 하나 보냅니다. (이걸 안 하면 봇이 나에게 말을 걸 수 없습니다)

### 2. 내 chat_id 확인
브라우저에서 아래 주소를 엽니다. `<토큰>` 자리에 1번에서 받은 토큰을 넣으세요.
```
https://api.telegram.org/bot<토큰>/getUpdates
```
`"chat":{"id":123456789` 부분의 숫자가 chat_id입니다.

### 3. GitHub 저장소에 올리기
이 폴더를 새 저장소로 push 합니다.

### 4. Secrets 등록
저장소 → Settings → Secrets and variables → Actions → **Secrets** 탭
- `TELEGRAM_BOT_TOKEN` : 봇 토큰
- `TELEGRAM_CHAT_ID` : chat_id

키워드 필터를 쓰려면 같은 화면 **Variables** 탭에
- `KEYWORDS` : 예) `패키징,소자,공정` (비워두면 전체 알림)

### 5. 첫 실행
Actions 탭 → "알림dog 공지 확인" → Run workflow

**첫 실행은 알림을 보내지 않습니다.** 현재 목록을 기준선으로 저장만 합니다.
그 다음 실행부터 변경분만 알려줍니다.

## 로컬 테스트
```bash
pip install -r requirements.txt
python notify.py          # 토큰 없으면 콘솔에만 출력 (DRY RUN)
```

## 알림 조건
| 상황 | 알림 |
|---|---|
| 새 과정 등록 | 보냄 |
| 모집전 → 모집중 | 보냄 |
| 모집중 → 모집마감 | 안 보냄 |

## 감시 대상 늘리기
`notify.py`의 `TARGETS`에서 재직자 교육 항목 주석을 해제하세요.

## 주의
- 사이트 robots.txt는 자동 접근을 제한합니다. 개인용 30분 간격 이상을 유지하세요.
- 사이트 HTML 구조가 바뀌면 파싱이 0건이 됩니다. 이때는 상태를 덮어쓰지 않고 건너뜁니다.
