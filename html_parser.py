"""HTML 법령 파싱 모듈

유럽 법령, 중국 법령 등 HTML 형식으로 제공되는 법령을 파싱합니다.
"""
import re
import requests
from bs4 import BeautifulSoup
import pandas as pd


def parse_eu_html(url: str) -> dict:
    """유럽 법령 HTML을 파싱하여 구조화된 데이터를 반환한다.

    Args:
        url: HTML 법령 URL

    Returns:
        {
            'preamble': [{'type': 'CONSIDERING', 'text': '...'}, ...],
            'articles': [{'id': 'Article 1', 'title': '...', 'text': '...', 'hierarchy': {...}}, ...]
        }
    """
    # HTML 다운로드
    response = requests.get(url)
    response.encoding = 'utf-8'
    html = response.text

    # BeautifulSoup으로 파싱
    soup = BeautifulSoup(html, 'html.parser')

    # 전체 텍스트 추출
    text = soup.get_text()

    # 전문 파싱
    preamble = _parse_html_preamble(text)

    # 조문 파싱
    articles = _parse_html_articles(text)

    return {
        'preamble': preamble,
        'articles': articles
    }


def _parse_html_preamble(text: str) -> list[dict]:
    """HTML 텍스트에서 전문을 파싱한다."""
    # "THE CONTRACTING MEMBER STATES" 부터 "HAVE AGREED AS FOLLOWS" 까지 추출
    preamble_match = re.search(
        r'(THE CONTRACTING MEMBER STATES.*?HAVE AGREED AS FOLLOWS:)',
        text,
        re.DOTALL | re.IGNORECASE
    )

    if not preamble_match:
        return []

    preamble_text = preamble_match.group(1)

    results = []

    # 서두
    header_match = re.search(r'^(THE CONTRACTING MEMBER STATES,?)', preamble_text, re.IGNORECASE)
    if header_match:
        results.append({
            'type': '서두',
            'text': header_match.group(1).strip()
        })

    # CONSIDERING, RECALLING, WISHING 등 각 문단
    pattern = re.compile(
        r'(CONSIDERING|RECALLING|WISHING|HAVING|NOTING|DESIRING|RECOGNIZING|CONVINCED|AWARE)\s+that\s+(.*?)(?=(?:CONSIDERING|RECALLING|WISHING|HAVING|NOTING|DESIRING|RECOGNIZING|CONVINCED|AWARE)\s+that|HAVE AGREED AS FOLLOWS|$)',
        re.DOTALL | re.IGNORECASE
    )

    for match in pattern.finditer(preamble_text):
        keyword = match.group(1).upper()
        content = match.group(2).strip()
        # 끝의 세미콜론 제거
        content = re.sub(r'[;:]\s*$', '', content)
        # 줄바꿈을 공백으로 변환
        content = re.sub(r'\s+', ' ', content)

        results.append({
            'type': keyword,
            'text': f'{keyword} that {content}'
        })

    # HAVE AGREED AS FOLLOWS
    if 'HAVE AGREED AS FOLLOWS' in preamble_text:
        results.append({
            'type': '합의',
            'text': 'HAVE AGREED AS FOLLOWS:'
        })

    return results


def _parse_html_articles(text: str) -> list[dict]:
    """HTML 텍스트에서 조문을 파싱한다."""
    articles = []

    # 계층 구조 추출 (PART, CHAPTER)
    hierarchy = _extract_html_hierarchy(text)

    # Article 패턴: "Article N" + 제목 (선택)
    article_pattern = re.compile(
        r'\n(Article\s+\d+[a-z]*)\n(.*?)(?=\nArticle\s+\d+|$)',
        re.DOTALL | re.IGNORECASE
    )

    for match in article_pattern.finditer(text):
        article_id = match.group(1).strip()
        article_content = match.group(2).strip()

        # 조문 제목 추출 (첫 줄)
        lines = article_content.split('\n')
        title = ""
        content_start = 0

        if lines:
            first_line = lines[0].strip()
            # 첫 줄이 제목인지 확인 (숫자나 (a) 등으로 시작하지 않음)
            if first_line and not re.match(r'^[\d\(]', first_line):
                title = first_line
                content_start = 1

        # 본문 추출
        article_text = '\n'.join(lines[content_start:]).strip()

        # 현재 조문이 속한 계층 찾기
        article_pos = text.find(match.group(0))
        current_hierarchy = _find_hierarchy_at_position(hierarchy, article_pos)

        articles.append({
            'id': article_id,
            'title': title,
            'text': article_text,
            'hierarchy': current_hierarchy
        })

    return articles


def _extract_html_hierarchy(text: str) -> list[dict]:
    """HTML 텍스트에서 계층 구조(PART, CHAPTER 등)를 추출한다."""
    hierarchy = []

    # PART 패턴 - 더 유연하게 수정
    part_pattern = re.compile(
        r'(?:^|\n)(PART\s+[IVXLCDM]+)\s*(.*?)(?=\n\n|$)',
        re.MULTILINE
    )

    for match in part_pattern.finditer(text):
        part_num = match.group(1).strip()
        part_title_raw = match.group(2).strip()
        # 여러 줄에 걸친 제목일 수 있으므로 정리
        part_title = re.sub(r'\s+', ' ', part_title_raw).split('\n')[0]

        # CHAPTER나 Article이 아닌 경우만 제목으로 인식
        if not re.match(r'^(CHAPTER|Article)', part_title, re.IGNORECASE):
            hierarchy.append({
                'type': 'part',
                'title': f'{part_num} {part_title}'.strip() if part_title else part_num,
                'start_pos': match.start()
            })

    # CHAPTER 패턴 - 더 유연하게 수정
    chapter_pattern = re.compile(
        r'(?:^|\n)(CHAPTER\s+[IVXLCDM0-9]+)\s*(.*?)(?=\n\n|$)',
        re.MULTILINE
    )

    for match in chapter_pattern.finditer(text):
        chapter_num = match.group(1).strip()
        chapter_title_raw = match.group(2).strip()
        # 여러 줄에 걸친 제목일 수 있으므로 정리
        chapter_title = re.sub(r'\s+', ' ', chapter_title_raw).split('\n')[0]

        # Article이 아닌 경우만 제목으로 인식
        if not re.match(r'^Article', chapter_title, re.IGNORECASE):
            hierarchy.append({
                'type': 'chapter',
                'title': f'{chapter_num} {chapter_title}'.strip() if chapter_title else chapter_num,
                'start_pos': match.start()
            })

    # 위치 순서대로 정렬
    hierarchy.sort(key=lambda x: x['start_pos'])

    return hierarchy


