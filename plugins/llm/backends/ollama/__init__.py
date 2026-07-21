from plugins.llm.registry import register_backend


def _ollama_factory(**kwargs):
    from plugins.llm.ollama import OllamaPhotoExtractor
    return OllamaPhotoExtractor(**kwargs)


register_backend("ollama", _ollama_factory)
