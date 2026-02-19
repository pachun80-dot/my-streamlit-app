"""유럽(EPC) 법령 파서."""

import re
from parsers.base import BaseParser, _extract_article_title, _clean_english_article


class EpcParser(BaseParser):
    """유럽 특허 조약(EPC) 파서."""

    COUNTRY_CODE = "epc"
    SUPPORTED_EXTENSIONS = [".pdf"]
    PATH_KEYWORDS = ["epc", "european"]
    LANG = "english"
    FORMAT = "standard"

    @classmethod
    def matches(cls, file_path: str) -> bool:
        path_lower = file_path.replace("\\", "/").lower()
        ext = __import__('os').path.splitext(file_path)[1].lower()
        if ext not in cls.SUPPORTED_EXTENSIONS:
            return False
        for kw in cls.PATH_KEYWORDS:
            if kw in path_lower:
                return True
        return False

    def split_articles(self, text: str) -> list[dict]:
        return _split_english(text)

    def detect_hierarchy(self, text: str) -> list[dict]:
        return _detect_hierarchy_english(text)

    def parse_paragraphs(self, text: str) -> list[dict]:
        return _parse_paragraphs_english(text)

    def extract_article_title(self, text: str) -> str:
        return _extract_article_title(text, "english")

    def clean_article(self, article_id: str, text: str, title: str) -> str:
        """EPC 조문 정리 - 제목 및 참조번호 제거"""
        lines = text.split("\n")
        clean_lines = []

        for i, line in enumerate(lines):
            line_stripped = line.strip()

            # 첫 번째 줄: Article ID 제거
            if i == 0 and article_id in line_stripped:
                continue

            # 초반 3줄 이내: 제목이나 참조가 포함된 줄 제거
            if i < 3:
                # 제목만 있는 줄 (정확히 일치)
                if title and line_stripped == title:
                    continue

                # 제목 + 참조번호 형식: "Territorial effect ... R. 39" 또는 "Territorial effect ... R."
                # 제목이 줄 앞부분에 있고, 참조(Art./R.)가 뒷부분에 있으면 제거
                if title and line_stripped.startswith(title):
                    # 참조 패턴 확인 (줄 끝 부분에 Art. 또는 R. 있음)
                    # 제목 길이를 고려하여 제목 이후의 텍스트만 확인
                    after_title = line_stripped[len(title):].strip()
                    if re.match(r'^(?:Art\.|R\.|Rule)(?:\s*[\d,\s\-a-zA-Z]*)?$', after_title):
                        continue

                # 참조번호만 있는 줄
                if re.match(r'^(?:Art\.|R\.|Rule|Reg\.)\s*[\d,\s\-a-zA-Z]+$', line_stripped):
                    continue

            # 실제 내용 추가
            if line_stripped:
                clean_lines.append(line)

        clean_text = "\n".join(clean_lines).strip()

        # 정리 후 내용이 없으면 원본 반환
        if not clean_text or len(clean_text) < 10:
            return text

        # 개정 이력 제거 (본문 끝에 붙어있는 경우)
        # 1. "See decisions/opinions of the Enlarged Board of Appeal..." (판례 참조)
        clean_text = re.sub(r'\s*See decisions?/opinions? of the Enlarged Board of Appeal[^.]*\.?\s*', ' ', clean_text, flags=re.IGNORECASE)

        # 2. "See information from..." 패턴
        clean_text = re.sub(r'\s*See information from[^.]*\.\s*', ' ', clean_text, flags=re.IGNORECASE)

        # 3. 일반적인 "See decision/opinion/notice..." 패턴
        clean_text = re.sub(r'\s*See (?:decision|opinion|notice)(?:s)?(?:/(?:decision|opinion|notice)(?:s)?)?(?: of| from)[^.]*\.\s*', ' ', clean_text, flags=re.IGNORECASE)

        # 4. "Amended/Inserted/Deleted by..." 패턴
        clean_text = re.sub(r'\s*(?:Amended|Inserted|Deleted) by the Act[^.]*\.\s*', ' ', clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r'\s*(?:Title )?(?:Amended|Inserted|Deleted) by[^.]*\.\s*', ' ', clean_text, flags=re.IGNORECASE)

        # 5. 괄호 안의 개정 이력: "(See decision...)" 또는 "(Annex I)"
        clean_text = re.sub(r'\s*\(See (?:decision|opinion|notice)(?:s)?[^)]*\)\s*', ' ', clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r'\s*\(Annex [IVX]+\)\s*', ' ', clean_text, flags=re.IGNORECASE)

        # 6. 날짜 형식의 참조: "11.2000.", "11.2022", "05.2011 (OJ EPO...)" 등
        clean_text = re.sub(r'\s*\d{1,2}\.\d{4}\.?\s*(?:\([^)]*\))?\s*', ' ', clean_text)

        # 7. "concerning..." 형식의 notice/decision 참조
        clean_text = re.sub(r'\s*(?:notice|decision|information) from the [^.]*concerning[^.]*\.\s*', ' ', clean_text, flags=re.IGNORECASE)

        # "European Patent Convention April 2025" 같은 헤더 제거
        clean_text = re.sub(r'\s*European Patent Convention\s+(?:April|January|February|March|May|June|July|August|September|October|November|December)\s+\d{4}\s*', ' ', clean_text)

        # 단독 페이지 번호 줄 제거 (예: "61" 또는 "61 ")
        clean_text = re.sub(r'(?m)^\d{1,3}\s*$', '', clean_text)

        # 항 번호 "(숫자)" 앞에 있는 페이지 번호 제거
        # "this Convention.61 (2)" → "this Convention.\n(2)"
        # 마침표/개행 뒤의 페이지 번호와 공백을 제거
        clean_text = re.sub(r'([.!?])\s*\d{1,3}\s+(?=\(\d+\))', r'\1\n', clean_text)
        # 줄바꿈 뒤의 페이지 번호와 공백을 제거
        clean_text = re.sub(r'\n\s*\d{1,3}\s+(?=\(\d+\))', '\n', clean_text)

        # 연속 공백 정리
        clean_text = re.sub(r' {2,}', ' ', clean_text)

        # 본문 마지막에 잘못 포함된 Chapter/Part/Section 제목 제거
        # 한 줄 형태: "...조문내용.\nChapter III The European Patent Office"
        clean_text = re.sub(
            r'\s*\n[ \t]*(?:Part|PART|Chapter|CHAPTER|Section|SECTION)\s+[IVX0-9]+[^\n]*$',
            '',
            clean_text
        )
        # 두 줄 형태: "...조문내용.\nChapter III\nThe European Patent Office"
        # ($\n 패턴: 첫 줄 끝 + 개행 + 두 번째 제목 줄 끝)
        clean_text = re.sub(
            r'\s*\n[ \t]*(?:Part|PART|Chapter|CHAPTER|Section|SECTION)\s+[IVX0-9]+[ \t]*$\n[ \t]*[A-Za-z ]+$',
            '',
            clean_text,
            flags=re.MULTILINE
        )

        return clean_text.strip()

    def find_article_position(self, article_id: str, text: str) -> int:
        if "Article" in article_id:
            pattern = re.escape(article_id) + r"(?:\s|$)"
            match = re.search(pattern, text)
            if match:
                return match.start()
        return -1

    def format_article_id(self, article_id: str) -> str:
        """조문 ID를 숫자만 남기도록 포맷팅

        예: "Article 52" → "52"
             "Article 4a" → "4a"
        """
        if article_id.startswith("Article "):
            return article_id.replace("Article ", "")
        return article_id

    def split_final_signature(self, article_id: str, paragraphs: list[dict]) -> list[dict]:
        """Article 178의 서명/날짜 부분을 별도 행으로 분리

        Args:
            article_id: 조문 ID (예: "Article 178")
            paragraphs: 파싱된 항/호 리스트

        Returns:
            서명 부분이 분리된 항/호 리스트
        """
        if article_id != "Article 178" or not paragraphs:
            return paragraphs

        # 마지막 항에서 서명/날짜 부분 분리
        last_para = paragraphs[-1]
        text = last_para.get("text", "")

        # "IN WITNESS WHEREOF"로 시작하는 부분 찾기
        match = re.search(r'(.*?)\s+(IN WITNESS WHEREOF.*)', text, re.DOTALL)
        if match:
            # 마지막 항의 텍스트 업데이트 (서명 부분 제거)
            last_para["text"] = match.group(1).strip()

            # 서명 부분을 별도 행으로 추가
            signature_text = match.group(2).strip()

            # "Done at Munich..."을 별도로 분리
            sig_parts = re.split(r'\s+(Done at Munich.*)', signature_text, maxsplit=1)

            if len(sig_parts) == 1:
                # "Done at Munich" 없음, 서명만
                paragraphs.append({
                    "paragraph": "",
                    "item": "",
                    "subitem": "",
                    "subsubitem": "",
                    "text": signature_text
                })
            elif len(sig_parts) >= 2:
                # IN WITNESS WHEREOF 부분
                paragraphs.append({
                    "paragraph": "",
                    "item": "",
                    "subitem": "",
                    "subsubitem": "",
                    "text": sig_parts[0].strip()
                })
                # Done at Munich 부분
                if len(sig_parts) == 3 and sig_parts[2].strip():
                    paragraphs.append({
                        "paragraph": "",
                        "item": "",
                        "subitem": "",
                        "subsubitem": "",
                        "text": sig_parts[1].strip() + " " + sig_parts[2].strip()
                    })
                else:
                    paragraphs.append({
                        "paragraph": "",
                        "item": "",
                        "subitem": "",
                        "subsubitem": "",
                        "text": sig_parts[1].strip()
                    })

        return paragraphs