def _find_hierarchy_at_position(hierarchy: list[dict], position: int) -> dict:
    """특정 위치에서의 계층 정보를 반환한다."""
    current_part = ""
    current_chapter = ""

    for h in hierarchy:
        if h['start_pos'] > position:
            break
        if h['type'] == 'part':
            current_part = h['title']
            current_chapter = ""  # 새 Part에서 Chapter 초기화
        elif h['type'] == 'chapter':
            current_chapter = h['title']

    return {
        'part': current_part,
        'chapter': current_chapter
    }


def parse_eu_html_to_dataframe(url: str) -> pd.DataFrame:
    """유럽 법령 HTML을 파싱하여 구조화된 DataFrame을 반환한다.

    Args:
        url: HTML 법령 URL

    Returns:
        DataFrame with columns: ['편', '장', '절', '조문번호', '조문제목', '항', '호', '목', '세목', '원문']
    """
    # HTML 파싱
    data = parse_eu_html(url)

    rows = []

    # 전문 추가
    for para in data['preamble']:
        rows.append({
            '편': '',
            '장': '',
            '절': '',
            '조문번호': '전문',
            '조문제목': para['type'],
            '항': '',
            '호': '',
            '목': '',
            '세목': '',
            '원문': para['text']
        })

    # 조문 추가
    for article in data['articles']:
        article_id = article['id']
        title = article['title']
        text = article['text']
        hierarchy = article['hierarchy']

        # 항/호 파싱
        # 1. 2. 3. 패턴으로 항 분리 (유럽 법령 스타일)
        para_pattern = re.compile(r'(?:^|\n)\s*(\d+)\.\s+(.*?)(?=(?:\n\s*\d+\.|$))', re.DOTALL | re.MULTILINE)
        paragraphs = list(para_pattern.finditer(text))

        if not paragraphs:
            # 항이 없는 경우 - (a), (b) 패턴만 확인
            # 여러 줄바꿈과 공백을 허용하는 패턴
            item_pattern = re.compile(r'\n\s*\(([a-z])\)\s*\n\s*(.*?)(?=\n\s*\([a-z]\)|$)', re.DOTALL)
            items = list(item_pattern.finditer(text))

            if not items:
                # 호도 없는 경우 전체를 하나로
                rows.append({
                    '편': hierarchy['part'],
                    '장': hierarchy['chapter'],
                    '절': '',
                    '조문번호': article_id,
                    '조문제목': title,
                    '항': '',
                    '호': '',
                    '목': '',
                    '세목': '',
                    '원문': text.strip()
                })
            else:
                # 호만 있는 경우
                # 첫 번째 호 이전 텍스트 (있으면 본문으로)
                first_item_start = items[0].start()
                intro_text = text[:first_item_start].strip()

                if intro_text:
                    rows.append({
                        '편': hierarchy['part'],
                        '장': hierarchy['chapter'],
                        '절': '',
                        '조문번호': article_id,
                        '조문제목': title,
                        '항': '',
                        '호': '',
                        '목': '',
                        '세목': '',
                        '원문': intro_text
                    })

                # 각 호
                for item_match in items:
                    item_letter = item_match.group(1)
                    item_text = item_match.group(2).strip()

                    rows.append({
                        '편': hierarchy['part'],
                        '장': hierarchy['chapter'],
                        '절': '',
                        '조문번호': article_id,
                        '조문제목': title,
                        '항': '',
                        '호': item_letter,
                        '목': '',
                        '세목': '',
                        '원문': item_text
                    })
        else:
            for para_match in paragraphs:
                para_num = para_match.group(1)
                para_text = para_match.group(2).strip()

                # (a), (b) 패턴으로 호 분리
                item_pattern = re.compile(r'\n\s*\(([a-z])\)\s*\n\s*(.*?)(?=\n\s*\([a-z]\)|$)', re.DOTALL)
                items = list(item_pattern.finditer(para_text))

                if not items:
                    # 호가 없는 경우
                    rows.append({
                        '편': hierarchy['part'],
                        '장': hierarchy['chapter'],
                        '절': '',
                        '조문번호': article_id,
                        '조문제목': title,
                        '항': para_num,
                        '호': '',
                        '목': '',
                        '세목': '',
                        '원문': para_text
                    })
                else:
                    # 항 내 호들
                    # 첫 번째 호 이전 텍스트
                    first_item_start = items[0].start()
                    para_intro = para_text[:first_item_start].strip()

                    if para_intro:
                        rows.append({
                            '편': hierarchy['part'],
                            '장': hierarchy['chapter'],
                            '절': '',
                            '조문번호': article_id,
                            '조문제목': title,
                            '항': para_num,
                            '호': '',
                            '목': '',
                            '세목': '',
                            '원문': para_intro
                        })

                    # 각 호
                    for item_match in items:
                        item_letter = item_match.group(1)
                        item_text = item_match.group(2).strip()

                        rows.append({
                            '편': hierarchy['part'],
                            '장': hierarchy['chapter'],
                            '절': '',
                            '조문번호': article_id,
                            '조문제목': title,
                            '항': para_num,
                            '호': item_letter,
                            '목': '',
                            '세목': '',
                            '원문': item_text
                        })

    return pd.DataFrame(rows)


def save_structured_to_excel(df: pd.DataFrame, output_path: str):
    """구조화된 DataFrame을 엑셀로 저장한다."""
    # 엑셀에서 허용하지 않는 제어 문자 제거
    def clean_for_excel(text):
        if not isinstance(text, str):
            return text
        import re
        return re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]', '', text)

    df_clean = df.copy()
    for col in df_clean.columns:
        if df_clean[col].dtype == 'object':
            df_clean[col] = df_clean[col].apply(clean_for_excel)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df_clean.to_excel(writer, index=False, sheet_name="법조문")

        worksheet = writer.sheets["법조문"]
        for idx, col in enumerate(df_clean.columns):
            max_length = max(
                df_clean[col].astype(str).map(len).max(),
                len(col)
            )
            worksheet.column_dimensions[chr(65 + idx)].width = min(max_length + 2, 50)


# ══════════════════════════════════════════════════════════════
# 중국 법령 HTML 파싱
# ══════════════════════════════════════════════════════════════

def parse_china_html(url: str) -> dict:
    """중국 법령 HTML을 파싱하여 구조화된 데이터를 반환한다.

    Args:
        url: 중국 법령 HTML URL (예: CNIPA 웹사이트)

    Returns:
        {
            'articles': [{'id': '第X条', 'title': '', 'text': '...', 'hierarchy': {'chapter': '第X章 ...'}}, ...]
        }
    """
    # HTML 다운로드
    response = requests.get(url)
    response.encoding = 'utf-8'
    html = response.text

    # BeautifulSoup으로 파싱
    soup = BeautifulSoup(html, 'html.parser')

    # 전체 텍스트 추출
    text = soup.get_text()

    # 조문 파싱
    articles = _parse_china_articles(text)

    return {
        'articles': articles
    }


