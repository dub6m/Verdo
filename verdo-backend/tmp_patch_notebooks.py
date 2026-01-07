import json
from pathlib import Path

paths=[Path('app/services/ingester/tests/test_pdf.ipynb'),Path('app/services/ingester/tests/test_pptx.ipynb')]
for p in paths:
    nb=json.load(open(p,'r',encoding='utf-8'))
    new_cells=[]
    if nb['cells'] and nb['cells'][0]['cell_type']=='markdown':
        new_cells.append(nb['cells'][0])
        start_idx=1
    else:
        start_idx=0
    setup_md={"cell_type":"markdown","metadata":{},"source":["## Environment Detection & Setup (Colab or Local)\n\n"]}
    setup_code={"cell_type":"code","metadata":{},"execution_count":None,"outputs":[],"source":[
        "# Robust Colab detection and paths\n",
        "import os, sys\n",
        "from pathlib import Path\n",
        "IN_COLAB = False\n",
        "try:\n",
        "    import google.colab  # type: ignore\n",
        "    IN_COLAB = True\n",
        "except Exception:\n",
        "    IN_COLAB = False\n",
        "print('Running in Colab:' , IN_COLAB)\n",
        "\n",
        "PROJECT_NAME = 'verdo-backend'\n",
        "if IN_COLAB:\n",
        "    from google.colab import drive  # type: ignore\n",
        "    drive.mount('/content/drive')\n",
        "    DRIVE_ROOT = Path('/content/drive/MyDrive')\n",
        "    PROJECT_ROOT = DRIVE_ROOT / PROJECT_NAME\n",
        "else:\n",
        "    PROJECT_ROOT = Path.cwd()\n",
        "    for _ in range(5):\n",
        "        if (PROJECT_ROOT / 'app').exists():\n",
        "            break\n",
        "        PROJECT_ROOT = PROJECT_ROOT.parent\n",
        "INGESTER_PATH = PROJECT_ROOT / 'app' / 'services'\n",
        "TEST_FILES_PATH = PROJECT_ROOT / 'test_files'\n",
        "sys.path.insert(0, str(INGESTER_PATH))\n",
        "print('Project root:', PROJECT_ROOT)\n",
        "print('Ingester path added:', INGESTER_PATH)\n",
        "print('Test files path:', TEST_FILES_PATH)\n"
    ]}
    deps_md={"cell_type":"markdown","metadata":{},"source":["### Dependencies (Colab Only)\n\n"]}
    deps_code={"cell_type":"code","metadata":{},"execution_count":None,"outputs":[],"source":[
        "if IN_COLAB:\n",
        "    # Quiet installs to speed up outputs\n",
        "    !pip -q install python-dotenv ultralytics pytesseract pillow pdf2image opencv-python-headless\n",
        "    # !apt-get -y install tesseract-ocr\n"
    ]}
    secrets_md={"cell_type":"markdown","metadata":{},"source":["### API Keys (Colab: Secrets; Local: .env)\n\n"]}
    secrets_code={"cell_type":"code","metadata":{},"execution_count":None,"outputs":[],"source":[
        "OPENAI_API_KEY = None\n",
        "ZAI_API_KEY = None\n",
        "if IN_COLAB:\n",
        "    try:\n",
        "        from google.colab import userdata  # type: ignore\n",
        "        OPENAI_API_KEY = userdata.get('OPENAIKEY')\n",
        "        ZAI_API_KEY = userdata.get('ZAIAPIKEY')\n",
        "    except Exception as e:\n",
        "        print('Colab secrets unavailable:', e)\n",
        "else:\n",
        "    try:\n",
        "        from dotenv import load_dotenv\n",
        "        load_dotenv()\n",
        "    except Exception:\n",
        "        pass\n",
        "    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY') or os.getenv('OPENAIKEY')\n",
        "    ZAI_API_KEY = os.getenv('ZAI_API_KEY') or os.getenv('ZAIAPIKEY')\n",
        "print('OpenAI key set:', bool(OPENAI_API_KEY))\n",
        "print('Zhipu key set:', bool(ZAI_API_KEY))\n"
    ]}
    new_cells += [setup_md, setup_code, deps_md, deps_code, secrets_md, secrets_code]
    skip_phrases = ('Detect if running in Colab', 'google.colab', 'drive.mount', 'Install Dependencies', 'pip install', 'apt-get', 'dotenv', 'Secrets')
    for c in nb['cells'][start_idx:]:
        s=''.join(c.get('source',[])) if c.get('source') else ''
        if c['cell_type']=='code' and any(x in s for x in skip_phrases):
            continue
        if c['cell_type']=='markdown' and any(x in s for x in ('Environment Detection', 'Mount Google Drive','Install Dependencies','API Keys')):
            continue
        new_cells.append(c)
    nb['cells']=new_cells
    m=nb.setdefault('metadata',{})
    ks=m.setdefault('kernelspec',{})
    ks.setdefault('display_name','Python 3')
    ks.setdefault('language','python')
    ks.setdefault('name','python3')
    json.dump(nb, open(p,'w',encoding='utf-8'), ensure_ascii=False, indent=1)
    print('Patched', p)