def _clean_epc_annotations(text: str) -> str:
    """EPC PDF의 여백 참조·개정 이력·페이지 머리글을 제거한다.

    EPC PDF는 여백에 관련 조문/규칙 참조(Art. N, R. N)가 있는데,
    텍스트 추출 시 본문에 섞여 들어온다.
    """
    # 페이지 머리글/바닥글: "숫자\nEuropean Patent Convention..."
    text = re.sub(r'\n\d{1,3}\nEuropean Patent Convention[^\n]*', '', text)
    text = re.sub(r'\nEuropean Patent Convention[^\n]*\n\d{1,3}(?=\n|$)', '', text)

    # Article/Rule 줄 끝의 여백 참조: "Article 16 Art. 15" → "Article 16"
    text = re.sub(
        r'^((?:Article|Rule)\s+\d+[A-Za-z]*)\s+(?:Art\.|R\.)\s*[\d,\s\-a-zA-Z]+$',
        r'\1', text, flags=re.MULTILINE
    )

    # 단독 여백 참조 줄: "Art. 15, 92" 또는 "R. 11, 61-65" (줄 전체)
    text = re.sub(r'(?m)^(?:Art\.|R\.)\s*[\d,\s\-a-zA-Z]{1,30}$', '', text)

    # 여백 참조 연속 줄 (줄바꿈된 참조 번호): "12d, 97, 98" 또는 "134a"
    # 숫자와 콤마가 주인 짧은 줄만 제거 (Article/Rule/Section 등은 보호)
    text = re.sub(
        r'(?m)^(?!Article|Rule|Section|The |A |An |In |No |Any )[\d][,\s\d\-a-zA-Z]{0,19}$(?=\n(?:\(|[A-Z][a-z]))',
        '', text
    )

    # 제목 줄 끝의 여백 참조: "Receiving Section R. 10, 11" → "Receiving Section"
    # "Boards of Appeal R. 12a, 12b, 12c," 처럼 알파벳 포함 참조도 처리
    # 주의: \s 대신 [ ] 사용 (개행 매칭 방지)
    text = re.sub(r'(?m)^([A-Z][a-zA-Z ]+?)[ ]+R\.[ ]*[\d, \-a-zA-Z]+[, ]*$', r'\1', text)

    # 제목 줄 끝의 참조 번호 잔여: "Legal Division 134a" → "Legal Division"
    # "Enlarged Board of Appeal 112a" → "Enlarged Board of Appeal"
    text = re.sub(r'(?m)^([A-Z][a-zA-Z ]+?)[ ]+(\d+[a-z])$', r'\1', text)

    # 본문 줄 끝의 참조 번호: "shall be responsible for: 12d, 13, 109"
    text = re.sub(r'(?m)((?:for|of|under|to):?[ ]*)(\d+[a-z]?(?:,[ ]*\d+[a-z]?)*)[ ]*$', r'\1', text)

    # 개정 이력 및 참조 제거 (여러 패턴)
    # 1. 숫자로 시작하는 각주 라인 (예: "149 Amended by...", "150 See decisions...")
    text = re.sub(r'(?m)^\d{1,3}\s+(?:Amended|Inserted|Deleted|See (?:decision|opinion|notice))[^\n]*$', '', text)

    # 2. "See opinion(s)/decision(s) of..."
    text = re.sub(r'(?m)^See (?:opinions?|decisions?|notice|decision)(?:/decisions?)?(?: from| of)[^\n]*$', '', text)

    # 3. "Amended by...", "Inserted by...", "Deleted by..." 등
    text = re.sub(r'(?m)^(?:Title )?(?:[Aa]mended|[Ii]nserted|[Dd]eleted)(?: by)[^\n]*$', '', text)

    # 4. 개정법 전체 이름 형식: "Amended by the Act revising..."
    text = re.sub(r'(?m)^(?:Title )?(?:Amended|Inserted|Deleted) by the Act[^\n]*$', '', text)

    # 5. 다중 줄 개정 이력 블록 제거 (빈 줄로 구분된)
    # "Amended by...\nSee decision...\nAmended by..." 같은 블록
    text = re.sub(r'(?m)^(?:(?:Title )?(?:Amended|Inserted|Deleted|See (?:decision|opinion|notice))[^\n]*\n?)+', '', text)

    # 6. 단독 숫자 라인 제거 (각주 번호)
    text = re.sub(r'(?m)^\d{1,3}\s*$', '', text)

    # 줄바꿈 하이픈과 페이지 번호 처리: "pa- 96\ntents" → "patents"
    # 하이픈 + 공백/숫자 + 줄바꿈 + 소문자로 이어지는 경우
    # 1단계: "pa- 96\ntents" → "pa-\ntents" (중간 페이지 번호 제거)
    text = re.sub(r'([a-z])-\s+\d{1,3}\s*\n\s*([a-z])', r'\1-\n\2', text)

    # 2단계: "pa-\ntents" → "patents" (하이픈 제거)
    text = re.sub(r'([a-z])-\s*\n\s*([a-z])', r'\1\2', text)

    # 문장 끝 페이지 번호 제거: "tents. 96\n" → "tents.\n"
    text = re.sub(r'([.!?])\s+\d{1,3}\s*\n', r'\1\n', text)

    # Article/Rule/Section 앞의 페이지 번호 제거
    # "10 Article 11" → "Article 11"
    # "106\nArticle 100" → "Article 100"
    text = re.sub(r'\b\d{1,3}\s+(?=(?:Article|Rule|Section|Regulation)\s+\d)', '', text)
    text = re.sub(r'\b\d{1,3}\s*\n\s*(?=(?:Article|Rule|Section|Regulation)\s+\d)', '\n', text)

    # Article 번호 뒤의 페이지 번호 제거 (공백 있는 경우)
    # "Article 11 12" → "Article 11" (12는 페이지 번호)
    text = re.sub(r'((?:Article|Rule|Section|Regulation)\s+\d+[a-z]?)\s+\d{1,3}\b', r'\1', text)

    # Article 번호에 붙은 페이지 번호/각주 번호 제거 (공백 없는 경우)
    # "Article 6353" → "Article 63" (53은 페이지 번호/각주)
    # 4-5자리 숫자를 2-3자리로 자르기
    text = re.sub(r'\b(Article|Rule|Section|Regulation)\s+(\d{2,3})(\d{2,3})(?=\s|[A-Z])', r'\1 \2', text)

    # 항/호/목 번호에 붙은 각주 번호 제거
    # "(2)181" → "(2)", "(a)53" → "(a)", "(i)12" → "(i)"
    text = re.sub(r'\((\d+[a-z]?)\)\d{2,3}\b', r'(\1)', text)  # (2)181 → (2)
    text = re.sub(r'\(([a-z])\)\d{2,3}\b', r'(\1)', text)      # (a)53 → (a)
    text = re.sub(r'\(([ivxlcdm]+)\)\d{2,3}\b', r'(\1)', text) # (i)12 → (i)

    # 연속 빈 줄 정리
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text