def _parse_china_articles(text: str) -> list[dict]:
    """중국 법령 텍스트에서 조문을 파싱한다.

    중국 법령 구조:
    - 第X章: 장 제목
    - 第X条: 조문 번호
    - (一), (二), (三): 항목 번호
    """
    articles = []

    # 계층 구조 추출 (章)
    hierarchy = _extract_china_hierarchy(text)

    # 조문 패턴: 第X条 (X는 한자 숫자 또는 아라비아 숫자)
    # 한자 숫자: 一二三四五六七八九十百千
    article_pattern = re.compile(
        r'第([一二三四五六七八九十百千\d]+)条\s*(.*?)(?=第[一二三四五六七八九十百千\d]+条|$)',
        re.DOTALL
    )

    for match in article_pattern.finditer(text):
        article_num = match.group(1).strip()
        article_content = match.group(2).strip()

        article_id = f"第{article_num}条"

        # 현재 조문이 속한 장 찾기
        article_pos = match.start()
        current_chapter = _find_china_chapter_at_position(hierarchy, article_pos)

        articles.append({
            'id': article_id,
            'title': '',  # 중국법은 조문 제목이 없음
            'text': article_content,
            'hierarchy': {'chapter': current_chapter}
        })

    return articles


def _extract_china_hierarchy(text: str) -> list[dict]:
    """중국 법령 텍스트에서 계층 구조(章)를 추출한다."""
    hierarchy = []

    # 章 패턴: 第X章 제목
    chapter_pattern = re.compile(
        r'第([一二三四五六七八九十百千\d]+)章\s+([^\n第]+)',
        re.MULTILINE
    )

    for match in chapter_pattern.finditer(text):
        chapter_num = match.group(1).strip()
        chapter_title = match.group(2).strip()

        # 제목 정리 (공백 정규화)
        chapter_title = re.sub(r'\s+', ' ', chapter_title)

        hierarchy.append({
            'type': 'chapter',
            'title': f'第{chapter_num}章 {chapter_title}',
            'start_pos': match.start()
        })

    return hierarchy


def _find_china_chapter_at_position(hierarchy: list[dict], position: int) -> str:
    """특정 위치에서의 장(章) 정보를 반환한다."""
    current_chapter = ""

    for h in hierarchy:
        if h['start_pos'] > position:
            break
        if h['type'] == 'chapter':
            current_chapter = h['title']

    return current_chapter


def parse_china_html_to_dataframe(url: str) -> pd.DataFrame:
    """중국 법령 HTML을 파싱하여 구조화된 DataFrame을 반환한다.

    Args:
        url: 중국 법령 HTML URL

    Returns:
        DataFrame with columns: ['편', '장', '절', '조문번호', '조문제목', '항', '호', '목', '세목', '원문']
    """
    # HTML 파싱
    data = parse_china_html(url)

    rows = []

    # 조문 추가
    for article in data['articles']:
        article_id = article['id']
        text = article['text']
        chapter = article['hierarchy']['chapter']

        # (一), (二), (三) 패턴으로 항목 분리
        item_pattern = re.compile(r'[（\(]([一二三四五六七八九十]+)[）\)]\s*(.*?)(?=[（\(][一二三四五六七八九十]+[）\)]|$)', re.DOTALL)
        items = list(item_pattern.finditer(text))

        if not items:
            # 항목이 없는 경우 전체를 하나로
            rows.append({
                '편': '',
                '장': chapter,
                '절': '',
                '조문번호': article_id,
                '조문제목': '',
                '항': '',
                '호': '',
                '목': '',
                '세목': '',
                '원문': text
            })
        else:
            for item_match in items:
                item_num = item_match.group(1)
                item_text = item_match.group(2).strip()

                rows.append({
                    '편': '',
                    '장': chapter,
                    '절': '',
                    '조문번호': article_id,
                    '조문제목': '',
                    '항': item_num,
                    '호': '',
                    '목': '',
                    '세목': '',
                    '원문': item_text
                })

    return pd.DataFrame(rows)



# ══════════════════════════════════════════════════════════════
# 뉴질랜드 법령 HTML 파싱
# ══════════════════════════════════════════════════════════════

def _nz_clean_text(text: str) -> str:
    """non-breaking space 등 특수 공백을 일반 공백으로 치환."""
    return text.replace('\xa0', ' ').replace('\u200b', '').strip()


