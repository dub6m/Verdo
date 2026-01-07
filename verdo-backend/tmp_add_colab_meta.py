import json
for p in ['app/services/ingester/tests/test_pdf.ipynb','app/services/ingester/tests/test_pptx.ipynb']:
    with open(p,encoding='utf-8') as f:
        nb=json.load(f)
    nb.setdefault('metadata',{})['colab']={'name':'VSCode-Colab-Ready'}
    with open(p,'w',encoding='utf-8') as f:
        json.dump(nb,f,ensure_ascii=False,indent=1)
    print('Updated colab metadata for', p)