"""
알림dog - 다중 사이트 공지 알림
GitHub Actions에서 주기적으로 실행되며, 변경사항을 Telegram으로 전송한다.

사이트를 추가하려면:
  1) parse_XXX(html, target) 함수를 하나 만든다
  2) build_XXX(item, kind) 함수를 하나 만든다
  3) TARGETS 리스트에 항목을 추가하며 parser/builder를 지정한다
"""
import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

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
KEYWORDS = [k.strip() for k in os.environ.get("KEYWORDS", "").split(",") if k.strip()]


def esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# =========================================================
# 사이트 1: KSIA 반도체 교육과정
# =========================================================

KSIA_LIST = "https://infra.ksia.or.kr/user/Wo/WoUser0101.do"
KSIA_VIEW = "https://infra.ksia.or.kr/user/Wo/WoUser0101V.do"


def parse_ksia(html, target):
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

        detail = f"{KSIA_VIEW}?" + "&".join(
            f"{k}={v}" for k, v in {**target["params"], "WO_SEQ": seq}.items()
        )

        items.append({
            "uid": seq,
            "category": target["name"],
            "org": org_el.get_text(strip=True) if org_el else "",
            "title": " ".join(a.get_text(strip=True).split()),
            "apply_period": dates[0] if len(dates) > 0 else "",
            "edu_period": dates[1] if len(dates) > 1 else "",
            "capacity": chips[0] if len(chips) > 0 else "",
            "state": chips[1] if len(chips) > 1 else "",
            "url": detail,
        })
    return items


def build_ksia(item, kind):
    head = "🆕 새 교육과정" if kind == "new" else "🔔 모집 시작"
    return "\n".join([
        f"<b>{head}</b>",
        "",
        f"<b>{esc(item['title'])}</b>",
        f"🏫 {esc(item['org'])} · {esc(item['category'])}",
        f"📅 모집 {esc(item['apply_period'])}",
        f"📚 교육 {esc(item['edu_period'])}",
        f"👥 {esc(item['capacity'])} · {esc(item['state'])}",
        "",
        f'<a href="{esc(item["url"])}">신청 페이지 열기</a>',
    ])


# =========================================================
# 사이트 2: 연세대 전기전자공학부 채용 공지
# =========================================================

YONSEI_LIST = "https://ee.yonsei.ac.kr/ee/community/career_notice.do"


def parse_yonsei(html, target):
    soup = BeautifulSoup(html, "lxml")
    items = []
    for tr in soup.select("table.board-table tbody tr"):
        a = tr.select_one("a.c-board-title")
        if not a:
            continue
        m = re.search(r"articleNo=(\d+)", a.get("href", ""))
        if not m:
            continue
        tds = tr.find_all("td", recursive=False)
        items.append({
            "uid": m.group(1),
            "category": target["name"],
            "org": tds[3].get_text(strip=True) if len(tds) > 3 else "",
            "title": " ".join(a.get_text(strip=True).split()),
            "date": tds[4].get_text(strip=True) if len(tds) > 4 else "",
            "has_file": bool(tr.select_one(".board-notice-file")),
            # 공지 게시판은 '상태' 개념이 없으므로 고정값을 둔다
            "state": "-",
            "url": f"{YONSEI_LIST}?mode=view&articleNo={m.group(1)}",
        })
    return items


def build_yonsei(item, kind):
    clip = " 📎 첨부파일 있음" if item.get("has_file") else ""
    return "\n".join([
        "<b>📢 새 채용 공지</b>",
        "",
        f"<b>{esc(item['title'])}</b>",
        f"🏫 {esc(item['org'])} · {esc(item['category'])}",
        f"🗓 {esc(item['date'])}{clip}",
        "",
        f'<a href="{esc(item["url"])}">공지 보러가기</a>',
    ])


# =========================================================
# 감시 대상 등록
# =========================================================

TARGETS = [
    {
        "name": "예비취업자 교육",
        "key": "ksia002",
        "url": KSIA_LIST,
        "params": {
            "SCH_PRM_GB": "002",
            "TAB_ID": "1",
            "CURRENT_MENU_CODE": "MENU0040",
            "TOP_MENU_CODE": "MENU0040",
        },
        "parser": parse_ksia,
        "builder": build_ksia,
        # 모집전 -> 모집중 전환도 알림
        "watch_state": "모집중",
    },
    {
        "name": "연세대 전기전자 채용",
        "key": "yonsei-ee",
        "url": YONSEI_LIST,
        "params": {},
        "parser": parse_yonsei,
        "builder": build_yonsei,
        # 공지 게시판은 상태 전환 개념이 없음
        "watch_state": None,
    },
]


# =========================================================
# 공통 로직 (사이트가 늘어나도 바뀌지 않는 부분)
# =========================================================

def fetch(url, params, retries=3):
    last_err = None
    for i in range(retries):
        try:
            r = requests.get(url, params=params or None, headers=HEADERS, timeout=30)
            r.raise_for_status()
            r.encoding = r.apparent_encoding or "utf-8"
            return r.text
        except Exception as e:
            last_err = e
            if i < retries - 1:
                time.sleep(2 ** i * 3)
    raise RuntimeError(f"페이지 요청 실패: {last_err}")


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
    if not KEYWORDS:
        return True
    haystack = f"{item.get('title','')} {item.get('org','')}"
    return any(k in haystack for k in KEYWORDS)


def send(text):
    if not BOT_TOKEN or not CHAT_ID:
        print("[DRY RUN] 토큰 미설정, 콘솔 출력만 합니다.\n" + text + "\n" + "-" * 50)
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
    current = dict(state)  # 한 사이트가 실패해도 다른 사이트 기록은 보존
    notifications = []

    for target in TARGETS:
        try:
            html = fetch(target["url"], target["params"])
            items = target["parser"](html, target)
        except Exception as e:
            print(f"경고: '{target['name']}' 확인 실패 — {e}", file=sys.stderr)
            continue

        if not items:
            print(f"경고: '{target['name']}' 파싱 0건. 이 사이트는 건너뜁니다.", file=sys.stderr)
            continue

        print(f"{target['name']}: {len(items)}건 수집")

        for item in items:
            key = f"{target['key']}-{item['uid']}"
            current[key] = {"state": item.get("state", "-"), "title": item["title"]}
            prev = state.get(key)

            if prev is None:
                if not first_run and matches_keyword(item):
                    notifications.append((item, target, "new"))
            elif target["watch_state"] and prev.get("state") != item.get("state"):
                if item.get("state") == target["watch_state"] and matches_keyword(item):
                    notifications.append((item, target, "open"))

    if first_run:
        print(f"첫 실행: {len(current)}건을 기준선으로 저장합니다. 알림은 보내지 않습니다.")
    else:
        print(f"알림 대상 {len(notifications)}건")
        for item, target, kind in notifications:
            send(target["builder"](item, kind))
            time.sleep(1)

    save_state(current)
    return 0


if __name__ == "__main__":
    sys.exit(main())