def parse_nz_html_to_dataframe(url: str) -> pd.DataFrame:
    """뉴질랜드 법령 HTML을 파싱하여 구조화된 DataFrame을 반환한다.

    DOM 기반 파싱: h2.part, h3.subpart, h5.prov, div.subprov, div.label-para 구조 활용.

    Args:
        url: 뉴질랜드 법령 HTML URL

    Returns:
        DataFrame with columns: ['편', '장', '절', '조문번호', '조문제목', '항', '호', '목', '세목', '원문']
    """
    _nz_headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    response = requests.get(url, headers=_nz_headers)
    response.encoding = 'utf-8'
    soup = BeautifulSoup(response.text, 'html.parser')

    # TOC 영역 제거
    for toc in soup.find_all(class_=re.compile(r'toc', re.IGNORECASE)):
        toc.decompose()
    # history (개정이력) 영역 제거
    for hist in soup.find_all(class_='history'):
        hist.decompose()

    rows = []
    current_part = ""
    current_subpart = ""
    current_schedule = ""  # 부칙 영역 추적
    current_heading = ""  # 소제목 (숫자 없는 제목)

    # h2.part → Part, h2.schedule → 부칙, h3.subpart → Subpart, h3/h4 (일반) → 소제목, h5.prov → Section
    for elem in soup.find_all(['h2', 'h3', 'h4', 'h5']):
        classes = elem.get('class', [])

        if elem.name == 'h2' and 'schedule' in classes:
            # Schedule (부칙) 제목
            label = elem.find('span', class_='label')
            if label:
                sched_num = _nz_clean_text(label.get_text(strip=True))
                rest = _nz_clean_text(elem.get_text(strip=True))[len(sched_num):]
                current_schedule = f"[Schedule] {sched_num} {rest}".strip()
            else:
                current_schedule = f"[Schedule] {_nz_clean_text(elem.get_text(strip=True))}"
            current_part = current_schedule
            current_subpart = ""
            current_heading = ""

        elif elem.name == 'h2' and 'part' in classes:
            # Part 제목 (예: "Part 1Preliminary")
            label = elem.find('span', class_='label')
            if label:
                part_num = _nz_clean_text(label.get_text(strip=True))
                rest = _nz_clean_text(elem.get_text(strip=True))[len(part_num):]
                part_title = f"{part_num} {rest}".strip()
            else:
                part_title = _nz_clean_text(elem.get_text(strip=True))
            # 부칙 영역 내 Part는 접두사 추가
            current_part = f"{current_schedule} > {part_title}" if current_schedule else part_title
            current_subpart = ""
            current_heading = ""

        elif elem.name == 'h3' and 'subpart' in classes:
            # Subpart 제목
            current_subpart = _nz_clean_text(elem.get_text(strip=True))
            current_heading = ""

        elif (elem.name in ['h3', 'h4']) and ('subpart' not in classes and 'part' not in classes):
            # 일반 제목 (소제목) - Part나 Subpart가 아닌 h3/h4
            # 예: "Liability of Commissioner and others", "Registrable designs and proceedings for registration"
            heading_text = _nz_clean_text(elem.get_text(strip=True))
            # 너무 짧거나 숫자로 시작하는 것은 제외
            if len(heading_text) > 5 and not heading_text[0].isdigit():
                current_heading = heading_text

        elif elem.name == 'h5' and 'prov' in classes:
            # Section (조문)
            label = elem.find('span', class_='label')
            if not label:
                continue
            sec_num = _nz_clean_text(label.get_text(strip=True))
            sec_title = _nz_clean_text(elem.get_text(strip=True))[len(sec_num):].strip()
            section_id = f"Section {sec_num}"

            # 장 결정: Subpart가 있으면 Subpart, 없으면 소제목(heading)
            chapter = current_subpart if current_subpart else current_heading

            # prov-body 찾기
            body = elem.find_next_sibling('div', class_='prov-body')
            if not body:
                rows.append({
                    '편': current_part, '장': chapter, '절': '',
                    '조문번호': section_id, '조문제목': sec_title,
                    '항': '', '호': '', '목': '', '세목': '',
                    '원문': ''
                })
                continue

            # prov-body 내 subprov (항) 분석
            subprovs = body.find_all('div', class_='subprov', recursive=False)

            if not subprovs:
                # subprov 없이 바로 본문
                text = _nz_clean_text(body.get_text(strip=True))
                rows.append({
                    '편': current_part, '장': chapter, '절': '',
                    '조문번호': section_id, '조문제목': sec_title,
                    '항': '', '호': '', '목': '', '세목': '',
                    '원문': text
                })
                continue

            for subprov_div in subprovs:
                # 항 번호 추출: p.subprov > span.label
                para_label = subprov_div.find('p', class_='subprov')
                para_num = ""
                if para_label:
                    label_span = para_label.find('span', class_='label')
                    if label_span:
                        raw = label_span.get_text(strip=True)
                        # (1) → 1
                        m = re.match(r'\((\d+)\)', raw)
                        if m:
                            para_num = m.group(1)

                # 항 내부의 para div
                para_div = subprov_div.find('div', class_='para', recursive=False)
                if not para_div:
                    text = _nz_clean_text(subprov_div.get_text(strip=True))
                    # 항 번호 제거
                    if para_num:
                        text = re.sub(r'^\(' + para_num + r'\)\s*', '', text)
                    rows.append({
                        '편': current_part, '장': chapter, '절': '',
                        '조문번호': section_id, '조문제목': sec_title,
                        '항': para_num, '호': '', '목': '', '세목': '',
                        '원문': text
                    })
                    continue

                _parse_nz_para_div(rows, current_part, chapter,
                                   section_id, sec_title, para_num, para_div)

    return pd.DataFrame(rows)


