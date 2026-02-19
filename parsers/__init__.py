"""parsers 패키지 — 국가별 법령 파서 레지스트리 및 공개 API.

새 국가 추가 시:
1. parsers/japan.py 생성 → BaseParser 상속, @register 데코레이터
2. 아래 import 섹션에 `import parsers.japan` 추가
3. app.py의 COUNTRY_MAP에 추가
"""

import os
import re
import time
import pandas as pd

from parsers.base import (
    BaseParser,
    parse_pdf,
    parse_rtf,
    _parse_preamble,
    _extract_article_title,
    _clean_english_article,
    save_structured_to_excel,
)

# ══════════════════════════════════════════════════════════════
# 레지스트리
# ══════════════════════════════════════════════════════════════

_REGISTRY: list[type[BaseParser]] = []


def register(parser_cls):
    """데코레이터: 파서 클래스를 레지스트리에 등록한다."""
    _REGISTRY.append(parser_cls)
    return parser_cls


def get_parser(file_path: str) -> BaseParser:
    """파일 경로에서 적합한 파서 인스턴스를 반환한다."""
    for cls in _REGISTRY:
        if cls.matches(file_path):
            return cls()
    # 기본값: EPC 파서
    from parsers.epc import EpcParser
    return EpcParser()


# ══════════════════════════════════════════════════════════════
# 국가별 파서 등록 (import 시 자동 등록)
# ══════════════════════════════════════════════════════════════

# 각 모듈을 import하면서 @register 데코레이터로 등록
# (순환 import 방지를 위해 여기서 import)
from parsers.epc import EpcParser
from parsers.korea import KoreaParser
from parsers.hongkong import HongkongParser
from parsers.usa import UsaParser
from parsers.germany import GermanyParser
from parsers.france import FranceParser

# 레지스트리에 등록 (경로 키워드가 구체적인 것 → 일반적인 것 순서)
register(KoreaParser)
register(HongkongParser)
register(UsaParser)
register(GermanyParser)
register(FranceParser)
register(EpcParser)  # 기본 영문 파서 (맨 마지막 — fallback)


# ══════════════════════════════════════════════════════════════
# 공개 API (기존 pdf_parser.py 호환)
# ══════════════════════════════════════════════════════════════

def _detect_lang(file_path: str) -> str:
    """파일 경로와 파일명에서 언어를 자동 감지한다."""
    path_lower = file_path.replace("\\", "/").lower()
    filename = os.path.basename(file_path)

    if "korea" in path_lower:
        return "korean"

    # 대만 폴더: 파일명에 한자(CJK Unified Ideographs)가 포함되면 chinese
    if "taiwan" in path_lower:
        if re.search(r"[\u4e00-\u9fff]", filename):
            return "chinese"
        return "english"

    if "france" in path_lower or "français" in path_lower or "francais" in path_lower:
        return "french"

    return "english"


def _detect_format(file_path: str) -> str:
    """파일 경로에서 법령 형식을 감지한다."""
    if file_path:
        path_lower = file_path.replace("\\", "/").lower()
        filename_lower = os.path.basename(file_path).lower()
        if "newzealand" in path_lower:
            return "nz"
        if "hongkong" in path_lower or "hong kong" in path_lower or "cap " in filename_lower:
            return "hk"
        if "usa" in path_lower:
            return "us"
        if "france" in path_lower or "français" in path_lower or "francais" in path_lower:
            return "france"
    return "standard"


