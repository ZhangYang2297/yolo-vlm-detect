import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.logger import setup_logging, get_logger
setup_logging()
logger = get_logger("test")

print("=== Testing Redis ===")
from core.redis_client import get_redis, enqueue, dequeue
r = get_redis()
assert r.ping()
enqueue("test:queue", {"hello": "world"})
result = dequeue("test:queue", timeout=2)
assert result["hello"] == "world"
print("Redis OK")

print("=== Testing MinIO ===")
from core.minio_client import get_minio, upload_bytes
client = get_minio()
buckets = [b.name for b in client.list_buckets()]
assert "alarm-media" in buckets
# 测试上传下载
test_data = b"hello minio test"
upload_bytes("test/hello.txt", test_data, "text/plain")
print("MinIO OK")

print("=== Testing MySQL ===")
from flask import Flask
from core.db import init_db, db
from core.models import AnalysisTask, AlarmRecord
app = Flask(__name__)
init_db(app)
with app.app_context():
    # 尝试查询
    tasks = AnalysisTask.query.all()
    print(f"MySQL OK, tables created, existing tasks: {len(tasks)}")

print("=== All infrastructure tests passed! ===")
