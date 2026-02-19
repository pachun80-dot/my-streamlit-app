"""홍콩 법령 파서 (RTF 전용)

홍콩 특허법은 RTF 형식으로 제공됩니다.
구조:
- Part N: 편
- Division N—: 장/절
- N.\t제목: 섹션 (조문)
- (1)\t내용: 항 (subsection)
- (a)\t내용: 호 (paragraph)
"""
import os
import re
from parsers.base import BaseParser


class HongkongParser(BaseParser):
    """홍콩 법령 RTF 파서"""

    @staticmethod
    def matches(file_path: str) -> bool:
        """홍콩 법령 파일인지 확인"""
        path_lower = file_path.replace("\\", "/").lower()
        return "hongkong" in path_lower or "hong kong" in path_lower or "cap " in path_lower

    def split_articles(self, text: str) -> list[dict]:
        """홍콩 RTF 텍스트를 섹션 단위로 분리"""
        return _split_hk_english(text)

    def detect_hierarchy(self, text: str) -> list[dict]:
        """Part, Division 계층 구조 추출"""
        return _detect_hierarchy_hk(text)

    def parse_paragraphs(self, text: str, section_id: str = None) -> list[dict]:
        """섹션 내용을 항/호 단위로 파싱"""
        return _parse_paragraphs_hongkong(text, section_id)


