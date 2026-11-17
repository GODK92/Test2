import functools
import json
import os
import re
import uuid
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="쇼핑 리스트", page_icon="🛒", layout="centered")

MAX_NAME_LEN = 100
MAX_ITEMS = 200
DATA_DIR = Path(__file__).parent / "data"
UID_PATTERN = re.compile(r"^[0-9a-f]{12}$")

# 주의: st.session_state.items 는 dict의 items() 메서드와 충돌하므로
# 이 파일에서는 항상 st.session_state["items"] 처럼 대괄호로 접근한다.


# ---------- 저장소 (사용자별 JSON 파일) ----------

def get_uid() -> str:
    """URL 쿼리(?u=...)의 사용자 ID. 없거나 형식이 잘못되면 새로 발급해 URL에 넣는다.

    ID마다 별도 파일을 쓰므로 방문자끼리 리스트가 섞이지 않고,
    새로고침해도 URL이 유지되어 같은 리스트가 다시 열린다.
    형식을 검증하므로 파일 경로 조작(../)도 막힌다.
    """
    uid = st.query_params.get("u", "")
    if not UID_PATTERN.match(uid):
        uid = uuid.uuid4().hex[:12]
        st.query_params["u"] = uid
    return uid


def data_path() -> Path:
    return DATA_DIR / f"{st.session_state['uid']}.json"


def load_data() -> tuple[list[dict], int] | None:
    """저장 파일을 읽는다. 파일이 없거나 깨졌으면 None."""
    try:
        raw = json.loads(data_path().read_text(encoding="utf-8"))
        items = [
            {
                "id": int(i["id"]),
                "name": str(i["name"]).strip()[:MAX_NAME_LEN],
                "checked": bool(i["checked"]),
            }
            for i in raw["items"][:MAX_ITEMS]
        ]
        next_id = max([int(raw.get("next_id", 1))] + [i["id"] + 1 for i in items])
        return items, next_id
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save_data() -> None:
    """현재 상태를 파일에 저장 (임시 파일에 쓴 뒤 교체해 저장 도중 깨짐 방지)."""
    tmp = None
    try:
        DATA_DIR.mkdir(exist_ok=True)
        path = data_path()
        # 탭마다 임시 파일 이름을 달리해 동시 저장 시 서로 덮어쓰지 않게 한다
        tmp = path.with_name(f"{path.stem}.{uuid.uuid4().hex[:8]}.tmp")
        payload = {
            "items": st.session_state["items"],
            "next_id": st.session_state["next_id"],
        }
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        st.session_state["notice"] = "저장하지 못했어요. 새로고침하면 변경 내용이 사라질 수 있어요."
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def find_item(item_id: int) -> dict | None:
    for item in st.session_state["items"]:
        if item["id"] == item_id:
            return item
    return None


def sync_from_disk() -> None:
    """다른 탭/기기에서 바뀐 내용을 반영하기 위해 파일의 최신 상태로 세션을 갱신한다.

    파일이 아직 없거나 읽을 수 없으면 현재 세션 상태를 그대로 둔다.
    """
    data = load_data()
    if data is not None:
        st.session_state["items"], st.session_state["next_id"] = data
    editing = st.session_state["editing_id"]
    if editing is not None and find_item(editing) is None:
        st.session_state["editing_id"] = None


def init_state() -> None:
    """세션 상태를 준비하고 매 실행마다 저장 파일의 최신 내용을 반영한다."""
    if "uid" not in st.session_state:
        st.session_state["uid"] = get_uid()
    st.session_state.setdefault("items", [])  # [{"id": int, "name": str, "checked": bool}]
    st.session_state.setdefault("next_id", 1)
    st.session_state.setdefault("editing_id", None)
    st.session_state.setdefault("notice", None)  # 콜백에서 남기는 경고 메시지
    sync_from_disk()


def escape_md(text: str) -> str:
    """사용자 입력이 마크다운/LaTeX/이모지 코드로 해석되지 않게 이스케이프."""
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|~<>$:&])", r"\\\1", text)


# ---------- 상태 변경 (모두 on_click / on_change 콜백에서 호출) ----------

