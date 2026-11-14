"""상세 목차 · 간략 목차(md) · 간략 목차(csv)를 맞추는 도구.

    python3 scripts/toc.py csv     간략 목차 md에서 csv를 다시 만든다
    python3 scripts/toc.py check   세 파일이 서로 맞는지 확인한다 (어긋나면 exit 1)
"""
import csv
import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DETAIL = ROOT / "AI융합교육방법_교재_상세목차.md"
BRIEF = ROOT / "AI융합교육방법_교재_간략목차.md"
BRIEF_CSV = ROOT / "AI융합교육방법_교재_간략목차.csv"
CSV_HEADER = ["구분", "부", "장", "번호", "제목", "쪽수"]
FRONT_BACK = ("머리말", "부록", "참고문헌")


def trimmed_ok(full, short):
    """short가 full과 같거나, full에서 ' (' 또는 ':'로 시작하는 뒷부분(집필 메모)만 뺀 것인지."""
    return full == short or (full.startswith(short) and full[len(short):].startswith((" (", ":")))


def parse_detail(text):
    d = {"parts": {}, "chapters": [], "sections": [], "pages": {}, "appendix": [], "addie": {}}
    in_toc = False
    chapter = ""
    for line in text.splitlines():
        if line.startswith("## "):
            in_toc = line.startswith("## 5. 상세 목차")
        if m := re.match(r"^\| (\d+)부 (.+?) \| (\d+)~(\d+)장 \| .+? \| (.+?) \|$", line):
            d["addie"][m[1]] = (m[2], int(m[3]), int(m[4]), m[5])
        if not in_toc:
            continue
        if m := re.match(r"^### (\d+)부\. (.+)$", line):
            d["parts"][m[1]] = m[2]
        elif m := re.match(r"^### (머리말|부록|참고문헌) \((\d+)쪽\)$", line):
            d["pages"][m[1]] = int(m[2])
        elif m := re.match(r"^#### (\d+)장\. (.+) \((\d+)쪽\)$", line):
            chapter = m[1]
            d["chapters"].append((m[1], m[2], int(m[3])))
        elif m := re.match(r"^- (\d+\.\d+) (.+)$", line):
            d["sections"].append((m[1], m[2], chapter))
        elif m := re.match(r"^\| ([A-Z]) \| (.+?) \|$", line):
            d["appendix"].append((m[1], m[2]))
    return d


def parse_brief(text):
    """간략 목차 md를 CSV 행 목록과 부 설명으로 읽는다."""
    rows, part_desc = [], {}
    part = chapter = area = ""
    expect_desc = False
    for line in text.splitlines():
        if expect_desc and line.strip():
            part_desc[part] = line.strip()
            expect_desc = False
            continue
        if m := re.match(r"^### (\d+부)\. (.+) \((\d+)쪽\)$", line):
            part, chapter, area = m[1], "", ""
            rows.append(["부", part, "", part, m[2], m[3]])
            expect_desc = True
        elif m := re.match(r"^### (머리말|부록|참고문헌) \((\d+)쪽\)$", line):
            part = chapter = ""
            area = m[1]
            rows.append([area, "", "", "", area, m[2]])
        elif m := re.match(r"^\*\*(\d+장)\. (.+)\*\* \((\d+)쪽\)$", line):
            chapter = m[1]
            rows.append(["장", part, chapter, chapter, m[2], m[3]])
        elif m := re.match(r"^- (\d+\.\d+) (.+)$", line):
            rows.append(["절", part, chapter, m[1], m[2], ""])
        elif area == "부록" and (m := re.match(r"^- ([A-Z])\. (.+)$", line)):
            rows.append(["부록", "", "", m[1], m[2], ""])
    return rows, part_desc