def _split_english(text: str) -> list[dict]:
    """영문 법령을 조문 단위로 분리한다.

    줄 시작에 오는 'Article N' 만 조문 시작으로 인식한다.
    - 본문 중간의 참조("pursuant to Article 174")는 무시한다.
    - 분리 후 본문이 짧은 항목(목차·참조표 등)은 제거한다.
    - 같은 Article 번호가 여러 번 나오면 가장 긴 본문을 유지한다.
    """
    # EPC 여백 주석 제거 (European Patent Convention 포함 시)
    if "European Patent Convention" in text:
        text = _clean_epc_annotations(text)

    # EPC Preamble 보존
    import re
    preamble_match = re.search(r'\n\s*PREAMBLE\s*\n(.*?)(?=\n\s*PART I\b)', text, re.DOTALL | re.IGNORECASE)
    preamble_text = ""
    if preamble_match:
        preamble_start = preamble_match.start()
        preamble_end = preamble_match.end()
        preamble_text = text[preamble_start:preamble_end].strip()

    pattern = re.compile(
        r"(?:^|\n)\s*"  # Allow leading spaces after newline
        r"((?:Article|Section|Rule|Regulation)\s+\d{1,3}[a-z]?)\b",  # Limit to 3 digits max + optional letter
        re.IGNORECASE,
    )

    candidates = list(pattern.finditer(text))
    if not candidates:
        return [{"id": "전문", "text": text.strip()}] if text.strip() else []

    # Cross-reference 필터: "Article N," 처럼 조문번호 바로 뒤에 쉼표가 오는 경우는
    # 본문 내 참조(예: "Article 54, paragraphs 2 and 3")이므로 조문 시작으로 보지 않음
    candidates = [
        m for m in candidates
        if m.end() >= len(text) or text[m.end()] != ','
    ]
    if not candidates:
        return [{"id": "전문", "text": text.strip()}] if text.strip() else []

    # 1차: 모든 줄-시작 매칭으로 분리
    raw_articles = []
    for i, match in enumerate(candidates):
        start = match.start()
        if text[start:start + 1] == "\n":
            start += 1
        end = candidates[i + 1].start() if i + 1 < len(candidates) else len(text)
        chunk = text[start:end].strip()
        if not chunk:
            continue
        article_id = match.group(1).strip()

        # 비정상 ID 필터 (PDF 줄바꿈으로 숫자가 합쳐진 경우: Article 169196 등)
        num_match = re.search(r"\d+", article_id)
        if num_match and len(num_match.group()) > 4:
            continue

        raw_articles.append({"id": article_id, "text": chunk})

    # 2차: 조문 내용에서 편/장/절 제목 제거
    # EPC PDF에서 두 줄 형태로 나뉜 제목도 처리:
    #   "Chapter III                   \n        The European Patent Office"
    # $\n 패턴: 첫 줄 끝($) + 개행 + 두 번째 제목 줄
    hierarchy_patterns = [
        # 두 줄 형태 우선 처리 (한 줄 패턴보다 먼저 적용)
        re.compile(r"^[ \t]*(?:PART|Part)\s+[IVX]+[ \t]*$\n[ \t]*[A-Za-z ]+$", re.MULTILINE),
        re.compile(r"^[ \t]*(?:CHAPTER|Chapter)\s+[IVX0-9]+[ \t]*$\n[ \t]*[A-Za-z ]+$", re.MULTILINE),
        re.compile(r"^[ \t]*(?:SECTION|Section)\s+[IVX]+[ \t]*$\n[ \t]*[A-Za-z ]+$", re.MULTILINE),
        # 한 줄 형태
        re.compile(r"^[ \t]*(?:PART|Part)\s+[IVX]+[^\n]*\n?", re.MULTILINE | re.IGNORECASE),
        re.compile(r"^[ \t]*(?:CHAPTER|Chapter)\s+[IVX0-9]+[^\n]*\n?", re.MULTILINE | re.IGNORECASE),
        re.compile(r"^[ \t]*(?:SECTION|Section)\s+[IVX]+[^\n]*\n?", re.MULTILINE | re.IGNORECASE),
        re.compile(r"\n[ \t]*(?:PART|Part)\s+[IVX]+[^\n]*", re.IGNORECASE),
        re.compile(r"\n[ \t]*(?:CHAPTER|Chapter)\s+[IVX0-9]+[^\n]*", re.IGNORECASE),
        re.compile(r"\n[ \t]*(?:SECTION|Section)\s+[IVX]+[^\n]*", re.IGNORECASE),
    ]

    for a in raw_articles:
        cleaned_text = a["text"]
        for pattern in hierarchy_patterns:
            cleaned_text = pattern.sub("", cleaned_text)
        cleaned_text = cleaned_text.strip()
        a["text"] = cleaned_text

    # 3차: 삭제 조문 감지 — 본문에 (deleted) / (repealed) 포함 시 표시
    for a in raw_articles:
        if re.search(r"\(deleted\)|\(repealed\)", a["text"], re.IGNORECASE):
            a["deleted"] = True

    # 4차: 같은 ID 중복 시 가장 긴 본문만 유지 (TOC < 본문이므로 자동 제거)
    seen = {}
    for a in raw_articles:
        aid = a["id"]
        if aid not in seen or len(a["text"]) > len(seen[aid]["text"]):
            seen[aid] = a

    # 5차: 본문이 너무 짧은 항목 제거 (단, 삭제 조문은 유지)
    MIN_CONTENT_LEN = 80
    filtered = {}
    for k, v in seen.items():
        if len(v["text"]) >= MIN_CONTENT_LEN or v.get("deleted"):
            filtered[k] = v

    # 6차: 집단 삭제 조문 추가
    # "Articles 159, 160, 161, 162 and 163 were deleted" 같은 패턴 감지
    import re
    group_delete_pattern = re.compile(
        r'Articles?\s+[\d,\s]+and\s+\d+\s+(?:was|were)\s+deleted',
        re.IGNORECASE
    )
    for match in group_delete_pattern.finditer(text):
        # 매칭된 텍스트에서 모든 숫자 추출
        matched_text = match.group(0)
        all_nums = re.findall(r'\b(\d+)\b', matched_text)

        # 각 번호를 개별 삭제 조문으로 추가
        for num in all_nums:
            article_id = f"Article {num}"
            if article_id not in filtered:
                filtered[article_id] = {
                    "id": article_id,
                    "text": "(deleted)",
                    "deleted": True
                }

    # 원래 등장 순서 유지
    id_order = []
    for a in raw_articles:
        if a["id"] in filtered and a["id"] not in id_order:
            id_order.append(a["id"])

    # 집단 삭제 조문을 id_order에 추가 (숫자 순서대로 삽입)
    import re
    for aid in filtered.keys():
        if aid not in id_order:
            # 숫자 추출
            match = re.search(r'(\d+)', aid)
            if match:
                num = int(match.group(1))
                # 적절한 위치에 삽입
                inserted = False
                for i, existing_id in enumerate(id_order):
                    existing_match = re.search(r'(\d+)', existing_id)
                    if existing_match and int(existing_match.group(1)) > num:
                        id_order.insert(i, aid)
                        inserted = True
                        break
                if not inserted:
                    id_order.append(aid)

    articles = []

    # 전문(서문) 추가: PREAMBLE 섹션이 감지되면 실제 내용만, 없으면 첫 조문 이전 전체
    if preamble_text:
        # PREAMBLE 섹션 내용만 추출 (TOC·제목·여백 제외)
        # preamble_match.group(1)은 PREAMBLE 헤더 다음부터 PART I 이전까지의 내용
        preamble_content = preamble_match.group(1).strip()
        # 공백만 있는 줄 → 빈 줄, 연속 빈 줄 정리
        preamble_content = re.sub(r'(?m)^[ \t]+$', '', preamble_content)
        preamble_content = re.sub(r'[ \t]{2,}', ' ', preamble_content)
        preamble_content = re.sub(r'\n{3,}', '\n\n', preamble_content)
        # 페이지 번호·헤더 제거: "HAVE AGREED..." 이후 불필요 텍스트 제거
        have_agreed = re.search(r'HAVE AGREED[^\n]*', preamble_content, re.IGNORECASE)
        if have_agreed:
            preamble_content = preamble_content[:have_agreed.end()].strip()
        preamble_content = preamble_content.strip()
        if preamble_content:
            articles.append({"id": "전문", "text": preamble_content})
    else:
        first_start = candidates[0].start()
        if text[first_start:first_start + 1] == "\n":
            first_start += 1
        preamble = text[:first_start].strip()
        if preamble:
            articles.append({"id": "전문", "text": preamble})

    for aid in id_order:
        entry = filtered[aid]
        if entry.get("deleted"):
            entry["id"] = entry["id"] + " (삭제)"
            entry["text"] = "(삭제)"
        articles.append(entry)

    return articles