def mutation(fn):
    """파일의 최신 상태를 먼저 읽고 → 변경을 적용하고 → 저장한다.

    세션 메모리의 오래된 목록을 통째로 덮어써서 다른 탭의 변경이 사라지는 것을 막는다.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        sync_from_disk()
        fn(*args, **kwargs)
        save_data()

    return wrapper


@mutation
def add_item() -> None:
    """추가 폼의 입력값을 읽어 아이템 추가."""
    name = st.session_state.get("new_item_name", "").strip()[:MAX_NAME_LEN]
    if not name:
        st.session_state["notice"] = "물건 이름을 입력해 주세요."
        return
    if len(st.session_state["items"]) >= MAX_ITEMS:
        st.session_state["notice"] = f"물건은 최대 {MAX_ITEMS}개까지 담을 수 있어요."
        return
    st.session_state["items"].append(
        {"id": st.session_state["next_id"], "name": name, "checked": False}
    )
    st.session_state["next_id"] += 1


def start_edit(item_id: int) -> None:
    st.session_state["editing_id"] = item_id


def cancel_edit() -> None:
    st.session_state["editing_id"] = None


@mutation
def update_item(item_id: int) -> None:
    """수정 입력창의 값으로 이름 변경. 빈 값이면 저장하지 않고 수정 모드 유지."""
    name = st.session_state.get(f"edit_input_{item_id}", "").strip()[:MAX_NAME_LEN]
    if not name:
        st.session_state["notice"] = "물건 이름을 입력해 주세요."
        return
    item = find_item(item_id)
    if item is not None:
        item["name"] = name
    st.session_state["editing_id"] = None


@mutation
def delete_item(item_id: int) -> None:
    st.session_state["items"] = [
        i for i in st.session_state["items"] if i["id"] != item_id
    ]
    if st.session_state["editing_id"] == item_id:
        st.session_state["editing_id"] = None


@mutation
def toggle_item(item_id: int) -> None:
    item = find_item(item_id)
    if item is not None:
        item["checked"] = st.session_state[f"check_{item_id}"]


@mutation
def clear_checked() -> None:
    st.session_state["items"] = [
        i for i in st.session_state["items"] if not i["checked"]
    ]


# ---------- 화면 ----------

# 최소한의 CSS. Streamlit이 위젯 key로 붙여주는 `st-key-<key>` 클래스를 주로 쓴다.
CSS = """
<style>
:root {
  --danger: #c53030;
  --muted: #6b6f7a;
}
@media (prefers-color-scheme: dark) {
  :root {--danger: #ff6b6b; --muted: #9aa0ab;}
}
footer {visibility: hidden;}
.block-container {max-width: 640px; padding-top: 2.5rem;}
h1 {padding-bottom: 0.25rem; font-size: 2rem !important;}
[data-testid="stVerticalBlock"] {gap: 0.6rem;}

/* 모바일에서도 컬럼이 세로로 쌓이지 않고 한 줄을 유지 */
[data-testid="stHorizontalBlock"] {flex-wrap: nowrap !important; align-items: center; gap: 0.5rem;}
[data-testid="stColumn"] {min-width: 0 !important;}

/* 폼: 테두리 제거 */
[data-testid="stForm"] {border: 0; padding: 0;}

/* 터치 영역 44px 이상 */
.stButton button, [data-testid="stFormSubmitButton"] button {min-height: 2.75rem;}
[class*="st-key-edit_"] button, [class*="st-key-del_"] button {min-width: 2.75rem;}

/* 항목 카드 */
[class*="st-key-row_"] {border-radius: 0.75rem; padding: 0.25rem 0.75rem !important;}
[class*="st-key-row_done_"] label p {color: var(--muted);}

/* 수정/삭제 버튼: 좁은 화면에서는 아이콘만 (글자는 스크린리더용으로 유지) */
[class*="st-key-edit_"] button, [class*="st-key-del_"] button {padding: 0.25rem 0.5rem; white-space: nowrap;}
[class*="st-key-del_"] button {color: var(--danger);}
[class*="st-key-del_"] button:hover {background: rgba(197, 48, 48, 0.12);}
@media (max-width: 640px) {
  [class*="st-key-edit_"] button p, [class*="st-key-del_"] button p {
    position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0);
  }
  /* 좁은 화면에서는 입력창 안내 문구("Press Enter...")가 입력 내용과 겹치므로 숨김 */
  [data-testid="InputInstructions"] {display: none;}
}