def _parse_nz_para_div(rows, part, subpart, section_id, title, para_num, para_div):
    """뉴질랜드 법령 div.para 내부를 파싱하여 호/목을 분리."""
    # div.para 직계 자식에서 p.text와 div.label-para 찾기
    label_paras = para_div.find_all('div', class_='label-para', recursive=False)

    if not label_paras:
        # 호가 없는 경우 - 본문 텍스트 수집 (def-para 정의 조항 포함)
        texts = []
        for child in para_div.children:
            if hasattr(child, 'name'):
                if child.name == 'p' and 'text' in child.get('class', []):
                    texts.append(_nz_clean_text(child.get_text(strip=True)))
                elif child.name == 'div' and 'def-para' in child.get('class', []):
                    # div.def-para: NZ 법령의 정의 조항 (label-para 대신 사용)
                    # separator=' '로 inline 요소(dfn, a 등) 사이 공백 보존
                    def_text = re.sub(r'\s+', ' ', child.get_text(separator=' ')).strip()
                    def_text = _nz_clean_text(def_text)
                    if def_text:
                        texts.append(def_text)
        text = ' '.join(texts) if texts else _nz_clean_text(para_div.get_text(strip=True))
        if text:
            rows.append({
                '편': part, '장': subpart, '절': '',
                '조문번호': section_id, '조문제목': title,
                '항': para_num, '호': '', '목': '', '세목': '',
                '원문': text
            })
        return

    # 호 이전 도입 텍스트
    intro_texts = []
    for child in para_div.children:
        if hasattr(child, 'name'):
            if child.name == 'div' and 'label-para' in child.get('class', []):
                break
            if child.name == 'p' and 'text' in child.get('class', []):
                intro_texts.append(_nz_clean_text(child.get_text(strip=True)))
    intro = ' '.join(intro_texts)
    if intro:
        rows.append({
            '편': part, '장': subpart, '절': '',
            '조문번호': section_id, '조문제목': title,
            '항': para_num, '호': '', '목': '', '세목': '',
            '원문': intro
        })

    # 각 호 (a), (b), ... 처리
    for lp_div in label_paras:
        h5_label = lp_div.find('h5', class_='label-para')
        if not h5_label:
            continue
        label_span = h5_label.find('span', class_='label')
        if not label_span:
            continue
        raw_label = label_span.get_text(strip=True)

        # (a)→a, (i)→i 형태
        m = re.match(r'\(([a-z]+)\)', raw_label)
        if not m:
            continue
        letter = m.group(1)

        # 호인지 목인지 판별: 단일 알파벳(a-z) = 호, 로마숫자(i,ii,iii...) = 목
        is_roman = re.match(r'^[ivxlc]+$', letter) and letter not in ('a', 'b', 'c', 'd', 'e', 'f',
            'g', 'h', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'w', 'y', 'z')

        # 호의 내부 para div
        inner_para = lp_div.find('div', class_='para')
        if not inner_para:
            continue

        # 호 안에 하위 label-para (목)가 있는지 확인
        sub_label_paras = inner_para.find_all('div', class_='label-para', recursive=False)

        if sub_label_paras and not is_roman:
            # 호(a) 안에 목(i)(ii)가 있음
            # 호 도입 텍스트
            ho_intro_texts = []
            for child in inner_para.children:
                if hasattr(child, 'name'):
                    if child.name == 'div' and 'label-para' in child.get('class', []):
                        break
                    if child.name == 'p' and 'text' in child.get('class', []):
                        ho_intro_texts.append(_nz_clean_text(child.get_text(strip=True)))
            ho_intro = ' '.join(ho_intro_texts)
            if ho_intro:
                rows.append({
                    '편': part, '장': subpart, '절': '',
                    '조문번호': section_id, '조문제목': title,
                    '항': para_num, '호': letter, '목': '', '세목': '',
                    '원문': ho_intro
                })

            # 각 목(i)(ii) 처리
            for sub_lp in sub_label_paras:
                sub_h5 = sub_lp.find('h5', class_='label-para')
                if not sub_h5:
                    continue
                sub_span = sub_h5.find('span', class_='label')
                if not sub_span:
                    continue
                sub_raw = sub_span.get_text(strip=True)
                sub_m = re.match(r'\(([ivxlc]+)\)', sub_raw)
                if not sub_m:
                    continue
                sub_letter = sub_m.group(1)

                sub_inner = sub_lp.find('div', class_='para')
                if not sub_inner:
                    sub_text = _nz_clean_text(sub_lp.get_text(strip=True))
                    # label 제거
                    sub_text = re.sub(r'^\([ivxlc]+\)\s*', '', sub_text)
                    rows.append({
                        '편': part, '장': subpart, '절': '',
                        '조문번호': section_id, '조문제목': title,
                        '항': para_num, '호': letter, '목': sub_letter, '세목': '',
                        '원문': sub_text
                    })
                    continue

                # 목 안에 세목(A)(B)가 있는지 확인
                subsub_label_paras = sub_inner.find_all('div', class_='label-para', recursive=False)

                if subsub_label_paras:
                    # 목 도입 텍스트
                    mok_intro_texts = []
                    for child in sub_inner.children:
                        if hasattr(child, 'name'):
                            if child.name == 'div' and 'label-para' in child.get('class', []):
                                break
                            if child.name == 'p' and 'text' in child.get('class', []):
                                mok_intro_texts.append(_nz_clean_text(child.get_text(strip=True)))
                    mok_intro = ' '.join(mok_intro_texts)
                    if mok_intro:
                        rows.append({
                            '편': part, '장': subpart, '절': '',
                            '조문번호': section_id, '조문제목': title,
                            '항': para_num, '호': letter, '목': sub_letter, '세목': '',
                            '원문': mok_intro
                        })

                    # 각 세목(A)(B) 처리
                    for subsub_lp in subsub_label_paras:
                        subsub_h5 = subsub_lp.find('h5', class_='label-para')
                        if not subsub_h5:
                            continue
                        subsub_span = subsub_h5.find('span', class_='label')
                        if not subsub_span:
                            continue
                        subsub_raw = subsub_span.get_text(strip=True)
                        # (A), (B) 등 대문자 패턴
                        subsub_m = re.match(r'\(([A-Z])\)', subsub_raw)
                        if not subsub_m:
                            continue
                        subsub_letter = subsub_m.group(1)

                        subsub_inner = subsub_lp.find('div', class_='para')
                        subsub_text = _nz_clean_text(subsub_inner.get_text(strip=True)) if subsub_inner else _nz_clean_text(subsub_lp.get_text(strip=True))
                        # label 제거
                        subsub_text = re.sub(r'^\([A-Z]\)\s*', '', subsub_text)

                        rows.append({
                            '편': part, '장': subpart, '절': '',
                            '조문번호': section_id, '조문제목': title,
                            '항': para_num, '호': letter, '목': sub_letter, '세목': f'({subsub_letter})',
                            '원문': subsub_text
                        })
                else:
                    # 세목 없이 목 텍스트만
                    sub_text = _nz_clean_text(sub_inner.get_text(strip=True))
                    # label 제거
                    sub_text = re.sub(r'^\([ivxlc]+\)\s*', '', sub_text)

                    rows.append({
                        '편': part, '장': subpart, '절': '',
                        '조문번호': section_id, '조문제목': title,
                        '항': para_num, '호': letter, '목': sub_letter, '세목': '',
                        '원문': sub_text
                    })
        else:
            # 하위 목 없이 호 텍스트만
            text = _nz_clean_text(inner_para.get_text(strip=True))
            rows.append({
                '편': part, '장': subpart, '절': '',
                '조문번호': section_id, '조문제목': title,
                '항': para_num, '호': letter, '목': '', '세목': '',
                '원문': text
            })


# ══════════════════════════════════════════════════════════════
# 독일 법령 HTML 파싱 (gesetze-im-internet.de)
# ══════════════════════════════════════════════════════════════

