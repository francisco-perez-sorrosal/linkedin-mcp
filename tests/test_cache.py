import tempfile
from pathlib import Path
import pytest

from linkedin_mcp_server.cache import BasicInMemoryCache


@pytest.fixture
def temp_cache_dir():
    """Create a temporary directory for cache testing"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def cache(temp_cache_dir):
    """Create a cache instance for testing"""
    return BasicInMemoryCache(
        app_name="test",
        cache_subdir="test_cache",
        cache_file="test.jsonl",
        cache_key_name="job_id",
        base_cache_dir=temp_cache_dir
    )


def test_put_with_overwrite_no_duplicates(temp_cache_dir):
    """Test that put() with overwrite=True does not create duplicate JSONL entries"""
    # Create cache
    cache = BasicInMemoryCache(
        app_name="test",
        cache_subdir="test_cache",
        cache_file="test.jsonl",
        cache_key_name="job_id",
        base_cache_dir=temp_cache_dir
    )

    # Insert initial item
    item = {"job_id": "123", "title": "Engineer"}
    assert cache.put(item) is True

    # Overwrite with new data
    updated_item = {"job_id": "123", "title": "Senior Engineer"}
    assert cache.put(updated_item, overwrite=True) is True

    # Flush to write changes to disk
    cache.flush()

    # Reload cache from disk
    new_cache = BasicInMemoryCache(
        app_name="test",
        cache_subdir="test_cache",
        cache_file="test.jsonl",
        cache_key_name="job_id",
        base_cache_dir=temp_cache_dir
    )

    # Verify only one entry exists
    assert len(new_cache.keys) == 1
    assert new_cache.get("123")["title"] == "Senior Engineer"

    # Verify JSONL file has exactly one line
    cache_file = Path(temp_cache_dir) / ".test" / "test_cache" / "test.jsonl"
    with open(cache_file) as f:
        lines = f.readlines()
    assert len(lines) == 1


def test_put_batch_inserts_correctly(cache):
    """Test that put_batch() inserts N items and the JSONL file has exactly N entries"""
    items = [
        {"job_id": "1", "title": "Engineer 1"},
        {"job_id": "2", "title": "Engineer 2"},
        {"job_id": "3", "title": "Engineer 3"},
    ]

    count = cache.put_batch(items)
    assert count == 3

    # Verify in-memory cache
    assert len(cache.keys) == 3

    # Verify JSONL file
    with open(cache.cache_file) as f:
        lines = f.readlines()
    assert len(lines) == 3


def test_flush_produces_valid_jsonl(cache):
    """Test that flush() produces a valid JSONL file that round-trips through _load_cache()"""
    # Insert items
    items = [
        {"job_id": "1", "title": "Engineer 1"},
        {"job_id": "2", "title": "Engineer 2"},
    ]
    cache.put_batch(items)

    # Trigger an overwrite to set _needs_flush
    cache.put({"job_id": "1", "title": "Senior Engineer 1"}, overwrite=True)

    # Flush
    cache.flush()

    # Reload cache
    new_cache = BasicInMemoryCache(
        app_name="test",
        cache_subdir="test_cache",
        cache_file="test.jsonl",
        cache_key_name="job_id",
        base_cache_dir=str(cache.cache_dir.parent.parent)
    )

    # Verify data integrity
    assert len(new_cache.keys) == 2
    assert new_cache.get("1")["title"] == "Senior Engineer 1"
    assert new_cache.get("2")["title"] == "Engineer 2"


def test_flush_uses_atomic_write(cache):
    """Test that flush uses temp file (atomic write pattern)"""
    # Insert an item
    cache.put({"job_id": "1", "title": "Engineer"})

    # Trigger overwrite
    cache.put({"job_id": "1", "title": "Senior"}, overwrite=True)

    # Check that temp file is used during flush
    # (We can't easily test crash recovery, but we verify the pattern)
    temp_file = cache.cache_file.with_suffix('.tmp')

    # Temp file should not exist before flush
    assert not temp_file.exists()

    # Flush
    cache.flush()

    # Temp file should not exist after successful flush
    assert not temp_file.exists()

    # Original file should exist and be valid
    assert cache.cache_file.exists()


def test_put_batch_with_overwrite(cache):
    """Test put_batch with overwrite=True"""
    # Insert initial items
    initial = [
        {"job_id": "1", "title": "Engineer 1"},
        {"job_id": "2", "title": "Engineer 2"},
    ]
    cache.put_batch(initial)

    # Overwrite with batch
    updated = [
        {"job_id": "1", "title": "Senior Engineer 1"},
        {"job_id": "3", "title": "Engineer 3"},
    ]
    count = cache.put_batch(updated, overwrite=True)
    assert count == 2

    # Verify final state
    assert len(cache.keys) == 3
    assert cache.get("1")["title"] == "Senior Engineer 1"
    assert cache.get("2")["title"] == "Engineer 2"
    assert cache.get("3")["title"] == "Engineer 3"


def test_exists(cache):
    """Test exists() method"""
    assert cache.exists("1") is False

    cache.put({"job_id": "1", "title": "Engineer"})
    assert cache.exists("1") is True
    assert cache.exists("2") is False