def _detect_hierarchy_english(text: str) -> list[dict]:
    """영문 법령에서 편/장/절 계층 구조를 감지한다."""
    hierarchy = []

    # 영문: Part I, Chapter 1, Section 1 (전체 제목 포함)
    # EPC PDF는 들여쓰기가 많으므로 \s*를 추가하여 공백 허용
    # Part 번호와 제목 사이에 숫자(페이지번호 등)가 있을 수 있음: "PART X180 INTERNATIONAL..."
    part_pattern = re.compile(
        r"(?:^|\n)\s*((?:Part|PART)\s+[IVX]+)(?:\d+)?\s+([A-Z][^\n]{10,70})|(?:^|\n)\s*((?:Part|PART)\s+[IVX]+)(\s*\n[A-Z][A-Z\s]+)",
        re.IGNORECASE
    )
    chapter_pattern = re.compile(
        r"(?:^|\n)\s*((?:Chapter|CHAPTER)\s+[IVX0-9]+)(?:\s+([A-Za-z][^\n]{5,60}))?",
        re.IGNORECASE
    )
    section_pattern = re.compile(
        r"(?:^|\n)\s*((?:Section|SECTION)\s+[IVX]+)(?:\s+([A-Za-z][^\n]{5,60}))?",
        re.IGNORECASE
    )

    # 편 감지
    for match in part_pattern.finditer(text):
        # 두 가지 패턴 중 어느 것이 매칭되었는지 확인
        if match.group(1):  # 첫 번째 패턴: Part + optional digit + title
            part_num = match.group(1).strip()
            part_title = match.group(2).strip() if match.group(2) else ""
        else:  # 두 번째 패턴: Part + newline + all-caps title
            part_num = match.group(3).strip()
            part_title = match.group(4).strip() if match.group(4) else ""

        if part_title:
            full_title = f"{part_num} {part_title}"
        else:
            full_title = part_num

        full_title = " ".join(full_title.split())
        # 끝에 붙은 숫자 제거 (페이지 번호 등)
        full_title = re.sub(r"\s+\d+$", "", full_title)

        if "Chapter" not in full_title and "Article" not in full_title:
            hierarchy.append({
                "type": "part",
                "title": full_title,
                "start_pos": match.start()
            })

    # 장 감지
    for match in chapter_pattern.finditer(text):
        chapter_num = match.group(1).strip()
        chapter_title = match.group(2).strip() if match.group(2) else ""

        if chapter_title:
            full_title = f"{chapter_num} {chapter_title}"
        else:
            full_title = chapter_num

        full_title = " ".join(full_title.split())
        full_title = re.sub(r"\s+\d+$", "", full_title)

        if "Article" not in full_title:
            hierarchy.append({
                "type": "chapter",
                "title": full_title,
                "start_pos": match.start()
            })

    # 절 감지
    for match in section_pattern.finditer(text):
        section_num = match.group(1).strip()
        section_title = match.group(2).strip() if match.group(2) else ""

        if section_title:
            full_title = f"{section_num} {section_title}"
        else:
            full_title = section_num

        full_title = " ".join(full_title.split())
        full_title = re.sub(r"\s+\d+$", "", full_title)

        if "Article" not in full_title:
            hierarchy.append({
                "type": "section",
                "title": full_title,
                "start_pos": match.start()
            })

    # 제목 정제: <개정 ...>, <신설 ...> 등 이력 태그 제거
    for h in hierarchy:
        h["title"] = re.sub(r"\s*<[^>]+>\s*$", "", h["title"]).strip()

    # 위치 순서대로 정렬
    hierarchy.sort(key=lambda x: x["start_pos"])

    return hierarchy


