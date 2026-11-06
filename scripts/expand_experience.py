"""Add real, retraceable DeepSeek results to the offline experience.

Run from the project root. Uses the locally configured key; never saves it.
Only short evidence excerpts and publication metadata go into the repository.
"""
import json
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from criteria import configured_key
from demo import QUESTION, CRITERIA
from literature_search import search, candidates, full_text
from screen_paper import screen_paper

DOIS = ['10.1038/s41586-023-06063-y', '10.1038/s41467-026-68324-4',
        '10.1038/s41467-026-69294-3', '10.3389/fimmu.2025.1674743']


def main():
    destination = Path(__file__).resolve().parents[1] / 'demo_results.json'
    results = json.loads(destination.read_text())
    key = configured_key()
    if not key:
        raise SystemExit('请先在本机配置 DeepSeek 密钥。')
    for doi in DOIS:
        if any(r.get('doi') == doi for r in results):
            continue
        _, rows = search('DOI:' + doi, 2)
        items = candidates(rows)
        if not items:
            raise RuntimeError('No publication found: ' + doi)
        item = items[0]
        print('Reading: ' + item['title'], flush=True)
        source, pages = full_text(item)
        if not pages:
            raise RuntimeError('No accessible full text: ' + doi)
        assessment = screen_paper(QUESTION, CRITERIA, pages, key)
        is_secondary = any(t.lower() in {'review', 'systematic review', 'editorial', 'comment'}
                           for t in item['publication_types'])
        if is_secondary and assessment['priority'] == '优先读':
            assessment['priority'] = '背景参考'
        result = {**item, **assessment, 'doi': doi, 'source_kind': source,
                  'short_pages': [p['page'] for p in pages if len(p['text']) < 50] if source == 'PDF 全文' else [],
                  'screened_on': date.today().isoformat(), 'year': rows[0].get('pubYear', ''),
                  'journal': (rows[0].get('journalInfo') or {}).get('journal', {}).get('title', '')}
        # Avoid distributing article text; retain only the checked, short quotations.
        result.pop('abstract', None)
        if is_secondary:
            result['source_note'] = '综述文献，用作背景参考；其中引用的试验不视为本研究的独立结果。'
        results.append(result)
        destination.write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n')
        evidence = sum(f['verified'] for f in assessment['findings'])
        print(f"Saved: {assessment['priority']} / {evidence} located quotations / {source}", flush=True)
    print(f'Total experience papers: {len(results)}', flush=True)


if __name__ == '__main__':
    main()