/* 완료 항목 모두 삭제: 위험 동작 */
.st-key-clear_checked button:not(:disabled) {border-color: var(--danger); color: var(--danger);}
.st-key-clear_checked button:not(:disabled):hover {background: rgba(197, 48, 48, 0.12);}
.st-key-clear_checked {margin-top: 0.5rem;}

/* 빈 상태 */
.empty-state {text-align: center; padding: 2.5rem 1rem; color: var(--muted);}
.empty-state .big {font-size: 3rem; line-height: 1.2;}
</style>
"""


def render_add_form() -> None:
    with st.form("add_form", clear_on_submit=True, border=False):
        col_input, col_btn = st.columns([5, 1.4])
        col_input.text_input(
            "물건 이름",
            key="new_item_name",
            max_chars=MAX_NAME_LEN,
            placeholder="물건 이름 (예: 우유)",
            label_visibility="collapsed",
        )
        with col_btn:
            st.form_submit_button(
                "추가", on_click=add_item, type="primary", use_container_width=True
            )


def render_progress() -> None:
    items = st.session_state["items"]
    total = len(items)
    done = sum(1 for i in items if i["checked"])
    st.markdown(f"전체 {total}개 중 **{done}개** 완료")
    st.progress(done / total if total else 0.0)


def render_edit_row(item: dict) -> None:
    """수정 행. 폼으로 감싸 Enter 키로도 저장되게 한다(첫 번째 제출 버튼 = 저장)."""
    item_id = item["id"]
    with st.form(f"edit_form_{item_id}", border=False):
        col_input, col_save, col_cancel = st.columns([5, 1.4, 1.4])
        col_input.text_input(
            "이름 수정",
            value=item["name"],
            key=f"edit_input_{item_id}",
            max_chars=MAX_NAME_LEN,
            label_visibility="collapsed",
        )
        col_save.form_submit_button(
            "저장", key=f"save_{item_id}", on_click=update_item, args=(item_id,),
            type="primary", use_container_width=True,
        )
        col_cancel.form_submit_button(
            "취소", key=f"cancel_{item_id}", on_click=cancel_edit,
            use_container_width=True,
        )


def render_view_row(item: dict) -> None:
    item_id = item["id"]
    col_check, col_edit, col_del = st.columns([6, 1.6, 1.6])
    label = escape_md(item["name"])
    # 다른 탭에서 바뀐 체크 상태가 위젯의 오래된 값에 가려지지 않도록 매번 맞춰 준다
    st.session_state[f"check_{item_id}"] = item["checked"]
    col_check.checkbox(
        f"~~{label}~~" if item["checked"] else label,
        key=f"check_{item_id}",
        on_change=toggle_item,
        args=(item_id,),
    )
    col_edit.button(
        "수정", key=f"edit_{item_id}", icon="✏️", type="tertiary",
        on_click=start_edit, args=(item_id,), help="이름 수정",
    )
    col_del.button(
        "삭제", key=f"del_{item_id}", icon="🗑️", type="tertiary",
        on_click=delete_item, args=(item_id,), help="삭제",
    )


def render_item(item: dict) -> None:
    item_id = item["id"]
    editing = st.session_state["editing_id"] == item_id
    row_key = f"row_done_{item_id}" if item["checked"] and not editing else f"row_{item_id}"
    with st.container(border=True, key=row_key):
        if editing:
            render_edit_row(item)
        else:
            render_view_row(item)


def render_list() -> None:
    items = st.session_state["items"]
    if not items:
        st.markdown(
            '<div class="empty-state"><div class="big">🧺</div>'
            "<p><b>아직 담은 물건이 없어요</b><br>위 입력창에 살 물건을 적어 보세요</p></div>",
            unsafe_allow_html=True,
        )
        return
    render_progress()
    for item in items:
        render_item(item)
    st.button(
        "완료 항목 모두 삭제",
        key="clear_checked",
        icon="🧹",
        on_click=clear_checked,
        disabled=not any(i["checked"] for i in items),
        use_container_width=True,
    )


def main() -> None:
    init_state()
    st.markdown(CSS, unsafe_allow_html=True)
    st.title("🛒 쇼핑 리스트")
    render_add_form()
    notice = st.session_state["notice"]
    if notice:
        st.warning(notice)
        st.session_state["notice"] = None
    render_list()
    st.caption("💡 이 페이지 주소(URL)를 북마크해 두면 나중에도 같은 리스트를 열 수 있어요.")


main()