def csv_text(rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")  # git(core.autocrlf=input)과 맞추려고 LF로 씀
    w.writerow(CSV_HEADER)
    w.writerows(rows)
    return buf.getvalue()


def write_csv():
    rows, _ = parse_brief(BRIEF.read_text(encoding="utf-8"))
    BRIEF_CSV.write_text(csv_text(rows), encoding="utf-8-sig", newline="")
    print(f"{BRIEF_CSV.name}: {len(rows)}행")


def check():
    d = parse_detail(DETAIL.read_text(encoding="utf-8"))
    rows, part_desc = parse_brief(BRIEF.read_text(encoding="utf-8"))
    errors = []

    def same(label, detail_val, brief_val):
        if detail_val != brief_val:
            errors.append(f"{label}\n    상세: {detail_val}\n    간략: {brief_val}")

    # 장: 번호·제목·쪽수가 같아야 함
    brief_ch = [(r[2].removesuffix("장"), r[4], int(r[5])) for r in rows if r[0] == "장"]
    same("장 번호", [c[0] for c in d["chapters"]], [c[0] for c in brief_ch])
    for dc, bc in zip(d["chapters"], brief_ch):
        same(f"{dc[0]}장 제목·쪽수", dc, bc)

    # 절: 번호가 같고, 번호에 맞는 장 아래에 있고, 간략 제목은 상세 제목에서 집필 메모만 뺀 것이어야 함
    brief_sec = [(r[3], r[4], r[2].removesuffix("장")) for r in rows if r[0] == "절"]
    same("절 번호", [s[0] for s in d["sections"]], [s[0] for s in brief_sec])
    for where, secs in (("상세", d["sections"]), ("간략", brief_sec)):
        for num, _, ch in secs:
            if num.split(".")[0] != ch:
                errors.append(f"{where} 목차의 {num} 절이 {ch}장 아래에 있음")
    detail_sec = {n: t for n, t, _ in d["sections"]}
    for num, title, _ in brief_sec:
        if num in detail_sec and not trimmed_ok(detail_sec[num], title):
            errors.append(f"{num} 절 제목 (같거나 ' (' ':' 앞에서만 줄일 수 있음)\n    상세: {detail_sec[num]}\n    간략: {title}")

    # 부: 제목·설명·소속 장·쪽수 합계
    ch_pages = {n: p for n, _, p in d["chapters"]}
    for r in rows:
        if r[0] != "부":
            continue
        n = r[1].removesuffix("부")
        same(f"{r[1]} 제목", d["parts"].get(n), r[4])
        if n in d["addie"]:
            _, lo, hi, desc = d["addie"][n]
            same(f"{r[1]} 설명 (상세 목차 1절 ADDIE 표)", desc, part_desc.get(r[1]))
            same(f"{r[1]} 쪽수 합계", sum(ch_pages.get(str(c), 0) for c in range(lo, hi + 1)), int(r[5]))
            for c in rows:
                if c[0] == "장" and c[1] == r[1]:
                    if not lo <= int(c[2].removesuffix("장")) <= hi:
                        errors.append(f"{c[2]}이 {r[1]}에 들어 있음 (ADDIE 표는 {lo}~{hi}장)")
        else:
            errors.append(f"{r[1]}: 상세 목차 ADDIE 표에 없음")

    # 머리말·부록·참고문헌 쪽수, 부록 항목
    for name in FRONT_BACK:
        brief_p = next((int(r[5]) for r in rows if r[0] == name and r[4] == name), None)
        same(f"{name} 쪽수", d["pages"].get(name), brief_p)
    brief_app = [(r[3], r[4]) for r in rows if r[0] == "부록" and r[3]]
    same("부록 항목 기호", [k for k, _ in d["appendix"]], [k for k, _ in brief_app])
    detail_app = dict(d["appendix"])
    for k, title in brief_app:
        if k in detail_app and not trimmed_ok(detail_app[k], title):
            errors.append(f"부록 {k} 제목\n    상세: {detail_app[k]}\n    간략: {title}")

    # csv가 간략 목차 md에서 만든 결과와 같아야 함
    current = BRIEF_CSV.read_text(encoding="utf-8-sig") if BRIEF_CSV.exists() else ""
    if current.replace("\r\n", "\n") != csv_text(rows).replace("\r\n", "\n"):
        errors.append(f"{BRIEF_CSV.name}가 간략 목차 md와 다름 → python3 scripts/toc.py csv")

    if errors:
        print(f"어긋남 {len(errors)}건")
        for e in errors:
            print(f"- {e}")
        sys.exit(1)
    print(f"일치: 장 {len(brief_ch)} · 절 {len(brief_sec)} · 부 {len(part_desc)} · 부록 {len(brief_app)} · csv {len(rows)}행")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "csv":
        write_csv()
    elif cmd == "check":
        check()
    else:
        print(__doc__)
        sys.exit(2)
