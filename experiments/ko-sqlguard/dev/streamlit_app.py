"""ko-sqlguard 웹 데모 (Streamlit).

    streamlit run dev/streamlit_app.py --server.port 8510

안전: 이 앱은 입력된 SQL을 **절대 실행하지 않는다**. ko-sqlguard.check() 는
sqlglot 파싱만 하는 순수 함수이며, 데모는 그 결과만 보여준다. 데이터베이스
드라이버를 import하지 않고, 연결/쿼리 실행 경로가 존재하지 않는다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ko_sqlguard import Guard, GuardPolicy, Severity, Verdict

st.set_page_config(page_title="ko-sqlguard 데모", page_icon="🛡️", layout="wide")

MAX_INPUT = 50_000

VERDICT_STYLE = {
    Verdict.PASS: ("✅ PASS", "그대로 허용"),
    Verdict.TRANSFORM: ("🟡 TRANSFORM", "안전하게 재작성 후 허용"),
    Verdict.BLOCK: ("⛔ BLOCK", "차단됨"),
}
SEV_EMOJI = {
    Severity.LOW: "🔵",
    Severity.MEDIUM: "🟠",
    Severity.HIGH: "🔴",
    Severity.CRITICAL: "🟣",
}

EXAMPLES: dict[str, list[str]] = {
    "정상 (허용/재작성)": [
        "SELECT id, name FROM customers WHERE id = 42",
        "SELECT * FROM orders",
        "SELECT count(*) FROM orders o JOIN customers c ON o.cid = c.id",
        "SELECT 이름, 나이 FROM 고객",
    ],
    "차단 — 문장/스택": [
        "DROP TABLE orders",
        "SELECT * FROM orders; DROP TABLE orders",
        "drop/**/table orders",
        "UPDATE orders SET total = 0",
    ],
    "차단 — allowlist/락": [
        "SELECT * FROM secrets",
        "SELECT * FROM secrets WHERE id IN (WITH secrets AS (SELECT 1 id) SELECT id FROM secrets)",
        "(SELECT * FROM orders) FOR UPDATE",
    ],
    "차단 — 위험 함수/주입": [
        "SELECT pg_sleep(10)",
        "SELECT pg_file_write('/tmp/x','data',false)",
        "SELECT * FROM orders WHERE id = 1 OR 1=1",
    ],
}


def parse_allowed_tables(text: str) -> dict[str, list[str]] | None:
    text = text.strip()
    if not text:
        return None  # None = 모든 테이블 허용
    out: dict[str, list[str]] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if ":" in line:
            name, cols = line.split(":", 1)
            name = name.strip()
            if not name:
                continue  # 콜론만/빈 이름은 무시 (조용한 전체차단 방지)
            out[name] = [c.strip() for c in cols.split(",") if c.strip()]
        else:
            out[line] = []
    return out or None


def build_policy() -> GuardPolicy:
    st.sidebar.header("정책 (GuardPolicy)")
    tables_text = st.sidebar.text_area(
        "허용 테이블",
        value="orders\ncustomers:id,name,email",
        help="한 줄에 하나. `테이블` 또는 `테이블:컬럼,컬럼`. 비우면 전체 허용.",
        height=110,
    )
    read_only = st.sidebar.checkbox("읽기 전용 (read_only)", value=True)
    col1, col2 = st.sidebar.columns(2)
    default_limit = int(col1.number_input("기본 LIMIT", min_value=0, value=1000, step=100))
    max_limit = int(col2.number_input("최대 LIMIT", min_value=0, value=10000, step=1000))
    if default_limit and max_limit and default_limit > max_limit:
        st.sidebar.info("기본 LIMIT이 최대보다 큽니다 — 주입 시 최대로 제한됩니다.")
    block_cartesian = st.sidebar.checkbox("카테시안 차단", value=True)
    block_tautology = st.sidebar.checkbox("항진명제(OR 1=1) 차단", value=True)
    sev = st.sidebar.select_slider(
        "차단 임계 severity (min_block_severity)",
        options=[Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL],
        value=Severity.MEDIUM,
        format_func=lambda s: s.name,
    )
    return GuardPolicy(
        allowed_tables=parse_allowed_tables(tables_text),
        read_only=read_only,
        default_limit=default_limit or None,
        max_limit=max_limit or None,
        block_cartesian=block_cartesian,
        block_tautology=block_tautology,
        min_block_severity=sev,
    )


def render_result(sql: str, policy: GuardPolicy) -> None:
    if len(sql) > MAX_INPUT:
        st.warning(f"입력이 너무 깁니다 (데모 제한 {MAX_INPUT:,}자).")
        return
    try:
        result = Guard(policy).check(sql)  # 순수 함수 — SQL을 실행하지 않음
    except Exception as e:  # noqa: BLE001 — 데모 방어막
        st.error(f"검사 중 예기치 못한 오류: {type(e).__name__}: {e}")
        return

    label, desc = VERDICT_STYLE[result.verdict]
    if result.verdict is Verdict.PASS:
        st.success(f"### {label}\n{desc}")
    elif result.verdict is Verdict.TRANSFORM:
        st.warning(f"### {label}\n{desc}")
    else:
        st.error(f"### {label}\n{desc}")

    if result.verdict is Verdict.TRANSFORM and result.sql:
        st.caption("재작성된 SQL (실행될 버전):")
        st.code(result.sql, language="sql")

    if result.violations:
        st.caption("위반 내역:")
        for v in result.violations:
            emoji = SEV_EMOJI.get(v.severity, "•")
            with st.container(border=True):
                st.markdown(f"{emoji} **{v.severity.name}** · `{v.code}` · _{v.action}_")
                st.write(v.reason)
                if v.fix:
                    st.caption(f"💡 {v.fix}")
    else:
        st.caption("위반 없음.")


def render_examples() -> None:
    st.markdown("#### 예제 (클릭하면 입력창에 채워집니다)")
    for category, queries in EXAMPLES.items():
        if not queries:
            continue
        st.write(f"**{category}**")
        cols = st.columns(len(queries))
        for i, q in enumerate(queries):
            label = q if len(q) < 40 else q[:37] + "…"
            if cols[i].button(label, key=f"{category}-{i}", help=q):
                st.session_state.sql = q


def main() -> None:
    st.title("🛡️ ko-sqlguard 웹 데모")
    st.caption(
        "LLM이 만든 PostgreSQL 쿼리를 **실행 전에** 결정론적으로 검증합니다. "
        "이 데모는 SQL을 파싱·판정만 하며 **절대 실행하지 않습니다.**"
    )

    policy = build_policy()

    if "sql" not in st.session_state:
        st.session_state.sql = (
            "SELECT * FROM secrets WHERE id IN (WITH secrets AS (SELECT 1 id) SELECT id FROM secrets)"
        )

    # 예제 버튼은 text_area 위에서 렌더 → session_state.sql 수정이 위젯 생성 전이라 안전.
    render_examples()
    sql = st.text_area("검사할 SQL", key="sql", height=120)
    st.caption("입력을 바꾸면 자동으로 즉시 검사됩니다.")

    left, right = st.columns([3, 2])
    with left:
        if sql.strip():
            render_result(sql, policy)
        else:
            st.info("위에 SQL을 입력하거나 예제를 눌러보세요.")
    with right:
        st.markdown("##### 현재 정책")
        st.json(
            {
                "allowed_tables": policy.allowed_tables,
                "read_only": policy.read_only,
                "default_limit": policy.default_limit,
                "max_limit": policy.max_limit,
                "block_cartesian": policy.block_cartesian,
                "block_tautology": policy.block_tautology,
                "min_block_severity": policy.min_block_severity.name,
            }
        )


if __name__ == "__main__":
    main()