def _split_hk_english(text: str) -> list[dict]:
    """홍콩 RTF에서 섹션 및 Schedule을 추출한다.

    형식:
    - Section: N.\t제목\n(1)\t내용...
    - Schedule: Schedule N\n제목\n내용

    각 Section에 Part/Schedule 정보를 포함하여 반환한다.
    """
    articles = []

    # 먼저 Part와 Schedule의 위치를 추출
    part_schedule_positions = []
    first_schedule_pos = None

    # Part 패턴: Part N 또는 Part NA (제목 포함) - 로마숫자(I,II,III) 또는 아라비아숫자(1,2,3) 지원
    part_pattern = re.compile(r'\n(Part (?:\d+|[IVX]+)[A-Z]?)\n([^\n]+)', re.IGNORECASE)
    for match in part_pattern.finditer(text):
        part_num = match.group(1).strip()
        part_title = match.group(2).strip()
        # Part 번호와 제목 결합
        full_name = f"{part_num}: {part_title}"
        part_schedule_positions.append({
            'name': full_name,
            'start_pos': match.start()
        })

    # Schedule 패턴 (앞에 밑줄이 있는 실제 Schedule 헤더만 매칭)
    # 밑줄 5개 이상 이후 200자 이내에 Schedule (숫자는 선택사항)
    schedule_pattern = re.compile(r'_{5,}.{0,200}?\n(Schedule(?:\s+\d+[A-Z]?)?)\s*\n', re.DOTALL | re.IGNORECASE)
    for match in schedule_pattern.finditer(text):
        schedule_name = match.group(1).strip()
        schedule_pos = match.start()

        # 첫 Schedule 위치 저장
        if first_schedule_pos is None:
            first_schedule_pos = schedule_pos

        # Schedule을 부칙으로 표시
        part_schedule_positions.append({
            'name': f'부칙 ({schedule_name})',
            'start_pos': schedule_pos
        })

    # 위치순 정렬
    part_schedule_positions.sort(key=lambda x: x['start_pos'])

    # Schedule 이후의 Part들 제거 (Schedule 4 내부 Part 구조)
    if first_schedule_pos:
        part_schedule_positions = [ps for ps in part_schedule_positions
                                   if ps['start_pos'] < first_schedule_pos or '부칙' in ps['name']]

    # Schedule들의 위치 찾기
    schedule_ranges = []
    for i, ps in enumerate(part_schedule_positions):
        if '부칙' in ps['name']:
            # 이 Schedule의 시작과 끝 위치
            schedule_start = ps['start_pos']
            # 다음 Part/Schedule까지가 이 Schedule의 범위
            if i + 1 < len(part_schedule_positions):
                schedule_end = part_schedule_positions[i + 1]['start_pos']
            else:
                schedule_end = len(text)
            schedule_ranges.append({
                'name': ps['name'],
                'start': schedule_start,
                'end': schedule_end
            })

    # 첫 Schedule 시작 위치
    first_schedule_pos = schedule_ranges[0]['start'] if schedule_ranges else None

    # 1단계: 모든 Section 시작 위치 찾기
    section_positions = []
    # Positive lookbehind를 사용하여 \n을 소비하지 않음
    # 알파벳 0개 이상 매칭: 31Z, 31ZA, 31ZB 등
    section_start_pattern = re.compile(r'(?<=\n)(\d+[A-Z]*)\.\t+([^\n]+)')

    for match in section_start_pattern.finditer(text):
        section_num = match.group(1)
        section_title = match.group(2).strip()
        match_pos = match.start()

        # 본문 섹션 (첫 Schedule 이전)
        if first_schedule_pos is None or match_pos < first_schedule_pos:
            # 본문 섹션 포함
            pass
        else:
            # Schedule 범위 내의 섹션인지 확인
            in_schedule = False
            for sched in schedule_ranges:
                if sched['start'] <= match_pos < sched['end']:
                    # Schedule 1만 섹션 추출 (Schedule 2, 3, 4는 표/폐지/하위Part 구조)
                    if 'Schedule 1' in sched['name']:
                        in_schedule = True
                    break

            # Schedule 범위가 아니면 제외 (Schedule 4의 하위 Part 등)
            if not in_schedule:
                continue

        # 제목 끝 다음부터 내용 시작
        title_end = match.end()
        # 제목 다음 줄바꿈을 건너뛰고 내용 시작
        if title_end < len(text) and text[title_end] == '\n':
            start_pos = title_end + 1
        else:
            start_pos = title_end

        section_positions.append({
            'num': section_num,
            'title': section_title,
            'start': start_pos,
            'match_start': match.start() - 1  # \n 위치 (-1)
        })

    # 2단계: 각 Section의 내용 추출 (다음 Section 시작 전까지)
    for i, section_info in enumerate(section_positions):
        section_num = section_info['num']
        section_title = section_info['title']
        content_start = section_info['start']

        # 다음 Section 시작 위치 (없으면 텍스트 끝)
        content_end = section_positions[i + 1]['match_start'] if i + 1 < len(section_positions) else len(text)

        # Part/Schedule 경계에서 내용 자르기
        section_pos = section_info['match_start']
        for ps in part_schedule_positions:
            # 이 섹션 이후에 나타나는 첫 Part/Schedule에서 내용 종료
            if ps['start_pos'] > section_pos and ps['start_pos'] < content_end:
                content_end = ps['start_pos']
                break

        # 내용 추출
        section_content = text[content_start:content_end].strip()

        # 마지막 줄이 소제목인 경우 제거
        # (절 제목이 이전 조문 내용 끝에 붙는 문제: e.g. "Proceedings for Revocation of Registration")
        _excluded_starts = ('The ', 'Any ', 'A ', 'An ', 'If ', 'Where ', 'Subject ', 'In ', 'For ')
        _last_line_match = re.search(r'\n([A-Z][^\n\t]{9,79})\s*$', section_content)
        if _last_line_match:
            _candidate = _last_line_match.group(1).strip()
            if (not _candidate.endswith(('.', '|', ',')) and
                    not _candidate.startswith(_excluded_starts)):
                section_content = section_content[:_last_line_match.start()].strip()

        # 이 섹션이 속한 Part/Schedule 찾기
        section_pos = section_info['match_start']
        current_part = ""
        for ps in part_schedule_positions:
            if ps['start_pos'] < section_pos:
                current_part = ps['name']
            else:
                break

        articles.append({
            'id': section_num,
            'title': section_title,
            'text': section_content,
            'part': current_part  # Part/Schedule 정보 추가
        })

    # Schedule 처리 (Section이 없는 Schedule을 별도 조문으로 추가)
    for sched in schedule_ranges:
        sched_name = sched['name']
        sched_start = sched['start']
        sched_end = sched['end']

        # 이 Schedule 범위 내에 Section이 있는지 확인
        has_sections = any(
            sched_start <= sec['match_start'] < sched_end
            for sec in section_positions
        )

        # Section이 없는 Schedule만 전체를 하나의 조문으로 추출
        if not has_sections:
            # Schedule 내용 추출
            schedule_text = text[sched_start:sched_end].strip()

            # Schedule 이름에서 번호 추출 (부칙 (Schedule 1) -> Schedule 1)
            schedule_id = "Schedule"
            if 'Schedule' in sched_name:
                # "부칙 (Schedule 1)" -> "Schedule 1"
                match = re.search(r'Schedule\s*(\d+[A-Z]?)?', sched_name)
                if match:
                    schedule_id = match.group(0).strip()

            # Schedule 제목 찾기
            # "Schedule\n\n|[ss. 2 & 83]|\nParis Convention Countries..." 형식
            schedule_title = ""

            # Schedule 단어 이후부터 검색
            schedule_keyword_pos = schedule_text.find('Schedule')
            if schedule_keyword_pos >= 0:
                after_schedule = schedule_text[schedule_keyword_pos:]
                lines = after_schedule.split('\n')

                # Schedule 다음 줄들에서 제목 찾기
                for line in lines[1:15]:
                    line = line.strip()
                    # 빈 줄, 밑줄, 대괄호 표기, Editorial Note, Format changes 등 제외
                    if (line and
                        not line.startswith('_') and
                        not line.startswith('|') and
                        not line.startswith('[') and
                        not line.startswith('(') and
                        'Editorial Note' not in line and
                        len(line) > 5):  # 너무 짧은 줄 제외
                        schedule_title = line
                        break

            articles.append({
                'id': schedule_id,
                'title': schedule_title,
                'text': schedule_text,
                'part': sched_name
            })

    return articles


