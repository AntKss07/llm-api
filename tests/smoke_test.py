"""Quick smoke test for all API endpoints — uses a temp file DB"""
import sys
import tempfile
import os

sys.path.insert(0, '.')

# Set up a temp DB
tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
tmp.close()
DB_PATH = tmp.name

from app import create_app

app = create_app(db_path=DB_PATH)
app.config['TESTING'] = True
c = app.test_client()

results = []

def check(name, r, expected_status):
    ok = "PASS" if r.status_code == expected_status else "FAIL"
    results.append((ok, name, r.status_code, expected_status))
    icon = "v" if ok == "PASS" else "X"
    print(f"[{icon}] {name}: HTTP {r.status_code} (expected {expected_status})")
    return r.get_json()

# Health
h = c.get('/api/health')
hd = check("GET /api/health", h, 200)
print(f"   model={hd.get('model')}, healthy={hd.get('healthy')}")

# Create conversation
r = c.post('/api/conversations', json={"title": "Test Chat"}, content_type='application/json')
cd = check("POST /api/conversations", r, 201)
conv_id = cd['conversation']['id']
print(f"   id={conv_id[:8]}..., title={cd['conversation']['title']}")

# List conversations
r2 = c.get('/api/conversations')
ld = check("GET /api/conversations", r2, 200)
print(f"   count={len(ld['conversations'])}")

# Rename
r3 = c.patch(f'/api/conversations/{conv_id}', json={"title": "Renamed!"}, content_type='application/json')
rd = check("PATCH /api/conversations/<id>", r3, 200)
print(f"   new title={rd['conversation']['title']}")

# Get with messages
r4 = c.get(f'/api/conversations/{conv_id}')
gd = check("GET /api/conversations/<id>", r4, 200)
print(f"   messages={len(gd['conversation']['messages'])}")

# 404 conversation
r4b = c.get('/api/conversations/00000000-0000-0000-0000-000000000000')
check("GET /api/conversations/<bad-id> (expect 404)", r4b, 404)

# 400 invalid UUID
r4c = c.get('/api/conversations/not-a-uuid')
check("GET /api/conversations/<invalid> (expect 400)", r4c, 400)

# Delete
r5 = c.delete(f'/api/conversations/{conv_id}')
check("DELETE /api/conversations/<id>", r5, 200)

# Confirm gone
r6 = c.get(f'/api/conversations/{conv_id}')
check("GET after DELETE (expect 404)", r6, 404)

# Chat validation
r7 = c.post('/api/chat', json={"message": ""}, content_type='application/json')
check("POST /api/chat empty msg (expect 400)", r7, 400)

r8 = c.post('/api/chat', json={"message": "x" * 33000}, content_type='application/json')
check("POST /api/chat too-long (expect 400)", r8, 400)

r9 = c.post('/api/chat', data="bad json", content_type='application/json')
check("POST /api/chat bad JSON (expect 400)", r9, 400)

r10 = c.get('/api/nonexistent')
check("GET /api/nonexistent (expect 404)", r10, 404)

r11 = c.post('/api/chat', json={"message": "hello", "conversation_id": "not-a-uuid"}, content_type='application/json')
check("POST /api/chat invalid UUID (expect 400)", r11, 400)

r12 = c.post('/api/chat', json={"message": "hello", "conversation_id": "00000000-0000-0000-0000-000000000000"}, content_type='application/json')
check("POST /api/chat unknown conv (expect 404)", r12, 404)

# No API key
import config as cfg
old_key = cfg.GEMINI_API_KEY
cfg.GEMINI_API_KEY = None
r13 = c.post('/api/chat', json={"message": "hello"}, content_type='application/json')
check("POST /api/chat missing API key (expect 500)", r13, 500)
cfg.GEMINI_API_KEY = old_key

# Summary
os.unlink(DB_PATH)

passed = sum(1 for x in results if x[0] == "PASS")
failed = sum(1 for x in results if x[0] == "FAIL")
print(f"\n{'='*55}")
print(f"ENDPOINT SMOKE TEST: {passed}/{len(results)} passed, {failed} failed")
if failed == 0:
    print("ALL ENDPOINT TESTS PASSED")
else:
    for x in results:
        if x[0] == "FAIL":
            print(f"  FAILED: {x[1]} — got {x[2]}, expected {x[3]}")
    sys.exit(1)