def parse_germany_html_to_dataframe(url: str) -> pd.DataFrame:
    """독일 법령 HTML을 파싱하여 구조화된 DataFrame을 반환한다.

    대상 사이트: https://www.gesetze-im-internet.de/

    HTML 구조:
      - div.jnnorm → 각 조문/섹션 블록
      - h2 → Abschnitt(편/장) 제목
      - h3 > span.jnenbez → § 번호
      - div.jurAbsatz → 항(Absatz) 내용
      - dl > dt/dd → 호(Nummer) 목록

    Args:
        url: 독일 법령 HTML URL

    Returns:
        DataFrame with columns: ['편', '장', '절', '조문번호', '조문제목', '항', '호', '목', '세목', '원문']
    """
    response = requests.get(url)
    response.encoding = 'utf-8'
    soup = BeautifulSoup(response.text, 'html.parser')

    norms = soup.find_all('div', class_='jnnorm')
    if not norms:
        raise ValueError("jnnorm 영역을 찾을 수 없습니다.")

    rows = []
    current_teil = ''       # 편 (Teil / Erster Abschnitt 등 최상위)
    current_abschnitt = ''  # 장 (Abschnitt / Unterabschnitt)

    for norm in norms:
        # 계층 제목 (h2)
        h2 = norm.find('h2')
        if h2:
            spans = h2.find_all('span')
            if spans:
                heading = ' '.join(s.get_text(strip=True) for s in spans).strip()
            else:
                heading = h2.get_text(strip=True)
            if not heading:
                continue
            # Teil(편) vs Abschnitt(장) 판별
            # Teil N ..., Erster Abschnitt ... 등 → 편
            # Abschnitt N ..., 숫자. 제목 등 → 장
            first_span = spans[0].get_text(strip=True) if spans else heading
            if first_span.startswith('Teil') or re.match(
                    r'^(Erster|Zweiter|Dritter|Vierter|Fünfter|Sechster|Siebenter|Achter|Neunter|Zehnter|Elfter|Zwölfter)\s',
                    first_span):
                current_teil = heading
                current_abschnitt = ''
            else:
                current_abschnitt = heading
            continue

        # § 조문 (h3)
        h3 = norm.find('h3')
        if not h3:
            continue

        enbez = h3.find('span', class_='jnenbez')
        if not enbez:
            continue
        article_id = enbez.get_text(strip=True)
        # § 앞 불필요 공백/특수문자 제거
        article_id = re.sub(r'^[\s\u00a0\u200b]+', '', article_id).strip()

        # (weggefallen) 조문 건너뛰기
        entitel = h3.find('span', class_='jnentitel')
        article_title = entitel.get_text(strip=True) if entitel else ''
        if '(weggefallen)' in article_title:
            continue

        # 항(Absatz) 추출
        absaetze = norm.find_all('div', class_='jurAbsatz')
        if not absaetze:
            rows.append({
                '편': current_teil, '장': current_abschnitt, '절': '',
                '조문번호': article_id, '조문제목': article_title,
                '항': '', '호': '', '목': '', '세목': '',
                '원문': ''
            })
            continue

        for abs_idx, absatz in enumerate(absaetze, 1):
            # dl > dt/dd 구조 (호 목록) 확인
            dl = absatz.find('dl')
            if dl:
                # dl 이전 텍스트 (항 본문)
                intro_parts = []
                for child in absatz.children:
                    if child == dl:
                        break
                    text = child.get_text() if hasattr(child, 'get_text') else str(child)
                    text = text.strip()
                    if text:
                        intro_parts.append(text)
                # (N) 항번호 제거
                intro = ' '.join(intro_parts)
                intro = re.sub(r'^\(\d+[a-z]?\)\s*', '', intro).strip()

                abs_num = str(abs_idx)
                if intro:
                    rows.append({
                        '편': current_teil, '장': current_abschnitt, '절': '',
                        '조문번호': article_id, '조문제목': article_title,
                        '항': abs_num, '호': '', '목': '', '세목': '',
                        '원문': intro
                    })

                # 호 추출
                dts = dl.find_all('dt')
                dds = dl.find_all('dd')
                for dt, dd in zip(dts, dds):
                    num = dt.get_text(strip=True).rstrip('.')
                    dd_text = dd.get_text(strip=True)
                    rows.append({
                        '편': current_teil, '장': current_abschnitt, '절': '',
                        '조문번호': article_id, '조문제목': article_title,
                        '항': abs_num, '호': num, '목': '', '세목': '',
                        '원문': dd_text
                    })

                # dl 이후 텍스트 (있으면)
                after_dl = []
                found_dl = False
                for child in absatz.children:
                    if child == dl:
                        found_dl = True
                        continue
                    if found_dl:
                        text = child.get_text() if hasattr(child, 'get_text') else str(child)
                        text = text.strip()
                        if text:
                            after_dl.append(text)
                if after_dl:
                    rows.append({
                        '편': current_teil, '장': current_abschnitt, '절': '',
                        '조문번호': article_id, '조문제목': article_title,
                        '항': abs_num, '호': '', '목': '', '세목': '',
                        '원문': ' '.join(after_dl)
                    })
            else:
                # 일반 항 (호 없음)
                text = absatz.get_text(strip=True)
                text = re.sub(r'^\(\d+[a-z]?\)\s*', '', text).strip()
                if not text:
                    continue
                rows.append({
                    '편': current_teil, '장': current_abschnitt, '절': '',
                    '조문번호': article_id, '조문제목': article_title,
                    '항': str(abs_idx), '호': '', '목': '', '세목': '',
                    '원문': text
                })

    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════
# 러시아 법령 HTML 파싱 (rospatent.gov.ru)
# ══════════════════════════════════════════════════════════════

def parse_russia_html_to_dataframe(url: str) -> pd.DataFrame:
    """러시아 민법 4부(지식재산권법) HTML을 파싱하여 구조화된 DataFrame을 반환한다.

    대상 사이트: https://rospatent.gov.ru/en/documents/...

    HTML 구조:
      - h2.h2 → Chapter 제목 (장)
      - h2 (no class) → § Section 제목 (절)
      - <p><strong><em>Article NNNN.</em> Title</strong></p> → 조문
      - <p>1. ... → 항(paragraph)
      - <p>1) ... → 호(subparagraph)

    Args:
        url: 러시아 법령 HTML URL

    Returns:
        DataFrame with columns: ['편', '장', '절', '조문번호', '조문제목', '항', '호', '목', '세목', '원문']
    """
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    response = requests.get(url, timeout=30, verify=False)
    response.encoding = 'utf-8'
    soup = BeautifulSoup(response.text, 'html.parser')

    content = soup.find('div', class_='col-dm-69')
    if not content:
        raise ValueError("본문 영역(col-dm-69)을 찾을 수 없습니다.")

    rows = []
    current_chapter = ''
    current_section = ''
    current_article_id = ''
    current_article_title = ''
    current_para_num = ''  # 직전 항번호 (호에 연결용)

    # 본문의 h2와 p를 순서대로 순회
    for elem in content.find_all(['h2', 'p']):
        if elem.name == 'h2':
            text = elem.get_text(strip=True)
            classes = elem.get('class', [])
            if 'h2' in classes:
                # Chapter (장)
                current_chapter = text
                current_section = ''
            elif text.startswith('§'):
                # § Section (절)
                current_section = text
            elif text.startswith('Section'):
                # Section VII 등 (편)
                current_chapter = text
                current_section = ''
            continue

        # p 태그 처리
        text = elem.get_text(strip=True)
        if not text:
            continue

        # Article 시작 감지
        strong = elem.find('strong')
        if strong and 'Article' in strong.get_text():
            raw = strong.get_text(strip=True)
            # "Article 1225.Protected Results..." 또는 "Article 1225. Protected Results..."
            m = re.match(r'(Article\s+\d+[.\s]*)\s*(.*)', raw)
            if m:
                current_article_id = m.group(1).rstrip('. ').strip()
                current_article_title = m.group(2).strip()
                current_para_num = ''
            continue

        if not current_article_id:
            continue

        # 항/호 판별
        para_match = re.match(r'^(\d+)\.\s*(.*)', text, re.DOTALL)
        sub_match = re.match(r'^(\d+(?:\.\d+)?)\)\s*(.*)', text, re.DOTALL)

        if sub_match:
            # 호: "1)", "2)", "14.1)" 등 → 직전 항번호 유지
            rows.append({
                '편': '', '장': current_chapter, '절': current_section,
                '조문번호': current_article_id, '조문제목': current_article_title,
                '항': current_para_num, '호': sub_match.group(1), '목': '', '세목': '',
                '원문': sub_match.group(2).strip()
            })
        elif para_match:
            # 항: "1.", "2." 등
            current_para_num = para_match.group(1)
            rows.append({
                '편': '', '장': current_chapter, '절': current_section,
                '조문번호': current_article_id, '조문제목': current_article_title,
                '항': current_para_num, '호': '', '목': '', '세목': '',
                '원문': para_match.group(2).strip()
            })
        else:
            # 항번호 없는 본문
            rows.append({
                '편': '', '장': current_chapter, '절': current_section,
                '조문번호': current_article_id, '조문제목': current_article_title,
                '항': '', '호': '', '목': '', '세목': '',
                '원문': text
            })

    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════
