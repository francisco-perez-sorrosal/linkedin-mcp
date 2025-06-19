import os
from pathlib import Path
from typing import Any
import jsonlines

from loguru import logger


class BasicInMemoryCache:
    """
    Manages caching of json objects to prevent redundant actions
    """
    
    def __init__(self, 
                app_name: str, 
                cache_subdir: str, 
                cache_file: str, 
                cache_key_name: str,
                base_cache_dir: str | None = None):
        """
        Initialize the job description cache
        
        Args:
            app_name (str): Name of the application
            cache_subdir (str): Subdirectory for cache storage
            cache_file (str): Name of the cache file
            cache_key_name (str): Name of the key to use for finding elements in the cache
            base_cache_dir (str, optional): Base directory for cache storage
        """
        # Store the cache key name
        self.cache_key_name = cache_key_name
        
        # Use a default cache directory if not provided
        if base_cache_dir is None:
            base_cache_dir = os.path.expanduser("~")
        
        cache_dir = os.path.join(
            base_cache_dir, 
            f".{app_name}", 
            cache_subdir
        )
        
        # Ensure cache directory exists
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Cache file path
        self.cache_file = self.cache_dir / cache_file
        
        # In-memory cache for faster lookups
        self._cache: dict[str, Any] = self._load_cache()

    def _load_cache(self) -> dict[str, Any]:
        """
        Load existing cache from JSONL file
        
        Returns:
            dict: Cached job descriptions
        """
        cache: dict[str, Any] = {}
        
        if not self.cache_file.exists():
            return cache
        
        try:
            with jsonlines.open(self.cache_file, mode='r') as reader:
                for obj in reader:
                    # Use the specified cache key name to create the cache index
                    cache_index = obj.get(self.cache_key_name)
                    if cache_index:
                        cache[cache_index] = obj
        except Exception as e:
            logger.error(f"Error loading cache: {e}")
        
        logger.info(f"Loaded {len(cache)} items from cache {self.cache_file}")
        return cache

    @property
    def keys(self) -> list[str]:
        """
        Retrieve all keys from the cache
        
        Returns:
            list[str]: List of keys in the cache
        """
        return list(self._cache.keys())
        

    def build_dict_with(self, *obj_attrs: str, sep: str = " - ") -> dict:
        """
        Build a dictionary from the cache based on the specified object attributes
        
        Args:
            *obj_attrs (str): Attributes of the object to use as keys in the dictionary
        
        Returns:
            dict: Dictionary with keys from the cache and values from the specified attributes
        """
        return {key: sep.join(obj.get(attr, "N/A") for attr in obj_attrs) for key, obj in self._cache.items()}

    def is_empty(self) -> bool:
        """
        Check if the cache is empty
        
        Returns:
            bool: True if the cache is empty, False otherwise
        """
        return not self._cache
    
    
    def get(self, key: str) -> dict[str, Any] | None:
        """
        Retrieve a cached item by its key
        
        Args:
            key (str): Key to look up in the cache
        
        Returns:
            Optional[dict]: Cached item or None if not found
        """
        return self._cache.get(key)
    

    def put(self, serializable_structure: dict[str, Any], overwrite: bool = False) -> bool:
        """
        Save an item to cache using the specified cache key name
        
        Args:
            serializable_structure (dict): Serializable structure to be cached
        
        Returns:
            bool: True if item was added to cache, False if item already exists
        """
        
        # Get the cache index using the specified cache key name
        if not self.cache_key_name in serializable_structure:
            raise KeyError(f"Cache key name '{self.cache_key_name}' not found in serializable structure")
        
        cache_index = serializable_structure[self.cache_key_name]        
        
        try:                        
            if self.exists(str(cache_index)):
                if not overwrite:
                    logger.warning(f"Value found ({cache_index}) for cache key name '{self.cache_key_name}' but we can't overwrite")
                    return False
                logger.warning(f"Item with key {cache_index} already exists in cache. Overwriting...")

            # Update in-memory cache possibly overwriting it
            self._cache[str(cache_index)] = serializable_structure
            
            # Append to JSONL file
            with jsonlines.open(self.cache_file, mode='a') as writer:
                writer.write(serializable_structure)
            
            logger.info(f"Cached new item with key: {cache_index}")
            return True
        
        except Exception as e:
            logger.error(f"Error saving to cache: {e}")
            return False
                        
    def exists(self, key_value: str) -> bool:
        """
        Check if an item exists in the cache based on the specified cache key
        
        Args:
            key_value (str): Value of the cache key to look up
        
        Returns:
            bool: True if item exists in cache, False otherwise
        """
        return key_value in self._cache
