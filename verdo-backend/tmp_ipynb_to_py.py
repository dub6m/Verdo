import json, re
from pathlib import Path

def ipynb_to_py(ipynb_path: Path, py_path: Path):
    nb=json.load(open(ipynb_path,'r',encoding='utf-8'))
    lines=[]
    for cell in nb.get('cells',[]):
        if cell.get('cell_type')=='markdown':
            src=''.join(cell.get('source',[]))
            lines.append('# ' + '\n# '.join(src.splitlines()) + '\n\n')
        elif cell.get('cell_type')=='code':
            src=''.join(cell.get('source',[]))
            lines.append(src.rstrip()+"\n\n")
    code=''.join(lines)
    code=re.sub(r"^!.*$","",code,flags=re.M)
    removals=[
        r"(?s)try:\n\s*import google\.colab.*?except Exception:.*?\n",
        r"(?s)from google\.colab import drive.*?drive\.mount\(.*?\)\n",
        r"(?s)from google\.colab import userdata.*?\n",
        r"(?s)IN_COLAB\s*=\s*True.*?\n",
        r"(?s)IN_COLAB\s*=\s*False.*?\n",
        r"(?s)if IN_COLAB:.*?\n(\s{4,}.*?\n)+",
    ]
    for pat in removals:
        code=re.sub(pat,'',code)
    code=re.sub(r"\n{3,}","\n\n",code)
    py_path.write_text(code,encoding='utf-8')

pairs=[
    (Path('app/services/ingester/tests/test_pdf.ipynb'), Path('app/services/ingester/tests/test_pdf.py')),
    (Path('app/services/ingester/tests/test_pptx.ipynb'), Path('app/services/ingester/tests/test_pptx.py')),
]
for ip,op in pairs:
    ipynb_to_py(ip,op)
    print('Wrote', op)