def _detect_hierarchy_hk(text: str) -> list[dict]:
    """홍콩 RTF에서 Part, Division, Subdivision 계층을 추출한다."""
    hierarchy = []

    # Part N 또는 Part NA: 제목 - 로마숫자(I,II,III) 또는 아라비아숫자(1,2,3) 지원
    part_pattern = re.compile(r'\nPart ((?:\d+|[IVX]+)[A-Z]?)\n([^\n]+)')
    for match in part_pattern.finditer(text):
        part_num = match.group(1)
        part_title = match.group(2).strip()
        hierarchy.append({
            'type': 'part',
            'title': f"Part {part_num}: {part_title}",
            'start_pos': match.start()
        })

    # Division N—제목
    division_pattern = re.compile(r'\nDivision (\d+[A-Z]?)—([^\n]+)')
    for match in division_pattern.finditer(text):
        div_num = match.group(1)
        div_title = match.group(2).strip()
        hierarchy.append({
            'type': 'division',
            'title': f"Division {div_num}—{div_title}",
            'start_pos': match.start()
        })

    # Subdivision N—제목
    subdivision_pattern = re.compile(r'\nSubdivision (\d+[A-Z]?)—([^\n]+)')
    for match in subdivision_pattern.finditer(text):
        subdiv_num = match.group(1)
        subdiv_title = match.group(2).strip()
        hierarchy.append({
            'type': 'subdivision',
            'title': f"Subdivision {subdiv_num}—{subdiv_title}",
            'start_pos': match.start()
        })

    # 숫자 없는 소제목 (디자인법 등)
    # 섹션 번호 앞에 나오는 소제목 (명사구 형태)
    # 예: Registrable Designs\n5.\t, Applications for Registration\n12.\t
    # 조건: 탭 없음, 대문자로 시작, 적당한 길이 (10~80자), 다음 줄이 섹션 번호
    # 필터: Part 제목이 아니고, 마침표로 끝나지 않고, 특정 단어로 시작 안함

    # Part 제목 목록 생성 (제외용)
    part_titles = set()
    for h in hierarchy:
        if h['type'] == 'part':
            # "Part I: Preliminary" -> "Preliminary"
            title_parts = h['title'].split(': ', 1)
            if len(title_parts) > 1:
                part_titles.add(title_parts[1].strip())

    subheading_pattern = re.compile(
        r'\n([A-Z][^\n\t]{9,79})\n(?=\d+\.\t)',
        re.MULTILINE
    )
    for match in subheading_pattern.finditer(text):
        subheading_title = match.group(1).strip()

        # 필터링:
        # 1. Part 제목과 동일한 것 제외
        # 2. 괄호로 시작하는 것 제외
        # 3. 마침표/파이프로 끝나는 것 제외 (문장, 표)
        # 4. 특정 단어로 시작하는 것 제외 (본문 문장)
        excluded_starts = ('(', 'The ', 'Any ', 'A ', 'An ', 'If ', 'Where ', 'Subject ', 'In ', 'For ')

        if (subheading_title not in part_titles and
            not subheading_title.endswith(('.', '|')) and
            not subheading_title.startswith(excluded_starts)):
            hierarchy.append({
                'type': 'division',  # 장으로 분류
                'title': subheading_title,
                'start_pos': match.start(1)  # 소제목 시작 위치
            })

    # 위치 순서대로 정렬
    hierarchy.sort(key=lambda x: x['start_pos'])
    return hierarchy