def split_articles(text: str, lang: str = None, file_path: str = None) -> list[dict]:
    """텍스트를 조문 단위로 분리한다.

    Args:
        text: 전체 법령 텍스트
        lang: 언어 ('english', 'chinese', 'korean'). None이면 file_path로 자동 감지.
        file_path: 원본 파일 경로 (언어 자동 감지용)

    Returns:
        [{'id': '조문번호', 'text': '원문'}, ...]
    """
    if lang is None:
        lang = _detect_lang(file_path) if file_path else "english"

    if lang == "chinese":
        from parsers.taiwan import _split_chinese
        return _split_chinese(text)
    elif lang == "korean":
        from parsers.korea import _split_korean
        return _split_korean(text)
    elif lang == "french":
        from parsers.france import _split_french
        return _split_french(text)

    fmt = _detect_format(file_path)
    if fmt == "nz":
        from parsers.newzealand import _split_nz_english
        return _split_nz_english(text)
    if fmt == "hk":
        from parsers.hongkong import _split_hk_english
        return _split_hk_english(text)
    if fmt == "us":
        from parsers.usa import _split_us_english
        return _split_us_english(text)

    from parsers.epc import _split_english
    return _split_english(text)


def extract_structured_articles(
    file_path: str,
    progress_callback=None
) -> pd.DataFrame:
    """PDF에서 법조문을 계층 구조(편/장/절/조/항/호)로 추출하여 DataFrame으로 반환한다.

    Args:
        file_path: PDF 파일 경로
        progress_callback: 진행률 콜백 함수 (current, total, message)

    Returns:
        DataFrame with columns: ['편', '장', '절', '조문번호', '조문제목', '항', '호', '목', '세목', '원문']
    """
    # 0. 파서 인스턴스 가져오기
    parser = get_parser(file_path)

    # 1. 텍스트 추출 (PDF 또는 RTF)
    file_ext = os.path.splitext(file_path)[1].lower()
    if file_ext == ".rtf":
        text = parse_rtf(file_path)
    else:
        # use_layout=False: 2단 구성 처리 비활성화 (단어 잘림 방지)
        text = parse_pdf(file_path, use_layout=False)
    lang = _detect_lang(file_path)
    fmt = _detect_format(file_path)

    # 2. 계층 구조 감지 (편/장/절)
    hierarchy = _detect_hierarchy(text, lang, file_path=file_path)

    # 3. 조문 추출
    articles = split_articles(text, lang=lang, file_path=file_path)

    # 4. 각 조문의 항/호 파싱 및 DataFrame 생성
    rows = []
    current_part = ""
    current_chapter = ""
    current_section = ""

    # 이전 조문의 계층 정보 (위치를 못 찾은 조문을 위해)
    previous_part = ""
    previous_book = ""
    previous_title = ""
    previous_chapter = ""
    previous_section = ""

    for article in articles:
        article_id = article["id"]
        article_text = article["text"]

        # 홍콩 파서: Part/Schedule 정보가 article dict에 포함됨
        from parsers.hongkong import HongkongParser
        use_article_part = False
        if isinstance(parser, HongkongParser) and 'part' in article:
            current_part = article.get('part', '')
            current_chapter = ''
            current_section = ''
            use_article_part = True  # 플래그 설정: hierarchy 대신 article의 Part 사용

        # 전문 처리
        if article_id == "전문":
            # EPC는 전문을 문단별로 나누지 않음 (전체를 하나로 유지)
            from parsers.epc import EpcParser
            if isinstance(parser, EpcParser):
                rows.append({
                    "편": "",
                    "장": "",
                    "절": "",
                    "조문번호": "전문",
                    "조문제목": "",
                    "항": "",
                    "호": "",
                    "목": "",
                    "세목": "",
                    "원문": article_text
                })
            else:
                # 다른 국가는 전문을 문단별로 파싱
                preamble_paras = _parse_preamble(article_text)
                if preamble_paras:
                    for para in preamble_paras:
                        rows.append({
                            "편": "",
                            "장": "",
                            "절": "",
                            "조문번호": "전문",
                            "조문제목": para.get("paragraph", ""),
                            "항": "",
                            "호": "",
                            "목": "",
                            "세목": "",
                            "원문": para["text"]
                        })
                else:
                    rows.append({
                        "편": "",
                        "장": "",
                        "절": "",
                        "조문번호": "전문",
                        "조문제목": "",
                        "항": "",
                        "호": "",
                        "목": "",
                        "세목": "",
                        "원문": article_text
                    })
            continue

        # 현재 조문이 속한 계층 정보 업데이트
        article_pos = text.find(article_text)

        # 전체 텍스트로 찾지 못한 경우 조문 ID 패턴으로 찾기
        if article_pos == -1:
            # 영문: "Article N" 형식
            if "Article" in article_id:
                pattern = re.escape(article_id) + r"(?:\s|$)"
                match = re.search(pattern, text)
                if match:
                    article_pos = match.start()
            # 한국어: "제N조" 형식
            elif "제" in article_id and "조" in article_id:
                pattern = re.escape(article_id) + r"(?:\(|<|\s|$)"
                match = re.search(pattern, text)
                if match:
                    article_pos = match.start()
            # 중국어: "第N條" 형식
            elif "第" in article_id and "條" in article_id:
                pattern = re.escape(article_id)
                match = re.search(pattern, text)
                if match:
                    article_pos = match.start()

            # 미국: "§ N." 형식
            if article_pos == -1 and fmt == "us":
                us_pat = re.compile(
                    r"(?:^|\n)§\s*" + re.escape(article_id) + r"\.\s+"
                )
                all_matches = list(us_pat.finditer(text))
                if all_matches:
                    article_pos = all_matches[-1].start()

            # 홍콩: "N." 형식
            if article_pos == -1 and fmt == "hk":
                hk_pat = re.compile(
                    r"(?:^|\n)" + re.escape(article_id) + r"\.\s+[A-Z(]"
                )
                all_matches = list(hk_pat.finditer(text))
                if all_matches:
                    article_pos = all_matches[-1].start()

            # 여전히 못 찾은 경우 처음 100자로 재시도
            if article_pos == -1 and len(article_text) > 100:
                article_pos = text.find(article_text[:100])

        # 위치를 찾지 못한 경우 이전 조문의 계층 정보 사용
        if article_pos == -1:
            latest_part = previous_part
            latest_book = previous_book
            latest_title = previous_title
            latest_chapter = previous_chapter
            latest_section = previous_section
        # 홍콩 파서이고 article에 Part 정보가 있는 경우
        elif use_article_part:
            # Part는 article에서 가져오고, Division/Subdivision은 hierarchy에서 가져오기
            latest_part = current_part
            latest_book = ""
            latest_title = ""
            latest_chapter = ""
            latest_section = ""

            # hierarchy에서 Division/Subdivision 찾기 (현재 Part 범위 내만)
            # Part 경계를 추적하여 Division이 다른 Part에 속하지 않도록 함
            current_hierarchy_part = ""
            for h in hierarchy:
                if h["start_pos"] > article_pos:
                    break
                # Part가 바뀌면 chapter/section 초기화
                if h["type"] == "part":
                    current_hierarchy_part = h["title"]
                    latest_chapter = ""
                    latest_section = ""
                # Division/Subdivision은 같은 Part 내에서만 할당
                elif current_hierarchy_part == current_part:
                    if h["type"] == "division":
                        latest_chapter = h["title"]
                        latest_section = ""  # Division이 나오면 Subdivision 초기화
                    elif h["type"] == "subdivision":
                        latest_section = h["title"]
        else:
            latest_part = ""
            latest_book = ""
            latest_title = ""
            latest_chapter = ""
            latest_section = ""
            for h in hierarchy:
                if h["start_pos"] > article_pos:
                    break
                if h["type"] == "part":
                    latest_part = h["title"]
                    latest_book = ""
                    latest_title = ""
                    latest_chapter = ""
                    latest_section = ""
                elif h["type"] == "book":
                    # Livre는 매번 대체 (누적하지 않음)
                    latest_book = h["title"]
                elif h["type"] == "title":
                    # Titre (프랑스법: 편에 포함)
                    latest_title = h["title"]
                elif h["type"] == "chapter":
                    # Chapitre (프랑스법: 장)
                    latest_chapter = h["title"]
                    latest_section = ""
                elif h["type"] == "division":
                    # Division (홍콩법: 장)
                    latest_chapter = h["title"]
                    latest_section = ""
                elif h["type"] == "subdivision":
                    # Subdivision (홍콩법: 절)
                    latest_section = h["title"]
                elif h["type"] == "section":
                    # Section (프랑스법: 절)
                    latest_section = h["title"]
                elif h["type"] == "subsection":
                    # Sous-section은 Section과 함께 "절"에 표시
                    if latest_section and "Sous-section" in h["title"]:
                        latest_section = latest_section + " / " + h["title"]
                    else:
                        latest_section = h["title"]

            # 현재 계층 정보를 다음 조문을 위해 저장
            previous_part = latest_part
            previous_book = latest_book
            previous_title = latest_title
            previous_chapter = latest_chapter
            previous_section = latest_section

        # 프랑스법: Partie/Livre/Titre를 합쳐서 "편"에 표시
        current_part_list = []
        if latest_part:
            current_part_list.append(latest_part)
        if latest_book:
            current_part_list.append(latest_book)
        if latest_title:
            current_part_list.append(latest_title)
        current_part = " / ".join(current_part_list) if current_part_list else ""

        current_chapter = latest_chapter
        current_section = latest_section

        # 한국법: 조문번호/제목/원문 분리
        if lang == "korean":
            from parsers.korea import _clean_korean_article
            article_id, title, article_text = _clean_korean_article(
                article_id, article_text
            )
        else:
            # 조문 제목 추출
            if "title" in article and article["title"]:
                title = article["title"]
            else:
                title = _extract_article_title(article_text, lang)

            # 영문 조문 원문 정리 (중복 헤더 제거)
            if lang in ["english", None]:
                # 파서별 clean_article 메서드 사용 (EPC는 특수 처리 필요)
                if hasattr(parser, 'clean_article'):
                    article_text = parser.clean_article(article_id, article_text, title)
                else:
                    article_text = _clean_english_article(article_id, article_text, title)

        # 조문 ID 포맷팅 (파서별 처리)
        display_article_id = article_id
        if hasattr(parser, 'format_article_id'):
            display_article_id = parser.format_article_id(article_id)

        # 항/호 파싱
        paragraphs = _parse_paragraphs_and_items(article_text, lang, fmt=fmt, article_id=article_id)

        # EPC Article 178: 서명/날짜 부분 분리
        if hasattr(parser, 'split_final_signature'):
            paragraphs = parser.split_final_signature(article_id, paragraphs)

        # 줄바꿈 제거 함수 (영문 전용)
        def remove_line_breaks(text):
            """조문 내 줄바꿈을 공백으로 변경 (영문 전용)"""
            if lang not in ["english", None]:
                return text
            # 단일 줄바꿈을 공백으로 변경, 연속 줄바꿈은 유지
            text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text)
            # 연속된 공백을 하나로 정리
            text = re.sub(r' {2,}', ' ', text)
            # 줄바꿈 주변 공백 정리
            text = re.sub(r' *\n *', '\n', text)
            return text.strip()

        if not paragraphs:
            rows.append({
                "편": current_part,
                "장": current_chapter,
                "절": current_section,
                "조문번호": display_article_id,
                "조문제목": title,
                "항": "",
                "호": "",
                "목": "",
                "세목": "",
                "원문": remove_line_breaks(article_text)
            })
        else:
            for para in paragraphs:
                rows.append({
                    "편": current_part,
                    "장": current_chapter,
                    "절": current_section,
                    "조문번호": display_article_id,
                    "조문제목": title,
                    "항": para.get("paragraph", ""),
                    "호": para.get("item", ""),
                    "목": para.get("subitem", ""),
                    "세목": para.get("subsubitem", ""),
                    "원문": remove_line_breaks(para["text"])
                })

    df = pd.DataFrame(rows)

    # 조문번호 정규화: 'Section N' / 'Article N' / 'Rule N' / '§ N' → 'N'
    # 한국법(숫자만), 중문(第N条), 전문/삭제 등은 그대로 유지
    def _strip_article_prefix(val):
        s = str(val).strip()
        m = re.match(r'^(?:Section|Article|Rule|§)\s*(.+)$', s, re.IGNORECASE)
        return m.group(1).strip() if m else s

    if '조문번호' in df.columns:
        df['조문번호'] = df['조문번호'].apply(
            lambda x: _strip_article_prefix(x) if pd.notna(x) and str(x).strip() not in ('전문', '') else x
        )

    # 조문 번호로 정렬 (항/호/목 순서도 포함)
    # 1. 전문이 맨 앞
    # 2. 홍콩 파서: Part 번호 → 조문 번호 → 항 → 호 → 목 순서대로
    # 3. 기타: 조문 번호 → 항 → 호 → 목 순서대로
    def get_sort_key(row):
        import re
        from parsers.hongkong import HongkongParser

        article_id = row['조문번호']

        if article_id == "전문":
            return (-1, 0, 0, "", 0, "", "", 0, "", "")

        # 홍콩 파서: Part 번호 추출
        part_num = 0
        part_name = str(row['편']) if pd.notna(row['편']) else ""
        if isinstance(parser, HongkongParser) and part_name:
            # "Part N" 또는 "부칙 (Schedule N)" 패턴에서 숫자 추출
            if part_name.startswith('부칙'):
                part_num = 9999  # 부칙은 맨 뒤로
            else:
                part_match = re.search(r'Part (\d+)', part_name)
                if part_match:
                    part_num = int(part_match.group(1))

        # 조문 번호 파싱 (31ZC, 31ZD 등 알파벳 여러 개 지원)
        match = re.match(r'(\d+)([A-Z]*)', str(article_id))
        if match:
            article_num = int(match.group(1))
            article_letter = match.group(2) or ""
        else:
            # 기타 (삭제 등)
            return (1, part_num, 0, str(article_id), 0, "", "", 0, "", "")

        # 항 번호 파싱: (1), (2), (3), (1A), (1B) 등
        para = str(row['항']) if pd.notna(row['항']) else ""
        para_num = 999999  # 빈 항 번호는 맨 뒤로 (서명/날짜 등)
        para_letter = ""
        if para and para.strip():
            para_match = re.search(r'\(?(\d+)([a-zA-Z]?)\)?', para)
            if para_match:
                para_num = int(para_match.group(1))
                para_letter = para_match.group(2) or ""

        # 호 번호 파싱: (a), (b), (c) 등
        item = str(row['호']) if pd.notna(row['호']) else ""
        item_letter = ""
        if item:
            item_match = re.search(r'\(?([a-z])\)?', item)
            if item_match:
                item_letter = item_match.group(1)

        # 목 번호 파싱: (i), (ii), (iii) 등
        subitem = str(row['목']) if pd.notna(row['목']) else ""
        subitem_roman = ""
        subitem_num = 0
        if subitem:
            subitem_match = re.search(r'\(?([ivxlcdm]+)\)?', subitem, re.IGNORECASE)
            if subitem_match:
                subitem_roman = subitem_match.group(1).lower()
                # 로마 숫자를 아라비아 숫자로 변환
                roman_values = {'i': 1, 'v': 5, 'x': 10, 'l': 50, 'c': 100, 'd': 500, 'm': 1000}
                total = 0
                prev_value = 0
                for char in reversed(subitem_roman):
                    value = roman_values.get(char, 0)
                    if value < prev_value:
                        total -= value
                    else:
                        total += value
                    prev_value = value
                subitem_num = total

        # 세목 번호 파싱: (A), (B), (C) 등
        subsubitem = str(row['세목']) if pd.notna(row['세목']) else ""
        subsubitem_letter = ""
        if subsubitem:
            subsubitem_match = re.search(r'\(?([A-Z])\)?', subsubitem)
            if subsubitem_match:
                subsubitem_letter = subsubitem_match.group(1)

        return (0, part_num, article_num, article_letter, para_num, para_letter, item_letter, subitem_num, subitem_roman, subsubitem_letter)

    df['_sort_key'] = df.apply(get_sort_key, axis=1)
    df = df.sort_values('_sort_key').drop('_sort_key', axis=1).reset_index(drop=True)

    # 편/장 정보가 없는 조문을 인접 조문의 정보로 채우기
    # (삭제된 조문 제외)
    for idx in df.index:
        row = df.loc[idx]
        # 전문이나 삭제 조문은 건너뛰기
        if row['조문번호'] == '전문' or '삭제' in str(row['조문번호']):
            continue

        # 편 정보가 없는 경우
        if pd.isna(row['편']) or row['편'] == '':
            # 이전/다음 조문에서 찾기
            found = False
            # 먼저 다음 조문 확인 (같은 Part일 가능성 높음)
            for next_idx in range(idx + 1, min(idx + 5, len(df))):
                next_row = df.loc[next_idx]
                if next_row['편'] and next_row['편'] != '':
                    df.loc[idx, '편'] = next_row['편']
                    df.loc[idx, '장'] = next_row['장']
                    found = True
                    break

            # 다음 조문에서 못 찾으면 이전 조문 확인
            if not found:
                for prev_idx in range(idx - 1, max(idx - 5, -1), -1):
                    prev_row = df.loc[prev_idx]
                    if prev_row['편'] and prev_row['편'] != '':
                        df.loc[idx, '편'] = prev_row['편']
                        df.loc[idx, '장'] = prev_row['장']
                        break

    return df


