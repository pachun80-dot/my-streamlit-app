#!/usr/bin/env python3
"""프랑스 LEGI XML 파싱 스크립트.

사용법:
    python parse_france.py <LEGI_DIR> [OUTPUT_DIR] [LAW_NAME]

예시:
    python parse_france.py DATA/FRANCE/CPI_only/LEGITEXT000006069414
    python parse_france.py DATA/FRANCE/CPI_only/LEGITEXT000006069414 DATA/output/구조화법률/프랑스
"""

import sys
from pathlib import Path
from parsers.france import parse_and_save_french_law


def main():
    if len(sys.argv) < 2:
        print("사용법: python parse_france.py <LEGI_DIR> [OUTPUT_DIR] [LAW_NAME]")
        print()
        print("예시:")
        print("  python parse_france.py DATA/FRANCE/CPI_only/LEGITEXT000006069414")
        print("  python parse_france.py DATA/FRANCE/CPI_only/LEGITEXT000006069414 DATA/output/구조화법률/프랑스")
        print("  python parse_france.py DATA/FRANCE/CPI_only/LEGITEXT000006069414 DATA/output/구조화법률/프랑스 Custom_Law_Name")
        sys.exit(1)

    legi_dir = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "DATA/output/구조화법률/프랑스"
    law_name = sys.argv[3] if len(sys.argv) > 3 else "Code_de_la_propriété_intellectuelle"

    # 디렉토리 존재 확인
    if not Path(legi_dir).exists():
        print(f"❌ 오류: 디렉토리가 존재하지 않습니다: {legi_dir}")
        sys.exit(1)

    # 파싱 실행
    result = parse_and_save_french_law(
        legi_dir=legi_dir,
        output_dir=output_dir,
        law_name=law_name,
        save_separate=True
    )

    print("\n" + "=" * 80)
    print("✅ 파싱 완료!")
    print("=" * 80)
    print(f"\n📊 통계:")
    print(f"  • L조문: {result['stats']['l_articles']}개 ({result['stats']['l_rows']}개 행)")
    print(f"  • R조문: {result['stats']['r_articles']}개 ({result['stats']['r_rows']}개 행)")
    print(f"  • 전체: {result['stats']['total_articles']}개 ({result['stats']['total_rows']}개 행)")

    print(f"\n📁 저장된 파일:")
    for file_path in result['files']:
        print(f"  ✓ {file_path}")


if __name__ == "__main__":
    main()