# 대만 법령 HTML 파싱 (law.moj.gov.tw 영문판)
# ══════════════════════════════════════════════════════════════

def parse_taiwan_html_to_dataframe(url: str) -> pd.DataFrame:
    """대만 법령 HTML(영문)을 파싱하여 구조화된 DataFrame을 반환한다.

    대상 사이트: https://law.moj.gov.tw/ENG/LawClass/LawAll.aspx?pcode=...

    HTML 구조:
      - div.law-reg-content 내부
      - div.h3.char-2 → Chapter 제목
      - div.h3.char-3 → Section 제목
      - div.row > div.col-no (Article N) + div.col-data (조문 내용)

    Args:
        url: 대만 법령 영문 HTML URL

    Returns:
        DataFrame with columns: ['편', '장', '절', '조문번호', '조문제목', '항', '호', '목', '세목', '원문']
    """
    response = requests.get(url)
    response.encoding = 'utf-8'
    soup = BeautifulSoup(response.text, 'html.parser')

    content = soup.find(class_='law-reg-content')
    if not content:
        raise ValueError("law-reg-content 영역을 찾을 수 없습니다.")

    rows = []
    current_chapter = ''
    current_section = ''

    for child in content.children:
        if not hasattr(child, 'name') or not child.name:
            continue

        classes = child.get('class', [])

        # Chapter / Section 제목
        if 'h3' in classes:
            heading_text = child.get_text(strip=True)
            if 'char-2' in classes:
                current_chapter = heading_text
                current_section = ''
            elif 'char-3' in classes:
                current_section = heading_text
            continue

        # Article row
        if 'row' not in classes:
            continue

        col_no = child.find('div', class_='col-no')
        col_data = child.find('div', class_='col-data')
        if not col_no or not col_data:
            continue

        article_id = col_no.get_text(strip=True)

        # col-data에서 본문 추출
        # 대만 법령은 조문 제목이 없고 바로 본문으로 시작
        data_parts = []
        for elem in col_data.children:
            if hasattr(elem, 'name') and elem.name == 'br':
                continue
            text = elem.get_text() if hasattr(elem, 'name') else str(elem)
            text = text.strip()
            if text:
                data_parts.append(text)

        article_title = ''  # 대만 법령은 조문 제목 없음
        body_text = '\n'.join(data_parts) if data_parts else ''

        # 항(Paragraph) 분리: 줄바꿈으로 구분된 문단들
        # 호(Subparagraph) 분리: "1.", "2." 등 숫자 패턴
        _parse_taiwan_article(rows, current_chapter, current_section,
                              article_id, article_title, body_text)

    return pd.DataFrame(rows)


def _parse_taiwan_article(rows: list, chapter: str, section: str,
                          article_id: str, title: str, body: str):
    """대만 조문 하나를 항/호 단위로 분해하여 rows에 추가한다."""

    if not body.strip():
        rows.append({
            '편': '', '장': chapter, '절': section,
            '조문번호': article_id, '조문제목': title,
            '항': '', '호': '', '목': '', '세목': '',
            '원문': title
        })
        return

    lines = [ln.strip() for ln in body.split('\n') if ln.strip()]

    # 호 패턴: "1.", "2." 등으로 시작하는 줄
    subpara_pattern = re.compile(r'^(\d+)\.\s+(.*)')

    # 먼저 호의 시작 위치를 모두 찾기
    subpara_positions = []
    for i, line in enumerate(lines):
        m = subpara_pattern.match(line)
        if m:
            subpara_positions.append((i, m.group(1), m.group(2)))

    if not subpara_positions:
        # 호가 없으면 전체를 하나의 항으로
        rows.append({
            '편': '', '장': chapter, '절': section,
            '조문번호': article_id, '조문제목': title,
            '항': '1', '호': '', '목': '', '세목': '',
            '원문': ' '.join(lines)
        })
        return

    # 첫 번째 호 이전의 도입부 (있으면 첫 번째 항 본문)
    first_subpara_idx = subpara_positions[0][0]
    if first_subpara_idx > 0:
        intro_lines = lines[:first_subpara_idx]
        rows.append({
            '편': '', '장': chapter, '절': section,
            '조문번호': article_id, '조문제목': title,
            '항': '1', '호': '', '목': '', '세목': '',
            '원문': ' '.join(intro_lines)
        })

    # 각 호 처리 (다음 호까지의 모든 줄을 수집)
    for idx, (pos, sub_num, first_line) in enumerate(subpara_positions):
        # 다음 호의 시작 위치
        next_pos = subpara_positions[idx + 1][0] if idx + 1 < len(subpara_positions) else len(lines)

        # 현재 호부터 다음 호 전까지의 모든 줄 수집
        sub_lines = [first_line]  # 첫 줄의 나머지 텍스트
        for j in range(pos + 1, next_pos):
            sub_lines.append(lines[j])

        sub_text = ' '.join(sub_lines)

        rows.append({
            '편': '', '장': chapter, '절': section,
            '조문번호': article_id, '조문제목': title,  # 조문 제목 추가
            '항': '1', '호': sub_num, '목': '', '세목': '',
            '원문': sub_text
        })


# ══════════════════════════════════════════════════════════════
# 일본 법령 HTML 파싱
# ══════════════════════════════════════════════════════════════

def parse_japan_html(file_path: str) -> dict:
    """일본 법령 HTML 파일을 파싱하여 구조화된 데이터를 반환한다."""
    pass


# ══════════════════════════════════════════════════════════════
# 홍콩 법령 HTML 파싱
# ══════════════════════════════════════════════════════════════

