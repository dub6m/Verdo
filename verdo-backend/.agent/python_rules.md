# Python Coding Rules

# **1. Naming Conventions**

### **1.1 Classes → PascalCase**

- Use for any class definition.
- Example (EXAMPLE):

```python
class ImageRouter:
    pass
```

---

### **1.2 Methods → camelCase**

- No snake_case.
- No leading underscores unless private.

(EXAMPLE):

```python
def buildSchedule(self): ...
```

---

### **1.3 Instance Variables → camelCase**

(EXAMPLE):

```python
self.taskQueue = queue.Queue()
```

---

### **1.4 Module-Level Constants → UPPER_CASE**

(EXAMPLE):

```python
DEFAULT_TIMEOUT = 30
```

---

### **1.5 Avoid obscure abbreviations**

- Use clear names (`imageBytes`, `maxWorkers`, `taskQueue`).
- Only allow abbreviations widely known (`db`, `id`, `utc`, `api`).

---

# **2. Commenting Rules**

### **2.1 Use `#` comments, NOT triple-quoted strings for explanation**

Docstrings (`"""..."""`) only when:

- Public libraries
- Documentation tools need them (**rare** for your SaaS)

Everything else → `#` comments.

---

### **2.2 Section Headers**

Lightweight separators:

(EXAMPLE):

```python
# --- Image Helpers ------------------------------------------------------
```

Rules:

- Always start with `# ---`
- Use uppercase for section name
- Keep line length ≤ 78 for readability

---

### **2.3 Function Header Comments**

One-line “what this does”.

(EXAMPLE):

```python
# Converts PPTX to a sequence of normalized text blocks
def convertFile(self): ...
```

---

### **2.4 Inline Comments**

Short and placed on same line:

(EXAMPLE):

```python
pool = {}  # store active workers
```

---

# **3. File Structure Order**

Every Python file should follow this **top-down structure**:

1. **Imports**
2. **Environment loading** (if needed)
3. **Global constants**
4. **Classes**
5. **Helpers**
6. **Main entrypoint (if present)**

This ensures every file is readable top-down.

---

# **4. Import Rules**

### **4.1 Order imports by group**

1. Standard library
2. Third-party
3. Local modules

(EXAMPLE):

```python
import os
import time

import httpx
from openai import OpenAI

from .utils import tokenizer
```

---

### **4.2 Never use wildcard imports**

🚫 `from module import *`

Always be explicit.

---

# **5. Spacing & Whitespace Rules**

### **5.1 Blank lines**

- 2 blank lines between **top-level class or function definitions**
- 1 blank line between **logical blocks inside methods**

(EXAMPLE):

```python
def parse(self):
    tokens = []

    for t in text:
        ...
```

---

### **5.2 Indentation**

- Always Tabs

---

### **5.3 No trailing spaces**

Clean files.

---

# **6. Line Length Rules**

### **6.1 Target ≤ 100 characters**

110 is hard max.

### **6.2 Break long dicts or function calls over multiple lines**

(EXAMPLE):

```python
response = client.post(
    "/api/upload",
    json=data,
    timeout=30,
)
```

---

# **7. Error Handling Rules**

### **7.1 Only wrap the minimum code in try/except**

Never wrap whole methods unnecessarily.

---

### **7.2 Error strings follow a clear format**

(EXAMPLE):

```python
return f"<ERROR: {str(e)}>"
```

---

### **7.3 Never swallow exceptions silently**

- Either rethrow
- Or return structured error

---

# **8. Concurrency & Threading Rules**

(Applies only to files that use concurrency.)

### **8.1 Always use thread-safe queues or locks**

### **8.2 All worker threads should be daemon threads**

### **8.3 No direct `threading.Thread()` outside constructors**

Encapsulation principle.

---

# **9. Function Design Rules**

### **9.1 Functions should do one thing**

If a function starts needing multiple responsibilities → split it.

---

### **9.2 Avoid large functions (> 50 lines)**

Split into logical helpers.

---

### **9.3 Do NOT change public signatures once integrated**

Only modify:

- internals
- private helpers

---

# **10. Formatting Philosophy**

Your global style prioritizes:

1. **Clarity** over formal PEP8 compliance
2. **camelCase everywhere**
3. **Minimalistic structure**
4. **Comment-light, but comment-meaningful**
5. **Readable separators**
6. **SDK usage instead of raw REST when possible**
7. **No magic, no ambiguity, no wildcard imports**
