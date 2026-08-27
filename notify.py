"""
알림dog - KSIA 반도체 교육과정 신규/모집오픈 알림
GitHub Actions에서 주기적으로 실행되며, 변경사항을 Telegram으로 전송한다.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = "https://infra.ksia.or.kr"
LIST_URL = BASE + "/user/Wo/WoUser0101.do"
VIEW_URL = BASE + "/user/Wo/WoUser0101V.do"

# 감시 대상. SCH_PRM_GB: 001=재직자, 002=예비취업자
TARGETS = [
    {
        "name": "예비취업자 교육",
        "params": {
            "SCH_PRM_GB": "002",
            "TAB_ID": "1",
            "CURRENT_MENU_CODE": "MENU0040",
            "TOP_MENU_CODE": "MENU0040",
        },
    },
    # 재직자 교육도 받고 싶으면 아래 주석을 해제하세요.
    # {
    #     "name": "재직자 교육",
    #     "params": {
    #         "SCH_PRM_GB": "001",
    #         "TAB_ID": "1",
    #         "CURRENT_MENU_CODE": "MENU0039",
    #         "TOP_MENU_CODE": "MENU0039",
    #     },
    # },
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

STATE_FILE = Path(__file__).parent / "seen.json"

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
# 쉼표로 구분된 관심 키워드. 비워두면 전체 알림.
KEYWORDS = [k.strip() for k in os.environ.get("KEYWORDS", "").split(",") if k.strip()]


def fetch(params, retries=3):
    """목록 페이지를 가져온다. 실패 시 지수 백오프로 재시도."""
    last_err = None
    for i in range(retries):
        try:
            r = requests.get(LIST_URL, params=params, headers=HEADERS, timeout=30)
            r.raise_for_status()
            r.encoding = r.apparent_encoding or "utf-8"
            return r.text
        except Exception as e:
            last_err = e
            if i < retries - 1:
                time.sleep(2 ** i * 3)
    raise RuntimeError(f"페이지 요청 실패: {last_err}")


def parse(html, target):
    """목록 HTML에서 과정 정보를 뽑아낸다."""
    soup = BeautifulSoup(html, "lxml")
    items = []
    for li in soup.select("ul.programList > li"):
        a = li.select_one(".title > a")
        if not a:
            continue
        m = re.search(r"fnMoveView\('(\d+)','(\d+)'\)", a.get("onclick") or "")
        if not m:
            continue
        seq = m.group(1)

        dates = [
            p.select_one("span").get_text(strip=True)
            for p in li.select(".date > p")
            if p.select_one("span")
        ]
        chips = [
            re.sub(r"\s+", " ", s.get_text(strip=True)) for s in li.select(".chips > span")
        ]
        org_el = li.select_one(".p_name")

        detail = f"{VIEW_URL}?" + "&".join(
            f"{k}={v}" for k, v in {**target["params"], "WO_SEQ": seq}.items()
        )

        items.append(
            {
                "seq": seq,
                "category": target["name"],
                "org": org_el.get_text(strip=True) if org_el else "",
                "title": " ".join(a.get_text(strip=True).split()),
                "apply_period": dates[0] if len(dates) > 0 else "",
                "edu_period": dates[1] if len(dates) > 1 else "",
                "capacity": chips[0] if len(chips) > 0 else "",
                "state": chips[1] if len(chips) > 1 else "",
                "url": detail,
            }
        )
    return items


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print("경고: seen.json이 손상되어 초기화합니다.", file=sys.stderr)
    return {}


def save_state(state):
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )


def matches_keyword(item):
    """키워드 미설정이면 전부 통과."""
    if not KEYWORDS:
        return True
    haystack = f"{item['title']} {item['org']}"
    return any(k in haystack for k in KEYWORDS)


def escape(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_message(item, kind):
    head = "🆕 새 교육과정" if kind == "new" else "🔔 모집 시작"
    lines = [
        f"<b>{head}</b>",
        "",
        f"<b>{escape(item['title'])}</b>",
        f"🏫 {escape(item['org'])} · {escape(item['category'])}",
        f"📅 모집 {escape(item['apply_period'])}",
        f"📚 교육 {escape(item['edu_period'])}",
        f"👥 {escape(item['capacity'])} · {escape(item['state'])}",
        "",
        f'<a href="{escape(item["url"])}">신청 페이지 열기</a>',
    ]
    return "\n".join(lines)


def send(text):
    if not BOT_TOKEN or not CHAT_ID:
        print("[DRY RUN] 토큰 미설정, 콘솔 출력만 합니다.\n" + text + "\n" + "-" * 40)
        return True
    r = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        },
        timeout=20,
    )
    if not r.ok:
        print(f"Telegram 전송 실패 {r.status_code}: {r.text}", file=sys.stderr)
        return False
    return True


def main():
    state = load_state()
    first_run = len(state) == 0
    current = {}
    notifications = []

    for target in TARGETS:
        html = fetch(target["params"])
        items = parse(html, target)
        if not items:
            # 파싱 0건은 사이트 구조 변경 신호일 수 있으므로 상태를 덮어쓰지 않는다.
            print(f"경고: '{target['name']}' 파싱 결과 0건. 이번 회차는 건너뜁니다.", file=sys.stderr)
            return 0
        print(f"{target['name']}: {len(items)}건 수집")

        for item in items:
            key = f"{target['params']['SCH_PRM_GB']}-{item['seq']}"
            current[key] = {"state": item["state"], "title": item["title"]}
            prev = state.get(key)

            if prev is None:
                if not first_run and matches_keyword(item):
                    notifications.append((item, "new"))
            elif prev.get("state") != item["state"]:
                # 모집전 -> 모집중 전환만 알린다. 마감 전환은 알리지 않는다.
                if item["state"] == "모집중" and matches_keyword(item):
                    notifications.append((item, "open"))

    if first_run:
        print(f"첫 실행: {len(current)}건을 기준선으로 저장합니다. 알림은 보내지 않습니다.")
    else:
        print(f"알림 대상 {len(notifications)}건")
        for item, kind in notifications:
            send(build_message(item, kind))
            time.sleep(1)  # Telegram rate limit 여유

    save_state(current)
    return 0


if __name__ == "__main__":
    sys.exit(main())