def parse_hongkong_html_to_dataframe(url: str) -> pd.DataFrame:
    """홍콩 법령 HTML을 파싱하여 구조화된 DataFrame을 반환한다.

    대상 사이트: https://www.elegislation.gov.hk/

    HTML 구조:
      - section 태그로 조문 구분
      - data-section 속성에 조문 번호
      - h4/h5 태그로 Part/Division 등 계층 구분
      - p 태그로 조문 내용 포함

    Args:
        url: 홍콩 법령 HTML URL

    Returns:
        DataFrame with columns: ['편', '장', '절', '조문번호', '조문제목', '항', '호', '목', '세목', '원문']
    """
    response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
    response.encoding = 'utf-8'
    soup = BeautifulSoup(response.text, 'html.parser')

    rows = []
    current_part = ""
    current_division = ""

    # 법령 본문 찾기
    main_content = soup.find('div', class_='content') or soup.find('div', id='content') or soup

    for elem in main_content.find_all(['h2', 'h3', 'h4', 'section', 'div']):
        classes = elem.get('class', [])
        elem_class_str = ' '.join(classes) if classes else ''

        # Part/Division 제목 감지
        if elem.name in ['h2', 'h3', 'h4']:
            text = elem.get_text(strip=True)
            text_upper = text.upper()

            if 'PART' in text_upper:
                current_part = text
                current_division = ""
            elif 'DIVISION' in text_upper or 'SUBDIVISION' in text_upper:
                current_division = text
            continue

        # Section (조문) 감지
        section_num = elem.get('data-section') or elem.get('id')
        
        if not section_num:
            # section 태그가 아니면 ID나 클래스에서 section 번호 찾기
            if 'section' in elem_class_str.lower() or elem.name == 'section':
                # 텍스트에서 section 번호 추출
                text = elem.get_text(strip=True)
                match = re.match(r'(\d+[A-Z]?)\.\s*(.+)', text)
                if match:
                    section_num = match.group(1)
                else:
                    continue
            else:
                continue

        # Section 번호 정리
        section_id = f"Section {section_num}" if not section_num.startswith('Section') else section_num

        # 조문 제목과 내용 추출
        heading = elem.find(['h5', 'h6', 'strong', 'b'])
        if heading:
            section_title = heading.get_text(strip=True)
            # 제목 뒤의 번호 제거
            section_title = re.sub(r'^\d+[A-Z]?\.\s*', '', section_title)
        else:
            section_title = ""

        # 조문 내용 추출
        paragraphs = elem.find_all('p')
        if not paragraphs:
            # p 태그가 없으면 전체 텍스트 사용
            content_text = elem.get_text(strip=True)
            # 제목 부분 제거
            if section_title:
                content_text = content_text.replace(section_title, '', 1).strip()
        else:
            content_parts = []
            for p in paragraphs:
                p_text = p.get_text(strip=True)
                if p_text:
                    content_parts.append(p_text)
            content_text = ' '.join(content_parts)

        if not content_text:
            continue

        # 항/호/목 파싱
        items = _parse_hongkong_items(content_text)

        if items:
            for item in items:
                rows.append({
                    '편': current_part,
                    '장': current_division,
                    '절': '',
                    '조문번호': section_id,
                    '조문제목': section_title,
                    '항': item.get('subsection', ''),
                    '호': item.get('para', ''),
                    '목': item.get('subpara', ''),
                    '세목': '',
                    '원문': item['text']
                })
        else:
            # 항목이 없으면 전체 내용을 하나의 행으로
            rows.append({
                '편': current_part,
                '장': current_division,
                '절': '',
                '조문번호': section_id,
                '조문제목': section_title,
                '항': '',
                '호': '',
                '목': '',
                '세목': '',
                '원문': content_text
            })

    df = pd.DataFrame(rows)
    return df


def _parse_hongkong_items(text: str) -> list[dict]:
    """홍콩 법령 조문 내용에서 항목을 파싱한다.

    홍콩 법령 항목 형식:
      - (1), (2), (3) → subsection (항)
      - (a), (b), (c) → paragraph (호)
      - (i), (ii), (iii) → subparagraph (목)

    Returns:
        [{'subsection': '(1)', 'para': '', 'subpara': '', 'text': '...'}, ...]
    """
    items = []

    # (1), (2), (3) 형식의 subsection 찾기
    subsection_pattern = re.compile(r'\((\d+)\)\s+(.+?)(?=\(\d+\)\s+|\Z)', re.DOTALL)
    subsection_matches = list(subsection_pattern.finditer(text))

    if subsection_matches:
        for match in subsection_matches:
            subsection_num = f"({match.group(1)})"
            subsection_text = match.group(2).strip()

            # 하위 paragraph (a), (b), (c) 찾기
            para_items = _parse_hongkong_paragraphs(subsection_text)

            if para_items:
                for para_item in para_items:
                    para_item['subsection'] = subsection_num
                    items.append(para_item)
            else:
                items.append({
                    'subsection': subsection_num,
                    'para': '',
                    'subpara': '',
                    'text': subsection_text
                })
        return items

    # subsection이 없으면 paragraph만 찾기
    para_items = _parse_hongkong_paragraphs(text)
    if para_items:
        return para_items

    return []


def _parse_hongkong_paragraphs(text: str) -> list[dict]:
    """홍콩 법령에서 (a), (b), (c) 및 (i), (ii), (iii) 항목을 파싱한다."""
    items = []

    # (a), (b), (c) 형식의 paragraph 찾기
    para_pattern = re.compile(r'\(([a-z])\)\s+(.+?)(?=\([a-z]\)\s+|\Z)', re.DOTALL)
    para_matches = list(para_pattern.finditer(text))

    if para_matches:
        for match in para_matches:
            para_letter = f"({match.group(1)})"
            para_text = match.group(2).strip()

            # 하위 subparagraph (i), (ii), (iii) 찾기
            subpara_items = _parse_hongkong_subparagraphs(para_text)

            if subpara_items:
                for subpara_item in subpara_items:
                    subpara_item['para'] = para_letter
                    items.append(subpara_item)
            else:
                items.append({
                    'subsection': '',
                    'para': para_letter,
                    'subpara': '',
                    'text': para_text
                })
        return items

    # paragraph가 없으면 subparagraph만 찾기
    subpara_items = _parse_hongkong_subparagraphs(text)
    if subpara_items:
        return subpara_items

    return []


def _parse_hongkong_subparagraphs(text: str) -> list[dict]:
    """홍콩 법령에서 (i), (ii), (iii) 항목을 파싱한다."""
    items = []

    # (i), (ii), (iii), (iv), (v) 형식의 subparagraph 찾기
    # 로마숫자 패턴
    roman_pattern = re.compile(r'\((i{1,3}|iv|v|vi{0,3}|ix|x)\)\s+(.+?)(?=\((?:i{1,3}|iv|v|vi{0,3}|ix|x)\)\s+|\Z)', re.DOTALL)
    roman_matches = list(roman_pattern.finditer(text))

    if roman_matches:
        for match in roman_matches:
            subpara_roman = f"({match.group(1)})"
            subpara_text = match.group(2).strip()

            items.append({
                'subsection': '',
                'para': '',
                'subpara': subpara_roman,
                'text': subpara_text
            })

    return items

