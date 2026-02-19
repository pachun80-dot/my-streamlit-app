# 프랑스 법령 XML 파서

프랑스 공식 LEGI 데이터베이스의 XML 파일을 파싱하여 구조화된 Excel로 변환합니다.

## 특징

### ✅ 완벽한 구조 보존
- **`<p>` 태그 단위 파싱** - 도입부, 항목, 결론 문단을 정확히 구분
- **계층 구조 자동 추출** - Partie/Livre/Titre/Chapitre/Section을 편/장/절에 매핑
- **혼합 항목 지원** - I/II (항) + 1°/2° (호) + a)/b) (목) 복합 구조 처리
- **VIGUEUR 버전만** - 현행 유효한 조문만 파싱 (MODIFIE/ABROGE 제외)

### 🔍 정확한 항목 분리
```
Article R715-2
  행1: [도입부] Le règlement d'usage... comprend :
  행2: [1°] Le nom du titulaire...
  행3: [2°] L'objet de l'association...
  ...
  행9: [8°] Les conditions d'usage...
  행10: [결론] Le règlement d'usage est publié... ← 8°와 분리!
```

## 사용법

### 1. 명령줄 실행

```bash
# 기본 실행
python parse_france.py DATA/FRANCE/CPI_only/LEGITEXT000006069414

# 출력 디렉토리 지정
python parse_france.py DATA/FRANCE/CPI_only/LEGITEXT000006069414 DATA/output/구조화법률/프랑스

# 법령 이름 지정
python parse_france.py DATA/FRANCE/CPI_only/LEGITEXT000006069414 DATA/output/구조화법률/프랑스 Custom_Law_Name
```

### 2. Python 코드에서 사용

```python
from parsers.france import parse_and_save_french_law

result = parse_and_save_french_law(
    legi_dir="DATA/FRANCE/CPI_only/LEGITEXT000006069414",
    output_dir="DATA/output/구조화법률/프랑스",
    law_name="Code_de_la_propriété_intellectuelle",
    save_separate=True
)

print(f"총 {result['stats']['total_articles']}개 조문")
print(f"L조문: {result['stats']['l_articles']}개")
print(f"R조문: {result['stats']['r_articles']}개")
```

## 출력 형식

### Excel 파일 구조
| 편 | 장 | 절 | 조문번호 | 조문제목 | 항 | 호 | 목 | 세목 | 원문 |
|----|----|----|---------|---------|----|----|----|----|------|
| Partie législative / Livre I | Chapitre II | ... | L111-1 | | | 1° | | | Le nom du titulaire... |
| ... | ... | ... | L111-1 | | | 2° | | | L'objet de l'association... |

### 생성되는 파일
- `{LAW_NAME}_L_VIGUEUR.xlsx` - L조문만 (Partie législative)
- `{LAW_NAME}_R_VIGUEUR.xlsx` - R조문만 (Partie réglementaire)
- `{LAW_NAME}_ALL.xlsx` - 전체 (L + R)

## 데이터 소스

### LEGI 데이터베이스
프랑스 공식 법령 데이터베이스: https://www.data.gouv.fr/fr/datasets/legi-codes-lois-et-reglements-consolides/

### 디렉토리 구조
```
DATA/FRANCE/CPI_only/LEGITEXT000006069414/
├── article/LEGI/ARTI/      # 조문 XML 파일
├── section_ta/LEGI/SCTA/   # 섹션 XML 파일
└── texte/                  # 법령 메타데이터
```

## 지원 항목 형식

| 형식 | 예시 | 매핑 |
|------|------|------|
| 로마 숫자 | I, II, III, IV, V, ... | 항 |
| Degree | 1°, 2°, 3°, ... | 호 |
| 알파벳 | a), b), c), ... | 목 |

### 혼합 구조 예시
```
I.-도입 문장
  1° Plantes fourragères:
    a) Trifolium pratense
    b) Trifolium incarnatum
  2° Plantes oléagineuses:
    Glycine max
II.-결론 문단
```

## 특수 처리

### 1. 참조 제외
- "au 2° de l'article R. 714-4" → 2°를 항목으로 인식하지 않음
- "du 3°", "le 1°" 등 참조 구문 필터링

### 2. R* 조문
- R*###-# 형식의 특수 조문 지원
- 정렬 시 일반 R조문 뒤에 배치

### 3. 조문 번호 정렬
```
L111-1, L111-2, ..., L999-99
R111-1, R111-2, ..., R*111-1, ..., R999-99
```

## 통계 (지식재산권법 예시)

```
L조문 (Partie législative):
  • 883개 조문
  • 2,087개 행
  • 356개 항, 373개 호, 106개 목

R조문 (Partie réglementaire):
  • 989개 조문
  • 2,468개 행
  • 324개 항, 579개 호, 145개 목

전체:
  • 1,872개 조문
  • 4,555개 행
```

## 트러블슈팅

### "article 디렉토리를 찾을 수 없습니다"
- LEGI XML 디렉토리 구조가 올바른지 확인
- `article/LEGI/ARTI/` 하위에 XML 파일이 있는지 확인

### "파싱된 조문이 0개"
- XML 파일에 `ETAT="VIGUEUR"` 항목이 있는지 확인
- 필터(`L` 또는 `R`)가 올바른지 확인

### 항목 순서가 잘못됨
- XML 파일의 `<p>` 태그 순서 확인
- 파서는 `<p>` 태그 순서를 유지하므로 원본 XML 구조에 문제가 있을 수 있음

## 제한사항

- **XML 전용**: PDF 파싱은 지원하지 않음 (XML이 훨씬 정확함)
- **LEGI 형식 전용**: 다른 XML 형식은 지원하지 않음
- **자동 감지 불가**: 명시적으로 `parse_france.py` 실행 필요

## 참고

- 독일 XML 파서: `parsers/germany.py`
- 메모리: `/Users/yunseok/.claude/projects/-Users-yunseok-Desktop-PycharmProjects-------/memory/MEMORY.md`