def _parse_paragraphs_english(text: str) -> list[dict]:
    """영문 조문 텍스트에서 항, 호, 목을 파싱한다.

    (1), (2), (3)... (paragraph) / (a), (b), (c)... (item) / (i), (ii), (iii)... (subitem)
    """
    results = []

    # Paragraph: (1), (2)...
    # 줄 시작, 줄바꿈, 또는 문장 끝(마침표/느낌표/물음표) 후에 오는 (숫자)
    para_pattern = re.compile(r"(?:^|\n|[.!?])\s*\((\d+)\)\s+")
    paragraphs = list(para_pattern.finditer(text))

    # 항 번호가 없으면 (a), (b), (c) 항목만 파싱
    if not paragraphs:
        item_pattern = re.compile(r"(?:^|\n)\s*\(([a-hj-uw-z])\)\s+")
        items = list(item_pattern.finditer(text))

        if not items:
            # 항목도 없으면 전체를 하나로
            return []

        # (a), (b), (c) 항목 파싱
        results = []
        first_item_start = items[0].start()
        intro_text = text[:first_item_start].strip()

        # 도입부가 있으면 추가
        if intro_text:
            results.append({
                "paragraph": "",
                "item": "",
                "subitem": "",
                "subsubitem": "",
                "text": intro_text
            })

        # 각 항목 처리
        for i, item_match in enumerate(items):
            item_letter = item_match.group(1)
            start = item_match.end()
            end = items[i + 1].start() if i + 1 < len(items) else len(text)
            item_text = text[start:end].strip()

            results.append({
                "paragraph": "",
                "item": f"({item_letter})",
                "subitem": "",
                "subsubitem": "",
                "text": item_text
            })

        return results

    # 정의 조항 감지
    def _is_definition_paragraph(para_text: str) -> bool:
        means_count = len(re.findall(r'\bmeans\b', para_text))
        if means_count >= 3:
            return True
        if "unless the context otherwise requires" in para_text.lower():
            return True
        return False

    for i, para_match in enumerate(paragraphs):
        para_num = str(para_match.group(1))  # 문자열로 변환
        start = para_match.end()
        end = paragraphs[i + 1].start() if i + 1 < len(paragraphs) else len(text)
        para_text = text[start:end].strip()

        # 정의 조항이면 (a)/(b) 분리 없이 전체를 하나로 유지
        if _is_definition_paragraph(para_text):
            results.append({
                "paragraph": para_num,
                "item": "",
                "subitem": "",
                "subsubitem": "",
                "text": para_text
            })
            continue

        # Item: (a), (b), (c)... (i, v, x 제외 - 로마 숫자와 구분)
        item_pattern = re.compile(r"(?:^|\n)\s*\(([a-hj-uw-z])\)\s+")
        items = list(item_pattern.finditer(para_text))

        if not items:
            results.append({
                "paragraph": para_num,
                "item": "",
                "subitem": "",
                "subsubitem": "",
                "text": para_text
            })
        else:
            # (a) 앞의 리드 텍스트를 별도 행으로 추가
            lead_text = para_text[:items[0].start()].strip()
            if lead_text:
                results.append({
                    "paragraph": para_num,
                    "item": "",
                    "subitem": "",
                    "subsubitem": "",
                    "text": lead_text
                })

            for j, item_match in enumerate(items):
                item_letter = str(item_match.group(1))  # 문자열로 변환
                item_start = item_match.end()
                item_end = items[j + 1].start() if j + 1 < len(items) else len(para_text)
                item_text = para_text[item_start:item_end].strip()

                # Subitem: (i), (ii), (iii), (iv)... (로마 숫자)
                subitem_pattern = re.compile(r"(?:^|\n)\s*\(([ivxlcdm]+)\)\s+")
                subitems = list(subitem_pattern.finditer(item_text))

                if not subitems:
                    results.append({
                        "paragraph": para_num,
                        "item": item_letter,
                        "subitem": "",
                        "subsubitem": "",
                        "text": item_text
                    })
                else:
                    for k, subitem_match in enumerate(subitems):
                        subitem_roman = str(subitem_match.group(1))  # 문자열로 변환
                        subitem_start = subitem_match.end()
                        subitem_end = subitems[k + 1].start() if k + 1 < len(subitems) else len(item_text)
                        subitem_text = item_text[subitem_start:subitem_end].strip()
                        results.append({
                            "paragraph": para_num,
                            "item": item_letter,
                            "subitem": subitem_roman,
                            "subsubitem": "",
                            "text": subitem_text
                        })

    return results
