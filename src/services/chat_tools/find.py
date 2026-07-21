"""Find tool - Finds photos matching description using vector search."""

import re
from src.services.chat_tools.base import BaseTool, ToolMetadata
from src.services.chat_response import ChatResponse
from typing import Optional


class FindTool(BaseTool):
    """Tool that finds photos matching a description using vector embeddings."""
    
    metadata = ToolMetadata(
        command="/find",
        name="Find",
        description="Finds photos matching the description",
        help_text="/find <number> <description> - Finds photos matching the description (default: 10)",
        usage="/find <number> <description>",
        requires_folder=True,
        arg_pattern=r'^/find\s+'
    )
    
    def execute(self, folder_path: Optional[str] = None, args: Optional[str] = None) -> ChatResponse:
        """Execute the find tool.
        
        Uses vector embeddings to find photos matching the description.
        
        Args:
            folder_path: The folder path to search in
            args: The search description (and optional limit)
            
        Returns:
            ChatResponse with matching photos or error
        """
        if not args:
            return ChatResponse(
                status="error",
                response="Please provide a description to search for.",
                sender="assistant",
                model="N/A"
            )
        
        description = args.strip()
        
        # Parse limit from description - look for number at the beginning
        # Pattern: 5 cats, 10 dogs, etc.
        limit = 10  # Default limit
        match = re.match(r'^(\d+)\s+(.+)$', description)
        if match:
            try:
                limit = int(match.group(1))
                description = match.group(2).strip()
            except ValueError:
                # If the first part isn't a valid number, ignore it
                pass
        
        if not description:
            return ChatResponse(
                status="error",
                response="Please provide a description to search for.",
                sender="assistant",
                model="N/A"
            )
        
        try:
            from src.sidecar.database.db import FeaturesDatabase
            from src.embeddings import create_generator
            
            db_path = FeaturesDatabase.default_db_path(folder_path)
            db = FeaturesDatabase(db_path)
            
            # Generate embedding from the description text
            generator = create_generator(
                backend=self.config.embedding_backend,
                host=self.config.llm_host,
                port=self.config.llm_port,
                model=self.config.embedding_model,
                timeout=self.config.timeout,
            )
            query_vector = generator.generate_from_text(description)
            
            # Find similar photos using REST-based search with the parsed limit
            results = db.find_similar_rest(query_vector, self.config.embedding_model, limit=limit)
            db.close()
            
            if results:
                response_data = {
                    "type": "photos",
                    "count": len(results),
                    "limit": limit,
                    "photos": [{"path": p, "score": s} for p, s in results[:limit]]
                }
                return ChatResponse(
                    status="success",
                    response=response_data,
                    response_type="photos",
                    sender="assistant",
                    model="N/A"
                )
            else:
                return ChatResponse(
                    status="success",
                    response="No matching photos found.",
                    sender="assistant",
                    model="N/A"
                )
        except Exception as e:
            import logging
            import traceback
            logger = logging.getLogger(__name__)
            logger.error(f"Error finding photos: {e}")
            logger.error(traceback.format_exc())
            return ChatResponse(
                status="error",
                response=f"Failed to find photos: {str(e)}",
                sender="assistant",
                model="N/A"
            )
