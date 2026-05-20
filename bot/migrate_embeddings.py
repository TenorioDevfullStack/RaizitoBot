import logging
import sys
import os
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from bot.db import _connect, _upsert_knowledge_item
from bot.rag import embed_text
from bot.vector_store import use_supabase_vector_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def migrate_embeddings():
    logger.info("Starting embedding migration...")
    
    conn = _connect()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT id, user_id, source_type, source_id, title, content, metadata FROM knowledge_items")
        rows = cursor.fetchall()
        total = len(rows)
        logger.info(f"Found {total} items to re-index.")
        
        for i, row in enumerate(rows, start=1):
            item_id, user_id, source_type, source_id, title, content, metadata_json = row
            
            logger.info(f"[{i}/{total}] Re-indexing: {title} (ID: {item_id})")
            
            # This will generate new embedding and update both SQLite and Supabase (if configured)
            try:
                _upsert_knowledge_item(
                    cursor,
                    user_id,
                    source_type,
                    source_id,
                    title,
                    content,
                    metadata=None
                )
                conn.commit() # Commit after each item to ensure progress is saved
            except Exception as e:
                logger.error(f"Failed to re-index item {item_id}: {e}")
                conn.rollback()
                
        logger.info("Migration completed successfully.")
        
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_embeddings()
