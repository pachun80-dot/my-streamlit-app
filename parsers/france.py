"""프랑스 LEGI XML 파서.

프랑스 공식 LEGI 데이터베이스의 XML 파일을 파싱하여 구조화된 DataFrame 생성.
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from html import unescape
import re
from typing import List, Tuple
import pandas as pd
from parsers.base import BaseParser


class FranceParser(BaseParser):
    """프랑스 LEGI XML 파서 (XML 디렉토리 전용)."""

    COUNTRY_CODE = "france"
    SUPPORTED_EXTENSIONS = [".xml"]
    PATH_KEYWORDS = ["france", "français", "francais", "FRANCE", "legi", "LEGI"]
    LANG = "french"
    FORMAT = "france"

    @classmethod
    def matches(cls, file_path: str) -> bool:
        """이 파서는 명시적으로 호출할 때만 사용."""
        # XML 디렉토리는 자동 감지하지 않고 명시적 호출만 지원
        return False

    def split_articles(self, text: str) -> list[dict]:
        """BaseParser 인터페이스 호환용 (사용 안 함)."""
        return []

    def detect_hierarchy(self, text: str) -> list[dict]:
        """BaseParser 인터페이스 호환용 (사용 안 함)."""
        return []

    def parse_paragraphs(self, text: str) -> list[dict]:
        """BaseParser 인터페이스 호환용 (사용 안 함)."""
        return []


def detect_section_type(title: str) -> tuple:
    """섹션 제목에서 타입과 번호 감지."""
    title_lower = title.lower()

    if "partie législative" in title_lower or "partie réglementaire" in title_lower:
        return ("part", "")

    partie_match = re.match(r"(première|deuxième|troisième|quatrième|cinquième)\s+partie", title_lower)
    if partie_match:
        num_map = {"première": "1", "deuxième": "2", "troisième": "3", "quatrième": "4", "cinquième": "5"}
        return ("part", num_map.get(partie_match.group(1), ""))

    livre_match = re.match(r"livre\s+([ivxlcdm]+)", title_lower)
    if livre_match:
        return ("book", livre_match.group(1).upper())

    titre_match = re.match(r"titre\s+([ivxlcdm]+)", title_lower)
    if titre_match:
        return ("title", titre_match.group(1).upper())

    chapitre_match = re.match(r"chapitre\s+([ivxlcdm]+)", title_lower)
    if chapitre_match:
        return ("chapter", chapitre_match.group(1).upper())

    section_match = re.match(r"section\s+(\d+)", title_lower)
    if section_match:
        return ("section", section_match.group(1))

    subsection_match = re.match(r"sous-section\s+(\d+)", title_lower)
    if subsection_match:
        return ("subsection", subsection_match.group(1))

    return ("unknown", "")


def extract_hierarchy_from_contexte(root) -> list:
    """CONTEXTE XML에서 계층 구조 추출."""
    hierarchy = []

    def extract_nested_tm(tm_elem, level=0):
        titre_tm = tm_elem.find('TITRE_TM')
        if titre_tm is not None and titre_tm.text:
            title = titre_tm.text.strip()
            section_type, section_num = detect_section_type(title)
            hierarchy.append({
                'type': section_type,
                'num': section_num,
                'title': title,
                'level': level
            })

        for nested_tm in tm_elem.findall('TM'):
            extract_nested_tm(nested_tm, level + 1)

    for tm in root.findall('.//CONTEXTE/TEXTE/TM'):
        extract_nested_tm(tm)

    return hierarchy


def extract_paragraphs_from_element(elem) -> List[str]:
    """CONTENU 요소에서 각 <p> 태그를 별도 문단으로 추출."""
    paragraphs = []

    for p in elem.findall('.//p'):
        text_parts = []
        if p.text:
            text_parts.append(p.text)
        for child in p:
            if child.text:
                text_parts.append(child.text)
            if child.tail:
                text_parts.append(child.tail)

        para_text = ''.join(text_parts)
        para_text = unescape(para_text)
        para_text = re.sub(r'\s+', ' ', para_text)
        para_text = para_text.strip()

        if para_text:
            paragraphs.append(para_text)

    # <p> 태그가 없으면 전체를 하나의 문단으로
    if not paragraphs:
        text_parts = []
        if elem.text:
            text_parts.append(elem.text)
        for child in elem:
            if child.text:
                text_parts.append(child.text)
            if child.tail:
                text_parts.append(child.tail)
        full_text = ''.join(text_parts)
        full_text = unescape(full_text)
        full_text = re.sub(r'\s+', ' ', full_text)
        full_text = full_text.strip()
        if full_text:
            paragraphs.append(full_text)

    return paragraphs


def find_item_in_paragraph(para: str) -> Tuple[str, str, str]:
    """문단 시작 부분에서 항목 번호 찾기.

    Returns:
        (type, number, rest_of_text) - 항목이 없으면 ('none', '', para)
    """
    # 1°, 2°, 3° 형식 (문단 시작)
    degree_match = re.match(r'^\s*(\d+)°\s+(.+)', para, re.DOTALL)
    if degree_match:
        context_before = para[:degree_match.start(1)]
        if not any(kw in context_before.lower() for kw in ['au ', 'du ', 'le ', 'article', 'visé']):
            return ('degree', degree_match.group(1) + '°', degree_match.group(2))

    # I, II, III 로마 숫자 (문단 시작)
    roman_match = re.match(r'^\s*(I{1,3}|IV|V|VI{0,3}|IX|X)[\s.\-]+(.+)', para, re.DOTALL)
    if roman_match:
        context_before = para[:roman_match.start(1)]
        if not any(kw in context_before.lower() for kw in ['au ', 'du ', 'le ', 'article', 'visé', 'livre']):
            return ('roman', roman_match.group(1), roman_match.group(2))

    # a), b), c) 형식 (문단 시작)
    alpha_match = re.match(r'^\s*([a-z])\)\s+(.+)', para, re.DOTALL)
    if alpha_match:
        return ('alpha', alpha_match.group(1) + ')', alpha_match.group(2))

    return ('none', '', para)


def parse_paragraphs(paragraphs: List[str]) -> List[dict]:
    """문단 리스트를 구조화된 행으로 변환.

    도입부, 항목들, 결론 문단을 구분하여 처리.
    """
    rows = []
    current_roman = ''
    current_degree = ''

    has_items = False
    last_item_index = -1

    # 1단계: 항목이 있는지, 마지막 항목 위치 확인
    for i, para in enumerate(paragraphs):
        item_type, item_num, text = find_item_in_paragraph(para)
        if item_type != 'none':
            has_items = True
            last_item_index = i

    # 2단계: 각 문단을 행으로 변환
    for i, para in enumerate(paragraphs):
        item_type, item_num, text = find_item_in_paragraph(para)

        if item_type == 'none':
            # 항목 번호가 없는 문단
            rows.append({
                'roman': '',
                'degree': '',
                'alpha': '',
                'text': para
            })
        elif item_type == 'roman':
            current_roman = item_num
            current_degree = ''
            rows.append({
                'roman': current_roman,
                'degree': '',
                'alpha': '',
                'text': text
            })
        elif item_type == 'degree':
            current_degree = item_num
            rows.append({
                'roman': current_roman,
                'degree': current_degree,
                'alpha': '',
                'text': text
            })
        elif item_type == 'alpha':
            rows.append({
                'roman': current_roman,
                'degree': current_degree,
                'alpha': item_num,
                'text': text
            })

    return rows


def parse_french_legi_xml(legi_dir: str, article_filter=None) -> pd.DataFrame:
    """LEGI XML 디렉토리에서 프랑스 법령을 파싱한다.

    Args:
        legi_dir: LEGI XML 디렉토리 경로 (예: "DATA/FRANCE/CPI_only/LEGITEXT000006069414")
        article_filter: 조문 필터 ('L' 또는 'R' 또는 None)

    Returns:
        구조화된 DataFrame (편/장/절/조문번호/항/호/목/원문)
    """
    legi_path = Path(legi_dir)
    article_dir = legi_path / "article" / "LEGI" / "ARTI"

    if not article_dir.exists():
        return pd.DataFrame()

    all_articles = []

    # 모든 XML 파일 파싱
    for xml_file in article_dir.rglob("*.xml"):
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()

            # VIGUEUR 상태만 처리
            etat = root.findtext(".//ETAT", "").strip()
            if etat != "VIGUEUR":
                continue

            article_num = root.findtext(".//NUM", "").strip()
            if not article_num:
                continue

            # 필터 적용
            if article_filter and not article_num.startswith(article_filter):
                continue

            content_elem = root.find(".//BLOC_TEXTUEL/CONTENU")
            if content_elem is None:
                continue

            # 문단 단위로 추출
            paragraphs = extract_paragraphs_from_element(content_elem)
            hierarchy = extract_hierarchy_from_contexte(root)

            # 계층 구조 매핑
            part_parts = []
            chapter_title = ""
            section_title = ""

            for h in hierarchy:
                h_type = h.get('type', '')
                if h_type in ['part', 'book']:
                    part_parts.append(h['title'])
                elif h_type == 'title':
                    if section_title:
                        section_title = h['title'] + " / " + section_title
                    else:
                        section_title = h['title']
                elif h_type == 'chapter':
                    chapter_title = h['title']
                elif h_type in ['section', 'subsection']:
                    if section_title:
                        section_title += " / " + h['title']
                    else:
                        section_title = h['title']

            part_title = " / ".join(part_parts) if part_parts else ""

            article_data = {
                'article_num': article_num,
                'part': part_title,
                'chapter': chapter_title,
                'section': section_title,
                'paragraphs': paragraphs
            }
            all_articles.append(article_data)

        except Exception as e:
            continue

    # 조문 번호로 정렬
    def article_sort_key(article):
        num = article['article_num']
        match = re.match(r'([LR])(\*?)(\d+)-(\d+)', num)
        if match:
            prefix, star, first, second = match.groups()
            prefix_val = 1 if prefix == 'L' else 2
            star_val = 0.5 if star else 0
            return (prefix_val, int(first), star_val, int(second))
        return (3, 0, 0, 0)

    all_articles.sort(key=article_sort_key)

    # DataFrame 행 생성
    rows = []
    for article in all_articles:
        parsed_rows = parse_paragraphs(article['paragraphs'])

        for parsed_row in parsed_rows:
            row = {
                '편': article['part'],
                '장': article['chapter'],
                '절': article['section'],
                '조문번호': article['article_num'],
                '조문제목': "",
                '항': parsed_row.get('roman', ''),
                '호': parsed_row.get('degree', ''),
                '목': parsed_row.get('alpha', ''),
                '세목': '',
                '원문': parsed_row['text']
            }
            rows.append(row)

    df = pd.DataFrame(rows)
    return df


def parse_and_save_french_law(
    legi_dir: str,
    output_dir: str = "DATA/output/구조화법률/프랑스",
    law_name: str = "Code_de_la_propriété_intellectuelle",
    save_separate: bool = True
) -> dict:
    """프랑스 법령을 파싱하고 Excel로 저장.

    Args:
        legi_dir: LEGI XML 디렉토리 경로
        output_dir: 출력 디렉토리
        law_name: 법령 이름 (파일명에 사용)
        save_separate: L/R 조문을 별도 파일로 저장할지 여부

    Returns:
        파싱 결과 정보 (통계, 파일 경로 등)
    """
    print("=" * 80)
    print(f"프랑스 LEGI XML 파싱: {law_name}")
    print("=" * 80)

    # L조문 파싱
    print("\n[1/3] L조문 (Partie législative) 파싱 중...")
    df_l = parse_french_legi_xml(legi_dir, "L")
    l_articles = df_l['조문번호'].nunique() if not df_l.empty else 0
    l_rows = len(df_l)
    print(f"  ✓ {l_articles}개 조문, {l_rows}개 행")

    # R조문 파싱
    print("\n[2/3] R조문 (Partie réglementaire) 파싱 중...")
    df_r = parse_french_legi_xml(legi_dir, "R")
    r_articles = df_r['조문번호'].nunique() if not df_r.empty else 0
    r_rows = len(df_r)
    print(f"  ✓ {r_articles}개 조문, {r_rows}개 행")

    # 전체 합치기
    df_all = pd.concat([df_l, df_r], ignore_index=True)
    total_articles = l_articles + r_articles
    total_rows = len(df_all)

    print(f"\n[3/3] 전체: {total_articles}개 조문, {total_rows}개 행")

    # 통계 계산
    stats = {
        'l_articles': l_articles,
        'l_rows': l_rows,
        'l_roman': len(df_l[df_l['항'] != '']) if not df_l.empty else 0,
        'l_degree': len(df_l[df_l['호'] != '']) if not df_l.empty else 0,
        'l_alpha': len(df_l[df_l['목'] != '']) if not df_l.empty else 0,
        'r_articles': r_articles,
        'r_rows': r_rows,
        'r_roman': len(df_r[df_r['항'] != '']) if not df_r.empty else 0,
        'r_degree': len(df_r[df_r['호'] != '']) if not df_r.empty else 0,
        'r_alpha': len(df_r[df_r['목'] != '']) if not df_r.empty else 0,
        'total_articles': total_articles,
        'total_rows': total_rows
    }

    print(f"\n항목 통계:")
    print(f"  L: {stats['l_roman']}개 항, {stats['l_degree']}개 호, {stats['l_alpha']}개 목")
    print(f"  R: {stats['r_roman']}개 항, {stats['r_degree']}개 호, {stats['r_alpha']}개 목")

    # 파일 저장
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    saved_files = []

    if save_separate and not df_l.empty:
        # L조문 저장
        l_file = output_path / f"{law_name}_L_VIGUEUR.xlsx"
        df_l.to_excel(l_file, index=False)
        saved_files.append(str(l_file))
        print(f"\n  ✓ {l_file}")

    if save_separate and not df_r.empty:
        # R조문 저장
        r_file = output_path / f"{law_name}_R_VIGUEUR.xlsx"
        df_r.to_excel(r_file, index=False)
        saved_files.append(str(r_file))
        print(f"  ✓ {r_file}")

    # 전체 저장
    all_file = output_path / f"{law_name}_ALL.xlsx"
    df_all.to_excel(all_file, index=False)
    saved_files.append(str(all_file))
    print(f"  ✓ {all_file}")

    print("\n" + "=" * 80)

    return {
        'stats': stats,
        'files': saved_files,
        'dataframes': {
            'L': df_l,
            'R': df_r,
            'ALL': df_all
        }
    }


if __name__ == "__main__":
    # 테스트 실행
    result = parse_and_save_french_law(
        "DATA/FRANCE/CPI_only/LEGITEXT000006069414",
        "DATA/output/구조화법률/프랑스"
    )

    print("\n파싱 완료!")
    print(f"총 {result['stats']['total_articles']}개 조문, {result['stats']['total_rows']}개 행")