def _parse_paragraphs_hongkong(text: str, section_id: str = None) -> list[dict]:
    """홍콩 섹션 내용을 항/호 단위로 파싱한다.

    (1)\t항 내용
    (a)\t호 내용
    (i)\t목 내용

    Args:
        text: 섹션 내용
        section_id: 섹션 번호 (예: "2", "2A") - Section 2만 정의 조항 특별 처리
    """
    rows = []

    # (1), (2), (3), (1A), (1B) 항 패턴
    # 항 앞에 탭 문자가 있을 수 있음: \t(1)\t 또는 \n\t(1)\t
    # 텍스트 시작 부분의 항도 매칭: ^(1)\t
    # 대문자도 매칭: (1A), (1B) 등
    subsection_pattern = re.compile(
        r'(?:^|[\n\t])\((\d+[a-zA-Z]?)\)\t+(.*?)(?=(?:^|[\n\t])\(\d+[a-zA-Z]?\)\t+|\Z)',
        re.DOTALL | re.MULTILINE
    )
    subsections = list(subsection_pattern.finditer(text))

    if not subsections:
        # 항이 없으면 (a), (b) 호만 파싱 시도
        # 로마 숫자 (i, v, x)만 제외 (소문자 단일 문자 로마 숫자)
        para_pattern = re.compile(
            r'(?:^|[\n\t])\(([a-hj-uwyz])\)\t+(.*?)(?=(?:^|[\n\t])\([a-hj-uwyz]\)\t+|\Z)',
            re.DOTALL | re.MULTILINE
        )
        paras = list(para_pattern.finditer(text))

        if not paras:
            # 호도 없으면 전체를 하나로
            if text.strip():
                rows.append({
                    'paragraph': '',
                    'item': '',
                    'subitem': '',
                'subsubitem': '',
                    'text': text.strip()
                })
        else:
            # 첫 호 이전 도입부
            first_para_start = paras[0].start()
            intro = text[:first_para_start].strip()
            if intro:
                rows.append({
                    'paragraph': '',
                    'item': '',
                    'subitem': '',
                'subsubitem': '',
                    'text': intro
                })

            # 각 호 처리
            for para_match in paras:
                para_letter = para_match.group(1)  # 괄호 제거 (translator.py에서 추가)
                para_text = para_match.group(2).strip()

                # 호 안에서 목 (i), (ii), (iii) 찾기
                # 로마 숫자 패턴
                subitem_pattern = re.compile(
                    r'(?:^|[\n\t])\(([ivxlcdm]+)\)\t+(.*?)(?=(?:^|[\n\t])\([ivxlcdm]+\)\t+|\Z)',
                    re.DOTALL | re.MULTILINE
                )
                subitems = list(subitem_pattern.finditer(para_text))

                if not subitems:
                    # 목이 없으면 호 전체를 하나로
                    rows.append({
                        'paragraph': '',
                        'item': para_letter,
                        'subitem': '',
                        'subsubitem': '',
                        'text': para_text
                    })
                else:
                    # 첫 목 이전 도입부
                    first_subitem_start = subitems[0].start()
                    intro = para_text[:first_subitem_start].strip()
                    if intro:
                        rows.append({
                            'paragraph': '',
                            'item': para_letter,
                            'subitem': '',
                            'subsubitem': '',
                            'text': intro
                        })

                    # 각 목 처리
                    for subitem_match in subitems:
                        subitem_letter = subitem_match.group(1)  # 괄호 제거 (translator.py에서 추가)
                        subitem_text = subitem_match.group(2).strip()
                        rows.append({
                            'paragraph': '',
                            'item': para_letter,
                            'subitem': subitem_letter,
                            'subsubitem': '',
                            'text': subitem_text
                        })

        return rows

    # 첫 번째 항 이전 텍스트 (도입부)
    first_subsection_start = subsections[0].start()
    intro_text = text[:first_subsection_start].strip()
    if intro_text:
        rows.append({
            'paragraph': '',
            'item': '',
            'subitem': '',
                'subsubitem': '',
            'text': intro_text
        })

    # 각 항 처리
    for subsection_match in subsections:
        subsection_num = subsection_match.group(1)  # 괄호 제거 (translator.py에서 추가)
        subsection_text = subsection_match.group(2).strip()

        # 정의 규정 패턴 감지: Section 2에만 적용
        # "means—", "includes—", "requires—" 다음의 (a), (b)는 호가 아님
        is_definition = False
        if section_id == "2":
            is_definition = (
                'means—' in subsection_text or 'includes—' in subsection_text or
                'means -' in subsection_text or 'requires—' in subsection_text or
                'requires -' in subsection_text or 'context otherwise requires' in subsection_text
            )

        # 항 내에서 호 (a), (b), (c) 찾기
        # 정의 규정이 아닌 경우만 호로 파싱
        if not is_definition:
            # 호 앞에 탭 문자가 있을 수 있음: \t(a)\t 또는 \n\t(a)\t 또는 ^(a)\t
            # 로마 숫자 i, v, x만 제외 (소문자 단일 문자 로마 숫자)
            para_pattern = re.compile(
                r'(?:^|[\n\t])\(([a-hj-uwyz])\)\t+(.*?)(?=(?:^|[\n\t])\([a-hj-uwyz]\)\t+|\Z)',
                re.DOTALL | re.MULTILINE
            )
            paras = list(para_pattern.finditer(subsection_text))
        else:
            # 정의 규정인 경우 호로 파싱하지 않음
            paras = []

        if not paras:
            # 호가 없으면 항 전체
            rows.append({
                'paragraph': subsection_num,
                'item': '',
                'subitem': '',
                'subsubitem': '',
                'text': subsection_text
            })
        else:
            # 호 이전 도입부
            first_para_start = paras[0].start()
            para_intro = subsection_text[:first_para_start].strip()
            if para_intro:
                rows.append({
                    'paragraph': subsection_num,
                    'item': '',
                    'subitem': '',
                'subsubitem': '',
                    'text': para_intro
                })

            # 각 호 처리
            for para_match in paras:
                para_letter = para_match.group(1)  # 괄호 제거 (translator.py에서 추가)
                para_text = para_match.group(2).strip()

                # 호 내에서 목 (i), (ii), (iii) 찾기
                # 목 앞에도 탭 문자가 있을 수 있음 또는 텍스트 시작
                subitem_pattern = re.compile(
                    r'(?:^|[\n\t])\(([ivxlcdm]+)\)\t+(.*?)(?=(?:^|[\n\t])\([ivxlcdm]+\)\t+|\Z)',
                    re.DOTALL | re.MULTILINE
                )
                subitems = list(subitem_pattern.finditer(para_text))

                if not subitems:
                    # 목이 없으면 호 전체
                    rows.append({
                        'paragraph': subsection_num,
                        'item': para_letter,
                        'subitem': '',
                'subsubitem': '',
                        'text': para_text
                    })
                else:
                    # 목 이전 도입부
                    first_subitem_start = subitems[0].start()
                    subitem_intro = para_text[:first_subitem_start].strip()
                    if subitem_intro:
                        rows.append({
                            'paragraph': subsection_num,
                            'item': para_letter,
                            'subitem': '',
                'subsubitem': '',
                            'text': subitem_intro
                        })

                    # 각 목 처리
                    for subitem_match in subitems:
                        subitem_roman = subitem_match.group(1)  # 괄호 제거 (translator.py에서 추가)
                        subitem_text = subitem_match.group(2).strip()

                        # 목 내에서 세목 (A), (B), (C) 찾기
                        # (I), (V), (X) 등 로마 숫자는 제외 (텍스트로 포함)
                        subsubitem_pattern = re.compile(
                            r'(?:^|[\n\t])\(([A-HJ-UW-Z])\)\t+(.*?)(?=(?:^|[\n\t])\([A-HJ-UW-Z]\)\t+|\Z)',
                            re.DOTALL | re.MULTILINE
                        )
                        subsubitems = list(subsubitem_pattern.finditer(subitem_text))

                        if not subsubitems:
                            # 세목이 없으면 목 전체
                            rows.append({
                                'paragraph': subsection_num,
                                'item': para_letter,
                                'subitem': subitem_roman,
                                'subsubitem': '',
                                'text': subitem_text
                            })
                        else:
                            # 세목 이전 도입부
                            first_subsubitem_start = subsubitems[0].start()
                            subsubitem_intro = subitem_text[:first_subsubitem_start].strip()
                            if subsubitem_intro:
                                rows.append({
                                    'paragraph': subsection_num,
                                    'item': para_letter,
                                    'subitem': subitem_roman,
                                    'subsubitem': '',
                                    'text': subsubitem_intro
                                })

                            # 각 세목 처리
                            for subsubitem_match in subsubitems:
                                subsubitem_letter = subsubitem_match.group(1)  # 괄호 제거 (translator.py에서 추가)
                                subsubitem_text = subsubitem_match.group(2).strip()

                                rows.append({
                                    'paragraph': subsection_num,
                                    'item': para_letter,
                                    'subitem': subitem_roman,
                                    'subsubitem': subsubitem_letter,
                                    'text': subsubitem_text
                                })

    return rows