def _detect_hierarchy(text: str, lang: str, file_path: str = None) -> list[dict]:
    """텍스트에서 편/장/절 계층 구조를 감지한다.

    각 국가별 파서의 detect_hierarchy를 호출한다.
    """
    fmt = _detect_format(file_path) if file_path else "standard"

    if lang == "chinese":
        from parsers.taiwan import _detect_hierarchy_chinese
        return _detect_hierarchy_chinese(text)
    elif lang == "korean":
        from parsers.korea import _detect_hierarchy_korean
        return _detect_hierarchy_korean(text)
    elif lang == "french":
        from parsers.france import _detect_hierarchy_french
        return _detect_hierarchy_french(text)
    elif fmt == "us":
        from parsers.usa import _detect_hierarchy_us
        return _detect_hierarchy_us(text)
    elif fmt == "nz":
        from parsers.newzealand import _detect_hierarchy_nz
        return _detect_hierarchy_nz(text)
    elif fmt == "hk":
        from parsers.hongkong import _detect_hierarchy_hk
        return _detect_hierarchy_hk(text)
    else:
        from parsers.epc import _detect_hierarchy_english
        return _detect_hierarchy_english(text)


def _parse_paragraphs_and_items(text: str, lang: str, fmt: str = "standard", article_id: str = None) -> list[dict]:
    """조문 텍스트에서 항, 호, 목, 세목을 파싱한다.

    각 국가별 파서의 parse_paragraphs를 호출한다.
    """
    if fmt == "us":
        from parsers.usa import _parse_paragraphs_us
        return _parse_paragraphs_us(text)
    elif fmt == "hk":
        from parsers.hongkong import _parse_paragraphs_hongkong
        return _parse_paragraphs_hongkong(text, article_id)
    elif fmt == "france":
        from parsers.france import _parse_paragraphs_french
        return _parse_paragraphs_french(text)
    elif lang == "chinese":
        return []
    elif lang == "korean":
        from parsers.korea import _parse_paragraphs_korean
        return _parse_paragraphs_korean(text)
    elif lang == "french":
        from parsers.france import _parse_paragraphs_french
        return _parse_paragraphs_french(text)
    else:
        from parsers.epc import _parse_paragraphs_english
        return _parse_paragraphs_english(text)
